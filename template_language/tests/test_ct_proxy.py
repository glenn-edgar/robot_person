"""Tests for ct.py — the module-level proxy."""

from __future__ import annotations

import pytest

from template_language import ct
from template_language.errors import Codes, TemplateError
from template_language.recorder import (
    Recorder,
    _pop_recorder,
    _push_recorder,
    _recorder_stack,
    chain_tree_methods,
)


@pytest.fixture(autouse=True)
def _clear_stack():
    _recorder_stack.clear()
    yield
    _recorder_stack.clear()


def test_ct_outside_template_raises():
    with pytest.raises(TemplateError) as exc:
        ct.asm_log_message("nope")
    assert exc.value.code == Codes.CT_USED_OUTSIDE_TEMPLATE
    assert exc.value.details["method"] == "asm_log_message"


def test_ct_inside_recorder_dispatches():
    rec = Recorder(engine="chain_tree", template_path="t",
                   valid_methods=chain_tree_methods())
    _push_recorder(rec)
    try:
        ct.asm_log_message("hello")
    finally:
        _pop_recorder(rec)
    assert len(rec.op_list.ops) == 1
    assert rec.op_list.ops[0].method == "asm_log_message"
    assert rec.op_list.ops[0].args == ("hello",)


def test_ct_repr():
    assert "ct" in repr(ct).lower() or "proxy" in repr(ct).lower()


def test_ct_unknown_method_raises_template_error():
    rec = Recorder(engine="chain_tree", template_path="t",
                   valid_methods=chain_tree_methods())
    _push_recorder(rec)
    try:
        with pytest.raises(TemplateError) as exc:
            ct.no_such_method
        assert exc.value.code == Codes.UNKNOWN_RECORDER_METHOD
    finally:
        _pop_recorder(rec)
