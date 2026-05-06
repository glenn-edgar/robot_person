"""Stage-2 tests for the discord_notify leaf, including content_bb_key.

The leaf supports two modes: static content (used historically) and
blackboard-driven content (added for the daily_report composite where
an upstream leaf writes the message into the blackboard before this
leaf ships it). These tests cover both modes plus the validation +
runtime-skip branches.

Lives under robots/farm_soil/tests/ because that's where the multi-
root bootstrap (farm_soil + user_templates) is wired up by conftest.py.
"""

from __future__ import annotations

import time
from datetime import timezone

import pytest

from template_language import ct, define_template, generate_code, use_template


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeNotifier:
    """Stand-in for skills.discord.DiscordNotifier — captures sends."""

    instances: list["_FakeNotifier"] = []

    def __init__(self, webhook_url, **_kwargs):
        self.webhook_url = webhook_url
        self.sent: list[tuple[str, dict]] = []
        _FakeNotifier.instances.append(self)

    def send(self, content, *, username=None):
        self.sent.append((content, {"username": username}))
        return True, None


def _patch_notifier(monkeypatch):
    _FakeNotifier.instances = []
    import user_templates.templates.leaves.chain_tree.discord_notify as leaf
    monkeypatch.setattr(leaf, "DiscordNotifier", _FakeNotifier)


def _make_inline_solution(body):
    """Register a one-off test solution at a fixed path and return its op_list.

    The conftest's autouse fixture clears the template registry between
    tests, so re-registering at the same path each time is safe.
    """
    path = "project.farm_soil.solutions.chain_tree._test_inline"
    define_template(path=path, fn=body, kind="solution", engine="chain_tree")
    return use_template(path)


def _build_chain(op_list, log: list[str]):
    return generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: int(time.time()),
        timezone=timezone.utc,
        logger=log.append,
    )


def _run_to_termination(chain, kb_name: str) -> None:
    counter = {"n": 0}

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= 20:
            chain.engine["cfl_engine_flag"] = False

    chain.engine["sleep"] = capped_sleep
    chain.run(starting=[kb_name])


# ---------------------------------------------------------------------------
# Static content (regression — pre-P0.5 behavior)
# ---------------------------------------------------------------------------

def test_static_content_path_unchanged(monkeypatch):
    _patch_notifier(monkeypatch)

    def body():
        ct.start_test("kb_static")
        use_template(
            "user.leaves.chain_tree.discord_notify",
            name="static_msg",
            webhook_url="https://example.invalid/wh",
            content="hello world",
        )
        ct.asm_terminate_system()
        ct.end_test()

    op_list = _make_inline_solution(body)
    log: list[str] = []
    chain = _build_chain(op_list, log)
    _run_to_termination(chain, "kb_static")

    assert len(_FakeNotifier.instances) == 1
    assert _FakeNotifier.instances[0].sent == [
        ("hello world", {"username": None})
    ]
    assert any("sent ok" in line for line in log)


# ---------------------------------------------------------------------------
# Blackboard-driven content (the new P0.5 path)
# ---------------------------------------------------------------------------

def test_content_bb_key_reads_from_blackboard(monkeypatch):
    _patch_notifier(monkeypatch)

    def body():
        ct.start_test("kb_bb")
        # Seed the blackboard the report-rendering leaf would normally
        # write; using asm_blackboard_set keeps this test self-contained
        # without needing the (yet-unbuilt) sqlite_query leaf.
        ct.asm_blackboard_set("daily_report_text", "morning report body")
        use_template(
            "user.leaves.chain_tree.discord_notify",
            name="from_bb",
            webhook_url="https://example.invalid/wh",
            content_bb_key="daily_report_text",
        )
        ct.asm_terminate_system()
        ct.end_test()

    op_list = _make_inline_solution(body)
    log: list[str] = []
    chain = _build_chain(op_list, log)
    _run_to_termination(chain, "kb_bb")

    assert len(_FakeNotifier.instances) == 1
    assert _FakeNotifier.instances[0].sent == [
        ("morning report body", {"username": None})
    ]


def test_content_bb_key_missing_skips_send_with_log(monkeypatch):
    _patch_notifier(monkeypatch)

    def body():
        ct.start_test("kb_missing_bb")
        use_template(
            "user.leaves.chain_tree.discord_notify",
            name="missing",
            webhook_url="https://example.invalid/wh",
            content_bb_key="never_set",
        )
        ct.asm_terminate_system()
        ct.end_test()

    op_list = _make_inline_solution(body)
    log: list[str] = []
    chain = _build_chain(op_list, log)
    _run_to_termination(chain, "kb_missing_bb")

    # Notifier was never constructed; send was skipped at the leaf level.
    assert _FakeNotifier.instances == []
    assert any(
        "skipped — blackboard key 'never_set' missing or empty" in line
        for line in log
    )


def test_content_bb_key_empty_string_skips_send(monkeypatch):
    _patch_notifier(monkeypatch)

    def body():
        ct.start_test("kb_empty_bb")
        ct.asm_blackboard_set("body_key", "")
        use_template(
            "user.leaves.chain_tree.discord_notify",
            name="empty",
            webhook_url="https://example.invalid/wh",
            content_bb_key="body_key",
        )
        ct.asm_terminate_system()
        ct.end_test()

    op_list = _make_inline_solution(body)
    log: list[str] = []
    chain = _build_chain(op_list, log)
    _run_to_termination(chain, "kb_empty_bb")

    assert _FakeNotifier.instances == []
    assert any("skipped" in line for line in log)


# ---------------------------------------------------------------------------
# Template-time validation
# ---------------------------------------------------------------------------

def test_both_content_and_bb_key_set_is_error():
    def body():
        ct.start_test("kb_both")
        use_template(
            "user.leaves.chain_tree.discord_notify",
            name="both",
            webhook_url="https://example.invalid/wh",
            content="static",
            content_bb_key="key",
        )
        ct.asm_terminate_system()
        ct.end_test()

    with pytest.raises(Exception) as excinfo:
        _make_inline_solution(body)
    assert "not both" in str(excinfo.value)


def test_neither_content_nor_bb_key_set_is_error():
    def body():
        ct.start_test("kb_neither")
        use_template(
            "user.leaves.chain_tree.discord_notify",
            name="neither",
            webhook_url="https://example.invalid/wh",
        )
        ct.asm_terminate_system()
        ct.end_test()

    with pytest.raises(Exception) as excinfo:
        _make_inline_solution(body)
    assert "required" in str(excinfo.value)
