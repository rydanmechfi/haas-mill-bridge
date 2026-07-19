"""Raw TCP client for the Haas Ethernet Q-Commands / MDC interface (port 5051).

Confirmed live 2026-07-18 against a real Super Mini Mill (see
Shop_Assistant's CLAUDE.md, "Haas Super Mini Mill" section, for the full
recon writeup): Setting 143 was already enabled, both bare `\n` and `\r\n`
terminators work, and single-value responses come back as
`>>LABEL, VALUE\r\n>`. Aggregate commands (Q100/Q200/Q300/Q104) return one
labeled field each on this control's software version, not the multi-field
bundles some outside docs describe -- don't assume otherwise without
re-checking live.

One persistent connection per poll cycle, NOT one connection per query.
The original design opened a fresh connection for every single query on
the theory that MTConnect covers most things and only ~5 Q-command reads
happen per cycle, so the overhead wouldn't matter. It did: after the bridge
had been running continuously for a while, the mill's own MDC server
started responding with "Too many connections. Disconnecting." -- confirmed
2026-07-19. `QCommandSession` fixes this by reusing one connection for
every query made inside a `with` block; response framing (every reply ends
with a bare `>` prompt byte, confirmed live: `>>MACRO, 3.8464\r\n>`) makes
this straightforward -- read until the buffer ends with `>` instead of
waiting for the connection to close, since the connection is now meant to
stay open between commands.

Read-only by construction: there is no write/E-command method here.
"""

import socket


class QCommandError(Exception):
    pass


def _parse_response(raw: str) -> dict:
    """Parse `>>LABEL, VALUE\r\n>...` into {LABEL: VALUE}. Lines that don't
    parse into an even number of comma-separated LABEL/VALUE pairs (e.g.
    Q500's plain "STATUS BUSY") are kept verbatim under "_raw" for
    debugging rather than dropped."""
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


class QCommandSession:
    """One TCP connection, reused for every query made inside a `with`
    block. Open a fresh session per poll cycle -- don't hold one open
    across cycles (untested territory, and there's no need to: a poll
    cycle's handful of queries take well under a second)."""

    def __init__(self, host: str, port: int = 5051, timeout: float = 4.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def __enter__(self) -> "QCommandSession":
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise QCommandError(f"connect {self.host}:{self.port} -> {e}") from e
        return self

    def __exit__(self, *exc) -> None:
        if self.sock is not None:
            self.sock.close()

    def query(self, command: str) -> dict:
        assert self.sock is not None, "QCommandSession used outside a 'with' block"
        try:
            self.sock.sendall(command.encode("ascii") + b"\r\n")
            buf = b""
            while not buf.endswith(b">"):
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
        except OSError as e:
            raise QCommandError(f"{command} -> {e}") from e
        return _parse_response(buf.decode("ascii", errors="replace"))

    def read_macro(self, var: int) -> float:
        fields = self.query(f"?Q600 {var}")
        raw = fields.get("MACRO")
        if raw is None:
            raise QCommandError(f"?Q600 {var} returned no MACRO field: {fields}")
        return float(raw)
