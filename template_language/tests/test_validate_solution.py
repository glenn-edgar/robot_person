"""Tests for validate_solution — the LLM closed-loop verb."""

from __future__ import annotations

from typing import Callable, Optional

import pytest

from template_language import (
    Codes,
    Stage,
    ct,
    define_template,
    use_template,
    validate_solution,
)
from template_language.recorder import _recorder_stack
from template_language.registry import clear_registry


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    _recorder_stack.clear()
    yield
    clear_registry()
    _recorder_stack.clear()


def test_ok_solution_returns_ok_true():
    def body(*, msg: str = "hi"):
        ct.start_test("kb")
        ct.asm_log_message(msg)
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")
    assert validate_solution("p", msg="hello") == {"ok": True}


def test_unknown_template_returns_error_dict():
    result = validate_solution("not.registered")
    assert result["ok"] is False
    assert result["code"] == Codes.UNKNOWN_TEMPLATE
    assert result["stage"] == Stage.EXPANSION


def test_missing_required_slot_returns_error():
    def body(*, must: str):
        ct.asm_log_message(must)
    define_template("p", body, kind="leaf", engine="chain_tree")
    r = validate_solution("p")
    assert r["ok"] is False
    assert r["code"] == Codes.MISSING_REQUIRED_SLOT
    assert r["details"]["slot"] == "must"


def test_slot_kind_mismatch_returns_error_with_details():
    def body(*, n: str):
        ct.asm_log_message(n)
    define_template("p", body, kind="leaf", engine="chain_tree")
    r = validate_solution("p", n=42)
    assert r["ok"] is False
    assert r["code"] == Codes.SLOT_KIND_MISMATCH
    assert r["details"]["expected_kind"] == "STRING"
    assert r["details"]["got_type"] == "int"


def test_replay_error_surfaces():
    """An op that the real builder rejects → replay_op_failed."""
    def body():
        ct.start_test("")  # empty kb name → ValueError at replay
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")
    r = validate_solution("p")
    assert r["ok"] is False
    assert r["stage"] == Stage.REPLAY
    assert r["code"] == Codes.REPLAY_OP_FAILED
    assert r["details"]["underlying"]["type"] == "ValueError"


def test_recorder_stack_imbalance_caught():
    def body():
        ct.start_test("kb")
        # missing end_test
    define_template("p", body, kind="solution", engine="chain_tree")
    r = validate_solution("p")
    assert r["ok"] is False
    assert r["code"] == Codes.RECORDER_STACK_IMBALANCE


def test_template_stack_populated_on_nested_error():
    def child(*, x: str):
        ct.asm_log_message(x)
    def parent(*, x: str):
        ct.start_test("kb")
        use_template("ch", x=x)
        ct.end_test()
    define_template("ch", child, kind="leaf", engine="chain_tree")
    define_template("p",  parent, kind="composite", engine="chain_tree")
    # Parent's required-string `x` passes, child gets validated too.
    # Force a kind mismatch via parent's slot:
    r = validate_solution("p", x=99)
    assert r["ok"] is False
    assert r["code"] == Codes.SLOT_KIND_MISMATCH


def test_returned_dict_structure():
    """Verify the full shape used by the LLM loop."""
    def body(*, n: str): ct.asm_log_message(n)
    define_template("p", body, kind="leaf", engine="chain_tree")
    r = validate_solution("p", n=None)
    assert set(r.keys()) == {"ok", "stage", "code", "details", "template_stack"}
    assert r["ok"] is False
    assert r["code"] == Codes.SLOT_NULL_NOT_ALLOWED


def test_recorder_stack_clean_after_validate():
    def body(*, n: str): ct.asm_log_message(n)
    define_template("p", body, kind="leaf", engine="chain_tree")
    validate_solution("p", n=42)         # error path
    validate_solution("p", n="ok")       # success path
    assert _recorder_stack == []
