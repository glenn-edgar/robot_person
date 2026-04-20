"""Delay / timing operator tests. Uses a manually controlled clock."""

from se_builtins import delays as T
from se_builtins import pred as P
from se_dsl import make_node
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_TERMINATE,
    invoke_any,
    new_instance_from_tree,
    new_module,
)

_NS_PER_SEC = 1_000_000_000


def _clock():
    """Returns (get_time_fn, advance_seconds_fn) over a mutable ns clock."""
    t = {"ns": 0}
    return (lambda: t["ns"]), (lambda s: t.update(ns=t["ns"] + int(s * _NS_PER_SEC)))


# ---------------------------------------------------------------------------
# se_time_delay
# ---------------------------------------------------------------------------

def test_time_delay_halts_until_deadline_then_disables():
    get_t, advance = _clock()
    mod = new_module(get_time=get_t)
    node = make_node(T.se_time_delay, "m_call", params={"seconds": 2.0})
    inst = new_instance_from_tree(mod, node)

    # First tick: INIT fires, stores deadline; return HALT because not yet expired
    r = invoke_any(inst, node, EVENT_TICK, {})
    assert r == SE_PIPELINE_HALT

    advance(1.0)
    r = invoke_any(inst, node, EVENT_TICK, {})
    assert r == SE_PIPELINE_HALT

    advance(1.5)  # total 2.5s, past 2.0s deadline
    r = invoke_any(inst, node, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE


def test_time_delay_with_zero_seconds_is_instant():
    get_t, _ = _clock()
    mod = new_module(get_time=get_t)
    node = make_node(T.se_time_delay, "m_call", params={"seconds": 0})
    inst = new_instance_from_tree(mod, node)
    r = invoke_any(inst, node, EVENT_TICK, {})
    # Deadline equals now → DISABLE
    assert r == SE_PIPELINE_DISABLE


def test_time_delay_uses_event_data_timestamp_if_provided():
    get_t, _ = _clock()
    mod = new_module(get_time=get_t)
    node = make_node(T.se_time_delay, "m_call", params={"seconds": 1.0})
    inst = new_instance_from_tree(mod, node)

    ts0 = 1_000_000_000
    r = invoke_any(inst, node, EVENT_TICK, {"timestamp": ts0})
    assert r == SE_PIPELINE_HALT

    # Later timestamp beyond deadline → DISABLE (clock untouched)
    r = invoke_any(inst, node, EVENT_TICK, {"timestamp": ts0 + 2 * _NS_PER_SEC})
    assert r == SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_wait_event
# ---------------------------------------------------------------------------

def test_wait_event_disables_on_match():
    mod = new_module()
    node = make_node(T.se_wait_event, "m_call", params={"event_id": "go"})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT
    assert invoke_any(inst, node, "other", {}) == SE_PIPELINE_HALT
    assert invoke_any(inst, node, "go", {}) == SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_wait
# ---------------------------------------------------------------------------

def test_wait_without_include_tick_ignores_ticks():
    mod = new_module()
    node = make_node(T.se_wait, "m_call", params={"include_tick": False})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT
    assert invoke_any(inst, node, "any_event", {}) == SE_PIPELINE_DISABLE


def test_wait_with_include_tick_triggers_on_tick():
    mod = new_module()
    node = make_node(T.se_wait, "m_call", params={"include_tick": True})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_wait_timeout
# ---------------------------------------------------------------------------

def test_wait_timeout_disables_on_matching_event():
    get_t, _ = _clock()
    mod = new_module(get_time=get_t)
    node = make_node(T.se_wait_timeout, "m_call",
                     params={"event_id": "done", "seconds": 10.0})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT
    assert invoke_any(inst, node, "done", {}) == SE_PIPELINE_DISABLE


def test_wait_timeout_terminates_on_timeout():
    get_t, advance = _clock()
    mod = new_module(get_time=get_t)
    node = make_node(T.se_wait_timeout, "m_call",
                     params={"event_id": "done", "seconds": 1.0})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT
    advance(2.0)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_TERMINATE


# ---------------------------------------------------------------------------
# se_nop
# ---------------------------------------------------------------------------

def test_nop_returns_pipeline_disable():
    mod = new_module()
    node = make_node(T.se_nop, "m_call")
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_DISABLE
