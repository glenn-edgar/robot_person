"""CFL return codes, walker signals, and reserved event strings.

All identifiers match the LuaJIT reference port (cfl_types.h / cfl_runtime.lua)
so behavior translates 1:1. Codes are represented as short string constants —
not ints — because the spec's user-facing main fn signature returns a string
("CFL_CONTINUE", etc.) and because dispatch never takes the numeric fast path
that the LuaJIT port needed for embedded-C reasons.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# CFL return codes (emitted by main fns; consumed by execute_node)
# ---------------------------------------------------------------------------

CFL_CONTINUE = "CFL_CONTINUE"
CFL_HALT = "CFL_HALT"
CFL_TERMINATE = "CFL_TERMINATE"
CFL_RESET = "CFL_RESET"
CFL_DISABLE = "CFL_DISABLE"
CFL_SKIP_CONTINUE = "CFL_SKIP_CONTINUE"
CFL_TERMINATE_SYSTEM = "CFL_TERMINATE_SYSTEM"

_VALID_CFL_CODES = frozenset({
    CFL_CONTINUE,
    CFL_HALT,
    CFL_TERMINATE,
    CFL_RESET,
    CFL_DISABLE,
    CFL_SKIP_CONTINUE,
    CFL_TERMINATE_SYSTEM,
})


def is_valid_cfl_code(code: str) -> bool:
    return code in _VALID_CFL_CODES


# ---------------------------------------------------------------------------
# Walker signals (emitted by execute_node; consumed by the DFS walker)
# ---------------------------------------------------------------------------

CT_CONTINUE = "CT_CONTINUE"            # descend into enabled children
CT_SKIP_CHILDREN = "CT_SKIP_CHILDREN"  # do not descend; continue with siblings
CT_STOP_SIBLINGS = "CT_STOP_SIBLINGS"  # stop iterating siblings at this level
CT_STOP_ALL = "CT_STOP_ALL"            # unwind entirely; abort the walk


# ---------------------------------------------------------------------------
# Event type tags (the `event_type` field on the event dict)
# ---------------------------------------------------------------------------

CFL_EVENT_TYPE_NULL = "CFL_EVENT_TYPE_NULL"
CFL_EVENT_TYPE_PTR = "CFL_EVENT_TYPE_PTR"
CFL_EVENT_TYPE_NODE_ID = "CFL_EVENT_TYPE_NODE_ID"
CFL_EVENT_TYPE_STREAMING_DATA = "CFL_EVENT_TYPE_STREAMING_DATA"


# ---------------------------------------------------------------------------
# Reserved event ids (the `event_id` field on the event dict)
# ---------------------------------------------------------------------------

CFL_TIMER_EVENT = "CFL_TIMER_EVENT"
CFL_SECOND_EVENT = "CFL_SECOND_EVENT"
CFL_MINUTE_EVENT = "CFL_MINUTE_EVENT"
CFL_HOUR_EVENT = "CFL_HOUR_EVENT"
CFL_TERMINATE_EVENT = "CFL_TERMINATE_EVENT"
CFL_TERMINATE_SYSTEM_EVENT = "CFL_TERMINATE_SYSTEM_EVENT"
CFL_RAISE_EXCEPTION_EVENT = "CFL_RAISE_EXCEPTION_EVENT"
CFL_CHANGE_STATE_EVENT = "CFL_CHANGE_STATE_EVENT"
CFL_RESET_STATE_MACHINE_EVENT = "CFL_RESET_STATE_MACHINE_EVENT"
CFL_TERMINATE_STATE_MACHINE_EVENT = "CFL_TERMINATE_STATE_MACHINE_EVENT"
CFL_TURN_HEARTBEAT_ON_EVENT = "CFL_TURN_HEARTBEAT_ON_EVENT"
CFL_TURN_HEARTBEAT_OFF_EVENT = "CFL_TURN_HEARTBEAT_OFF_EVENT"
CFL_HEARTBEAT_EVENT = "CFL_HEARTBEAT_EVENT"
CFL_SET_EXCEPTION_STEP_EVENT = "CFL_SET_EXCEPTION_STEP_EVENT"


# ---------------------------------------------------------------------------
# Priorities
# ---------------------------------------------------------------------------

PRIORITY_HIGH = "high"
PRIORITY_NORMAL = "normal"


# ---------------------------------------------------------------------------
# CFL code → walker signal
# ---------------------------------------------------------------------------
#
# Matches the table in continue.md "Return code → walker signal mapping".
# The side effect on the engine (terminate_node_tree etc.) is NOT encoded
# here — it lives in engine.execute_node so it can touch engine state.

_CODE_TO_SIGNAL = {
    CFL_CONTINUE: CT_CONTINUE,
    CFL_HALT: CT_STOP_SIBLINGS,
    CFL_SKIP_CONTINUE: CT_SKIP_CHILDREN,
    CFL_DISABLE: CT_SKIP_CHILDREN,
    CFL_RESET: CT_CONTINUE,
    # CFL_TERMINATE and CFL_TERMINATE_SYSTEM are context-dependent; resolved
    # in engine.execute_node.
}


def code_to_signal(code: str) -> str:
    """Map a (non-context-dependent) CFL code to a walker signal."""
    try:
        return _CODE_TO_SIGNAL[code]
    except KeyError as exc:
        raise ValueError(
            f"code_to_signal: code {code!r} is context-dependent or invalid; "
            "resolve in execute_node"
        ) from exc
