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


# ---------------------------------------------------------------------------
# 6. retry_until_success: stops on first marked-pass attempt.
# ---------------------------------------------------------------------------

def test_retry_until_success_stops_on_first_pass():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    attempts = [0]

    def attempt(handle, node):
        attempts[0] += 1
        # Side-effect: write the latest attempt number to bb so the
        # predicate can decide based on it.
        handle["blackboard"]["last_attempt"] = attempts[0]

    def predicate(handle, node, event_type, event_id, event_data):
        # Filter the post-mark probe — predicate fires inside a one-shot
        # so it never sees CFL_TERMINATE_EVENT, but defensive filter is cheap.
        if event_id == "CFL_TERMINATE_EVENT":
            return False
        # Pass on the 3rd attempt and later.
        return handle["blackboard"].get("last_attempt", 0) >= 3

    ct.add_one_shot("ATTEMPT", attempt)
    ct.add_boolean("OK_NOW", predicate)

    ct.start_test("retry")
    seq = macros.retry_until_success(
        ct,
        "rty",
        attempt_one_shot="ATTEMPT",
        success_predicate_fn="OK_NOW",
        max_attempts=5,
    )
    ct.end_test()

    ct.run(starting=["retry"])

    # Attempts 1 and 2 marked fail; attempt 3 marked pass; sequence
    # short-circuited (attempts 4 and 5 never ran).
    assert attempts[0] == 3
    state = seq["ct_control"]["sequence_state"]
    assert state["results"][0]["status"] is False
    assert state["results"][1]["status"] is False
    assert state["results"][2]["status"] is True


def test_retry_until_success_runs_all_attempts_when_predicate_never_passes():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    attempts = [0]

    def attempt(handle, node):
        attempts[0] += 1

    def never(handle, node, event_type, event_id, event_data):
        return False

    ct.add_one_shot("ATTEMPT", attempt)
    ct.add_boolean("NEVER", never)

    ct.start_test("noretry")
    macros.retry_until_success(
        ct, "rty", "ATTEMPT", "NEVER", max_attempts=4,
    )
    ct.end_test()

    ct.run(starting=["noretry"])

    # All 4 attempts ran; sequence_til_pass completes (no pass found).
    assert attempts[0] == 4


# ---------------------------------------------------------------------------
# 7. state_machine_from_table: builds an SM that walks events through.
# ---------------------------------------------------------------------------

def test_state_machine_from_table_drives_state_walk():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    def step_a(handle, node):
        log.append("entered A")

    def step_b(handle, node):
        log.append("entered B")

    def step_done(handle, node):
        log.append("entered DONE")
        # Self-terminate so the test ends.
        handle["engine"]["cfl_engine_flag"] = False

    ct.add_one_shot("STEP_A", step_a)
    ct.add_one_shot("STEP_B", step_b)
    ct.add_one_shot("STEP_DONE", step_done)

    ct.start_test("tbl")
    sm = macros.state_machine_from_table(
        ct, "fsm",
        transitions=[
            ("a", "GO_TO_B", "b", "STEP_B"),
            ("b", "GO_TO_DONE", "done", "STEP_DONE"),
        ],
        initial_state="a",
    )
    ct.end_test()

    # Pre-stage events on the queue so the SM transitions immediately
    # without needing a real event source.
    from ct_runtime import enqueue
    from ct_runtime.event_queue import make_event
    from ct_runtime.codes import CFL_EVENT_TYPE_NULL, PRIORITY_NORMAL

    # We need to enqueue these AFTER activate_kb stamps the SM root, so
    # use a sleep callback that injects them on the first tick.
    fired = [False]

    def inject(_dt):
        if fired[0]:
            return
        fired[0] = True
        enqueue(ct.engine, make_event(
            target=sm, event_type=CFL_EVENT_TYPE_NULL,
            event_id="GO_TO_B", data=None, priority=PRIORITY_NORMAL,
        ))
        enqueue(ct.engine, make_event(
            target=sm, event_type=CFL_EVENT_TYPE_NULL,
            event_id="GO_TO_DONE", data=None, priority=PRIORITY_NORMAL,
        ))

    ct.engine["sleep"] = inject
    ct.run(starting=["tbl"])

    assert "entered B" in log
    assert "entered DONE" in log


def test_state_machine_from_table_rejects_initial_not_in_states():
    import pytest
    ct = ChainTree(**_engine_kwargs([]))
    ct.start_test("bad")
    with pytest.raises(ValueError, match="initial_state"):
        macros.state_machine_from_table(
            ct, "fsm",
            transitions=[("a", "EV", "b", None)],
            initial_state="z",  # not in any transition
        )
