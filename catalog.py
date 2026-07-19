"""Build the two browsable "catalog" sensors -- every confirmed-readable
parameter, dumped as attributes on one entity per source so it's fully
inspectable (Developer Tools -> States, or the full-catalog markdown card on
the Haas dashboard) without needing a dedicated HA entity per parameter.

See haas_params.py for the confirmed item lists this pulls from. Anything
not listed there was checked during Phase 0 recon (2026-07-18) and found
absent/dead on this control -- deliberately left out rather than pushed as
a placeholder that would just read "unknown".
"""

from haas_params import MDC_ITEMS, MTCONNECT_HEALTH_ITEMS


def build_mtconnect_catalog(current: dict) -> dict:
    return {
        friendly: current[item_id]
        for friendly, item_id in MTCONNECT_HEALTH_ITEMS.items()
        if item_id in current
    }


def build_mdc_catalog(qc) -> dict:
    out = {}
    for friendly, (command, macro_var) in MDC_ITEMS.items():
        try:
            if macro_var is not None:
                out[friendly] = qc.read_macro(macro_var)
            else:
                fields = qc.query(f"?{command}")
                out[friendly] = next(iter(fields.values()), None)
        except Exception as e:
            out[f"{friendly}_error"] = str(e)
    return out
