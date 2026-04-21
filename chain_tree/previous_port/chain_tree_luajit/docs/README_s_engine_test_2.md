# S-Engine Integration Test 2

Integration tests for the S-Expression engine running inside ChainTree control flow nodes.

## Overview

This test suite validates the three s-engine node types and the CFL bridge function layer:

| Node Type | DSL Helper | Description |
|-----------|------------|-------------|
| `se_engine` | `ct:se_engine(module, tree, bb_field)` | Composite — children controlled by s-engine via `cfl_enable_child`/`cfl_disable_children` |
| `se_engine_link` | `ct:se_engine_link(module, tree, bb_field)` | Leaf — runs tree to completion in a column, used with `define_join_link` |
| `se_tick` | `ct:se_tick(bb_field)` | Leaf — standalone tick node (requires separate `se_module_load` + `se_tree_load`) |

## Tests

### Test 0: twenty_ninth_test — Bitmask Trigger Composites
Two `se_engine` composites running `s_expression_test_2` (bitmask trigger with `se_trigger_on_change`). Each composite has ChainTree children (log, event_logger, halt) that are enabled/disabled by the s-engine tree based on bitmask predicate evaluation. The outer column sets and clears bitmask bits to exercise the trigger.

**S-Engine features tested:** `se_trigger_on_change`, `cfl_s_bit_or`, `cfl_s_bit_and`, `cfl_enable_children`, `cfl_disable_children`

### Test 1: thirty_test — State Machine with Child Columns
An `se_engine` composite running `s_expression_test_4` (state machine). The s-engine state machine cycles through 3 states, each enabling different ChainTree child columns. Each child column contains a `dispatch_test` s-engine that listens for `CFL_SECOND_EVENT`. A join link waits for the state machine to complete before terminating.

**S-Engine features tested:** `se_state_machine`, `se_field_dispatch`, `se_event_dispatch`, `cfl_enable_child`, `cfl_disable_children`, `se_tick_delay`, `se_set_field`

### Test 2: thirty_one_test — Field Dispatch + Event Dispatch
Two sequential `se_engine_link` nodes:
1. `s_expression_test_7` — field dispatch cycling through robot commands (FORWARD → BACK → LEFT → RIGHT → STOP), each command sets motor speeds and delays
2. `s_expression_test_8` — event dispatch handling timer, button, sensor, alarm, and shutdown events with internal event generation

**S-Engine features tested:** `se_field_dispatch`, `se_event_dispatch`, `cfl_internal_event`, `se_set_field`, `se_i_set_field`, `se_tick_delay`, user main/oneshot functions

### Test 3: thirty_two_test — Sequential Link Tests 10-16
Seven sequential `se_engine_link` nodes testing progressively complex s-engine features:

| Tree | Description |
|------|-------------|
| `s_expression_test_10` | Nested field access — set floats/ints via `SE_SET_FIELD_FLOAT`/`SE_SET_FIELD` builtins, verify with user READ functions |
| `s_expression_test_11` | Pointer fields — malloc/free node structs, store pointers in blackboard, verify read-back |
| `s_expression_test_12` | Linked list — build, traverse, free a 3-node list using pointer fields |
| `s_expression_test_13` | Pointer sharing — two fields point to same allocation, modify through one, verify through other |
| `s_expression_test_14` | Static buffer copy + JSON reads — copy ROM data, read JSON node data into blackboard fields |
| `s_expression_test_15` | Constant record copy — `cfl_copy_const_full` and `cfl_copy_const` from ROM constants |
| `s_expression_test_16` | External init — boolean function sets up blackboard before tree runs (via `aux_function_name`) |

**S-Engine features tested:** `SE_SET_FIELD_FLOAT`, `SE_SET_FIELD`, `cfl_json_read_*`, `cfl_copy_const`, `cfl_copy_const_full`, `PTR64_FIELD`, `CONST`, nested `field_ref`/`nested_field_ref`, user oneshot functions, boolean init callback

## Directory Layout

```
s_engine_test_2/
  main.c                              Test harness (cookie-cutter pattern)
  Makefile                            Builds and links all libraries
  s_engine_test_2.lua                 ChainTree DSL — defines 4 test KBs
  s_engine_test_2.json                Generated JSON IR
  chaintree_handle_image.h            Generated binary image (embedded C array)
  chaintree_handle_blackboard.h       Generated blackboard offset defines
  chaintree_handle.ctb                Generated binary image (mmap-loadable)
  s_engine_test_2_debug.yaml          Debug YAML dump
  docs/
    README_s_engine_test_2.md         This file
  s_engine/
    chain_flow_dsl_tests.lua          S-engine DSL — 12 trees in 1 module
    chain_flow_dsl_tests.h            Generated module/tree hashes
    chain_flow_dsl_tests_bin_32.h     Generated binary ROM (C array)
    chain_flow_dsl_tests_records.h    Generated record struct definitions
    chain_flow_dsl_tests_user_functions.h  Generated user function prototypes
    chain_flow_dsl_tests_user_registration.c  Manual override (user fns only)
    user_functions.c                  TEST_31/TEST_32 user functions
    user_functions_33_39.c            TEST_33 through TEST_39 user functions
```

## Build Steps

### 1. Compile the s-engine module
```bash
./s_expression/s_build.sh dsl_tests/s_engine_test_2/s_engine/chain_flow_dsl_tests.lua dsl_tests/s_engine_test_2/s_engine/
```
**Important:** After this step, restore the manual `chain_flow_dsl_tests_user_registration.c` — the compiler overwrites it with CFL bridge symbols that must not be double-registered.

### 2. Generate ChainTree JSON from DSL
```bash
./s_build_json.sh dsl_tests/s_engine_test_2/s_engine_test_2.lua dsl_tests/s_engine_test_2/
```

### 3. Generate ChainTree binary image from JSON
```bash
./s_build_headers_binary.sh dsl_tests/s_engine_test_2/s_engine_test_2.json dsl_tests/s_engine_test_2/
```

### 4. Build and run
```bash
cd dsl_tests/s_engine_test_2
make clean && make
./main 0   # twenty_ninth_test
./main 1   # thirty_test
./main 2   # thirty_one_test
./main 3   # thirty_two_test
```

## CFL Bridge Helper Functions

The s-engine DSL helpers in `s_expression/lua_dsl/se_helpers_dir/se_chain_tree.lua` wrap CFL bridge functions:

### Child Control
```lua
cfl_enable_children()           -- enable all children of ct_node_id
cfl_disable_children()          -- disable all children
cfl_i_disable_children()        -- disable all children (on init)
cfl_enable_child(index)         -- enable child by index
cfl_disable_child(index)        -- disable child by index
```

### Internal Events
```lua
cfl_internal_event(event_id, data)  -- post to ChainTree event queue
```

### Bitmask Predicates
```lua
local p = cfl_s_bit_or_start()     -- OR predicate (returns handle)
    cfl_bit_entry(0, 1)            -- bit indices
end_call(p)

local p = cfl_s_bit_and_start()    -- AND predicate
    cfl_bit_entry(2, 3)
end_call(p)
```

### JSON Reads
```lua
cfl_json_read_float("field.path", "node_dict.column_data.user_data.x")
cfl_json_read_uint("field", "json.path")
cfl_json_read_int("field", "json.path")
cfl_json_read_bool("field", "json.path")
cfl_json_read_string_buf("field", "json.path")
cfl_json_read_string_ptr("field", "json.path")
```

### Constant Record Copy
```lua
cfl_copy_const_full("const_name")           -- copy entire constant to blackboard
cfl_copy_const("field_name", "const_name")  -- copy constant to specific field
```

### Bitmask Set/Clear
```lua
cfl_set_bits(0, 1, 2)    -- set bits by index
cfl_clear_bits(3, 4)      -- clear bits by index
```

## Return Code Mapping

| S-Engine Result | CFL Result (se_engine composite) | CFL Result (se_tick leaf) |
|----------------|----------------------------------|--------------------------|
| SE_FUNCTION_HALT | CFL_CONTINUE (children tick) | CFL_HALT (hold position) |
| SE_FUNCTION_TERMINATE | CFL_DISABLE | CFL_DISABLE |
| SE_FUNCTION_CONTINUE | CFL_CONTINUE | CFL_HALT |
| SE_PIPELINE_* | CFL_CONTINUE | CFL_HALT |
| SE_CONTINUE | CFL_CONTINUE | CFL_HALT |
| SE_DISABLE | CFL_DISABLE | CFL_DISABLE |

## Known Issues

1. **User registration override**: The s-engine compiler generates `_user_registration.c` with CFL bridge function symbols. Must be manually replaced after each `s_build.sh` run — CFL bridge functions are already registered via `cfl_se_get_*_table()`.

2. **Field type restrictions**: S-engine DSL only allows `int32`, `uint32`, `float` for `FIELD()`. Use `int32` instead of `bool`, `uint32` instead of `uint16`/`uint8`. Use `PTR64_FIELD` instead of `PTR_FIELD`.

3. **SE_EVENT_TICK = 4**: Matches `CFL_TIMER_EVENT`. Events pass through directly — no mapping between ChainTree and s-engine event IDs.
