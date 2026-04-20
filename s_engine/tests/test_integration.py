"""Integration tests — multi-operator scenarios ported from LuaJIT dsl_tests/.

These exercise realistic plan shapes (nested control + dispatch + timing +
user fns) through the full engine, verifying observable outcomes in the
module dictionary and captured log output.

LuaJIT-specific tests that exercise subsystems the Python port dropped
(stack, quads, equations, function dictionaries, pointer slots) are NOT
ported. Their behaviors are replaced by plain Python callables and the
`call_tree` primitive.

Ported scenarios:
  - callback_via_call_tree      (was: callback_function)
  - fork_generator_and_waiter    (was: complex_sequence Test 1)
  - verify_time_watchdog         (was: complex_sequence Test 2)
  - verify_event_count_watchdog  (was: complex_sequence Test 3)
  - wait_timeout_reset_loop      (was: complex_sequence Test 5)
  - parallel_dispatch_interactions  (was: dispatch)
  - car_window_state_machine     (simplified end-to-end)
"""

from __future__ import annotations

import se_dsl as dsl
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_TERMINATE,
    invoke_any,
    new_instance_from_tree,
    new_module,
    push_event,
    run_until_idle,
)

_NS_PER_SEC = 1_000_000_000


def _clock(start_ns: int = 0):
    t = {"ns": start_ns}
    return (lambda: t["ns"]), (lambda s: t.update(ns=t["ns"] + int(s * _NS_PER_SEC)))


def _tick_until(inst, plan, max_ticks=200, advance=None, seconds_per_tick=0.0):
    """Drive an instance by pushing tick events until DISABLE/TERMINATE or max reached.
    Returns (last_result, ticks_taken)."""
    for i in range(max_ticks):
        r = invoke_any(inst, plan, EVENT_TICK, {})
        if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
            return r, i + 1
        if advance and seconds_per_tick:
            advance(seconds_per_tick)
    return r, max_ticks


# ===========================================================================
# 1. callback_via_call_tree (ported from callback_function)
# ===========================================================================
# LuaJIT test stored a callable in a pointer field and invoked indirectly.
# Python: define a subtree, call it via `call_tree`.

def test_callback_via_call_tree():
    captured = []

    # The "callback" subtree — would have been the stored callable in LuaJIT
    callback = dsl.sequence(
        dsl.log("callback function called"),
        dsl.log("callback doing work"),
    )

    main = dsl.sequence(
        dsl.log("test started"),
        dsl.call_tree(callback),
        dsl.log("test finished"),
    )

    mod = new_module(logger=captured.append)
    inst = new_instance_from_tree(mod, main)
    r, _ = _tick_until(inst, main)
    assert r == SE_PIPELINE_DISABLE
    assert captured == [
        "[log] test started",
        "[log] callback function called",
        "[log] callback doing work",
        "[log] test finished",
    ]


# ===========================================================================
# 2. fork_generator_and_waiter (ported from complex_sequence Test 1)
# ===========================================================================
# Generator pushes N events; waiter counts them via dict_inc_and_test.

def test_fork_generator_and_waiter():
    # Generator: loop that pushes 5 events, each tick
    generator = dsl.while_loop(
        dsl.dict_lt("events_sent", 5),
        dsl.sequence_once(
            dsl.queue_event("sensor.tick"),
            dsl.dict_inc("events_sent"),
        ),
    )
    # Waiter: count incoming sensor.tick events, fire when threshold reached
    waiter = dsl.while_loop(
        dsl.pred_not(dsl.dict_ge("events_seen", 5)),
        dsl.sequence_once(
            dsl.on_event("sensor.tick", dsl.dict_inc("events_seen")),
        ),
    )

    plan = dsl.fork(generator, waiter)
    mod = new_module(dictionary={"events_sent": 0, "events_seen": 0})
    inst = new_instance_from_tree(mod, plan)

    for _ in range(100):
        invoke_any(inst, plan, EVENT_TICK, {})
        run_until_idle(inst)  # drain queued sensor.ticks
        if mod["dictionary"]["events_seen"] >= 5:
            break

    assert mod["dictionary"]["events_sent"] == 5


# ===========================================================================
# 3. verify_time_watchdog (ported from complex_sequence Test 2)
# ===========================================================================
# chain_flow wrapping a verify_and_check_elapsed_time: fires error on timeout.

def test_verify_time_watchdog():
    get_t, advance = _clock()
    captured = []

    plan = dsl.chain_flow(
        dsl.log("verify time test start"),
        dsl.verify_and_check_elapsed_time(
            on_error=dsl.log("verify timeout expired"),
            timeout_seconds=5.0,
            reset=False,
        ),
        dsl.return_pipeline_continue(),  # keeps the chain alive until watchdog
    )
    mod = new_module(get_time=get_t, logger=captured.append)
    inst = new_instance_from_tree(mod, plan)

    # Run ticks until the watchdog fires. Advance clock between ticks.
    for _ in range(200):
        r = invoke_any(inst, plan, EVENT_TICK, {})
        if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
            break
        advance(0.1)  # 100ms per tick
    # verify_and_check_elapsed_time returns TERMINATE (reset=False). chain_flow
    # propagates that upward.
    assert r == SE_PIPELINE_TERMINATE
    assert "[log] verify timeout expired" in captured
    assert "[log] verify time test start" in captured


# ===========================================================================
# 4. verify_event_count_watchdog (ported from complex_sequence Test 3)
# ===========================================================================
# chain_flow: monitor + generator. Monitor fires error on Nth target event.

def test_verify_event_count_watchdog():
    captured = []

    # Monitor chain — error fires when "alarm" event is seen more than 2 times.
    monitor = dsl.chain_flow(
        dsl.log("monitor start"),
        dsl.verify_and_check_elapsed_events(
            on_error=dsl.log("alarm count exceeded"),
            target_event_id="alarm",
            max_count=2,
            reset=False,
        ),
        dsl.return_pipeline_continue(),
    )

    mod = new_module(logger=captured.append)
    inst = new_instance_from_tree(mod, monitor)

    # Tick the monitor; interleave alarm events from the outside.
    for i in range(10):
        r = invoke_any(inst, monitor, EVENT_TICK, {})
        if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
            break
        # On each iteration, send one alarm
        r = invoke_any(inst, monitor, "alarm", {})
        if r in (SE_PIPELINE_DISABLE, SE_PIPELINE_TERMINATE):
            break

    assert r == SE_PIPELINE_TERMINATE
    assert "[log] alarm count exceeded" in captured


# ===========================================================================
# 5. wait_timeout_reset_loop (ported from complex_sequence Test 5 simplified)
# ===========================================================================
# wait_timeout with no matching event → repeatedly TERMINATEs on timeout.

def test_wait_timeout_terminates_on_timeout():
    get_t, advance = _clock()

    plan = dsl.wait_timeout("never", 1.0)
    mod = new_module(get_time=get_t)
    inst = new_instance_from_tree(mod, plan)

    # Before timeout
    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_HALT
    advance(0.5)
    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_HALT
    advance(1.0)  # cumulative 1.5s > 1.0s timeout
    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_TERMINATE


def test_wait_timeout_disables_on_matching_event_before_timeout():
    get_t, advance = _clock()

    plan = dsl.wait_timeout("done", 10.0)
    mod = new_module(get_time=get_t)
    inst = new_instance_from_tree(mod, plan)

    assert invoke_any(inst, plan, EVENT_TICK, {}) == SE_PIPELINE_HALT
    advance(0.5)
    assert invoke_any(inst, plan, "done", {}) == SE_PIPELINE_DISABLE


# ===========================================================================
# 6. parallel_dispatch_interactions (ported from dispatch test)
# ===========================================================================
# Three dispatch mechanisms working together in a function_interface:
# - event_dispatch handles external events
# - dict_dispatch reacts to dictionary changes
# - state_machine generates state-dependent events

def test_parallel_dispatch_interactions():
    captured = []

    # event_dispatch: two external events map to setting dict state
    event_handler = dsl.event_dispatch({
        "user_event_1": dsl.dict_set("state_tag", 1),
        "user_event_3": dsl.dict_set("state_tag", 2),
    })

    # dict_dispatch: react to state_tag values
    field_handler = dsl.dict_dispatch("state_tag", {
        0: dsl.log("state 0"),
        1: dsl.log("state 1"),
        2: dsl.log("state 2"),
    })

    main = dsl.function_interface(event_handler, field_handler)
    mod = new_module(
        dictionary={"state_tag": 0},
        logger=captured.append,
    )
    inst = new_instance_from_tree(mod, main)

    # Tick once — dict_dispatch should log state 0
    invoke_any(inst, main, EVENT_TICK, {})
    assert "[log] state 0" in captured

    # Send user_event_1 → state_tag becomes 1
    invoke_any(inst, main, "user_event_1", {})
    assert mod["dictionary"]["state_tag"] == 1

    # Next tick — dict_dispatch should now pick state 1
    invoke_any(inst, main, EVENT_TICK, {})
    assert "[log] state 1" in captured

    # user_event_3 → state_tag = 2
    invoke_any(inst, main, "user_event_3", {})
    invoke_any(inst, main, EVENT_TICK, {})
    assert "[log] state 2" in captured


# ===========================================================================
# 7. car_window_state_machine (end-to-end state machine)
# ===========================================================================
# Power window controller as a named-state machine reacting to user events.

def test_car_window_state_machine():
    captured = []

    sm = dsl.state_machine(
        states={
            "idle":        dsl.dict_set("window_state", "idle"),
            "going_up":    dsl.dict_set("window_state", "going_up"),
            "going_down":  dsl.dict_set("window_state", "going_down"),
            "stopped":     dsl.dict_set("window_state", "stopped"),
        },
        transitions={
            ("idle",        "up_btn_press"):   "going_up",
            ("idle",        "down_btn_press"): "going_down",
            ("going_up",    "up_btn_release"): "stopped",
            ("going_up",    "limit_reached"):  "idle",
            ("going_down",  "down_btn_release"): "stopped",
            ("going_down",  "limit_reached"):  "idle",
            ("stopped",     "up_btn_press"):   "going_up",
            ("stopped",     "down_btn_press"): "going_down",
        },
        initial="idle",
    )

    mod = new_module(dictionary={}, logger=captured.append)
    inst = new_instance_from_tree(mod, sm)

    # Tick: initial state action fires
    invoke_any(inst, sm, EVENT_TICK, {})
    assert mod["dictionary"]["window_state"] == "idle"

    # User presses Up
    invoke_any(inst, sm, "up_btn_press", {})
    assert mod["dictionary"]["window_state"] == "going_up"

    # Window hits the top — auto limit
    invoke_any(inst, sm, "limit_reached", {})
    assert mod["dictionary"]["window_state"] == "idle"

    # Down press
    invoke_any(inst, sm, "down_btn_press", {})
    assert mod["dictionary"]["window_state"] == "going_down"

    # Release mid-way
    invoke_any(inst, sm, "down_btn_release", {})
    assert mod["dictionary"]["window_state"] == "stopped"

    # From stopped, press Up again
    invoke_any(inst, sm, "up_btn_press", {})
    assert mod["dictionary"]["window_state"] == "going_up"
