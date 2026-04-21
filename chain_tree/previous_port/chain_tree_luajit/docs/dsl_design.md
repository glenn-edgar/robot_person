# DSL Design

The Lua DSL frontend compiles ChainTree definitions into JSON IR. The dict runtime loads this JSON directly -- no binary image or C code generation is needed.

## chain_tree_master.lua

The unified DSL class. Composes all mixin modules into a single metatable via method copying (first writer wins). Inherits from `ColumnFlow` as the base class.

Mixin modules (from `lua_support/`):

| Module | Purpose |
|--------|---------|
| `column_flow.lua` | `define_column`, `define_column_link`, `end_column` -- core column/leaf structure |
| `basic_cf_links.lua` | `asm_log_message`, `asm_halt`, `asm_terminate`, `asm_terminate_system`, `asm_disable` |
| `wait_cf_links.lua` | `asm_wait_time`, `asm_wait_for_event` |
| `verify_cf_links.lua` | `asm_verify`, `asm_verify_bitmask` |
| `state_machine.lua` | `define_state_machine`, `define_state`, `end_state_machine` |
| `sequence_till.lua` | `define_sequence_pass`, `define_sequence_fail`, `asm_mark_sequence` |
| `data_flow.lua` | `asm_set_bitmask`, `asm_clear_bitmask`, `asm_df_mask` |
| `exception_handler.lua` | `define_exception_handler`, `asm_raise_exception` |
| `streaming.lua` | `asm_tap`, `asm_filter`, `asm_sink`, `asm_transform`, `asm_collect`, `asm_verify_stream` |
| `controlled_nodes.lua` | `define_controlled_node`, `asm_controlled_link` |
| `s_expression_nodes.lua` | Legacy S-Expression node helpers |
| `s_engine.lua` | `se_module_load`, `se_tree_load`, `se_tick`, `se_engine`, `se_engine_link` |

## Key DSL Methods

### Column structure

```lua
local col = ct:define_column("name", main_fn, init_fn, term_fn, aux_fn, data, auto_start)
    ct:asm_log_message("hello")
    ct:asm_wait_time(1.5)
    ct:asm_terminate_system()
ct:end_column(col)
```

`define_column` creates a parent node with children. `define_column_link` creates a leaf node (no children). `auto_start` controls whether the column is enabled when its parent initializes.

### Basic links

- `asm_log_message(msg)` -- leaf: prints timestamped message, disables
- `asm_wait_time(seconds)` -- leaf: halts until timestamp exceeded, disables
- `asm_halt()` -- leaf: returns CFL_HALT every tick
- `asm_terminate_system()` -- leaf: returns CFL_TERMINATE_SYSTEM (stops engine)

### S-Engine integration

```lua
-- Load module, create tree, tick it
ct:se_module_load("module_name", "USER_REGISTER_FN")
ct:se_tree_load("module_name", "tree_name", "bb_field")
ct:se_tick("bb_field")

-- Self-contained composite: module + tree + tick + controlled children
local eng = ct:se_engine("module_name", "tree_name", "bb_field")
    ct:asm_log_message("controlled by s-engine")
    ct:asm_halt()
ct:end_se_engine(eng)

-- Self-contained leaf (no children): runs tree to completion
ct:se_engine_link("module_name", "tree_name", "bb_field")
```

## Build Pipeline

```
DSL .lua file  --->  s_build_json.sh  --->  .json IR file
                     (runs luajit)
```

The script sets `LUA_PATH` to resolve `lua_dsl/lua_support/` modules, then executes the DSL file which calls `ct:generate_json(output_path)` to emit the JSON IR.

## JSON IR Schema

The JSON IR (schema version "1.0") is the stable contract between DSL and all backends. Top-level keys:

```json
{
  "schema_version": "1.0",
  "nodes": {
    "<ltree_path>": {
      "label_dict": {
        "ltree_name": "<ltree_path>",
        "main_function_name": "CFL_COLUMN_MAIN",
        "initialization_function_name": "CFL_COLUMN_INIT",
        "termination_function_name": "CFL_COLUMN_TERM",
        "aux_function_name": "CFL_NULL",
        "links": ["<child_ltree_1>", "<child_ltree_2>"],
        "parent": "<parent_ltree>"
      },
      "node_dict": {
        "column_data": { ... }
      }
    }
  },
  "ltree_to_index": { "<ltree_path>": 0 },
  "kb_metadata": { "<kb_name>": { "root_node": "<ltree_path>", ... } },
  "event_string_table": { "CFL_TIMER_EVENT": 4, ... },
  "bitmask_table": { ... },
  "blackboard": {
    "field_defaults": { ... },
    "const_records": { ... }
  }
}
```

Each node has a `label_dict` (function names, links, parent) and a `node_dict` (runtime configuration data). The loader resolves function names to actual Lua function references at registration time.
