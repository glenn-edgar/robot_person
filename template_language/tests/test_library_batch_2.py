"""Library batch 2: try_till_pass, try_till_fail, mark_link.

The two sequence-til templates pass the sequence RecRef to their
children as a one-arg callable; children typically use the RecRef to
attach a `mark_link` leaf that decides pass/fail at INIT.
"""

from __future__ import annotations

from datetime import timezone

import pytest

from template_language import (
    Codes,
    Kind,
    RecRef,
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

def _build_chain(op_list, *, log: list[str] = None, max_ticks: int = 10):
    counter = {"n": 0}
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda _: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: 0,
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
# mark_link
# ======================================================================

def test_mark_link_loadable():
    d = describe_template("leaves.chain_tree.mark_link")
    assert d["kind"] == "leaf"
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["seq"]["kind"] == "RECREF"
    assert by_name["seq"]["required"]
    assert by_name["name"]["kind"] == "STRING"
    assert by_name["boolean_function"]["kind"] == "ENGINE_BOOLEAN"
    assert by_name["boolean_function_data"]["kind"] == "DICT"
    assert by_name["boolean_function_data"]["nullable"] is True


def test_mark_link_op_list_records_add_boolean_then_mark():
    """The leaf records two ops: add_boolean (registers the predicate)
    then asm_mark_sequence_if (the actual leaf)."""
    pred = lambda h, n, et, eid, ed: True

    def solution():
        ct.start_test("kb")
        seq_ref = ct.define_sequence_til_pass("seq")
        use_template(
            "leaves.chain_tree.mark_link",
            seq=seq_ref,
            name="my_check",
            boolean_function=pred,
            boolean_function_data={"k": 1},
        )
        ct.end_sequence_til_pass()
        ct.end_test()
    define_template("solution.ml", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.ml")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test",
        "define_sequence_til_pass",
        "add_boolean",                    # registers the predicate
        "asm_mark_sequence_if",           # the leaf itself
        "end_sequence_til_pass",
        "end_test",
    ]
    # The data flows into both true_data and false_data slots.
    mark_op = next(o for o in op_list.ops if o.method == "asm_mark_sequence_if")
    assert mark_op.kwargs["true_data"] == {"k": 1}
    assert mark_op.kwargs["false_data"] == {"k": 1}


def test_mark_link_seq_required_kind_recref():
    """Passing a non-RecRef to the seq slot → SLOT_KIND_MISMATCH."""
    def solution():
        use_template(
            "leaves.chain_tree.mark_link",
            seq="not-a-recref",
            name="x",
            boolean_function=lambda h, n, et, eid, ed: True,
        )
    define_template("solution.bad", solution, kind="solution", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        use_template("solution.bad")
    assert exc.value.code == Codes.SLOT_KIND_MISMATCH


# ======================================================================
# try_till_pass / try_till_fail
# ======================================================================

def test_try_till_pass_loadable():
    d = describe_template("composites.chain_tree.try_till_pass")
    assert d["kind"] == "composite"
    slot_names = {s["name"] for s in d["slots"]}
    assert slot_names == {"name", "children", "finalize_fn"}
    # auto_start intentionally absent.


def test_try_till_fail_loadable():
    d = describe_template("composites.chain_tree.try_till_fail")
    slot_names = {s["name"] for s in d["slots"]}
    assert slot_names == {"name", "children", "finalize_fn"}


def test_try_till_pass_op_list_passes_seq_to_children():
    """Each child is invoked with the sequence RecRef. Children that use
    it (e.g. mark_link) attach to that specific sequence."""
    captured_seqs = []

    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.try_till_pass",
            name="attempts",
            children=[
                lambda seq: captured_seqs.append(seq) or ct.asm_log_message("a"),
                lambda seq: captured_seqs.append(seq) or ct.asm_log_message("b"),
            ],
        )
        ct.end_test()
    define_template("solution.ttp", solution, kind="solution", engine="chain_tree")
    use_template("solution.ttp")

    # Both children received the same RecRef (the sequence's).
    assert len(captured_seqs) == 2
    assert isinstance(captured_seqs[0], RecRef)
    assert captured_seqs[0] is captured_seqs[1]


def test_try_till_pass_op_list_shape_with_mark_link():
    """End-to-end shape: try_till_pass + child using mark_link."""
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.try_till_pass",
            name="attempts",
            children=[
                lambda seq: use_template(
                    "leaves.chain_tree.mark_link",
                    seq=seq, name="check_a",
                    boolean_function=lambda h, n, et, eid, ed: True,
                    boolean_function_data={"step": "a"},
                ),
                lambda seq: use_template(
                    "leaves.chain_tree.mark_link",
                    seq=seq, name="check_b",
                    boolean_function=lambda h, n, et, eid, ed: False,
                    boolean_function_data={"step": "b"},
                ),
            ],
        )
        ct.end_test()
    define_template("solution.ttp_ml", solution,
                    kind="solution", engine="chain_tree")
    op_list = use_template("solution.ttp_ml")
    methods = [op.method for op in op_list.ops]
    assert methods == [
        "start_test",
        "define_sequence_til_pass",
        "add_boolean", "asm_mark_sequence_if",   # check_a child
        "add_boolean", "asm_mark_sequence_if",   # check_b child
        "end_sequence_til_pass",
        "end_test",
    ]


def test_try_till_fail_op_list_uses_til_fail_primitive():
    def solution():
        ct.start_test("kb")
        use_template(
            "composites.chain_tree.try_till_fail",
            name="checks",
            children=[lambda seq: ct.asm_log_message("x")],
        )
        ct.end_test()
    define_template("solution.ttf", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.ttf")
    methods = [op.method for op in op_list.ops]
    assert "define_sequence_til_fail" in methods
    assert "end_sequence_til_fail" in methods
    assert "define_sequence_til_pass" not in methods


def test_try_till_pass_with_finalize_fn_passes_through():
    fn = lambda handle, node: None
    def solution():
        ct.start_test("kb")
        ct.add_one_shot("FINALIZE_FN", fn)
        use_template(
            "composites.chain_tree.try_till_pass",
            name="x",
            children=[lambda seq: ct.asm_log_message("y")],
            finalize_fn="FINALIZE_FN",
        )
        ct.end_test()
    define_template("solution.fin", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.fin")
    seq_op = next(o for o in op_list.ops if o.method == "define_sequence_til_pass")
    assert seq_op.kwargs.get("finalize_fn") == "FINALIZE_FN"


# ======================================================================
# Integration: mark_link inside try_till_pass at runtime
# ======================================================================

def test_mark_link_passes_sequence_when_predicate_true():
    """Runtime: the predicate returns True → sequence_til_pass passes
    on first attempt and short-circuits remaining attempts.

    Each child of a sequence_til_* must mark pass/fail (engine contract);
    we use one mark_link per attempt-column. The first attempt's
    predicate returns True → the second attempt is skipped."""
    log: list[str] = []
    second_attempt_predicate_calls = []

    def solution():
        ct.start_test("kb_pass")
        ct.define_column("outer")
        use_template(
            "composites.chain_tree.try_till_pass",
            name="login_seq",
            children=[
                lambda seq: use_template(
                    "leaves.chain_tree.mark_link",
                    seq=seq, name="attempt_1",
                    boolean_function=lambda h, n, et, eid, ed: True,
                    boolean_function_data={"attempt": 1},
                ),
                lambda seq: use_template(
                    "leaves.chain_tree.mark_link",
                    seq=seq, name="attempt_2",
                    boolean_function=(
                        lambda h, n, et, eid, ed:
                        second_attempt_predicate_calls.append(True) or True
                    ),
                    boolean_function_data={"attempt": 2},
                ),
            ],
        )
        ct.asm_log_message("after-sequence")
        ct.end_column()
        ct.end_test()
    define_template("solution.run_pass", solution,
                    kind="solution", engine="chain_tree")

    chain = _build_chain(use_template("solution.run_pass"), log=log)
    chain.run(starting=["kb_pass"])

    # First attempt passed → second attempt's predicate never ran.
    assert second_attempt_predicate_calls == []
    # Outer column continued to next sibling.
    assert "after-sequence" in log


def test_mark_link_predicate_runs_for_each_attempt():
    """All-fail walk: every attempt's predicate fires before the
    sequence as a whole reports fail."""
    predicate_calls = []

    def solution():
        ct.start_test("kb_fail")
        ct.define_column("outer")
        use_template(
            "composites.chain_tree.try_till_pass",
            name="login_seq",
            children=[
                # `i=i` default binds the loop variable on each iteration —
                # otherwise all lambdas would close over the final `i=3`.
                (lambda seq, i=i: use_template(
                    "leaves.chain_tree.mark_link",
                    seq=seq, name=f"attempt_{i}",
                    boolean_function=(
                        lambda h, n, et, eid, ed, i=i:
                        predicate_calls.append(i) or False
                    ),
                    boolean_function_data={"attempt": i},
                ))
                for i in (1, 2, 3)
            ],
        )
        ct.end_column()
        ct.end_test()
    define_template("solution.run_fail", solution,
                    kind="solution", engine="chain_tree")

    chain = _build_chain(use_template("solution.run_fail"))
    chain.run(starting=["kb_fail"])

    # All three predicates ran in order — sequence_til_pass exhausted.
    assert predicate_calls == [1, 2, 3]
