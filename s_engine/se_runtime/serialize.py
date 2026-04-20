"""Tree serialization and deserialization for network transport.

Wire shape is JSON-compatible:
  {
    "fn":        "<function_name>",         # string, looked up via fn_registry
    "call_type": "m_call" | "o_call" | "io_call" | "p_call",
    "params":    {...},                      # dispatch-managed values
    "children":  [... recursive ...],
  }

Only the tree *shape* is serialized — dispatch-managed fields (active,
initialized, ever_init, state, user_data, deadline) are NOT written and
are re-initialized to defaults on deserialize. Wire transport is for
plan templates, not live instance snapshots.

### Tuple keys in params

Some operator params (notably `state_machine.transitions`) use tuple keys
like `("idle", "start")`. JSON doesn't allow non-string dict keys, so
tuple-keyed dicts are encoded as a tagged form:

    {"__tuple_keyed__": [[["idle", "start"], "running"], ...]}

And restored on deserialize. This is the only non-obvious part of the
wire format.

### Trust boundary

`deserialize_tree(wire, fn_registry)` only accepts fn names that are keys
of `fn_registry`. A tree referencing an unregistered name raises
`KeyError`. This is the security boundary — the wire form is data only,
never code, so arbitrary code execution is not possible.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping


_TUPLE_KEY_MARKER = "__tuple_keyed__"


# ---------------------------------------------------------------------------
# Serialize
# ---------------------------------------------------------------------------

def serialize_tree(node: Mapping[str, Any]) -> dict:
    """Walk a tree dict, return a JSON-safe shape-only representation."""
    fn = node["fn"]
    if not callable(fn):
        raise TypeError(f"serialize_tree: node['fn'] is not callable: {fn!r}")
    if not hasattr(fn, "__name__"):
        raise TypeError(f"serialize_tree: node['fn'] has no __name__: {fn!r}")
    return {
        "fn": fn.__name__,
        "call_type": node["call_type"],
        "params": _serialize_value(node.get("params") or {}),
        "children": [serialize_tree(c) for c in (node.get("children") or ())],
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, dict):
        if any(isinstance(k, tuple) for k in value):
            entries = [
                [list(k), _serialize_value(v)]
                for k, v in value.items()
            ]
            return {_TUPLE_KEY_MARKER: entries}
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_serialize_value(x) for x in value]
    if isinstance(value, list):
        return [_serialize_value(x) for x in value]
    if callable(value) and hasattr(value, "__name__"):
        # Embedded user callables in params aren't supported for wire transport —
        # they would have to go through the fn_registry too. Keeping it strict.
        raise TypeError(
            f"serialize_tree: callable {value.__name__!r} in params is not serializable; "
            "pass a name string and resolve it inside the fn body, or pre-resolve."
        )
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(
        f"serialize_tree: unsupported value type {type(value).__name__} in params"
    )


# ---------------------------------------------------------------------------
# Deserialize
# ---------------------------------------------------------------------------

def deserialize_tree(
    wire: Mapping[str, Any],
    fn_registry: Mapping[str, Callable],
) -> dict:
    """Reconstruct a tree dict from wire form. Unknown fn names raise KeyError.

    The resulting tree has all dispatch-managed fields at their defaults:
    active=True, initialized=False, ever_init=False, state=0, user_data=None.
    """
    fn_name = wire["fn"]
    fn = fn_registry.get(fn_name)
    if fn is None:
        raise KeyError(
            f"deserialize_tree: fn {fn_name!r} not in registry "
            f"(known: {sorted(fn_registry)[:5]}...)"
        )
    return {
        "fn": fn,
        "call_type": wire["call_type"],
        "params": _deserialize_value(wire.get("params") or {}),
        "children": [deserialize_tree(c, fn_registry) for c in (wire.get("children") or ())],
        "active": True,
        "initialized": False,
        "ever_init": False,
        "state": 0,
        "user_data": None,
    }


def _deserialize_value(value: Any) -> Any:
    if isinstance(value, dict):
        if _TUPLE_KEY_MARKER in value:
            return {
                tuple(k): _deserialize_value(v)
                for k, v in value[_TUPLE_KEY_MARKER]
            }
        return {k: _deserialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deserialize_value(x) for x in value]
    return value
