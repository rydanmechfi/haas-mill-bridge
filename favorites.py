"""Promote a small curated subset of catalog values to individual
first-class sensor/binary_sensor entities, since HA tile/gauge/conditional
cards need real entities to point at, not another entity's attributes.

This is a starting point, not a final list -- adding a favorite is adding a
line here, not new plumbing. See Shop_Assistant's docs/shop-dashboard.yaml
"Haas Mill Status" section for where these land.
"""


def build_favorites(mtconnect: dict, mdc: dict) -> dict:
    """Returns {entity_id: (state, attributes)}."""
    alarms = mtconnect.get("active_alarms", "")
    condition = mtconnect.get("machine_condition", "Normal")
    has_alarm = condition != "Normal" or bool(alarms) and alarms != "NO ACTIVE ALARMS"

    run_status = mtconnect.get("run_status", "unknown")
    state_label = f"ALARM: {alarms}" if has_alarm else run_status

    out = {
        "sensor.haas_mill_state": (state_label, {"data_source": "mtconnect"}),
        "sensor.haas_mill_program_name": (
            mtconnect.get("program", "unknown"),
            {"data_source": "mtconnect"},
        ),
        "sensor.haas_mill_spindle_speed": (
            mtconnect.get("spindle_speed_rpm", "unknown"),
            {"data_source": "mtconnect", "unit_of_measurement": "RPM"},
        ),
        "binary_sensor.haas_mill_alarm": (
            "on" if has_alarm else "off",
            {"data_source": "mtconnect", "alarm_text": alarms},
        ),
    }
    if "active_tool_number" in mdc:
        out["sensor.haas_mill_active_tool"] = (mdc["active_tool_number"], {"data_source": "mdc"})
    if "spindle_load_pct" in mdc:
        out["sensor.haas_mill_spindle_load"] = (
            mdc["spindle_load_pct"],
            {"data_source": "mdc", "unit_of_measurement": "%"},
        )

    # active_mcodes is a short (~4-entry) window, oldest first -- NOT just a
    # "currently on" flag. Confirmed live 2026-08-02: right after a coolant
    # restart it read "05,09,08,03" (M09 off, THEN M08 on, both still in the
    # window at once). Whichever of 07/08/09 appears LAST (rightmost/most
    # recent) is the real current state; just checking "is 08 present
    # anywhere" would misread a quick off-then-on-again (or the reverse) if
    # both ends are still in the window. Absent entirely (confirmed during a
    # long idle stretch: "05,05,30,05", no 07/08/09 at all) = off, it ages
    # out once other M-codes push it out of the window.
    active_mcodes = [c.strip() for c in mtconnect.get("active_mcodes", "").split(",")]
    coolant_codes_seen = [c for c in active_mcodes if c in ("07", "08", "09")]
    coolant_running = bool(coolant_codes_seen) and coolant_codes_seen[-1] != "09"
    out["binary_sensor.haas_mill_coolant_running"] = (
        "on" if coolant_running else "off",
        {"data_source": "mtconnect", "active_mcodes": mtconnect.get("active_mcodes", "")},
    )
    return out
