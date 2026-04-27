"""Streaming-node tests — sink/tap/filter/transform on schema-tagged events.

Pattern: a column with [emit, sink, ...]. The emit one-shot posts a
streaming event into the queue; the engine drains the timer event first
(visiting all leaves in order — sink sees TIMER and CONTINUEs as no-match),
then drains the streaming event (walker.walk(target=root, streaming) →
descends through emit (disabled now) → reaches sink → matches → fires
boolean).

Tests bound run-time via a sleep callback that clears active_kbs after a
few ticks.
"""

from __future__ import annotations

import pytest

from ct_dsl import ChainTree


def _bounded_engine(log, max_ticks=5):
    sleep_calls = [0]
    ct = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,  # placeholder, replaced below
        get_time=lambda: 0.0,
        logger=log.append,
    )

    def stop_after(_dt):
        sleep_calls[0] += 1
        if sleep_calls[0] >= max_ticks:
            ct.engine["active_kbs"].clear()

    ct.engine["sleep"] = stop_after
    return ct


# ---------------------------------------------------------------------------
# 1. Sink processes matching streaming event.
# ---------------------------------------------------------------------------

def test_sink_processes_matching_event():
    log: list[str] = []
    received: list[dict] = []

    def handler(handle, node, event_type, event_id, event_data):
        received.append(dict(event_data))
        return False

    ct = _bounded_engine(log)
    ct.add_boolean("HANDLER", handler)

    port = {"event_id": "SENSOR", "schema": "accel"}

    ct.start_test("s")
    sink = ct.asm_streaming_sink(port, "HANDLER")
    ct.asm_emit_streaming(sink, port, {"x": 1.0, "y": 2.0})
    ct.end_test()

    ct.run(starting=["s"])

    assert len(received) == 1
    assert received[0]["x"] == 1.0
    assert received[0]["y"] == 2.0
    assert received[0]["_schema"] == "accel"


# ---------------------------------------------------------------------------
# 2. Sink IGNORES events with the wrong schema.
# ---------------------------------------------------------------------------

def test_sink_ignores_wrong_schema():
    log: list[str] = []
    received: list[dict] = []

    def handler(handle, node, event_type, event_id, event_data):
        received.append(dict(event_data))
        return False

    ct = _bounded_engine(log)
    ct.add_boolean("HANDLER", handler)

    sink_port = {"event_id": "SENSOR", "schema": "accel"}
    wrong_port = {"event_id": "SENSOR", "schema": "gyro"}

    ct.start_test("s")
    sink = ct.asm_streaming_sink(sink_port, "HANDLER")
    ct.asm_emit_streaming(sink, wrong_port, {"x": 1.0})
    ct.end_test()

    ct.run(starting=["s"])

    assert received == []


# ---------------------------------------------------------------------------
# 3. Sink matches when the port omits "schema" (event_id only).
# ---------------------------------------------------------------------------

def test_sink_matches_event_id_only_when_no_schema():
    log: list[str] = []
    received: list[dict] = []

    def handler(handle, node, event_type, event_id, event_data):
        received.append(dict(event_data))
        return False

    ct = _bounded_engine(log)
    ct.add_boolean("HANDLER", handler)

    port_no_schema = {"event_id": "ALERT"}

    ct.start_test("s")
    sink = ct.asm_streaming_sink(port_no_schema, "HANDLER")
    # Emit with arbitrary schema — should still match.
    ct.asm_emit_streaming(sink, {"event_id": "ALERT", "schema": "whatever"},
                          {"msg": "boom"})
    ct.end_test()

    ct.run(starting=["s"])

    assert len(received) == 1
    assert received[0]["msg"] == "boom"


# ---------------------------------------------------------------------------
# 4. Filter blocks downstream sink when predicate False; allows when True.
# ---------------------------------------------------------------------------

def test_filter_blocks_or_allows_per_predicate():
    log: list[str] = []
    received: list[dict] = []

    def loud_predicate(handle, node, event_type, event_id, event_data):
        # True if x > 5 (large readings only).
        return (event_data or {}).get("x", 0) > 5

    def handler(handle, node, event_type, event_id, event_data):
        received.append(dict(event_data))
        return False

    ct = _bounded_engine(log)
    ct.add_boolean("LOUD", loud_predicate)
    ct.add_boolean("HANDLER", handler)

    port = {"event_id": "SENSOR", "schema": "accel"}

    root = ct.start_test("flt")
    # Pipeline: filter then sink. To make the filter participate, the
    # emit MUST target an ancestor (root) of both filter and sink — when
    # the streaming event fires, the walker descends from root through
    # filter THEN sink. Targeting the sink directly bypasses the filter.
    ct.asm_streaming_filter(port, "LOUD")
    ct.asm_streaming_sink(port, "HANDLER")
    ct.asm_emit_streaming(root, port, {"x": 1.0})    # blocked by filter
    ct.asm_emit_streaming(root, port, {"x": 10.0})   # passes through filter
    ct.end_test()

    ct.run(starting=["flt"])

    assert len(received) == 1
    assert received[0]["x"] == 10.0


# ---------------------------------------------------------------------------
# 5. Transform: user fn reads inbound packet, emits transformed packet.
# ---------------------------------------------------------------------------

def test_transform_emits_on_outport():
    log: list[str] = []
    transform_in: list[dict] = []
    final_received: list[dict] = []
    refs = {}

    def transform(handle, node, event_type, event_id, event_data):
        # Capture input
        transform_in.append(dict(event_data))
        # Emit transformed packet on outport
        outport = node["data"]["outport"]
        from ct_runtime import enqueue
        from ct_runtime.codes import CFL_EVENT_TYPE_STREAMING_DATA, PRIORITY_NORMAL
        from ct_runtime.event_queue import make_event
        new_data = {
            "_schema": outport.get("schema", "transformed"),
            "doubled": event_data["x"] * 2,
        }
        enqueue(handle["engine"], make_event(
            target=refs["sink"],
            event_type=CFL_EVENT_TYPE_STREAMING_DATA,
            event_id=outport["event_id"],
            data=new_data,
            priority=PRIORITY_NORMAL,
        ))
        return False

    def final_handler(handle, node, event_type, event_id, event_data):
        final_received.append(dict(event_data))
        return False

    ct = _bounded_engine(log, max_ticks=8)
    ct.add_boolean("TRANSFORM", transform)
    ct.add_boolean("FINAL_HANDLER", final_handler)

    inport = {"event_id": "RAW", "schema": "raw"}
    outport = {"event_id": "TRANSFORMED", "schema": "doubled"}

    ct.start_test("t")
    transform_node = ct.asm_streaming_transform(inport, outport, "TRANSFORM")
    sink = ct.asm_streaming_sink(outport, "FINAL_HANDLER")
    refs["sink"] = sink
    ct.asm_emit_streaming(transform_node, inport, {"x": 7})
    ct.end_test()

    ct.run(starting=["t"])

    assert len(transform_in) == 1
    assert transform_in[0]["x"] == 7
    assert len(final_received) == 1
    assert final_received[0]["doubled"] == 14
    assert final_received[0]["_schema"] == "doubled"
