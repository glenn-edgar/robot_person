"""Core dispatch.

`invoke_any` is the one function control operators call on their children. It
routes by `call_type`:

  - m_call   → full INIT/event/TERMINATE lifecycle, three-family return code
  - o_call   → fire-once-per-activation oneshot (initialized flag)
  - io_call  → fire-once-per-instance oneshot (ever_init flag)
  - p_call   → pure bool predicate; True → PIPELINE_CONTINUE, False → PIPELINE_HALT

Inactive nodes are transparent — any invocation returns PIPELINE_CONTINUE
without calling the fn.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
)


def invoke_any(
    inst: dict,
    node: dict,
    event_id: str,
    event_data: Optional[Mapping[str, Any]] = None,
) -> int:
    call_type = node["call_type"]
    if call_type == "m_call":
        return invoke_main(inst, node, event_id, event_data)
    if call_type == "o_call":
        invoke_oneshot(inst, node)
        return SE_PIPELINE_CONTINUE
    if call_type == "io_call":
        invoke_oneshot(inst, node)
        return SE_PIPELINE_CONTINUE
    if call_type == "p_call":
        return SE_PIPELINE_CONTINUE if invoke_pred(inst, node) else SE_PIPELINE_HALT
    raise ValueError(f"invoke_any: unknown call_type: {call_type!r}")


def invoke_main(
    inst: dict,
    node: dict,
    event_id: str,
    event_data: Optional[Mapping[str, Any]] = None,
) -> int:
    """Full lifecycle: lazy INIT then the event. TERMINATE fires on PIPELINE_DISABLE."""
    if not node.get("active", True):
        return SE_PIPELINE_CONTINUE

    fn = node["fn"]

    data = event_data if event_data is not None else {}

    if not node.get("initialized", False):
        node["initialized"] = True
        node["ever_init"] = True
        inst["current_event_id"] = EVENT_INIT
        inst["current_event_data"] = data
        fn(inst, node, EVENT_INIT, data)

    inst["current_event_id"] = event_id
    inst["current_event_data"] = data
    result = fn(inst, node, event_id, data)
    if result is None:
        result = SE_PIPELINE_CONTINUE

    if result == SE_PIPELINE_DISABLE:
        inst["current_event_id"] = EVENT_TERMINATE
        inst["current_event_data"] = {}
        fn(inst, node, EVENT_TERMINATE, {})
        # Clear dispatch-managed state so a subsequent parent-level
        # child_terminate is a no-op (no double-fire of TERMINATE).
        node["active"] = False
        node["initialized"] = False
        node["state"] = 0
        node["user_data"] = None

    return result


def invoke_oneshot(inst: dict, node: dict) -> None:
    """Fire-once semantics; o_call uses `initialized`, io_call uses `ever_init`."""
    survives = node["call_type"] == "io_call"
    flag_key = "ever_init" if survives else "initialized"
    if node.get(flag_key, False):
        return
    node[flag_key] = True
    if survives:
        node["initialized"] = True
    node["fn"](inst, node)


def invoke_pred(inst: dict, node: dict) -> bool:
    """Pure bool — strict True/False to avoid int/bool confusion with return codes."""
    return bool(node["fn"](inst, node))
