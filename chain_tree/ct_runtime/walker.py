"""Iterative DFS walker over a CFL node tree.

Visits a start node and descends into its children pre-order. Enabled-only
filtering is the responsibility of the caller-supplied `get_children`
callback (default: `node.enabled_children`). `visit(node, event, level)`
returns one of the CT_* signals from `codes`, which steer the walk:

    CT_CONTINUE         descend into this node's children, then next sibling
    CT_SKIP_CHILDREN    do NOT descend; go to next sibling
    CT_STOP_SIBLINGS    skip children AND remaining siblings at this level
    CT_STOP_ALL         unwind entirely; abort the walk

The walker is purely mechanical — it holds no engine state and does not
interpret CFL return codes. `execute_node` is where CFL codes are translated
to walker signals and side effects (terminate_node_tree, enable_node) run.
"""

from __future__ import annotations

from typing import Any, Callable, List

from .codes import (
    CT_CONTINUE,
    CT_SKIP_CHILDREN,
    CT_STOP_ALL,
    CT_STOP_SIBLINGS,
)
from .node import enabled_children


VisitFn = Callable[[dict, Any, int], str]
ChildrenFn = Callable[[dict], List[dict]]


def walk(
    start: dict,
    event: Any,
    visit: VisitFn,
    get_children: ChildrenFn = enabled_children,
) -> None:
    """Walk the subtree rooted at `start` in pre-order DFS.

    `visit` is called once per visited node. Returns normally when the walk
    is complete (either naturally, or because `visit` signaled CT_STOP_ALL).
    """
    sig = visit(start, event, 0)
    if sig in (CT_STOP_ALL, CT_STOP_SIBLINGS, CT_SKIP_CHILDREN):
        return
    if sig != CT_CONTINUE:
        raise ValueError(f"walker: unknown signal {sig!r} from visit({start!r})")

    # Stack of iterators over each level's enabled-children list.
    stack = [iter(get_children(start))]
    while stack:
        try:
            node = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue

        level = len(stack)
        sig = visit(node, event, level)
        if sig == CT_STOP_ALL:
            return
        if sig == CT_STOP_SIBLINGS:
            # Drop this level's iterator — remaining siblings are skipped.
            stack.pop()
            continue
        if sig == CT_SKIP_CHILDREN:
            continue
        if sig == CT_CONTINUE:
            stack.append(iter(get_children(node)))
            continue
        raise ValueError(f"walker: unknown signal {sig!r} from visit({node!r})")
