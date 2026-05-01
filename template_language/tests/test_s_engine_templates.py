"""Tests for the s_engine templates: print_hello + fire_in_window."""

from __future__ import annotations

import pytest

from template_language import (
    Codes,
    TemplateError,
    ct,
    define_template,
    describe_template,
    generate_code,
    use_template,
    validate_solution,
)


# ---- print_hello (s_engine leaf) ----------------------------------

def test_print_hello_loadable():
    d = describe_template("leaves.s_engine.print_hello")
    assert d["kind"] == "leaf"
    assert d["engine"] == "s_engine"
    assert d["slots"] == []


def test_print_hello_replays_to_log_node():
    op_list = use_template("leaves.s_engine.print_hello")
    assert op_list.body_return is not None
    tree = generate_code(op_list)
    assert isinstance(tree, dict)
    assert tree["call_type"] == "o_call"   # log is a oneshot call
    assert tree["params"]["message"] == "hello"


# ---- fire_in_window (s_engine composite) --------------------------

def test_fire_in_window_loadable():
    d = describe_template("composites.s_engine.fire_in_window")
    assert d["kind"] == "composite"
    assert d["engine"] == "s_engine"
    by_name = {s["name"]: s for s in d["slots"]}
    assert set(by_name) == {"start", "end", "body"}
    assert by_name["body"]["kind"] == "ACTION"


def test_fire_in_window_op_list_order():
    """s_engine ops are recorded bottom-up: predicate first, then body
    constructs its own ops, then if_then wraps both."""
    def solution():
        return use_template(
            "composites.s_engine.fire_in_window",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.log("inside"),
        )
    define_template("solution.shape", solution, kind="solution", engine="s_engine")

    op_list = use_template("solution.shape")
    methods = [op.method for op in op_list.ops]
    # in_time_window builds the predicate. body's lambda calls ct.log.
    # Then if_then wraps both. Order matters: args are evaluated before
    # the wrapping call.
    assert methods == ["in_time_window", "log", "if_then"]


def test_fire_in_window_replay_produces_if_then_tree():
    def solution():
        return use_template(
            "composites.s_engine.fire_in_window",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.log("inside"),
        )
    define_template("solution.tree", solution, kind="solution", engine="s_engine")

    op_list = use_template("solution.tree")
    tree = generate_code(op_list)
    # Outermost is if_then. Children are [pred, then_].
    assert tree["call_type"] == "m_call"
    # Two children: the predicate and the then-branch.
    assert len(tree["children"]) == 2
    pred = tree["children"][0]
    then_branch = tree["children"][1]
    assert pred["call_type"] == "p_call"   # in_time_window
    assert then_branch["call_type"] == "o_call"  # log
    assert then_branch["params"]["message"] == "inside"


def test_fire_in_window_validate_solution():
    def solution():
        return use_template(
            "composites.s_engine.fire_in_window",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.log("inside"),
        )
    define_template("solution.val", solution, kind="solution", engine="s_engine")
    assert validate_solution("solution.val") == {"ok": True}


def test_fire_in_window_with_nested_template_as_body():
    """Body can call another use_template; that returns a RecRef which
    flows into the if_then's then_ branch."""
    def solution():
        return use_template(
            "composites.s_engine.fire_in_window",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: use_template("leaves.s_engine.print_hello"),
        )
    define_template("solution.nest", solution, kind="solution", engine="s_engine")

    op_list = use_template("solution.nest")
    tree = generate_code(op_list)
    # then_ branch is the print_hello log node.
    then_branch = tree["children"][1]
    assert then_branch["params"]["message"] == "hello"


def test_fire_in_window_runtime_in_window_fires_body():
    """End-to-end runtime: build the tree, instantiate, push tick events.
    With wall-clock fixed inside the window, the body's log should
    execute via the s_engine runtime."""
    pytest.importorskip("se_runtime")

    def solution():
        return use_template(
            "composites.s_engine.fire_in_window",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.log("body-fired"),
        )
    define_template("solution.rt_in", solution, kind="solution", engine="s_engine")

    op_list = use_template("solution.rt_in")
    tree = generate_code(op_list)

    # Build a minimal runtime around the tree.
    from datetime import datetime, timezone
    from se_runtime import (
        new_instance_from_tree,
        push_event,
        run_until_idle,
        EVENT_TICK,
    )
    from se_runtime.module import new_module

    log: list[str] = []
    epoch_in_window = int(datetime(2026, 5, 1, 12, 0, 0,
                                   tzinfo=timezone.utc).timestamp())
    module = new_module(
        logger=log.append,
        get_wall_time=lambda: epoch_in_window,
        timezone=timezone.utc,
    )
    inst = new_instance_from_tree(module, tree)
    push_event(inst, EVENT_TICK, None)
    run_until_idle(inst)

    # se_dsl.log formats messages as "[log] <message>".
    assert any("body-fired" in line for line in log)


def test_fire_in_window_runtime_out_of_window_skips_body():
    pytest.importorskip("se_runtime")

    def solution():
        return use_template(
            "composites.s_engine.fire_in_window",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.log("body-fired"),
        )
    define_template("solution.rt_out", solution, kind="solution", engine="s_engine")

    op_list = use_template("solution.rt_out")
    tree = generate_code(op_list)

    from datetime import datetime, timezone
    from se_runtime import (
        new_instance_from_tree,
        push_event,
        run_until_idle,
        EVENT_TICK,
    )
    from se_runtime.module import new_module

    log: list[str] = []
    epoch_out_of_window = int(datetime(2026, 5, 1, 22, 0, 0,
                                       tzinfo=timezone.utc).timestamp())
    module = new_module(
        logger=log.append,
        get_wall_time=lambda: epoch_out_of_window,
        timezone=timezone.utc,
    )
    inst = new_instance_from_tree(module, tree)
    push_event(inst, EVENT_TICK, None)
    run_until_idle(inst)

    assert not any("body-fired" in line for line in log)


# ---- the same logical template at two paths -----------------------

def test_both_engine_variants_coexist():
    """The same logical template (fire_in_window) exists at two
    distinct ltree paths, one per engine."""
    ct_d = describe_template("composites.chain_tree.fire_in_window")
    se_d = describe_template("composites.s_engine.fire_in_window")
    assert ct_d["engine"] == "chain_tree"
    assert se_d["engine"] == "s_engine"
    # Slot signatures differ — chain_tree adds `name`, s_engine drops it.
    ct_slots = {s["name"] for s in ct_d["slots"]}
    se_slots = {s["name"] for s in se_d["slots"]}
    assert "name" in ct_slots
    assert "name" not in se_slots
    assert {"start", "end", "body"} <= ct_slots
    assert {"start", "end", "body"} == se_slots
