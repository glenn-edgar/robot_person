"""Tests for replay.py — generate_code, RecRef substitution, error wrapping."""

from __future__ import annotations

import pytest

from template_language import (
    Codes,
    Op,
    OpList,
    RecRef,
    TemplateError,
    ct,
    define_template,
    generate_code,
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


def test_round_trip_minimal_kb():
    def body(*, msg: str = "hello"):
        ct.start_test("kb_demo")
        ct.asm_log_message(msg)
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")

    op_list = use_template("p", msg="world")
    chain = generate_code(op_list, tick_period=0.25)

    # The artifact is a real ChainTree.
    assert hasattr(chain, "engine")
    assert hasattr(chain, "run")
    # It registered the KB.
    kbs = chain.engine["kbs"]
    assert "kb_demo" in kbs


def test_state_machine_round_trip_with_recref():
    """define_state_machine returns a RecRef that's reused by
    asm_change_state. Phase 2 must substitute the real sm node."""
    def body(*, sm_name: str = "sm"):
        ct.start_test("kb")
        sm = ct.define_state_machine(sm_name, state_names=["a", "b"], initial_state="a")
        ct.define_state("a")
        ct.asm_change_state(sm, "b")
        ct.end_state()
        ct.define_state("b")
        ct.asm_log_message("at b")
        ct.end_state()
        ct.end_state_machine()
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")

    op_list = use_template("p", sm_name="x")
    chain = generate_code(op_list, tick_period=0.25)

    # Build succeeded — sm node exists and asm_change_state's data
    # references the real sm dict, not a RecRef.
    kb_root = chain.engine["kbs"]["kb"]["root"]
    # Find the SM node.
    sm_nodes = [c for c in kb_root["children"] if c["main_fn_name"] == "CFL_STATE_MACHINE_MAIN"]
    assert len(sm_nodes) == 1
    sm_node = sm_nodes[0]
    state_a = sm_node["children"][0]
    # state a contains a change_state leaf whose sm_node points back at sm.
    change_leaf = state_a["children"][0]
    assert change_leaf["data"]["sm_node"] is sm_node
    # No leftover RecRef anywhere.
    assert not isinstance(change_leaf["data"]["sm_node"], RecRef)


def test_unresolved_recref_raises():
    """A hand-crafted op that mentions a RecRef never produced earlier."""
    stray = RecRef("stray")
    op_list = OpList(engine="chain_tree", ops=[
        Op(method="start_test", args=("kb",), kwargs={}, source=["t"]),
        # asm_change_state takes (sm_node, new_state) — feed it a stray
        # RecRef with no producer.
        Op(method="asm_change_state", args=(stray, "x"), kwargs={}, source=["t"]),
    ])
    with pytest.raises(TemplateError) as exc:
        generate_code(op_list, tick_period=0.25)
    assert exc.value.code == Codes.UNRESOLVED_RECREF


def test_replay_op_failed_wraps_underlying():
    """Real builder raises (e.g., bad arg) → wrapped in replay_op_failed."""
    op_list = OpList(engine="chain_tree", ops=[
        # start_test rejects empty name with ValueError.
        Op(method="start_test", args=("",), kwargs={}, source=["t"]),
    ])
    with pytest.raises(TemplateError) as exc:
        generate_code(op_list, tick_period=0.25)
    assert exc.value.code == Codes.REPLAY_OP_FAILED
    assert exc.value.details["method"] == "start_test"
    assert exc.value.details["underlying"]["type"] == "ValueError"
    assert exc.value.template_stack == ["t"]


def test_engine_dispatch_failed_for_unknown_engine():
    op_list = OpList(engine="bogus", ops=[])
    with pytest.raises(TemplateError) as exc:
        generate_code(op_list)
    assert exc.value.code == Codes.ENGINE_DISPATCH_FAILED


def test_engine_dispatch_se_engine_not_yet_implemented():
    op_list = OpList(engine="s_engine", ops=[])
    with pytest.raises(TemplateError) as exc:
        generate_code(op_list)
    assert exc.value.code == Codes.ENGINE_DISPATCH_FAILED


def test_engine_kwargs_passed_to_chain_tree():
    def body():
        ct.start_test("kb")
        ct.end_test()
    define_template("p", body, kind="solution", engine="chain_tree")
    op_list = use_template("p")
    chain = generate_code(op_list, tick_period=1.5)
    assert chain.engine["tick_period"] == 1.5
