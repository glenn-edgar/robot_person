"""bb — leaf-level conveniences for reaching the engine transport via a kb.

The blackboard itself stays a plain Python dict (per the namespace rule
in DESIGN.md / feedback_blackboard_namespace memory). Cross-process
event traffic does NOT live on the blackboard; it lives on the engine's
transport. These helpers are the documented, supported way for a leaf
to publish or subscribe — leaves should not poke `kb["engine"]["transport"]`
directly, since the lookup path is internal layout that may shift.

Stage-2 default transport is `InProcessTransport` (synchronous, in-
memory). Stage-3+ will be `ZmqTransport`. Same call sites; leaves don't
care which.
"""

from __future__ import annotations

from .transport import EventHandler


def bb_emit(kb: dict, topic: str, payload: dict) -> None:
    """Publish one event on the engine transport bound to this KB."""
    kb["engine"]["transport"].emit(topic, payload)


def bb_subscribe(kb: dict, prefix: str, handler: EventHandler) -> None:
    """Register a handler for events whose topic starts with `prefix`."""
    kb["engine"]["transport"].subscribe(prefix, handler)
