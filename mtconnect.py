"""HTTP/XML client for the Haas NGC's built-in MTConnect agent (port 8082).

Confirmed live 2026-07-18 against a real Super Mini Mill: /probe and
/current both respond on port 8082 (NOT 5000, which some community code
assumes -- 5000 didn't respond at all here). This control's agent is
unusually rich: it exposes the entire 200-slot tool table (length/diameter
geometry+wear, flutes, tool type, approx dimensions, pocket, etc.) as flat
comma-separated EVENT/MESSAGE data items, not just execution/spindle/alarm
telemetry. See Shop_Assistant's CLAUDE.md, "Haas Super Mini Mill" section,
for the confirmed data-item list and cross-validation notes.
"""

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


class MTConnectError(Exception):
    pass


class MTConnectClient:
    def __init__(self, host: str, port: int = 8082, timeout: float = 10.0):
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def _get(self, path: str) -> ET.Element:
        url = f"{self.base}{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                return ET.fromstring(resp.read())
        except (urllib.error.URLError, ET.ParseError) as e:
            raise MTConnectError(f"GET {url} -> {e}") from e

    def probe(self) -> ET.Element:
        """Raw /probe tree -- data-item discovery. Not used by the running
        bridge; call this manually when re-verifying haas_params.py against
        a control software update."""
        return self._get("/probe")

    def current(self) -> dict:
        """Return {dataItemId: value} for every data item in the /current
        snapshot, regardless of namespace or nesting depth.

        Two shapes need special handling, both confirmed live:

        - CONDITION-category items (e.g. "mcond") carry no useful text of
          their own -- MTConnect represents their state as the element's
          own tag name (<Normal/>, <Fault .../>, etc.), identified
          structurally by living inside a <Condition> container (checked
          via a parent map, not by "text happens to be empty" -- that
          heuristic is wrong, see below).
        - Some MESSAGE items nest structured data instead of plain text --
          confirmed on "aalarms": clear is `<Message>NO ACTIVE
          ALARMS</Message>` (plain text), but an active alarm is
          `<Message><Haas><Alarms><Alarm>2075 AXIS LUBRICATION RESERVOIR
          EMPTY</Alarm></Alarms></Haas></Message>` (nested, .text is empty
          even though there's real content underneath). `elem.itertext()`
          walks all descendant text regardless of nesting depth, which
          handles this generically without hardcoding the Haas/Alarms/Alarm
          path -- collapsed through `" ".join(text.split())` to flatten the
          indentation whitespace itertext() picks up between tags.
        """
        root = self._get("/current")
        parent_map = {child: parent for parent in root.iter() for child in parent}

        def in_condition_container(elem) -> bool:
            node = elem
            while node in parent_map:
                node = parent_map[node]
                if node.tag.split("}")[-1] == "Condition":
                    return True
            return False

        values: dict = {}
        for elem in root.iter():
            item_id = elem.get("dataItemId")
            if item_id is None:
                continue
            if in_condition_container(elem):
                values[item_id] = elem.tag.split("}")[-1]  # Normal/Warning/Fault/Unavailable
            else:
                values[item_id] = " ".join("".join(elem.itertext()).split())
        return values
