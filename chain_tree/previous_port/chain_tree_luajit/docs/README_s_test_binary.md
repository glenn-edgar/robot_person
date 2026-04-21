# S-Engine Integration Test 1 (s_test_binary)

First integration test for the S-Expression engine running inside ChainTree via the `se_tick` leaf node pipeline.

## Overview

Tests the standalone `se_module_load` → `se_tree_load` → `se_tick` pipeline where the s-engine tree runs as a leaf node in a ChainTree column. The module uses a state machine tree that cycles through states with tick delays.

## Tests

### Test 0: se_basic_load_test — State Machine Tree
Loads the `state_machine_test` s-engine module, creates a tree instance stored in the blackboard, and ticks it via `se_tick`. The s-engine tree runs a state machine (states 0→1→2→0) with `se_fork_join`, `se_fork`, `se_state_machine`, and `se_tick_delay`. Terminates after ~363 ticks.

**S-Engine features tested:** `se_function_interface`, `se_fork_join`, `se_fork`, `se_state_machine`, `se_case`, `se_tick_delay`, `se_set_field`, `se_log`, `se_return_function_terminate`

### Test 1: se_multi_tree_test — Multiple Tree Instances
Loads two tree instances from the same module into separate blackboard slots.

### Test 2: se_custom_bb_test — Custom Blackboard Loader
Tests the custom blackboard loading boolean function callback on `se_tree_load`.

## Directory Layout

```
s_test_binary/
  main.c                              Test harness
  Makefile                            Builds and links all libraries
  s_engine_test.lua                   ChainTree DSL — defines 3 test KBs
  s_engine_test.json                  Generated JSON IR
  chaintree_handle_image.h            Generated binary image
  chaintree_handle_blackboard.h       Generated blackboard offsets
  s_engine/
    state_machine_test.lua            S-engine DSL — state machine module
    state_machine_test.h              Generated hashes
    state_machine_test_bin_32.h       Generated binary ROM
```

## Build Steps

```bash
# 1. Compile s-engine module
./s_expression/s_build.sh dsl_tests/s_test_binary/s_engine/state_machine_test.lua dsl_tests/s_test_binary/s_engine/

# 2. Generate ChainTree JSON
./s_build_json.sh dsl_tests/s_test_binary/s_engine_test.lua dsl_tests/s_test_binary/

# 3. Generate binary image
./s_build_headers_binary.sh dsl_tests/s_test_binary/s_engine_test.json dsl_tests/s_test_binary/

# 4. Build and run
cd dsl_tests/s_test_binary && make clean && make
./main        # runs test 0 (default)
./main 1      # runs test 1
./main 2      # runs test 2
```

## Node Types Used

This test uses the original three-node pipeline:
- `se_module_load` — loads s-engine module binary into registry
- `se_tree_load` — creates tree instance, stores pointer in blackboard
- `se_tick` — ticks the tree each ChainTree tick

For new tests, prefer `se_engine` (composite) or `se_engine_link` (leaf) which combine all three into a single node.

## Libraries

- `runtime_binary/libcfl_binarycore.a` — ChainTree binary runtime
- `runtime_functions/libcfl_core_functions.a` — ChainTree node functions + CFL bridge
- `s_expression/lib/libs_s_engine.a` — S-expression engine runtime
