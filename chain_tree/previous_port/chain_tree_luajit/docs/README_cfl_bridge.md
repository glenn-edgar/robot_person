# CFL Bridge Architecture

The CFL bridge connects the ChainTree control flow engine with the S-Expression tick-driven interpreter, allowing s-engine trees to run as ChainTree nodes.

## Architecture Overview

```
ChainTree Runtime                          S-Expression Engine
┌─────────────────────┐                   ┌──────────────────────┐
│  cfl_runtime_run()  │                   │  s_expr_node_tick()  │
│       │             │                   │       │              │
│  tree walker        │                   │  eval loop           │
│       │             │                   │       │              │
│  se_engine node ────┼── tick ──────────→│  tree instance       │
│       │             │                   │       │              │
│  children ←─────────┼── enable/disable ─│  CFL_ENABLE_CHILD    │
│                     │                   │  CFL_DISABLE_CHILDREN│
│  event queue ←──────┼── events ────────→│  CFL_INTERNAL_EVENT  │
│                     │                   │                      │
│  blackboard ←───────┼── read/write ────→│  CFL_JSON_READ_*     │
│                     │                   │  CFL_SET_BITS         │
│  bitmask ←──────────┼── predicates ────→│  CFL_S_BIT_OR/AND   │
└─────────────────────┘                   └──────────────────────┘
```

## Node Types

### se_engine (Composite)
Self-contained s-engine lifecycle. Init loads module, creates tree. Main ticks the tree. Term frees tree, unloads module. Children are ChainTree nodes controlled by the s-engine via `cfl_enable_child`/`cfl_disable_children`.

```
Init:  load module → create tree → store ptr in BB → set user_ctx
Main:  tick tree → process event queue → map result codes
Term:  free tree → unload module (engine handles child termination)
```

Children are **NOT** enabled by init. The s-engine tree decides when to enable them.

### se_engine_link (Leaf)
Same as se_engine but used as a leaf in a column with `define_join_link`. No children. Returns `CFL_CONTINUE` while running, `CFL_DISABLE` when tree completes.

### se_tick (Leaf, Legacy)
Standalone tick node. Requires separate `se_module_load` and `se_tree_load` siblings. Returns `CFL_HALT` while running (holds column position), `CFL_DISABLE` when done.

## Return Code Mapping

The bridge maps s-engine result codes to ChainTree return codes differently for composite vs leaf:

| S-Engine Result | se_engine (Composite) | se_tick (Leaf) |
|----------------|----------------------|----------------|
| SE_FUNCTION_HALT | CFL_CONTINUE | CFL_HALT |
| SE_FUNCTION_CONTINUE | CFL_CONTINUE | CFL_HALT |
| SE_FUNCTION_TERMINATE | CFL_DISABLE | CFL_DISABLE |
| SE_FUNCTION_DISABLE | CFL_DISABLE | CFL_DISABLE |
| SE_FUNCTION_RESET | CFL_CONTINUE + reset | CFL_HALT + reset |
| SE_PIPELINE_* | CFL_CONTINUE | CFL_HALT |
| SE_CONTINUE | CFL_CONTINUE | CFL_HALT |
| SE_HALT | CFL_HALT | CFL_HALT |
| SE_DISABLE | CFL_DISABLE | CFL_DISABLE |
| SE_TERMINATE | CFL_TERMINATE | CFL_TERMINATE |

**Key difference:** Composites return `CFL_CONTINUE` so the tree walker visits and ticks their children. Leaves return `CFL_HALT` to hold their position in a column.

## Module Registry

The app registers s-engine module binaries before the engine starts:

```c
// Without user functions
cfl_se_registry_register_def(reg, "module_name",
    module_bin_32, MODULE_BIN_32_SIZE);

// With user function registration callback
cfl_se_registry_register_def_with_user(reg, "module_name",
    module_bin_32, MODULE_BIN_32_SIZE,
    user_register_wrapper, NULL);
```

When `se_engine` init fires, it:
1. Looks up the module by FNV-1a hash of the name
2. Parses the binary with `s_expr_load_from_rom()`
3. Registers function tables: builtins → CFL bridge → user (via callback)
4. Validates all functions resolved
5. Creates the tree instance with `ct_node_id` = composite's node index

Modules are shared — if two `se_engine` nodes reference the same module, it's loaded once.

## Event Flow

```
ChainTree timer tick (event_id=4)
    → se_engine_main_fn receives event_id=4
    → passes directly to s_expr_node_tick(tree, 4, event_data)
    → s-engine processes:
        - builtin delays check event_id == SE_EVENT_TICK (4)
        - event dispatch matches on event_id
        - CFL_INTERNAL_EVENT posts to ChainTree queue
    → ChainTree delivers queued events on next tick cycle
    → se_engine_main_fn receives custom event_id (e.g., 0xEE04)
    → passes to s_expr_node_tick(tree, 0xEE04, event_data)
```

**SE_EVENT_TICK = 4** (same as CFL_TIMER_EVENT). No mapping — events pass through directly.

## CFL Bridge Functions

Registered automatically via `cfl_se_get_oneshot_table()`, `cfl_se_get_pred_table()`, `cfl_se_get_main_table()`. NOT registered by user code.

### Oneshots (control ChainTree from s-engine)
| Function | Params | Description |
|----------|--------|-------------|
| CFL_ENABLE_CHILDREN | none | Enable all children of ct_node_id |
| CFL_DISABLE_CHILDREN | none | Disable all children |
| CFL_ENABLE_CHILD | int(index) | Enable child by link index |
| CFL_DISABLE_CHILD | int(index) | Disable child by link index |
| CFL_INTERNAL_EVENT | int(event_id), int(data) | Post to ChainTree event queue |
| CFL_LOG | str_ptr(msg) | Log with timestamp and ct_node_id |
| CFL_SET_BITS | int... | Set bitmask bits |
| CFL_CLEAR_BITS | int... | Clear bitmask bits |
| CFL_JSON_READ_INT | field_ref, str_ptr(path) | Read JSON int → blackboard |
| CFL_JSON_READ_UINT | field_ref, str_ptr(path) | Read JSON uint → blackboard |
| CFL_JSON_READ_FLOAT | field_ref, str_ptr(path) | Read JSON float → blackboard |
| CFL_JSON_READ_BOOL | field_ref, str_ptr(path) | Read JSON bool → blackboard |
| CFL_JSON_READ_STRING_BUF | field_ref, str_ptr(path) | Read JSON string → char array |
| CFL_JSON_READ_STRING_PTR | field_ref, str_ptr(path) | Read JSON string → char* pointer |
| CFL_COPY_CONST | field_ref, const_ref | Copy ROM constant to field |
| CFL_COPY_CONST_FULL | const_ref | Copy ROM constant to entire blackboard |

### Predicates (read ChainTree state from s-engine)
| Function | Params | Description |
|----------|--------|-------------|
| CFL_READ_BIT | int(bit_index) | Read single bitmask bit |
| CFL_S_BIT_OR | int/pred... | OR over bit indices and/or nested predicates |
| CFL_S_BIT_AND | int/pred... | AND over bits/predicates |
| CFL_S_BIT_NOR | int/pred... | NOR |
| CFL_S_BIT_NAND | int/pred... | NAND |
| CFL_S_BIT_XOR | int/pred... | XOR |

### Main (tick-level ChainTree interaction)
| Function | Params | Description |
|----------|--------|-------------|
| CFL_WAIT_CHILD_DISABLED | int(child_index) | HALT until child disabled |

## User Registration Override

The s-engine compiler treats any non-`SE_` function as a "user" function. When using ChainTree integration, the generated `_user_registration.c` includes CFL bridge symbols that don't exist as linkable C functions (they're static in the bridge tables).

**Solution:** After each `s_build.sh` run, replace `_user_registration.c` with a manual version that only registers true user functions:

```c
void my_module_register_all(s_expr_module_t* module) {
    s_expr_module_register_oneshot(module, &user_oneshot_table);
    s_expr_module_register_main(module, &user_main_table);
    // Do NOT register CFL bridge functions here
}
```

## Key Files

| File | Description |
|------|-------------|
| `runtime_functions/src/cfl_se_module_registry.c` | Bridge implementation — all node types |
| `runtime_functions/include/cfl_se_module_registry.h` | Data structures and API |
| `runtime_functions/src/cfl_se_oneshot_functions.c` | CFL bridge oneshot functions |
| `runtime_functions/src/cfl_se_pred_functions.c` | CFL bridge predicate functions |
| `runtime_functions/src/cfl_se_main_functions.c` | CFL bridge main functions |
| `lua_dsl/lua_support/s_engine.lua` | DSL helpers (se_engine, se_engine_link, se_tick) |
| `s_expression/lua_dsl/se_helpers_dir/se_chain_tree.lua` | CFL bridge DSL helpers |
