"""Node construction helpers.

A CFL node is a plain Python dict. This module centralizes the shape so
builders, the walker, and the engine all agree on keys.

Minimum shape (matches continue.md "Per-node state" + walker needs):

    {
        "name":            str,                  # debug label; no uniqueness requirement
        "parent":          <node dict or None>,
        "children":        list[<node dict>],    # structural order; enabled filter applied at walk time
        "main_fn_name":    str or None,          # CFL-side main, required for non-leaf scaffolding
        "boolean_fn_name": str or None,          # aux / boolean fn, passed to main fn
        "init_fn_name":    str or None,          # optional init one-shot
        "term_fn_name":    str or None,          # optional term one-shot
        "ct_control": {
            "enabled":     bool,
            "initialized": bool,
            # feature-specific fields added by each node type's builtin
        },
        "data": dict,                            # user-facing; DSL config + per-node scratch
    }

`node["ct_control"]` is engine-managed; user fns treat it as read-only.
`node["data"]` is freely writable by the node's own fns.
"""

from __future__ import annotations

from typing import Iterable, List, Optional


def make_node(
    name: str = "",
    main_fn_name: Optional[str] = None,
    boolean_fn_name: Optional[str] = None,
    init_fn_name: Optional[str] = None,
    term_fn_name: Optional[str] = None,
    data: Optional[dict] = None,
    children: Optional[Iterable[dict]] = None,
) -> dict:
    """Construct a node dict. Parent and enabled state default unset/false;
    callers that build trees must link parents explicitly via link_children.
    """
    node = {
        "name": name,
        "parent": None,
        "children": [],
        "main_fn_name": main_fn_name,
        "boolean_fn_name": boolean_fn_name,
        "init_fn_name": init_fn_name,
        "term_fn_name": term_fn_name,
        "ct_control": {"enabled": False, "initialized": False},
        "data": dict(data) if data else {},
    }
    if children:
        link_children(node, children)
    return node


def link_children(parent: dict, children: Iterable[dict]) -> None:
    """Attach children to a parent, setting each child's parent back-pointer."""
    for c in children:
        c["parent"] = parent
        parent["children"].append(c)


def enabled_children(node: dict) -> List[dict]:
    """Currently-enabled child list, in declaration order.

    This is the canonical get_forward_enabled_links(node) callback the walker
    uses. Feature-specific node types (state machine, exception catch) that
    need non-ordered or overlay link semantics provide their own variant.
    """
    return [c for c in node["children"] if c["ct_control"]["enabled"]]


def is_leaf(node: dict) -> bool:
    return not node["children"]


def walk_ancestors(node: dict) -> Iterable[dict]:
    """Yield parents from immediate-parent upward. Root is yielded last."""
    cur = node["parent"]
    while cur is not None:
        yield cur
        cur = cur["parent"]
