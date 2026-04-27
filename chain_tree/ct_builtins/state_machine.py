"""CFL state-machine builtin.

A state machine is a parent node whose children are "state" columns. Only
one state is enabled at a time. Transitions are driven by high-priority
CFL_CHANGE_STATE_EVENT events targeting the SM node.

node["data"] schema:
    {
        "auto_start":            bool,
        "state_names":           [str, ...],   # declared in DSL order
        "initial_state":         str,
        "current_state_index":   int,          # set by INIT, updated on change
        "current_state_name":    str,
        "defined_states":        [str, ...],   # builder-time validation only
    }

Children of the SM node ARE the state columns, in `state_names` declared
order (the DSL re-orders them at end_state_machine to match).

Aux fn (boolean) contract: optional early-out — True → CFL_DISABLE.

Behavior per event:
  CFL_CHANGE_STATE_EVENT → if event.data.sm_node is this node:
      terminate_node_tree(current state child); enable_node(new state child);
      update current_state_index/name. Return CFL_CONTINUE so the walker
      descends into the new state.
  CFL_TIMER_EVENT → if active state child still enabled, CFL_CONTINUE;
      otherwise CFL_DISABLE (state machine done — its current state
      finished its column).
  Any other event → CFL_CONTINUE (let walker deliver to the active state).
"""

from __future__ import annotations

from ct_runtime import enable_node, enqueue, terminate_node_tree
from ct_runtime.codes import (
    CFL_CHANGE_STATE_EVENT,
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_EVENT_TYPE_NULL,
    CFL_RESET_STATE_MACHINE_EVENT,
    CFL_TERMINATE_STATE_MACHINE_EVENT,
    CFL_TIMER_EVENT,
    PRIORITY_HIGH,
)
from ct_runtime.event_queue import make_event
from ct_runtime.registry import lookup_boolean


# ---------------------------------------------------------------------------
# State machine main / init
# ---------------------------------------------------------------------------

def cfl_state_machine_main(handle, bool_fn_name, node, event):
    # Aux early-out (matches column / supervisor convention).
    if bool_fn_name and bool_fn_name != "CFL_NULL":
        bool_fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
        if bool_fn is None:
            raise LookupError(
                f"CFL_STATE_MACHINE_MAIN: aux fn {bool_fn_name!r} not in registry"
            )
        if bool_fn(handle, node, event["event_type"], event["event_id"], event["data"]):
            return CFL_DISABLE

    event_id = event["event_id"]

    if event_id == CFL_CHANGE_STATE_EVENT:
        ed = event["data"] or {}
        if ed.get("sm_node") is node:
            _do_change_state(handle, node, ed["new_state"])
        return CFL_CONTINUE

    if event_id == CFL_TERMINATE_STATE_MACHINE_EVENT:
        ed = event["data"] or {}
        if ed.get("sm_node") is node:
            terminate_node_tree(handle["engine"], handle, node)
        return CFL_CONTINUE

    if event_id == CFL_RESET_STATE_MACHINE_EVENT:
        ed = event["data"] or {}
        if ed.get("sm_node") is node:
            terminate_node_tree(handle["engine"], handle, node)
            enable_node(node)
        return CFL_CONTINUE

    if event_id != CFL_TIMER_EVENT:
        return CFL_CONTINUE

    # Normal tick: is the active state child still alive?
    idx = node["data"].get("current_state_index", 0)
    active_child = node["children"][idx]
    if active_child["ct_control"]["enabled"]:
        return CFL_CONTINUE
    return CFL_DISABLE


def cfl_state_machine_init(handle, node) -> None:
    states = node["data"]["state_names"]
    initial = node["data"]["initial_state"]
    if initial not in states:
        raise ValueError(
            f"CFL_STATE_MACHINE_INIT: initial_state {initial!r} not in {states!r}"
        )
    initial_idx = states.index(initial)

    # Disable everything; enable_node on the chosen child handles the rest.
    for c in node["children"]:
        c["ct_control"]["enabled"] = False
        c["ct_control"]["initialized"] = False
    enable_node(node["children"][initial_idx])

    node["data"]["current_state_index"] = initial_idx
    node["data"]["current_state_name"] = initial


def cfl_state_machine_term(handle, node) -> None:
    return None


# ---------------------------------------------------------------------------
# Internal helper used by both the event-driven path and the change one-shot
# ---------------------------------------------------------------------------

def _do_change_state(handle, sm_node, new_state_name) -> None:
    states = sm_node["data"]["state_names"]
    if new_state_name not in states:
        raise ValueError(
            f"change_state: {new_state_name!r} not declared in SM states {states!r}"
        )
    new_idx = states.index(new_state_name)
    cur_idx = sm_node["data"].get("current_state_index", 0)

    if new_idx != cur_idx:
        terminate_node_tree(
            handle["engine"], handle, sm_node["children"][cur_idx]
        )
    enable_node(sm_node["children"][new_idx])
    sm_node["data"]["current_state_index"] = new_idx
    sm_node["data"]["current_state_name"] = new_state_name


# ---------------------------------------------------------------------------
# One-shots used as DSL leaves to drive transitions
# ---------------------------------------------------------------------------
#
# All three read node["data"]["sm_node"] (a direct ref to the SM CFL node)
# and post a high-priority event back to the queue. The event handler
# above (in CFL_STATE_MACHINE_MAIN) does the actual state mutation when
# the event reaches the SM.

def _post_to_sm(handle, sm_node, event_id, extra=None) -> None:
    data = {"sm_node": sm_node}
    if extra:
        data.update(extra)
    enqueue(handle["engine"], make_event(
        target=sm_node,
        event_type=CFL_EVENT_TYPE_NULL,
        event_id=event_id,
        data=data,
        priority=PRIORITY_HIGH,
    ))


def cfl_change_state(handle, node) -> None:
    """node['data'] = {'sm_node': <SM ref>, 'new_state': str}"""
    _post_to_sm(
        handle,
        node["data"]["sm_node"],
        CFL_CHANGE_STATE_EVENT,
        {"new_state": node["data"]["new_state"]},
    )


def cfl_terminate_state_machine(handle, node) -> None:
    _post_to_sm(handle, node["data"]["sm_node"], CFL_TERMINATE_STATE_MACHINE_EVENT)


def cfl_reset_state_machine(handle, node) -> None:
    _post_to_sm(handle, node["data"]["sm_node"], CFL_RESET_STATE_MACHINE_EVENT)
