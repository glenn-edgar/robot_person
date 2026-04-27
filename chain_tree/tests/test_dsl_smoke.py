"""End-to-end DSL smoke tests.

Build trees with the fluent ChainTree builder, run the engine, observe
side effects via captured logger output and blackboard writes.
"""

from __future__ import annotations

import pytest

from ct_dsl import ChainTree


def _logged():
    """Build a (logger_callable, log_list) pair for capturing log output."""
    log: list[str] = []
    return log.append, log


def _stub_engine_kwargs(log):
    return dict(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )


# ---------------------------------------------------------------------------
# 1. Trivial: log + terminate.
# ---------------------------------------------------------------------------

def test_log_then_terminate():
    log: list[str] = []
    ct = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )
    ct.start_test("t")
    ct.asm_log_message("hello")
    ct.asm_log_message("world")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["t"])

    assert log == ["hello", "world"]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 2. Wait time: with a monotonically advancing clock, leaves halt then
#    advance on the right tick.
# ---------------------------------------------------------------------------

def test_wait_time_advances_on_elapsed_clock():
    log: list[str] = []
    clock = [0.0]

    def get_time():
        return clock[0]

    def fake_sleep(dt):
        clock[0] += dt

    ct = ChainTree(
        tick_period=1.0,                # sleep advances the fake clock by 1s
        sleep=fake_sleep,
        get_time=get_time,
        logger=log.append,
    )
    ct.start_test("t")
    ct.asm_log_message("before")
    ct.asm_wait_time(2.0)               # halt for 2 ticks (~2s)
    ct.asm_log_message("after")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["t"])

    # before should be logged on the first tick; after on the third
    # (init at t=0, ticks at t=1, 2 still halting; t=2 elapsed >= 2 → disable
    # then "after" + terminate on the same tick).
    assert log == ["before", "after"]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 3. Nested column: leaves inside a sub-column are still visited in order.
# ---------------------------------------------------------------------------

def test_nested_column_ordering():
    log: list[str] = []
    ct = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )
    ct.start_test("t")
    ct.asm_log_message("outer-1")
    ct.define_column("inner")
    ct.asm_log_message("inner-1")
    ct.asm_log_message("inner-2")
    ct.end_column()
    ct.asm_log_message("outer-2")
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["t"])

    assert log == ["outer-1", "inner-1", "inner-2", "outer-2"]


# ---------------------------------------------------------------------------
# 4. User-registered one-shot fires with KB blackboard access.
# ---------------------------------------------------------------------------

def test_user_one_shot_with_blackboard():
    log: list[str] = []
    captured = {}

    def my_action(handle, node):
        handle["blackboard"]["touched"] = True
        captured["data"] = dict(node["data"])
        captured["kb_name"] = handle["name"]

    ct = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )
    ct.add_one_shot("MY_ACTION", my_action, description="test action")

    ct.start_test("t")
    ct.asm_one_shot("MY_ACTION", {"value": 42})
    ct.asm_terminate()
    ct.end_test()

    ct.run(starting=["t"])

    kb = ct.engine["kbs"]["t"]
    assert kb["blackboard"]["touched"] is True
    assert captured["data"] == {"value": 42}
    assert captured["kb_name"] == "t"


# ---------------------------------------------------------------------------
# 5. Multi-KB: two tests in the same engine, both run to completion.
# ---------------------------------------------------------------------------

def test_multi_kb():
    log: list[str] = []
    ct = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )

    ct.start_test("a")
    ct.asm_log_message("a-1")
    ct.asm_terminate()
    ct.end_test()

    ct.start_test("b")
    ct.asm_log_message("b-1")
    ct.asm_terminate()
    ct.end_test()

    ct.run()  # starting defaults to all KBs

    # Both KBs should have logged once. Order between KBs is per-tick fan-out
    # (a then b in registration order), so the exact log order is deterministic.
    assert log == ["a-1", "b-1"]
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 6. Stack-balance failures raise immediately.
# ---------------------------------------------------------------------------

def test_end_test_without_start():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    with pytest.raises(RuntimeError):
        ct.end_test()


def test_end_column_in_test_frame():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("t")
    with pytest.raises(RuntimeError):
        ct.end_column()


def test_duplicate_test_name():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("t")
    ct.asm_terminate()
    ct.end_test()
    with pytest.raises(ValueError):
        ct.start_test("t")


def test_run_with_open_frame():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("t")
    ct.asm_terminate()
    # forgot end_test
    with pytest.raises(RuntimeError):
        ct.run()


def test_unresolved_one_shot_at_run():
    ct = ChainTree(tick_period=0.0, sleep=lambda _: None, get_time=lambda: 0.0)
    ct.start_test("t")
    ct.asm_one_shot("DOES_NOT_EXIST")
    ct.asm_terminate()
    ct.end_test()
    with pytest.raises(LookupError):
        ct.run()
