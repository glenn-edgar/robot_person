"""Tests for DiscordNotifier message construction.

No real network — uses a stub `_post` to capture the payload that
would have gone to Discord.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_skill = os.path.dirname(_here)
_skills_root = os.path.dirname(_skill)
_repo = os.path.dirname(_skills_root)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from skills.discord.main import CONTENT_MAX, DiscordNotifier  # noqa: E402


def _make_stub():
    """Return (notifier_factory, captured_calls) where each call records
    (url, payload, timeout)."""
    calls: list[tuple[str, dict, float]] = []

    def stub(url, payload, timeout):
        calls.append((url, payload, timeout))
        return True, None

    return stub, calls


def test_send_uses_default_username():
    stub, calls = _make_stub()
    n = DiscordNotifier("https://example/webhook", default_username="farm_bot",
                       _post=stub)
    ok, err = n.send("hello")
    assert ok and err is None
    assert calls[0][1] == {"content": "hello", "username": "farm_bot"}


def test_send_overrides_username_per_call():
    stub, calls = _make_stub()
    n = DiscordNotifier("https://example/webhook", default_username="farm_bot",
                       _post=stub)
    n.send("hi", username="moisture_alert")
    assert calls[0][1]["username"] == "moisture_alert"


def test_long_content_is_truncated():
    stub, calls = _make_stub()
    n = DiscordNotifier("https://example/webhook", _post=stub)
    long_content = "A" * (CONTENT_MAX + 100)
    n.send(long_content)
    sent = calls[0][1]["content"]
    assert len(sent) == CONTENT_MAX
    assert sent.endswith("...")
    assert sent.startswith("AAAA")


def test_empty_content_refused_without_http():
    stub, calls = _make_stub()
    n = DiscordNotifier("https://example/webhook", _post=stub)
    ok, err = n.send("")
    assert not ok
    assert "empty" in err
    assert calls == []   # no HTTP attempt


def test_failed_post_propagates_error():
    def stub(url, payload, timeout):
        return False, "HTTP 401 Unauthorized: bad webhook"

    n = DiscordNotifier("https://example/webhook", _post=stub)
    ok, err = n.send("hello")
    assert not ok
    assert "401" in err


def test_constructor_rejects_empty_url():
    import pytest
    with pytest.raises(ValueError):
        DiscordNotifier("")


def test_logger_receives_diagnostics():
    stub, _ = _make_stub()
    log: list[str] = []
    n = DiscordNotifier("https://example/webhook", _post=stub, logger=log.append)
    n.send("hello")
    assert any("POSTing" in line for line in log)
    assert any("204" in line for line in log)
