"""sequence_til tests — pass and fail flavors, finalize, exhaustion, mark misuse."""

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
# 1. pass-til succeeds on attempt 2/3 — third attempt never runs.
# ---------------------------------------------------------------------------

def test_sequence_til_pass_succeeds_on_second_attempt():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    finalize_calls = {"n": 0}

    def on_finalize(handle, node):
        finalize_calls["n"] += 1
        finalize_calls["final_status"] = node["ct_control"]["sequence_state"]["final_status"]

    ct.add_one_shot("ON_FINALIZE", on_finalize)

    ct.start_test("p")
    seq = ct.define_sequence_til_pass("retry", finalize_fn="ON_FINALIZE")

    ct.define_column("attempt_1")
    ct.asm_log_message("trying 1")
    ct.asm_mark_sequence_fail(seq)
    ct.end_column()

    ct.define_column("attempt_2")
    ct.asm_log_message("trying 2")
    ct.asm_mark_sequence_pass(seq)
    ct.end_column()

    ct.define_column("attempt_3")
    ct.asm_log_message("trying 3 (should not run)")
    ct.asm_mark_sequence_pass(seq)
    ct.end_column()

    ct.end_sequence_til_pass()
    ct.end_test()

    ct.run(starting=["p"])

    assert log == ["trying 1", "trying 2"]
    assert finalize_calls["n"] == 1
    assert finalize_calls["final_status"] is True
    state = seq["ct_control"]["sequence_state"]
    assert state["current_index"] == 1
    assert state["results"][0]["status"] is False
    assert state["results"][1]["status"] is True
    assert state["results"][2] is None
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 2. pass-til exhausts all attempts → finalize with final_status=False.
# ---------------------------------------------------------------------------

def test_sequence_til_pass_exhausts_all_attempts():
    log: list[str] = []
    finalize_calls = {"n": 0}

    def on_finalize(handle, node):
        finalize_calls["n"] += 1
        finalize_calls["final_status"] = node["ct_control"]["sequence_state"]["final_status"]

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("ON_FINALIZE", on_finalize)

    ct.start_test("e")
    seq = ct.define_sequence_til_pass("attempts", finalize_fn="ON_FINALIZE")
    for i in range(1, 4):
        ct.define_column(f"attempt_{i}")
        ct.asm_log_message(f"try {i}")
        ct.asm_mark_sequence_fail(seq)
        ct.end_column()
    ct.end_sequence_til_pass()
    ct.end_test()

    ct.run(starting=["e"])

    assert log == ["try 1", "try 2", "try 3"]
    assert finalize_calls["n"] == 1
    assert finalize_calls["final_status"] is False     # all failed
    state = seq["ct_control"]["sequence_state"]
    assert state["current_index"] == 2                  # last index reached
    assert all(r["status"] is False for r in state["results"])


# ---------------------------------------------------------------------------
# 3. fail-til runs all when every child passes.
# ---------------------------------------------------------------------------

def test_sequence_til_fail_runs_all_when_all_pass():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("f")
    seq = ct.define_sequence_til_fail("checks")
    for i in range(1, 4):
        ct.define_column(f"check_{i}")
        ct.asm_log_message(f"check {i}")
        ct.asm_mark_sequence_pass(seq)
        ct.end_column()
    ct.end_sequence_til_fail()
    ct.end_test()

    ct.run(starting=["f"])

    assert log == ["check 1", "check 2", "check 3"]
    state = seq["ct_control"]["sequence_state"]
    assert state["final_status"] is True
    assert state["current_index"] == 2


# ---------------------------------------------------------------------------
# 4. fail-til stops at first failure.
# ---------------------------------------------------------------------------

def test_sequence_til_fail_stops_at_first_failure():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("ff")
    seq = ct.define_sequence_til_fail("checks")
    ct.define_column("check_1")
    ct.asm_log_message("check 1")
    ct.asm_mark_sequence_pass(seq)
    ct.end_column()
    ct.define_column("check_2")
    ct.asm_log_message("check 2 (will fail)")
    ct.asm_mark_sequence_fail(seq)
    ct.end_column()
    ct.define_column("check_3")
    ct.asm_log_message("check 3 (should not run)")
    ct.asm_mark_sequence_pass(seq)
    ct.end_column()
    ct.end_sequence_til_fail()
    ct.end_test()

    ct.run(starting=["ff"])

    assert log == ["check 1", "check 2 (will fail)"]
    state = seq["ct_control"]["sequence_state"]
    assert state["final_status"] is False
    assert state["current_index"] == 1


# ---------------------------------------------------------------------------
# 5. Missing mark raises immediately.
# ---------------------------------------------------------------------------

def test_sequence_til_missing_mark_raises():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("m")
    ct.define_sequence_til_pass("forgotten")
    ct.define_column("forgot_to_mark")
    ct.asm_log_message("only this")
    ct.end_column()
    ct.end_sequence_til_pass()
    ct.end_test()

    with pytest.raises(RuntimeError, match="without calling CFL_MARK_SEQUENCE"):
        ct.run(starting=["m"])
