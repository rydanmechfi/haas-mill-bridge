"""Build the two browsable "catalog" sensors -- every confirmed-readable
parameter, dumped as attributes on one entity per source so it's fully
inspectable (Developer Tools -> States, or the full-catalog markdown card on
the Haas dashboard) without needing a dedicated HA entity per parameter.

See haas_params.py for the confirmed item lists this pulls from. Anything
not listed there was checked during Phase 0 recon (2026-07-18) and found
absent/dead on this control -- deliberately left out rather than pushed as
a placeholder that would just read "unknown".

Presentation transforms (unit conversion, rounding) happen here rather than
in haas_params.py, which documents the raw MTConnect source of truth.
Requested 2026-07-19: axis positions in inches to 4 decimal places instead
of raw millimeters (and instead of the floating-point noise MTConnect
reports for a nominally-zero axis, e.g. "-2.56e-14"), spindle speed rounded
to a whole RPM instead of MTConnect's raw fractional value.
"""

from haas_params import MDC_ITEMS, MTCONNECT_HEALTH_ITEMS

# friendly (mm) key -> friendly (in) key, for the axis-position fields
_INCH_POSITION_KEYS = {
    "x_position_mm": "x_position_in",
    "y_position_mm": "y_position_in",
    "z_position_mm": "z_position_in",
}


def build_mtconnect_catalog(current: dict) -> dict:
    out = {}
    for friendly, item_id in MTCONNECT_HEALTH_ITEMS.items():
        if item_id not in current:
            continue
        value = current[item_id]
        if friendly in _INCH_POSITION_KEYS:
            out[_INCH_POSITION_KEYS[friendly]] = f"{float(value) / 25.4:.4f}"
        elif friendly == "spindle_speed_rpm":
            out[friendly] = f"{float(value):.0f}"
        else:
            out[friendly] = value
    return out


def build_mdc_catalog(session) -> dict:
    """`session` is an open QCommandSession (see qcommand.py) -- every call
    here reuses that one connection, not a fresh one per query."""
    out = {}
    for friendly, (command, macro_var) in MDC_ITEMS.items():
        try:
            if macro_var is not None:
                out[friendly] = session.read_macro(macro_var)
            else:
                fields = session.query(f"?{command}")
                out[friendly] = next(iter(fields.values()), None)
        except Exception as e:
            out[f"{friendly}_error"] = str(e)
    return out
