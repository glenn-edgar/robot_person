"""Time-window operator tests. Uses an injected wall clock + fixed TZ."""

from datetime import datetime, timedelta, timezone

import pytest

from se_builtins import time_window as TW
from se_dsl import make_node
from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    invoke_any,
    new_instance_from_tree,
    new_module,
)

_UTC = timezone.utc
_PDT = timezone(timedelta(hours=-7))  # fixed offset — no DST surprises


def _epoch(year, month, day, hour=0, minute=0, second=0, *, tz=_UTC) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=tz).timestamp())


def _clock(epoch_seconds):
    return lambda: epoch_seconds


def _node(key, start, end):
    return make_node(
        TW.se_time_window_check, "m_call",
        params={"key": key, "start": start, "end": end},
    )


# ---------------------------------------------------------------------------
# Time-of-day span — basic in / out / boundaries
# ---------------------------------------------------------------------------

def test_span_in_window_mid_range():
    # 09:30 local, window 09:00..17:00 → in (span, not per-field)
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 9, 30)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    r = invoke_any(inst, node, EVENT_TICK, {})
    assert r == SE_PIPELINE_CONTINUE
    assert mod["dictionary"]["on"] is True


def test_span_out_of_window():
    # 18:00 local, window 09:00..17:00 → out
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 18, 0)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["on"] is False


def test_end_default_extends_to_end_of_unit():
    # {hour: 17} as end means up to 17:59:59; 17:45 should be in-window
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 17, 45)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["on"] is True


def test_start_default_begins_at_zero():
    # {hour: 9} as start means 09:00:00; 09:00:00 is in-window
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 9, 0, 0)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["on"] is True


def test_paired_minute_constrains_per_field():
    # Per-field AND: hour ∈ [9..17] AND minute ∈ [30..30]. 09:15 → out (minute).
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 9, 15)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9, "minute": 30}, {"hour": 17, "minute": 30})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["on"] is False

    # 09:30 — hour and minute both match. In.
    mod2 = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 9, 30)),
        timezone=_UTC,
    )
    inst2 = new_instance_from_tree(mod2, node)
    invoke_any(inst2, node, EVENT_TICK, {})
    assert mod2["dictionary"]["on"] is True


# ---------------------------------------------------------------------------
# Wrap-around (end < start)
# ---------------------------------------------------------------------------

def test_wrap_span_late_evening_in_window():
    # 22:00..06:00, current 23:30 → in (wraps midnight)
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 23, 30)),
        timezone=_UTC,
    )
    node = _node("night", {"hour": 22}, {"hour": 6})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["night"] is True


def test_wrap_span_early_morning_in_window():
    # 22:00..06:00, current 03:00 → in
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 24, 3, 0)),
        timezone=_UTC,
    )
    node = _node("night", {"hour": 22}, {"hour": 6})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["night"] is True


def test_wrap_span_midday_out():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 12, 0)),
        timezone=_UTC,
    )
    node = _node("night", {"hour": 22}, {"hour": 6})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["night"] is False


# ---------------------------------------------------------------------------
# Empty / wildcard window
# ---------------------------------------------------------------------------

def test_empty_window_is_always_in():
    # {}..{} → 0..86399 seconds-of-day → always in
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 3, 33, 33)),
        timezone=_UTC,
    )
    node = _node("on", {}, {})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["on"] is True


# ---------------------------------------------------------------------------
# Local time conversion
# ---------------------------------------------------------------------------

def test_local_timezone_shifts_window_evaluation():
    # Same epoch instant, evaluated in two timezones.
    # Epoch represents 2026-04-23 16:00 UTC == 09:00 PDT (UTC-7).
    ts = _epoch(2026, 4, 23, 16, 0, tz=_UTC)
    window_start = {"hour": 9}
    window_end = {"hour": 17}

    # UTC → 16:00 local → in 09..17 span
    mod_utc = new_module(dictionary={}, get_wall_time=_clock(ts), timezone=_UTC)
    node = _node("on", window_start, window_end)
    inst = new_instance_from_tree(mod_utc, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod_utc["dictionary"]["on"] is True

    # PDT → 09:00 local → also in span, but that's the boundary; pick a time
    # that differentiates. Re-run with an epoch that is out-of-window in UTC
    # but in-window in PDT.
    ts2 = _epoch(2026, 4, 23, 23, 0, tz=_UTC)  # 23:00 UTC == 16:00 PDT

    mod_utc_out = new_module(dictionary={}, get_wall_time=_clock(ts2), timezone=_UTC)
    node_utc_out = _node("on", window_start, window_end)
    inst = new_instance_from_tree(mod_utc_out, node_utc_out)
    invoke_any(inst, node_utc_out, EVENT_TICK, {})
    assert mod_utc_out["dictionary"]["on"] is False  # 23:00 UTC out of 09..17

    mod_pdt_in = new_module(dictionary={}, get_wall_time=_clock(ts2), timezone=_PDT)
    node_pdt_in = _node("on", window_start, window_end)
    inst = new_instance_from_tree(mod_pdt_in, node_pdt_in)
    invoke_any(inst, node_pdt_in, EVENT_TICK, {})
    assert mod_pdt_in["dictionary"]["on"] is True  # 16:00 PDT in 09..17


# ---------------------------------------------------------------------------
# Day-of-week and day-of-month masks
# ---------------------------------------------------------------------------

def test_dow_mask_matches_weekday():
    # 2026-04-23 = Thursday, weekday() == 3. Window dow 0..4 (Mon..Fri).
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
    )
    node = _node("workday",
                 {"hour": 9, "dow": 0},
                 {"hour": 17, "dow": 4})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["workday"] is True


def test_dow_mask_excludes_saturday():
    # 2026-04-25 = Saturday, weekday() == 5. Window dow 0..4.
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 25, 10, 0)),
        timezone=_UTC,
    )
    node = _node("workday",
                 {"hour": 9, "dow": 0},
                 {"hour": 17, "dow": 4})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["workday"] is False


def test_dow_single_day():
    # dow 1..1 — Tuesdays only. 2026-04-21 is a Tuesday.
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 21, 12, 0)),
        timezone=_UTC,
    )
    node = _node("tues", {"dow": 1}, {"dow": 1})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["tues"] is True

    # Wednesday should be excluded
    mod2 = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 22, 12, 0)),
        timezone=_UTC,
    )
    node2 = _node("tues", {"dow": 1}, {"dow": 1})
    inst2 = new_instance_from_tree(mod2, node2)
    invoke_any(inst2, node2, EVENT_TICK, {})
    assert mod2["dictionary"]["tues"] is False


def test_dom_mask_matches():
    # dom 1..7 (first week of month). 2026-04-03 = day 3.
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 3, 12, 0)),
        timezone=_UTC,
    )
    node = _node("first_week", {"dom": 1}, {"dom": 7})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["first_week"] is True


def test_dom_mask_excludes_later_dates():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 15, 12, 0)),
        timezone=_UTC,
    )
    node = _node("first_week", {"dom": 1}, {"dom": 7})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK, {})
    assert mod["dictionary"]["first_week"] is False


def test_half_specified_dow_raises():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 12, 0)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9, "dow": 0}, {"hour": 17})  # dow missing from end
    inst = new_instance_from_tree(mod, node)
    with pytest.raises(ValueError, match="dow"):
        invoke_any(inst, node, EVENT_TICK, {})


def test_half_specified_minute_raises():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 12, 0)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9, "minute": 30}, {"hour": 17})  # minute only in start
    inst = new_instance_from_tree(mod, node)
    with pytest.raises(ValueError, match="minute"):
        invoke_any(inst, node, EVENT_TICK, {})


def test_half_specified_sec_raises():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 12, 0)),
        timezone=_UTC,
    )
    node = _node("on", {}, {"sec": 15})  # sec only in end
    inst = new_instance_from_tree(mod, node)
    with pytest.raises(ValueError, match="sec"):
        invoke_any(inst, node, EVENT_TICK, {})


def test_half_specified_hour_raises():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 12, 0)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9}, {})  # hour only in start
    inst = new_instance_from_tree(mod, node)
    with pytest.raises(ValueError, match="hour"):
        invoke_any(inst, node, EVENT_TICK, {})


# ---------------------------------------------------------------------------
# Per-field semantics — only specified fields constrain the check
# ---------------------------------------------------------------------------

def test_per_field_sec_only_fires_at_sec_15():
    # {sec:15}..{sec:15} — fires whenever wall-clock sec == 15, regardless of
    # hour/minute/dow/dom. The "every minute when sec=15" use case.
    node = _node("hit", {"sec": 15}, {"sec": 15})

    for h, m, s, expected in [
        (0, 0, 15, True),
        (12, 34, 15, True),
        (23, 59, 15, True),
        (0, 0, 14, False),
        (0, 0, 16, False),
        (12, 34, 0, False),
    ]:
        mod = new_module(
            dictionary={},
            get_wall_time=_clock(_epoch(2026, 4, 23, h, m, s)),
            timezone=_UTC,
        )
        inst = new_instance_from_tree(mod, node)
        invoke_any(inst, node, EVENT_TICK, {})
        assert mod["dictionary"]["hit"] is expected, (h, m, s)


def test_per_field_minute_only():
    # {minute:30}..{minute:30} — fires at any HH:30:SS.
    node = _node("hit", {"minute": 30}, {"minute": 30})
    for h, m, s, expected in [
        (9, 30, 0, True),
        (9, 30, 45, True),
        (17, 30, 0, True),
        (9, 29, 59, False),
        (9, 31, 0, False),
    ]:
        mod = new_module(
            dictionary={},
            get_wall_time=_clock(_epoch(2026, 4, 23, h, m, s)),
            timezone=_UTC,
        )
        inst = new_instance_from_tree(mod, node)
        invoke_any(inst, node, EVENT_TICK, {})
        assert mod["dictionary"]["hit"] is expected, (h, m, s)


def test_per_field_minute_wrap():
    # {minute:50}..{minute:10} — wrap-aware per-field: minute ∈ [50..59] ∪ [0..10].
    node = _node("hit", {"minute": 50}, {"minute": 10})
    for m, expected in [(50, True), (55, True), (59, True),
                        (0, True), (10, True),
                        (11, False), (30, False), (49, False)]:
        mod = new_module(
            dictionary={},
            get_wall_time=_clock(_epoch(2026, 4, 23, 9, m, 0)),
            timezone=_UTC,
        )
        inst = new_instance_from_tree(mod, node)
        invoke_any(inst, node, EVENT_TICK, {})
        assert mod["dictionary"]["hit"] is expected, m


def test_per_field_hour_minute_AND():
    # hour ∈ [9..17] AND minute ∈ [30..30].
    node = _node("hit", {"hour": 9, "minute": 30}, {"hour": 17, "minute": 30})
    for h, m, expected in [
        (9, 30, True),
        (12, 30, True),
        (17, 30, True),
        (9, 0, False),       # minute fails
        (9, 15, False),      # minute fails
        (18, 30, False),     # hour fails
        (8, 30, False),      # hour fails
    ]:
        mod = new_module(
            dictionary={},
            get_wall_time=_clock(_epoch(2026, 4, 23, h, m, 0)),
            timezone=_UTC,
        )
        inst = new_instance_from_tree(mod, node)
        invoke_any(inst, node, EVENT_TICK, {})
        assert mod["dictionary"]["hit"] is expected, (h, m)


# ---------------------------------------------------------------------------
# Lifecycle events return CONTINUE without writing
# ---------------------------------------------------------------------------

def test_init_and_terminate_are_noops():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 12, 0)),
        timezone=_UTC,
    )
    node = _node("on", {"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_INIT, {}) == SE_PIPELINE_CONTINUE
    assert "on" not in mod["dictionary"]
    assert invoke_any(inst, node, EVENT_TERMINATE, {}) == SE_PIPELINE_CONTINUE
    assert "on" not in mod["dictionary"]
