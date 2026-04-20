"""Instance construction and event-queue ops.

An instance binds one tree to a module. It carries the node-graph root (whose
per-node state lives inline on each dict), two event queues (high and normal
priority), and the current event context during a tick.

Constructing an instance does NOT eagerly walk the tree to initialize nodes;
init is lazy and fires when dispatch first reaches each node.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Mapping, Optional


def new_instance(module: dict, tree_name: str) -> dict:
    """Create an instance from a tree registered under `tree_name`."""
    tree = module["trees"].get(tree_name)
    if tree is None:
        raise KeyError(f"new_instance: unknown tree: {tree_name!r}")
    return new_instance_from_tree(module, tree)


def new_instance_from_tree(module: dict, tree: dict) -> dict:
    """Create an instance from a tree dict directly (no registration step)."""
    return {
        "module": module,
        "root": tree,
        "high_queue": deque(),
        "normal_queue": deque(),
        "current_event_id": None,
        "current_event_data": None,
    }


def push_event(
    inst: dict,
    event_id: str,
    event_data: Optional[Mapping[str, Any]] = None,
    priority: str = "normal",
) -> None:
    """Push an event onto the high or normal queue."""
    if priority not in ("high", "normal"):
        raise ValueError(f"push_event: priority must be 'high' or 'normal', got {priority!r}")
    data = dict(event_data) if event_data else {}
    limit = inst["module"].get("event_queue_limit")
    if limit is not None and _queue_size(inst) >= limit:
        raise OverflowError(f"event queue limit reached: {limit}")
    queue = inst["high_queue"] if priority == "high" else inst["normal_queue"]
    queue.append((event_id, data))


def pop_event(inst: dict) -> Optional[tuple[str, dict]]:
    """Pop the next event — high drained first, then normal. Returns None if empty."""
    if inst["high_queue"]:
        return inst["high_queue"].popleft()
    if inst["normal_queue"]:
        return inst["normal_queue"].popleft()
    return None


def queue_empty(inst: dict) -> bool:
    return not inst["high_queue"] and not inst["normal_queue"]


def _queue_size(inst: dict) -> int:
    return len(inst["high_queue"]) + len(inst["normal_queue"])
