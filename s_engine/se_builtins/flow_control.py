"""Flow-control operators (all m_call).

Each operator below is the `fn` field of an m_call node. Parent control
functions call `invoke_any` on children directly (via the child_* helpers),
dispatching on the returned three-family result code.

The canonical dispatch rules inside `sequence` are load-bearing — the
FUNCTION_HALT → PIPELINE_HALT rewrite, the "application codes propagate
unchanged" rule, the "child still running if pipeline CONTINUE or HALT"
rule. Same rules appear in fork/chain_flow with minor variations; each
operator documents its specifics.

Reference: se_builtins_flow_control.lua:61-902.
"""

from __future__ import annotations

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    SE_FUNCTION_CONTINUE,
    SE_FUNCTION_DISABLE,
    SE_FUNCTION_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_RESET,
    SE_PIPELINE_SKIP_CONTINUE,
    SE_PIPELINE_TERMINATE,
    SE_SKIP_CONTINUE,
    is_application,
    is_function,
)
from se_runtime.lifecycle import (
    child_invoke,
    child_invoke_pred,
    child_reset,
    child_reset_recursive,
    child_terminate,
    children_reset_all,
    children_terminate_all,
)

# Fork FSM states (match LuaJIT C constants)
_FORK_STATE_RUNNING = 1
_FORK_STATE_COMPLETE = 2

# While FSM states
_WHILE_EVAL_PRED = 0
_WHILE_RUN_BODY = 1


# ---------------------------------------------------------------------------
# se_sequence — foundational dispatcher. Other operators mirror its table.
# ---------------------------------------------------------------------------

def se_sequence(inst, node, event_id, event_data):
    children = node.get("children") or ()
    n = len(children)

    if event_id == EVENT_INIT:
        node["state"] = 0
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        s = node["state"]
        if s < n:
            child = children[s]
            if child.get("initialized"):
                child_terminate(inst, node, s)
        node["state"] = 0
        return SE_PIPELINE_CONTINUE

    # TICK: may advance multiple children in one pass
    while node["state"] < n:
        s = node["state"]
        child = children[s]
        ct = child["call_type"]

        if ct in ("o_call", "io_call", "p_call"):
            child_invoke(inst, node, s, event_id, event_data)
            node["state"] = s + 1
            continue

        # m_call
        r = child_invoke(inst, node, s, event_id, event_data)

        # Application codes (0-5) propagate unchanged
        if is_application(r):
            return r

        # Function codes (6-11): propagate; FUNCTION_HALT → PIPELINE_HALT
        if is_function(r):
            if r == SE_FUNCTION_HALT:
                return SE_PIPELINE_HALT
            return r

        # Pipeline codes (12-17)
        if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
            return SE_PIPELINE_CONTINUE  # child still running; pause

        if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE, SE_PIPELINE_RESET):
            child_terminate(inst, node, s)
            node["state"] = s + 1
            continue

        if r == SE_PIPELINE_SKIP_CONTINUE:
            return SE_PIPELINE_CONTINUE

        return SE_PIPELINE_CONTINUE  # unknown: pause

    return SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_sequence_once — fire every child exactly once in a single tick.
# ---------------------------------------------------------------------------

def se_sequence_once(inst, node, event_id, event_data):
    children = node.get("children") or ()

    if event_id == EVENT_INIT:
        node["state"] = 0
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_TERMINATE:
        for idx, child in enumerate(children):
            if child.get("initialized"):
                child_terminate(inst, node, idx)
        node["state"] = 0
        return SE_PIPELINE_CONTINUE

    for idx, child in enumerate(children):
        ct = child["call_type"]
        if ct in ("o_call", "io_call", "p_call"):
            child_invoke(inst, node, idx, event_id, event_data)
            continue
        r = child_invoke(inst, node, idx, event_id, event_data)
        if r not in (SE_PIPELINE_CONTINUE, SE_PIPELINE_DISABLE):
            break

    for idx, child in enumerate(children):
        if child.get("initialized"):
            child_terminate(inst, node, idx)

    return SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_function_interface — outermost parallel dispatcher. Returns FUNCTION codes.
# ---------------------------------------------------------------------------

def se_function_interface(inst, node, event_id, event_data):
    children = node.get("children") or ()

    if event_id == EVENT_INIT:
        node["state"] = _FORK_STATE_RUNNING
        for idx in range(len(children)):
            child_reset(inst, node, idx)
        return SE_FUNCTION_CONTINUE

    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        node["state"] = _FORK_STATE_COMPLETE
        return SE_FUNCTION_CONTINUE

    if node["state"] != _FORK_STATE_RUNNING:
        return SE_FUNCTION_DISABLE

    active = 0
    for idx, child in enumerate(children):
        if not child.get("active", True):
            continue

        r = child_invoke(inst, node, idx, event_id, event_data)

        # Non-pipeline codes propagate up
        if r < SE_PIPELINE_CONTINUE:
            return r

        if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
            active += 1
        elif r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
            child_terminate(inst, node, idx)
        elif r == SE_PIPELINE_RESET:
            child_terminate(inst, node, idx)
            child_reset(inst, node, idx)
            active += 1
        elif r == SE_PIPELINE_SKIP_CONTINUE:
            active += 1
            break
        else:
            active += 1

    if active == 0:
        node["state"] = _FORK_STATE_COMPLETE
        return SE_FUNCTION_DISABLE
    return SE_FUNCTION_CONTINUE


# ---------------------------------------------------------------------------
# Shared fork helper — used by se_fork and se_fork_join for their child loop.
# Returns (early_return_code_or_None, skip_flag). If early_return is set,
# the operator must return that immediately.
# ---------------------------------------------------------------------------

def _fork_tick_children(inst, node, event_id, event_data):
    children = node.get("children") or ()
    skip = False

    for idx, child in enumerate(children):
        if skip:
            break
        ct = child["call_type"]
        if ct in ("o_call", "io_call"):
            if not child.get("initialized"):
                child_invoke(inst, node, idx, event_id, event_data)
            continue
        if ct == "p_call":
            if not child.get("initialized"):
                child_invoke(inst, node, idx, event_id, event_data)
                child["initialized"] = True  # pred normally has no lifecycle; track fired-once
            continue

        # m_call
        if not child.get("active", True):
            continue

        r = child_invoke(inst, node, idx, event_id, event_data)
        if r == SE_FUNCTION_HALT:
            r = SE_PIPELINE_HALT

        if r < SE_PIPELINE_CONTINUE:
            return r, skip

        if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
            pass
        elif r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
            child_terminate(inst, node, idx)
        elif r == SE_PIPELINE_RESET:
            child_terminate(inst, node, idx)
            child_reset_recursive(inst, node, idx)
        elif r == SE_PIPELINE_SKIP_CONTINUE:
            skip = True

    return None, skip


def _count_active_main(node):
    count = 0
    for child in node.get("children") or ():
        if child["call_type"] == "m_call" and child.get("active", True):
            count += 1
    return count


# ---------------------------------------------------------------------------
# se_fork — parallel; completes (PIPELINE_DISABLE) when all mains done.
# ---------------------------------------------------------------------------

def se_fork(inst, node, event_id, event_data):
    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        node["state"] = _FORK_STATE_COMPLETE
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_INIT:
        node["state"] = _FORK_STATE_RUNNING
        for idx in range(len(node.get("children") or ())):
            child_reset(inst, node, idx)
        return SE_PIPELINE_CONTINUE

    if node["state"] != _FORK_STATE_RUNNING:
        return SE_PIPELINE_DISABLE

    early, _ = _fork_tick_children(inst, node, event_id, event_data)
    if early is not None:
        return early

    if _count_active_main(node) == 0:
        node["state"] = _FORK_STATE_COMPLETE
        return SE_PIPELINE_DISABLE
    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_fork_join — parent-join; FUNCTION_HALT while mains running, DISABLE when done.
# ---------------------------------------------------------------------------

def se_fork_join(inst, node, event_id, event_data):
    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    if event_id == EVENT_INIT:
        return SE_PIPELINE_CONTINUE

    early, _ = _fork_tick_children(inst, node, event_id, event_data)
    if early is not None:
        return early

    if _count_active_main(node) == 0:
        return SE_PIPELINE_DISABLE
    return SE_FUNCTION_HALT


# ---------------------------------------------------------------------------
# se_chain_flow — tick every active child every event.
# ---------------------------------------------------------------------------

def se_chain_flow(inst, node, event_id, event_data):
    if event_id == EVENT_INIT:
        return SE_PIPELINE_CONTINUE
    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE

    children = node.get("children") or ()
    active = 0
    skip = False

    for idx, child in enumerate(children):
        if skip:
            break
        if not child.get("active", True):
            continue
        ct = child["call_type"]

        if ct in ("o_call", "io_call", "p_call"):
            child_invoke(inst, node, idx, event_id, event_data)
            child_terminate(inst, node, idx)
            continue

        # m_call
        r = child_invoke(inst, node, idx, event_id, event_data)

        if r == SE_FUNCTION_HALT:
            return SE_PIPELINE_HALT
        if r < SE_PIPELINE_CONTINUE:
            return r

        if r == SE_PIPELINE_CONTINUE:
            active += 1
        elif r == SE_PIPELINE_HALT:
            return SE_PIPELINE_CONTINUE
        elif r == SE_PIPELINE_DISABLE:
            child_terminate(inst, node, idx)
        elif r == SE_PIPELINE_TERMINATE:
            children_terminate_all(inst, node)
            return SE_PIPELINE_TERMINATE
        elif r == SE_PIPELINE_RESET:
            children_terminate_all(inst, node)
            children_reset_all(inst, node)
            return SE_PIPELINE_CONTINUE
        elif r == SE_PIPELINE_SKIP_CONTINUE:
            active += 1
            skip = True
        else:
            active += 1

    if active == 0:
        return SE_PIPELINE_DISABLE
    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_while — loop: children[0]=pred, children[1]=body.
# ---------------------------------------------------------------------------

def se_while(inst, node, event_id, event_data):
    if event_id == EVENT_TERMINATE:
        children = node.get("children") or ()
        if len(children) >= 2 and children[1].get("initialized"):
            child_terminate(inst, node, 1)
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_INIT:
        node["state"] = _WHILE_EVAL_PRED
        return SE_PIPELINE_CONTINUE

    if node["state"] == _WHILE_EVAL_PRED:
        if not child_invoke_pred(inst, node, 0):
            return SE_PIPELINE_DISABLE
        child_reset_recursive(inst, node, 1)
        node["state"] = _WHILE_RUN_BODY

    r = child_invoke(inst, node, 1, event_id, event_data)

    if r < SE_PIPELINE_CONTINUE:
        return r

    if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT, SE_PIPELINE_SKIP_CONTINUE):
        return SE_FUNCTION_HALT

    if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE, SE_PIPELINE_RESET):
        child_terminate(inst, node, 1)
        child_reset_recursive(inst, node, 1)
        node["state"] = _WHILE_EVAL_PRED
        return SE_PIPELINE_HALT

    return SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_if_then_else — children[0]=pred, [1]=then, [2]=else (optional).
# ---------------------------------------------------------------------------

def se_if_then_else(inst, node, event_id, event_data):
    children = node.get("children") or ()
    n = len(children)
    if n < 2:
        raise ValueError("se_if_then_else: need at least predicate and then branch")
    has_else = n >= 3

    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    if event_id == EVENT_INIT:
        return SE_PIPELINE_CONTINUE

    condition = child_invoke_pred(inst, node, 0)

    if condition:
        r = child_invoke(inst, node, 1, event_id, event_data)
    elif has_else:
        r = child_invoke(inst, node, 2, event_id, event_data)
    else:
        return SE_PIPELINE_CONTINUE

    if r < SE_PIPELINE_CONTINUE:
        return r

    if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
        return r

    if r == SE_PIPELINE_RESET:
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        if has_else:
            child_terminate(inst, node, 2)
            child_reset(inst, node, 2)
        return SE_PIPELINE_RESET

    if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        if has_else:
            child_terminate(inst, node, 2)
            child_reset(inst, node, 2)
        return SE_PIPELINE_CONTINUE

    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_cond — multi-branch (pred0, action0, pred1, action1, ..., [default]).
# params["has_else"]: bool — whether the last child is a default action.
# node["user_data"]: last active action child index (None = no active branch).
# ---------------------------------------------------------------------------

def se_cond(inst, node, event_id, event_data):
    children = node.get("children") or ()
    n = len(children)
    has_else = node["params"].get("has_else", False)

    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_INIT:
        node["user_data"] = None
        return SE_PIPELINE_CONTINUE

    # Walk pred/action pairs. If has_else, the last child is a trailing default action.
    num_pairs = (n - 1) // 2 if has_else else n // 2
    matched_action = None
    for pair_idx in range(num_pairs):
        pred_idx = pair_idx * 2
        if child_invoke_pred(inst, node, pred_idx):
            matched_action = pred_idx + 1
            break

    if matched_action is None and has_else:
        matched_action = n - 1

    if matched_action is None:
        return SE_PIPELINE_CONTINUE

    active = node.get("user_data")
    if matched_action != active:
        if active is not None:
            child_terminate(inst, node, active)
            child_reset_recursive(inst, node, active)
        child_terminate(inst, node, matched_action)
        child_reset_recursive(inst, node, matched_action)
        node["user_data"] = matched_action

    r = child_invoke(inst, node, matched_action, event_id, event_data)

    if r < SE_PIPELINE_CONTINUE:
        return r

    if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
        return SE_PIPELINE_CONTINUE

    if r == SE_PIPELINE_RESET:
        child_terminate(inst, node, matched_action)
        child_reset_recursive(inst, node, matched_action)
        return SE_PIPELINE_CONTINUE

    if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE, SE_PIPELINE_SKIP_CONTINUE):
        return r

    return SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# se_trigger_on_change — edge-triggered action dispatch.
# children[0]=pred, children[1]=rising, children[2]=falling (optional).
# params["initial"]: 0 or 1 — initial assumed state.
# node["state"]: last predicate value (0 or 1).
# ---------------------------------------------------------------------------

def _trigger_invoke_and_handle(inst, node, action_idx, event_id, event_data):
    r = child_invoke(inst, node, action_idx, event_id, event_data)

    if r < SE_PIPELINE_CONTINUE:
        return r
    if r in (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT):
        return SE_PIPELINE_CONTINUE
    if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE, SE_PIPELINE_RESET):
        child_terminate(inst, node, action_idx)
        child_reset(inst, node, action_idx)
        return SE_PIPELINE_CONTINUE
    return SE_PIPELINE_CONTINUE


def se_trigger_on_change(inst, node, event_id, event_data):
    children = node.get("children") or ()
    n = len(children)
    if n < 2:
        raise ValueError("se_trigger_on_change: need at least predicate and rising action")
    has_falling = n >= 3

    if event_id == EVENT_TERMINATE:
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE

    if event_id == EVENT_INIT:
        initial = node["params"].get("initial", 0)
        node["state"] = 1 if initial else 0
        return SE_PIPELINE_CONTINUE

    current = 1 if child_invoke_pred(inst, node, 0) else 0
    prev = node["state"]
    node["state"] = current

    rising = prev == 0 and current == 1
    falling = prev == 1 and current == 0

    if rising:
        if has_falling:
            child_terminate(inst, node, 2)
            child_reset(inst, node, 2)
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        return _trigger_invoke_and_handle(inst, node, 1, event_id, event_data)

    if falling and has_falling:
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        child_terminate(inst, node, 2)
        child_reset(inst, node, 2)
        return _trigger_invoke_and_handle(inst, node, 2, event_id, event_data)

    return SE_PIPELINE_CONTINUE
