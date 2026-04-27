"""Dual-priority FIFO queue pair for the CFL engine.

One shared pair per engine handle (not per-KB). Semantics from continue.md:

- Two queues: high, normal.
- Pop order: high drained before normal. pop() returns the oldest high-priority
  event if any exist, otherwise the oldest normal-priority event.
- Events enqueued during event handlers are processed in the same drain phase
  (before the next wall-clock sleep).

Events themselves are plain dicts with the shape documented in continue.md:

    {
        "target":     <node dict>,
        "event_type": <str>,
        "event_id":   <str>,
        "data":       <Any>,
        "priority":   "high" | "normal",
    }
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

from .codes import PRIORITY_HIGH, PRIORITY_NORMAL


def new_event_queue() -> dict:
    return {
        "high": deque(),
        "normal": deque(),
    }


def enqueue(queue: dict, event: dict) -> None:
    """Push an event onto its priority queue.

    The event's 'priority' field decides which queue it lands in; missing or
    unrecognized priorities are treated as normal.
    """
    if event.get("priority") == PRIORITY_HIGH:
        queue["high"].append(event)
    else:
        event["priority"] = PRIORITY_NORMAL
        queue["normal"].append(event)


def pop(queue: dict) -> Optional[dict]:
    """Return and remove the next event, or None if both queues are empty."""
    if queue["high"]:
        return queue["high"].popleft()
    if queue["normal"]:
        return queue["normal"].popleft()
    return None


def nonempty(queue: dict) -> bool:
    return bool(queue["high"]) or bool(queue["normal"])


def clear(queue: dict) -> None:
    queue["high"].clear()
    queue["normal"].clear()


def make_event(
    target: Any,
    event_type: str,
    event_id: str,
    data: Any = None,
    priority: str = PRIORITY_NORMAL,
) -> dict:
    """Construct a well-formed event dict."""
    return {
        "target": target,
        "event_type": event_type,
        "event_id": event_id,
        "data": data,
        "priority": priority,
    }
