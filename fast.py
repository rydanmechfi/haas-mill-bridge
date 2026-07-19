"""Fast-tier poll: just the two genuinely rapidly-changing values (spindle
RPM via MTConnect, spindle load via a single Q-command read), pushed on a
much shorter interval than the full health/tool-table cycle.

Deliberately minimal -- a lone Q-command connection every few seconds is
nowhere near the connection-burst limit found empirically 2026-07-19: a
quick back-to-back test against the real mill showed roughly a dozen rapid
connections succeed, then the next one just hangs until timeout. That's
almost certainly what eventually broke the original one-connection-per
-query design (5 connections fired with no spacing between them, every 30s,
for hours) -- a single connection spaced multiple real seconds apart isn't
close to that failure mode.
"""

from mtconnect import MTConnectError
from qcommand import QCommandError, QCommandSession


def poll_fast(mtc, haas_host: str, mdc_port: int, ha) -> None:
    try:
        current = mtc.current()
    except MTConnectError:
        current = None
    if current is not None:
        speed = current.get("sspeed")
        if speed is not None:
            ha.post_state(
                "sensor.haas_mill_spindle_speed",
                f"{float(speed):.0f}",
                {"data_source": "mtconnect"},
            )

    try:
        with QCommandSession(haas_host, mdc_port) as session:
            load = session.read_macro(1098)
    except QCommandError:
        return
    ha.post_state(
        "sensor.haas_mill_spindle_load",
        f"{load:.1f}",
        {"data_source": "mdc", "unit_of_measurement": "%"},
    )
