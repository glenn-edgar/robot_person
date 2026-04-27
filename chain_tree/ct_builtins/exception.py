"""Exception-catch + heartbeat — three-stage MAIN/RECOVERY/FINALIZE pipeline.

Structure: an exception_catch node has EXACTLY three children, in declared
order MAIN, RECOVERY, FINALIZE. Initially only MAIN is enabled. Lifecycle:

  MAIN runs to completion ──────────► FINALIZE runs ──► catch DISABLEs
              │
              └── exception raised ──► RECOVERY runs ──► FINALIZE runs ──► catch DISABLEs

Triggered transitions:
  - CFL_RAISE_EXCEPTION_EVENT (high-pri, posted by `cfl_raise_exception`
    one-shot from any descendant): if filter says "handle here" and we're
    in MAIN → terminate MAIN, enable RECOVERY. If filter says "forward
    up" → re-enqueue to parent_exception_node (or dead-end), DISABLE.
  - Heartbeat timeout (CFL_TIMER_EVENT increments counter; >= timeout
    while in MAIN → same MAIN→RECOVERY transition).
  - Stage child disables on its own (detected on TIMER tick): advance
    MAIN→FINALIZE or RECOVERY→FINALIZE, or FINALIZE→DISABLE catch.

node["data"] schema:
    {
        "boolean_filter_fn": str,    # filter; True = forward up, False = handle here
        "logging_fn":        str,    # one-shot fired on each raise
    }

node["ct_control"]["exception_state"]:
    {
        "exception_stage":         "MAIN" | "RECOVERY" | "FINALIZE",
        "catch_links":             {"MAIN": <node>, "RECOVERY": <node>, "FINALIZE": <node>},
        "parent_exception_node":   <node | None>,
        "logging_fn":              str,
        "boolean_filter_fn":       str,
        "raised_exception":        <exception payload dict | None>,
        "heartbeat_enabled":       bool,
        "heartbeat_time_out":      int,    # timer ticks
        "heartbeat_count":         int,
        "step_count":              int,
    }
"""

from __future__ import annotations

from ct_runtime import enable_node, enqueue, terminate_node_tree
from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_EVENT_TYPE_NULL,
    CFL_HEARTBEAT_EVENT,
    CFL_RAISE_EXCEPTION_EVENT,
    CFL_SET_EXCEPTION_STEP_EVENT,
    CFL_TIMER_EVENT,
    CFL_TURN_HEARTBEAT_OFF_EVENT,
    CFL_TURN_HEARTBEAT_ON_EVENT,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
)
from ct_runtime.event_queue import make_event
from ct_runtime.registry import lookup_boolean, lookup_one_shot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_catch_ancestor(node: dict) -> "dict | None":
    """Walk parent chain; return the nearest ancestor whose main_fn_name
    is CFL_EXCEPTION_CATCH_MAIN. None if no catch ancestor exists.
    """
    cur = node["parent"]
    while cur is not None:
        if cur.get("main_fn_name") == "CFL_EXCEPTION_CATCH_MAIN":
            return cur
        cur = cur["parent"]
    return None


def _post(handle, target, event_id, data=None, priority=PRIORITY_NORMAL) -> None:
    enqueue(handle["engine"], make_event(
        target=target,
        event_type=CFL_EVENT_TYPE_NULL,
        event_id=event_id,
        data=data,
        priority=priority,
    ))


def _enter_recovery(handle, node, state) -> None:
    """Transition MAIN → RECOVERY: tear down MAIN child, enable RECOVERY."""
    main_child = state["catch_links"]["MAIN"]
    recovery_child = state["catch_links"]["RECOVERY"]
    terminate_node_tree(handle["engine"], handle, main_child)
    state["exception_stage"] = "RECOVERY"
    enable_node(recovery_child)


def _enter_finalize(handle, node, state) -> None:
    """Transition active stage → FINALIZE."""
    stage = state["exception_stage"]
    active = state["catch_links"][stage]
    terminate_node_tree(handle["engine"], handle, active)
    state["exception_stage"] = "FINALIZE"
    enable_node(state["catch_links"]["FINALIZE"])


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def cfl_exception_catch_init(handle, node) -> None:
    children = node["children"]
    if len(children) != 3:
        raise ValueError(
            f"CFL_EXCEPTION_CATCH_INIT: expected 3 children "
            f"(MAIN/RECOVERY/FINALIZE), got {len(children)}"
        )
    node["ct_control"]["exception_state"] = {
        "exception_stage": "MAIN",
        "catch_links": {
            "MAIN": children[0],
            "RECOVERY": children[1],
            "FINALIZE": children[2],
        },
        "parent_exception_node": _find_catch_ancestor(node),
        "logging_fn": node["data"].get("logging_fn", "CFL_NULL"),
        "boolean_filter_fn": node["data"].get("boolean_filter_fn", "CFL_NULL"),
        "raised_exception": None,
        "heartbeat_enabled": False,
        "heartbeat_time_out": 0,
        "heartbeat_count": 0,
        "step_count": 0,
    }
    # Disable RECOVERY and FINALIZE; enable only MAIN.
    for c in children:
        c["ct_control"]["enabled"] = False
        c["ct_control"]["initialized"] = False
    enable_node(children[0])


def cfl_exception_catch_term(handle, node) -> None:
    return None


# ---------------------------------------------------------------------------
# Main fn — the heart of the pipeline
# ---------------------------------------------------------------------------

def cfl_exception_catch_main(handle, bool_fn_name, node, event):
    state = node["ct_control"]["exception_state"]
    event_id = event["event_id"]

    # ----- Exception path -------------------------------------------------
    if event_id == CFL_RAISE_EXCEPTION_EVENT:
        return _handle_raise(handle, node, state, event)

    # ----- Heartbeat control events --------------------------------------
    if event_id == CFL_TURN_HEARTBEAT_ON_EVENT:
        state["heartbeat_enabled"] = True
        state["heartbeat_time_out"] = int(event["data"] or 0)
        state["heartbeat_count"] = 0
        return CFL_CONTINUE

    if event_id == CFL_TURN_HEARTBEAT_OFF_EVENT:
        state["heartbeat_enabled"] = False
        return CFL_CONTINUE

    if event_id == CFL_HEARTBEAT_EVENT:
        state["heartbeat_count"] = 0
        return CFL_CONTINUE

    if event_id == CFL_SET_EXCEPTION_STEP_EVENT:
        state["step_count"] = int(event["data"] or 0)
        return CFL_CONTINUE

    # ----- Timer tick: heartbeat check + stage advancement ---------------
    if event_id != CFL_TIMER_EVENT:
        return CFL_CONTINUE

    # Heartbeat timeout: only escalates from MAIN → RECOVERY.
    if state["heartbeat_enabled"] and state["exception_stage"] == "MAIN":
        state["heartbeat_count"] += 1
        if state["heartbeat_count"] >= state["heartbeat_time_out"]:
            state["heartbeat_enabled"] = False  # one-shot escalation
            _enter_recovery(handle, node, state)
            return CFL_CONTINUE

    # Stage advancement: when current stage's child has disabled, move on.
    stage = state["exception_stage"]
    active = state["catch_links"][stage]
    if active["ct_control"]["enabled"]:
        return CFL_CONTINUE

    if stage in ("MAIN", "RECOVERY"):
        _enter_finalize(handle, node, state)
        return CFL_CONTINUE

    # FINALIZE done — entire pipeline complete.
    return CFL_DISABLE


def _handle_raise(handle, node, state, event):
    """Run logging, consult filter, either handle here or forward up."""
    # Logging fires unconditionally — observers want every raise on record.
    log_name = state["logging_fn"]
    if log_name and log_name != "CFL_NULL":
        log_fn = lookup_one_shot(handle["engine"]["registry"], log_name)
        if log_fn is None:
            raise LookupError(f"exception logging fn {log_name!r} not in registry")
        # Stash the exception payload on the node so the logger can read it.
        state["raised_exception"] = dict(event["data"] or {})
        log_fn(handle, node)

    # Filter: True = forward up, False = handle here. CFL_NULL defaults to
    # False (handle here).
    forward = False
    filter_name = state["boolean_filter_fn"]
    if filter_name and filter_name != "CFL_NULL":
        filt = lookup_boolean(handle["engine"]["registry"], filter_name)
        if filt is None:
            raise LookupError(f"exception filter fn {filter_name!r} not in registry")
        forward = bool(filt(handle, node, event["event_type"], event["event_id"], event["data"]))

    # Already past MAIN stage → can't re-handle even if filter says so.
    if not forward and state["exception_stage"] != "MAIN":
        forward = True

    if forward:
        parent_catch = state["parent_exception_node"]
        if parent_catch is not None:
            _post(handle, parent_catch, CFL_RAISE_EXCEPTION_EVENT,
                  event["data"], priority=PRIORITY_HIGH)
        return CFL_DISABLE

    # Handle here: terminate MAIN, switch to RECOVERY.
    _enter_recovery(handle, node, state)
    return CFL_CONTINUE


# ---------------------------------------------------------------------------
# One-shots posted from inside a catch's subtree
# ---------------------------------------------------------------------------

def cfl_raise_exception(handle, node) -> None:
    """node['data'] = {'exception_id': str, 'exception_data': Any}"""
    target = _find_catch_ancestor(node)
    if target is None:
        raise RuntimeError(
            f"CFL_RAISE_EXCEPTION: no exception_catch ancestor for "
            f"node {node.get('name')!r}"
        )
    _post(handle, target, CFL_RAISE_EXCEPTION_EVENT, {
        "exception_id": node["data"].get("exception_id"),
        "exception_data": node["data"].get("exception_data"),
        "raising_node": node,
    }, priority=PRIORITY_HIGH)


def cfl_turn_heartbeat_on(handle, node) -> None:
    """node['data'] = {'timeout': int}  (ticks before timeout fires)"""
    target = _find_catch_ancestor(node)
    if target is None:
        raise RuntimeError(
            f"CFL_TURN_HEARTBEAT_ON: no exception_catch ancestor for "
            f"node {node.get('name')!r}"
        )
    _post(handle, target, CFL_TURN_HEARTBEAT_ON_EVENT,
          int(node["data"].get("timeout", 0)))


def cfl_turn_heartbeat_off(handle, node) -> None:
    target = _find_catch_ancestor(node)
    if target is None:
        return  # silent no-op if there's no catch — heartbeat off is harmless
    _post(handle, target, CFL_TURN_HEARTBEAT_OFF_EVENT)


def cfl_heartbeat_event(handle, node) -> None:
    target = _find_catch_ancestor(node)
    if target is None:
        return
    _post(handle, target, CFL_HEARTBEAT_EVENT)


def cfl_set_exception_step(handle, node) -> None:
    target = _find_catch_ancestor(node)
    if target is None:
        return
    _post(handle, target, CFL_SET_EXCEPTION_STEP_EVENT,
          int(node["data"].get("step", 0)))
