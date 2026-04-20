"""Delay / timing operators.

Python time model: 64-bit monotonic **nanoseconds**. Tick events carry
`event_data["timestamp"]` when a producer wants fixed time for a whole
cascade; if absent, operators fall back to `inst.module["get_time"]()` at
the moment of the check.

All durations in `params` are specified in **seconds** (float) per spec.
Internally converted to ns when compared to timestamps. Seconds-scale
tick rates — `se_tick_delay` is deliberately not ported.
"""

from __future__ import annotations

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_RESET,
    SE_PIPELINE_TERMINATE,
)

_NS_PER_SEC = 1_000_000_000


def _now_ns(inst, event_data):
    """Prefer event_data['timestamp'], fall back to module's get_time()."""
    if event_data and "timestamp" in event_data:
        return event_data["timestamp"]
    return inst["module"]["get_time"]()


# ---------------------------------------------------------------------------
# se_time_delay — wait for a duration in seconds from activation.
# params["seconds"]: float
# node["user_data"]["deadline"]: ns timestamp
# ---------------------------------------------------------------------------

def se_time_delay(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        seconds = node["params"].get("seconds", 0.0)
        if seconds <= 0:
            node["user_data"] = {"deadline": _now_ns(inst, event_data)}
            return SE_PIPELINE_CONTINUE
        node["user_data"] = {
            "deadline": _now_ns(inst, event_data) + int(seconds * _NS_PER_SEC),
        }
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        return SE_PIPELINE_CONTINUE

    if _now_ns(inst, event_data) >= node["user_data"]["deadline"]:
        return SE_PIPELINE_DISABLE
    return SE_PIPELINE_HALT


# ---------------------------------------------------------------------------
# se_wait_event — wait for a specific event_id.
# params["event_id"]: str
# ---------------------------------------------------------------------------

def se_wait_event(inst, node, event_id, event_data):
    if event_id in (EVENT_INIT, EVENT_TERMINATE):
        return SE_PIPELINE_CONTINUE
    if event_id == node["params"]["event_id"]:
        return SE_PIPELINE_DISABLE
    return SE_PIPELINE_HALT


# ---------------------------------------------------------------------------
# se_wait — generic wait; suspends until any event arrives.
# params["include_tick"]: bool — whether a tick event counts as "arrival".
# ---------------------------------------------------------------------------

def se_wait(inst, node, event_id, event_data):
    if event_id in (EVENT_INIT, EVENT_TERMINATE):
        return SE_PIPELINE_CONTINUE
    include_tick = node["params"].get("include_tick", False)
    if event_id == EVENT_TICK and not include_tick:
        return SE_PIPELINE_HALT
    return SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_wait_timeout — wait for a specific event OR a timeout, whichever first.
# params: {"event_id": str, "seconds": float}
# Returns DISABLE on event match, TERMINATE on timeout (caller differentiates).
# ---------------------------------------------------------------------------

def se_wait_timeout(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        seconds = node["params"].get("seconds", 0.0)
        node["user_data"] = {
            "deadline": _now_ns(inst, event_data) + int(seconds * _NS_PER_SEC),
        }
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        return SE_PIPELINE_CONTINUE

    if event_id == node["params"]["event_id"]:
        return SE_PIPELINE_DISABLE

    if _now_ns(inst, event_data) >= node["user_data"]["deadline"]:
        return SE_PIPELINE_TERMINATE

    return SE_PIPELINE_HALT


# ---------------------------------------------------------------------------
# se_nop — returns PIPELINE_DISABLE immediately. Placeholder.
# ---------------------------------------------------------------------------

def se_nop(inst, node, event_id, event_data):
    if event_id in (EVENT_INIT, EVENT_TERMINATE):
        return SE_PIPELINE_CONTINUE
    return SE_PIPELINE_DISABLE
