# Incremental Binary Test (incremental_binary)

Comprehensive integration test suite for the ChainTree binary runtime. Tests all core ChainTree node types and control flow patterns using the binary image loader path.

## Overview

This is the primary ChainTree test suite — 29 tests covering columns, sequences, forks, state machines, supervisors, exceptions, streaming, bitmask operations, controlled nodes, and blackboard features. Tests are selected by commenting/uncommenting `cfl_add_test_by_index` lines in `main.c`.

## Tests

| Index | Test | Description |
|-------|------|-------------|
| 0 | first_test | Valve activation, wait_time, wait_for_event, send_named_event, verify, verify_timeout |
| 1 | second_test | Gate node with auto-start columns |
| 2 | fourth_test | Column with log messages and reset |
| 3 | fifth_test | State machine — sequential state transitions |
| 4 | sixth_test | Fork columns — parallel execution |
| 5 | seventh_test | Fork-join columns — parallel with join wait |
| 6 | eighth_test | Sequence-til-pass — advance on success |
| 7 | ninth_test | Sequence-til-fail — advance on failure |
| 8 | tenth_test | Supervisor — one_for_one, one_for_all, rest_for_all, failure_window |
| 9 | eleventh_test | For loop column |
| 10 | twelfth_test | While loop column |
| 11 | thirteenth_test | Watchdog timer |
| 12 | fourteenth_test | Data flow mask — event filtering with bitmask |
| 13 | seventeenth_test | Exception handler — try/catch/recovery/finalize |
| 14 | eighteenth_test | Exception handler with heartbeat monitoring |
| 15 | nineteenth_test | State machine — sequential, parallel, nested, event filtering |
| 16 | twentieth_test | Bitmask wait and verify |
| 17 | twenty_first_test | Test start/stop control |
| 18 | twenty_second_test | Local arena + state machine |
| 19 | twenty_third_test | Controlled node container |
| 20 | twenty_fourth_test | Streaming — packet tap, sink, filter, transform |
| 21 | twenty_fifth_test | Streaming — delayed generators + collector sink |
| 22 | twenty_sixth_test | Streaming — verified sink with packet verification |
| 23 | twenty_seventh_test | Client controlled node — drone flight patterns |
| 24 | twenty_eighth_test | Client controlled node with exceptions |
| 25 | twenty_ninth_test | Blackboard — field access, constant records, 64-bit pointers |

## Directory Layout

```
incremental_binary/
  main.c                              Test harness (incremental selection)
  Makefile                            Builds and links both libraries
  incremental_build.lua               ChainTree DSL — 29 test KBs (~2400 lines)
  incremental_build.json              Generated JSON IR
  chaintree_handle_image.h            Generated binary image
  chaintree_handle_blackboard.h       Generated blackboard offsets
  user_one_shot_functions.c           User oneshot functions
  user_boolean_functions.c            User boolean functions
  user_main_functions.c               User main functions
  user_bb_test_functions.c            Blackboard test functions
  user_avro_test_file.c               Streaming/Avro test functions
  user_node_control_boolean_fns.c     Controlled node boolean functions
  user_streaming_boolean.c            Streaming boolean functions
```

## Build Steps

```bash
# 1. Generate ChainTree JSON
./s_build_json.sh dsl_tests/incremental_binary/incremental_build.lua dsl_tests/incremental_binary/

# 2. Generate binary image
./s_build_headers_binary.sh dsl_tests/incremental_binary/incremental_build.json dsl_tests/incremental_binary/

# 3. Build and run
cd dsl_tests/incremental_binary && make clean && make
./main
```

## Test Selection

Edit `main.c` and uncomment the desired `cfl_add_test_by_index` line:
```c
//cfl_add_test_by_index(handle, 0);  // first_test
//cfl_add_test_by_index(handle, 1);  // second_test
...
cfl_add_test_by_index(handle, 25);   // twenty_ninth_test (active)
```

## Libraries

- `runtime_binary/libcfl_binarycore.a` — ChainTree binary runtime
- `runtime_functions/libcfl_core_functions.a` — ChainTree node functions

Note: This test does not use the S-Expression engine. For s-engine integration tests, see `s_test_binary` and `s_engine_test_2`.

## ChainTree Node Types Tested

- **Column** — sequential execution of children
- **Fork** — parallel execution, continues when any child active
- **Fork-Join** — parallel execution, waits for all children
- **Sequence Pass/Fail** — advance on pass or fail result
- **State Machine** — field-based state dispatch with event filtering
- **Supervisor** — one_for_one, one_for_all, rest_for_all restart strategies
- **For/While** — loop control flow
- **Watchdog** — timeout-based monitoring
- **Gate Node** — auto-start selective children
- **Data Flow Mask** — bitmask-gated event filtering
- **Exception Handler** — try/catch/recovery/finalize pattern with heartbeat
- **Controlled Node** — client-controlled enable/disable with exceptions
- **Streaming** — tap/sink/filter/transform/collect packet pipeline
- **Blackboard** — shared mutable state with constant records
