"""DSL macro tests — verify the parametric subtree helpers expand correctly."""

from __future__ import annotations

from ct_dsl import ChainTree
from ct_dsl import macros


def _bumper(key):
    def fn(handle, node):
        handle["blackboard"][key] = handle["blackboard"].get(key, 0) + 1
    return fn


def _engine_kwargs(log):
    return dict(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )


# ---------------------------------------------------------------------------
# 1. repeat_n: action fires N times.
# ---------------------------------------------------------------------------

def test_repeat_n_runs_action_n_times():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("BUMP", _bumper("count"))

    ct.start_test("r")
    macros.repeat_n(ct, "loop", "BUMP", count=5)
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["r"])

    assert ct.engine["kbs"]["r"]["blackboard"]["count"] == 5


# ---------------------------------------------------------------------------
# 2. every_n_seconds runs forever (bounded by external stop).
# ---------------------------------------------------------------------------

def test_every_n_seconds_runs_repeatedly():
    log: list[str] = []
    clock = [0.0]
    ct = ChainTree(
        tick_period=1.0,
        sleep=lambda _dt: clock.__setitem__(0, clock[0] + 1.0),
        get_time=lambda: clock[0],
        logger=log.append,
    )
    ct.add_one_shot("BUMP", _bumper("ticks"))

    ct.start_test("p")
    macros.every_n_seconds(ct, "periodic", "BUMP", period_seconds=2.0)
    ct.end_test()

    # Bound the run: stop after ~10 ticks of the engine clock.
    sleep_count = [0]
    real_sleep = ct.engine["sleep"]

    def bounded_sleep(dt):
        real_sleep(dt)
        sleep_count[0] += 1
        if sleep_count[0] >= 10:
            ct.engine["active_kbs"].clear()

    ct.engine["sleep"] = bounded_sleep
    ct.run(starting=["p"])

    # With period=2s and 1s/tick: action fires roughly once per ~3 ticks
    # (action + wait_time + reset → re-init takes a tick). At least 2 fires
    # within 10 ticks.
    assert ct.engine["kbs"]["p"]["blackboard"]["ticks"] >= 2


# ---------------------------------------------------------------------------
# 3. timeout_wrap: action that never sends heartbeat triggers recovery.
# ---------------------------------------------------------------------------

def test_timeout_wrap_invokes_recovery_on_no_heartbeat():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("ON_TO", lambda h, n: h["blackboard"].__setitem__("timed_out", True))

    def build(ct):
        ct.asm_log_message("starting")
        ct.asm_halt()  # never finishes, never sends heartbeat

    ct.start_test("to")
    macros.timeout_wrap(ct, "wrap", build, timeout_ticks=3, on_timeout="ON_TO")
    ct.end_test()

    ct.run(starting=["to"])

    bb = ct.engine["kbs"]["to"]["blackboard"]
    assert bb.get("timed_out") is True
    assert "starting" in log


# ---------------------------------------------------------------------------
# 4. guarded_action: action runs when predicate True, parent TERMINATEs
#    when False.
# ---------------------------------------------------------------------------

def test_guarded_action_runs_when_predicate_true():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("ALWAYS", lambda *_a: True)
    ct.add_one_shot("DO", _bumper("done"))

    ct.start_test("g")
    macros.guarded_action(ct, "ALWAYS", "DO")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["g"])

    assert ct.engine["kbs"]["g"]["blackboard"]["done"] == 1


def test_guarded_action_skipped_when_predicate_false():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("NEVER", lambda *_a: False)
    ct.add_one_shot("DO", _bumper("done"))

    ct.start_test("g")
    macros.guarded_action(ct, "NEVER", "DO")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["g"])

    bb = ct.engine["kbs"]["g"]["blackboard"]
    assert "done" not in bb        # action never fired
    # verify failed → CFL_TERMINATE on parent (root) → KB ends


# ---------------------------------------------------------------------------
# 5. wait_then_act: wait for N timer events, then fire action.
# ---------------------------------------------------------------------------

def test_wait_then_act_fires_after_event_count():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("DO", _bumper("acted"))

    ct.start_test("w")
    macros.wait_then_act(ct, "CFL_TIMER_EVENT", "DO", count=3)
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["w"])

    assert ct.engine["kbs"]["w"]["blackboard"]["acted"] == 1
