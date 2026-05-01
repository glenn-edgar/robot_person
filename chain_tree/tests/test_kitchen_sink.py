"""End-to-end kitchen-sink scenario combining the major operator families.

Realistic shape: a sensor-monitor workflow gated by business hours.

  state_machine "workflow":
    state "check"      — wait until wall clock is in business hours via
                         wait_until_in_time_window, then transition.
    state "collecting" — streaming sink + 4 emit packets through a
                         quality filter (one of them fails the
                         predicate); after 3 good readings a
                         user-enqueued internal event releases a
                         wait_for_event with timeout, which transitions
                         to "alerting".
    state "alerting"   — controlled-node RPC: client sends a request to
                         a server whose child logs the dispatch; on
                         response the state changes to "done".
    state "done"       — log "complete"; SM detects the column is
                         finished and disables itself.

Operators exercised: wait_until_in_time_window, state_machine + change_state,
streaming_sink + emit_streaming (with inline quality filtering in the
handler), wait_for_event + timeout, controlled_server, controlled_client,
log, plus the bridge-equivalent of cfl_internal_event from a user fn.

The wall clock is fixed at 2026-04-23 10:00 UTC (a Thursday in the 9-17
business-hours window), so the verify gate passes deterministically.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ct_dsl import ChainTree
from ct_runtime import enqueue
from ct_runtime.codes import CFL_EVENT_TYPE_NULL, PRIORITY_NORMAL
from ct_runtime.event_queue import make_event


def _wall_clock(dt: datetime) -> int:
    return int(dt.timestamp())


def test_kitchen_sink_workflow():
    log: list[str] = []
    received_alerts: list[dict] = []

    sensor_port = {"event_id": "SENSOR", "schema": "moisture"}
    request_port = {"event_id": "ALERT_REQ", "schema": "alert"}
    response_port = {"event_id": "ALERT_RESP", "schema": "alert_ack"}

    # sm_holder[0] is filled in after the SM is built; the streaming
    # handler closes over it to target the SM with READINGS_DONE.
    sm_holder: list = []

    def on_reading(handle, node, event_type, event_id, event_data):
        # Same filter contract as biz_check.
        if event_id != sensor_port["event_id"]:
            return False
        # Inline quality filter: only [0.0, 1.0] readings count. A 1.5
        # value is dropped silently.
        val = (event_data or {}).get("value", 0.0)
        if not (0.0 <= val <= 1.0):
            return False
        bb = handle["blackboard"]
        bb["good_readings"] = bb.get("good_readings", 0) + 1
        if bb["good_readings"] == 3:
            # Release the wait_for_event sibling. Targeted at the SM so
            # the walker descends into the active state column.
            enqueue(handle["engine"], make_event(
                target=sm_holder[0],
                event_type=CFL_EVENT_TYPE_NULL,
                event_id="READINGS_DONE",
                data=None,
                priority=PRIORITY_NORMAL,
            ))
        return False

    def alert_handler(handle, node, event_type, event_id, event_data):
        if event_id != request_port["event_id"]:
            return False
        received_alerts.append(dict(event_data or {}))
        return False

    def on_resp(handle, node, event_type, event_id, event_data):
        if event_id != response_port["event_id"]:
            return False
        handle["blackboard"]["resp_seen"] = True
        return False

    chain = ChainTree(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: _wall_clock(
            datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        ),
        timezone=timezone.utc,
        logger=log.append,
    )
    chain.add_boolean("ON_READING", on_reading)
    chain.add_boolean("ALERT_HANDLER", alert_handler)
    chain.add_boolean("ON_RESP", on_resp)

    chain.start_test("monitor")
    sm = chain.define_state_machine(
        "workflow",
        state_names=["check", "collecting", "alerting", "done"],
        initial_state="check",
    )
    sm_holder.append(sm)

    chain.define_state("check")
    chain.asm_wait_until_in_time_window({"hour": 9}, {"hour": 17})
    chain.asm_log_message("biz hours OK")
    chain.asm_change_state(sm, "collecting")
    chain.end_state()

    chain.define_state("collecting")
    chain.asm_log_message("collecting")
    sink = chain.asm_streaming_sink(sensor_port, "ON_READING")
    chain.asm_emit_streaming(sink, sensor_port, {"value": 0.5})
    chain.asm_emit_streaming(sink, sensor_port, {"value": 1.5})  # dropped
    chain.asm_emit_streaming(sink, sensor_port, {"value": 0.6})
    chain.asm_emit_streaming(sink, sensor_port, {"value": 0.9})
    chain.asm_wait_for_event(
        event_id="READINGS_DONE",
        count=1,
        timeout=20,                 # generous; should fire on first tick
        timeout_event_id="CFL_TIMER_EVENT",
    )
    chain.asm_change_state(sm, "alerting")
    chain.end_state()

    chain.define_state("alerting")
    server = chain.define_controlled_server(
        "alert_svc",
        request_port=request_port,
        response_port=response_port,
        handler_fn="ALERT_HANDLER",
        response_data={"status": "delivered"},
    )
    chain.asm_log_message("alert dispatched")
    chain.end_controlled_server()
    chain.asm_client_controlled_node(
        server,
        request_port=request_port,
        response_port=response_port,
        request_data={"severity": "warn"},
        response_handler="ON_RESP",
    )
    chain.asm_change_state(sm, "done")
    chain.end_state()

    chain.define_state("done")
    chain.asm_log_message("workflow complete")
    chain.end_state()
    chain.end_state_machine()
    chain.end_test()

    chain.run(starting=["monitor"])

    bb = chain.engine["kbs"]["monitor"]["blackboard"]

    # Three valid readings counted; the 1.5 reading was dropped.
    assert bb["good_readings"] == 3
    # RPC round-trip: server received the request, client saw the response.
    assert len(received_alerts) == 1
    assert received_alerts[0]["severity"] == "warn"
    assert received_alerts[0]["_schema"] == "alert"
    assert bb["resp_seen"] is True
    # SM walked through all four states and finished on "done".
    assert sm["data"]["current_state_name"] == "done"
    # Logs from each state appeared in workflow order.
    assert log == [
        "biz hours OK",
        "collecting",
        "alert dispatched",
        "workflow complete",
    ]
    # KB completed cleanly.
    assert chain.engine["active_kbs"] == []
