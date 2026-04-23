"""Module construction and loading.

A module is the unit of deployment. It holds:
  - dictionary: mutable shared state (flat dict[str, Any])
  - constants:  immutable shared state (MappingProxyType)
  - trees:      dict[str, tree_root_node]
  - fn_registry: name -> callable, for deserialized trees
  - get_time:   callable returning monotonic ns
  - get_wall_time: callable returning Linux 64-bit epoch seconds (wall clock)
  - timezone:   tzinfo for local-time conversions (None = system local)
  - crash_callback: optional display/logging hook
  - logger:     callable for oneshot logging (defaults to print)
"""

from __future__ import annotations

import time
from datetime import tzinfo
from types import MappingProxyType
from typing import Any, Callable, Mapping, MutableMapping, Optional


def _default_get_time() -> int:
    return time.monotonic_ns()


def _default_get_wall_time() -> int:
    return int(time.time())


def new_module(
    dictionary: Optional[MutableMapping[str, Any]] = None,
    constants: Optional[Mapping[str, Any]] = None,
    trees: Optional[MutableMapping[str, dict]] = None,
    fn_registry: Optional[Mapping[str, Callable]] = None,
    get_time: Optional[Callable[[], int]] = None,
    get_wall_time: Optional[Callable[[], int]] = None,
    timezone: Optional[tzinfo] = None,
    crash_callback: Optional[Callable] = None,
    logger: Optional[Callable[[str], None]] = None,
    event_queue_limit: Optional[int] = None,
) -> dict:
    """Build a module from explicit parts (dynamic workflow)."""
    dictionary = dict(dictionary) if dictionary else {}
    constants_dict = dict(constants) if constants else {}
    _check_no_key_collision(dictionary, constants_dict)
    return {
        "dictionary": dictionary,
        "constants": MappingProxyType(constants_dict),
        "trees": dict(trees) if trees else {},
        "fn_registry": dict(fn_registry) if fn_registry else {},
        "get_time": get_time or _default_get_time,
        "get_wall_time": get_wall_time or _default_get_wall_time,
        "timezone": timezone,
        "crash_callback": crash_callback,
        "logger": logger or print,
        "event_queue_limit": event_queue_limit,
    }


def load_module(module_dict: Mapping[str, Any]) -> dict:
    """Load a pre-built module dict (static-emission workflow).

    Accepts the shape produced by emit_module_file(). Wraps constants in
    MappingProxyType, validates key collisions, defaults get_time if missing,
    and normalizes each tree by filling in any missing dispatch-managed
    fields (active, initialized, ever_init, state, user_data).
    """
    dictionary = dict(module_dict.get("dictionary") or {})
    constants_src = module_dict.get("constants") or {}
    constants_dict = dict(constants_src)
    _check_no_key_collision(dictionary, constants_dict)

    raw_trees = module_dict.get("trees") or {}
    trees = {name: _normalize_tree(tree) for name, tree in raw_trees.items()}

    return {
        "dictionary": dictionary,
        "constants": MappingProxyType(constants_dict),
        "trees": trees,
        "fn_registry": dict(module_dict.get("fn_registry") or {}),
        "get_time": module_dict.get("get_time") or _default_get_time,
        "get_wall_time": module_dict.get("get_wall_time") or _default_get_wall_time,
        "timezone": module_dict.get("timezone"),
        "crash_callback": module_dict.get("crash_callback"),
        "logger": module_dict.get("logger") or print,
        "event_queue_limit": module_dict.get("event_queue_limit"),
    }


def _normalize_tree(node: Any) -> dict:
    """Fill in missing dispatch-managed fields on a tree loaded from source."""
    if not isinstance(node, Mapping):
        raise TypeError(f"load_module: tree node is not a dict: {node!r}")
    normalized = dict(node)
    normalized.setdefault("params", {})
    normalized.setdefault("children", [])
    normalized["active"] = node.get("active", True)
    normalized["initialized"] = node.get("initialized", False)
    normalized["ever_init"] = node.get("ever_init", False)
    normalized["state"] = node.get("state", 0)
    normalized["user_data"] = node.get("user_data", None)
    normalized["children"] = [_normalize_tree(c) for c in normalized["children"]]
    return normalized


def register_tree(module: dict, name: str, tree: dict) -> None:
    """Register a tree under a name in the module."""
    module["trees"][name] = tree


def _check_no_key_collision(
    dictionary: Mapping[str, Any], constants: Mapping[str, Any]
) -> None:
    overlap = set(dictionary) & set(constants)
    if overlap:
        sample = ", ".join(sorted(overlap)[:5])
        raise ValueError(
            f"module: dictionary and constants share keys: {sample}"
        )
