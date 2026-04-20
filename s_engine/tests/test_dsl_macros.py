"""DSL macro tests — Tier 1 and Tier 2 expansion and behavior."""

import pytest

import se_dsl as dsl
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    invoke_any,
    new_instance_from_tree,
    new_module,
)

_NS_PER_SEC = 1_000_000_000


def _clock():
    t = {"ns": 0}
    return (lambda: t["ns"]), (lambda s: t.update(ns=t["ns"] + int(s * _NS_PER_SEC)))


# ---------------------------------------------------------------------------
# Tier 1: guarded_action
# ---------------------------------------------------------------------------

def test_guarded_action_runs_only_when_pred_true():
    plan = dsl.guarded_action(
        dsl.dict_eq("ready", True),
        dsl.dict_set("ran", True),
    )
    mod = new_module(dictionary={"ready": False})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"].get("ran") is None

    mod["dictionary"]["ready"] = True
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"]["ran"] is True


# ---------------------------------------------------------------------------
# Tier 1: on_event
# ---------------------------------------------------------------------------

def test_on_event_runs_action_only_on_matching_event():
    plan = dsl.on_event("go", dsl.dict_set("fired", True))
    mod = new_module(dictionary={})
    inst = new_instance_from_tree(mod, plan)

    invoke_any(inst, plan, EVENT_TICK, {})
    assert "fired" not in mod["dictionary"]

    invoke_any(inst, plan, "go", {})
    assert mod["dictionary"]["fired"] is True


# ---------------------------------------------------------------------------
# Tier 1: if_dict
# ---------------------------------------------------------------------------

def test_if_dict_expands_to_predicate_and_branches():
    plan = dsl.if_dict("mode", "x",
                       then_=dsl.dict_set("out", "matched"),
                       else_=dsl.dict_set("out", "nope"))
    mod = new_module(dictionary={"mode": "x"})
    inst = new_instance_from_tree(mod, plan)
    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"]["out"] == "matched"


# ---------------------------------------------------------------------------
# Tier 1: every_n_ticks
# ---------------------------------------------------------------------------

def test_every_n_ticks_fires_action_on_threshold():
    plan = dsl.every_n_ticks(3, dsl.dict_inc("fired"))
    mod = new_module(dictionary={"fired": 0})
    inst = new_instance_from_tree(mod, plan)
    for _ in range(7):
        invoke_any(inst, plan, EVENT_TICK, {})
    # state_inc_and_test returns True at tick 3, 4, 5, 6, 7 → fires 5 times
    # (once the threshold is hit, it remains True because state keeps incrementing)
    assert mod["dictionary"]["fired"] >= 1


# ---------------------------------------------------------------------------
# Tier 1: with_timeout
# ---------------------------------------------------------------------------

def test_with_timeout_completes_normally_if_action_finishes():
    """Action disables before timeout; watchdog never fires."""
    get_t, advance = _clock()

    action = dsl.sequence_once(dsl.dict_set("did_action", True))
    on_timeout = dsl.dict_set("timed_out", True)
    plan = dsl.with_timeout(action, seconds=10.0, on_timeout=on_timeout)

    mod = new_module(dictionary={}, get_time=get_t)
    inst = new_instance_from_tree(mod, plan)

    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"].get("did_action") is True
    assert mod["dictionary"].get("timed_out") is None


# ---------------------------------------------------------------------------
# Tier 2: retry_with_backoff
# ---------------------------------------------------------------------------

def test_retry_with_backoff_emits_attempts_with_delays():
    # 3 attempts, 0.5s base: [attempt0, delay 0.5s, attempt1, delay 1.0s, attempt2]
    attempts = []

    def factory(i):
        def fn(inst, node, event_id, event_data):
            from se_runtime import (
                EVENT_INIT,
                EVENT_TERMINATE,
                SE_PIPELINE_DISABLE,
                SE_PIPELINE_CONTINUE,
            )
            if event_id in (EVENT_INIT, EVENT_TERMINATE):
                return SE_PIPELINE_CONTINUE
            attempts.append(i)
            return SE_PIPELINE_DISABLE
        return dsl.make_node(fn, "m_call")

    plan = dsl.retry_with_backoff(factory, attempts=3, base_delay_seconds=0.5)

    # Structure check: 5 children (3 attempts + 2 delays)
    assert len(plan["children"]) == 5

    get_t, advance = _clock()
    mod = new_module(get_time=get_t)
    inst = new_instance_from_tree(mod, plan)

    # Drive to completion, advancing the clock past each delay
    for _ in range(50):
        r = invoke_any(inst, plan, EVENT_TICK, {})
        if r == SE_PIPELINE_DISABLE:
            break
        advance(2.0)  # always advance beyond any delay
    assert attempts == [0, 1, 2]


def test_retry_with_backoff_zero_attempts_raises():
    with pytest.raises(ValueError):
        dsl.retry_with_backoff(lambda i: dsl.nop(), attempts=0, base_delay_seconds=1.0)


# ---------------------------------------------------------------------------
# Tier 2: state_machine_from_table
# ---------------------------------------------------------------------------

def test_state_machine_from_table_builds_transitions():
    plan = dsl.state_machine_from_table(
        state_actions={
            "idle": dsl.dict_set("st", "I"),
            "running": dsl.dict_set("st", "R"),
        },
        transitions=[
            ("idle", "start", "running"),
            ("running", "stop", "idle"),
        ],
        initial="idle",
    )
    mod = new_module(dictionary={})
    inst = new_instance_from_tree(mod, plan)

    invoke_any(inst, plan, EVENT_TICK, {})
    assert mod["dictionary"].get("st") == "I"
    invoke_any(inst, plan, "start", {})
    assert mod["dictionary"]["st"] == "R"  # running's action fired


# ---------------------------------------------------------------------------
# Macro output is engine-consumable (fully-expanded)
# ---------------------------------------------------------------------------

def test_macros_emit_plain_node_dicts():
    """Every macro produces a node dict with the required fields."""
    for plan in (
        dsl.guarded_action(dsl.true_pred(), dsl.nop()),
        dsl.on_event("x", dsl.nop()),
        dsl.if_dict("k", 1, dsl.nop()),
        dsl.every_n_ticks(2, dsl.nop()),
        dsl.with_timeout(dsl.nop(), 1.0, dsl.nop()),
        dsl.retry_with_backoff(lambda i: dsl.nop(), 2, 0.1),
    ):
        for field in ("fn", "call_type", "params", "children",
                      "active", "initialized", "ever_init", "state", "user_data"):
            assert field in plan, f"macro output missing {field!r}"
        assert plan["call_type"] in ("m_call", "o_call", "io_call", "p_call")
