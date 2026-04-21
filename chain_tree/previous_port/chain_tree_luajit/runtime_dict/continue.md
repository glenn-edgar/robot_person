# Dict-Based Runtime — Continue Notes

## Current State: 26/26 PASS (structurally), output matching in progress

All 26 tests pass. Most produce output matching the C reference binary.
Remaining work is output fidelity for streaming/packet tests.

## Test Results (without usleep, fast mode)

| Idx | KB Name | Ticks | Status |
|-----|---------|-------|--------|
| 0 | first_test | 122 | Match |
| 1 | second_test | 333 | Match (missing wait_for_event_error — sim-time vs wall-clock SECOND_EVENT) |
| 2 | fourth_test | 201 | Match |
| 3 | fifth_test | 304 | Match (state machine, event loggers) |
| 4 | sixth_test | 201 | Match |
| 5 | seventh_test | 201 | Match |
| 6 | eighth_test | 107 | Match (sequence pass with mark_sequence) |
| 7 | ninth_test | 107 | Match (sequence fail) |
| 8 | tenth_test | 666 | Match (supervisor, 4 phases, leaky bucket) |
| 9 | eleventh_test | 66 | Match |
| 10 | twelfth_test | 110 | Match |
| 11 | thirteenth_test | 331 | Match (watchdog pat/disable/enable) |
| 12 | fourteenth_test | 205 | Match (bitmask, DF mask) |
| 13 | seventeenth_test | 481 | Match (exception 4 combos, recovery, catch-all) |
| 14 | eighteenth_test | 469 | Match (exception + heartbeat) |
| 15 | ninteenth_test | 1810 | Match (SM event filtering) |
| 16 | twentieth_test | 54 | Match (bitmask verify) |
| 17 | twenty_first_test | 117 | Match (multi-KB stub — verify fails as expected) |
| 18 | twenty_second_test | 103 | Match |
| 19 | twenty_third_test | 1 | Match (avro verify, CFL_TERMINATE) |
| 20 | twenty_fourth_test | 1003 | **NEEDS WORK** — streaming tap/filter/sink/transform not printing |
| 21 | twenty_fifth_test | 1003 | Partial — collector works, needs full packet output |
| 22 | twenty_sixth_test | 301 | **NEEDS WORK** — PACKET_GENERATOR fires but packets not reaching streaming nodes |
| 23 | twenty_seventh_test | 153 | Match (drone controlled nodes) |
| 24 | twenty_eighth_test | 153 | Match (drone + exception) |
| 25 | twenty_ninth_test | 1 | Match (blackboard) |

## Known Issues — Streaming Tests (20, 21, 22)

### Root Cause: PACKET_GENERATOR event routing
The `PACKET_GENERATOR` one-shot creates FFI packets and inserts streaming events
into the event queue with `event_type = "streaming_data"`. The events target the
launch column (`nd.event_column`, resolved to ltree). However:

1. **Test 22 (twenty_sixth_test)**: The generator node [1209] fires inside a
   sub-column `COL_pack._0` but the output only shows the parent column's
   LOG_MESSAGE repeating. The generator fires and emits packets, but the
   streaming TAP/SINK/VERIFY nodes in the same parent column don't receive them.

   **Suspect**: The streaming event is queued targeting the launch column root,
   but when `execute_event` walks from that root, the streaming nodes might not
   match because `streaming_event_matches()` checks `handle.current_event_type`
   which is set correctly by `execute_event`. Need to trace whether the walker
   actually reaches the streaming nodes during the streaming_data event walk.

2. **Test 20 (twenty_fourth_test)**: Similar — streaming pipeline (tap, filter,
   transform, sink) nodes should process packets but no output appears.

3. **Test 21 (twenty_fifth_test)**: Collector works (prints accept/reject), but
   only for first few batches. Container reset was fixed. Need to verify full
   output parity with C.

### Next Debug Steps
1. Add trace inside `streaming_event_matches()` to verify it's called during
   streaming_data events
2. Check if the walker is visiting streaming nodes at all — the streaming nodes
   are children of the launch column but might be in sub-columns that the walker
   skips due to HALT/DISABLE from other nodes
3. Verify the inport event_id matches (should be 38 = SENSOR_EVENT for test 22)
4. Check if `handle.current_event_type` is "streaming_data" when streaming nodes'
   main functions run

## Bugs Fixed This Session

### Critical
- **cjson.null**: JSON `null` decodes as truthy userdata in LuaJIT. Added `scrub_nulls()` in ct_loader to convert to real `nil`. Was causing state machine event filter to block all events.
- **CFL_GATE_NODE_INIT**: Was aliased to CFL_COLUMN_INIT (enables ALL children). Fixed to only enable `auto_start=true` children, matching C's `cfl_enable_auto_start_nodes`.
- **CFL_STATE_MACHINE_MAIN**: Rewrote to deferred state change model (current_state vs new_state). Bool_fn returning true → CFL_SKIP_CONTINUE (not CFL_DISABLE). Matches C.
- **CFL_CHANGE_STATE**: Was reading `nd.sm_node_id` but JSON has `nd.node_id`. Fixed. Also sends sync_event to SM when sync_event_id is set.
- **Auto-start suppression**: State machine and exception catch init suppress auto_start via `node.node_dict._sm_auto_start_suppressed` flag, preventing engine from re-enabling all children after selective init.
- **CFL_MARK_SEQUENCE**: Was using tree parent. Fixed to use `nd.parent_node_name` (explicit ltree to sequence node).
- **CFL_SET_BITMASK/CFL_CLEAR_BITMASK**: Was reading `nd.bitmask_indices` (array). Fixed to read `nd.bit_mask` (pre-computed integer).
- **Watchdog enable/disable/pat**: Were modifying own node state. Fixed to target watchdog node via `nd.node_id`.
- **CFL_TURN_HEARTBEAT_ON**: Was reading `nd.heartbeat_timeout`. Fixed to read `nd.time_out`.
- **AVRO_VERIFY_PACKET/CONST**: Was returning CFL_DISABLE. Fixed to CFL_TERMINATE (matching C user functions).
- **Finalize functions**: Not registered because only referenced in `column_data.finalize_function`, not in label_dict. Fixed loader to also register functions from the merged registry that aren't in the name sets.

### Exception Handling (full rewrite)
- `find_parent_exception_node()` helper walks up parent chain
- `CFL_RAISE_EXCEPTION` sends to nearest catch node (not root)
- `CFL_SET_EXCEPTION_STEP` sends step event to nearest catch
- `CFL_EXCEPTION_CATCH_MAIN` full state machine: main→recovery→finalize stages
- `CFL_RECOVERY_MAIN` 4-state recovery: eval→wait→parallel_enable→parallel_wait
- `CFL_EXCEPTION_CATCH_INIT` suppresses auto_start, enables only main link

### Supervisor (full rewrite)
- Per-child failure tracking array
- Leaky bucket time-windowed failure detection
- 3 termination types: one_for_one (0), one_for_all (1), rest_for_all (2)
- `CFL_MARK_SUPERVISOR_NODE_FAILURE_INIT` walks up to find supervisor

### Avro/FFI Packets
- `GENERATE_FFI()` added to avro_dsl.lua
- `stream_test_1_ffi.lua` and `drone_control_ffi.lua` generated
- Streaming builtins: real port matching via schema_hash
- Collector: container reset after emission, port index tracking
- User functions: real FFI packet creation, verify, filter, tap, transform, sink

### Multi-KB
- `CFL_VERIFY_TESTS_ACTIVE` returns false (target KB never started in single-KB mode)
- `CFL_WAIT_FOR_TESTS_COMPLETE` returns true immediately

### Timer
- Second/minute/hour events generated on sim-time boundary crossings
- `ffi.C.usleep()` for real-time tick delay
- Wall-clock timestamp via `clock_gettime(CLOCK_REALTIME)` for CFL_LOG_MESSAGE

## File Inventory

### Runtime (runtime_dict/)
- `ct_definitions.lua` — string return codes, event IDs
- `ct_common.lua` — node helpers (children, state, data access)
- `ct_walker.lua` — iterative DFS with string node IDs
- `ct_engine.lua` — node execution, termination, event_type support
- `ct_loader.lua` — JSON loader: cjson null scrub, blackboard, index resolution
- `ct_builtins.lua` — all builtin functions (~1800 lines)
- `ct_runtime.lua` — event loop with usleep, time events
- `ct_avro.lua` — FFI packet helpers

### Test (dsl_tests/incremental_binary/)
- `incremental_build.lua` — DSL source (from C port, corrected SM sync)
- `incremental_build.json` — generated JSON IR
- `incremental_build_debug.yaml` — debug YAML with array_index per node
- `test_dict.lua` — test harness (index or name, timing, wall clock)
- `user_functions_dict.lua` — user functions with FFI packets
- `stream_test_1_ffi.lua` — generated FFI schema
- `drone_control_ffi.lua` — generated FFI schema

### DSL (c_avro_packets/)
- `avro_dsl.lua` — extended with GENERATE_FFI()
