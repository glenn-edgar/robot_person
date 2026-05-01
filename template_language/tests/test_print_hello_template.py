"""Tests for the print_hello leaf templates."""

from __future__ import annotations

from datetime import timezone

import pytest

from template_language import (
    ct,
    define_template,
    describe_template,
    generate_code,
    use_template,
)


def test_chain_tree_print_hello_loadable():
    d = describe_template("leaves.chain_tree.print_hello")
    assert d["kind"] == "leaf"
    assert d["engine"] == "chain_tree"
    assert d["slots"] == []
    assert "hello" in d["describe"].lower()


def test_chain_tree_print_hello_op_list():
    """No-slot leaf — body emits one asm_log_message op."""
    def solution():
        ct.start_test("kb")
        use_template("leaves.chain_tree.print_hello")
        ct.end_test()
    define_template("solution.hello", solution, kind="solution", engine="chain_tree")
    op_list = use_template("solution.hello")
    methods = [op.method for op in op_list.ops]
    assert methods == ["start_test", "asm_log_message", "end_test"]
    assert op_list.ops[1].args == ("hello",)


def test_chain_tree_print_hello_runs():
    log: list[str] = []
    def solution():
        ct.start_test("kb_hello")
        use_template("leaves.chain_tree.print_hello")
        ct.asm_terminate()
        ct.end_test()
    define_template("solution.run_hello", solution,
                    kind="solution", engine="chain_tree")

    op_list = use_template("solution.run_hello")
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda _: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: 0,
        timezone=timezone.utc,
        logger=log.append,
    )
    chain.run(starting=["kb_hello"])
    assert "hello" in log
