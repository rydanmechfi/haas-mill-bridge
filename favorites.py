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

    # Primary signal: #12018, discrete output "COOLANT_PUMP_MOTOR" -- the
    # actual relay state (confirmed live 2026-08-02 against the control's
    # own DIAGNOSTICS -> I/O tab), so unlike active_mcodes below it catches
    # coolant toggled manually at the panel, not just from a running
    # program. Should only ever read 0.0 or 1.0; one earlier one-off read
    # of 23.0 (never repeated) looked like a comms glitch, so anything
    # other than a clean 0/1 is treated as untrustworthy for this cycle
    # rather than taken at face value.
    coolant_pump_raw = mdc.get("coolant_pump_motor")
    coolant_relay_reading = None
    if coolant_pump_raw is not None:
        try:
            val = float(coolant_pump_raw)
            if val in (0.0, 1.0):
                coolant_relay_reading = val == 1.0
        except (TypeError, ValueError):
            pass

    # Fallback signal: active_mcodes, a short (~4-entry) MTConnect window,
    # oldest first -- NOT just a "currently on" flag. Confirmed live
    # 2026-08-02: right after a coolant restart it read "05,09,08,03" (M09
    # off, THEN M08 on, both still in the window at once). Whichever of
    # 07/08/09 appears LAST (rightmost/most recent) is the real current
    # state. Absent entirely (confirmed during a long idle stretch:
    # "05,05,30,05", no 07/08/09 at all) = off, it ages out once other
    # M-codes push it out of the window. Used only when the relay reading
    # above is unavailable/glitchy for this cycle -- it's blind to manual
    # panel coolant use, which is exactly the gap #12018 fixes.
    active_mcodes = [c.strip() for c in mtconnect.get("active_mcodes", "").split(",")]
    coolant_codes_seen = [c for c in active_mcodes if c in ("07", "08", "09")]
    mcode_reading = bool(coolant_codes_seen) and coolant_codes_seen[-1] != "09"

    if coolant_relay_reading is not None:
        coolant_running, coolant_source = coolant_relay_reading, "mdc_relay"
    else:
        coolant_running, coolant_source = mcode_reading, "mtconnect_mcode_fallback"

    out["binary_sensor.haas_mill_coolant_running"] = (
        "on" if coolant_running else "off",
        {
            "data_source": coolant_source,
            "coolant_pump_motor_raw": coolant_pump_raw,
            "active_mcodes": mtconnect.get("active_mcodes", ""),
        },
    )

    # Coolant level (#13013, raw sensor units) -> 0-100%. SINGLE-POINT
    # calibration, not a proper two-point curve: user read the control's
    # own native Coolant Display gauge on 2026-08-02 at raw 2891 = 60%,
    # which is the only real-world reference point so far. Assumes a true
    # zero baseline (raw 0 == empty) to derive the 100% raw value --
    # reasonable for a simple level sensor, but unverified at either
    # extreme. Refine with a second reading (e.g. right after topping off
    # to full, or if it's ever visibly near empty) rather than trusting
    # this scale precisely; clamped to 0-100 so a reading past the
    # projected 100% (plausible if the true curve isn't linear that far)
    # doesn't display as a nonsensical >100%.
    coolant_level_raw = mdc.get("coolant_level_raw")
    if coolant_level_raw is not None:
        RAW_AT_100PCT = 2891 / 0.60
        try:
            pct = max(0.0, min(100.0, float(coolant_level_raw) / RAW_AT_100PCT * 100))
            out["sensor.haas_mill_coolant_level"] = (
                f"{pct:.0f}",
                {
                    "data_source": "mdc",
                    "unit_of_measurement": "%",
                    "raw_value": coolant_level_raw,
                    "calibration": "single-point 2026-08-02: raw 2891 = 60%, assumes zero baseline",
                },
            )
        except (TypeError, ValueError):
            pass

    # Coolant temperature (#13014, raw sensor units) -- NO calibration
    # reference exists yet (unlike coolant level, there's no native
    # on-screen gauge to cross-check against), so this is exposed as an
    # explicitly raw/uncalibrated value rather than guessing a °F or °C
    # conversion. Currently reads a suspiciously low "3", which may mean
    # this sensor isn't populated/wired on this machine -- don't trust it
    # as a real temperature until there's a way to cross-check it.
    coolant_temp_raw = mdc.get("coolant_temperature_raw")
    if coolant_temp_raw is not None:
        out["sensor.haas_mill_coolant_temperature_raw"] = (
            coolant_temp_raw,
            {"data_source": "mdc", "calibration": "uncalibrated -- raw sensor units, not a real temperature yet"},
        )
    return out
