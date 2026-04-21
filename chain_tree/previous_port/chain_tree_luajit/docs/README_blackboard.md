# Blackboard System

ChainTree provides a shared mutable blackboard for cross-KB communication, plus read-only constant records in ROM.

## ChainTree Blackboard

### DSL Definition

One blackboard per configuration, defined before any tests:

```lua
ct:define_blackboard("system_state")
    ct:bb_field("mode",        "int32",  0)
    ct:bb_field("temperature", "float",  20.0)
    ct:bb_field("debug_ptr",   "uint64", 0)
ct:end_blackboard()

ct:define_const_record("calibration")
    ct:const_field("gain",   "float",  1.5)
    ct:const_field("max",    "int32",  1000)
ct:end_const_record()
```

Supported types: `int32`, `uint32`, `uint16`, `float`, `uint64`.

### Runtime API

**Fast access (compile-time offsets from `_blackboard.h`):**
```c
#include "chaintree_handle_blackboard.h"

int32_t *mode = CFL_BB_FIELD(handle, BB_OFFSET_MODE, int32_t);
*mode = 42;
```

**Dynamic access (by name hash):**
```c
void *field = cfl_bb_field_by_name(handle, "temperature");
float *temp = (float *)field;
```

**Constant records:**
```c
const cfl_bb_const_record_t *cal = cfl_bb_const_find(handle, hash);
float gain = CFL_BB_CONST_FIELD(cal->data, GAIN_OFFSET, float);
```

### Lifecycle
- `cfl_bb_init()` — allocates from `cfl_perm`, copies defaults during `cfl_runtime_create()`
- `cfl_bb_reset()` — restores defaults during `cfl_runtime_reset()`
- If `flash_handle->bb_table` is NULL, blackboard is silently skipped (backward compatible)

### Binary Image Sections
- **BBRD** (0x0010) — field descriptors with FNV-1a hashes + typed defaults blob
- **CREC** (0x0011) — constant directory + per-record field descriptors + data blobs

## S-Expression Engine Blackboard

Each s-engine tree instance has its own blackboard, sized to its record definition.

### DSL Definition

```lua
RECORD("my_blackboard")
    FIELD("counter",     "int32")
    FIELD("temperature", "float")
    PTR64_FIELD("data",  "my_record")
END_RECORD()

start_tree("my_tree")
    use_record("my_blackboard")
    -- ...
end_tree("my_tree")
```

### Access from User Functions

```c
// By field_ref parameter (compile-time offset, fastest)
int32_t *counter = S_EXPR_GET_FIELD(inst, &params[0], int32_t);

// By name string (runtime lookup, slower)
float *temp = s_expr_blackboard_get_field_by_string(inst, "temperature");

// Raw pointer
void *bb = s_expr_tree_get_blackboard(inst);
uint16_t size = s_expr_tree_get_blackboard_size(inst);
```

### DSL Field Operations

```lua
se_set_field("counter", 42)          -- set (auto-detects int/float)
se_i_set_field("counter", 0)         -- set on init only
se_increment_field("counter", 1)     -- increment
se_decrement_field("counter", 1)     -- decrement

-- Nested field access
local c = o_call("SE_SET_FIELD_FLOAT")
    nested_field_ref("motor.position.x")
    flt(100.0)
end_call(c)
```

### Constants

```lua
CONST("defaults", "my_blackboard")
    VALUE("counter", 0)
    VALUE("temperature", 20.5)
END_CONST()

-- In tree:
cfl_copy_const_full("defaults")           -- copy entire constant to blackboard
cfl_copy_const("counter", "defaults")     -- copy single field
```

## Blackboard Interaction Between Engines

When an s-engine tree runs inside ChainTree via `se_engine`:

- The **ChainTree blackboard** stores the tree instance pointer (`uint64` field)
- The **s-engine blackboard** is per-tree-instance, allocated from `cfl_heap`
- CFL bridge oneshots (`CFL_JSON_READ_*`) read ChainTree JSON node data into the s-engine blackboard
- The `CFL_SET_BITS`/`CFL_CLEAR_BITS` bridge functions modify the ChainTree bitmask, not the s-engine blackboard

```
ChainTree Blackboard              S-Engine Blackboard
┌────────────────────┐           ┌──────────────────┐
│ se_tree_ptr: uint64│──ptr──→   │ counter: int32   │
│ mode: int32        │           │ temperature: float│
│ bitmask: uint64    │           │ data_ptr: uint64  │
└────────────────────┘           └──────────────────┘
```
