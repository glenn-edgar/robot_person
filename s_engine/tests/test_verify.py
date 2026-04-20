"""Verify operator tests."""

from se_builtins import oneshot as O
from se_builtins import pred as P
from se_builtins import verify as V
from se_dsl import make_node
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_RESET,
    SE_PIPELINE_TERMINATE,
    invoke_any,
    new_instance_from_tree,
    new_module,
)

_NS_PER_SEC = 1_000_000_000


def _clock():
    t = {"ns": 0}
    return (lambda: t["ns"]), (lambda s: t.update(ns=t["ns"] + int(s * _NS_PER_SEC)))


def _error_oneshot(captured, label):
    def fn(inst, node):
        captured.append(label)
    return make_node(fn, "o_call")


# ---------------------------------------------------------------------------
# se_verify
# ---------------------------------------------------------------------------

def test_verify_continues_while_pred_true():
    mod = new_module(dictionary={"ok": True})
    tree = make_node(V.se_verify, "m_call",
                     params={"reset_flag": False},
                     children=[
                         make_node(P.dict_eq, "p_call",
                                   params={"key": "ok", "value": True}),
                         _error_oneshot([], "err"),
                     ])
    inst = new_instance_from_tree(mod, tree)
    r = invoke_any(inst, tree, EVENT_TICK, {})
    assert r == SE_PIPELINE_CONTINUE


def test_verify_fires_error_and_terminates_on_pred_false():
    errors = []
    mod = new_module(dictionary={"ok": False})
    tree = make_node(V.se_verify, "m_call",
                     params={"reset_flag": False},
                     children=[
                         make_node(P.dict_eq, "p_call",
                                   params={"key": "ok", "value": True}),
                         _error_oneshot(errors, "fail"),
                     ])
    inst = new_instance_from_tree(mod, tree)
    r = invoke_any(inst, tree, EVENT_TICK, {})
    assert r == SE_PIPELINE_TERMINATE
    assert errors == ["fail"]


def test_verify_with_reset_flag_returns_reset():
    errors = []
    mod = new_module(dictionary={"ok": False})
    tree = make_node(V.se_verify, "m_call",
                     params={"reset_flag": True},
                     children=[
                         make_node(P.dict_eq, "p_call",
                                   params={"key": "ok", "value": True}),
                         _error_oneshot(errors, "fail"),
                     ])
    inst = new_instance_from_tree(mod, tree)
    r = invoke_any(inst, tree, EVENT_TICK, {})
    assert r == SE_PIPELINE_RESET


# ---------------------------------------------------------------------------
# se_verify_and_check_elapsed_time
# ---------------------------------------------------------------------------

def test_elapsed_time_fires_error_on_timeout():
    get_t, advance = _clock()
    errors = []
    mod = new_module(get_time=get_t)
    tree = make_node(V.se_verify_and_check_elapsed_time, "m_call",
                     params={"timeout_seconds": 1.0, "reset_flag": False},
                     children=[_error_oneshot(errors, "timed_out")])
    inst = new_instance_from_tree(mod, tree)

    assert invoke_any(inst, tree, EVENT_TICK, {}) == SE_PIPELINE_CONTINUE
    advance(0.5)
    assert invoke_any(inst, tree, EVENT_TICK, {}) == SE_PIPELINE_CONTINUE
    advance(1.0)  # total 1.5s > 1.0s
    assert invoke_any(inst, tree, EVENT_TICK, {}) == SE_PIPELINE_TERMINATE
    assert errors == ["timed_out"]


# ---------------------------------------------------------------------------
# se_verify_and_check_elapsed_events
# ---------------------------------------------------------------------------

def test_elapsed_events_counts_target_events_only():
    errors = []
    mod = new_module()
    tree = make_node(V.se_verify_and_check_elapsed_events, "m_call",
                     params={"target_event_id": "alarm",
                             "max_count": 2,
                             "reset_flag": False},
                     children=[_error_oneshot(errors, "over_limit")])
    inst = new_instance_from_tree(mod, tree)

    invoke_any(inst, tree, EVENT_TICK, {})
    invoke_any(inst, tree, "alarm", {})     # count=1
    invoke_any(inst, tree, "other", {})     # unchanged
    invoke_any(inst, tree, "alarm", {})     # count=2 (still within limit)
    assert errors == []
    r = invoke_any(inst, tree, "alarm", {}) # count=3 > max_count=2
    assert r == SE_PIPELINE_TERMINATE
    assert errors == ["over_limit"]
