"""Streaming collect + sink_collected tests.

Collect is a multi-port packet accumulator: it holds the most-recent
packet per configured inport and, once every inport has fired at least
once, emits a single combined packet on its outport. Sink_collected is
the canonical downstream consumer.

All tests build a column with [collect, sink_collected, emit_*]; emits
target the column root so each streaming event's walker descends
through both collect (which matches and accumulates) and
sink_collected (which only matches the combined packet on the
outport).
"""

from __future__ import annotations

from ct_dsl import ChainTree


def _bounded_engine(log, max_ticks=5):
    sleep_calls = [0]
    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,  # placeholder, replaced below
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
# 1. All inports satisfied → combined packet emitted exactly once
# ---------------------------------------------------------------------------

def test_collect_emits_combined_when_all_inports_fired():
    log: list[str] = []
    received: list[dict] = []

    temp_port = {"event_id": "TEMP", "schema": "celsius"}
    humid_port = {"event_id": "HUMID", "schema": "fraction"}
    combined_port = {"event_id": "WEATHER", "schema": "weather_report"}

    def handler(handle, node, event_type, event_id, event_data):
        if event_id != combined_port["event_id"]:
            return False
        received.append(dict(event_data))
        return False

    chain = _bounded_engine(log, max_ticks=4)
    chain.add_boolean("HANDLER", handler)

    root = chain.start_test("c")
    chain.asm_streaming_collect(
        inports=[temp_port, humid_port],
        outport=combined_port,
        target_node=root,
    )
    chain.asm_streaming_sink_collected(combined_port, "HANDLER")
    chain.asm_emit_streaming(root, temp_port, {"value": 22.5})
    chain.asm_emit_streaming(root, humid_port, {"value": 0.45})
    chain.end_test()
    chain.run(starting=["c"])

    # Exactly one combined packet emitted; carries the outport's schema and
    # both inport sub-packets keyed by their event_ids.
    assert len(received) == 1
    pkt = received[0]
    assert pkt["_schema"] == "weather_report"
    assert pkt["TEMP"]["value"] == 22.5
    assert pkt["TEMP"]["_schema"] == "celsius"
    assert pkt["HUMID"]["value"] == 0.45
    assert pkt["HUMID"]["_schema"] == "fraction"


# ---------------------------------------------------------------------------
# 2. Partial inputs (only one inport fired) → no emit
# ---------------------------------------------------------------------------

def test_collect_holds_when_only_one_inport_fired():
    log: list[str] = []
    received: list[dict] = []

    temp_port = {"event_id": "TEMP"}
    humid_port = {"event_id": "HUMID"}
    combined_port = {"event_id": "WEATHER"}

    def handler(handle, node, event_type, event_id, event_data):
        if event_id != combined_port["event_id"]:
            return False
        received.append(dict(event_data))
        return False

    chain = _bounded_engine(log, max_ticks=4)
    chain.add_boolean("HANDLER", handler)

    root = chain.start_test("c")
    collect_node = chain.asm_streaming_collect(
        inports=[temp_port, humid_port],
        outport=combined_port,
        target_node=root,
    )
    chain.asm_streaming_sink_collected(combined_port, "HANDLER")
    chain.asm_emit_streaming(root, temp_port, {"value": 22.5})
    chain.end_test()
    chain.run(starting=["c"])

    # No combined packet emitted (humid never arrived).
    assert received == []
    # The temp packet is still pending (waiting for humid).
    assert "TEMP" in collect_node["data"]["pending"]
    assert "HUMID" not in collect_node["data"]["pending"]


# ---------------------------------------------------------------------------
# 3. Multiple cycles: pending clears after each emit
# ---------------------------------------------------------------------------

def test_collect_clears_pending_after_emit_and_handles_second_cycle():
    log: list[str] = []
    received: list[dict] = []

    temp_port = {"event_id": "TEMP"}
    humid_port = {"event_id": "HUMID"}
    combined_port = {"event_id": "WEATHER"}

    def handler(handle, node, event_type, event_id, event_data):
        if event_id != combined_port["event_id"]:
            return False
        received.append(dict(event_data))
        return False

    chain = _bounded_engine(log, max_ticks=4)
    chain.add_boolean("HANDLER", handler)

    root = chain.start_test("c")
    collect_node = chain.asm_streaming_collect(
        inports=[temp_port, humid_port],
        outport=combined_port,
        target_node=root,
    )
    chain.asm_streaming_sink_collected(combined_port, "HANDLER")
    # Cycle 1
    chain.asm_emit_streaming(root, temp_port, {"value": 22.5})
    chain.asm_emit_streaming(root, humid_port, {"value": 0.45})
    # Cycle 2 (different values)
    chain.asm_emit_streaming(root, temp_port, {"value": 25.0})
    chain.asm_emit_streaming(root, humid_port, {"value": 0.50})
    chain.end_test()
    chain.run(starting=["c"])

    # Two combined packets emitted (one per complete set).
    assert len(received) == 2
    assert received[0]["TEMP"]["value"] == 22.5
    assert received[0]["HUMID"]["value"] == 0.45
    assert received[1]["TEMP"]["value"] == 25.0
    assert received[1]["HUMID"]["value"] == 0.50
    # Pending is empty after the last emit.
    assert collect_node["data"]["pending"] == {}


# ---------------------------------------------------------------------------
# 4. Latest-wins semantics: repeated packet on one inport overwrites pending
# ---------------------------------------------------------------------------

def test_collect_overwrites_pending_with_latest_packet():
    log: list[str] = []
    received: list[dict] = []

    temp_port = {"event_id": "TEMP"}
    humid_port = {"event_id": "HUMID"}
    combined_port = {"event_id": "WEATHER"}

    def handler(handle, node, event_type, event_id, event_data):
        if event_id != combined_port["event_id"]:
            return False
        received.append(dict(event_data))
        return False

    chain = _bounded_engine(log, max_ticks=4)
    chain.add_boolean("HANDLER", handler)

    root = chain.start_test("c")
    chain.asm_streaming_collect(
        inports=[temp_port, humid_port],
        outport=combined_port,
        target_node=root,
    )
    chain.asm_streaming_sink_collected(combined_port, "HANDLER")
    # Two temp readings before the humid arrives — only the latest wins.
    chain.asm_emit_streaming(root, temp_port, {"value": 20.0})
    chain.asm_emit_streaming(root, temp_port, {"value": 22.5})
    chain.asm_emit_streaming(root, humid_port, {"value": 0.45})
    chain.end_test()
    chain.run(starting=["c"])

    assert len(received) == 1
    assert received[0]["TEMP"]["value"] == 22.5
    assert received[0]["HUMID"]["value"] == 0.45


# ---------------------------------------------------------------------------
# 5. Schema mismatch on inport → packet is ignored
# ---------------------------------------------------------------------------

def test_collect_ignores_schema_mismatched_packet():
    log: list[str] = []
    received: list[dict] = []

    temp_port = {"event_id": "TEMP", "schema": "celsius"}
    humid_port = {"event_id": "HUMID"}
    combined_port = {"event_id": "WEATHER"}

    def handler(handle, node, event_type, event_id, event_data):
        if event_id != combined_port["event_id"]:
            return False
        received.append(dict(event_data))
        return False

    chain = _bounded_engine(log, max_ticks=4)
    chain.add_boolean("HANDLER", handler)

    root = chain.start_test("c")
    collect_node = chain.asm_streaming_collect(
        inports=[temp_port, humid_port],
        outport=combined_port,
        target_node=root,
    )
    chain.asm_streaming_sink_collected(combined_port, "HANDLER")
    # Wrong schema for temp — collect should drop it.
    wrong_temp = {"event_id": "TEMP", "schema": "fahrenheit"}
    chain.asm_emit_streaming(root, wrong_temp, {"value": 73})
    chain.asm_emit_streaming(root, humid_port, {"value": 0.5})
    chain.end_test()
    chain.run(starting=["c"])

    # No combined emitted; only humid is in pending.
    assert received == []
    assert "TEMP" not in collect_node["data"]["pending"]
    assert "HUMID" in collect_node["data"]["pending"]


# ---------------------------------------------------------------------------
# 6. Observer aux fn fires on each matching packet (return value ignored)
# ---------------------------------------------------------------------------

def test_collect_observer_fires_on_each_matching_packet():
    log: list[str] = []
    observations: list[str] = []

    temp_port = {"event_id": "TEMP"}
    humid_port = {"event_id": "HUMID"}
    combined_port = {"event_id": "WEATHER"}

    def observer(handle, node, event_type, event_id, event_data):
        if event_id == "CFL_TERMINATE_EVENT":
            return False
        observations.append(event_id)
        # Return True — collect ignores the return value, emit must still
        # depend on inport coverage.
        return True

    def handler(handle, node, event_type, event_id, event_data):
        if event_id != combined_port["event_id"]:
            return False
        log.append("combined")
        return False

    chain = _bounded_engine(log, max_ticks=4)
    chain.add_boolean("OBS", observer)
    chain.add_boolean("HANDLER", handler)

    root = chain.start_test("c")
    chain.asm_streaming_collect(
        inports=[temp_port, humid_port],
        outport=combined_port,
        observer_fn="OBS",
        target_node=root,
    )
    chain.asm_streaming_sink_collected(combined_port, "HANDLER")
    chain.asm_emit_streaming(root, temp_port, {"value": 1})
    chain.asm_emit_streaming(root, humid_port, {"value": 2})
    chain.end_test()
    chain.run(starting=["c"])

    # Observer saw two matching packets (temp, humid). Combined sink fired.
    assert observations == ["TEMP", "HUMID"]
    assert "combined" in log
