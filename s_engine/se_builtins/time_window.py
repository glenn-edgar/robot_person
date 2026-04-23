"""Wall-clock time-window operator.

`se_time_window_check` reads the current wall-clock time (Linux 64-bit
epoch seconds) via `inst.module["get_wall_time"]()`, converts it to local
time using `inst.module["timezone"]` (None = system local), and writes a
boolean to `dictionary[key]` indicating whether the current local time
falls inside the configured window.

Window shape (B1 — time-of-day span + day filters):

  Time-of-day span (hour, minute, sec) — these compose into a single
  seconds-of-day value (0..86399) and are compared as a span:
    - missing from `start` defaults to 0
    - missing from `end`   defaults to the unit's max (23/59/59)
    - if end < start, the span wraps past midnight

  Day filters (dow, dom) — independent per-field masks AND'd with the span:
    - dow: 0=Mon..6=Sun   (Python datetime.weekday())
    - dom: 1..31
    - must appear in BOTH start and end (or neither = wildcard)
    - form their own wrap-aware closed range

The node is always active — returns SE_PIPELINE_CONTINUE on every tick
including INIT and TERMINATE.
"""

from __future__ import annotations

from datetime import datetime

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    SE_PIPELINE_CONTINUE,
)


def _sod_from_parts(parts, *, is_end: bool) -> int:
    """Compose (hour, minute, sec) into seconds-of-day.
    Missing fine fields default to 0 on start, unit-max on end."""
    if is_end:
        hour = parts.get("hour", 23)
        minute = parts.get("minute", 59)
        sec = parts.get("sec", 59)
    else:
        hour = parts.get("hour", 0)
        minute = parts.get("minute", 0)
        sec = parts.get("sec", 0)
    return hour * 3600 + minute * 60 + sec


def _span_contains(current: int, start_v: int, end_v: int) -> bool:
    if start_v <= end_v:
        return start_v <= current <= end_v
    return current >= start_v or current <= end_v


def _mask_field_ok(current: int, start_v, end_v, field_name: str) -> bool:
    if start_v is None and end_v is None:
        return True
    if start_v is None or end_v is None:
        raise ValueError(
            f"se_time_window_check: field {field_name!r} must be present in both "
            f"start and end, or neither"
        )
    return _span_contains(current, start_v, end_v)


def se_time_window_check(inst, node, event_id, event_data):
    if event_id == EVENT_INIT or event_id == EVENT_TERMINATE:
        return SE_PIPELINE_CONTINUE

    params = node["params"]
    key = params["key"]
    start = params["start"]
    end = params["end"]

    epoch_seconds = inst["module"]["get_wall_time"]()
    tz = inst["module"].get("timezone")
    dt = datetime.fromtimestamp(epoch_seconds, tz=tz)

    current_sod = dt.hour * 3600 + dt.minute * 60 + dt.second
    start_sod = _sod_from_parts(start, is_end=False)
    end_sod = _sod_from_parts(end, is_end=True)
    tod_ok = _span_contains(current_sod, start_sod, end_sod)

    dow_ok = _mask_field_ok(dt.weekday(), start.get("dow"), end.get("dow"), "dow")
    dom_ok = _mask_field_ok(dt.day, start.get("dom"), end.get("dom"), "dom")

    inst["module"]["dictionary"][key] = tod_ok and dow_ok and dom_ok
    return SE_PIPELINE_CONTINUE
