"""Node-level lifecycle helpers used by control functions.

These operate on children directly (by index into `node["children"]`) rather
than on named references. Every node carries its own state inline; there is no
parallel node_states array. Mirrors LuaJIT se_runtime.lua:470-545.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from se_runtime.codes import EVENT_TERMINATE


def child_count(node: dict) -> int:
    return len(node.get("children") or ())


def _reset_node_state(child: dict) -> None:
    """Reactivate a child to uninitialized state. `ever_init` preserved."""
    child["active"] = True
    child["initialized"] = False
    child["state"] = 0
    child["user_data"] = None
    if "deadline" in child:
        child["deadline"] = None


def _deactivate_node_state(child: dict) -> None:
    """Deactivate a child after terminate. `ever_init` preserved."""
    child["active"] = False
    child["initialized"] = False
    child["state"] = 0
    child["user_data"] = None
    if "deadline" in child:
        child["deadline"] = None


def child_invoke(
    inst: dict,
    node: dict,
    idx: int,
    event_id: str,
    event_data: Optional[Mapping[str, Any]] = None,
) -> int:
    """Invoke child by 0-based index via the generic dispatcher."""
    from se_runtime.dispatch import invoke_any

    child = node["children"][idx]
    return invoke_any(inst, child, event_id, event_data)


def child_invoke_pred(inst: dict, node: dict, idx: int) -> bool:
    from se_runtime.dispatch import invoke_pred

    child = node["children"][idx]
    return invoke_pred(inst, child)


def child_invoke_oneshot(inst: dict, node: dict, idx: int) -> None:
    from se_runtime.dispatch import invoke_oneshot

    child = node["children"][idx]
    invoke_oneshot(inst, child)


def child_terminate(inst: dict, node: dict, idx: int) -> None:
    """Terminate a child — fire TERMINATE on initialized m_call, then deactivate.

    Oneshots and preds are stateless-by-lifecycle at terminate time; their
    state/flags are cleared without calling the fn. A child that was already
    uninitialized (e.g., never activated, or cleaned up by invoke_main's
    self-DISABLE path) is not re-TERMINATEd — avoiding LuaJIT's double-fire.
    """
    children = node.get("children") or ()
    if idx < 0 or idx >= len(children):
        return
    child = children[idx]
    if child.get("call_type") == "m_call" and child.get("initialized"):
        inst["current_event_id"] = EVENT_TERMINATE
        inst["current_event_data"] = {}
        child["fn"](inst, child, EVENT_TERMINATE, {})
    _deactivate_node_state(child)


def child_reset(inst: dict, node: dict, idx: int) -> None:
    """Reset a single child (no terminate call; state cleared)."""
    children = node.get("children") or ()
    if idx < 0 or idx >= len(children):
        return
    _reset_node_state(children[idx])


def reset_recursive(inst: dict, subtree_root: dict) -> None:
    """Recursively reset every node in a subtree, preserving ever_init."""
    _reset_node_state(subtree_root)
    for child in subtree_root.get("children") or ():
        reset_recursive(inst, child)


def child_reset_recursive(inst: dict, node: dict, idx: int) -> None:
    children = node.get("children") or ()
    if idx < 0 or idx >= len(children):
        return
    reset_recursive(inst, children[idx])


def children_terminate_all(inst: dict, node: dict) -> None:
    """Terminate children in reverse order, then reset all."""
    children = node.get("children") or ()
    for idx in range(len(children) - 1, -1, -1):
        child_terminate(inst, node, idx)
    for child in children:
        _reset_node_state(child)


def children_reset_all(inst: dict, node: dict) -> None:
    """Reset all children without calling terminate first."""
    for child in node.get("children") or ():
        _reset_node_state(child)
