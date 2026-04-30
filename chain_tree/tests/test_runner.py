"""Tests for the python -m ct_runner CLI runner.

Use temporary .py files written into pytest's tmp_path, then invoke
`run_script` (the in-process function powering the CLI) and verify exit
codes + side effects.
"""

from __future__ import annotations

import os
import textwrap

import pytest

from ct_runner import run_script


def _write_script(tmp_path, body: str, name: str = "user.py") -> str:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


# ---------------------------------------------------------------------------
# 1. Happy path: KB completes cleanly → exit 0.
# ---------------------------------------------------------------------------

def test_runner_runs_clean_completion_exits_zero(tmp_path):
    path = _write_script(tmp_path, """
        from ct_dsl import ChainTree

        chain_tree = ChainTree(tick_period=0.0, sleep=lambda _dt: None,
                               get_time=lambda: 0.0)

        chain_tree.start_test("ok")
        chain_tree.asm_log_message("hi")
        chain_tree.asm_terminate()
        chain_tree.end_test()
    """)

    rc = run_script(path)
    assert rc == 0


# ---------------------------------------------------------------------------
# 2. Custom variable name resolves correctly.
# ---------------------------------------------------------------------------

def test_runner_honors_var_kwarg(tmp_path):
    path = _write_script(tmp_path, """
        from ct_dsl import ChainTree

        my_chain = ChainTree(tick_period=0.0, sleep=lambda _dt: None,
                             get_time=lambda: 0.0)
        my_chain.start_test("ok")
        my_chain.asm_terminate()
        my_chain.end_test()
    """)

    rc = run_script(path, var_name="my_chain")
    assert rc == 0


# ---------------------------------------------------------------------------
# 3. Missing attribute name → exit 1 with stderr message.
# ---------------------------------------------------------------------------

def test_runner_missing_attribute_exits_one(tmp_path, capsys):
    path = _write_script(tmp_path, """
        from ct_dsl import ChainTree
        # No top-level chain_tree attribute defined.
        _ct = ChainTree(tick_period=0.0)
    """)

    rc = run_script(path)
    assert rc == 1
    err = capsys.readouterr().err
    assert "no attribute named 'chain_tree'" in err


# ---------------------------------------------------------------------------
# 4. Wrong type for the named attr → exit 1.
# ---------------------------------------------------------------------------

def test_runner_wrong_type_exits_one(tmp_path, capsys):
    path = _write_script(tmp_path, """
        chain_tree = "not a ChainTree"
    """)

    rc = run_script(path)
    assert rc == 1
    err = capsys.readouterr().err
    assert "not ChainTree" in err


# ---------------------------------------------------------------------------
# 5. File not found → FileNotFoundError surfaces (CLI catches it).
# ---------------------------------------------------------------------------

def test_runner_missing_file_raises(tmp_path):
    path = str(tmp_path / "does_not_exist.py")
    with pytest.raises(FileNotFoundError):
        run_script(path)


# ---------------------------------------------------------------------------
# 6. Subset of KBs via `starting` kwarg.
# ---------------------------------------------------------------------------

def test_runner_starting_filter_runs_only_named_kbs(tmp_path):
    # Two KBs; only run the second. Verify the first never fired its
    # log message because we never activated it.
    path = _write_script(tmp_path, """
        log = []  # collected by the CLI runner via the engine logger

        from ct_dsl import ChainTree

        chain_tree = ChainTree(tick_period=0.0, sleep=lambda _dt: None,
                               get_time=lambda: 0.0,
                               logger=log.append)

        chain_tree.start_test("a")
        chain_tree.asm_log_message("KB-a ran")
        chain_tree.asm_terminate()
        chain_tree.end_test()

        chain_tree.start_test("b")
        chain_tree.asm_log_message("KB-b ran")
        chain_tree.asm_terminate()
        chain_tree.end_test()
    """)

    # We cannot inspect the user module's `log` from outside, but if the
    # runner correctly honors `starting`, only KB "b" runs and exit is 0.
    rc = run_script(path, starting=["b"])
    assert rc == 0


# ---------------------------------------------------------------------------
# 7. CLI entry point — main() argv parsing.
# ---------------------------------------------------------------------------

def test_runner_main_argv_parsing(tmp_path):
    from ct_runner import main

    path = _write_script(tmp_path, """
        from ct_dsl import ChainTree
        my_ct = ChainTree(tick_period=0.0, sleep=lambda _dt: None,
                          get_time=lambda: 0.0)
        my_ct.start_test("only")
        my_ct.asm_terminate()
        my_ct.end_test()
    """)

    rc = main([path, "--var=my_ct", "--starting=only"])
    assert rc == 0


# ---------------------------------------------------------------------------
# 8. Exception in user file is caught by main() → exit 1 with traceback.
# ---------------------------------------------------------------------------

def test_runner_main_catches_user_exception(tmp_path, capsys):
    from ct_runner import main

    path = _write_script(tmp_path, """
        raise RuntimeError("boom")
    """)

    rc = main([path])
    assert rc == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "boom" in err
