"""Return codes and reserved event IDs.

Three concentric families of 6 codes each, matching the LuaJIT port exactly
(s_engine_types.h). Values are load-bearing: parent control functions dispatch
on family membership, and in-family variant identity.
"""

from __future__ import annotations

SE_CONTINUE = 0
SE_HALT = 1
SE_TERMINATE = 2
SE_RESET = 3
SE_DISABLE = 4
SE_SKIP_CONTINUE = 5

SE_FUNCTION_CONTINUE = 6
SE_FUNCTION_HALT = 7
SE_FUNCTION_TERMINATE = 8
SE_FUNCTION_RESET = 9
SE_FUNCTION_DISABLE = 10
SE_FUNCTION_SKIP_CONTINUE = 11

SE_PIPELINE_CONTINUE = 12
SE_PIPELINE_HALT = 13
SE_PIPELINE_TERMINATE = 14
SE_PIPELINE_RESET = 15
SE_PIPELINE_DISABLE = 16
SE_PIPELINE_SKIP_CONTINUE = 17

_APPLICATION_RANGE = range(0, 6)
_FUNCTION_RANGE = range(6, 12)
_PIPELINE_RANGE = range(12, 18)

_VARIANT_NAMES = (
    "CONTINUE",
    "HALT",
    "TERMINATE",
    "RESET",
    "DISABLE",
    "SKIP_CONTINUE",
)


def is_application(code: int) -> bool:
    return code in _APPLICATION_RANGE


def is_function(code: int) -> bool:
    return code in _FUNCTION_RANGE


def is_pipeline(code: int) -> bool:
    return code in _PIPELINE_RANGE


def variant(code: int) -> int:
    """Return the 0..5 position within the code's family."""
    return code % 6


def to_pipeline(code: int) -> int:
    return SE_PIPELINE_CONTINUE + variant(code)


def to_function(code: int) -> int:
    return SE_FUNCTION_CONTINUE + variant(code)


def to_application(code: int) -> int:
    return SE_CONTINUE + variant(code)


def code_name(code: int) -> str:
    if is_application(code):
        return "SE_" + _VARIANT_NAMES[variant(code)]
    if is_function(code):
        return "SE_FUNCTION_" + _VARIANT_NAMES[variant(code)]
    if is_pipeline(code):
        return "SE_PIPELINE_" + _VARIANT_NAMES[variant(code)]
    return f"SE_UNKNOWN({code})"


def is_complete(code: int) -> bool:
    """True when the outer tree has finished this tick.

    Application codes below CONTINUE never occur — CONTINUE is 0 — so the
    check is: pipeline/function DISABLE, pipeline/function TERMINATE, or
    any application code other than plain CONTINUE/HALT.
    """
    v = variant(code)
    return v in (2, 4)  # TERMINATE or DISABLE across any family


EVENT_INIT = "init"
EVENT_TICK = "tick"
EVENT_TERMINATE = "terminate"

_RESERVED_EVENT_IDS = frozenset({EVENT_INIT, EVENT_TICK, EVENT_TERMINATE})


def is_reserved_event(event_id: str) -> bool:
    return event_id in _RESERVED_EVENT_IDS
