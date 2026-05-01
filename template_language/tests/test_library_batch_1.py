"""Library batch 1: state_machine, time_gate, termination, container.

Each template gets:
  - a loadable / shape test (lazy-load + describe_template)
  - an op-list shape test (verifies the recorded sequence)
  - a runtime test (build + chain.run with stubbed clocks)
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

def _epoch_utc(hour: int) -> int:
    return int(datetime(2026, 5, 1, hour, 0, 0, tzinfo=timezone.utc).timestamp())


def _build_chain(op_list, *, hour_utc: int = 12, log: list[str] = None,
                 max_ticks: int = 6):
    counter = {"n": 0}
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda _: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: _epoch_utc(hour_utc),
        timezone=timezone.utc,
        logger=(log.append if log is not None else (lambda _: None)),
    )
    def capped(_dt):
        counter["n"] += 1
        if counter["n"] >= max_ticks:
            chain.engine["cfl_engine_flag"] = False
    chain.engine["sleep"] = capped
    return chain


# ======================================================================
# state_machine
# ======================================================================

def test_state_machine_loadable():
    d = describe_template("composites.chain_tree.state_machine")
    assert d["kind"] == "composite"
    assert d["engine"] == "chain_tree"
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["name"]["kind"] == "STRING" and by_name["name"]["required"]
    assert by_name["states"]["kind"] == "LIST" and by_name["states"]["required"]
    assert by_name["initial_state"]["kind"] == "STRING"
    assert by_name["auto_start"]["kind"] == "BOOL"
    assert by_name["auto_start"]["default"] is True


def test_state_machine_op_list_shape():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.state_machine",
            name="sm1",
            states=[
                ("idle",   lambda: ct.asm_log_message("idle msg")),
                ("active", lambda: ct.asm_log_message("active msg")),
            ],
            initial_state="idle",
        )
        ct.end_test()
    define_template("solution.shape", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.shape")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test",
        "define_state_machine",
        "define_state", "asm_log_message", "end_state",
        "define_state", "asm_log_message", "end_state",
        "end_state_machine",
        "end_test",
    ]


def test_state_machine_auto_start_false_passes_through():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.state_machine",
            name="sm2", states=[("only", lambda: None)],
            initial_state="only", auto_start=False,
        )
        ct.end_test()
    define_template("solution.as", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.as")
    sm_op = next(o for o in op_list.ops if o.method == "define_state_machine")
    assert sm_op.kwargs["auto_start"] is False


def test_state_machine_runtime_initial_state_runs():
    log: list[str] = []
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.state_machine",
            name="rt_sm",
            states=[
                ("idle",   lambda: ct.asm_log_message("idle-fired")),
                ("active", lambda: ct.asm_log_message("active-fired")),
            ],
            initial_state="idle",
        )
        ct.end_test()
    define_template("solution.rt", solution, kind="solution", engine="chain_tree")
    chain = _build_chain(use_template("solution.rt"), log=log)
    chain.run(starting=["kb"])
    assert "idle-fired" in log
    assert "active-fired" not in log


def test_state_machine_duplicate_state_in_recording_raises():
    """Recorder catches duplicate state names within the SM."""
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.state_machine",
            name="dup",
            states=[("a", lambda: None), ("a", lambda: None)],
            initial_state="a",
        )
        ct.end_test()
    define_template("solution.dup", solution, kind="solution", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("solution.dup")
    assert exc.value.code == Codes.DUPLICATE_NAME_IN_RECORDING
    assert exc.value.details["namespace"] == "state"


# ======================================================================
# time_gate
# ======================================================================

def test_time_gate_loadable():
    d = describe_template("composites.chain_tree.time_gate")
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["on_exit"]["kind"] == "STRING"
    assert by_name["on_exit"]["required"]


def test_time_gate_op_list_with_reset():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.time_gate",
            name="g", start={"hour": 9}, end={"hour": 17},
            body=lambda: ct.asm_log_message("inside"),
            on_exit="reset",
        )
        ct.end_test()
    define_template("solution.tg_r", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.tg_r")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test",
        "define_column",
        "asm_wait_until_in_time_window",
        "asm_log_message",
        "asm_wait_until_out_of_time_window",
        "asm_reset",
        "end_column",
        "end_test",
    ]


def test_time_gate_op_list_with_terminate():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.time_gate",
            name="g", start={"hour": 9}, end={"hour": 17},
            body=lambda: ct.asm_log_message("inside"),
            on_exit="terminate",
        )
        ct.end_test()
    define_template("solution.tg_t", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.tg_t")
    assert any(op.method == "asm_terminate" for op in op_list.ops)
    assert not any(op.method == "asm_reset" for op in op_list.ops)


def test_time_gate_invalid_on_exit_raises():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.time_gate",
            name="g", start={"hour": 9}, end={"hour": 17},
            body=lambda: None,
            on_exit="halt",   # invalid per locked vocabulary
        )
        ct.end_test()
    define_template("solution.tg_bad", solution, kind="solution", engine="chain_tree")
    with pytest.raises(ValueError):
        use_template("solution.tg_bad")


def test_time_gate_runtime_in_window_fires_body():
    log: list[str] = []
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.time_gate",
            name="g", start={"hour": 9}, end={"hour": 17},
            body=lambda: ct.asm_log_message("body-fired"),
            on_exit="terminate",
        )
        ct.end_test()
    define_template("solution.tg_rt", solution, kind="solution", engine="chain_tree")
    chain = _build_chain(use_template("solution.tg_rt"), hour_utc=12, log=log)
    chain.run(starting=["kb"])
    assert "body-fired" in log


# ======================================================================
# termination
# ======================================================================

def test_termination_loadable():
    d = describe_template("composites.chain_tree.termination")
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["delay_seconds"]["kind"] == "FLOAT"
    assert by_name["delay_seconds"]["required"]
    assert by_name["pre_log"]["nullable"] is True
    assert by_name["post_log"]["nullable"] is True


def test_termination_op_list_with_logs():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.termination",
            name="sd", delay_seconds=1.5,
            pre_log="going down", post_log="goodbye",
        )
        ct.end_test()
    define_template("solution.term", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.term")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test", "define_column",
        "asm_log_message", "asm_wait_time", "asm_log_message",
        "asm_terminate_system",
        "end_column", "end_test",
    ]


def test_termination_op_list_without_logs():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.termination",
            name="sd", delay_seconds=0.5,
        )
        ct.end_test()
    define_template("solution.term2", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.term2")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test", "define_column",
        "asm_wait_time",
        "asm_terminate_system",
        "end_column", "end_test",
    ]


def test_termination_runtime_terminates_engine():
    """Runtime: with a clock that advances on sleep, the wait elapses
    and asm_terminate_system fires, bringing the engine down."""
    log: list[str] = []
    clock = [0.0]
    def get_time(): return clock[0]
    def fake_sleep(dt): clock[0] += dt

    def solution():
        ct.start_test("kb_term")
        use_template(
            "composites.chain_tree.termination",
            name="sd", delay_seconds=1.0,
            pre_log="going down", post_log="bye",
        )
        ct.end_test()
    define_template("solution.term_rt", solution,
                    kind="solution", engine="chain_tree")

    op_list = use_template("solution.term_rt")
    chain = generate_code(
        op_list,
        tick_period=1.0,
        sleep=fake_sleep,
        get_time=get_time,
        get_wall_time=lambda: 0,
        logger=log.append,
    )
    chain.run(starting=["kb_term"])
    assert "going down" in log
    assert "bye" in log
    # Engine flag flipped → run() exited.
    assert chain.engine["cfl_engine_flag"] is False


# ======================================================================
# container
# ======================================================================

def test_container_loadable():
    d = describe_template("composites.chain_tree.container")
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["children"]["kind"] == "LIST"
    assert by_name["auto_start"]["default"] is True


def test_container_splices_children_in_order():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.container",
            name="seq",
            children=[
                lambda: ct.asm_log_message("a"),
                lambda: ct.asm_log_message("b"),
                lambda: ct.asm_log_message("c"),
            ],
        )
        ct.end_test()
    define_template("solution.cont", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.cont")
    log_args = [op.args[0] for op in op_list.ops if op.method == "asm_log_message"]
    assert log_args == ["a", "b", "c"]


def test_container_can_nest_use_template():
    """A child callable can itself call use_template — splice survives."""
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.container",
            name="outer",
            children=[
                lambda: use_template("leaves.chain_tree.print_hello"),
                lambda: ct.asm_log_message("after-hello"),
            ],
        )
        ct.end_test()
    define_template("solution.cont_nest", solution,
                    kind="solution", engine="chain_tree")
    op_list = use_template("solution.cont_nest")
    log_args = [op.args[0] for op in op_list.ops if op.method == "asm_log_message"]
    assert log_args == ["hello", "after-hello"]


def test_container_runtime_runs_children_in_order():
    log: list[str] = []
    def solution():
        ct.start_test("kb_c")
        use_template(
            "composites.chain_tree.container",
            name="rt",
            children=[
                lambda: ct.asm_log_message("first"),
                lambda: ct.asm_log_message("second"),
                lambda: ct.asm_terminate_system(),
            ],
        )
        ct.end_test()
    define_template("solution.cont_rt", solution,
                    kind="solution", engine="chain_tree")
    chain = _build_chain(use_template("solution.cont_rt"), log=log, max_ticks=3)
    chain.run(starting=["kb_c"])
    assert log.index("first") < log.index("second")
