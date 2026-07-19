"""Minimal authenticated Home Assistant REST client for pushing entity
states. Same conventions as Shop_Assistant's tools/ha_automation.py (token
resolution order, HAError shape) adapted to POST /api/states/<entity_id>
instead of the automation config endpoint -- this repo has its own token
rather than reusing Shop_Assistant's .ha_token, since it's a separate
deployed service with its own credential.

Auth is a long-lived access token (HA: your user -> Security -> Long-lived
access tokens), read from the first of: --token, the HA_TOKEN environment
variable, or a .ha_token file at this repo's root (gitignored).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def get_token(cli_token: str | None = None) -> str:
    if cli_token:
        return cli_token
    if os.environ.get("HA_TOKEN"):
        return os.environ["HA_TOKEN"]
    token_file = REPO_ROOT / ".ha_token"
    if token_file.is_file():
        return token_file.read_text().strip()
    sys.exit(
        "No token. Pass --token, set HA_TOKEN, or put a long-lived access "
        f"token in {token_file} (HA: user -> Security -> Long-lived access tokens)."
    )


class HAError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"HTTP {code}: {message}")


class HAPushClient:
    def __init__(self, host: str, token: str):
        self.base = f"http://{host}"
        self.token = token

    def _request(self, method: str, path: str, body=None):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise HAError(e.code, detail) from None
        except urllib.error.URLError as e:
            raise HAError(0, f"unreachable: {e.reason}") from None

    def post_state(self, entity_id: str, state, attributes: dict | None = None):
        body = {"state": str(state)}
        if attributes:
            body["attributes"] = attributes
        return self._request("POST", f"/api/states/{entity_id}", body=body)

    def get_state(self, entity_id: str):
        try:
            return self._request("GET", f"/api/states/{entity_id}")
        except HAError as e:
            if e.code == 404:
                return None
            raise
