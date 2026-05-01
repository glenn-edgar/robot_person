"""Wall-clock time-of-day operators.

Three layers:
  1. Field-mask logic via the internal _in_window helper (pure function;
     no instance, no dispatch).
  2. Operator-level behavior under direct invocation:
     - se_wait_until_in_time_window  → HALT/DISABLE
     - se_wait_until_out_of_time_window → HALT/DISABLE
     - se_in_time_window (predicate) → bool
  3. End-to-end via the DSL:
     - chain_flow + wait_until_in → wait-shape composition
     - if_then_else + in_time_window → predicate gating
     - canonical fire-once-per-window pattern (chain_flow with both leaves)
"""

from datetime import datetime, timedelta, timezone

import pytest

import se_dsl as dsl
from se_builtins import time_window as TW
from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    invoke_any,
    invoke_pred,
    new_instance_from_tree,
    new_module,
)

_UTC = timezone.utc
_PDT = timezone(timedelta(hours=-7))  # fixed offset — no DST surprises


def _epoch(year, month, day, hour=0, minute=0, second=0, *, tz=_UTC) -> int:
    return int(datetime(year, month, day, hour, minute, second, tzinfo=tz).timestamp())


def _clock(epoch_seconds):
    return lambda: epoch_seconds


def _stub_inst(epoch_seconds, tz=_UTC):
    """Minimum fake inst: a module with get_wall_time/timezone. No tree, no
    dispatch state — only what _in_window touches."""
    return {
        "module": {
            "get_wall_time": _clock(epoch_seconds),
            "timezone": tz,
        },
    }


def _params_node(start, end):
    return {"params": {"start": dict(start), "end": dict(end)}}


# ---------------------------------------------------------------------------
# Field-mask logic — _in_window directly. No dictionary, no dispatch.
# ---------------------------------------------------------------------------

def test_in_window_mid_range():
    inst = _stub_inst(_epoch(2026, 4, 23, 9, 30))
    assert TW._in_window(inst, _params_node({"hour": 9}, {"hour": 17})) is True


def test_in_window_out_of_range():
    inst = _stub_inst(_epoch(2026, 4, 23, 18, 0))
    assert TW._in_window(inst, _params_node({"hour": 9}, {"hour": 17})) is False


def test_in_window_end_extends_to_end_of_unit():
    inst = _stub_inst(_epoch(2026, 4, 23, 17, 45))
    assert TW._in_window(inst, _params_node({"hour": 9}, {"hour": 17})) is True


def test_in_window_start_begins_at_zero():
    inst = _stub_inst(_epoch(2026, 4, 23, 9, 0, 0))
    assert TW._in_window(inst, _params_node({"hour": 9}, {"hour": 17})) is True


def test_in_window_per_field_minute_AND():
    node = _params_node({"hour": 9, "minute": 30}, {"hour": 17, "minute": 30})
    assert TW._in_window(_stub_inst(_epoch(2026, 4, 23, 9, 15)), node) is False
    assert TW._in_window(_stub_inst(_epoch(2026, 4, 23, 9, 30)), node) is True


def test_in_window_wrap_late_evening():
    inst = _stub_inst(_epoch(2026, 4, 23, 23, 30))
    assert TW._in_window(inst, _params_node({"hour": 22}, {"hour": 6})) is True


def test_in_window_wrap_early_morning():
    inst = _stub_inst(_epoch(2026, 4, 24, 3, 0))
    assert TW._in_window(inst, _params_node({"hour": 22}, {"hour": 6})) is True


def test_in_window_wrap_midday_out():
    inst = _stub_inst(_epoch(2026, 4, 23, 12, 0))
    assert TW._in_window(inst, _params_node({"hour": 22}, {"hour": 6})) is False


def test_in_window_empty_is_always_in():
    inst = _stub_inst(_epoch(2026, 4, 23, 3, 33, 33))
    assert TW._in_window(inst, _params_node({}, {})) is True


def test_in_window_local_timezone_shifts_evaluation():
    # 23:00 UTC == 16:00 PDT. Window 09..17.
    ts = _epoch(2026, 4, 23, 23, 0, tz=_UTC)
    node = _params_node({"hour": 9}, {"hour": 17})
    assert TW._in_window(_stub_inst(ts, tz=_UTC), node) is False
    assert TW._in_window(_stub_inst(ts, tz=_PDT), node) is True


def test_in_window_dow_matches_weekday():
    # 2026-04-23 = Thursday (weekday() == 3); window dow 0..4 (Mon..Fri).
    inst = _stub_inst(_epoch(2026, 4, 23, 10, 0))
    node = _params_node({"hour": 9, "dow": 0}, {"hour": 17, "dow": 4})
    assert TW._in_window(inst, node) is True


def test_in_window_dow_excludes_saturday():
    inst = _stub_inst(_epoch(2026, 4, 25, 10, 0))
    node = _params_node({"hour": 9, "dow": 0}, {"hour": 17, "dow": 4})
    assert TW._in_window(inst, node) is False


def test_in_window_dow_single_day():
    node = _params_node({"dow": 1}, {"dow": 1})
    assert TW._in_window(_stub_inst(_epoch(2026, 4, 21, 12, 0)), node) is True   # Tue
    assert TW._in_window(_stub_inst(_epoch(2026, 4, 22, 12, 0)), node) is False  # Wed


def test_in_window_dom_first_week():
    node = _params_node({"dom": 1}, {"dom": 7})
    assert TW._in_window(_stub_inst(_epoch(2026, 4, 3, 12, 0)), node) is True
    assert TW._in_window(_stub_inst(_epoch(2026, 4, 15, 12, 0)), node) is False


def test_in_window_per_field_sec_only():
    node = _params_node({"sec": 15}, {"sec": 15})
    cases = [(0, 0, 15, True), (12, 34, 15, True), (23, 59, 15, True),
             (0, 0, 14, False), (0, 0, 16, False), (12, 34, 0, False)]
    for h, m, s, expected in cases:
        inst = _stub_inst(_epoch(2026, 4, 23, h, m, s))
        assert TW._in_window(inst, node) is expected, (h, m, s)


def test_in_window_per_field_minute_wrap():
    node = _params_node({"minute": 50}, {"minute": 10})
    cases = [(50, True), (55, True), (59, True), (0, True), (10, True),
             (11, False), (30, False), (49, False)]
    for m, expected in cases:
        inst = _stub_inst(_epoch(2026, 4, 23, 9, m, 0))
        assert TW._in_window(inst, node) is expected, m


def test_half_specified_dow_raises():
    inst = _stub_inst(_epoch(2026, 4, 23, 12, 0))
    node = _params_node({"hour": 9, "dow": 0}, {"hour": 17})
    with pytest.raises(ValueError, match="dow"):
        TW._in_window(inst, node)


def test_half_specified_minute_raises():
    inst = _stub_inst(_epoch(2026, 4, 23, 12, 0))
    node = _params_node({"hour": 9, "minute": 30}, {"hour": 17})
    with pytest.raises(ValueError, match="minute"):
        TW._in_window(inst, node)


def test_half_specified_sec_raises():
    inst = _stub_inst(_epoch(2026, 4, 23, 12, 0))
    node = _params_node({}, {"sec": 15})
    with pytest.raises(ValueError, match="sec"):
        TW._in_window(inst, node)


def test_half_specified_hour_raises():
    inst = _stub_inst(_epoch(2026, 4, 23, 12, 0))
    node = _params_node({"hour": 9}, {})
    with pytest.raises(ValueError, match="hour"):
        TW._in_window(inst, node)


# ---------------------------------------------------------------------------
# Wait-leaf HALT/DISABLE behavior — direct invocation
# ---------------------------------------------------------------------------

def _build_wait(start, end, fn=TW.se_wait_until_in_time_window):
    return dsl.make_node(fn, "m_call", params={"start": dict(start), "end": dict(end)})


def test_wait_until_in_disables_when_in_window():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
    )
    node = _build_wait({"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_INIT, {}) == SE_PIPELINE_CONTINUE
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_DISABLE


def test_wait_until_in_halts_when_out_of_window():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 22, 0)),
        timezone=_UTC,
    )
    node = _build_wait({"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_INIT, {})
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT


def test_wait_until_out_halts_when_in_window():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
    )
    node = _build_wait({"hour": 9}, {"hour": 17}, fn=TW.se_wait_until_out_of_time_window)
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_INIT, {})
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT


def test_wait_until_out_disables_when_out_of_window():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 22, 0)),
        timezone=_UTC,
    )
    node = _build_wait({"hour": 9}, {"hour": 17}, fn=TW.se_wait_until_out_of_time_window)
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_INIT, {})
    assert invoke_any(inst, node, EVENT_TICK, {}) == SE_PIPELINE_DISABLE


def test_wait_lifecycle_events_return_continue():
    """EVENT_INIT and EVENT_TERMINATE never trigger the wait check — both
    return CONTINUE regardless of window membership. Matches se_wait_event
    convention."""
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),  # in window
        timezone=_UTC,
    )
    node = _build_wait({"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    assert invoke_any(inst, node, EVENT_INIT, {}) == SE_PIPELINE_CONTINUE
    assert invoke_any(inst, node, EVENT_TERMINATE, {}) == SE_PIPELINE_CONTINUE


# ---------------------------------------------------------------------------
# Predicate (p_call) — direct invocation
# ---------------------------------------------------------------------------

def test_in_time_window_predicate_true_in_window():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
    )
    node = dsl.in_time_window({"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    assert invoke_pred(inst, node) is True


def test_in_time_window_predicate_false_out_of_window():
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 22, 0)),
        timezone=_UTC,
    )
    node = dsl.in_time_window({"hour": 9}, {"hour": 17})
    inst = new_instance_from_tree(mod, node)
    assert invoke_pred(inst, node) is False


def test_in_time_window_predicate_with_pred_not():
    """pred_not(in_time_window(...)) is the canonical way to spell
    'out of window' as a predicate — no separate out_of_time_window p_call."""
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 22, 0)),  # out of window
        timezone=_UTC,
    )
    inverse = dsl.pred_not(dsl.in_time_window({"hour": 9}, {"hour": 17}))
    inst = new_instance_from_tree(mod, inverse)
    assert invoke_pred(inst, inverse) is True


# ---------------------------------------------------------------------------
# DSL integration — wait leaves drop into chain_flow / sequence
# ---------------------------------------------------------------------------

def _stepping_walls(wall_start_epoch, seconds_per_tick=1800):
    """(get_wall_time, get_time, advance) — clock state advances by
    `seconds_per_tick` whenever `advance()` is called."""
    state = {"wall": wall_start_epoch, "mono": 0}

    def get_wall_time():
        return int(state["wall"])

    def get_time():
        return state["mono"]

    def advance():
        state["wall"] += seconds_per_tick
        state["mono"] += seconds_per_tick * 1_000_000_000

    return get_wall_time, get_time, advance, state


def test_chain_flow_wait_until_in_blocks_then_proceeds():
    """chain_flow with [log, wait_until_in, log]. Action B should NOT fire
    until the wait DISABLEs. Steps wall clock from 08:30 forward; window 09..17."""
    log = []

    def make_log(msg):
        def _fn(inst, node):
            log.append(msg)
        return dsl.make_node(_fn, "o_call")

    get_wall, get_time, advance, _state = _stepping_walls(
        _epoch(2026, 4, 23, 8, 30), seconds_per_tick=1800
    )

    tree = dsl.chain_flow(
        make_log("A"),
        dsl.wait_until_in_time_window({"hour": 9}, {"hour": 17}),
        make_log("B"),
    )

    mod = new_module(dictionary={}, get_wall_time=get_wall, get_time=get_time, timezone=_UTC)
    inst = new_instance_from_tree(mod, tree)

    invoke_any(inst, tree, EVENT_INIT, {})

    # Tick 1: 08:30, out of window. A fires (o_call), wait HALTs, B blocked.
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert rc == SE_PIPELINE_CONTINUE
    assert log == ["A"]

    # Tick 2: 09:00, in window. wait DISABLEs, B fires, chain_flow drains.
    advance()
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["A", "B"]
    assert rc == SE_PIPELINE_DISABLE


def test_chain_flow_fire_once_per_window_pattern():
    """Canonical composition:
       chain_flow(
         action,                      # fires once
         wait_until_out_of_time_window, # HALT until window closes
       )
    Then once OUT of window, chain_flow drains (DISABLE). Re-arm by RESET
    on a parent.

    Stepping clock from 16:30 (in window) forward. Window 09..17.
    """
    log = []

    def fire(inst, node):
        log.append("fired")

    get_wall, get_time, advance, _state = _stepping_walls(
        _epoch(2026, 4, 23, 16, 30), seconds_per_tick=1800
    )

    tree = dsl.chain_flow(
        dsl.make_node(fire, "o_call"),
        dsl.wait_until_out_of_time_window({"hour": 9}, {"hour": 17}),
    )

    mod = new_module(dictionary={}, get_wall_time=get_wall, get_time=get_time, timezone=_UTC)
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_INIT, {})

    # Tick 1: 16:30 IN window. action fires (o_call), wait HALTs.
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["fired"]
    assert rc == SE_PIPELINE_CONTINUE

    # Tick 2: 17:00 — still in window per the {hour:17} mask (extends to 17:59).
    advance()
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["fired"]  # still gated
    assert rc == SE_PIPELINE_CONTINUE

    # Tick 3: 17:30 — still in (17:00..17:59). wait still HALT.
    advance()
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["fired"]
    assert rc == SE_PIPELINE_CONTINUE

    # Tick 4: 18:00 OUT of window. wait DISABLEs, chain_flow drains.
    advance()
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["fired"]
    assert rc == SE_PIPELINE_DISABLE


def test_sequence_wait_until_in_parks_then_advances():
    """Same shape but with sequence (state-tracked) instead of chain_flow.
    Sequence parks node['state'] on HALT, advances on DISABLE."""
    log = []

    def fire(inst, node):
        log.append("after")

    get_wall, get_time, advance, _state = _stepping_walls(
        _epoch(2026, 4, 23, 8, 30), seconds_per_tick=1800
    )

    tree = dsl.sequence(
        dsl.wait_until_in_time_window({"hour": 9}, {"hour": 17}),
        dsl.make_node(fire, "o_call"),
    )

    mod = new_module(dictionary={}, get_wall_time=get_wall, get_time=get_time, timezone=_UTC)
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_INIT, {})

    # Tick 1: 08:30 OUT. wait HALTs → sequence parks, action does not run.
    invoke_any(inst, tree, EVENT_TICK, {})
    assert log == []

    # Tick 2: 09:00 IN. wait DISABLEs → sequence advances → action runs.
    advance()
    rc = invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["after"]
    assert rc == SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# DSL integration — predicate plugs into if_then_else / cond
# ---------------------------------------------------------------------------

def test_if_then_else_with_in_time_window_predicate():
    """if_then_else gates which branch runs based on the predicate. The
    predicate-as-guard use case that doesn't need a wait leaf."""
    log = []

    def then_fn(inst, node):
        log.append("inside")

    def else_fn(inst, node):
        log.append("outside")

    tree = dsl.if_then_else(
        dsl.in_time_window({"hour": 9}, {"hour": 17}),
        dsl.make_node(then_fn, "o_call"),
        dsl.make_node(else_fn, "o_call"),
    )

    # In window → "inside" fires.
    mod = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 10, 0)),
        timezone=_UTC,
    )
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_INIT, {})
    invoke_any(inst, tree, EVENT_TICK, {})
    assert log == ["inside"]

    # Out of window → "outside" fires.
    log.clear()
    mod2 = new_module(
        dictionary={},
        get_wall_time=_clock(_epoch(2026, 4, 23, 22, 0)),
        timezone=_UTC,
    )
    inst2 = new_instance_from_tree(mod2, tree)
    invoke_any(inst2, tree, EVENT_INIT, {})
    invoke_any(inst2, tree, EVENT_TICK, {})
    assert log == ["outside"]
