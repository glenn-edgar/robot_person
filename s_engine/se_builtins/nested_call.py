"""Nested tree-call primitive — the only replacement for the LuaJIT spawn family.

`se_call_tree` is an m_call that owns a child instance of another tree. On
every event the parent forwards to this node, the child ticks synchronously
and its internal event queue drains until the child either completes or
suspends with a non-completion pipeline code.

### Sharing

The child instance shares the parent's module — meaning the dictionary,
constants, tree registry, get_time, crash_callback, and logger are all the
same objects. The child has its own event queue and its own per-node state.

### Parameters

Exactly one of:
  params["tree_name"]: str      — look up `module["trees"][name]`
  params["tree"]:      dict     — use this tree root dict directly

### Result translation at the boundary

- Application codes (0–5): propagate up unchanged (they escape the engine)
- Function codes (6–11):  converted to the equivalent pipeline code
- Pipeline codes (12–17): propagate unchanged

Rationale: function-family codes signal "escape across tree boundaries", which
is exactly what the call_tree boundary represents. Converting to pipeline
lets the parent's control op treat the child like any other pipeline child.

### Lifecycle

- INIT:     create child instance bound to target tree; forward the INIT's
            event_data as the child's first tick (timestamp-consistent behavior).
- TICK:     forward event to child; drain child's queue while not complete.
- TERMINATE: forward TERMINATE to child, then drop the reference.

Reference: se_builtins_spawn.lua:89-156 (tick_with_event_queue + se_spawn_and_tick_tree).
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    is_application,
    is_function,
    to_pipeline,
)
from se_runtime.instance import new_instance_from_tree, pop_event
from se_runtime.tick import tick_once


def _resolve_tree(inst: dict, node: dict) -> dict:
    params = node["params"]
    if "tree" in params and params["tree"] is not None:
        return params["tree"]
    if "tree_name" in params:
        name = params["tree_name"]
        tree = inst["module"]["trees"].get(name)
        if tree is None:
            raise KeyError(f"se_call_tree: unknown tree {name!r} in module registry")
        return tree
    raise ValueError("se_call_tree: params must set 'tree' or 'tree_name'")


def _result_is_complete(code: int) -> bool:
    """Child-side completion: anything other than CONTINUE or DISABLE ends the drain.

    DISABLE is NOT treated as 'still draining' here because a DISABLE from the
    child's root means the child itself completed normally. Mirrors LuaJIT's
    `result_is_complete` in se_builtins_spawn.lua:42.
    """
    return code != SE_PIPELINE_CONTINUE


def _tick_and_drain(child: dict, event_id: str, event_data: Optional[Mapping[str, Any]]) -> int:
    """Tick the child once, then drain its queue until it completes or suspends."""
    result = tick_once(child, event_id, event_data)
    while child["high_queue"] or child["normal_queue"]:
        if _result_is_complete(result):
            break
        ev = pop_event(child)
        if ev is None:
            break
        qid, qdata = ev
        result = tick_once(child, qid, qdata)
    return result


def _translate(code: int) -> int:
    """Translate a child result to what the parent's dispatch should see."""
    if is_application(code):
        return code  # escape unchanged
    if is_function(code):
        return to_pipeline(code)
    return code  # pipeline codes pass through


def _fresh_child(inst, node):
    """Build a fresh child instance with its own tree copy.

    Because per-node state lives inline on each dict, we must deep-copy the
    target tree so every call_tree invocation gets a clean tree with
    active=True, initialized=False, state=0 on every node — otherwise state
    from a prior invocation would leak into the next one (or into concurrent
    sibling invocations of the same tree).
    """
    tree = _resolve_tree(inst, node)
    tree_copy = copy.deepcopy(tree)
    return new_instance_from_tree(inst["module"], tree_copy)


def se_call_tree(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        node["user_data"] = {"child": _fresh_child(inst, node)}
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        child = (node.get("user_data") or {}).get("child")
        if child is not None:
            tick_once(child, EVENT_TERMINATE, event_data)
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    child = (node.get("user_data") or {}).get("child")
    if child is None:
        # Shouldn't happen — INIT always runs first. Defensive: re-create.
        node["user_data"] = {"child": _fresh_child(inst, node)}
        child = node["user_data"]["child"]

    result = _tick_and_drain(child, event_id, event_data)
    translated = _translate(result)

    # If child completed, allow parent's child_terminate to be a no-op.
    if translated != SE_PIPELINE_CONTINUE and not is_application(translated):
        # Drop reference on any completion (pipeline DISABLE/TERMINATE/etc).
        # Keep the dict around so TERMINATE can still find it null-gracefully.
        node["user_data"] = {"child": None}

    return translated
