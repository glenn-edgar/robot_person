"""Controlled-node (client-server RPC) tests.

The server starts dormant (no children enabled) and listens for a request
event. The client sends a request high-pri at INIT, halts until response.
Server matches → enables children → on completion sends response → disables.
Client matches response → disables. Both done, KB completes.
"""

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
# 1. Round trip: request → server work → response → client disables.
# ---------------------------------------------------------------------------

def test_controlled_node_request_response_round_trip():
    log: list[str] = []
    captured_request: list[dict] = []
    captured_response: list[dict] = []

    request_port = {"event_id": "FLY_REQ", "schema": "fly_request"}
    response_port = {"event_id": "FLY_RESP", "schema": "fly_response"}

    def req_handler(handle, node, event_type, event_id, event_data):
        # disable_node fires the boolean with CFL_TERMINATE_EVENT during
        # teardown — filter so only real request events count.
        if event_id != request_port["event_id"]:
            return False
        captured_request.append(dict(event_data))
        return False

    def resp_handler(handle, node, event_type, event_id, event_data):
        if event_id != response_port["event_id"]:
            return False
        captured_response.append(dict(event_data))
        return False

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("REQ", req_handler)
    ct.add_boolean("RESP", resp_handler)

    ct.start_test("rpc")
    server = ct.define_controlled_server(
        "fly_service",
        request_port=request_port,
        response_port=response_port,
        handler_fn="REQ",
        response_data={"status": "ok"},
    )
    ct.asm_log_message("processing flight")
    ct.end_controlled_server()

    ct.asm_client_controlled_node(
        server,
        request_port=request_port,
        response_port=response_port,
        request_data={"distance": 100},
        response_handler="RESP",
    )
    ct.end_test()

    ct.run(starting=["rpc"])

    # Server saw the request payload.
    assert len(captured_request) == 1
    assert captured_request[0]["distance"] == 100
    assert captured_request[0]["_schema"] == "fly_request"
    # Server's children executed.
    assert "processing flight" in log
    # Client saw the response.
    assert len(captured_response) == 1
    assert captured_response[0]["status"] == "ok"
    assert captured_response[0]["_schema"] == "fly_response"
    # KB completed.
    assert ct.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 2. Server with no handler still works — children run, response sent.
# ---------------------------------------------------------------------------

def test_controlled_node_no_handler_still_responds():
    log: list[str] = []
    captured_response: list[dict] = []

    request_port = {"event_id": "PING"}
    response_port = {"event_id": "PONG"}

    def resp_handler(handle, node, event_type, event_id, event_data):
        if event_id != response_port["event_id"]:
            return False
        captured_response.append(dict(event_data))
        return False

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("RESP", resp_handler)

    ct.start_test("ping")
    server = ct.define_controlled_server(
        "pinger",
        request_port=request_port,
        response_port=response_port,
        response_data={"ok": True},
    )
    ct.asm_log_message("pong work")
    ct.end_controlled_server()

    ct.asm_client_controlled_node(
        server,
        request_port=request_port,
        response_port=response_port,
        response_handler="RESP",
    )
    ct.end_test()

    ct.run(starting=["ping"])

    assert "pong work" in log
    assert len(captured_response) == 1
    assert captured_response[0]["ok"] is True


# ---------------------------------------------------------------------------
# 3. Server children with multiple steps — response sent only after all done.
# ---------------------------------------------------------------------------

def test_server_waits_for_all_children_before_responding():
    log: list[str] = []
    response_seen_at = []

    rp = {"event_id": "WORK"}
    rsp = {"event_id": "DONE"}

    def resp_handler(handle, node, event_type, event_id, event_data):
        if event_id != rsp["event_id"]:
            return False
        # Capture log length at the moment the response arrived.
        response_seen_at.append(list(log))
        return False

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("RESP", resp_handler)

    ct.start_test("multi")
    server = ct.define_controlled_server("worker", rp, rsp,
                                          response_data={"finished": True})
    ct.asm_log_message("step 1")
    ct.asm_log_message("step 2")
    ct.asm_log_message("step 3")
    ct.end_controlled_server()
    ct.asm_client_controlled_node(server, rp, rsp, response_handler="RESP")
    ct.end_test()

    ct.run(starting=["multi"])

    assert len(response_seen_at) == 1
    # All three steps were logged BEFORE the client got the response.
    assert response_seen_at[0] == ["step 1", "step 2", "step 3"]


# ---------------------------------------------------------------------------
# 4. Client timeout never fires when the server responds within budget.
# ---------------------------------------------------------------------------

def test_client_timeout_does_not_fire_when_response_arrives():
    log: list[str] = []
    captured_response: list[dict] = []
    error_calls: list[dict] = []

    rp = {"event_id": "REQ"}
    rsp = {"event_id": "RESP"}

    def resp_handler(handle, node, event_type, event_id, event_data):
        if event_id != rsp["event_id"]:
            return False
        captured_response.append(dict(event_data))
        return False

    def on_timeout(handle, node):
        error_calls.append({"data": dict(node["data"].get("error_data") or {})})

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_boolean("RESP", resp_handler)
    ct.add_one_shot("ON_TIMEOUT", on_timeout)

    ct.start_test("rpc_t")
    server = ct.define_controlled_server("svc", rp, rsp, response_data={"ok": True})
    ct.asm_log_message("work")
    ct.end_controlled_server()
    ct.asm_client_controlled_node(
        server, rp, rsp,
        response_handler="RESP",
        timeout=10,                 # generous; should never fire
        error_fn="ON_TIMEOUT",
        error_data={"why": "noresp"},
    )
    ct.end_test()
    ct.run(starting=["rpc_t"])

    assert len(captured_response) == 1
    assert captured_response[0]["ok"] is True
    # error_fn must NOT have fired — the response arrived first.
    assert error_calls == []


# ---------------------------------------------------------------------------
# 5. Client timeout fires error_fn and TERMINATEs when no response arrives.
# ---------------------------------------------------------------------------

def test_client_timeout_terminates_parent_with_error_fn():
    log: list[str] = []
    error_calls: list[dict] = []

    # Mismatched ports: the client's request_port doesn't match the server's,
    # so the server never recognizes the request and never responds.
    client_rp = {"event_id": "CLIENT_REQ"}
    client_rsp = {"event_id": "CLIENT_RESP"}
    server_rp = {"event_id": "SERVER_REQ"}
    server_rsp = {"event_id": "SERVER_RESP"}

    def on_timeout(handle, node):
        error_calls.append({
            "tick": "fired",
            "data": dict(node["data"].get("error_data") or {}),
        })
        handle["blackboard"]["timed_out"] = True

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("ON_TIMEOUT", on_timeout)

    ct.start_test("rpc_to")
    server = ct.define_controlled_server(
        "deaf_svc", server_rp, server_rsp, response_data={"ok": True},
    )
    ct.asm_log_message("never runs")
    ct.end_controlled_server()
    ct.asm_client_controlled_node(
        server,
        request_port=client_rp,
        response_port=client_rsp,
        timeout=3,                  # 3 timer ticks then bail
        error_fn="ON_TIMEOUT",
        error_data={"why": "no_response"},
    )
    ct.end_test()
    ct.run(starting=["rpc_to"])

    # error_fn fired exactly once with the configured error_data.
    assert len(error_calls) == 1
    assert error_calls[0]["data"]["why"] == "no_response"
    bb = ct.engine["kbs"]["rpc_to"]["blackboard"]
    assert bb["timed_out"] is True
    # Parent (test root) terminated; KB pruned.
    assert ct.engine["active_kbs"] == []
    # The server's child never ran — no request matched.
    assert "never runs" not in log


# ---------------------------------------------------------------------------
# 6. Client timeout with reset_flag=True RESETs the parent (retries the call).
# ---------------------------------------------------------------------------

def test_client_timeout_reset_flag_retries_until_terminate():
    log: list[str] = []
    error_calls: list[int] = []

    client_rp = {"event_id": "CLIENT_REQ"}
    client_rsp = {"event_id": "CLIENT_RESP"}
    server_rp = {"event_id": "SERVER_REQ"}
    server_rsp = {"event_id": "SERVER_RESP"}

    def on_timeout(handle, node):
        error_calls.append(1)
        # After the second timeout, signal to terminate the whole engine
        # so the test doesn't loop forever (RESET would otherwise retry
        # indefinitely against the unresponsive server).
        if len(error_calls) >= 2:
            handle["engine"]["cfl_engine_flag"] = False

    ct = ChainTree(**_engine_kwargs(log))
    ct.add_one_shot("ON_TIMEOUT", on_timeout)

    ct.start_test("rpc_rst")
    server = ct.define_controlled_server(
        "deaf_svc", server_rp, server_rsp, response_data={"ok": True},
    )
    ct.asm_log_message("server work")
    ct.end_controlled_server()
    ct.asm_client_controlled_node(
        server,
        request_port=client_rp,
        response_port=client_rsp,
        timeout=2,                  # short, retries quickly
        error_fn="ON_TIMEOUT",
        reset_flag=True,            # CFL_RESET on timeout
    )
    ct.end_test()
    ct.run(starting=["rpc_rst"])

    # Two timeouts before the on_timeout fn flipped the engine flag off.
    assert len(error_calls) == 2
