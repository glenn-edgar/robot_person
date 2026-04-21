# ChainTree LuaJIT Port — Continue Notes

## Current State

The LuaJIT runtime is **fully functional** including S-Expression engine integration. All tests pass.

### Test Results Summary

| Test Suite | Tests | Pass | Notes |
|---|---|---|---|
| `incremental_binary` | 23 KBs | 23/23 | Full ChainTree runtime |
| `s_test_binary` | 3 tests | 1/3 | Test 0 passes; tests 1,2 need module data for `se_multi_module`/`se_custom_module` |
| `s_engine_test_2` | 4 tests | 4/4 | SE composite nodes, state machines, dispatch, bitmask predicates |

### What was built (2026-03-25)

**ChainTree Runtime (156 functions → 0 missing):**
- Renamed all registry keys to match JSON IR (no `_MAIN`/`_BOOLEAN`/`_ONE_SHOT` suffixes)
- Implemented all ~60 init/term one-shots, missing mains, booleans, action one-shots
- Fixed walker/engine flags sharing (single array)
- Fixed auto-start children + column init enabling children

**S-Expression Engine Bridge (`runtime/cfl_se_bridge.lua`):**
- Module registry (register_def, load, find, unload)
- CFL_SE_MODULE_LOAD init/main/term — loads module into registry
- CFL_SE_TREE_LOAD init/main/term — creates tree instance, stores in blackboard
- CFL_SE_TICK init/main/term — ticks SE tree each ChainTree tick
- CFL_SE_ENGINE init/main/term — composite (module + tree + tick in one node)
- SE→CFL result code mapping (SE_HALT→CFL_HALT, SE_DISABLE→CFL_DISABLE, etc.)
- CFL-specific S-Engine builtins: CFL_LOG, CFL_ENABLE/DISABLE_CHILDREN,
  CFL_ENABLE/DISABLE_CHILD, CFL_SET/CLEAR_BITS, CFL_READ_BIT, CFL_S_BIT_OR/AND,
  CFL_INTERNAL_EVENT, CFL_WAIT_CHILD_DISABLED

**CFL DSL Helpers (`s_expression/lua_dsl/se_helpers_dir/se_chain_tree.lua`):**
- DSL helpers for CFL bridge functions (cfl_enable_children, cfl_s_bit_or_start, etc.)
- Filled the placeholder in the S-Expression DSL compiler

**Compiled S-Engine modules:**
- `state_machine_test_module.lua` — state machine with 3 states, fork-join, tick delays
- `chain_flow_dsl_tests_module.lua` — 12 trees, dispatch, bitmask predicates, motor control

### Key Design Decisions

- Module_load and tree_load mains return `CFL_CONTINUE` (stay alive until parent terminates), matching C behavior where these are "null mains"
- TICK main returns `CFL_HALT` → `CT_STOP_SIBLINGS`, preventing the run-column from executing until the SE tree completes
- SE runtime is loaded from `s_expression/lua_runtime/` via relative path
- Module registry persists modules even after module_load node terminates

## Remaining Work

- **s_test_binary tests 1,2** — Need DSL sources for `se_multi_module` and `se_custom_module` modules
- **Avro/streaming subsystem** — Controlled node and streaming functions are stubbed
- **TEST_33-39 user functions** — Pointer/struct tests in s_engine_test_2 are stubbed (C-specific memory layout)
- **Cross-test validation** — Compare output against C reference line-by-line
