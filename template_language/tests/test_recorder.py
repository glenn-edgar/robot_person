"""Tests for recorder.py — Op/RecRef/Recorder + the module-level stack."""

from __future__ import annotations

import pytest

from template_language import ct
from template_language.errors import Codes, TemplateError
from template_language.recorder import (
    Op,
    OpList,
    RecRef,
    Recorder,
    _active,
    _pop_recorder,
    _push_recorder,
    _recorder_stack,
    chain_tree_methods,
)


@pytest.fixture(autouse=True)
def _clear_stack():
    """Each test runs with an empty recorder stack."""
    _recorder_stack.clear()
    yield
    _recorder_stack.clear()


# -- helpers ----------------------------------------------------------

def _new_chain_tree_recorder(template_path="test.template") -> Recorder:
    methods = chain_tree_methods()
    return Recorder(engine="chain_tree", template_path=template_path,
                    valid_methods=methods)


def _with_recorder(rec):
    class _CM:
        def __enter__(self_):
            _push_recorder(rec)
            return rec
        def __exit__(self_, *a):
            _pop_recorder(rec)
    return _CM()


# -- RecRef ----------------------------------------------------------

def test_recref_unique_ids():
    a = RecRef("x")
    b = RecRef("x")
    assert a != b
    assert hash(a) != hash(b)


def test_recref_eq_same_id():
    a = RecRef("x")
    assert a == a
    assert a != "not a ref"


# -- method dispatch -------------------------------------------------

def test_chain_tree_methods_includes_known():
    methods = chain_tree_methods()
    assert "start_test" in methods
    assert "define_state_machine" in methods
    assert "asm_log_message" in methods
    assert "add_one_shot" in methods
    # private/dunder filtered out
    assert "_pop" not in methods
    assert "__init__" not in methods


def test_unknown_method_raises():
    rec = _new_chain_tree_recorder()
    with pytest.raises(TemplateError) as exc:
        rec.does_not_exist
    assert exc.value.code == Codes.UNKNOWN_RECORDER_METHOD


def test_method_returns_recref_and_records_op():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ref = ct.start_test("kb1")
    assert isinstance(ref, RecRef)
    assert len(rec.op_list.ops) == 1
    op = rec.op_list.ops[0]
    assert op.method == "start_test"
    assert op.args == ("kb1",)
    assert op.kwargs == {}


# -- frame discipline ------------------------------------------------

def test_balanced_frames_finalize_clean():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.define_column("col1")
        ct.end_column()
        ct.end_test()
    op_list = rec.finalize()
    assert op_list.engine == "chain_tree"
    assert [o.method for o in op_list.ops] == [
        "start_test", "define_column", "end_column", "end_test",
    ]


def test_close_without_open_raises():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        with pytest.raises(TemplateError) as exc:
            ct.end_test()
    assert exc.value.code == Codes.RECORDER_STACK_IMBALANCE


def test_mismatched_close_raises():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        with pytest.raises(TemplateError) as exc:
            ct.end_column()
    assert exc.value.code == Codes.RECORDER_STACK_IMBALANCE
    assert exc.value.details["expected_open"] == "column"
    assert exc.value.details["got_open"] == "test"


def test_unclosed_frame_at_finalize_raises():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
    with pytest.raises(TemplateError) as exc:
        rec.finalize()
    assert exc.value.code == Codes.RECORDER_STACK_IMBALANCE
    assert "test" in exc.value.details["unclosed_frames"]


def test_state_machine_frame_pair():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.define_state_machine("sm1", state_names=["a", "b"], initial_state="a")
        ct.define_state("a")
        ct.end_state()
        ct.define_state("b")
        ct.end_state()
        ct.end_state_machine()
        ct.end_test()
    rec.finalize()


# -- name discipline -------------------------------------------------

def test_duplicate_kb_name():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.end_test()
        with pytest.raises(TemplateError) as exc:
            ct.start_test("kb1")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING
    assert exc.value.details["namespace"] == "kb"
    assert exc.value.details["name"] == "kb1"


def test_duplicate_engine_fn_name():
    rec = _new_chain_tree_recorder()
    fn = lambda rt, data: None
    with _with_recorder(rec):
        ct.add_one_shot("DECIDE", fn)
        with pytest.raises(TemplateError) as exc:
            ct.add_main("DECIDE", fn)
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING
    assert exc.value.details["namespace"] == "engine_fn"


def test_duplicate_state_name_in_sm():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.define_state_machine("sm1", state_names=["a", "b"], initial_state="a")
        ct.define_state("a")
        ct.end_state()
        with pytest.raises(TemplateError) as exc:
            ct.define_state("a")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING
    assert exc.value.details["namespace"] == "state"


def test_state_names_scoped_per_sm():
    """Two different SMs can both have a state named 'a'."""
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.define_state_machine("sm1", state_names=["a"], initial_state="a")
        ct.define_state("a")
        ct.end_state()
        ct.end_state_machine()
        ct.define_state_machine("sm2", state_names=["a"], initial_state="a")
        ct.define_state("a")
        ct.end_state()
        ct.end_state_machine()
        ct.end_test()
    rec.finalize()


def test_duplicate_column_name_in_frame():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.define_column("col")
        ct.end_column()
        with pytest.raises(TemplateError) as exc:
            ct.define_column("col")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING
    assert exc.value.details["namespace"] == "column"


def test_duplicate_sm_name():
    rec = _new_chain_tree_recorder()
    with _with_recorder(rec):
        ct.start_test("kb1")
        ct.define_state_machine("sm1", state_names=["a"], initial_state="a")
        ct.define_state("a"); ct.end_state()
        ct.end_state_machine()
        with pytest.raises(TemplateError) as exc:
            ct.define_state_machine("sm1", state_names=["a"], initial_state="a")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING
    assert exc.value.details["namespace"] == "sm"


# -- stack & op-list source ------------------------------------------

def test_op_source_captures_template_stack():
    outer = _new_chain_tree_recorder("outer.tmpl")
    inner = _new_chain_tree_recorder("inner.tmpl")
    with _with_recorder(outer):
        with _with_recorder(inner):
            ct.asm_log_message("hi")
        # outer adds its own op
        ct.asm_log_message("bye")
    inner_op = inner.op_list.ops[0]
    assert inner_op.source == ["outer.tmpl", "inner.tmpl"]
    outer_op = outer.op_list.ops[0]
    assert outer_op.source == ["outer.tmpl"]


def test_pop_recorder_mismatch_raises():
    rec_a = _new_chain_tree_recorder("a")
    rec_b = _new_chain_tree_recorder("b")
    _push_recorder(rec_a)
    try:
        with pytest.raises(TemplateError) as exc:
            _pop_recorder(rec_b)
        assert exc.value.code == Codes.RECORDER_STACK_IMBALANCE
    finally:
        _pop_recorder(rec_a)
