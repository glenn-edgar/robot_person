"""Transport ABC — pluggable bus for the chain_tree runtime.

The transport is the seam between the engine and whatever IPC mechanism
moves events between processes (or, in stage 2, between in-process
subscribers). Skills stay engine-agnostic; LEAVES emit events; the
engine's transport delivers them.

Two operations:

  emit(topic, payload)
      Publish one event. Topic is a UTF-8 string; payload is a JSON-
      serializable dict. Fire-and-forget: emit returns immediately,
      regardless of whether any subscriber received the event.

  subscribe(prefix, handler)
      Register a handler keyed on a TOPIC PREFIX. Handler receives
      `(topic, payload)`. Empty prefix = firehose. Matches ZeroMQ's
      byte-prefix subscription model so the same call site works for
      InProcessTransport (stage 2) and ZmqTransport (stage 3+).

Semantics deliberately mirror PUB/SUB: lossy, fire-and-forget, no
delivery guarantee, no ordering across publishers, deterministic
ordering across subscribers within one emit (insertion order).

Subscriber exceptions DO NOT propagate to the publisher — a buggy
subscriber must not be able to crash the publisher. Implementations
should catch and log; the publisher's emit() always returns cleanly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


# (topic, payload) -> None. Both args are by-reference; handlers should
# treat payload as read-only (don't mutate; copy first if needed).
EventHandler = Callable[[str, dict], None]


class Transport(ABC):
    """Pluggable PUB/SUB bus interface for the chain_tree runtime."""

    @abstractmethod
    def emit(self, topic: str, payload: dict) -> None:
        """Publish one event. Fire-and-forget; never raises."""

    @abstractmethod
    def subscribe(self, prefix: str, handler: EventHandler) -> None:
        """Register a handler for topics that start with `prefix`."""
