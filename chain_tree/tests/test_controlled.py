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
