"""Tick entry points.

The engine processes one event at a time to completion — no preemption. When
the outer fn returns, the engine pulls the next event. The caller owns the
pump: `tick_once` runs a single event; `run_until_idle` drains the queue.

Exceptions from any fn are hard crashes. If `module["crash_callback"]` is set,
it is called with full context (inst, node, event_id, event_data, exception,
traceback string), then the exception is re-raised. The crash callback is for
display/logging only; it cannot suppress or alter control flow.
"""

from __future__ import annotations

import traceback
from typing import Any, Mapping, Optional

from se_runtime.codes import (
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_TERMINATE,
    is_complete as _code_is_complete,
)
from se_runtime.dispatch import invoke_any
from se_runtime.instance import pop_event, queue_empty


def tick_once(
    inst: dict,
    event_id: str = EVENT_TICK,
    event_data: Optional[Mapping[str, Any]] = None,
) -> int:
    """Run the outer tree's root for one event; returns its result code."""
    root = inst["root"]
    if not root.get("active", True):
        return SE_PIPELINE_TERMINATE

    data = dict(event_data) if event_data else {}
    try:
        return invoke_any(inst, root, event_id, data)
    except Exception as exc:
        _report_crash(inst, root, event_id, data, exc)
        raise


def run_until_idle(inst: dict) -> Optional[int]:
    """Drain both queues. Returns the last result code, or None if nothing ran."""
    last_result: Optional[int] = None
    while not queue_empty(inst):
        event = pop_event(inst)
        if event is None:
            break
        event_id, event_data = event
        last_result = tick_once(inst, event_id, event_data)
        if last_result == SE_PIPELINE_DISABLE or last_result == SE_PIPELINE_TERMINATE:
            # Tree completed; stop draining. Caller decides whether to reset or discard.
            break
    return last_result


def is_complete(code: Optional[int]) -> bool:
    """True if the code indicates the outer tree finished this tick."""
    if code is None:
        return False
    return _code_is_complete(code)


def _report_crash(
    inst: dict,
    node: dict,
    event_id: str,
    event_data: Mapping[str, Any],
    exc: BaseException,
) -> None:
    callback = inst["module"].get("crash_callback")
    if callback is None:
        return
    tb = traceback.format_exc()
    try:
        callback(inst, node, event_id, event_data, exc, tb)
    except Exception:  # noqa: BLE001 — crash callback failure must not mask original
        pass
