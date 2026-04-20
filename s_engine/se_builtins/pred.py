"""Predicate builtins (p_call).

Signature: fn(inst, node) -> bool. No lifecycle, no events. Composite
predicates invoke their p_call children through invoke_pred and short-circuit.

Field-read predicates were renamed to `dict_*` to match the Python port's
flat-dict state model (Option B in the naming discussion).
"""

from __future__ import annotations

from se_runtime.dispatch import invoke_pred


# ---------------------------------------------------------------------------
# Composite predicates
# ---------------------------------------------------------------------------

def pred_and(inst, node) -> bool:
    for child in node.get("children") or ():
        if not invoke_pred(inst, child):
            return False
    return True


def pred_or(inst, node) -> bool:
    for child in node.get("children") or ():
        if invoke_pred(inst, child):
            return True
    return False


def pred_not(inst, node) -> bool:
    children = node.get("children") or ()
    if len(children) != 1:
        raise ValueError(f"pred_not: requires exactly 1 child, got {len(children)}")
    return not invoke_pred(inst, children[0])


def pred_nor(inst, node) -> bool:
    return not pred_or(inst, node)


def pred_nand(inst, node) -> bool:
    return not pred_and(inst, node)


def pred_xor(inst, node) -> bool:
    """True iff an odd number of children are True. No short-circuit."""
    count = 0
    for child in node.get("children") or ():
        if invoke_pred(inst, child):
            count += 1
    return count % 2 == 1


# ---------------------------------------------------------------------------
# Constant predicates
# ---------------------------------------------------------------------------

def true_pred(inst, node) -> bool:
    return True


def false_pred(inst, node) -> bool:
    return False


# ---------------------------------------------------------------------------
# Event predicate
# ---------------------------------------------------------------------------

def check_event(inst, node) -> bool:
    """True if the engine's current event_id matches params['event_id']."""
    return inst["current_event_id"] == node["params"]["event_id"]


# ---------------------------------------------------------------------------
# Dictionary-comparison predicates
# ---------------------------------------------------------------------------

def _read_key(inst, node):
    return inst["module"]["dictionary"].get(node["params"]["key"])


def dict_eq(inst, node) -> bool:
    return _read_key(inst, node) == node["params"]["value"]


def dict_ne(inst, node) -> bool:
    return _read_key(inst, node) != node["params"]["value"]


def dict_gt(inst, node) -> bool:
    return _read_key(inst, node) > node["params"]["value"]


def dict_ge(inst, node) -> bool:
    return _read_key(inst, node) >= node["params"]["value"]


def dict_lt(inst, node) -> bool:
    return _read_key(inst, node) < node["params"]["value"]


def dict_le(inst, node) -> bool:
    return _read_key(inst, node) <= node["params"]["value"]


def dict_in_range(inst, node) -> bool:
    """True if params['min'] <= dictionary[params['key']] <= params['max']."""
    v = _read_key(inst, node)
    return node["params"]["min"] <= v <= node["params"]["max"]


# ---------------------------------------------------------------------------
# Counter predicates (mutate state as a side effect)
# ---------------------------------------------------------------------------

def dict_inc_and_test(inst, node) -> bool:
    """Increment dictionary[key] by 1, return True when it reaches threshold."""
    d = inst["module"]["dictionary"]
    key = node["params"]["key"]
    threshold = node["params"]["threshold"]
    new_val = (d.get(key) or 0) + 1
    d[key] = new_val
    return new_val >= threshold


def state_inc_and_test(inst, node) -> bool:
    """Increment the node's own `state`, return True when it reaches threshold."""
    node["state"] = (node.get("state") or 0) + 1
    return node["state"] >= node["params"]["threshold"]
