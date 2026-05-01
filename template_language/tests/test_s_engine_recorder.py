"""Tests for the s_engine recorder + replay path.

s_engine differs fundamentally from chain_tree:
  - No builder class. The DSL is a module of pure functions returning
    node dicts.
  - No frame discipline (no define_/end_ pairs).
  - No name registrations to enforce.
  - Composition is bottom-up via call args: child trees are dicts
    passed into parent calls.
  - Templates' bodies RETURN their tree root (a RecRef during phase 1,
    resolved to a dict during phase 2). This is what `generate_code`
    surfaces as its return.

These tests pin the recorder + replay path against a real s_engine
build artifact.
"""

from __future__ import annotations

import pytest

from template_language import (
    Codes,
    Kind,
    RecRef,
    TemplateError,
    ct,
    define_template,
    describe_template,
    generate_code,
    use_template,
    validate_solution,
)
from template_language.recorder import s_engine_methods


# ---- recorder method surface --------------------------------------

def test_s_engine_methods_lists_dsl_primitives():
    methods = s_engine_methods()
    # Spot-check primitives we know are in se_dsl.__all__.
    assert "sequence" in methods
    assert "log" in methods
    assert "if_then" in methods
    assert "dict_eq" in methods
    assert "wait_until_in_time_window" in methods
    # make_node is excluded (template authors use higher-level primitives).
    assert "make_node" not in methods


# ---- registration -------------------------------------------------

def test_register_s_engine_template():
    def body() -> RecRef:
        return ct.log("hello")
    define_template("p", body, kind="leaf", engine="s_engine")
    d = describe_template("p")
    assert d["engine"] == "s_engine"


# ---- expansion ----------------------------------------------------

def test_no_frame_discipline_means_no_imbalance():
    """An s_engine body that doesn't pair anything finalizes cleanly."""
    def body():
        ct.log("a")
        ct.log("b")
        return ct.sequence(ct.log("c"))
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    methods = [op.method for op in op_list.ops]
    # `c` is constructed before `sequence` because it's an arg.
    assert "log" in methods
    assert "sequence" in methods


def test_body_return_captured_as_root():
    def body():
        return ct.log("root")
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    assert op_list.body_return is not None
    # The body_return matches the only op's out_ref.
    assert op_list.body_return is op_list.ops[0].out_ref


def test_body_returning_none_keeps_body_return_none():
    def body():
        ct.log("x")  # discards return
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    assert op_list.body_return is None


def test_unknown_method_raises():
    def body():
        return ct.bogus_primitive()
    define_template("p", body, kind="solution", engine="s_engine")
    with pytest.raises(TemplateError) as exc:
        use_template("p")
    assert exc.value.code == Codes.UNKNOWN_RECORDER_METHOD


# ---- replay --------------------------------------------------------

def test_replay_returns_tree_root_as_dict():
    """Phase 2 returns the body's return RecRef resolved to its real dict."""
    def body():
        return ct.log("hello")
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    tree = generate_code(op_list)
    assert isinstance(tree, dict)
    # se_dsl.log() should produce a node with fn / call_type / params.
    assert tree["call_type"] == "o_call"


def test_replay_substitutes_recrefs_in_args():
    """ct.sequence(ct.log("a"), ct.log("b")) — phase 2 must resolve
    the two RecRefs into the real log dicts before calling sequence."""
    def body():
        return ct.sequence(
            ct.log("a"),
            ct.log("b"),
        )
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    tree = generate_code(op_list)
    assert tree["call_type"] == "m_call"  # sequence is a multi-call
    # Two children, both real dicts (no RecRefs).
    assert len(tree["children"]) == 2
    for child in tree["children"]:
        assert isinstance(child, dict)
        assert not isinstance(child, RecRef)


def test_replay_op_failed_wraps_se_dsl_error():
    """An se_dsl primitive raising at replay → replay_op_failed wraps it."""
    def body():
        return ct.log(123)  # log expects a string-ish; should raise on type.
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    # If se_dsl.log accepts ints it won't raise; verify by trying directly.
    import se_dsl
    try:
        se_dsl.log(123)
        pytest.skip("se_dsl.log accepts ints; skipping wrap-error test")
    except Exception:
        pass
    with pytest.raises(TemplateError) as exc:
        generate_code(op_list)
    assert exc.value.code == Codes.REPLAY_OP_FAILED


def test_body_returning_none_at_replay_is_an_error():
    def body():
        ct.log("orphan")  # discards return
    define_template("p", body, kind="solution", engine="s_engine")
    op_list = use_template("p")
    with pytest.raises(TemplateError) as exc:
        generate_code(op_list)
    assert exc.value.code == Codes.REPLAY_OP_FAILED
    assert "body returned None" in exc.value.details["reason"]


# ---- nested s_engine templates ------------------------------------

def test_nested_template_returns_recref_to_parent():
    """An inner s_engine template returns its tree root; the parent
    can pass it as an arg to its own dsl call."""
    def child():
        return ct.log("inner")
    def parent():
        return ct.sequence(
            use_template("child"),
            ct.log("outer"),
        )
    define_template("child",  child,  kind="composite", engine="s_engine")
    define_template("parent", parent, kind="solution",  engine="s_engine")

    op_list = use_template("parent")
    tree = generate_code(op_list)
    assert tree["call_type"] == "m_call"
    assert len(tree["children"]) == 2


# ---- cross-engine composition still rejected ----------------------

def test_cross_engine_composition_rejected():
    def ct_body():
        ct.start_test("kb"); ct.end_test()
    def se_body():
        use_template("ct.thing")          # parent is s_engine, child chain_tree
        return ct.log("x")
    define_template("ct.thing", ct_body, kind="solution", engine="chain_tree")
    define_template("se.thing", se_body, kind="solution", engine="s_engine")
    with pytest.raises(TemplateError) as exc:
        use_template("se.thing")
    assert exc.value.code == Codes.CROSS_ENGINE_COMPOSITION


# ---- validate_solution path ---------------------------------------

def test_validate_solution_works_for_s_engine():
    def body():
        return ct.sequence(ct.log("hi"))
    define_template("p", body, kind="solution", engine="s_engine")
    assert validate_solution("p") == {"ok": True}
