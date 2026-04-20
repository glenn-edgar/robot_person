"""Verify operators — pred/timeout/event-count watchdogs.

All three verify operators follow the same shape: check a condition each
tick, and on failure reset+invoke a designated "error oneshot" child, then
return either PIPELINE_RESET or PIPELINE_TERMINATE depending on the
reset_flag param.
"""

from __future__ import annotations

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_RESET,
    SE_PIPELINE_TERMINATE,
)
from se_runtime.lifecycle import (
    child_invoke_oneshot,
    child_invoke_pred,
    child_reset,
)

_NS_PER_SEC = 1_000_000_000


def _now_ns(inst, event_data):
    if event_data and "timestamp" in event_data:
        return event_data["timestamp"]
    return inst["module"]["get_time"]()


def _fail_code(node):
    return SE_PIPELINE_RESET if node["params"].get("reset_flag") else SE_PIPELINE_TERMINATE


def _fire_error(inst, node, error_child_idx):
    child_reset(inst, node, error_child_idx)
    child_invoke_oneshot(inst, node, error_child_idx)


# ---------------------------------------------------------------------------
# se_verify — evaluate pred every tick; fire error on False.
# children[0] = pred (p_call), children[1] = error oneshot
# ---------------------------------------------------------------------------

def se_verify(inst, node, event_id, event_data):
    if event_id in (EVENT_INIT, EVENT_TERMINATE):
        return SE_PIPELINE_CONTINUE

    if child_invoke_pred(inst, node, 0):
        return SE_PIPELINE_CONTINUE

    _fire_error(inst, node, 1)
    return _fail_code(node)


# ---------------------------------------------------------------------------
# se_verify_and_check_elapsed_time — fire error on timeout.
# children[0] = error oneshot
# params: {"timeout_seconds": float, "reset_flag": bool}
# ---------------------------------------------------------------------------

def se_verify_and_check_elapsed_time(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        node["user_data"] = {"start_time": _now_ns(inst, event_data)}
        return SE_PIPELINE_CONTINUE
    if event_id == EVENT_TERMINATE:
        return SE_PIPELINE_CONTINUE

    timeout_ns = int(node["params"]["timeout_seconds"] * _NS_PER_SEC)
    elapsed = _now_ns(inst, event_data) - node["user_data"]["start_time"]

    if elapsed > timeout_ns:
        _fire_error(inst, node, 0)
        return _fail_code(node)
    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_verify_and_check_elapsed_events — fire error when target_event seen too often.
# children[0] = error oneshot
# params: {"target_event_id": str, "max_count": int, "reset_flag": bool}
# ---------------------------------------------------------------------------

def se_verify_and_check_elapsed_events(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        node["user_data"] = {"count": 0}
        return SE_PIPELINE_CONTINUE
    if event_id == EVENT_TERMINATE:
        return SE_PIPELINE_CONTINUE

    if event_id == node["params"]["target_event_id"]:
        node["user_data"]["count"] += 1
        if node["user_data"]["count"] > node["params"]["max_count"]:
            _fire_error(inst, node, 0)
            return _fail_code(node)
    return SE_PIPELINE_CONTINUE
