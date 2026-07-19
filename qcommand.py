"""Raw TCP client for the Haas Ethernet Q-Commands / MDC interface (port 5051).

Confirmed live 2026-07-18 against a real Super Mini Mill (see
Shop_Assistant's CLAUDE.md, "Haas Super Mini Mill" section, for the full
recon writeup): Setting 143 was already enabled, both bare `\n` and `\r\n`
terminators work, and single-value responses come back as
`>>LABEL, VALUE\r\n>`. Aggregate commands (Q100/Q200/Q300/Q104) return one
labeled field each on this control's software version, not the multi-field
bundles some outside docs describe -- don't assume otherwise without
re-checking live.

One connection per query, no persistent-socket pooling: MTConnect now
covers the tool table and most health data in a single HTTP call, so this
client only handles a handful of queries per poll cycle -- the round-trip
overhead that would justify a persistent connection never materializes.

Read-only by construction: there is no write/E-command method here.
"""

import socket


class QCommandError(Exception):
    pass


class QCommandClient:
    def __init__(self, host: str, port: int = 5051, timeout: float = 4.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send(self, command: str) -> str:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(command.encode("ascii") + b"\r\n")
                sock.settimeout(self.timeout)
                chunks = []
                try:
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                except socket.timeout:
                    pass
                return b"".join(chunks).decode("ascii", errors="replace")
        except OSError as e:
            raise QCommandError(f"{command} -> {e}") from e

    def query(self, command: str) -> dict:
        """Send a raw Q-command, return {LABEL: VALUE} parsed out of the
        `>>LABEL, VALUE\r\n>...` response. Lines that don't parse into an
        even number of comma-separated LABEL/VALUE pairs (e.g. Q500's plain
        "STATUS BUSY") are kept verbatim under "_raw" for debugging rather
        than dropped."""
        raw = self._send(command)
        fields: dict = {}
        for line in raw.split("\r\n"):
            line = line.strip().lstrip(">").strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and len(parts) % 2 == 0:
                for i in range(0, len(parts) - 1, 2):
                    fields[parts[i]] = parts[i + 1]
            else:
                fields.setdefault("_raw", []).append(line)
        return fields

    def read_macro(self, var: int) -> float:
        fields = self.query(f"?Q600 {var}")
        raw = fields.get("MACRO")
        if raw is None:
            raise QCommandError(f"?Q600 {var} returned no MACRO field: {fields}")
        return float(raw)
