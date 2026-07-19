# haas-mill-bridge

Polls a Haas Super Mini Mill (NGC control) over its built-in network
interfaces and pushes machine state into Home Assistant — no HACS
integration, no MQTT broker, just a small always-on Python service and
HA's own REST API.

Born out of [Shop_Assistant](https://github.com/rydanmechfi/Shop_Assistant)
(the shop's Home Assistant / ESPHome project) needing two things from the
mill: an easy way to copy "Gauge Length" tool-offset values into a CAM
program without walking over to read the control screen, and an
at-a-glance health view (running/idle/alarm, program, spindle load, etc.)
on the shop's main dashboard.

## How it talks to the mill

Two interfaces, both built into the NGC control, confirmed live 2026-07-18
against a real machine:

- **MTConnect** (`http://<mill-ip>:8082`) — far richer than typical: this
  control's agent exposes the *entire 200-slot tool table* (gauge length,
  wear, diameter, flutes, tool type, approx dimensions, pocket, etc.) as
  flat arrays in one `/current` response, plus execution state, program,
  spindle speed, all work offsets, axis positions, overrides, alarms, and
  timers. This is the primary source for almost everything.
- **Ethernet Q-Commands / MDC** (`<mill-ip>:5051`, gated by the control's
  Setting 143) — only used for the handful of values MTConnect doesn't
  expose: spindle load, active tool number, power-on time, tool-change
  count, run mode. Read-only by construction — `qcommand.py` has no
  write/`E`-command method.

See `haas_params.py` for the exact confirmed mapping (MTConnect data-item
IDs, Q-command macro variables) and
[Shop_Assistant's CLAUDE.md](https://github.com/rydanmechfi/Shop_Assistant/blob/main/CLAUDE.md)
("Haas Super Mini Mill" section) for the full recon writeup, including how
each value was cross-validated between the two interfaces before being
trusted.

Both interfaces are cleartext and unauthenticated on the control's side
(CVE-2022-2475, CVE-2022-41636) — keep this bridge on the same isolated LAN
segment as the mill and never expose either port to the internet.

**Q-Command connections are rate-limited by the mill itself, not just by
convention.** A quick back-to-back test against the real control
(2026-07-19) showed roughly a dozen rapid connections succeed, then the
next one just hangs until timeout — almost certainly what eventually broke
an earlier version of this bridge that opened a fresh connection per query
with no spacing (`QCommandError: Too many connections. Disconnecting.`
after running for a while). `QCommandSession` (`qcommand.py`) fixes the
common case by reusing one connection for every query in a poll cycle;
don't reintroduce rapid-fire separate connections without spacing them out.

**MTConnect's streaming mode (`/sample?interval=`) is not supported on this
control** — confirmed live, returns an explicit `UNSUPPORTED` error. Only
polling works.

## What it creates in Home Assistant

Pushed via `POST /api/states/<entity_id>` using a long-lived access token:

| Entity | What |
|---|---|
| `sensor.haas_mill_mtconnect_catalog` | every confirmed MTConnect health/status value, as attributes |
| `sensor.haas_mill_mdc_catalog` | every confirmed Q-command value, as attributes |
| `sensor.haas_mill_tool_table` | all 200 tool slots (`attributes.tools`), refreshed every poll |
| `sensor.haas_mill_state` / `_program_name` / `_spindle_speed` / `_active_tool` / `_spindle_load` | curated favorites for dashboard tiles |
| `binary_sensor.haas_mill_alarm` | on when an alarm/fault condition is active |
| `binary_sensor.haas_mill_bridge_online` | connectivity — MTConnect reachable |
| `binary_sensor.haas_mill_tool_table_refresh_error` | on only when a refresh attempt failed |

Requires one HA helper created once via the UI (Settings → Devices &
Services → Helpers → Button): `input_button.haas_mill_refresh_tool_table`.
The bridge polls its state every few seconds and treats a new timestamp as
"do an immediate poll now" — though since the tool table now comes bundled
for free in the same MTConnect call as the health data, this is a manual
fast-forward, not the only way data gets refreshed (it updates on every
regular poll cycle regardless).

**Two poll tiers**: the full cycle (`POLL_INTERVAL_S`, default 30s) covers
everything above; a fast tier (`FAST_POLL_INTERVAL_S`, default 3s, see
`fast.py`) covers just `sensor.haas_mill_spindle_speed` and
`sensor.haas_mill_spindle_load` — the two values actually worth watching
move in near-real-time. Kept deliberately narrow (a lone Q-command
connection every few seconds, well clear of the burst limit noted above)
rather than dropping the whole poll interval, which would also mean
re-pushing and re-recording the 200-row tool table far more often than it
ever actually changes.

## Deploy

Runs as a `systemd` service on a small, always-on Linux host (a Proxmox
LXC, in this project's case) on the same LAN segment as the mill and Home
Assistant. Pure standard library — no `pip install` needed.

```bash
git clone https://github.com/rydanmechfi/haas-mill-bridge.git /opt/haas-mill-bridge
cd /opt/haas-mill-bridge
cp .env.example .env
# edit .env: set HA_TOKEN to a long-lived access token
#   (HA: your user -> Security -> Long-lived access tokens)

sudo useradd --system --no-create-home haas-bridge
sudo cp haas-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now haas-bridge
journalctl -u haas-bridge -f
```

## Dry-run / debug

```bash
python haas_bridge.py --once --haas-host 10.0.10.243 --ha-host 10.0.10.101:8123 --token <token>
```

Runs a single poll cycle and exits — confirm the pushed states with
`curl http://10.0.10.101:8123/api/states/sensor.haas_mill_mtconnect_catalog -H "Authorization: Bearer <token>"`
before wiring up the systemd service.
