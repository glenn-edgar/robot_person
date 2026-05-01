"""Wall-clock time-of-day wait leaves.

Two operators, both following the wait-leaf shape (HALT until cond,
DISABLE on flip):
  CFL_WAIT_UNTIL_IN_TIME_WINDOW    — HALT while OUT, DISABLE on entry
  CFL_WAIT_UNTIL_OUT_OF_TIME_WINDOW — HALT while IN, DISABLE on exit

Three test layers:
  1. Field-mask logic via the internal _in_window helper (pure function;
     no engine, no blackboard).
  2. Operator-level HALT/DISABLE behavior under direct invocation.
  3. End-to-end via the DSL: HALT pauses sibling siblings, DISABLE proceeds.
     Includes the canonical "fire once per window" composition.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import ct_runtime as ct
from ct_builtins import time_window as TW
from ct_runtime.codes import CFL_DISABLE, CFL_HALT, CFL_TIMER_EVENT
from ct_dsl import ChainTree


_UTC = timezone.utc
_PDT = timezone(timedelta(hours=-7))  # fixed offset; no DST surprises


def _epoch(year, month, day, hour=0, minute=0, second=0, *, tz=_UTC) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=tz).timestamp())


def _clock(epoch_seconds):
    return lambda: epoch_seconds


def _stub_handle(epoch_seconds: int, tz=_UTC) -> dict:
    """Minimum fake handle the operator needs: an engine with
    get_wall_time/timezone. No blackboard, no KBs, no queues, no registry."""
    return {
        "engine": {
            "get_wall_time": _clock(epoch_seconds),
            "timezone": tz,
        },
    }


def _node(start, end, main_fn="CFL_WAIT_UNTIL_IN_TIME_WINDOW") -> dict:
    return ct.make_node(
        name="tw",
        main_fn_name=main_fn,
        data={"start": dict(start), "end": dict(end)},
    )


# ---------------------------------------------------------------------------
# Field-mask logic — _in_window directly. No HALT/DISABLE involved.
# ---------------------------------------------------------------------------

def test_in_window_mid_range():
    handle = _stub_handle(_epoch(2026, 4, 23, 9, 30))
    assert TW._in_window(handle, _node({"hour": 9}, {"hour": 17})) is True


def test_in_window_out_of_range():
    handle = _stub_handle(_epoch(2026, 4, 23, 18, 0))
    assert TW._in_window(handle, _node({"hour": 9}, {"hour": 17})) is False


def test_in_window_end_extends_to_end_of_unit():
    handle = _stub_handle(_epoch(2026, 4, 23, 17, 45))
    assert TW._in_window(handle, _node({"hour": 9}, {"hour": 17})) is True


def test_in_window_wrap_late_evening():
    handle = _stub_handle(_epoch(2026, 4, 23, 23, 30))
    assert TW._in_window(handle, _node({"hour": 22}, {"hour": 6})) is True


def test_in_window_wrap_early_morning():
    handle = _stub_handle(_epoch(2026, 4, 24, 3, 0))
    assert TW._in_window(handle, _node({"hour": 22}, {"hour": 6})) is True


def test_in_window_wrap_midday_out():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    assert TW._in_window(handle, _node({"hour": 22}, {"hour": 6})) is False


def test_in_window_empty_is_always_in():
    handle = _stub_handle(_epoch(2026, 4, 23, 3, 33, 33))
    assert TW._in_window(handle, _node({}, {})) is True


def test_in_window_local_timezone_shifts_evaluation():
    # 23:00 UTC == 16:00 PDT. Window 09..17.
    ts = _epoch(2026, 4, 23, 23, 0, tz=_UTC)
    node = _node({"hour": 9}, {"hour": 17})
    assert TW._in_window(_stub_handle(ts, tz=_UTC), node) is False
    assert TW._in_window(_stub_handle(ts, tz=_PDT), node) is True


def test_in_window_dow_matches_weekday():
    # 2026-04-23 = Thursday (weekday() == 3); window dow 0..4 (Mon..Fri).
    handle = _stub_handle(_epoch(2026, 4, 23, 10, 0))
    node = _node({"hour": 9, "dow": 0}, {"hour": 17, "dow": 4})
    assert TW._in_window(handle, node) is True


def test_in_window_dow_excludes_saturday():
    # 2026-04-25 = Saturday (weekday() == 5).
    handle = _stub_handle(_epoch(2026, 4, 25, 10, 0))
    node = _node({"hour": 9, "dow": 0}, {"hour": 17, "dow": 4})
    assert TW._in_window(handle, node) is False


def test_in_window_dom_first_week():
    handle = _stub_handle(_epoch(2026, 4, 3, 12, 0))
    node = _node({"dom": 1}, {"dom": 7})
    assert TW._in_window(handle, node) is True
    handle2 = _stub_handle(_epoch(2026, 4, 15, 12, 0))
    assert TW._in_window(handle2, node) is False


def test_half_specified_dow_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node({"hour": 9, "dow": 0}, {"hour": 17})
    with pytest.raises(ValueError, match="dow"):
        TW._in_window(handle, node)


def test_half_specified_minute_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node({"hour": 9, "minute": 30}, {"hour": 17})
    with pytest.raises(ValueError, match="minute"):
        TW._in_window(handle, node)


def test_half_specified_sec_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node({}, {"sec": 15})
    with pytest.raises(ValueError, match="sec"):
        TW._in_window(handle, node)


def test_half_specified_hour_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node({"hour": 9}, {})
    with pytest.raises(ValueError, match="hour"):
        TW._in_window(handle, node)


def test_per_field_sec_only():
    node = _node({"sec": 15}, {"sec": 15})
    cases = [(0, 0, 15, True), (12, 34, 15, True), (23, 59, 15, True),
             (0, 0, 14, False), (0, 0, 16, False), (12, 34, 0, False)]
    for h, m, s, expected in cases:
        handle = _stub_handle(_epoch(2026, 4, 23, h, m, s))
        assert TW._in_window(handle, node) is expected, (h, m, s)


def test_per_field_minute_wrap():
    node = _node({"minute": 50}, {"minute": 10})
    cases = [(50, True), (55, True), (59, True), (0, True), (10, True),
             (11, False), (30, False), (49, False)]
    for m, expected in cases:
        handle = _stub_handle(_epoch(2026, 4, 23, 9, m, 0))
        assert TW._in_window(handle, node) is expected, m


def test_per_field_hour_minute_AND():
    node = _node({"hour": 9, "minute": 30}, {"hour": 17, "minute": 30})
    cases = [(9, 30, True), (12, 30, True), (17, 30, True),
             (9, 0, False), (9, 15, False), (18, 30, False), (8, 30, False)]
    for h, m, expected in cases:
        handle = _stub_handle(_epoch(2026, 4, 23, h, m, 0))
        assert TW._in_window(handle, node) is expected, (h, m)


# ---------------------------------------------------------------------------
# Operator HALT/DISABLE behavior — direct invocation
# ---------------------------------------------------------------------------

def test_wait_until_in_disables_when_in_window():
    handle = _stub_handle(_epoch(2026, 4, 23, 10, 0))
    node = _node({"hour": 9}, {"hour": 17})
    rc = TW.cfl_wait_until_in_time_window(
        handle, None, node, {"event_id": CFL_TIMER_EVENT}
    )
    assert rc == CFL_DISABLE


def test_wait_until_in_halts_when_out_of_window():
    handle = _stub_handle(_epoch(2026, 4, 23, 22, 0))
    node = _node({"hour": 9}, {"hour": 17})
    rc = TW.cfl_wait_until_in_time_window(
        handle, None, node, {"event_id": CFL_TIMER_EVENT}
    )
    assert rc == CFL_HALT


def test_wait_until_out_halts_when_in_window():
    handle = _stub_handle(_epoch(2026, 4, 23, 10, 0))
    node = _node({"hour": 9}, {"hour": 17})
    rc = TW.cfl_wait_until_out_of_time_window(
        handle, None, node, {"event_id": CFL_TIMER_EVENT}
    )
    assert rc == CFL_HALT


def test_wait_until_out_disables_when_out_of_window():
    handle = _stub_handle(_epoch(2026, 4, 23, 22, 0))
    node = _node({"hour": 9}, {"hour": 17})
    rc = TW.cfl_wait_until_out_of_time_window(
        handle, None, node, {"event_id": CFL_TIMER_EVENT}
    )
    assert rc == CFL_DISABLE


# ---------------------------------------------------------------------------
# DSL integration — HALT actually blocks downstream siblings; DISABLE proceeds
# ---------------------------------------------------------------------------

def _stepping_walls(wall_start_epoch: int, seconds_per_tick: float = 1.0):
    """(get_wall_time, get_time, sleep) where each `sleep` advances both
    clocks by `seconds_per_tick`. Wall starts at `wall_start_epoch`;
    monotonic at 0."""
    state = {"wall": wall_start_epoch, "mono": 0.0}

    def get_wall_time():
        return int(state["wall"])

    def get_time():
        return state["mono"]

    def sleep(_dt):
        state["wall"] += seconds_per_tick
        state["mono"] += seconds_per_tick

    return get_wall_time, get_time, sleep, state


def test_dsl_wait_until_in_disables_immediately_when_already_in():
    """Already inside the window on the first tick — wait disables, sibling
    log fires, parent terminates. No HALT spent."""
    log: list[str] = []
    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
        logger=log.append,
    )
    chain.start_test("g")
    chain.asm_wait_until_in_time_window({"hour": 9}, {"hour": 17})
    chain.asm_log_message("inside")
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["g"])

    assert log == ["inside"]
    assert chain.engine["active_kbs"] == []


def test_dsl_wait_until_in_blocks_siblings_then_proceeds():
    """Stepping wall clock from 08:30 forward; window 09..17. The wait
    leaf HALTs every tick the clock is below 09:00 — the sibling log NEVER
    fires those ticks. Once the clock crosses 09:00 the wait DISABLEs and
    the column drains: log fires once, terminate ends the KB.

    Asserts: HALT actually blocks siblings (otherwise the log would fire
    on tick 1 with the clock at 08:30)."""
    log: list[str] = []
    get_wall, get_time, sleep, state = _stepping_walls(
        wall_start_epoch=_epoch(2026, 4, 23, 8, 30),
        seconds_per_tick=1800,  # 30 minutes per tick
    )

    chain = ChainTree(
        tick_period=0.0,
        sleep=sleep,
        get_time=get_time,
        get_wall_time=get_wall,
        timezone=_UTC,
        logger=log.append,
    )
    chain.start_test("g")
    chain.asm_wait_until_in_time_window({"hour": 9}, {"hour": 17})
    chain.asm_log_message("entered window")
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["g"])

    assert log == ["entered window"]
    assert state["wall"] >= _epoch(2026, 4, 23, 9, 0)
    assert chain.engine["active_kbs"] == []


def test_dsl_wait_until_out_blocks_siblings_then_proceeds():
    """Stepping wall clock from 16:30 forward; window 09..17. The wait_out
    leaf HALTs every tick the clock is INSIDE the window; sibling log only
    fires once the clock leaves 17:00 boundary."""
    log: list[str] = []
    get_wall, get_time, sleep, state = _stepping_walls(
        wall_start_epoch=_epoch(2026, 4, 23, 16, 30),
        seconds_per_tick=1800,
    )

    chain = ChainTree(
        tick_period=0.0,
        sleep=sleep,
        get_time=get_time,
        get_wall_time=get_wall,
        timezone=_UTC,
        logger=log.append,
    )
    chain.start_test("g")
    chain.asm_wait_until_out_of_time_window({"hour": 9}, {"hour": 17})
    chain.asm_log_message("left window")
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["g"])

    assert log == ["left window"]
    # 17:00 is still IN; first OUT tick is 18:00.
    assert state["wall"] >= _epoch(2026, 4, 23, 18, 0)
    assert chain.engine["active_kbs"] == []


def test_dsl_fire_once_per_window_pattern():
    """Canonical composition:
       column:
         wait_until_in_time_window   — HALT until 09:00, DISABLE
         asm_log_message("fire")     — fires once
         wait_until_out_of_time_window — HALT until 18:00, DISABLE
         asm_terminate               — column drains; KB done

    Stepping clock: starts 08:30, +30min/tick. Crosses into the window at
    09:00, action fires, wait_out HALTs through 09..17, exits at 18:00,
    terminate.
    """
    log: list[str] = []
    get_wall, get_time, sleep, state = _stepping_walls(
        wall_start_epoch=_epoch(2026, 4, 23, 8, 30),
        seconds_per_tick=1800,
    )

    chain = ChainTree(
        tick_period=0.0,
        sleep=sleep,
        get_time=get_time,
        get_wall_time=get_wall,
        timezone=_UTC,
        logger=log.append,
    )
    chain.start_test("once")
    chain.asm_wait_until_in_time_window({"hour": 9}, {"hour": 17})
    chain.asm_log_message("fire")
    chain.asm_wait_until_out_of_time_window({"hour": 9}, {"hour": 17})
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["once"])

    # Action fires exactly once — HALT before, HALT after, DISABLE on exit.
    assert log == ["fire"]
    assert state["wall"] >= _epoch(2026, 4, 23, 18, 0)
    assert chain.engine["active_kbs"] == []
