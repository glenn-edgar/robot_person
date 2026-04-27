"""Tests for CFL_WAIT_MAIN (event-driven wait) and CFL_VERIFY (assertion)."""

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
# wait_for_event: count CFL_TIMER_EVENT, advance after N ticks.
# ---------------------------------------------------------------------------

def test_wait_for_event_disables_after_n_ticks():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("w")
    ct.asm_log_message("before")
    ct.asm_wait_for_event(event_id="CFL_TIMER_EVENT", count=3)
    ct.asm_log_message("after")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["w"])

    # before logs immediately on tick 1; wait HALTs ticks 1,2,3 (counter
    # increments to 3 on tick 3 → DISABLE on the 3rd visit); after + terminate
    # run on the same tick the wait disables.
    assert log == ["before", "after"]
    leaf_data = ct.engine["kbs"]["w"]["root"]["children"][1]["data"]
    assert leaf_data["current_count"] == 3
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# wait_for_event: timeout fires error_fn and TERMINATEs the column.
# ---------------------------------------------------------------------------

def test_wait_for_event_timeout_fires_error_and_terminates():
    log: list[str] = []
    error_calls: list[dict] = []

    def on_timeout(handle, node):
        error_calls.append({"data": dict(node["data"].get("error_data") or {})})
        handle["blackboard"]["timed_out"] = True

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("ON_TIMEOUT", on_timeout)

    ct.start_test("t")
    ct.asm_log_message("before")
    ct.asm_wait_for_event(
        event_id="WILL_NEVER_ARRIVE",
        count=1,
        timeout=3,
        error_fn="ON_TIMEOUT",
        error_data={"reason": "no_response"},
    )
    ct.asm_log_message("after")  # should NOT run (parent terminates)
    ct.end_test()

    ct.run(starting=["t"])

    assert log == ["before"]                       # "after" never reached
    assert ct.engine["kbs"]["t"]["blackboard"]["timed_out"] is True
    assert len(error_calls) == 1
    assert error_calls[0]["data"] == {"reason": "no_response"}
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# verify: aux returns True → walker continues to next sibling.
# ---------------------------------------------------------------------------

def test_verify_pass_continues():
    log: list[str] = []

    def always_true(handle, node, *_):
        return True

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("ALWAYS_TRUE", always_true)

    ct.start_test("v")
    ct.asm_log_message("before")
    ct.asm_verify("ALWAYS_TRUE")
    ct.asm_log_message("after")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["v"])

    assert log == ["before", "after"]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# verify: aux returns False → CFL_TERMINATE the parent. Subsequent leaves
# do NOT run.
# ---------------------------------------------------------------------------

def test_verify_fail_terminates_parent():
    log: list[str] = []
    error_calls = []

    def always_false(handle, node, *_):
        return False

    def on_fail(handle, node):
        error_calls.append("failed")
        handle["blackboard"]["assert_failed"] = True

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("ALWAYS_FALSE", always_false)
    ct.add_one_shot("ON_FAIL", on_fail)

    ct.start_test("vf")
    ct.asm_log_message("before")
    ct.asm_verify("ALWAYS_FALSE", error_fn="ON_FAIL")
    ct.asm_log_message("after")  # should NOT run
    ct.end_test()

    ct.run(starting=["vf"])

    assert log == ["before"]
    assert error_calls == ["failed"]
    assert ct.engine["kbs"]["vf"]["blackboard"]["assert_failed"] is True
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# verify: reset_flag retries the parent on failure.
# ---------------------------------------------------------------------------

def test_verify_fail_with_reset_flag_retries():
    from ct_runtime import CFL_TERMINATE_EVENT
    log: list[str] = []

    def fail_first_two(handle, node, event_type, event_id, event_data):
        # disable_node invokes the boolean with CFL_TERMINATE_EVENT during
        # teardown (spec contract); ignore that or our attempt counter
        # double-counts during reset cleanup.
        if event_id == CFL_TERMINATE_EVENT:
            return False
        n = handle["blackboard"].get("attempts", 0) + 1
        handle["blackboard"]["attempts"] = n
        return n >= 3

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("FAIL_FIRST_TWO", fail_first_two)

    ct.start_test("vr")
    ct.asm_verify("FAIL_FIRST_TWO", reset_flag=True)
    ct.asm_log_message("succeeded")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["vr"])

    assert ct.engine["kbs"]["vr"]["blackboard"]["attempts"] == 3
    assert log == ["succeeded"]
    assert ct.engine["active_kbs"] == []
