"""Verified Haas Super Mini Mill (NGC) parameter catalog.

Every mapping below was confirmed live against the real machine on
2026-07-18 (serial 1213067, software REL-100.24.000.1111, MTConnect device
"SMINIMILL") -- see CLAUDE.md's "Haas Super Mini Mill" section for the raw
recon output and cross-validation notes (e.g. tool 1's gauge length read
identically via both interfaces: 97.69856mm via MTConnect, 3.8464in via
Q600 #2001). Nothing here is guessed from external docs; anything that
didn't come back with a sane, cross-checkable value during recon was left
out rather than wired in speculatively.

Column/data-item names intentionally match the mill's own NGC MTConnect
data-item IDs and macro-variable numbers so this file can be re-verified
against a fresh /probe or Q-command sweep without translation.
"""

# --- MTConnect (port 8082), tool table -------------------------------------
# Each value is a comma-separated 200-element array in one /current
# response -- no per-tool Q-command reads needed. `tool_type` is a string
# enum (END_MILL/TAP/DRILL/...); every other column is numeric.
MTCONNECT_TOOL_COLUMNS = {
    "gauge_length": "lengthgeo",  # "Length Geometry (H)" on the control -- THIS is Gauge Length
    "length_wear": "lengthwear",
    "diameter_geometry": "diamgeo",
    "diameter_wear": "diamwear",
    "flutes": "flutes",
    "actual_diameter": "actualdiam",
    "tool_type": "tooltype",
    "tool_material": "toolmaterial",
    "approx_length": "approxlength",
    "approx_diameter": "approxdiam",
    "edge_measure": "edgemeasure",
    "tool_tolerance": "toolclearance",
    "probe_type": "probetype",
    "pocket": "pocket",
}

# Tool table columns confirmed to NOT exist anywhere on the network (full
# /probe scanned, nothing matched) -- Tool ID, Description, Category. Almost
# certainly UI-only text fields with no network-exposed backing register.

TOOL_TABLE_MAX = 200  # the control's real storage capacity (physical carousel is 30)

# --- MTConnect (port 8082), health/status -----------------------------------
# `machine_condition` is CONDITION-category: MTConnectClient.current()
# returns the element's own tag name (Normal/Warning/Fault) as the value,
# since condition items carry no useful text content.
MTCONNECT_HEALTH_ITEMS = {
    "availability": "avail",
    "machine_condition": "mcond",
    "active_alarms": "aalarms",
    "mode": "mode",
    "run_status": "rstat",
    "program": "ncprog",
    "emergency_stop": "estop",
    "rapid_override_pct": "rovrd",
    "feedrate_override_pct": "fdovrd",
    "spindle_speed_override_pct": "ssovrd",
    "spindle_speed_rpm": "sspeed",
    "this_cycle_s": "tcycle",
    "last_cycle_s": "lcycle",
    "cycle_remaining_s": "cyremtim",
    "x_position_mm": "x_axis_actual_position",
    "y_position_mm": "y_axis_actual_position",
    "z_position_mm": "z_axis_actual_position",
    "work_offset_g54": "g54",  # comma list: X,Y,Z,A,B,C
    "work_offset_g55": "g55",
    "work_offset_g56": "g56",
    "work_offset_g57": "g57",
    "work_offset_g58": "g58",
    "work_offset_g59": "g59",
    "live_tool_number": "sp3number",
    # "dhmtcodes" (raw MTConnect name "DHMT_Codes", under the Activecodes
    # component) -- comma list of currently-latched M-codes, e.g.
    # "03,04,08,26". Confirmed live 2026-08-01/08-02 by cross-checking a
    # real coolant on/off transition: with flood coolant running the list
    # contained "08" (M08); once coolant stopped it read "05,05,30,05" (no
    # "08", but "05" showed up matching the spindle also stopping - M05).
    # This is the actual live signal -- the <Coolant> MTConnect component's
    # own items (tsc/hpc/clntspigot/showerclnt/mist/pulsejet/tab, all under
    # dataItemId "coolant") looked promising by name but are STATIC
    # machine-config/purchased-option flags: their timestamps never moved
    # across that same test, confirmed dead ends, deliberately not used.
    "active_mcodes": "dhmtcodes",
}

# --- Ethernet Q-Commands / MDC (port 5051) ----------------------------------
# Only the values MTConnect doesn't expose at all. (command, macro_var):
# macro_var set -> read via `?Q600 <var>`; macro_var None -> the command
# itself returns one labeled field (e.g. `?Q300` -> "P.O. TIME, ...").
MDC_ITEMS = {
    "spindle_load_pct": ("Q600", 1098),
    "active_tool_number": ("Q600", 3026),
    "power_on_time": ("Q300", None),
    "tool_change_count": ("Q200", None),
    "run_mode": ("Q104", None),
}

# #3020/#3021 were tried as power-on/cycle time candidates during recon and
# do NOT reconcile with Q300's own "P.O. TIME" value (off by ~164 hours) --
# deliberately excluded. Use MDC_ITEMS["power_on_time"] (Q300) instead.
