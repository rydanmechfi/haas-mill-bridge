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

    # M08 (flood) or M07 (mist) present in the active-mcodes list = coolant
    # running. See haas_params.py's comment on "active_mcodes" for how this
    # was cross-validated against a real on/off transition -- M09 (coolant
    # off) is never itself listed, the codes for flood/mist just drop out
    # of the list entirely once coolant stops, so no "off" code to check.
    active_mcodes = [c.strip() for c in mtconnect.get("active_mcodes", "").split(",")]
    coolant_running = "08" in active_mcodes or "07" in active_mcodes
    out["binary_sensor.haas_mill_coolant_running"] = (
        "on" if coolant_running else "off",
        {"data_source": "mtconnect", "active_mcodes": mtconnect.get("active_mcodes", "")},
    )
    return out
