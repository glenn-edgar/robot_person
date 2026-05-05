"""TTN v3 storage API client.

Thin urllib wrapper around the TTN storage integration's
`uplink_message` endpoint. Returns the raw response body (SSE or
NDJSON depending on Accept header). Parsing lives in `decoder.py`.

Pure stdlib — no `requests` dependency, since this runs on resource-
constrained farm hardware.
"""

from __future__ import annotations

import urllib.error
import urllib.request


class TTNStorageClient:
    """Pulls historical uplinks from a TTN application's storage integration."""

    def __init__(
        self,
        url_base: str,
        app_name: str,
        url_after: str,
        bearer_token: str,
        limit: int = 200,
    ):
        self.url_base = url_base
        self.app_name = app_name
        self.url_after = url_after
        self.bearer_token = bearer_token
        self.limit = limit

    def _request_url(self, after: str) -> str:
        return (
            f"{self.url_base}{self.app_name}{self.url_after}"
            f"limit={self.limit}&after={after}"
        )

    def fetch(self, after: str) -> tuple[str, bool, str | None]:
        """GET uplinks received after `after` (RFC3339 timestamp).

        Returns (body_text, ok, error_msg). On any network or HTTP
        error, returns ("", False, "<reason>") so the caller can
        surface the cause in logs.
        """
        url = self._request_url(after)
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "text/event-stream",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.read().decode("utf-8", errors="replace"), True, None
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                body = ""
            return "", False, f"HTTP {e.code} {e.reason}: {body}"
        except urllib.error.URLError as e:
            return "", False, f"URL error: {e.reason}"
        except Exception as e:  # noqa: BLE001
            return "", False, f"{type(e).__name__}: {e}"
