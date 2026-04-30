"""sequence-til builtins — CFL_SEQUENCE_{PASS,FAIL}_MAIN + CFL_MARK_SEQUENCE.

A "sequence-til-pass" runs children sequentially and stops at the first
pass: `try strategy A; if it failed, try B; if B failed, try C; ...`.
A "sequence-til-fail" runs sequentially and stops at the first failure:
`A must pass; then B; then C; report whichever fails first`.

Each child is typically a column that, before disabling, calls
CFL_MARK_SEQUENCE to record its pass/fail outcome. The sequence node
polls "is the current child still enabled?" each tick; when the child
disables, it reads the recorded result and decides whether to advance,
finalize-success, or finalize-failure.

node["ct_control"]["sequence_state"] schema:
    {
        "current_index": int,            # which child is active
        "results":       [               # one entry per child position
            None | {"status": bool, "data": Any},
            ...
        ],
        "final_status":  None | bool,    # set on finalize
        "finalize_fn":   str,            # one-shot, "CFL_NULL" = none
    }

node["data"] schema:
    {
        "finalize_fn": str,              # mirrors ct_control for INIT setup
        "user_data":   Any,
    }

CFL_MARK_SEQUENCE node["data"] schema:
    {
        "parent_node": <ref>,            # direct ref to the sequence node
        "result":      bool,
        "data":        Any,
    }
"""

from __future__ import annotations

from ct_runtime import enable_node, terminate_node_tree
from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_TIMER_EVENT,
)
from ct_runtime.registry import lookup_boolean, lookup_one_shot


# ---------------------------------------------------------------------------
# Public main fns — pass and fail flavors share most logic
# ---------------------------------------------------------------------------

def cfl_sequence_pass_main(handle, bool_fn_name, node, event):
    return _common_main(handle, bool_fn_name, node, event, stop_on=True)


def cfl_sequence_fail_main(handle, bool_fn_name, node, event):
    return _common_main(handle, bool_fn_name, node, event, stop_on=False)


def _common_main(handle, bool_fn_name, node, event, *, stop_on: bool):
    """`stop_on` is the result value that ENDS the sequence early.
    pass-til: stop_on=True (first pass wins).
    fail-til: stop_on=False (first fail wins).
    """
    if bool_fn_name and bool_fn_name != "CFL_NULL":
        bool_fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
        if bool_fn is None:
            raise LookupError(
                f"sequence_til: aux fn {bool_fn_name!r} not in registry"
            )
        if bool_fn(handle, node, event["event_type"], event["event_id"], event["data"]):
            return CFL_DISABLE

    if event["event_id"] != CFL_TIMER_EVENT:
        return CFL_CONTINUE

    state = node["ct_control"]["sequence_state"]
    idx = state["current_index"]
    children = node["children"]
    if not children:
        return CFL_DISABLE

    active_child = children[idx]
    if active_child["ct_control"]["enabled"]:
        return CFL_CONTINUE

    # Active child has disabled — must have called CFL_MARK_SEQUENCE.
    if idx >= len(state["results"]) or state["results"][idx] is None:
        raise RuntimeError(
            f"sequence_til: child at index {idx} ({active_child.get('name')!r}) "
            f"disabled without calling CFL_MARK_SEQUENCE"
        )
    status = state["results"][idx]["status"]

    if status == stop_on:
        # Early exit: the result we were waiting for. Finalize & disable.
        state["final_status"] = status
        _fire_finalize(handle, node)
        return CFL_DISABLE

    # Wrong polarity: try the next child.
    if idx + 1 >= len(children):
        # Exhausted — finalize with the opposite status. (For pass-til:
        # all failed → final_status = False. For fail-til: all passed →
        # final_status = True.)
        state["final_status"] = status
        _fire_finalize(handle, node)
        return CFL_DISABLE

    # Tear the just-finished child down (paranoia — it's already disabled
    # but its descendants may still need cleanup if it disabled via its
    # column going empty rather than explicit terminate).
    terminate_node_tree(handle["engine"], handle, active_child)
    state["current_index"] = idx + 1
    enable_node(children[idx + 1])
    return CFL_CONTINUE


def _fire_finalize(handle, node) -> None:
    fn_name = node["ct_control"]["sequence_state"].get("finalize_fn", "CFL_NULL")
    if not fn_name or fn_name == "CFL_NULL":
        return
    fn = lookup_one_shot(handle["engine"]["registry"], fn_name)
    if fn is None:
        raise LookupError(f"sequence_til: finalize fn {fn_name!r} not in registry")
    fn(handle, node)


# ---------------------------------------------------------------------------
# INIT / TERM
# ---------------------------------------------------------------------------

def cfl_sequence_init(handle, node) -> None:
    """Reset sequence state and enable only the first child."""
    if not node["children"]:
        raise ValueError(
            f"sequence_til {node.get('name')!r}: must have at least one child"
        )
    node["ct_control"]["sequence_state"] = {
        "current_index": 0,
        "results": [None] * len(node["children"]),
        "final_status": None,
        "finalize_fn": node["data"].get("finalize_fn", "CFL_NULL"),
    }
    # Disable any leftover state on children before enabling the first.
    for c in node["children"]:
        c["ct_control"]["enabled"] = False
        c["ct_control"]["initialized"] = False
    enable_node(node["children"][0])


def cfl_sequence_term(handle, node) -> None:
    return None


# ---------------------------------------------------------------------------
# CFL_MARK_SEQUENCE one-shot
# ---------------------------------------------------------------------------

def cfl_mark_sequence(handle, node) -> None:
    parent = node["data"].get("parent_node")
    if parent is None:
        return  # no-op if not configured
    state = parent["ct_control"].get("sequence_state")
    if state is None:
        return  # no-op if parent isn't a sequence node
    idx = state["current_index"]
    while len(state["results"]) <= idx:
        state["results"].append(None)
    state["results"][idx] = {
        "status": bool(node["data"]["result"]),
        "data": node["data"].get("data"),
    }


def cfl_mark_sequence_if(handle, node) -> None:
    """One-shot variant of CFL_MARK_SEQUENCE that consults a boolean
    predicate to decide pass vs fail.

    node["data"] schema:
        {
            "parent_node":   <sequence_til parent node ref>,
            "predicate_fn":  str (registered boolean fn name),
            "true_data":     Any (recorded if predicate True),
            "false_data":    Any (recorded if predicate False),
        }

    Used by the `retry_until_success` macro: each attempt column probes
    the user-supplied predicate and marks pass-or-fail accordingly,
    letting `sequence_til_pass` short-circuit on the first success.
    """
    from ct_runtime.codes import CFL_EVENT_TYPE_NULL
    from ct_runtime.registry import lookup_boolean

    parent = node["data"].get("parent_node")
    if parent is None:
        return
    state = parent["ct_control"].get("sequence_state")
    if state is None:
        return

    pred_name = node["data"].get("predicate_fn")
    if not pred_name or pred_name == "CFL_NULL":
        return
    pred = lookup_boolean(handle["engine"]["registry"], pred_name)
    if pred is None:
        raise LookupError(
            f"CFL_MARK_SEQUENCE_IF: predicate {pred_name!r} not in registry"
        )
    result = bool(pred(handle, node, CFL_EVENT_TYPE_NULL,
                       "CFL_MARK_PROBE", None))

    idx = state["current_index"]
    while len(state["results"]) <= idx:
        state["results"].append(None)
    state["results"][idx] = {
        "status": result,
        "data": node["data"].get("true_data" if result else "false_data"),
    }
