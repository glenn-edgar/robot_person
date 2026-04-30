"""ct_builtins — CFL builtin main / boolean / one-shot fns.

The single entry point is `register_all_builtins(registry)` — call this on
a fresh registry before adding user functions. The DSL builder does it
automatically when constructing a ChainTree.
"""

from __future__ import annotations

from ct_runtime.registry import (
    add_boolean,
    add_main,
    add_one_shot,
)

from . import (
    column,
    control,
    controlled,
    exception,
    se_bridge,
    sequence_til,
    state_machine,
    streaming,
    supervisor,
    system,
    time_window,
    verify,
    wait,
)


def register_all_builtins(registry: dict) -> None:
    """Install every CFL builtin into the registry."""

    # Trivial control-flow main fns: name == returned code.
    for name, fn in control.CONTROL_MAINS.items():
        add_main(registry, name, fn, description=f"returns {name}")

    # CFL_NULL no-ops, registered into both boolean and one-shot tables
    # under the same name.
    add_boolean(registry, control.NULL_BOOLEAN_NAME, control.cfl_null_boolean,
                description="default boolean: always False (no early-out)")
    add_one_shot(registry, control.NULL_ONE_SHOT_NAME, control.cfl_null_one_shot,
                 description="default init/term one-shot: no-op")

    # Column / fork / pipeline parent.
    add_main(registry, "CFL_COLUMN_MAIN", column.cfl_column_main,
             description="container; CONTINUE while any child enabled, else DISABLE")
    add_one_shot(registry, "CFL_COLUMN_INIT", column.cfl_column_init,
                 description="enable all child links")
    add_one_shot(registry, "CFL_COLUMN_TERM", column.cfl_column_term,
                 description="column termination no-op")

    # Wait-for-time leaf.
    add_main(registry, "CFL_WAIT_TIME", wait.cfl_wait_time_main,
             description="HALT until time_delay elapsed since start_time, then DISABLE")
    add_one_shot(registry, "CFL_WAIT_TIME_INIT", wait.cfl_wait_time_init,
                 description="stamp start_time on the node from engine monotonic clock")

    # Wait-for-event leaf + standard event-counting aux.
    add_main(registry, "CFL_WAIT_MAIN", wait.cfl_wait_main,
             description="HALT until aux true (DISABLE) or timeout (error_fn + TERM/RESET)")
    add_one_shot(registry, "CFL_WAIT_INIT", wait.cfl_wait_init,
                 description="reset wait counters (current_count, timeout_count)")
    add_boolean(registry, "CFL_WAIT_FOR_EVENT", wait.cfl_wait_for_event,
                description="True after target_event_id has been seen target_count times")

    # Verify (assertion) leaf.
    add_main(registry, "CFL_VERIFY", verify.cfl_verify_main,
             description="aux true → CONTINUE; false → error_fn then RESET/TERMINATE")

    # Sequence-til: pass-on-first-success / fail-on-first-failure parents.
    add_main(registry, "CFL_SEQUENCE_PASS_MAIN", sequence_til.cfl_sequence_pass_main,
             description="advance children until one PASSES; finalize+DISABLE")
    add_main(registry, "CFL_SEQUENCE_FAIL_MAIN", sequence_til.cfl_sequence_fail_main,
             description="advance children until one FAILS; finalize+DISABLE")
    add_one_shot(registry, "CFL_SEQUENCE_INIT", sequence_til.cfl_sequence_init,
                 description="reset sequence state; enable first child only")
    add_one_shot(registry, "CFL_SEQUENCE_TERM", sequence_til.cfl_sequence_term,
                 description="sequence termination no-op")
    add_one_shot(registry, "CFL_MARK_SEQUENCE", sequence_til.cfl_mark_sequence,
                 description="record (status, data) into parent's sequence_state.results[current_index]")
    add_one_shot(registry, "CFL_MARK_SEQUENCE_IF", sequence_til.cfl_mark_sequence_if,
                 description="probe predicate_fn at INIT; mark pass on True else fail")

    # Controlled nodes: client-server RPC over directed events.
    add_main(registry, "CFL_CONTROLLED_SERVER_MAIN", controlled.cfl_controlled_server_main,
             description="server: on request match enable children + CONTINUE; on poll send response + DISABLE")
    add_main(registry, "CFL_CONTROLLED_CLIENT_MAIN", controlled.cfl_controlled_client_main,
             description="client: HALT until response matches, then DISABLE")
    add_one_shot(registry, "CFL_CONTROLLED_CLIENT_INIT", controlled.cfl_controlled_client_init,
                 description="client INIT: enqueue request high-pri to server with self ref")
    add_one_shot(registry, "CFL_CONTROLLED_CLIENT_TERM", controlled.cfl_controlled_client_term,
                 description="client termination no-op")

    # Streaming nodes: schema-tagged event pipelines (sink/tap/filter/transform).
    add_main(registry, "CFL_STREAMING_SINK_PACKET", streaming.cfl_streaming_sink_packet,
             description="match inport → call user boolean (consumer); CONTINUE")
    add_main(registry, "CFL_STREAMING_TAP_PACKET", streaming.cfl_streaming_tap_packet,
             description="match inport → call user boolean (observer); CONTINUE")
    add_main(registry, "CFL_STREAMING_FILTER_PACKET", streaming.cfl_streaming_filter_packet,
             description="match inport → boolean False ⇒ CFL_HALT (blocks downstream)")
    add_main(registry, "CFL_STREAMING_TRANSFORM_PACKET", streaming.cfl_streaming_transform_packet,
             description="match inport → call user boolean (user emits on outport)")
    add_main(registry, "CFL_STREAMING_COLLECT_PACKET", streaming.cfl_streaming_collect_packet,
             description="multi-port join: emit combined packet on outport when every inport has fired")
    add_one_shot(registry, "CFL_STREAMING_COLLECT_INIT", streaming.cfl_streaming_collect_init,
                 description="reset collect's pending-packet store on (re-)activation")
    add_main(registry, "CFL_STREAMING_SINK_COLLECTED", streaming.cfl_streaming_sink_collected,
             description="sink variant for collect-shaped packets (semantic alias of SINK)")
    add_main(registry, "CFL_STREAMING_VERIFY_PACKET", streaming.cfl_streaming_verify_packet,
             description="streaming-aware assertion: predicate True → CONTINUE; False → error_fn + RESET/TERMINATE")

    # Exception catch + heartbeat (3-stage MAIN/RECOVERY/FINALIZE pipeline).
    add_main(registry, "CFL_EXCEPTION_CATCH_MAIN", exception.cfl_exception_catch_main,
             description="3-stage pipeline; handles RAISE/HEARTBEAT events; advances MAIN→RECOVERY→FINALIZE")
    add_one_shot(registry, "CFL_EXCEPTION_CATCH_INIT", exception.cfl_exception_catch_init,
                 description="bind catch_links; enable MAIN child only")
    add_one_shot(registry, "CFL_EXCEPTION_CATCH_TERM", exception.cfl_exception_catch_term,
                 description="exception catch termination no-op")
    add_one_shot(registry, "CFL_RAISE_EXCEPTION", exception.cfl_raise_exception,
                 description="post high-pri RAISE_EXCEPTION_EVENT to nearest catch ancestor")
    add_one_shot(registry, "CFL_TURN_HEARTBEAT_ON", exception.cfl_turn_heartbeat_on,
                 description="post HEARTBEAT_ON_EVENT with timeout to nearest catch ancestor")
    add_one_shot(registry, "CFL_TURN_HEARTBEAT_OFF", exception.cfl_turn_heartbeat_off,
                 description="post HEARTBEAT_OFF_EVENT to nearest catch ancestor")
    add_one_shot(registry, "CFL_HEARTBEAT_EVENT", exception.cfl_heartbeat_event,
                 description="post HEARTBEAT_EVENT (resets timeout counter)")
    add_one_shot(registry, "CFL_SET_EXCEPTION_STEP", exception.cfl_set_exception_step,
                 description="post SET_EXCEPTION_STEP_EVENT (records progress)")

    # Supervisor (Erlang-style restart policies).
    add_main(registry, "CFL_SUPERVISOR_MAIN", supervisor.cfl_supervisor_main,
             description="ONE_FOR_ONE/ONE_FOR_ALL/REST_FOR_ALL restart on child disable")
    add_one_shot(registry, "CFL_SUPERVISOR_INIT", supervisor.cfl_supervisor_init,
                 description="enable all children; init reset_count + failure_counter")
    add_one_shot(registry, "CFL_SUPERVISOR_TERM", supervisor.cfl_supervisor_term,
                 description="supervisor termination no-op")

    # State machine: SM node + transition one-shots.
    add_main(registry, "CFL_STATE_MACHINE_MAIN", state_machine.cfl_state_machine_main,
             description="SM parent: handles CHANGE_STATE/RESET/TERMINATE events, scans active state")
    add_one_shot(registry, "CFL_STATE_MACHINE_INIT", state_machine.cfl_state_machine_init,
                 description="enable initial state child only")
    add_one_shot(registry, "CFL_STATE_MACHINE_TERM", state_machine.cfl_state_machine_term,
                 description="SM termination no-op")
    add_one_shot(registry, "CFL_CHANGE_STATE", state_machine.cfl_change_state,
                 description="post a high-pri CFL_CHANGE_STATE_EVENT to a SM node")
    add_one_shot(registry, "CFL_TERMINATE_STATE_MACHINE", state_machine.cfl_terminate_state_machine,
                 description="post a high-pri CFL_TERMINATE_STATE_MACHINE_EVENT to a SM node")
    add_one_shot(registry, "CFL_RESET_STATE_MACHINE", state_machine.cfl_reset_state_machine,
                 description="post a high-pri CFL_RESET_STATE_MACHINE_EVENT to a SM node")

    # Wall-clock window: writes bool to kb.blackboard[key] each tick.
    add_main(registry, "CFL_TIME_WINDOW_CHECK", time_window.cfl_time_window_check,
             description="write True/False to kb.blackboard[key] based on local-time window")

    # System utilities.
    add_one_shot(registry, "CFL_LOG_MESSAGE", system.cfl_log_message,
                 description="emit node.data['message'] via engine logger")
    add_one_shot(registry, "CFL_BLACKBOARD_SET", system.cfl_blackboard_set,
                 description="kb.blackboard[node.data['key']] = node.data['value']")
    add_one_shot(registry, "CFL_EMIT_STREAMING", system.cfl_emit_streaming,
                 description="post a streaming event to target_node (used by asm_emit_streaming)")

    # s_engine bridge: three CFL node types.
    add_main(registry, "SE_MODULE_LOAD_MAIN", se_bridge.se_module_load_main,
             description="DISABLE on first tick after INIT builds the module")
    add_one_shot(registry, "SE_MODULE_LOAD_INIT", se_bridge.se_module_load_init,
                 description="build s_engine module sharing kb.blackboard; register bridge + user fns")
    add_one_shot(registry, "SE_MODULE_LOAD_TERM", se_bridge.se_module_load_term,
                 description="no-op; module GC'd with KB blackboard")

    add_main(registry, "SE_TREE_CREATE_MAIN", se_bridge.se_tree_create_main,
             description="DISABLE on first tick after INIT instantiates the tree")
    add_one_shot(registry, "SE_TREE_CREATE_INIT", se_bridge.se_tree_create_init,
                 description="instantiate named tree; stamp CFL back-pointers on instance")
    add_one_shot(registry, "SE_TREE_CREATE_TERM", se_bridge.se_tree_create_term,
                 description="no-op; instance GC'd with KB blackboard")

    add_main(registry, "SE_TICK_MAIN", se_bridge.se_tick_main,
             description="composite; aux fn drives interaction, returns node.data.return_code")


__all__ = [
    "register_all_builtins",
    "column", "control", "controlled", "exception", "se_bridge", "sequence_til",
    "state_machine", "streaming", "supervisor", "system", "time_window",
    "verify", "wait",
]
