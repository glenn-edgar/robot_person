"""Dispatch operators — route events/values to subtrees.

Python port uses the spec's (cleaner) models instead of LuaJIT's integer
case-value scheme:

  event_dispatch :  params["mapping"] = {event_id_str: child_index}
  state_machine  :  params = {"states": {name: child_idx},
                              "transitions": {(state, event_id): next_state},
                              "initial": state_name}
  dict_dispatch  :  params = {"key": dict_key, "mapping": {value: child_idx}}

Unmatched events/values pass through as PIPELINE_CONTINUE (no error). This
differs from the LuaJIT Erlang-style crash; the spec §706 makes it explicit
("no match → PIPELINE_CONTINUE (passthrough, subtree unaffected)").
"""

from __future__ import annotations

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    SE_FUNCTION_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_RESET,
    SE_PIPELINE_SKIP_CONTINUE,
    SE_PIPELINE_TERMINATE,
)
from se_runtime.lifecycle import (
    child_invoke,
    child_reset_recursive,
    child_terminate,
)


# ---------------------------------------------------------------------------
# Shared: invoke an action child and normalize its pipeline result.
# ---------------------------------------------------------------------------

def _invoke_and_handle(inst, node, child_idx, event_id, event_data):
    r = child_invoke(inst, node, child_idx, event_id, event_data)

    # Non-pipeline codes propagate
    if r < SE_PIPELINE_CONTINUE:
        return r

    if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
        return r

    if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE, SE_PIPELINE_RESET):
        child_terminate(inst, node, child_idx)
        child_reset_recursive(inst, node, child_idx)
        return SE_PIPELINE_CONTINUE

    if r == SE_PIPELINE_SKIP_CONTINUE:
        return SE_PIPELINE_CONTINUE

    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_event_dispatch — route by event_id string.
# params["mapping"] = {event_id_str: child_index}
# node["user_data"] = last-invoked child index (None = none active)
# ---------------------------------------------------------------------------

def se_event_dispatch(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        prev = node.get("user_data")
        if prev is not None:
            child_terminate(inst, node, prev)
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    mapping = node["params"].get("mapping") or {}
    idx = mapping.get(event_id)
    if idx is None:
        return SE_PIPELINE_CONTINUE  # passthrough

    prev = node.get("user_data")
    if prev is not None and prev != idx:
        child_terminate(inst, node, prev)
        child_reset_recursive(inst, node, prev)
    node["user_data"] = idx

    return _invoke_and_handle(inst, node, idx, event_id, event_data)


# ---------------------------------------------------------------------------
# se_state_machine — named states with transition table.
# params: {"states": {name: child_idx},
#          "transitions": {(state, event_id): next_state},
#          "initial": state_name}
# node["user_data"] = current state name
# ---------------------------------------------------------------------------

def se_state_machine(inst, node, event_id, event_data):
    params = node["params"]
    states = params["states"]
    transitions = params.get("transitions") or {}

    if event_id == EVENT_INIT:
        node["user_data"] = params["initial"]
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        current = node.get("user_data")
        if current is not None:
            idx = states.get(current)
            if idx is not None:
                child_terminate(inst, node, idx)
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    current = node["user_data"]
    next_state = transitions.get((current, event_id))

    if next_state is not None and next_state != current:
        # Transition: terminate current child, switch, then invoke new
        current_idx = states.get(current)
        if current_idx is not None:
            child_terminate(inst, node, current_idx)
            child_reset_recursive(inst, node, current_idx)
        node["user_data"] = next_state
        current = next_state

    child_idx = states.get(current)
    if child_idx is None:
        return SE_PIPELINE_CONTINUE  # unmapped state → passthrough

    r = child_invoke(inst, node, child_idx, event_id, event_data)

    if r == SE_FUNCTION_HALT:
        return SE_PIPELINE_HALT
    if r < SE_PIPELINE_CONTINUE:
        return r
    if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
        return r
    if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE, SE_PIPELINE_RESET):
        child_terminate(inst, node, child_idx)
        child_reset_recursive(inst, node, child_idx)
        return SE_PIPELINE_CONTINUE
    if r == SE_PIPELINE_SKIP_CONTINUE:
        return SE_PIPELINE_CONTINUE
    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_dict_dispatch — route by dictionary[key] value.
# params = {"key": str, "mapping": {value: child_index}}
# node["user_data"] = last-invoked child index
# ---------------------------------------------------------------------------

def se_dict_dispatch(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        prev = node.get("user_data")
        if prev is not None:
            child_terminate(inst, node, prev)
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    key = node["params"]["key"]
    mapping = node["params"].get("mapping") or {}
    value = inst["module"]["dictionary"].get(key)
    idx = mapping.get(value)

    if idx is None:
        return SE_PIPELINE_CONTINUE  # passthrough

    prev = node.get("user_data")
    if prev is not None and prev != idx:
        child_terminate(inst, node, prev)
        child_reset_recursive(inst, node, prev)
    node["user_data"] = idx

    return _invoke_and_handle(inst, node, idx, event_id, event_data)
