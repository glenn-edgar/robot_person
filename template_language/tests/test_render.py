"""Tests for render.py — op_list_to_python / op_list_to_json."""

from __future__ import annotations

import pytest

from template_language import (
    ct,
    define_template,
    op_list_to_json,
    op_list_to_python,
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


def _build_simple_oplist():
    def body():
        ct.start_test("kb")
        ct.asm_log_message("hello")
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")
    return use_template("p")


def _build_sm_oplist():
    def body():
        ct.start_test("kb")
        ct.define_state_machine("sm", state_names=["a", "b"], initial_state="a")
        ct.define_state("a")
        ct.asm_log_message("at a")
        ct.end_state()
        ct.define_state("b")
        ct.asm_log_message("at b")
        ct.end_state()
        ct.end_state_machine()
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")
    return use_template("p")


# ---- op_list_to_python --------------------------------------------

def test_python_render_minimal():
    op_list = _build_simple_oplist()
    src = op_list_to_python(op_list)
    assert "# engine: chain_tree" in src
    assert "chain.start_test('kb')" in src
    assert "chain.asm_log_message('hello')" in src
    assert "chain.end_test()" in src


def test_python_render_indents_frames():
    op_list = _build_simple_oplist()
    src = op_list_to_python(op_list)
    lines = [ln for ln in src.splitlines() if ln and not ln.startswith("#")]
    # asm_log_message is indented one level inside start_test/end_test.
    log_line = next(ln for ln in lines if "asm_log_message" in ln)
    assert log_line.startswith("    ")
    end_line = next(ln for ln in lines if "end_test" in ln)
    assert not end_line.startswith("    ")


def test_python_render_custom_builder_name():
    op_list = _build_simple_oplist()
    src = op_list_to_python(op_list, builder_name="bldr")
    assert "bldr.start_test" in src
    # No bare "chain.start_test" — `chain` must not have leaked through.
    assert "chain.start_test" not in src


def test_python_render_assigns_recref_to_var():
    """Frame openers that produce reusable RecRefs (state_machine etc.)
    should appear as `name = builder.method(...)` for downstream readability."""
    op_list = _build_sm_oplist()
    src = op_list_to_python(op_list)
    # define_state_machine returns a ref; we assign it to a variable.
    assert "state_machine = chain.define_state_machine(" in src


def test_python_render_two_state_machines_get_distinct_names():
    """If a body opens two state_machines the renderer assigns
    state_machine, state_machine_2 etc."""
    def body():
        ct.start_test("kb")
        ct.define_state_machine("a", state_names=["x"], initial_state="x")
        ct.define_state("x"); ct.end_state()
        ct.end_state_machine()
        ct.define_state_machine("b", state_names=["x"], initial_state="x")
        ct.define_state("x"); ct.end_state()
        ct.end_state_machine()
        ct.end_test()
    define_template("p2", body, kind="solution", engine="chain_tree")
    src = op_list_to_python(use_template("p2"))
    assert "state_machine = chain.define_state_machine(" in src
    assert "state_machine_2 = chain.define_state_machine(" in src


# ---- op_list_to_json ---------------------------------------------

def test_json_render_shape():
    op_list = _build_simple_oplist()
    j = op_list_to_json(op_list)
    assert j["engine"] == "chain_tree"
    assert isinstance(j["ops"], list)
    op0 = j["ops"][0]
    assert op0["method"] == "start_test"
    assert op0["args"] == ["kb"]
    assert op0["kwargs"] == {}
    assert isinstance(op0["source"], list)
    assert op0["out_ref"] is not None
    assert "__recref__" in op0["out_ref"]


def test_json_render_recref_in_args():
    op_list = _build_sm_oplist()
    j = op_list_to_json(op_list)
    # asm_log_message ops have no recref args here — but define_state_machine
    # produces an out_ref that may show up downstream. Check overall: every
    # op's out_ref is either None or a recref marker.
    for op in j["ops"]:
        if op["out_ref"] is not None:
            assert "__recref__" in op["out_ref"]
            assert "kind" in op["out_ref"]


def test_json_render_callable_arg_marked_opaque():
    fn = lambda rt, data: None
    fn.__name__ = "my_fn"
    def body():
        ct.add_one_shot("X", fn)
    define_template("p", body, kind="leaf", engine="chain_tree")
    j = op_list_to_json(use_template("p"))
    op = j["ops"][0]
    assert op["method"] == "add_one_shot"
    assert op["args"][0] == "X"
    assert op["args"][1] == {"__callable__": "my_fn"}


def test_json_render_is_pure_data():
    """The result is JSON-serializable — no RecRef objects, no callables,
    no opaque types remain."""
    import json
    op_list = _build_sm_oplist()
    j = op_list_to_json(op_list)
    # Must round-trip through json.dumps without TypeError.
    s = json.dumps(j)
    assert "state_machine" in s or "state_names" in s
