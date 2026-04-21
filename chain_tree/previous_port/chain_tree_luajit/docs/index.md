# ChainTree LuaJIT Dict Runtime

## What is ChainTree

ChainTree is a control flow framework that unifies behavior trees, state machines, and sequential control flows. It has two execution engines:

1. **ChainTree** -- node structures walked by an iterative DFS engine. Parent nodes control child execution through enable/disable patterns.
2. **S-Expression Engine** -- flat parameter arrays evaluated by a tick-driven interpreter. Runs standalone or embedded inside ChainTree via bridge nodes.

## What is the Dict-Based Runtime

The dict-based runtime (`runtime_dict/`) is a pure LuaJIT implementation of the ChainTree engine. It replaces the earlier C-record-style LuaJIT runtime (`runtime/`) with a simpler architecture:

- Nodes are plain Lua tables keyed by ltree path strings (not integer indices)
- Functions are resolved by name from string-keyed dictionaries (not integer dispatch arrays)
- Return codes are strings (`"CFL_CONTINUE"`, `"CFL_HALT"`, etc.)
- No FFI structs for node data -- direct table access via `node.node_dict` and `node.label_dict`
- Per-node state via `handle.node_state[ltree_name]` (GC manages memory)
- Blackboard is a string-keyed Lua table (no byte offsets)

The dict runtime loads the same JSON IR produced by the Lua DSL frontend. No binary image or code generation step is needed.

## Directory Layout

```
chain_tree_luajit/
  lua_dsl/                    # DSL frontend (shared with C variant)
    chain_tree_master.lua     # Unified DSL class (all mixins)
    lua_support/              # Mixin modules (column_flow, s_engine, etc.)
  runtime_dict/               # Dict-based runtime modules
    ct_runtime.lua            # Event loop: create, reset, run
    ct_engine.lua             # Node execution: walker dispatch, init/main/term
    ct_loader.lua             # JSON IR loader, function registration
    ct_walker.lua             # Iterative DFS tree walker
    ct_common.lua             # Node helpers: children, enable/disable, node state
    ct_definitions.lua        # Constants: return codes, event IDs, walker codes
    ct_builtins.lua           # All built-in main/boolean/one-shot functions
    ct_se_bridge.lua          # S-Expression engine bridge
  s_expression/               # S-Engine LuaJIT runtime (separate subsystem)
  dsl_tests/                  # Test suites
    incremental_binary/       # 26 ChainTree integration tests
    s_test_binary/            # 3 S-Engine basic integration tests
    s_engine_test_2/          # 3 S-Engine advanced integration tests
  s_build_json.sh             # DSL-to-JSON build script
```

## Quick Start

### Generate JSON IR from DSL

```bash
cd chain_tree_luajit
./s_build_json.sh dsl_tests/incremental_binary/incremental_build.lua dsl_tests/incremental_binary
```

### Run tests with the dict runtime

```bash
# Run a specific test by name
luajit dsl_tests/incremental_binary/test_dict.lua first_test

# Run a specific test by index
luajit dsl_tests/incremental_binary/test_dict.lua 0

# S-Engine integration tests
luajit dsl_tests/s_test_binary/test_se_dict.lua se_basic_load_test
luajit dsl_tests/s_engine_test_2/test_se2_dict.lua twenty_ninth_test
```

## Prerequisites

- **LuaJIT** -- required for both DSL frontend and runtime
- **lua-cjson** (5.1) -- required for JSON IR loading
