# ChainTree JSON Schema v1.0

This document defines the intermediate representation (IR) produced by the
Lua DSL frontend and consumed by all backend code generators.

## Design Principle

```
                            ┌─── Python backend  ──→ .h/.c
                            │
Lua DSL ──→ .json (IR) ────┼─── LuaJIT backend  ──→ .h/.c
                            │
                            ├─── Zig backend     ──→ .h/.c
                            │
                            └─── Go backend      ──→ .h/.c
```

The JSON file is the **stable contract**. Frontends produce it; backends consume it.
Neither side knows about the other's implementation language.

## Top-Level Structure

```json
{
  "schema_version": "1.0",
  "total_nodes": 43,
  "kb_log_dict": { ... },
  "kb_metadata": { ... },
  "ltree_to_index": { ... },
  "event_string_table": { ... },
  "bitmask_table": { ... },
  "nodes": { ... }
}
```

## Field Reference

### `schema_version` (string, required)
Format version. Backends should check this and fail gracefully on unknown versions.

### `total_nodes` (integer, required)
Total number of indexed nodes (matches length of `ltree_to_index`).

### `kb_log_dict` (object)
Knowledge base build log. Informational only — not consumed by code generators.

### `kb_metadata` (object)
Per-KB configuration. Keyed by KB name:

```json
{
  "first_test": {
    "node_memory_factor": 10,
    "node_aliases": {
      "root": 0,
      "error_handler": 5
    }
  }
}
```

- `node_memory_factor` (integer): Memory allocation hint for runtime
- `node_aliases` (object): Named references to specific node indices

### `ltree_to_index` (object, required)
Maps ltree path strings to their original array indices:

```json
{
  "kb.first_test.GATE_root._0": 0,
  "kb.first_test.GATE_root._0.SEQ_main._1": 1
}
```

### `event_string_table` (object)
Maps event names to integer indices:

```json
{
  "SYSTEM_INIT": 0,
  "SENSOR_UPDATE": 1,
  "TIMER_EXPIRED": 2
}
```

### `bitmask_table` (object)
Maps bitmask names to bit positions:

```json
{
  "MOTOR_ENABLED": 0,
  "SENSOR_ACTIVE": 1,
  "ALARM_SET": 2
}
```

### `nodes` (object, required)
All tree nodes, keyed by ltree path. Each node contains:

```json
{
  "kb.first_test.GATE_root._0": {
    "label": "gate",
    "node_name": "GATE_root",
    "node_type": "gate",
    "label_dict": {
      "parent_ltree_name": "kb.first_test",
      "main_function_name": "Gate_Main",
      "initialization_function_name": "CFL_NULL",
      "termination_function_name": "CFL_NULL",
      "aux_function_name": "CFL_NULL",
      "links": [
        "kb.first_test.GATE_root._0.SEQ_main._1",
        "kb.first_test.GATE_root._0.SEQ_error._2"
      ]
    },
    "node_dict": {
      "auto_start": true,
      "error_function": "Handle_Error",
      "sm_node_id": "kb.first_test.SM_states._5"
    },
    "data": null
  }
}
```

#### Node Fields

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Node type label (gate, sequence, state_machine, etc.) |
| `node_name` | string | Human-readable node name |
| `node_type` | string | Node type identifier |
| `label_dict` | object | Structural metadata (parent, functions, children) |
| `node_dict` | object or null | Operational runtime configuration |
| `data` | any or null | Custom application data |

#### `label_dict` Fields

| Field | Type | Description |
|-------|------|-------------|
| `parent_ltree_name` | string | Parent node ltree path |
| `main_function_name` | string | Main function name (or "CFL_NULL") |
| `initialization_function_name` | string | Init function name (or "CFL_NULL") |
| `termination_function_name` | string | Term function name (or "CFL_NULL") |
| `aux_function_name` | string | Aux/boolean function name (or "CFL_NULL") |
| `links` | array of string or null | Child node ltree paths |

#### `node_dict` Fields (varies by node type)

| Field | Type | Resolved By |
|-------|------|-------------|
| `auto_start` | boolean | Packed into link_count bit 15 |
| `error_function` | string | → one_shot function index |
| `boolean_function` | string | → boolean function index |
| `initialize_function` | string | → one_shot function index |
| `finalize_function` | string | → one_shot function index |
| `wd_fn` | string | → one_shot function index |
| `logging_function` | string | → one_shot function index |
| `user_aux_function` | string | → boolean function index |
| `sm_node_id` | string | → node array index |
| `target_node_id` | string | → node array index |
| `parent_node_name` | string | → node array index |

## Null Handling

JSON `null` values appear in:
- `links`: null means no children (equivalent to empty array)
- `node_dict`: null means no runtime configuration
- `data`: null means no custom data

Backends must handle null for any field that can contain it.

## Compatibility

Backends should:
1. Check `schema_version` before processing
2. Ignore unknown top-level keys (forward compatibility)
3. Treat missing optional fields as their zero/empty defaults