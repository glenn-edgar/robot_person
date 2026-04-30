"""Streaming-aware assertion (asm_streaming_verify).

The verify leaf matches an inport like sink/tap; on each matching packet
it calls the predicate boolean. True passes (CONTINUE); False fires the
optional error one-shot and escalates RESET (retry parent) or TERMINATE
(give up). Non-matching events pass through transparently.
"""

from __future__ import annotations

from ct_dsl import ChainTree


def _bounded_engine(log, max_ticks=4):
    sleep_calls = [0]
    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )

    def stop_after(_dt):
        sleep_calls[0] += 1
        if sleep_calls[0] >= max_ticks:
            chain.engine["active_kbs"].clear()

    chain.engine["sleep"] = stop_after
    return chain


# ---------------------------------------------------------------------------
# 1. Predicate True on matching packet → CONTINUE; KB tickers idle.
# ---------------------------------------------------------------------------

def test_verify_predicate_true_passes_through():
    log: list[str] = []
    error_calls: list[dict] = []
    received: list[float] = []
    port = {"event_id": "READING", "schema": "celsius"}

    def in_range(handle, node, event_type, event_id, event_data):
        if event_id != port["event_id"]:
            return False
        return 0.0 <= (event_data or {}).get("v", -1) <= 100.0

    def downstream_sink(handle, node, event_type, event_id, event_data):
        if event_id != port["event_id"]:
            return False
        received.append((event_data or {})["v"])
        return False

    def on_fail(handle, node):
        error_calls.append(dict(node["data"].get("error_data") or {}))

    chain = _bounded_engine(log)
    chain.add_boolean("IN_RANGE", in_range)
    chain.add_boolean("SINK", downstream_sink)
    chain.add_one_shot("ON_FAIL", on_fail)

    root = chain.start_test("v")
    chain.asm_streaming_verify(port, "IN_RANGE", error_fn="ON_FAIL")
    chain.asm_streaming_sink(port, "SINK")
    chain.asm_emit_streaming(root, port, {"v": 22.5})
    chain.asm_emit_streaming(root, port, {"v": 60.0})
    chain.end_test()
    chain.run(starting=["v"])

    # Both packets passed; sink saw both.
    assert received == [22.5, 60.0]
    # No assertion failures fired.
    assert error_calls == []


# ---------------------------------------------------------------------------
# 2. Predicate False on matching packet → error_fn fires + parent terminates.
# ---------------------------------------------------------------------------

def test_verify_predicate_false_fires_error_and_terminates():
    log: list[str] = []
    error_calls: list[dict] = []
    received: list[float] = []
    port = {"event_id": "READING"}

    def in_range(handle, node, event_type, event_id, event_data):
        if event_id != port["event_id"]:
            return False
        return 0.0 <= (event_data or {}).get("v", -1) <= 100.0

    def sink(handle, node, event_type, event_id, event_data):
        if event_id != port["event_id"]:
            return False
        received.append((event_data or {})["v"])
        return False

    def on_fail(handle, node):
        error_calls.append({"data": dict(node["data"].get("error_data") or {})})

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )
    chain.add_boolean("IN_RANGE", in_range)
    chain.add_boolean("SINK", sink)
    chain.add_one_shot("ON_FAIL", on_fail)

    root = chain.start_test("v")
    chain.asm_streaming_verify(
        port, "IN_RANGE",
        error_fn="ON_FAIL",
        error_data={"why": "out_of_range"},
    )
    chain.asm_streaming_sink(port, "SINK")
    # First packet fails the predicate; second never reaches the sink
    # because the parent is torn down.
    chain.asm_emit_streaming(root, port, {"v": 999.0})
    chain.asm_emit_streaming(root, port, {"v": 50.0})
    chain.end_test()
    chain.run(starting=["v"])

    assert len(error_calls) == 1
    assert error_calls[0]["data"]["why"] == "out_of_range"
    # Sink may have been torn down before processing the bad packet — the
    # important invariant is that the GOOD packet (50.0) never made it,
    # because the test root terminated on the assertion failure.
    assert 50.0 not in received
    assert chain.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 3. Non-matching events pass through transparently.
# ---------------------------------------------------------------------------

def test_verify_ignores_non_matching_packets():
    log: list[str] = []
    error_calls: list[dict] = []
    received: list[float] = []
    verify_port = {"event_id": "TEMP"}
    other_port = {"event_id": "HUMID"}

    def always_false(handle, node, event_type, event_id, event_data):
        # Would fail if dispatched — proves verify never sees non-matching.
        if event_id == "CFL_TERMINATE_EVENT":
            return False
        return False

    def sink(handle, node, event_type, event_id, event_data):
        if event_id != other_port["event_id"]:
            return False
        received.append((event_data or {})["v"])
        return False

    def on_fail(handle, node):
        error_calls.append(1)

    chain = _bounded_engine(log)
    chain.add_boolean("FAIL_FN", always_false)
    chain.add_boolean("SINK", sink)
    chain.add_one_shot("ON_FAIL", on_fail)

    root = chain.start_test("v")
    chain.asm_streaming_verify(verify_port, "FAIL_FN", error_fn="ON_FAIL")
    chain.asm_streaming_sink(other_port, "SINK")
    # Only emit on the OTHER port — verify must stay quiet.
    chain.asm_emit_streaming(root, other_port, {"v": 7.0})
    chain.end_test()
    chain.run(starting=["v"])

    assert received == [7.0]
    assert error_calls == []


# ---------------------------------------------------------------------------
# 4. reset_flag=True → CFL_RESET; parent re-INITs and retries.
# ---------------------------------------------------------------------------

def test_verify_reset_flag_resets_parent_for_retry():
    log: list[str] = []
    error_calls: list[int] = []
    port = {"event_id": "READING"}

    # Predicate flips after the first failure: returns False on call 1,
    # True thereafter. With reset_flag=True the parent re-INITs after the
    # failure and the next pass succeeds.
    call_count = [0]

    def predicate(handle, node, event_type, event_id, event_data):
        if event_id != port["event_id"]:
            return False
        call_count[0] += 1
        return call_count[0] > 1

    def on_fail(handle, node):
        error_calls.append(1)

    chain = _bounded_engine(log, max_ticks=6)
    chain.add_boolean("PRED", predicate)
    chain.add_one_shot("ON_FAIL", on_fail)

    root = chain.start_test("v")
    chain.asm_streaming_verify(
        port, "PRED",
        error_fn="ON_FAIL",
        reset_flag=True,
    )
    chain.asm_emit_streaming(root, port, {"v": 1})
    chain.asm_emit_streaming(root, port, {"v": 2})
    chain.end_test()
    chain.run(starting=["v"])

    # error_fn fired at least once (the first failed assertion).
    assert len(error_calls) >= 1
