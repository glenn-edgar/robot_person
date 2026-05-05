"""Discord webhook HTTP client.

Thin urllib wrapper around the channel webhook URL. POST a JSON
payload (content + username), get back HTTP 204 No Content on success.
No discord.py / aiohttp dependency — webhooks are vanilla HTTPS.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def post_message(
    webhook_url: str,
    payload: dict,
    timeout_s: float = 5.0,
) -> tuple[bool, str | None]:
    """POST a JSON payload to a Discord webhook URL.

    Returns (ok, error_msg). Discord returns HTTP 204 on success;
    common failures surface as 401 (bad webhook), 404 (deleted), 429
    (rate-limited — body has retry_after seconds), or network errors.
    """
    data = json.dumps(payload).encode("utf-8")
    # Discord's Cloudflare edge rejects the default `Python-urllib/3.x`
    # User-Agent with HTTP 403 (error 1010); send an identified UA per
    # Discord's API guidelines for webhooks.
    req = urllib.request.Request(
        webhook_url,
        method="POST",
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "farm_robot-discord-skill/1.0 (+https://example.invalid)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            # 204 No Content on success; 200 if wait=true was set (we don't).
            if 200 <= resp.status < 300:
                return True, None
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")[:240]
        except Exception:
            body = ""
        return False, f"HTTP {e.code} {e.reason}: {body}"
    except urllib.error.URLError as e:
        return False, f"URL error: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
