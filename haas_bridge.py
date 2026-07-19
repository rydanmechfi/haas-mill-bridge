#!/usr/bin/env python3
"""Haas Super Mini Mill -> Home Assistant bridge.

Polls the mill's built-in MTConnect agent (port 8082) and, for the handful
of values MTConnect doesn't expose (spindle load, active tool number, power
-on time, tool-change count, run mode), its Ethernet Q-Commands/MDC socket
(port 5051), then pushes everything into Home Assistant over REST.

Runs on its own always-on host (a small Proxmox LXC, per Shop_Assistant's
CLAUDE.md "Haas Super Mini Mill" section) -- not on the HA host itself, not
inside HA's own process. Read-only towards the mill throughout: qcommand.py
has no write/E-command method.

Usage:
  python haas_bridge.py                # run the poll loop forever
  python haas_bridge.py --once          # single poll cycle, for dry-running/debugging
"""

import argparse
import datetime
import logging
import os
import time

from catalog import build_mdc_catalog, build_mtconnect_catalog
from favorites import build_favorites
from ha_client import HAError, HAPushClient, get_token
from mtconnect import MTConnectClient, MTConnectError
from qcommand import QCommandError, QCommandSession
from tool_table import build_tool_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("haas_bridge")


def poll_once(mtc: MTConnectClient, haas_host: str, mdc_port: int, ha: HAPushClient) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        current = mtc.current()
        mtconnect_ok = True
    except MTConnectError as e:
        log.warning("MTConnect unreachable: %s", e)
        current = {}
        mtconnect_ok = False

    # One connection per poll cycle, reused for every Q-command query this
    # cycle needs -- opening a fresh connection per query eventually tripped
    # the mill's own MDC connection limit (see qcommand.py).
    try:
        with QCommandSession(haas_host, mdc_port) as session:
            mdc_catalog = build_mdc_catalog(session)
    except QCommandError as e:
        log.warning("MDC unreachable: %s", e)
        mdc_catalog = {}
    mdc_ok = not all(k.endswith("_error") for k in mdc_catalog) if mdc_catalog else False

    ha.post_state(
        "binary_sensor.haas_mill_bridge_online",
        "on" if mtconnect_ok else "off",
        {"mtconnect_ok": mtconnect_ok, "mdc_ok": mdc_ok, "last_poll": now},
    )

    if not mtconnect_ok:
        return  # keep last-known-good values on every other entity this cycle

    mtconnect_catalog = build_mtconnect_catalog(current)
    ha.post_state("sensor.haas_mill_mtconnect_catalog", now, mtconnect_catalog)
    ha.post_state("sensor.haas_mill_mdc_catalog", now, mdc_catalog)

    for entity_id, (state, attrs) in build_favorites(mtconnect_catalog, mdc_catalog).items():
        ha.post_state(entity_id, state, attrs)

    tools = build_tool_table(current)
    ha.post_state("sensor.haas_mill_tool_table", now, {"tools": tools, "tool_count": len(tools)})
    ha.post_state("binary_sensor.haas_mill_tool_table_refresh_error", "off", {"last_refresh": now})

    log.info(
        "poll ok: run_status=%s program=%s tools=%d",
        mtconnect_catalog.get("run_status"),
        mtconnect_catalog.get("program"),
        len(tools),
    )


def check_refresh_button(ha: HAPushClient, last_seen):
    """Returns (pressed_since_last_check, new_last_seen). An input_button's
    HA state IS the ISO timestamp of its last press, so a changed value
    means "pressed since we last looked" -- no separate flag needed."""
    state = ha.get_state("input_button.haas_mill_refresh_tool_table")
    if state is None:
        return False, last_seen
    ts = state.get("state")
    if ts and ts not in ("unknown", "unavailable") and ts != last_seen:
        return True, ts
    return False, last_seen


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--haas-host", default=os.environ.get("HAAS_HOST", "10.0.10.243"))
    p.add_argument("--ha-host", default=os.environ.get("HA_HOST", "10.0.10.101:8123"))
    p.add_argument("--mtconnect-port", type=int, default=int(os.environ.get("MTCONNECT_PORT", "8082")))
    p.add_argument("--mdc-port", type=int, default=int(os.environ.get("MDC_PORT", "5051")))
    p.add_argument("--poll-interval", type=float, default=float(os.environ.get("POLL_INTERVAL_S", "30")))
    p.add_argument(
        "--button-poll-interval", type=float, default=float(os.environ.get("BUTTON_POLL_INTERVAL_S", "5"))
    )
    p.add_argument("--token", help="HA long-lived access token (else $HA_TOKEN or .ha_token)")
    p.add_argument("--once", action="store_true", help="run a single poll cycle and exit")
    args = p.parse_args()

    mtc = MTConnectClient(args.haas_host, args.mtconnect_port)
    ha = HAPushClient(args.ha_host, get_token(args.token))

    if args.once:
        poll_once(mtc, args.haas_host, args.mdc_port, ha)
        return

    last_button_ts = None
    last_poll = 0.0
    while True:
        pressed, last_button_ts = check_refresh_button(ha, last_button_ts)
        now = time.monotonic()
        if pressed or (now - last_poll) >= args.poll_interval:
            try:
                poll_once(mtc, args.haas_host, args.mdc_port, ha)
            except HAError as e:
                log.error("HA push failed: %s", e)
            last_poll = now
        time.sleep(args.button_poll_interval)


if __name__ == "__main__":
    main()
