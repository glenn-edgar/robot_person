"""Wall-clock time-of-day wait leaves (native CFL).

Two leaf operators that gate on whether the engine's wall clock currently
matches a configured local-time window. Both follow the standard wait-leaf
shape: HALT while the gate condition holds, DISABLE once it flips. To
re-arm, RESET the surrounding parent (composition via subtrees).

  CFL_WAIT_UNTIL_IN_TIME_WINDOW    — HALT while OUT of window, DISABLE on entry
  CFL_WAIT_UNTIL_OUT_OF_TIME_WINDOW — HALT while IN window, DISABLE on exit

Wall clock comes from `engine["get_wall_time"]()` (Linux 64-bit epoch
seconds), converted to local time via `engine["timezone"]` (None = system
local).

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

Canonical "fire once per window" composition:

    column:
      asm_wait_until_in_time_window(start, end)    # HALT until 09:00, DISABLE
      asm_one_shot("DO_THE_THING")                 # fires once
      asm_wait_until_out_of_time_window(start, end)# HALT until 17:00, DISABLE
                                                   # column drains → parent done
    # surround with a parent that RESETs the column to re-arm next day

  node["data"] = {"start": dict, "end": dict}
"""

from __future__ import annotations

from datetime import datetime

from ct_runtime.codes import CFL_DISABLE, CFL_HALT


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


def _in_window(handle, node) -> bool:
    data = node["data"]
    start = data["start"]
    end = data["end"]

    engine = handle["engine"]
    epoch_seconds = engine["get_wall_time"]()
    tz = engine.get("timezone")
    dt = datetime.fromtimestamp(epoch_seconds, tz=tz)

    return (
        _mask_field_ok(dt.hour,      start.get("hour"),   end.get("hour"),   "hour")
        and _mask_field_ok(dt.minute,    start.get("minute"), end.get("minute"), "minute")
        and _mask_field_ok(dt.second,    start.get("sec"),    end.get("sec"),    "sec")
        and _mask_field_ok(dt.weekday(), start.get("dow"),    end.get("dow"),    "dow")
        and _mask_field_ok(dt.day,       start.get("dom"),    end.get("dom"),    "dom")
    )


def cfl_wait_until_in_time_window(handle, _bool_fn_name, node, _event):
    """HALT while wall clock is OUT of the window; DISABLE on first tick IN."""
    if _in_window(handle, node):
        return CFL_DISABLE
    return CFL_HALT


def cfl_wait_until_out_of_time_window(handle, _bool_fn_name, node, _event):
    """HALT while wall clock is IN the window; DISABLE on first tick OUT.

    Idiomatic use: place after a one-shot action inside a column so the
    action fires once per window crossing. Re-arm by RESETting the parent.
    """
    if _in_window(handle, node):
        return CFL_HALT
    return CFL_DISABLE
