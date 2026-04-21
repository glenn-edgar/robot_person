# S-Engine Integration Test

Integration test for loading S-Expression engine modules from within the ChainTree control flow engine.

## Overview

This test demonstrates:
- Loading an s-engine module binary via a ChainTree leaf node (`se_module_load`)
- Creating s-engine tree instances and storing handles in blackboard uint64 pointer slots (`se_tree_load`)
- Module lifecycle managed by ChainTree init/term one-shots
- User function registration via a ChainTree boolean function callback

## Directory Layout

```
s_test_binary/
  main.c                          Test harness
  Makefile                        Builds and links all three libraries
  s_engine_test.lua               ChainTree DSL — defines 3 test knowledge bases
  s_engine_test.json              Generated JSON IR (from DSL)
  chaintree_handle_image.h        Generated binary image (embedded C array)
  chaintree_handle_blackboard.h   Generated blackboard offset defines
  chaintree_handle.ctb            Generated binary image (mmap-loadable)
  s_engine/
    se_test_module.lua            S-engine DSL — defines the test module + tree
    se_test_module.h              Generated module/tree/field hashes
    se_test_module_bin_32.h       Generated binary ROM (embedded C array)
    se_test_module_records.h      Generated record/field definitions
    se_test_module_user_functions.h      Generated user function prototypes
    se_test_module_user_registration.c   Generated user function registration
```

## Build Steps

### 1. Compile the s-engine module
```bash
./s_expression/s_build.sh dsl_tests/s_test_binary/s_engine/se_test_module.lua dsl_tests/s_test_binary/s_engine/
```

### 2. Generate ChainTree JSON from DSL
```bash
./s_build_json.sh dsl_tests/s_test_binary/s_engine_test.lua dsl_tests/s_test_binary/
```

### 3. Generate ChainTree binary image from JSON
```bash
./s_build_headers_binary.sh dsl_tests/s_test_binary/s_engine_test.json dsl_tests/s_test_binary/
```

### 4. Build and run
```bash
cd dsl_tests/s_test_binary
make
./main
```

## Libraries

The test links three static libraries:
- `runtime_binary/libcfl_binarycore.a` — ChainTree binary runtime
- `runtime_functions/libcfl_core_functions.a` — ChainTree node functions + s-engine bridge functions
- `s_expression/lib/libs_s_engine.a` — S-expression engine runtime

## Architecture

### Module Load Flow

1. Application registers module binary data via `cfl_se_registry_register_def()` before engine starts
2. ChainTree engine enables the `se_module_load` node
3. Init one-shot decodes `module_name` from JSON node data
4. Resolves name → binary via the registry, parses binary with `s_expr_load_from_rom()`
5. Registers function tables: builtins → cfl bridge → user (via boolean callback)
6. Validates the module
7. Term one-shot unloads the module on node termination

### Tree Load Flow

1. ChainTree engine enables the `se_tree_load` node
2. Init one-shot decodes `module_name`, `tree_name`, `bb_field_name` from JSON node data
3. Looks up the loaded module in the registry by name hash
4. Creates a tree instance via `s_expr_tree_create_by_hash()`
5. Resolves `bb_field_name` to a blackboard offset and stores the tree instance pointer
6. Term one-shot terminates the tree, frees the instance, and clears the blackboard slot

### Function Name Convention

The ChainTree DSL uses uppercase names (e.g., `CFL_SE_MODULE_LOAD_MAIN`). The binary pipeline lowercases and appends a type suffix to produce the registration name:
- `CFL_SE_MODULE_LOAD_MAIN` → `cfl_se_module_load_main_main`
- `CFL_SE_MODULE_LOAD_INIT` → `cfl_se_module_load_init_one_shot`
- `USER_REGISTER_S_FUNCTIONS` → `user_register_s_functions_boolean`

## Tests

| Test | Description |
|------|-------------|
| `se_basic_load_test` | Module load with user registration + single tree load |
| `se_multi_tree_test` | Module load + two trees in separate blackboard slots |
| `se_custom_bb_test` | Module load + tree load with custom blackboard loader boolean |
