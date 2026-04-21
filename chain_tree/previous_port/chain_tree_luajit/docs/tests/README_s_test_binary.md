# S-Engine Basic Integration Tests (Dict Runtime)

Basic S-Expression engine integration tests. 3 tests covering module lifecycle, multi-tree management, and custom blackboard loading.

## Location

```
dsl_tests/s_test_binary/
  s_engine_test.lua           -- DSL test definitions
  s_engine_test.json          -- Generated JSON IR
  test_se_dict.lua            -- Dict runtime test harness
```

## Running Tests

```bash
cd chain_tree_luajit

# By name
luajit dsl_tests/s_test_binary/test_se_dict.lua se_basic_load_test

# By index
luajit dsl_tests/s_test_binary/test_se_dict.lua 0
```

## Test Index

| Index | Name | Coverage |
|-------|------|----------|
| 0 | se_basic_load_test | Module load + single tree load/tick/terminate |
| 1 | se_multi_tree_test | Module load + two trees from same module, each in own blackboard slot |
| 2 | se_custom_bb_test | Module load + tree with custom blackboard loading (boolean override) |

## Test Details

### se_basic_load_test

Tests the fundamental S-Engine lifecycle within ChainTree:

1. Outer column wraps module scope
2. `se_module_load("state_machine_test", "USER_REGISTER_S_FUNCTIONS")` loads the module
3. `se_tree_load(...)` creates a tree instance, stores pointer in blackboard field `se_tree_ptr`
4. `se_tick("se_tree_ptr")` ticks the tree each ChainTree tick
5. After tree completes, logs message and calls `asm_terminate_system()`

### se_multi_tree_test

Same module, two tree instances in separate blackboard slots. Tests that the registry lookup works for multiple `se_tree_load` calls against the same module.

### se_custom_bb_test

Uses a custom blackboard loading boolean function (passed to `se_tree_load` as the 4th parameter). When the boolean returns true, default blackboard loading is skipped and the user function handles initialization.

## Module Registration Pattern

The test harness sets up the S-Engine bridge:

```lua
local se_bridge = require("ct_se_bridge")

-- After loading JSON IR and registering ChainTree functions:
local reg = se_bridge.create_registry(handle)

-- Register the S-Engine module definition
-- module_data comes from compiled S-Engine DSL output
se_bridge.register_def(reg, "state_machine_test", module_data, se_user_fns)
```

The `USER_REGISTER_S_FUNCTIONS` boolean (referenced in the DSL) is a ChainTree boolean function that runs during `CFL_SE_MODULE_LOAD_INIT` to register any additional SE user function tables.
