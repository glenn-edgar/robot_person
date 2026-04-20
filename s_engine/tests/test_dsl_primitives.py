"""End-to-end DSL tests.

Exercises the public DSL surface by building trees with DSL functions,
running them through the engine, and verifying observable behavior. These
tests double as the user-facing examples for how to write a plan.
"""

import pytest

import se_dsl as dsl
from se_runtime import (
    EVENT_TICK,
    SE_FUNCTION_HALT,
    SE_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    invoke_any,
    new_instance_from_tree,
    new_module,
)

_NS_PER_SEC = 1_000_000_000


def _clock():
    t = {"ns": 0}
    return (lambda: t["ns"]), (lambda s: t.update(ns=t["ns"] + int(s * _NS_PER_SEC)))


# ---------------------------------------------------------------------------
# make_node sanity
# ---------------------------------------------------------------------------

def test_make_node_rejects_unknown_call_type():
    with pytest.raises(ValueError, match="call_type must be one of"):
        dsl.make_node(lambda *_: None, "not_a_type")


def test_make_node_populates_all_required_fields():
    node = dsl.make_node(lambda *_: None, "m_call")
    for field in ("fn", "call_type", "params", "children",
                  "active", "initialized", "ever_init", "state", "user_data"):
        assert field in node
    assert node["active"] is True
    assert node["initialized"] is False
    assert node["ever_init"] is False


# ---------------------------------------------------------------------------
# Flow control composition
# ---------------------------------------------------------------------------

def test_sequence_with_oneshots_and_dict_ops():
    plan = dsl.sequence(
        dsl.dict_set("state", "starting"),
        dsl.dict_set("state", "running"),
        dsl.dict_inc("counter", delta=5),
    )
    mod = new_module(dictionary={"counter": 0})
    inst = new_instance_from_tree(mod, plan)
    r = invoke_any(inst, plan, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["state"] == "running"
    assert mod["dictionary"]["counter"] == 5


def test_if_then_else_branches_on_dict_value():
    plan = dsl.if_then_else(
        dsl.dict_eq("mode", "on"),
        dsl.dict_set("result", "was_on"),
        dsl.dict_set("result", "was_off"),
    )
    # Wrap in sequence_once so the oneshot fires correctly as the then-branch
    # — actually if_then_else works fine with oneshot direct; invoke_any handles it.
    mod = new_module(dictionary={"mode": "on"})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"]["result"] == "was_on"

    mod2 = new_module(dictionary={"mode": "off"})
    inst2 = new_instance_from_tree(mod2, plan)
    # Reset — fresh plan since state is carried
    plan2 = dsl.if_then_else(
        dsl.dict_eq("mode", "on"),
        dsl.dict_set("result", "was_on"),
        dsl.dict_set("result", "was_off"),
    )
    inst2 = new_instance_from_tree(mod2, plan2)
    invoke_any(inst2, plan2, EVENT_TICK, {})
    assert mod2["dictionary"]["result"] == "was_off"


def test_cond_with_case_helper_and_default():
    plan = dsl.cond(
        dsl.case(dsl.dict_eq("mode", "a"), dsl.dict_set("out", "A")),
        dsl.case(dsl.dict_eq("mode", "b"), dsl.dict_set("out", "B")),
        default=dsl.dict_set("out", "default"),
    )
    mod = new_module(dictionary={"mode": "b"})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"]["out"] == "B"


def test_while_loop_runs_body_until_pred_false():
    body = dsl.sequence_once(dsl.dict_inc("n"))
    plan = dsl.while_loop(dsl.dict_lt("n", 5), body)
    mod = new_module(dictionary={"n": 0})
    inst = new_instance_from_tree(mod, plan)
    for _ in range(40):
        r = invoke_any(inst, plan, EVENT_TICK, {})
        if r == SE_PIPELINE_DISABLE:
            break
    assert mod["dictionary"]["n"] == 5


# ---------------------------------------------------------------------------
# Predicate composition
# ---------------------------------------------------------------------------

def test_pred_composition_and_or_not():
    plan = dsl.if_then(
        dsl.pred_and(
            dsl.dict_ge("level", 0),
            dsl.pred_or(
                dsl.dict_eq("mode", "run"),
                dsl.dict_eq("mode", "warm"),
            ),
            dsl.pred_not(dsl.dict_eq("faulted", True)),
        ),
        dsl.dict_set("result", "ok"),
    )
    mod = new_module(dictionary={"level": 5, "mode": "warm", "faulted": False})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"]["result"] == "ok"


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def test_state_machine_transitions_via_dsl():
    plan = dsl.state_machine(
        states={
            "idle": dsl.dict_set("state_tag", "idle"),
            "running": dsl.dict_set("state_tag", "running"),
        },
        transitions={
            ("idle", "start"): "running",
            ("running", "stop"): "idle",
        },
        initial="idle",
    )
    mod = new_module(dictionary={})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"]["state_tag"] == "idle"
    invoke_any(inst, plan, "start", {})
    assert mod["dictionary"]["state_tag"] == "running"


def test_state_machine_rejects_initial_not_in_states():
    with pytest.raises(ValueError, match="initial"):
        dsl.state_machine(
            states={"idle": dsl.nop()},
            transitions={},
            initial="nope",
        )


# ---------------------------------------------------------------------------
# Event dispatch
# ---------------------------------------------------------------------------

def test_event_dispatch_routes_by_event_id():
    plan = dsl.event_dispatch({
        "alpha": dsl.dict_set("last", "A"),
        "beta": dsl.dict_set("last", "B"),
    })
    mod = new_module(dictionary={})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, "alpha", {})
    assert mod["dictionary"]["last"] == "A"
    invoke_any(inst, plan, "beta", {})
    assert mod["dictionary"]["last"] == "B"


# ---------------------------------------------------------------------------
# Nested tree call
# ---------------------------------------------------------------------------

def test_call_tree_with_direct_ref():
    child = dsl.sequence_once(dsl.dict_inc("shared"))
    parent = dsl.sequence(dsl.call_tree(child), dsl.dict_set("done", True))
    mod = new_module(dictionary={"shared": 0})
    inst = new_instance_from_tree(mod, parent)
    r = invoke_any(inst, parent, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["shared"] == 1
    assert mod["dictionary"]["done"] is True


def test_call_tree_with_name_lookup():
    from se_runtime import register_tree

    child = dsl.sequence_once(dsl.dict_inc("hit"))
    mod = new_module(dictionary={"hit": 0})
    register_tree(mod, "sub", child)

    parent = dsl.call_tree("sub")
    inst = new_instance_from_tree(mod, parent)
    invoke_any(inst, parent, EVENT_TICK, {})
    assert mod["dictionary"]["hit"] == 1


# ---------------------------------------------------------------------------
# Return code leaves
# ---------------------------------------------------------------------------

def test_return_halt_leaf_escapes_application_code():
    plan = dsl.sequence(dsl.return_halt())
    mod = new_module()
    inst = new_instance_from_tree(mod, plan)
    r = invoke_any(inst, plan, EVENT_TICK, {})
    assert r == SE_HALT  # application halt escapes out of sequence


def test_return_function_halt_rewritten_by_sequence_to_pipeline_halt():
    plan = dsl.sequence(dsl.return_function_halt())
    mod = new_module()
    inst = new_instance_from_tree(mod, plan)
    r = invoke_any(inst, plan, EVENT_TICK, {})
    assert r == SE_PIPELINE_HALT


# ---------------------------------------------------------------------------
# Delay operators with injected clock
# ---------------------------------------------------------------------------

def test_time_delay_dsl():
    get_t, advance = _clock()
    mod = new_module(get_time=get_t)
    plan = dsl.time_delay(1.0)
    inst = new_instance_from_tree(mod, plan)
    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_HALT
    advance(1.5)
    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_DISABLE


def test_wait_event_and_wait_timeout():
    get_t, advance = _clock()
    mod = new_module(get_time=get_t)
    plan = dsl.wait_timeout("done", 2.0)
    inst = new_instance_from_tree(mod, plan)
    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_HALT
    assert invoke_any(inst, plan, "done", {}) == SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# Logger wiring through DSL
# ---------------------------------------------------------------------------

def test_log_and_dict_log_via_dsl():
    captured = []
    plan = dsl.sequence(
        dsl.log("hello"),
        dsl.dict_log("pressure:", "pressure"),
    )
    mod = new_module(dictionary={"pressure": 42}, logger=captured.append)
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert captured == ["[log] hello", "[dict_log] pressure: pressure=42"]
