"""Acceptance test for the am_pm_state_machine template (Phase C gate).

Verifies the full round-trip: define → use → generate → run for both an
AM-clock and a PM-clock fixture, asserting the expected log messages
emerge across multiple ticks.

Tick choreography:
  Tick 1: SM enters `initial` state. Initial column logs "<sm> initial",
          fires the DECIDE one-shot which posts a high-priority
          CFL_CHANGE_STATE_EVENT. The drain processes the event, advancing
          the SM to `am` (or `pm`) before tick 1 ends.
  Tick 2: SM is in `am`/`pm`. That state's column logs "<sm> am"/"<sm> pm".
  Tick 3: state column has no enabled children → SM disables → KB root
          disables → run loop exits naturally.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from template_language import (
    ct,
    define_template,
    describe_template,
    generate_code,
    use_template,
)

# No explicit import of the am_pm module — the lazy loader in
# `get_template` resolves the path-to-file mapping on demand.


def _epoch_for_hour_utc(hour: int) -> int:
    """Return an epoch second whose UTC hour-of-day = `hour`."""
    return int(datetime(2026, 5, 1, hour, 0, 0, tzinfo=timezone.utc).timestamp())


def _build_am_pm_solution(*, sm_name: str = "demo"):
    """Wrap the am_pm SM template in a runnable solution template."""
    def _solution():
        ct.start_test(sm_name)
        use_template(
            "composites.chain_tree.am_pm_state_machine",
            sm_name=sm_name,
        )
        ct.end_test()
    return _solution


def _build_chain_with_clock(op_list, *, hour_utc: int, log: list[str], max_ticks: int = 5):
    """Generate the chain with stubbed clocks. Returns (chain, run_fn).
    `run_fn` runs with a tick-limited sleep that flips cfl_engine_flag after
    `max_ticks` ticks so the loop terminates even if the tree never disables."""
    counter = {"n": 0}
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: _epoch_for_hour_utc(hour_utc),
        timezone=timezone.utc,
        logger=log.append,
    )
    # Tick-cap: every iteration of run's outer while-loop calls sleep().
    # We replace sleep with a counter that disables the engine after
    # `max_ticks` ticks have elapsed (in case the tree fails to terminate).
    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= max_ticks:
            chain.engine["cfl_engine_flag"] = False
    chain.engine["sleep"] = capped_sleep
    return chain


# ----------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------

def test_am_pm_template_loadable():
    """Lazy loader resolves the path → file → registry."""
    d = describe_template("composites.chain_tree.am_pm_state_machine")
    assert d["kind"] == "composite"
    assert d["engine"] == "chain_tree"
    assert {s["name"] for s in d["slots"]} == {
        "sm_name", "initial_action", "morning_action", "afternoon_action",
    }


def test_op_list_shape():
    """Phase 1: the op-list contains the expected method sequence."""
    define_template("solution.demo", _build_am_pm_solution(sm_name="demo"),
                    kind="solution", engine="chain_tree")
    op_list = use_template("solution.demo")

    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test",
        "add_one_shot",            # DECIDE
        "define_state_machine",
        "define_state",            # initial
        "asm_log_message",         # "demo initial"
        "asm_one_shot",            # DECIDE
        "end_state",
        "define_state",            # am
        "asm_log_message",         # "demo am"
        "end_state",
        "define_state",            # pm
        "asm_log_message",         # "demo pm"
        "end_state",
        "end_state_machine",
        "end_test",
    ]


def test_am_clock_runs_initial_then_am():
    define_template("solution.am_demo", _build_am_pm_solution(sm_name="demo_am"),
                    kind="solution", engine="chain_tree")
    op_list = use_template("solution.am_demo")
    log: list[str] = []
    chain = _build_chain_with_clock(op_list, hour_utc=9, log=log, max_ticks=5)
    chain.run(starting=["demo_am"])

    assert "demo_am initial" in log
    assert "demo_am am" in log
    assert "demo_am pm" not in log
    # Ordering: initial fires before am.
    assert log.index("demo_am initial") < log.index("demo_am am")


def test_pm_clock_runs_initial_then_pm():
    define_template("solution.pm_demo", _build_am_pm_solution(sm_name="demo_pm"),
                    kind="solution", engine="chain_tree")
    op_list = use_template("solution.pm_demo")
    log: list[str] = []
    chain = _build_chain_with_clock(op_list, hour_utc=15, log=log, max_ticks=5)
    chain.run(starting=["demo_pm"])

    assert "demo_pm initial" in log
    assert "demo_pm pm" in log
    assert "demo_pm am" not in log
    assert log.index("demo_pm initial") < log.index("demo_pm pm")


def test_two_instantiations_use_distinct_names():
    """Two SMs with different sm_name slots coexist in one KB without
    add_one_shot collisions (slot-derived naming discipline)."""
    def two_sms():
        ct.start_test("multi")
        use_template("composites.chain_tree.am_pm_state_machine", sm_name="alpha")
        use_template("composites.chain_tree.am_pm_state_machine", sm_name="beta")
        ct.end_test()
    define_template("solution.two", two_sms, kind="solution", engine="chain_tree")

    op_list = use_template("solution.two")
    # Two add_one_shot ops, distinct names.
    one_shots = [op for op in op_list.ops if op.method == "add_one_shot"]
    assert [op.args[0] for op in one_shots] == ["alpha_DECIDE", "beta_DECIDE"]


def test_collision_when_same_sm_name_used_twice():
    """Same sm_name → engine_fn name collision at recording time."""
    def two_same():
        ct.start_test("collision")
        use_template("composites.chain_tree.am_pm_state_machine", sm_name="dup")
        use_template("composites.chain_tree.am_pm_state_machine", sm_name="dup")
        ct.end_test()
    define_template("solution.collide", two_same, kind="solution", engine="chain_tree")

    from template_language import Codes, TemplateError
    with pytest.raises(TemplateError) as exc:
        use_template("solution.collide")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING


def test_morning_action_slot_splices():
    """An ACTION slot that calls ct.* gets spliced into the morning state's
    column; its op appears in the op-list inside the `am` state, before
    end_state."""
    def with_morning():
        ct.start_test("with_morning_kb")
        use_template(
            "composites.chain_tree.am_pm_state_machine",
            sm_name="wm",
            morning_action=lambda: ct.asm_log_message("morning extra"),
        )
        ct.end_test()
    define_template("solution.wm", with_morning, kind="solution", engine="chain_tree")
    op_list = use_template("solution.wm")
    methods_args = [(op.method, op.args) for op in op_list.ops]
    # The "wm am" log is followed immediately by the spliced "morning extra"
    # log, and only THEN end_state. Find the relevant slice.
    am_idx = next(i for i, (m, a) in enumerate(methods_args)
                  if m == "asm_log_message" and a == ("wm am",))
    assert methods_args[am_idx + 1] == ("asm_log_message", ("morning extra",))
    assert methods_args[am_idx + 2][0] == "end_state"


def test_morning_action_runs_at_runtime():
    log: list[str] = []
    def with_morning():
        ct.start_test("rt_morning")
        use_template(
            "composites.chain_tree.am_pm_state_machine",
            sm_name="rtm",
            morning_action=lambda: ct.asm_log_message("morning extra"),
        )
        ct.end_test()
    define_template("solution.rtm", with_morning, kind="solution", engine="chain_tree")
    op_list = use_template("solution.rtm")
    chain = _build_chain_with_clock(op_list, hour_utc=8, log=log, max_ticks=5)
    chain.run(starting=["rt_morning"])
    assert "rtm initial" in log
    assert "rtm am" in log
    assert "morning extra" in log
    assert log.index("rtm am") < log.index("morning extra")
