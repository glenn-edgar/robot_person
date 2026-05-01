"""Tests for expansion.py — use_template + slot validation + composition."""

from __future__ import annotations

from typing import Callable, Optional

import pytest

from template_language import (
    Codes,
    OpList,
    RecRef,
    TemplateError,
    ct,
    define_template,
    use_template,
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


# ---- happy path ----------------------------------------------------

def test_outer_call_returns_op_list():
    def body(*, msg: str = "hi"):
        ct.start_test("kb")
        ct.asm_log_message(msg)
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")
    op_list = use_template("p", msg="hello")
    assert isinstance(op_list, OpList)
    assert op_list.engine == "chain_tree"
    assert [o.method for o in op_list.ops] == [
        "start_test", "asm_log_message", "end_test",
    ]
    assert op_list.ops[1].args == ("hello",)


def test_default_slots_filled_in():
    def body(*, msg: str = "default"):
        ct.asm_log_message(msg)
    define_template("p", body, kind="leaf", engine="chain_tree")
    # leaf template — recorder will complain about missing frame, so
    # wrap in a column-style frame? Actually asm_log_message emits a
    # leaf op with no frame discipline; finalize requires balanced
    # frames. Top-level asm_log_message → no frame opened, finalize ok.
    op_list = use_template("p")
    assert op_list.ops[0].args == ("default",)


# ---- slot validation errors ---------------------------------------

def test_unknown_slot():
    def body(*, x: str = "ok"): ct.asm_log_message(x)
    define_template("p", body, kind="leaf", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("p", bogus=1)
    assert exc.value.code == Codes.UNKNOWN_SLOT


def test_missing_required_slot():
    def body(*, must: str): ct.asm_log_message(must)
    define_template("p", body, kind="leaf", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("p")
    assert exc.value.code == Codes.MISSING_REQUIRED_SLOT


def test_slot_kind_mismatch():
    def body(*, n: str): ct.asm_log_message(n)
    define_template("p", body, kind="leaf", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("p", n=7)
    assert exc.value.code == Codes.SLOT_KIND_MISMATCH


def test_null_not_allowed_on_required_non_nullable():
    def body(*, n: str): ct.asm_log_message(n)
    define_template("p", body, kind="leaf", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("p", n=None)
    assert exc.value.code == Codes.SLOT_NULL_NOT_ALLOWED


def test_nullable_optional_slot_accepts_none():
    def body(*, action: Optional[Callable] = None):
        if action is not None:
            action()
        ct.asm_log_message("done")
    define_template("p", body, kind="leaf", engine="chain_tree")
    op_list = use_template("p", action=None)
    assert [o.method for o in op_list.ops] == ["asm_log_message"]


def test_unknown_template():
    with pytest.raises(TemplateError) as exc:
        use_template("nope")
    assert exc.value.code == Codes.UNKNOWN_TEMPLATE


# ---- composition / nesting ----------------------------------------

def test_nested_returns_none_and_splices():
    def child(*, msg: str):
        ct.asm_log_message(msg)
    def parent(*, a: str, b: str):
        ct.start_test("kb")
        result = use_template("ch", msg=a)
        assert result is None  # nested returns None
        use_template("ch", msg=b)
        ct.end_test()
    define_template("ch", child, kind="leaf", engine="chain_tree")
    define_template("p",  parent, kind="solution", engine="chain_tree")

    op_list = use_template("p", a="one", b="two")
    methods = [o.method for o in op_list.ops]
    assert methods == ["start_test", "asm_log_message", "asm_log_message", "end_test"]
    assert op_list.ops[1].args == ("one",)
    assert op_list.ops[2].args == ("two",)


def test_nested_op_source_includes_parent_path():
    def child(*, msg: str):
        ct.asm_log_message(msg)
    def parent(*, a: str):
        use_template("ch", msg=a)
    define_template("ch", child, kind="leaf", engine="chain_tree")
    define_template("parent.p", parent, kind="composite", engine="chain_tree")

    op_list = use_template("parent.p", a="hi")
    op = op_list.ops[0]
    assert op.source == ["parent.p", "ch"]


def test_cross_engine_composition_rejected():
    def ch(*, x: str = "x"): pass
    def parent(*, x: str = "x"):
        use_template("se.ch")
    define_template("se.ch", ch, kind="leaf", engine="s_engine")
    define_template("ct.p", parent, kind="composite", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("ct.p")
    assert exc.value.code == Codes.CROSS_ENGINE_COMPOSITION


def test_duplicate_engine_fn_across_nested():
    """Names from a nested template must collide with parent's claims."""
    fn = lambda rt, data: None
    def child(*, name: str):
        ct.add_one_shot(name, fn)
    def parent(*, name: str):
        ct.add_one_shot(name, fn)
        use_template("ch", name=name)  # collides
    define_template("ch", child, kind="leaf", engine="chain_tree")
    define_template("p", parent, kind="composite", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("p", name="X")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING


# ---- ct outside template ------------------------------------------

def test_ct_outside_template_raises():
    with pytest.raises(TemplateError) as exc:
        ct.asm_log_message("nope")
    assert exc.value.code == Codes.CT_USED_OUTSIDE_TEMPLATE


# ---- recorder stack always cleaned up on error --------------------

def test_stack_cleaned_on_body_exception():
    def body(*, x: str):
        ct.asm_log_message(x)
        raise RuntimeError("boom")
    define_template("p", body, kind="leaf", engine="chain_tree")
    with pytest.raises(RuntimeError):
        use_template("p", x="hi")
    assert _recorder_stack == []
