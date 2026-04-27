"""State machine tests — transitions, validation, lifecycle helpers."""

from __future__ import annotations

import pytest

from ct_dsl import ChainTree


def _engine_kwargs(log):
    return dict(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )


# ---------------------------------------------------------------------------
# 1. Traffic-light cycle: red → yellow → green → SM disables itself.
# ---------------------------------------------------------------------------

def test_state_machine_traffic_light_cycle():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("traffic")
    sm = ct.define_state_machine(
        "traffic_light",
        state_names=["red", "yellow", "green"],
        initial_state="red",
    )
    ct.define_state("red")
    ct.asm_log_message("red on")
    ct.asm_change_state(sm, "yellow")
    ct.end_state()

    ct.define_state("yellow")
    ct.asm_log_message("yellow on")
    ct.asm_change_state(sm, "green")
    ct.end_state()

    ct.define_state("green")
    ct.asm_log_message("green on")
    # No transition out — green's column completes naturally; SM detects
    # active state child disabled and itself disables.
    ct.end_state()
    ct.end_state_machine()
    ct.end_test()

    ct.run(starting=["traffic"])

    assert log == ["red on", "yellow on", "green on"]
    assert ct.engine["active_kbs"] == []
    assert sm["data"]["current_state_name"] == "green"


# ---------------------------------------------------------------------------
# 2. Reset state machine: re-INITs to initial state.
# ---------------------------------------------------------------------------

def test_state_machine_reset_returns_to_initial():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("rst")
    sm = ct.define_state_machine(
        "two_state",
        state_names=["a", "b"],
        initial_state="a",
    )
    ct.define_state("a")
    ct.asm_log_message("a")
    ct.asm_change_state(sm, "b")
    ct.end_state()

    ct.define_state("b")
    ct.asm_log_message("b")
    # Reset: should return to "a" → log "a" again. To avoid infinite loop,
    # reset only on the FIRST visit to b. The asm_one_shot pattern fires
    # INIT once per activation; after reset, a column is re-initialized
    # but b is not (it gets terminated on reset). So this fires once.
    ct.asm_reset_state_machine(sm)
    ct.end_state()
    ct.end_state_machine()
    # Add a one-shot AFTER the SM that fires when SM disables. Hmm —
    # we'd need an "after-SM" column. Simpler: terminate the test after
    # observing a→b→a→b cycles via blackboard counter.
    ct.end_test()

    # Just run it; the SM will cycle a→b→reset→a→b→reset→...
    # That's an infinite loop. Bound it with max iterations on the engine.
    # Easier: use a tick-counting wrapper for sleep that stops after N.
    ticks = {"n": 0}

    def bounded_sleep(_dt):
        ticks["n"] += 1
        if ticks["n"] > 8:
            # Force outer loop exit by clearing all KBs.
            ct.engine["active_kbs"].clear()

    ct.engine["sleep"] = bounded_sleep
    ct.run()

    # Should have logged 'a' and 'b' multiple times each.
    assert log.count("a") >= 2
    assert log.count("b") >= 2


# ---------------------------------------------------------------------------
# 3. Explicit terminate: asm_terminate_state_machine kills the SM.
# ---------------------------------------------------------------------------

def test_state_machine_explicit_terminate():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("term")
    sm = ct.define_state_machine(
        "killer",
        state_names=["alive", "doomed"],
        initial_state="alive",
    )
    ct.define_state("alive")
    ct.asm_log_message("alive")
    ct.asm_change_state(sm, "doomed")
    ct.end_state()

    ct.define_state("doomed")
    ct.asm_log_message("doomed")
    ct.asm_terminate_state_machine(sm)
    ct.end_state()
    ct.end_state_machine()
    ct.end_test()

    ct.run(starting=["term"])

    assert log == ["alive", "doomed"]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 4. DSL validation: undefined state raises at end_state_machine.
# ---------------------------------------------------------------------------

def test_dsl_undefined_state_raises_at_end():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    ct.define_state_machine("sm", state_names=["a", "b"], initial_state="a")
    ct.define_state("a")
    ct.end_state()
    # Forgot to define "b".
    with pytest.raises(ValueError, match="undefined states"):
        ct.end_state_machine()


def test_dsl_invalid_initial_state_raises():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    with pytest.raises(ValueError, match="not in state_names"):
        ct.define_state_machine("sm", state_names=["a", "b"], initial_state="c")


def test_dsl_undeclared_state_in_define_state():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    ct.define_state_machine("sm", state_names=["a", "b"], initial_state="a")
    with pytest.raises(ValueError, match="not in declared state_names"):
        ct.define_state("c")


def test_dsl_change_to_unknown_state_raises():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    sm = ct.define_state_machine("sm", state_names=["a", "b"], initial_state="a")
    ct.define_state("a")
    with pytest.raises(ValueError, match="not in SM states"):
        ct.asm_change_state(sm, "c")
