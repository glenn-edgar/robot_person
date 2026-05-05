"""skills.discord — post messages to a Discord channel via webhook.

Per the skills convention (skills/README.md): one class + __main__
test driver. Engine-agnostic.

Public class:
  DiscordNotifier — `__init__(webhook_url, ...)` + `send(content, ...)`
                    returning (ok, error_msg).

Helper module:
  webhook_client.py — urllib-based POST.

Discord webhook content limit is 2000 chars. Longer content is
truncated with a trailing ellipsis; the truncation is logged so the
caller can decide whether to split into multiple messages.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Callable, Optional

from .webhook_client import post_message


CONTENT_MAX = 2000


class DiscordNotifier:
    """Sends plain-text messages to a Discord channel via webhook URL.

    The webhook URL itself carries the auth (anyone who has it can post
    to that channel), so it's secret-equivalent and should live in a
    gitignored env file.

    Pass a `logger` callable (str -> None) to receive step-by-step
    diagnostics: payload size, HTTP outcome, truncation events.
    """

    def __init__(
        self,
        webhook_url: str,
        default_username: str = "farm_robot",
        timeout_s: float = 5.0,
        logger: Optional[Callable[[str], None]] = None,
        _post: Optional[Callable] = None,
    ):
        if not webhook_url:
            raise ValueError("DiscordNotifier: webhook_url is required")
        self.webhook_url = webhook_url
        self.default_username = default_username
        self.timeout_s = timeout_s
        self.logger = logger or (lambda msg: None)
        # `_post` injection point so tests can stub HTTP without monkeypatching.
        self._post = _post or post_message

    def _build_payload(self, content: str, username: Optional[str]) -> dict:
        """Construct the JSON body Discord expects. Truncates long content."""
        if len(content) > CONTENT_MAX:
            self.logger(
                f"discord: content {len(content)} chars > {CONTENT_MAX}, truncating"
            )
            content = content[: CONTENT_MAX - 3] + "..."
        return {
            "content": content,
            "username": username or self.default_username,
        }

    def send(
        self,
        content: str,
        *,
        username: Optional[str] = None,
    ) -> tuple[bool, str | None]:
        """Post one message. Returns (ok, error_msg)."""
        if not content:
            self.logger("discord: send refused — content is empty")
            return False, "content is empty"
        payload = self._build_payload(content, username)
        self.logger(
            f"discord: POSTing {len(payload['content'])} chars "
            f"as {payload['username']!r}"
        )
        ok, err = self._post(self.webhook_url, payload, self.timeout_s)
        if ok:
            self.logger("discord: 204 OK (message sent)")
        else:
            self.logger(f"discord: send FAILED — {err}")
        return ok, err


if __name__ == "__main__":
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print(
            "DISCORD_WEBHOOK_URL not set; export it (or add to "
            "robots/<robot>/secrets/ttn.env) and re-run.",
            file=sys.stderr,
        )
        sys.exit(2)
    notif = DiscordNotifier(url, logger=print)
    ts = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    ok, err = notif.send(
        f"discord skill smoke test — {ts} (skills.discord.main __main__)"
    )
    print(f"final: ok={ok} err={err}")
    sys.exit(0 if ok else 1)
