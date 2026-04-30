"""Wall-clock time-of-day window operator — native CFL + s_engine bridge.

Native side: `CFL_TIME_WINDOW_CHECK` writes a bool to the KB blackboard
each tick. Bridge side: the same window shape from s_engine
(`se_time_window_check`) runs through chain_tree's bridge using the
clock/timezone forwarded from the chain_tree engine.

All tests inject `get_wall_time` so wall-clock output is deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import ct_runtime as ct
from ct_builtins import time_window as TW
from ct_runtime.codes import CFL_CONTINUE, CFL_TIMER_EVENT, CFL_EVENT_TYPE_NULL
from ct_dsl import ChainTree


_UTC = timezone.utc
_PDT = timezone(timedelta(hours=-7))  # fixed offset; no DST surprises


def _epoch(year, month, day, hour=0, minute=0, second=0, *, tz=_UTC) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=tz).timestamp())


def _clock(epoch_seconds):
    return lambda: epoch_seconds


def _stub_handle(epoch_seconds: int, tz=_UTC) -> dict:
    """Build the minimum fake handle the operator needs: an engine with
    get_wall_time/timezone and a blackboard. No KBs / queues / registry."""
    return {
        "blackboard": {},
        "engine": {
            "get_wall_time": _clock(epoch_seconds),
            "timezone": tz,
        },
    }


def _node(key, start, end) -> dict:
    return ct.make_node(
        name="tw",
        main_fn_name="CFL_TIME_WINDOW_CHECK",
        data={"key": key, "start": dict(start), "end": dict(end)},
    )


# ---------------------------------------------------------------------------
# Native CFL operator — direct invocation
# ---------------------------------------------------------------------------

def test_native_in_window_mid_range():
    handle = _stub_handle(_epoch(2026, 4, 23, 9, 30))
    node = _node("on", {"hour": 9}, {"hour": 17})
    rc = TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert rc == CFL_CONTINUE
    assert handle["blackboard"]["on"] is True


def test_native_out_of_window():
    handle = _stub_handle(_epoch(2026, 4, 23, 18, 0))
    node = _node("on", {"hour": 9}, {"hour": 17})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["on"] is False


def test_native_end_default_extends_to_end_of_unit():
    # {hour: 17} as end means up to 17:59:59
    handle = _stub_handle(_epoch(2026, 4, 23, 17, 45))
    node = _node("on", {"hour": 9}, {"hour": 17})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["on"] is True


def test_native_wrap_span_late_evening_in_window():
    # 22:00..06:00 wraps midnight; 23:30 should be in
    handle = _stub_handle(_epoch(2026, 4, 23, 23, 30))
    node = _node("night", {"hour": 22}, {"hour": 6})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["night"] is True


def test_native_wrap_span_early_morning_in_window():
    handle = _stub_handle(_epoch(2026, 4, 24, 3, 0))
    node = _node("night", {"hour": 22}, {"hour": 6})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["night"] is True


def test_native_wrap_span_midday_out():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node("night", {"hour": 22}, {"hour": 6})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["night"] is False


def test_native_empty_window_is_always_in():
    handle = _stub_handle(_epoch(2026, 4, 23, 3, 33, 33))
    node = _node("on", {}, {})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["on"] is True


def test_native_local_timezone_shifts_evaluation():
    # 23:00 UTC == 16:00 PDT. Window 09..17.
    ts = _epoch(2026, 4, 23, 23, 0, tz=_UTC)

    handle_utc = _stub_handle(ts, tz=_UTC)
    node = _node("on", {"hour": 9}, {"hour": 17})
    TW.cfl_time_window_check(handle_utc, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle_utc["blackboard"]["on"] is False

    handle_pdt = _stub_handle(ts, tz=_PDT)
    TW.cfl_time_window_check(handle_pdt, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle_pdt["blackboard"]["on"] is True


def test_native_dow_mask_matches_weekday():
    # 2026-04-23 = Thursday (weekday() == 3); window dow 0..4 (Mon..Fri).
    handle = _stub_handle(_epoch(2026, 4, 23, 10, 0))
    node = _node("workday",
                 {"hour": 9, "dow": 0},
                 {"hour": 17, "dow": 4})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["workday"] is True


def test_native_dow_mask_excludes_saturday():
    # 2026-04-25 = Saturday (weekday() == 5).
    handle = _stub_handle(_epoch(2026, 4, 25, 10, 0))
    node = _node("workday",
                 {"hour": 9, "dow": 0},
                 {"hour": 17, "dow": 4})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["workday"] is False


def test_native_dom_mask_first_week():
    handle = _stub_handle(_epoch(2026, 4, 3, 12, 0))
    node = _node("first_week", {"dom": 1}, {"dom": 7})
    TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle["blackboard"]["first_week"] is True

    handle2 = _stub_handle(_epoch(2026, 4, 15, 12, 0))
    TW.cfl_time_window_check(handle2, None, node, {"event_id": CFL_TIMER_EVENT})
    assert handle2["blackboard"]["first_week"] is False


def test_native_half_specified_dow_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node("on", {"hour": 9, "dow": 0}, {"hour": 17})  # dow missing from end
    with pytest.raises(ValueError, match="dow"):
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})


def test_native_half_specified_minute_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node("on", {"hour": 9, "minute": 30}, {"hour": 17})  # minute only in start
    with pytest.raises(ValueError, match="minute"):
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})


def test_native_half_specified_sec_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node("on", {}, {"sec": 15})  # sec only in end
    with pytest.raises(ValueError, match="sec"):
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})


def test_native_half_specified_hour_raises():
    handle = _stub_handle(_epoch(2026, 4, 23, 12, 0))
    node = _node("on", {"hour": 9}, {})  # hour only in start
    with pytest.raises(ValueError, match="hour"):
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})


# ---------------------------------------------------------------------------
# Per-field semantics — only specified fields constrain the check
# ---------------------------------------------------------------------------

def test_native_per_field_sec_only_fires_at_sec_15():
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
        handle = _stub_handle(_epoch(2026, 4, 23, h, m, s))
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
        assert handle["blackboard"]["hit"] is expected, (h, m, s)


def test_native_per_field_minute_only():
    node = _node("hit", {"minute": 30}, {"minute": 30})
    for h, m, s, expected in [
        (9, 30, 0, True),
        (9, 30, 45, True),
        (17, 30, 0, True),
        (9, 29, 59, False),
        (9, 31, 0, False),
    ]:
        handle = _stub_handle(_epoch(2026, 4, 23, h, m, s))
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
        assert handle["blackboard"]["hit"] is expected, (h, m, s)


def test_native_per_field_minute_wrap():
    # minute ∈ [50..59] ∪ [0..10] (wrap-aware per-field).
    node = _node("hit", {"minute": 50}, {"minute": 10})
    for m, expected in [(50, True), (55, True), (59, True),
                        (0, True), (10, True),
                        (11, False), (30, False), (49, False)]:
        handle = _stub_handle(_epoch(2026, 4, 23, 9, m, 0))
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
        assert handle["blackboard"]["hit"] is expected, m


def test_native_per_field_hour_minute_AND():
    node = _node("hit", {"hour": 9, "minute": 30}, {"hour": 17, "minute": 30})
    for h, m, expected in [
        (9, 30, True),
        (12, 30, True),
        (17, 30, True),
        (9, 0, False),
        (9, 15, False),
        (18, 30, False),
        (8, 30, False),
    ]:
        handle = _stub_handle(_epoch(2026, 4, 23, h, m, 0))
        TW.cfl_time_window_check(handle, None, node, {"event_id": CFL_TIMER_EVENT})
        assert handle["blackboard"]["hit"] is expected, (h, m)


# ---------------------------------------------------------------------------
# End-to-end via the DSL: ChainTree.run() drives one tick, asserts blackboard
# ---------------------------------------------------------------------------

def test_dsl_writes_blackboard_on_first_tick():
    """asm_time_window_check inside a column writes the bool, then the
    column terminates so run() exits."""
    log: list[str] = []
    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 9, 30)),
        timezone=_UTC,
        logger=log.append,
    )
    chain.start_test("tw")
    chain.asm_time_window_check("on", {"hour": 9}, {"hour": 17})
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["tw"])

    bb = chain.engine["kbs"]["tw"]["blackboard"]
    assert bb["on"] is True


def test_dsl_writes_false_when_outside_window():
    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 18, 0)),
        timezone=_UTC,
    )
    chain.start_test("tw")
    chain.asm_time_window_check("on", {"hour": 9}, {"hour": 17})
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["tw"])

    assert chain.engine["kbs"]["tw"]["blackboard"]["on"] is False


# ---------------------------------------------------------------------------
# Bridge: s_engine's time_window_check uses chain_tree's get_wall_time/timezone
# ---------------------------------------------------------------------------

def test_se_bridge_forwards_wall_clock_to_s_engine():
    """An s_engine tree using `time_window_check` driven from a chain_tree
    se_tick must use the chain_tree engine's injected wall clock and TZ.
    Verifies se_module_load_init plumbed both through to new_module.
    """
    import se_dsl as dsl
    from se_runtime import push_event, run_until_idle

    main_tree = dsl.sequence(
        dsl.time_window_check("on", {"hour": 9}, {"hour": 17}),
    )

    fired = {"count": 0}

    def driver(handle, node, event_type, event_id, event_data):
        # Drive only the first CFL tick — second pass would skip the o_call.
        fired["count"] += 1
        if fired["count"] > 1:
            return
        inst = handle["blackboard"][node["data"]["tree_key"]]
        push_event(inst, "tick", {})
        run_until_idle(inst)

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 9, 30)),
        timezone=_UTC,
    )
    chain.add_boolean("DRIVER", driver)

    chain.start_test("br")
    chain.asm_se_module_load(key="mod", trees={"main": main_tree})
    chain.asm_se_tree_create(key="inst", module_key="mod", tree_name="main")
    chain.define_se_tick(tree_key="inst", aux_fn="DRIVER")
    chain.end_se_tick()
    chain.asm_terminate()
    chain.end_test()

    chain.run(starting=["br"])

    bb = chain.engine["kbs"]["br"]["blackboard"]
    assert bb["on"] is True


def test_se_bridge_window_outside_writes_false():
    import se_dsl as dsl
    from se_runtime import push_event, run_until_idle

    main_tree = dsl.sequence(
        dsl.time_window_check("on", {"hour": 9}, {"hour": 17}),
    )

    fired = {"count": 0}

    def driver(handle, node, event_type, event_id, event_data):
        fired["count"] += 1
        if fired["count"] > 1:
            return
        inst = handle["blackboard"][node["data"]["tree_key"]]
        push_event(inst, "tick", {})
        run_until_idle(inst)

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 18, 0)),
        timezone=_UTC,
    )
    chain.add_boolean("DRIVER", driver)

    chain.start_test("br")
    chain.asm_se_module_load(key="mod", trees={"main": main_tree})
    chain.asm_se_tree_create(key="inst", module_key="mod", tree_name="main")
    chain.define_se_tick(tree_key="inst", aux_fn="DRIVER")
    chain.end_se_tick()
    chain.asm_terminate()
    chain.end_test()

    chain.run(starting=["br"])

    assert chain.engine["kbs"]["br"]["blackboard"]["on"] is False


# ---------------------------------------------------------------------------
# Integration scenarios — composition with verify, reset/retry, stepping clock
# ---------------------------------------------------------------------------

def _stepping_walls(wall_start_epoch: int, seconds_per_tick: float = 1.0):
    """Build (get_wall_time, get_time, sleep) where each `sleep` call
    advances both clocks by `seconds_per_tick`. The wall clock starts at
    `wall_start_epoch`; the monotonic clock starts at 0."""
    state = {"wall": wall_start_epoch, "mono": 0.0}

    def get_wall_time():
        return int(state["wall"])

    def get_time():
        return state["mono"]

    def sleep(_dt):
        state["wall"] += seconds_per_tick
        state["mono"] += seconds_per_tick

    return get_wall_time, get_time, sleep, state


def test_integration_verify_passes_when_in_window():
    """Single-tick happy path: window in → verify passes → log + terminate."""
    log: list[str] = []

    def in_window(handle, node, event_type, event_id, event_data):
        return bool(handle["blackboard"].get("armed", False))

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
        logger=log.append,
    )
    chain.add_boolean("IN_WINDOW", in_window)

    chain.start_test("gate")
    chain.asm_time_window_check("armed", {"hour": 9}, {"hour": 17})
    chain.asm_verify("IN_WINDOW")
    chain.asm_log_message("inside window")
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["gate"])

    assert log == ["inside window"]
    assert chain.engine["kbs"]["gate"]["blackboard"]["armed"] is True
    assert chain.engine["active_kbs"] == []


def test_integration_verify_terminates_when_out_of_window():
    """Window false → verify fails (reset_flag=False) → parent terminates;
    the log-after-verify never runs."""
    log: list[str] = []

    def in_window(handle, node, event_type, event_id, event_data):
        return bool(handle["blackboard"].get("armed", False))

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 22, 0)),  # outside 09..17
        timezone=_UTC,
        logger=log.append,
    )
    chain.add_boolean("IN_WINDOW", in_window)

    chain.start_test("gate")
    chain.asm_time_window_check("armed", {"hour": 9}, {"hour": 17})
    chain.asm_verify("IN_WINDOW")
    chain.asm_log_message("inside window")  # should NEVER fire
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["gate"])

    assert log == []
    assert chain.engine["kbs"]["gate"]["blackboard"]["armed"] is False


def test_integration_reset_retries_until_clock_enters_window():
    """Stepping wall clock, 30 min/tick. Window 09..17. Start at 08:30
    (out → verify resets parent). At 09:00 verify passes; log + terminate.

    Exercises: window operator on every tick, verify reset re-initing the
    parent, the bit re-evaluated each tick against the advanced wall clock.
    """
    log: list[str] = []
    get_wall, get_time, sleep, state = _stepping_walls(
        wall_start_epoch=_epoch(2026, 4, 23, 8, 30),
        seconds_per_tick=1800,  # 30 minutes
    )

    def in_window(handle, node, event_type, event_id, event_data):
        return bool(handle["blackboard"].get("armed", False))

    chain = ChainTree(
        tick_period=0.0,
        sleep=sleep,
        get_time=get_time,
        get_wall_time=get_wall,
        timezone=_UTC,
        logger=log.append,
    )
    chain.add_boolean("IN_WINDOW", in_window)

    chain.start_test("retry")
    chain.asm_time_window_check("armed", {"hour": 9}, {"hour": 17})
    chain.asm_verify("IN_WINDOW", reset_flag=True)
    chain.asm_log_message("entered window")
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["retry"])

    # log fires exactly once (on the first tick when wall_time >= 09:00).
    assert log == ["entered window"]
    # Wall clock advanced from 08:30 — first tick out, second tick in,
    # then sleep once more after the loop exits.
    assert state["wall"] >= _epoch(2026, 4, 23, 9, 0)
    assert chain.engine["kbs"]["retry"]["blackboard"]["armed"] is True


def test_integration_native_and_bridged_share_clock():
    """A CFL-native window operator and a bridged s_engine window operator,
    with the SAME window shape and the SAME injected wall clock, must
    produce the same boolean. Confirms the bridge plumbs clock + tz
    consistently into the s_engine module."""
    import se_dsl as dsl
    from se_runtime import push_event, run_until_idle

    main_tree = dsl.sequence(
        dsl.time_window_check("se_armed", {"hour": 9}, {"hour": 17}),
    )

    fired = {"count": 0}

    def driver(handle, node, event_type, event_id, event_data):
        fired["count"] += 1
        if fired["count"] > 1:
            return
        inst = handle["blackboard"][node["data"]["tree_key"]]
        push_event(inst, "tick", {})
        run_until_idle(inst)

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 14, 0)),  # mid-window
        timezone=_UTC,
    )
    chain.add_boolean("DRIVER", driver)

    chain.start_test("coop")
    chain.asm_time_window_check("cfl_armed", {"hour": 9}, {"hour": 17})
    chain.asm_se_module_load(key="mod", trees={"main": main_tree})
    chain.asm_se_tree_create(key="inst", module_key="mod", tree_name="main")
    chain.define_se_tick(tree_key="inst", aux_fn="DRIVER")
    chain.end_se_tick()
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["coop"])

    bb = chain.engine["kbs"]["coop"]["blackboard"]
    assert bb["cfl_armed"] is True
    assert bb["se_armed"] is True
    # Same shape, same clock, same TZ → same answer on both sides.
    assert bb["cfl_armed"] == bb["se_armed"]


def test_integration_native_and_bridged_share_clock_outside():
    """Counterpart: clock outside the window, both sides must read False."""
    import se_dsl as dsl
    from se_runtime import push_event, run_until_idle

    main_tree = dsl.sequence(
        dsl.time_window_check("se_armed", {"hour": 9}, {"hour": 17}),
    )

    fired = {"count": 0}

    def driver(handle, node, event_type, event_id, event_data):
        fired["count"] += 1
        if fired["count"] > 1:
            return
        inst = handle["blackboard"][node["data"]["tree_key"]]
        push_event(inst, "tick", {})
        run_until_idle(inst)

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=_clock(_epoch(2026, 4, 23, 23, 0)),  # outside window
        timezone=_UTC,
    )
    chain.add_boolean("DRIVER", driver)

    chain.start_test("coop_out")
    chain.asm_time_window_check("cfl_armed", {"hour": 9}, {"hour": 17})
    chain.asm_se_module_load(key="mod", trees={"main": main_tree})
    chain.asm_se_tree_create(key="inst", module_key="mod", tree_name="main")
    chain.define_se_tick(tree_key="inst", aux_fn="DRIVER")
    chain.end_se_tick()
    chain.asm_terminate()
    chain.end_test()
    chain.run(starting=["coop_out"])

    bb = chain.engine["kbs"]["coop_out"]["blackboard"]
    assert bb["cfl_armed"] is False
    assert bb["se_armed"] is False


def test_integration_wrap_window_across_midnight():
    """Stepping clock from 23:30 → 01:30 (30 min/tick). Window 22..06 (wraps
    midnight). The bit must remain True across the midnight rollover —
    verify the column never trips out of window."""
    bit_history: list[bool] = []

    def in_window(handle, node, event_type, event_id, event_data):
        # Boolean fns must filter CFL_TERMINATE_EVENT — disable_node fires
        # us during teardown and we'd otherwise log a phantom 5th sample.
        if event_id == "CFL_TERMINATE_EVENT":
            return False
        bit_history.append(bool(handle["blackboard"].get("armed", False)))
        # Pass while in-window; fail (terminate, reset_flag=False) once
        # we've collected 4 samples — that gives us 4 ticks of evidence.
        return len(bit_history) < 4

    get_wall, get_time, sleep, _ = _stepping_walls(
        wall_start_epoch=_epoch(2026, 4, 23, 23, 30),
        seconds_per_tick=1800,
    )

    chain = ChainTree(
        tick_period=0.0,
        sleep=sleep,
        get_time=get_time,
        get_wall_time=get_wall,
        timezone=_UTC,
    )
    chain.add_boolean("IN_WINDOW", in_window)

    chain.start_test("wrap")
    chain.asm_time_window_check("armed", {"hour": 22}, {"hour": 6})
    chain.asm_verify("IN_WINDOW")  # reset_flag=False → terminate after 4 samples
    chain.end_test()
    chain.run(starting=["wrap"])

    # 4 samples covering 23:30, 00:00, 00:30, 01:00 — all within the
    # wrap-aware 22..06 window.
    assert bit_history == [True, True, True, True]
