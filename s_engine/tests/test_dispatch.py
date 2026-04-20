"""Dispatch lifecycle tests.

Builds minimal hand-written nodes (no DSL yet — DSL comes in Phase 5) to
exercise each call_type, the INIT→event→TERMINATE lifecycle, pred→pipeline
mapping, and oneshot fire-once semantics (both o_call and io_call).
"""

import pytest

from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    invoke_any,
    new_instance_from_tree,
    new_module,
    reset_recursive,
    run_until_idle,
    tick_once,
)


def _node(fn, call_type, **overrides):
    base = {
        "fn": fn,
        "call_type": call_type,
        "params": {},
        "children": [],
        "active": True,
        "initialized": False,
        "ever_init": False,
        "state": 0,
        "user_data": None,
    }
    base.update(overrides)
    return base


def test_m_call_fires_init_then_event_then_terminate():
    events: list[str] = []

    def fn(inst, node, event_id, event_data):
        events.append(event_id)
        if event_id == EVENT_TICK:
            return SE_PIPELINE_DISABLE
        return SE_PIPELINE_CONTINUE

    mod = new_module()
    node = _node(fn, "m_call")
    inst = new_instance_from_tree(mod, node)
    result = invoke_any(inst, node, EVENT_TICK, {})
    assert result == SE_PIPELINE_DISABLE
    assert events == [EVENT_INIT, EVENT_TICK, EVENT_TERMINATE]
    assert node["active"] is False
    assert node["ever_init"] is True


def test_m_call_init_fires_only_once_across_events():
    events: list[str] = []

    def fn(inst, node, event_id, event_data):
        events.append(event_id)
        return SE_PIPELINE_CONTINUE

    mod = new_module()
    node = _node(fn, "m_call")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    invoke_any(inst, node, EVENT_TICK, {})
    invoke_any(inst, node, "sensor.updated", {})
    assert events == [EVENT_INIT, EVENT_TICK, EVENT_TICK, "sensor.updated"]


def test_inactive_node_returns_continue_without_firing():
    called: list[int] = []

    def fn(inst, node, event_id, event_data):
        called.append(1)
        return SE_PIPELINE_DISABLE

    mod = new_module()
    node = _node(fn, "m_call", active=False)
    inst = new_instance_from_tree(mod, node)
    result = invoke_any(inst, node, EVENT_TICK, {})
    assert result == SE_PIPELINE_CONTINUE
    assert called == []


def test_o_call_fires_once_per_activation():
    count = [0]

    def fn(inst, node):
        count[0] += 1

    mod = new_module()
    node = _node(fn, "o_call")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    invoke_any(inst, node, EVENT_TICK)
    assert count[0] == 1
    # After reset, o_call fires again
    reset_recursive(inst, node)
    invoke_any(inst, node, EVENT_TICK)
    assert count[0] == 2


def test_io_call_survives_reset():
    count = [0]

    def fn(inst, node):
        count[0] += 1

    mod = new_module()
    node = _node(fn, "io_call")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert count[0] == 1
    reset_recursive(inst, node)
    invoke_any(inst, node, EVENT_TICK)
    assert count[0] == 1  # still 1: ever_init survived the reset


def test_p_call_true_returns_pipeline_continue():
    mod = new_module()
    node = _node(lambda inst, node: True, "p_call")
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK) == SE_PIPELINE_CONTINUE


def test_p_call_false_returns_pipeline_halt():
    mod = new_module()
    node = _node(lambda inst, node: False, "p_call")
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK) == SE_PIPELINE_HALT


def test_pred_returning_truthy_int_does_not_collide_with_result_codes():
    """Predicate returning 1 (truthy) must still go through the bool path."""
    mod = new_module()
    node = _node(lambda inst, node: 1, "p_call")  # would equal SE_HALT if dispatched as m_call
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK) == SE_PIPELINE_CONTINUE


def test_tick_once_with_inactive_root_returns_terminate():
    mod = new_module()
    node = _node(lambda *_: SE_PIPELINE_DISABLE, "m_call", active=False)
    inst = new_instance_from_tree(mod, node)
    from se_runtime import SE_PIPELINE_TERMINATE
    assert tick_once(inst) == SE_PIPELINE_TERMINATE


def test_crash_callback_fires_and_exception_propagates():
    captured = {}

    def bad_fn(inst, node, event_id, event_data):
        raise RuntimeError("boom")

    def crash(inst, node, event_id, event_data, exc, tb):
        captured["event_id"] = event_id
        captured["exc"] = exc
        captured["tb_contains"] = "RuntimeError" in tb

    mod = new_module(crash_callback=crash)
    node = _node(bad_fn, "m_call")
    inst = new_instance_from_tree(mod, node)
    with pytest.raises(RuntimeError, match="boom"):
        tick_once(inst)
    assert captured["event_id"] == EVENT_TICK
    assert isinstance(captured["exc"], RuntimeError)
    assert captured["tb_contains"] is True


def test_run_until_idle_drains_queue():
    seen: list[str] = []

    def fn(inst, node, event_id, event_data):
        seen.append(event_id)
        return SE_PIPELINE_CONTINUE

    mod = new_module()
    node = _node(fn, "m_call")
    inst = new_instance_from_tree(mod, node)
    from se_runtime import push_event
    push_event(inst, "a")
    push_event(inst, "b", priority="high")
    push_event(inst, "c")
    run_until_idle(inst)
    assert seen == [EVENT_INIT, "b", "a", "c"]


def test_run_until_idle_stops_on_disable():
    """Once the root returns PIPELINE_DISABLE, drain halts."""
    calls = [0]

    def fn(inst, node, event_id, event_data):
        calls[0] += 1
        return SE_PIPELINE_DISABLE

    mod = new_module()
    node = _node(fn, "m_call")
    inst = new_instance_from_tree(mod, node)
    from se_runtime import push_event
    push_event(inst, "a")
    push_event(inst, "b")
    run_until_idle(inst)
    # Exactly one user event processed (the first), after which root deactivates
    # The fn is called twice: INIT event + the "a" event. Then DISABLE fires TERMINATE.
    assert calls[0] == 3  # INIT + TICK(a) + TERMINATE
