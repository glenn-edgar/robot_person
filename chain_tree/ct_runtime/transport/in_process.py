"""InProcessTransport — stage-2 stub. No sockets. No ports. No threads.

Used by stage-2 deterministic tests (P0.4) and by the daily_report
runner before any bus work lands. Same call sites work unchanged when
the runtime swaps in ZmqTransport at stage 3+.

Implementation notes:

- Subscriber list is a plain list of `(prefix, handler)` tuples. Emit
  walks the list synchronously and calls every handler whose prefix
  matches `topic.startswith(prefix)`.
- Order of dispatch is subscription order (deterministic for tests).
  ZMQ doesn't promise cross-subscriber ordering; tests that assume
  it should not be ported to stage-3 unchanged.
- Handler exceptions are caught and logged. Matches the PUB/SUB
  contract that a buggy subscriber doesn't crash the publisher.
- Single-threaded. Stage-2 tests run in the test thread; nothing
  here protects against concurrent subscribe/emit. If an in-process
  multi-threaded use case ever appears, add a lock then — not now.
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import EventHandler, Transport


class InProcessTransport(Transport):
    """Synchronous in-memory PUB/SUB. Stage-2 stub."""

    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        self._subs: list[tuple[str, EventHandler]] = []
        self._logger = logger or (lambda msg: None)

    def emit(self, topic: str, payload: dict) -> None:
        for prefix, handler in list(self._subs):
            if topic.startswith(prefix):
                try:
                    handler(topic, payload)
                except BaseException as exc:  # noqa: BLE001 - PUB/SUB lossy
                    self._logger(
                        f"transport: handler raised on topic={topic!r}: "
                        f"{type(exc).__name__}: {exc}"
                    )

    def subscribe(self, prefix: str, handler: EventHandler) -> None:
        self._subs.append((prefix, handler))
