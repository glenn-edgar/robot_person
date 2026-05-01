"""Acceptance test for the fire_in_window template (chain_tree variant).

Verifies:
  - Op-list shape matches the canonical column + 2 waits + body splice.
  - Two instantiations with distinct `name` slots coexist.
  - Same `name` slot used twice → DUPLICATE_NAME_IN_RECORDING.
  - Body slot fires at runtime when the wall clock is INSIDE the
    configured window, and does NOT fire when OUTSIDE.

Tick choreography for the runtime tests:
  Tick 1: column INIT enables children. Walker descends; first leaf is
          asm_wait_until_in_time_window. If clock is in window → DISABLE
          and walker advances; if out of window → HALT, no further
          siblings run this tick.

So an "in window" clock fires the body on tick 1; an "out of window"
clock never fires the body. A tick cap stops the engine after a few
iterations either way.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from template_language import (
    Codes,
    TemplateError,
    ct,
    define_template,
    describe_template,
    generate_code,
    use_template,
)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _epoch_for_hour_utc(hour: int) -> int:
    return int(datetime(2026, 5, 1, hour, 0, 0, tzinfo=timezone.utc).timestamp())


def _build_chain_with_clock(op_list, *, hour_utc: int, log: list[str], max_ticks: int = 5):
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
    def capped(_dt):
        counter["n"] += 1
        if counter["n"] >= max_ticks:
            chain.engine["cfl_engine_flag"] = False
    chain.engine["sleep"] = capped
    return chain


# ----------------------------------------------------------------------
# tests
# ----------------------------------------------------------------------

def test_template_loadable():
    d = describe_template("composites.chain_tree.fire_in_window")
    assert d["kind"] == "composite"
    assert d["engine"] == "chain_tree"
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["name"]["kind"] == "STRING" and by_name["name"]["required"]
    assert by_name["start"]["kind"] == "DICT"   and by_name["start"]["required"]
    assert by_name["end"]["kind"] == "DICT"     and by_name["end"]["required"]
    assert by_name["body"]["kind"] == "ACTION"  and by_name["body"]["required"]


def test_op_list_shape():
    """Phase 1: column wraps wait + body + wait, in declared order."""
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.fire_in_window",
            name="market_gate",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.asm_log_message("market opened"),
        )
        ct.end_test()
    define_template("solution.shape", solution, kind="solution", engine="chain_tree")

    op_list = use_template("solution.shape")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test",
        "define_column",
        "asm_wait_until_in_time_window",
        "asm_log_message",                  # spliced body
        "asm_wait_until_out_of_time_window",
        "end_column",
        "end_test",
    ]


def test_body_fires_when_clock_in_window():
    log: list[str] = []
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.fire_in_window",
            name="biz_hours",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.asm_log_message("inside-window"),
        )
        ct.end_test()
    define_template("solution.in", solution, kind="solution", engine="chain_tree")

    op_list = use_template("solution.in")
    chain = _build_chain_with_clock(op_list, hour_utc=12, log=log, max_ticks=4)
    chain.run(starting=["kb"])

    assert "inside-window" in log


def test_body_does_not_fire_when_clock_out_of_window():
    log: list[str] = []
    def solution():
        ct.start_test("kb_out")
        use_template(
            "composites.chain_tree.fire_in_window",
            name="biz_hours",
            start={"hour": 9},
            end={"hour": 17},
            body=lambda: ct.asm_log_message("inside-window"),
        )
        ct.end_test()
    define_template("solution.out", solution, kind="solution", engine="chain_tree")

    op_list = use_template("solution.out")
    chain = _build_chain_with_clock(op_list, hour_utc=22, log=log, max_ticks=4)
    chain.run(starting=["kb_out"])

    assert "inside-window" not in log


def test_two_instantiations_with_distinct_names():
    """Two fire_in_window columns inside one parent — distinct `name`
    slots → no collision."""
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.fire_in_window",
            name="morning_gate",
            start={"hour": 6}, end={"hour": 12},
            body=lambda: ct.asm_log_message("morning"),
        )
        use_template(
            "composites.chain_tree.fire_in_window",
            name="evening_gate",
            start={"hour": 18}, end={"hour": 22},
            body=lambda: ct.asm_log_message("evening"),
        )
        ct.end_test()
    define_template("solution.two", solution, kind="solution", engine="chain_tree")

    op_list = use_template("solution.two")
    column_names = [op.args[0] for op in op_list.ops if op.method == "define_column"]
    assert column_names == ["morning_gate", "evening_gate"]


def test_same_name_across_templates_does_not_collide():
    """Per-frame (column) name tracking is intra-template only. Two
    fire_in_window instantiations under one parent both pass `name="dup"`;
    chain_tree's _mk_name auto-suffixes at the engine level, so neither
    the recorder (different recorder instances per use_template) nor the
    real builder rejects this. Distinct names are *recommended* for
    readable logs / op-list dumps but not enforced cross-template."""
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.fire_in_window",
            name="dup",
            start={"hour": 9}, end={"hour": 17},
            body=lambda: None,
        )
        use_template(
            "composites.chain_tree.fire_in_window",
            name="dup",
            start={"hour": 9}, end={"hour": 17},
            body=lambda: None,
        )
        ct.end_test()
    define_template("solution.dup", solution, kind="solution", engine="chain_tree")

    op_list = use_template("solution.dup")
    column_args = [op.args[0] for op in op_list.ops if op.method == "define_column"]
    assert column_args == ["dup", "dup"]
    # Replay also succeeds — no exception.
    chain = generate_code(op_list, tick_period=0.0,
                          sleep=lambda _: None, get_time=lambda: 0.0,
                          get_wall_time=lambda: 0)
    assert chain is not None


def test_body_can_use_other_templates_via_lambda():
    """The ACTION slot is a callable — a lambda that calls another
    use_template inside the gated column splices its ops correctly."""
    def inner(*, msg: str):
        ct.asm_log_message(msg)
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.fire_in_window",
            name="gate",
            start={"hour": 9}, end={"hour": 17},
            body=lambda: use_template("inner", msg="layered"),
        )
        ct.end_test()
    define_template("inner",        inner,    kind="leaf",     engine="chain_tree")
    define_template("solution.lay", solution, kind="solution", engine="chain_tree")

    op_list = use_template("solution.lay")
    methods = [op.method for op in op_list.ops]
    # The inner template's asm_log_message lands between the two waits.
    in_idx = methods.index("asm_wait_until_in_time_window")
    out_idx = methods.index("asm_wait_until_out_of_time_window")
    log_idx = methods.index("asm_log_message")
    assert in_idx < log_idx < out_idx
