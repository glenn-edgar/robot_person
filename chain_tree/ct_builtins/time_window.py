"""Wall-clock time-of-day window operator (native CFL).

Mirrors s_engine's `se_time_window_check` so the same window shape works
on both sides of the bridge. Reads the wall clock from
`engine["get_wall_time"]()` (Linux 64-bit epoch seconds), converts to local
time using `engine["timezone"]` (None = system local), and writes a bool
to `kb["blackboard"][key]` indicating whether the current local time
matches the configured window.

Window shape — uniform per-field masks across {hour, minute, sec, dow,
dom}. Each field is independent:

  - Both `start[f]` and `end[f]` present → field is constrained to
    [start[f], end[f]] inclusive, with wrap allowed when end[f] < start[f]
    (e.g. minute 50..10 means [50..59] ∪ [0..10]).
  - Both absent → field unconstrained.
  - Exactly one present → ValueError (paired-or-absent rule).

Final answer = logical AND of all five per-field checks. Field ranges:
  hour 0..23, minute 0..59, sec 0..59, dow 0..6 (0=Mon, datetime.weekday()),
  dom 1..31.

Examples:
  {sec:15}..{sec:15}                — every minute when sec == 15
  {hour:9}..{hour:17}               — hour ∈ [9..17] (inclusive)
  {hour:9, dow:0}..{hour:17, dow:4} — workday daytime (per-field AND)
  {minute:50}..{minute:10}          — wraps the hour (50..59 ∪ 0..10)
  {}..{}                            — always in (no constraints)

The node is always active — every tick refreshes the bool and returns
CFL_CONTINUE. Use it as a leaf inside a column with siblings that read
the flag (e.g. asm_verify against a CFL_BIT_AND boolean).

  node["data"] = {"key": str, "start": dict, "end": dict}
"""

from __future__ import annotations

from datetime import datetime

from ct_runtime.codes import CFL_CONTINUE


def _span_contains(current: int, start_v: int, end_v: int) -> bool:
    if start_v <= end_v:
        return start_v <= current <= end_v
    return current >= start_v or current <= end_v


def _mask_field_ok(current: int, start_v, end_v, field_name: str) -> bool:
    if start_v is None and end_v is None:
        return True
    if start_v is None or end_v is None:
        raise ValueError(
            f"CFL_TIME_WINDOW_CHECK: field {field_name!r} must be present in "
            f"both start and end, or neither"
        )
    return _span_contains(current, start_v, end_v)


def cfl_time_window_check(handle, _bool_fn_name, node, _event):
    data = node["data"]
    key = data["key"]
    start = data["start"]
    end = data["end"]

    engine = handle["engine"]
    epoch_seconds = engine["get_wall_time"]()
    tz = engine.get("timezone")
    dt = datetime.fromtimestamp(epoch_seconds, tz=tz)

    hour_ok   = _mask_field_ok(dt.hour,      start.get("hour"),   end.get("hour"),   "hour")
    minute_ok = _mask_field_ok(dt.minute,    start.get("minute"), end.get("minute"), "minute")
    sec_ok    = _mask_field_ok(dt.second,    start.get("sec"),    end.get("sec"),    "sec")
    dow_ok    = _mask_field_ok(dt.weekday(), start.get("dow"),    end.get("dow"),    "dow")
    dom_ok    = _mask_field_ok(dt.day,       start.get("dom"),    end.get("dom"),    "dom")

    handle["blackboard"][key] = (
        hour_ok and minute_ok and sec_ok and dow_ok and dom_ok
    )
    return CFL_CONTINUE
