"""Tests for ChainTree.validate() — build-time structural + reference checks.

Validate is run automatically by `run()`, but it's also callable on its
own so users can fail fast at construction time. Each test exercises one
class of error:

  - unresolved fn-name reference
  - exception_handler with wrong child count
  - state_machine with mismatched child / state_name
  - controlled_server with no children
  - sequence_til with no marks
  - cross-ref pointing to wrong-typed node
"""

from __future__ import annotations

import pytest

import ct_runtime as ct
from ct_dsl import ChainTree


def _engine_kwargs():
    return dict(tick_period=0.0, sleep=lambda _dt: None, get_time=lambda: 0.0)


# ---------------------------------------------------------------------------
# 1. Happy path: a clean DSL build passes validation.
# ---------------------------------------------------------------------------

def test_validate_passes_clean_build():
    chain = ChainTree(**_engine_kwargs())
    chain.start_test("ok")
    chain.asm_log_message("hi")
    chain.asm_terminate()
    chain.end_test()
    chain.validate()  # no exception


# ---------------------------------------------------------------------------
# 2. Unresolved fn name.
# ---------------------------------------------------------------------------

def test_validate_catches_unresolved_fn_reference():
    chain = ChainTree(**_engine_kwargs())
    # Hand-roll a node referencing an unregistered main fn.
    bad = ct.make_node(name="bad", main_fn_name="NOT_REGISTERED_MAIN")
    root = ct.make_node(name="root", main_fn_name="CFL_COLUMN_MAIN")
    ct.link_children(root, [bad])
    kb = ct.new_kb("k", root)
    ct.add_kb(chain.engine, kb)

    with pytest.raises(LookupError, match="NOT_REGISTERED_MAIN"):
        chain.validate()


# ---------------------------------------------------------------------------
# 3. Exception_handler with wrong child count.
# ---------------------------------------------------------------------------

def test_validate_catches_exception_handler_wrong_children():
    """The DSL's `end_exception_handler` enforces 3-children at build time,
    so to exercise validate's check directly we hand-roll a malformed
    catch and register it as a fresh KB.
    """
    chain = ChainTree(**_engine_kwargs())
    bad_catch = ct.make_node(
        name="bad_eh",
        main_fn_name="CFL_EXCEPTION_CATCH_MAIN",
        init_fn_name="CFL_EXCEPTION_CATCH_INIT",
        term_fn_name="CFL_EXCEPTION_CATCH_TERM",
        data={"boolean_filter_fn": "CFL_NULL", "logging_fn": "CFL_NULL"},
    )
    only_main = ct.make_node(
        name="m", main_fn_name="CFL_COLUMN_MAIN", init_fn_name="CFL_COLUMN_INIT",
        term_fn_name="CFL_COLUMN_TERM",
        data={"auto_start": True, "column_data": None},
    )
    ct.link_children(bad_catch, [only_main])
    root = ct.make_node(
        name="root", main_fn_name="CFL_COLUMN_MAIN",
        init_fn_name="CFL_COLUMN_INIT", term_fn_name="CFL_COLUMN_TERM",
        data={"auto_start": True, "column_data": None},
    )
    ct.link_children(root, [bad_catch])
    kb = ct.new_kb("ex", root)
    ct.add_kb(chain.engine, kb)

    with pytest.raises(ValueError, match="exception_handler.*expected 3"):
        chain.validate()


# ---------------------------------------------------------------------------
# 4. Controlled_server with no children.
# ---------------------------------------------------------------------------

def test_validate_catches_controlled_server_with_no_children():
    chain = ChainTree(**_engine_kwargs())
    chain.start_test("rpc")
    server = ct.make_node(
        name="empty_server",
        main_fn_name="CFL_CONTROLLED_SERVER_MAIN",
        boolean_fn_name="CFL_NULL",
        data={
            "request_port": {"event_id": "REQ"},
            "response_port": {"event_id": "RESP"},
            "client_node": None,
            "response_data": {},
        },
    )
    ct.link_children(chain._frames[-1]["node"], [server])
    chain.end_test()

    with pytest.raises(ValueError, match="controlled_server.*no work children"):
        chain.validate()


# ---------------------------------------------------------------------------
# 5. sequence_til with no marks.
# ---------------------------------------------------------------------------

def test_validate_catches_sequence_til_without_marks():
    chain = ChainTree(**_engine_kwargs())
    chain.start_test("seq")
    chain.define_sequence_til_pass("p")
    # No mark leaves; only a log.
    chain.asm_log_message("step")
    chain.end_sequence_til_pass()
    chain.end_test()

    with pytest.raises(ValueError, match="sequence_til.*no asm_mark_sequence"):
        chain.validate()


# ---------------------------------------------------------------------------
# 6. sm_node ref pointing to a non-state-machine node → caught.
# ---------------------------------------------------------------------------

def test_validate_catches_sm_node_ref_to_wrong_type():
    chain = ChainTree(**_engine_kwargs())
    # Build a tree where asm_change_state's sm_node points to a column,
    # not a state_machine.
    chain.start_test("bad_sm")
    fake_sm = ct.make_node(
        name="not_an_sm",
        main_fn_name="CFL_COLUMN_MAIN",
        init_fn_name="CFL_COLUMN_INIT",
        term_fn_name="CFL_COLUMN_TERM",
        data={"auto_start": True, "column_data": None},
    )
    ct.link_children(chain._frames[-1]["node"], [fake_sm])
    chain.asm_change_state.__func__  # ensure method exists
    bad_change = ct.make_node(
        name="change",
        main_fn_name="CFL_DISABLE",
        init_fn_name="CFL_CHANGE_STATE",
        boolean_fn_name="CFL_NULL",
        data={"sm_node": fake_sm, "new_state": "wherever"},
    )
    ct.link_children(chain._frames[-1]["node"], [bad_change])
    chain.end_test()

    with pytest.raises(ValueError, match="sm_node.*not a state machine"):
        chain.validate()


# ---------------------------------------------------------------------------
# 7. server_node ref pointing to a non-server → caught.
# ---------------------------------------------------------------------------

def test_validate_catches_server_node_ref_to_wrong_type():
    chain = ChainTree(**_engine_kwargs())
    chain.start_test("bad_rpc")
    fake_server = ct.make_node(
        name="not_a_server",
        main_fn_name="CFL_COLUMN_MAIN",
        init_fn_name="CFL_COLUMN_INIT",
        term_fn_name="CFL_COLUMN_TERM",
        data={"auto_start": True, "column_data": None},
    )
    ct.link_children(chain._frames[-1]["node"], [fake_server])
    bad_client = ct.make_node(
        name="client",
        main_fn_name="CFL_CONTROLLED_CLIENT_MAIN",
        init_fn_name="CFL_CONTROLLED_CLIENT_INIT",
        term_fn_name="CFL_CONTROLLED_CLIENT_TERM",
        boolean_fn_name="CFL_NULL",
        data={
            "server_node": fake_server,
            "request_port": {"event_id": "X"},
            "response_port": {"event_id": "Y"},
            "request_data": {},
            "timeout": 0,
            "timeout_event_id": "CFL_TIMER_EVENT",
            "timeout_count": 0,
            "error_fn": "CFL_NULL",
            "error_data": None,
            "reset_flag": False,
        },
    )
    ct.link_children(chain._frames[-1]["node"], [bad_client])
    chain.end_test()

    with pytest.raises(ValueError, match="server_node.*not a controlled server"):
        chain.validate()


# ---------------------------------------------------------------------------
# 8. run() still calls validate() — unresolved fn surfaces before any tick.
# ---------------------------------------------------------------------------

def test_run_invokes_validate_before_main_loop():
    chain = ChainTree(**_engine_kwargs())
    bad = ct.make_node(name="bad", main_fn_name="UNREGISTERED")
    root = ct.make_node(name="root", main_fn_name="CFL_COLUMN_MAIN")
    ct.link_children(root, [bad])
    kb = ct.new_kb("k", root)
    ct.add_kb(chain.engine, kb)

    with pytest.raises(LookupError, match="UNREGISTERED"):
        chain.run(starting=["k"])
