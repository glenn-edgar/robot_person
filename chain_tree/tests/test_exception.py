"""Exception catch + heartbeat tests.

Covers normal flow, raised exception → recovery, filter forwarding to a
parent catch, heartbeat reset and timeout, and DSL validation."""

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
# 1. Normal flow: MAIN runs to completion → FINALIZE runs → catch disables.
# ---------------------------------------------------------------------------

def test_exception_catch_normal_flow_main_then_finalize():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("normal")
    ct.define_exception_handler("h")
    ct.define_main_column()
    ct.asm_log_message("main work")
    ct.asm_terminate()
    ct.end_main_column()
    ct.define_recovery_column()
    ct.asm_log_message("recovery (should not run)")
    ct.end_recovery_column()
    ct.define_finalize_column()
    ct.asm_log_message("cleanup")
    ct.end_finalize_column()
    ct.end_exception_handler()
    ct.end_test()

    ct.run(starting=["normal"])

    assert log == ["main work", "cleanup"]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 2. Exception in MAIN → RECOVERY → FINALIZE.
# ---------------------------------------------------------------------------

def test_exception_in_main_runs_recovery_then_finalize():
    log: list[str] = []
    captured: list[dict] = []

    def logger_fn(handle, node):
        captured.append(dict(
            node["ct_control"]["exception_state"]["raised_exception"]
        ))

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("LOG_EXC", logger_fn)

    ct.start_test("e")
    ct.define_exception_handler("h", logging_fn="LOG_EXC")
    ct.define_main_column()
    ct.asm_log_message("main start")
    ct.asm_raise_exception("OOPS", {"detail": "things broke"})
    # asm_raise is async (enqueues high-pri event; the leaf disables and
    # the walker continues siblings). asm_halt blocks remaining siblings
    # until the catch processes the event and terminates the whole MAIN
    # column. This is the documented "raise then halt" idiom.
    ct.asm_halt()
    ct.asm_log_message("main end (should not run)")
    ct.end_main_column()
    ct.define_recovery_column()
    ct.asm_log_message("recovering")
    ct.end_recovery_column()
    ct.define_finalize_column()
    ct.asm_log_message("done")
    ct.end_finalize_column()
    ct.end_exception_handler()
    ct.end_test()

    ct.run(starting=["e"])

    assert log == ["main start", "recovering", "done"]
    assert len(captured) == 1
    assert captured[0]["exception_id"] == "OOPS"
    assert captured[0]["exception_data"] == {"detail": "things broke"}


# ---------------------------------------------------------------------------
# 3. Filter forwards exception up to outer catch.
# ---------------------------------------------------------------------------

def test_filter_forwards_to_outer_catch():
    log: list[str] = []

    def forward_filter(handle, node, event_type, event_id, event_data):
        # True → forward up; only forward exceptions tagged "OUTER".
        from ct_runtime import CFL_RAISE_EXCEPTION_EVENT
        if event_id != CFL_RAISE_EXCEPTION_EVENT:
            return False
        return (event_data or {}).get("exception_id") == "OUTER"

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("FORWARD_OUTER", forward_filter)

    ct.start_test("nest")
    ct.define_exception_handler("outer")
    ct.define_main_column()
    ct.define_exception_handler("inner", boolean_filter_fn="FORWARD_OUTER")
    ct.define_main_column()
    ct.asm_log_message("inner main")
    ct.asm_raise_exception("OUTER")
    ct.end_main_column()
    ct.define_recovery_column()
    ct.asm_log_message("inner recovery (should not run)")
    ct.end_recovery_column()
    ct.define_finalize_column()
    ct.asm_log_message("inner finalize")
    ct.end_finalize_column()
    ct.end_exception_handler()
    ct.end_main_column()
    ct.define_recovery_column()
    ct.asm_log_message("outer recovery")
    ct.end_recovery_column()
    ct.define_finalize_column()
    ct.asm_log_message("outer finalize")
    ct.end_finalize_column()
    ct.end_exception_handler()
    ct.end_test()

    ct.run(starting=["nest"])

    # inner forwards → it DISABLEs (no recovery), parent handles → outer runs
    # recovery and finalize.
    assert "inner main" in log
    assert "inner recovery (should not run)" not in log
    assert "outer recovery" in log
    assert "outer finalize" in log
    # inner finalize never runs because inner DISABLEd directly (forwarded).
    assert "inner finalize" not in log


# ---------------------------------------------------------------------------
# 4. Heartbeat: with regular heartbeat events, no timeout escalation.
# ---------------------------------------------------------------------------

def test_heartbeat_resets_counter_keeps_main_alive():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("hb")
    ct.define_exception_handler("h")
    ct.define_main_column()
    ct.asm_turn_heartbeat_on(timeout=5)
    ct.asm_log_message("main")
    # Send heartbeat then halt — heartbeat keeps the catch from timing out.
    ct.asm_heartbeat_event()
    ct.asm_terminate()                # column completes naturally
    ct.end_main_column()
    ct.define_recovery_column()
    ct.asm_log_message("recovery (should not fire)")
    ct.end_recovery_column()
    ct.define_finalize_column()
    ct.asm_log_message("done")
    ct.end_finalize_column()
    ct.end_exception_handler()
    ct.end_test()

    ct.run(starting=["hb"])

    assert "recovery (should not fire)" not in log
    assert "main" in log and "done" in log


# ---------------------------------------------------------------------------
# 5. Heartbeat timeout: MAIN halts forever, no heartbeats → escalates.
# ---------------------------------------------------------------------------

def test_heartbeat_timeout_triggers_recovery():
    log: list[str] = []
    ct = ChainTree(**_engine_kwargs(log))

    ct.start_test("to")
    ct.define_exception_handler("h")
    ct.define_main_column()
    ct.asm_turn_heartbeat_on(timeout=3)
    ct.asm_log_message("main start")
    ct.asm_halt()                    # never disables on its own; never sends heartbeat
    ct.end_main_column()
    ct.define_recovery_column()
    ct.asm_log_message("recovery")
    ct.end_recovery_column()
    ct.define_finalize_column()
    ct.asm_log_message("done")
    ct.end_finalize_column()
    ct.end_exception_handler()
    ct.end_test()

    ct.run(starting=["to"])

    assert log[0] == "main start"
    assert "recovery" in log
    assert "done" in log


# ---------------------------------------------------------------------------
# 6. DSL validation: missing column raises at end_exception_handler.
# ---------------------------------------------------------------------------

def test_dsl_missing_recovery_column_raises():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    ct.define_exception_handler("h")
    ct.define_main_column()
    ct.end_main_column()
    ct.define_finalize_column()
    ct.end_finalize_column()
    # Forgot RECOVERY.
    with pytest.raises(ValueError, match="RECOVERY"):
        ct.end_exception_handler()


def test_dsl_duplicate_main_column_raises():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    ct.define_exception_handler("h")
    ct.define_main_column()
    ct.end_main_column()
    with pytest.raises(RuntimeError, match="already defined"):
        ct.define_main_column()


def test_raise_exception_outside_handler_raises_at_runtime():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("v")
    # Place asm_raise_exception in a plain column with no enclosing
    # exception_handler — the one-shot will fail to find a catch ancestor
    # at runtime.
    ct.asm_raise_exception("OOPS")
    ct.asm_terminate()
    ct.end_test()
    with pytest.raises(RuntimeError, match="no exception_catch ancestor"):
        ct.run()
