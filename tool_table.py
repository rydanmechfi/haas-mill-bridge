"""Parse the mill's full 200-slot tool table out of a single MTConnect
/current response -- no Q-command sweep needed, since every confirmed
column comes back as one flat comma-separated array per data item (see
haas_params.py / Shop_Assistant's CLAUDE.md for how this was confirmed).

Returns all 200 slots, populated or not -- filtering to "tools actually in
use" is a dashboard-side concern (skip rows where gauge_length is 0), not a
bridge concern, so the data stays complete for anyone who wants the full
200-tool library view.
"""

from haas_params import MTCONNECT_TOOL_COLUMNS, TOOL_TABLE_MAX


def build_tool_table(current: dict) -> list:
    columns = {}
    for friendly, item_id in MTCONNECT_TOOL_COLUMNS.items():
        raw = current.get(item_id)
        if raw is None:
            continue
        values = [v.strip() for v in raw.split(",")]
        if friendly != "tool_type":
            values = [float(v) for v in values]
        columns[friendly] = values

    tools = []
    for i in range(TOOL_TABLE_MAX):
        tool = {"number": i + 1}
        for friendly, values in columns.items():
            if i < len(values):
                tool[friendly] = values[i]
        tools.append(tool)
    return tools
