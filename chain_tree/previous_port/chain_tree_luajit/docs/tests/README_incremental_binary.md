# Incremental Binary Test Suite (Dict Runtime)

The main ChainTree integration test suite. 26 tests covering all core node types and control flow patterns, run against the dict-based runtime.

## Location

```
dsl_tests/incremental_binary/
  incremental_build.lua       -- DSL test definitions
  incremental_build.json      -- Generated JSON IR
  test_dict.lua               -- Dict runtime test harness
  user_functions_dict.lua     -- User functions (dict style)
  stream_test_1_ffi.lua       -- FFI schema for streaming packets
  drone_control_ffi.lua       -- FFI schema for drone control packets
```

## Running Tests

```bash
cd chain_tree_luajit

# By name
luajit dsl_tests/incremental_binary/test_dict.lua first_test

# By index
luajit dsl_tests/incremental_binary/test_dict.lua 0
```

## Test Index

| Index | Name | Coverage |
|-------|------|----------|
| 0 | first_test | Valve activation, wait_time, wait_for_event, send_named_event, verify, verify_timeout |
| 1 | second_test | Gate node with auto-start columns |
| 2 | fourth_test | Column with log messages and reset |
| 3 | fifth_test | State machine -- sequential state transitions |
| 4 | sixth_test | Fork columns -- parallel execution |
| 5 | seventh_test | Fork-join columns -- parallel with join wait |
| 6 | eighth_test | Sequence-til-pass -- advance on success |
| 7 | ninth_test | Sequence-til-fail -- advance on failure |
| 8 | tenth_test | Supervisor -- one_for_one, one_for_all, rest_for_all, failure_window |
| 9 | eleventh_test | For loop column |
| 10 | twelfth_test | While loop column |
| 11 | thirteenth_test | Watchdog timer |
| 12 | fourteenth_test | Data flow mask -- event filtering with bitmask |
| 13 | seventeenth_test | Exception handler -- try/catch/recovery/finalize |
| 14 | eighteenth_test | Exception handler with heartbeat monitoring |
| 15 | ninteenth_test | State machine -- sequential, parallel, nested, event filtering |
| 16 | twentieth_test | Bitmask wait and verify |
| 17 | twenty_first_test | Test start/stop control |
| 18 | twenty_second_test | Streaming -- Avro packet generation and verification |
| 19 | twenty_third_test | Streaming -- const Avro packet |
| 20 | twenty_fourth_test | Streaming -- tap/filter/sink pipeline |
| 21 | twenty_fifth_test | Streaming -- transform (accumulate/average) |
| 22 | twenty_sixth_test | Streaming -- collector with multi-port |
| 23 | twenty_seventh_test | Streaming -- verify with range check |
| 24 | twenty_eighth_test | Controlled nodes -- drone control client/server |
| 25 | twenty_ninth_test | Blackboard -- field init, verify basic/nested/const/ptr64 |

## Key User Functions

### One-shot

- `ACTIVATE_VALVE` -- prints valve state
- `WAIT_FOR_EVENT_ERROR` / `VERIFY_ERROR` -- error handlers
- `INITIALIZE_SEQUENCE` / `DISPLAY_SEQUENCE_TILL_RESULT` / `DISPLAY_SEQUENCE_RESULT` -- sequence finalization
- `DISPLAY_FAILURE_WINDOW_RESULT` -- supervisor failure display
- `WATCH_DOG_TIME_OUT` -- watchdog timeout handler
- `EXCEPTION_LOGGING` -- exception detail printer
- `BB_INIT_FIELDS` / `BB_VERIFY_*` -- blackboard test functions
- `GENERATE_AVRO_PACKET` / `GENERATE_CONST_AVRO_PACKET` -- streaming packet generators
- `PACKET_GENERATOR` -- streaming pipeline source

### Boolean

- `WHILE_TEST` -- loop condition with count from user_data
- `CATCH_ALL_EXCEPTION` / `EXCEPTION_FILTER` -- exception handling
- `USER_SKIP_CONDITION` -- recovery step evaluation
- `DRONE_CONTROL_EXCEPTION_CATCH` -- drone exception handler
- `PACKET_FILTER` / `PACKET_TAP` / `PACKET_TRANSFORM` -- streaming pipeline stages
- `PACKET_SINK_A` / `PACKET_SINK_B` / `PACKET_COLLECTOR` -- streaming consumers
- `PACKET_VERIFY_X_RANGE` / `PACKET_VERIFIED_SINK` -- streaming verification
- `ON_FLY_*_COMPLETE` / `fly_*_monitor` -- controlled node client/server

### Main

- `SM_EVENT_FILTERING_MAIN` -- state machine with event filtering
- `AVRO_VERIFY_PACKET` / `AVRO_VERIFY_CONST_PACKET` -- streaming packet verification

## Test Harness Structure

`test_dict.lua` follows this pattern:

1. Set up `package.path` for `runtime_dict/` modules and local user functions
2. Load JSON IR via `loader.load()`
3. Register functions: `loader.register_functions(handle_data, builtins, user_fns)`
4. Validate the selected KB: `loader.validate(handle_data, kb_name)`
5. Create handle: `ct_runtime.create({delta_time=0.1, max_ticks=5000}, handle_data)`
6. Reset, add test, run: `ct_runtime.reset()`, `ct_runtime.add_test()`, `ct_runtime.run()`
