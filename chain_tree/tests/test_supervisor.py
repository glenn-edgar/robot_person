"""Supervisor tests — restart policies, rate limiting, finalize."""

from __future__ import annotations

import pytest

from ct_dsl import ChainTree


def _engine_kwargs(log, get_time=None):
    return dict(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=get_time or (lambda: 0.0),
        logger=log.append,
    )


def _bumper(key):
    """One-shot factory: each call increments handle.blackboard[key]."""
    def fn(handle, node):
        handle["blackboard"][key] = handle["blackboard"].get(key, 0) + 1
    return fn


# ---------------------------------------------------------------------------
# 1. ONE_FOR_ONE: only the failed child restarts; siblings keep running.
# ---------------------------------------------------------------------------

def test_one_for_one_restarts_only_failed_child():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.add_one_shot("BUMP_A", _bumper("a"))
    ct.add_one_shot("BUMP_B", _bumper("b"))

    ct.start_test("o2o")
    sup = ct.define_supervisor(
        "sup", termination_type="ONE_FOR_ONE",
        reset_limited_enabled=True, max_reset_number=3,
    )
    # A: bumps and immediately disables (column auto-disables when leaves done)
    ct.define_column("a")
    ct.asm_one_shot("BUMP_A")
    ct.asm_terminate()
    ct.end_column()
    # B: bumps once at INIT then halts forever (never disables on its own)
    ct.define_column("b")
    ct.asm_one_shot("BUMP_B")
    ct.asm_halt()
    ct.end_column()
    ct.end_supervisor()
    ct.end_test()

    ct.run(starting=["o2o"])

    bb = ct.engine["kbs"]["o2o"]["blackboard"]
    # A ran initial + 3 restarts = 4 times. B INITed once and stayed halted.
    assert bb["a"] == 4
    assert bb["b"] == 1
    assert sup["ct_control"]["supervisor_state"]["reset_count"] == 3


# ---------------------------------------------------------------------------
# 2. ONE_FOR_ALL: when ANY child fails, terminate + restart EVERY child.
# ---------------------------------------------------------------------------

def test_one_for_all_restarts_every_child_when_one_fails():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.add_one_shot("BUMP_A", _bumper("a"))
    ct.add_one_shot("BUMP_B", _bumper("b"))

    ct.start_test("o4all")
    sup = ct.define_supervisor(
        "sup", termination_type="ONE_FOR_ALL",
        reset_limited_enabled=True, max_reset_number=2,
    )
    ct.define_column("a")
    ct.asm_one_shot("BUMP_A")
    ct.asm_terminate()
    ct.end_column()
    ct.define_column("b")
    ct.asm_one_shot("BUMP_B")
    ct.asm_halt()
    ct.end_column()
    ct.end_supervisor()
    ct.end_test()

    ct.run(starting=["o4all"])

    bb = ct.engine["kbs"]["o4all"]["blackboard"]
    # A: initial + 2 restarts. B re-INITs each time supervisor restarts everyone.
    assert bb["a"] == 3
    assert bb["b"] == 3
    assert sup["ct_control"]["supervisor_state"]["reset_count"] == 2


# ---------------------------------------------------------------------------
# 3. REST_FOR_ALL: middle child fails → that and every child after restart;
#    earlier siblings continue untouched.
# ---------------------------------------------------------------------------

def test_rest_for_all_restarts_failed_and_later_siblings():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.add_one_shot("BUMP_A", _bumper("a"))
    ct.add_one_shot("BUMP_B", _bumper("b"))
    ct.add_one_shot("BUMP_C", _bumper("c"))

    ct.start_test("rfa")
    sup = ct.define_supervisor(
        "sup", termination_type="REST_FOR_ALL",
        reset_limited_enabled=True, max_reset_number=2,
    )
    # A: bumps once at INIT and halts (declared first; should never restart)
    ct.define_column("a")
    ct.asm_one_shot("BUMP_A")
    ct.asm_halt()
    ct.end_column()
    # B: bumps and disables (the "failing" child)
    ct.define_column("b")
    ct.asm_one_shot("BUMP_B")
    ct.asm_terminate()
    ct.end_column()
    # C: bumps and halts (declared after B; should restart with B)
    ct.define_column("c")
    ct.asm_one_shot("BUMP_C")
    ct.asm_halt()
    ct.end_column()
    ct.end_supervisor()
    ct.end_test()

    ct.run(starting=["rfa"])

    bb = ct.engine["kbs"]["rfa"]["blackboard"]
    # A INITed once (never restarted). B: initial + 2 restarts. C: same as B
    # (re-INITed each time B is restarted, since C is declared after B).
    assert bb["a"] == 1
    assert bb["b"] == 3
    assert bb["c"] == 3
    assert sup["ct_control"]["supervisor_state"]["reset_count"] == 2


# ---------------------------------------------------------------------------
# 4. Restart limit fires finalize and DISABLEs the supervisor.
# ---------------------------------------------------------------------------

def test_restart_limit_fires_finalize_and_disables():
    log: list[str] = []
    finalize_calls = []

    def on_finalize(handle, node):
        finalize_calls.append(node["ct_control"]["supervisor_state"]["reset_count"])
        handle["blackboard"]["finalized"] = True

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("BUMP_A", _bumper("a"))
    ct.add_one_shot("ON_FINALIZE", on_finalize)

    ct.start_test("lim")
    ct.define_supervisor(
        "sup", termination_type="ONE_FOR_ONE",
        reset_limited_enabled=True, max_reset_number=2,
        finalize_fn="ON_FINALIZE",
    )
    ct.define_column("a")
    ct.asm_one_shot("BUMP_A")
    ct.asm_terminate()
    ct.end_column()
    ct.end_supervisor()
    ct.end_test()

    ct.run(starting=["lim"])

    bb = ct.engine["kbs"]["lim"]["blackboard"]
    assert bb["a"] == 3                      # initial + 2 restarts
    assert bb["finalized"] is True
    assert finalize_calls == [2]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 5. Sliding window — failures outside the window don't count toward limit.
# ---------------------------------------------------------------------------

def test_sliding_window_expires_old_failures():
    """SupervisorFailureCounter: only failures within `reset_window` count."""
    from ct_builtins.supervisor import SupervisorFailureCounter

    clock = [0.0]
    counter = SupervisorFailureCounter(window=10.0, get_time=lambda: clock[0])

    counter.record_failure()
    counter.record_failure()
    assert counter.get_failure_count() == 2
    assert counter.is_threshold_exceeded(2) is True

    # Advance clock past the window — both failures expire.
    clock[0] = 11.0
    assert counter.get_failure_count() == 0
    assert counter.is_threshold_exceeded(2) is False

    counter.record_failure()
    assert counter.get_failure_count() == 1


# ---------------------------------------------------------------------------
# 6. restart_enabled=False: supervisor disables on first failure.
# ---------------------------------------------------------------------------

def test_restart_disabled_disables_on_first_failure():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("BUMP_A", _bumper("a"))

    ct.start_test("nr")
    sup = ct.define_supervisor("sup", termination_type="ONE_FOR_ONE",
                                restart_enabled=False)
    ct.define_column("a")
    ct.asm_one_shot("BUMP_A")
    ct.asm_terminate()
    ct.end_column()
    ct.end_supervisor()
    ct.end_test()

    ct.run(starting=["nr"])

    bb = ct.engine["kbs"]["nr"]["blackboard"]
    assert bb["a"] == 1                          # initial only, no restart
    assert sup["ct_control"]["supervisor_state"]["reset_count"] == 0
