"""Wall-clock time-of-day operators.

Three public builtins, all sharing the same field-mask logic:

  m_call:
    se_wait_until_in_time_window     — HALT while OUT of window, DISABLE on entry
    se_wait_until_out_of_time_window — HALT while IN window, DISABLE on exit

  p_call:
    se_in_time_window                — predicate: True iff currently in window

The two wait leaves drop into `se_chain_flow` / `se_sequence` for wait-shaped
composition. The predicate plugs into `se_if_then_else`, `se_cond`,
`se_state_machine` transition guards, `se_trigger_on_change`, etc. Use
`pred_not(in_time_window(...))` for the "out" predicate variant.

Wall clock comes from `inst.module["get_wall_time"]()` (Linux 64-bit epoch
seconds), converted to local time via `inst.module["timezone"]` (None =
system local).

Window shape — uniform per-field masks across {hour, minute, sec, dow,
dom}. Each field is independent:
  - Both `start[f]` and `end[f]` present → field ∈ [start[f], end[f]]
    inclusive; wrap allowed when end[f] < start[f]
    (e.g. minute 50..10 means [50..59] ∪ [0..10]).
  - Both absent → field unconstrained.
  - Exactly one present → ValueError (paired-or-absent rule).

Final answer = logical AND of all five per-field checks. Field ranges:
  hour 0..23, minute 0..59, sec 0..59, dow 0..6 (0=Mon, datetime.weekday()),
  dom 1..31.

Examples:
  {hour:9}..{hour:17}               — business hours
  {hour:9, dow:0}..{hour:17, dow:4} — weekday business hours
  {minute:50}..{minute:10}          — wraps the hour
  {}..{}                            — unconstrained (always in)

  node["params"] = {"start": dict, "end": dict}  (no "key" — no dictionary write)
"""

from __future__ import annotations

from datetime import datetime

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
)


def _span_contains(current: int, start_v: int, end_v: int) -> bool:
    if start_v <= end_v:
        return start_v <= current <= end_v
    return current >= start_v or current <= end_v


def _mask_field_ok(current: int, start_v, end_v, field_name: str) -> bool:
    if start_v is None and end_v is None:
        return True
    if start_v is None or end_v is None:
        raise ValueError(
            f"time-window field {field_name!r} must be present in both "
            f"start and end, or neither"
        )
    return _span_contains(current, start_v, end_v)


def _in_window(inst, node) -> bool:
    params = node["params"]
    start = params["start"]
    end = params["end"]

    epoch_seconds = inst["module"]["get_wall_time"]()
    tz = inst["module"].get("timezone")
    dt = datetime.fromtimestamp(epoch_seconds, tz=tz)

    return (
        _mask_field_ok(dt.hour,      start.get("hour"),   end.get("hour"),   "hour")
        and _mask_field_ok(dt.minute,    start.get("minute"), end.get("minute"), "minute")
        and _mask_field_ok(dt.second,    start.get("sec"),    end.get("sec"),    "sec")
        and _mask_field_ok(dt.weekday(), start.get("dow"),    end.get("dow"),    "dow")
        and _mask_field_ok(dt.day,       start.get("dom"),    end.get("dom"),    "dom")
    )


# ---------------------------------------------------------------------------
# m_call wait leaves — HALT/DISABLE on window membership.
# ---------------------------------------------------------------------------

def se_wait_until_in_time_window(inst, node, event_id, event_data):
    """HALT while wall clock is OUT of the window; DISABLE on first tick IN.
    To re-arm, RESET the surrounding parent."""
    if event_id in (EVENT_INIT, EVENT_TERMINATE):
        return SE_PIPELINE_CONTINUE
    if _in_window(inst, node):
        return SE_PIPELINE_DISABLE
    return SE_PIPELINE_HALT


def se_wait_until_out_of_time_window(inst, node, event_id, event_data):
    """HALT while wall clock is IN the window; DISABLE on first tick OUT.

    Idiomatic use: place after a one-shot action inside a chain_flow/sequence
    so the action fires once per window crossing. Re-arm by RESETting the
    surrounding parent.
    """
    if event_id in (EVENT_INIT, EVENT_TERMINATE):
        return SE_PIPELINE_CONTINUE
    if _in_window(inst, node):
        return SE_PIPELINE_HALT
    return SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# p_call predicate — bool.
# ---------------------------------------------------------------------------

def se_in_time_window(inst, node) -> bool:
    """True iff the current local wall-clock time is in the configured window.
    Use `pred_not(in_time_window(...))` for the inverse."""
    return _in_window(inst, node)
