# S-Expression Engine (s_engine) — LuaJIT Outer Engine Design Document

## 1. Overview

The outer engine provides the infrastructure layer that surrounds the inner engine's dispatch core. It handles everything that happens before the first tick and after the last: loading pipeline-generated module data, resolving function names to Lua functions, allocating tree instances, managing blackboards, and providing typed access to pointer slots, fields, and strings.

Where the inner engine is concerned with *executing* a program — dispatching functions, managing node state, propagating results — the outer engine is concerned with *preparing* a program for execution and providing the runtime services that executing functions depend on.

In the LuaJIT runtime, the outer engine is dramatically simpler than its C counterpart. There is no binary loader, no allocator interface, no hash-based function binding, and no explicit memory management. Lua tables replace all of these concerns with dynamic typing, garbage collection, and string-keyed lookups.

### Outer Engine Responsibilities

- **Module creation** — wrap pipeline-generated `module_data` tables, build name→index maps, annotate tree nodes with DFS indices
- **Function registration** — resolve function names (case-insensitive) to Lua function references
- **Validation** — verify all required functions are registered before creating instances
- **Tree instance allocation** — create per-execution state with node_states, pointer slots, blackboard, and event queue
- **Blackboard management** — initialize typed records from field descriptors, provide string-keyed field access
- **Pointer slot management** — allocate Lua tables for `pt_m_call` persistent storage
- **Utility functions** — merge builtin tables, time source injection

---

## 2. Architecture

### 2.1 Component Map

```
┌──────────────────────────────────────────────────────────────┐
│  se_runtime.lua — Full Outer + Inner Engine                  │
│  ├─ new_module()      — Module creation + annotation         │
│  ├─ register_fns()    — Function binding (name → fn)         │
│  ├─ validate_module() — Verify all functions present          │
│  ├─ new_instance()    — Tree instance factory                 │
│  ├─ merge_fns()       — Combine builtin tables               │
│  ├─ tick_once()       — Inner engine entry point              │
│  ├─ invoke_main/oneshot/pred/any() — Dispatch core           │
│  ├─ child_* helpers   — Child lifecycle management           │
│  ├─ param_* helpers   — Parameter accessors                  │
│  ├─ field_get/set     — Blackboard access                    │
│  ├─ get/set_u64/f64   — Pointer slot access                  │
│  ├─ get/set_user_u64/f64 — Extended node state               │
│  └─ event_push/pop/count/clear — Event queue                 │
├──────────────────────────────────────────────────────────────┤
│  module_data (Lua table) — Pipeline Output                   │
│  ├─ trees: { [name] = tree_def }                             │
│  ├─ tree_order: { name1, name2, ... }                        │
│  ├─ oneshot_funcs, main_funcs, pred_funcs: name lists         │
│  ├─ records: { [name] = { fields = { ... } } }              │
│  └─ constants: { ... }                                        │
└──────────────────────────────────────────────────────────────┘
```

Unlike the C implementation which splits outer engine concerns across `s_engine_init.h`, `s_engine_module.h`, and `s_engine_loader.h`, the LuaJIT runtime consolidates everything into `se_runtime.lua`. The pipeline output (`module_data`) replaces the SEXB binary loader entirely.

### 2.2 Ownership Model

The LuaJIT runtime uses Lua's garbage collector for all memory management. There is no explicit ownership tracking, no free functions, and no allocator interface:

| Resource | Created By | Freed By |
|----------|-----------|----------|
| `mod` (module table) | `new_module()` | GC when unreferenced |
| `inst` (tree instance) | `new_instance()` | GC when unreferenced |
| `inst.node_states` | `new_instance()` | GC (part of inst) |
| `inst.pointer_array` | `new_instance()` | GC (part of inst) |
| `inst.blackboard` | `new_instance()` | GC (part of inst) |
| `inst.event_queue` | `new_instance()` | GC (part of inst) |
| `inst.stack` | Caller (optional) | GC when unreferenced |
| `module_data` | Pipeline | GC when unreferenced |

There is no equivalent of the C distinction between "auto-allocated" and "externally bound" blackboards. In Lua, the blackboard is always a table on `inst`, and external code can replace or augment it freely.

### 2.3 Comparison with C Outer Engine

| C Outer Engine | LuaJIT Equivalent |
|---------------|-------------------|
| SEXB binary loader (`s_engine_loader.c`) | Not needed — `module_data` is a Lua table |
| `s_engine_handle_t` | Not needed — `mod` table serves this role |
| `s_expr_allocator_t` interface | Not needed — Lua GC handles all allocation |
| Hash-based function binding (`{hash, fn_ptr}` tables) | Name-based binding (`register_fns` with case-insensitive matching) |
| Static registries (file-scope globals, max 8 tables) | Per-module function arrays (no global state) |
| `s_expr_skip_param()` / brace navigation | Not needed — children pre-separated by pipeline |
| `s_expr_tree_free()` explicit cleanup | Not needed — GC handles cleanup |
| `s_expr_blackboard_get_field_by_hash()` | `inst.blackboard[field_name]` (string key) |
| `slot_flags[]` ownership tracking | Not needed — Lua tables have no ownership semantics |
| `EXCEPTION()` fatal error handler | `assert()` / `error()` with Lua error propagation |

---

## 3. Module Creation

### 3.1 `new_module(module_data, initial_fns)`

The primary entry point for creating a runtime module. Takes the pipeline-generated `module_data` table and an optional initial function table:

```lua
local mod = se_runtime.new_module(module_data, fns)
```

This function performs several setup steps:

**1. Build name→index maps**

For each function type (oneshot, main, pred), create a lookup table mapping `NAME:upper()` to its 0-based index in the module's function list:

```lua
-- From module_data.main_funcs = {"se_sequence", "se_fork", "se_chain_flow"}
-- Builds: mod._main_idx = { SE_SEQUENCE=0, SE_FORK=1, SE_CHAIN_FLOW=2 }
```

**2. Annotate every tree**

DFS traversal of each tree's node hierarchy, assigning:

- `node.node_index` — 0-based pre-order DFS index (used to index `inst.node_states`)
- `node.func_index` — 0-based index into the module's function array for this call_type

```lua
local function annotate_node(node, counter, module_data)
    node.node_index = counter[1]
    counter[1] = counter[1] + 1
    -- Resolve func_index by searching the appropriate function list
    -- (oneshot_funcs, main_funcs, or pred_funcs based on call_type)
    for _, child in ipairs(node.children or {}) do
        annotate_node(child, counter, module_data)
    end
end
```

**3. Build tree hash index**

For spawn lookups (`se_spawn_tree`, `se_spawn_and_tick_tree`), build a `mod.trees_by_hash` table mapping tree name hashes to tree names:

```lua
mod.trees_by_hash = {}
for _, tree_name in ipairs(module_data.tree_order) do
    local tree = module_data.trees[tree_name]
    if tree.name_hash then
        mod.trees_by_hash[tree.name_hash] = tree_name
    end
end
```

**4. Set default time function**

```lua
mod.get_time = os.clock   -- injectable; caller can replace
```

**5. Register initial functions**

If `initial_fns` is provided, calls `register_fns(mod, initial_fns)`.

### 3.2 Module Table Structure

After `new_module()`, the `mod` table contains:

| Field | Type | Purpose |
|-------|------|---------|
| `module_data` | table | Pipeline output (trees, function lists, records, constants) |
| `oneshot_fns` | table | `[0-based index]` → Lua function (nil = not yet registered) |
| `main_fns` | table | `[0-based index]` → Lua function |
| `pred_fns` | table | `[0-based index]` → Lua function |
| `_oneshot_idx` | table | `NAME_UPPER` → 0-based index |
| `_main_idx` | table | `NAME_UPPER` → 0-based index |
| `_pred_idx` | table | `NAME_UPPER` → 0-based index |
| `trees_by_hash` | table | `[hash_number]` → tree_name string |
| `get_time` | function | Wall-clock time source (default `os.clock`) |

---

## 4. Function Registration

### 4.1 `register_fns(mod, fns)`

Adds function implementations to an existing module. Can be called multiple times before `validate_module()` / `new_instance()`:

```lua
se_runtime.register_fns(mod, fns)
```

The `fns` table maps function names to Lua functions:

```lua
{
    se_sequence = function(inst, node, event_id, event_data) ... end,
    se_log      = function(inst, node) ... end,
    se_field_eq = function(inst, node) ... end,
}
```

Registration performs **case-insensitive matching** by uppercasing the function name and looking it up in the module's name→index maps:

```lua
for raw_name, fn in pairs(fns) do
    local uname = raw_name:upper()
    -- Check all three function types
    local idx = mod._oneshot_idx[uname]
    if idx ~= nil then mod.oneshot_fns[idx] = fn end
    idx = mod._main_idx[uname]
    if idx ~= nil then mod.main_fns[idx] = fn end
    idx = mod._pred_idx[uname]
    if idx ~= nil then mod.pred_fns[idx] = fn end
end
```

**Unknown names are silently ignored.** A function table may contain entries for multiple modules; only names referenced by this module's function lists are registered. This allows a single merged table to be passed to multiple modules.

### 4.2 `merge_fns(...)`

Utility to combine multiple builtin tables into one for registration:

```lua
local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_verify"),
    require("se_builtins_spawn"),
    require("se_builtins_dict"),
    require("se_builtins_quads"),
    require("se_builtins_return_codes"),
    require("se_builtins_stack"),
    { my_custom_fn = function(inst, node, eid, edata) ... end }
)
```

Later tables overwrite earlier entries with the same key, so custom functions can override builtins.

### 4.3 Comparison with C Registration

| Aspect | C | LuaJIT |
|--------|---|--------|
| Key type | FNV-1a hash (`uint32_t`) | Function name string (uppercased) |
| Table format | `{hash, fn_ptr}` pair arrays | `{name = fn}` Lua tables |
| Lookup | Linear scan of hash arrays | Direct table key lookup |
| Registry scope | Static file-scope globals (one module at a time) | Per-module tables (multiple modules safe) |
| Max tables | 8 per function type | Unlimited (merged into one table) |
| Unknown entries | Silently skipped | Silently skipped |

The name-based approach eliminates the possibility of hash collisions and makes debugging straightforward — error messages show function names rather than hex hashes.

---

## 5. Validation

### 5.1 `validate_module(mod)`

Checks that every function required by the module has been registered. Returns two values:

```lua
local ok, missing = se_runtime.validate_module(mod)
-- ok:      boolean — true if all functions present
-- missing: table   — list of {name=, kind=} for every gap
```

The check iterates each function list and verifies the corresponding slot in the function array is non-nil:

```lua
for i, name in ipairs(md.oneshot_funcs or {}) do
    if not mod.oneshot_fns[i-1] then
        missing[#missing+1] = { name=name, kind="oneshot" }
    end
end
-- (same for main_funcs, pred_funcs)
```

Unlike the C version which does a secondary lookup through static registries during validation, the LuaJIT version has no fallback — all functions must be explicitly registered via `register_fns()` before validation.

### 5.2 Automatic Validation in `new_instance()`

`new_instance()` calls `validate_module()` internally and errors with the complete missing-function list if any gaps exist. This means the caller sees every unregistered function at once rather than hitting them one at a time during execution:

```lua
-- Error output example:
-- new_instance: unregistered functions:
--   [main] se_custom_composite
--   [oneshot] se_custom_init
--   [pred] se_custom_check
```

---

## 6. Tree Instance Lifecycle

### 6.1 Creation: `new_instance(mod, tree_name)`

Allocates all per-tree runtime state in a single `inst` table:

```lua
local inst = se_runtime.new_instance(mod, "zone_init")
```

The function performs these steps:

**1. Validate module** — calls `validate_module(mod)`, errors if any functions missing.

**2. Look up tree definition** — `module_data.trees[tree_name]`, asserts if not found.

**3. Create instance table:**

```lua
local inst = {
    mod                = mod,          -- shared module reference
    tree               = tree,         -- tree definition from module_data
    node_states        = {},           -- [0..N-1] → state tables
    node_count         = tree.node_count,
    pointer_array      = {},           -- [0..P-1] → slot tables
    pointer_count      = tree.pointer_count or 0,
    blackboard         = {},           -- [field_name] → value
    current_node_index = 0,
    current_event_id   = 0,
    current_event_data = nil,
    in_pointer_call    = false,
    pointer_base       = 0,
    stack              = nil,          -- optional, set by caller
    tick_type          = 0,
    user_ctx           = nil,          -- application-defined
}
```

**4. Initialize node states:**

Every node gets an active state table:

```lua
for i = 0, tree.node_count - 1 do
    inst.node_states[i] = { flags = 0x01, state = 0, user_data = 0 }
    -- flags = FLAG_ACTIVE (0x01)
end
```

**5. Initialize pointer array:**

Each slot is a table mimicking the C `s_expr_slot_t` union:

```lua
for i = 0, inst.pointer_count - 1 do
    inst.pointer_array[i] = { ptr = nil, u64 = 0, i64 = 0, f64 = 0.0 }
end
```

**6. Initialize blackboard from record descriptor:**

If the tree has a `record_name`, look up the record definition and populate the blackboard with field defaults:

```lua
if tree.record_name then
    local rec = module_data.records and module_data.records[tree.record_name]
    if rec and rec.fields then
        for field_name, field_def in pairs(rec.fields) do
            local dv = field_def.default
            if type(dv) == "string" then dv = tonumber(dv) or dv end
            inst.blackboard[field_name] = (dv ~= nil) and dv or 0
        end
    end
end
```

**7. Initialize event queue:**

```lua
inst.event_queue       = {}
inst.event_queue_head  = 0
inst.event_queue_count = 0
```

### 6.2 Optional Stack

The caller can attach a parameter stack after instance creation:

```lua
local se_stack = require("se_stack")
inst.stack = se_stack.new_stack(256)  -- capacity in entries
```

This is required for trees that use `se_frame_allocate`, `se_stack_frame_instance`, `se_quad` with stack operands, or `se_push_stack`.

### 6.3 User Context

The caller can set `inst.user_ctx` to any value after creation. Unlike the C version where user context is propagated automatically from the engine handle, in LuaJIT the caller sets it directly:

```lua
inst.user_ctx = my_application_state
```

Builtin functions can access this as `inst.user_ctx` during execution.

### 6.4 Time Source

Time is accessed via `inst.mod.get_time()`. The default is `os.clock`, but the caller can replace it on the module:

```lua
mod.get_time = function() return my_monotonic_clock() end
```

All instances sharing the module use the same time source. Builtins that depend on time (`se_time_delay`, `se_wait_timeout`, `se_verify_and_check_elapsed_time`) call `inst.mod.get_time()` rather than accessing `os.clock` directly.

### 6.5 Cleanup

No explicit cleanup is needed. When `inst` goes out of scope and has no remaining references, the garbage collector reclaims all associated tables (node_states, pointer_array, blackboard, event_queue, stack).

If a tree spawns child instances (`se_spawn_tree`, `se_spawn_and_tick_tree`), those children are stored in the parent's blackboard or pointer slots. When the parent is collected, the children become unreferenced and are also collected — unless the caller holds separate references.

---

## 7. Blackboard Access

The blackboard is a plain Lua table with string keys. All access is by field name — there is no byte offset or hash-based access pattern.

### 7.1 By Field Name (Primary Pattern)

Used by all builtins via the `field_get` / `field_set` helpers and by external code directly:

```lua
-- Inside builtins (via param accessor):
local v = field_get(inst, node, 1)        -- reads inst.blackboard[node.params[1].value]
field_set(inst, node, 1, 42)              -- writes inst.blackboard[node.params[1].value] = 42

-- External code:
inst.blackboard["temperature"] = 25.5
local t = inst.blackboard["temperature"]
```

### 7.2 Type Coercion

The `field_get` accessor coerces string values to numbers automatically. This handles cases where the blackboard was initialized from JSON (which may produce strings for numeric values):

```lua
local function field_get(inst, node, i)
    local v = inst.blackboard[node.params[i].value]
    if type(v) == "string" then
        local n = tonumber(v)
        if n ~= nil then return n end
    end
    return v
end
```

### 7.3 Record Initialization

When a tree references a named record, `new_instance()` populates the blackboard from the record's field definitions:

```lua
-- Record definition in module_data:
records = {
    zone_state = {
        fields = {
            config_ptr  = { type = "ptr64",  default = nil },
            zone_id     = { type = "uint32", default = 0 },
            timeout_ms  = { type = "uint32", default = 5000 },
            threshold   = { type = "float",  default = 75.5 },
            enabled     = { type = "uint32", default = 1 },
        }
    }
}

-- After new_instance():
-- inst.blackboard = { config_ptr=0, zone_id=0, timeout_ms=5000, threshold=75.5, enabled=1 }
```

### 7.4 Comparison with C Blackboard Access

| C Pattern | LuaJIT Equivalent |
|-----------|-------------------|
| `S_EXPR_GET_FIELD(inst, param, int32_t)` (byte offset) | `inst.blackboard[field_name]` |
| `s_expr_blackboard_get_field_by_hash(inst, hash)` | `inst.blackboard[field_name]` |
| `s_expr_blackboard_get_field_by_string(inst, "name")` | `inst.blackboard["name"]` |
| `s_expr_blackboard_set_int(inst, hash, value)` | `inst.blackboard[field_name] = value` |
| `memcpy` from ROM defaults | `for field_name, def in pairs(fields) do bb[name] = def.default end` |

All three C access patterns (offset, hash, string) collapse into a single string-keyed table lookup in Lua.

---

## 8. Pointer Slot Management

Pointer slots provide persistent storage for `pt_m_call` functions. Each slot is a Lua table with typed fields:

```lua
inst.pointer_array[i] = { ptr = nil, u64 = 0, i64 = 0, f64 = 0.0 }
```

### 8.1 Access from pt_m_call Functions

During `pt_m_call` dispatch, the runtime saves/restores `inst.pointer_base` and `inst.in_pointer_call`:

```lua
-- In invoke_main, for pt_m_call nodes:
inst.in_pointer_call = true
inst.pointer_base    = node.pointer_index or 0
```

Builtins then access their slot via the runtime accessors:

```lua
-- Read/write u64:
local v = se_runtime.get_u64(inst, node)   -- inst.pointer_array[inst.pointer_base].u64
se_runtime.set_u64(inst, node, v)

-- Read/write f64:
local v = se_runtime.get_f64(inst, node)   -- inst.pointer_array[inst.pointer_base].f64
se_runtime.set_f64(inst, node, v)

-- Read/write ptr (used by spawn builtins for child tree instances):
local child = inst.pointer_array[inst.pointer_base].ptr
inst.pointer_array[inst.pointer_base].ptr = child_instance
```

### 8.2 Extended Node State

For builtins that need per-node persistent storage but don't use pointer slots (m_call, not pt_m_call), the runtime provides extra fields on the node_state table:

```lua
-- user_u64 / user_f64: stored directly on node_states[node.node_index]
se_runtime.get_user_u64(inst, node)    -- inst.node_states[node.node_index].user_u64
se_runtime.set_user_u64(inst, node, v)
se_runtime.get_user_f64(inst, node)    -- inst.node_states[node.node_index].user_f64
se_runtime.set_user_f64(inst, node, v)

-- state / flags: standard node_state fields
se_runtime.get_state(inst, node)       -- inst.node_states[node.node_index].state
se_runtime.set_state(inst, node, v)
```

This is possible because Lua tables are extensible — adding `user_u64` or `user_f64` fields to a node_state table requires no pre-allocation.

### 8.3 Comparison with C Pointer Slot Management

| C Pattern | LuaJIT Equivalent |
|-----------|-------------------|
| `s_expr_slot_t` (8-byte union: ptr/u64/i64/f64) | Lua table `{ptr, u64, i64, f64}` |
| `slot_flags[]` (NONE/ALLOCATED/EXTERNAL) | Not needed — no ownership tracking |
| `s_expr_pointer_alloc(inst, idx, size)` | Direct assignment: `slot.ptr = value` |
| `s_expr_pointer_free(inst, idx)` | Direct assignment: `slot.ptr = nil` |
| `s_expr_get_pointer_slot(inst, idx)` | `inst.pointer_array[inst.pointer_base]` |
| `s_expr_tree_slot_set_ptr(inst, idx, ptr)` | `inst.pointer_array[idx].ptr = value` |

---

## 9. Parameter Navigation

The LuaJIT runtime does **not** need parameter navigation. The pipeline pre-separates callable children into `node.children[]` and non-callable parameters into `node.params[]`, eliminating the need for:

- `s_expr_skip_param()` — no flat param arrays to skip over
- `brace_idx` — no nested structures to jump past
- `s_expr_count_params()` — just use `#node.params` or `#node.children`
- `s_expr_find_param()` — direct index into `node.params[i]`
- `s_expr_iterate_params()` — standard `for i = 1, #params do`
- `s_expr_brace_contents()` — children are already separated
- `s_expr_call_func()` / `s_expr_call_args()` — function name and children are node fields

This is the single largest simplification from C to LuaJIT. The entire parameter navigation subsystem — which is the "outer engine" core in C — is replaced by the pipeline doing the work at compile time.

### 9.1 What the Pipeline Provides

Each node in the tree has its callable and non-callable content pre-separated:

```lua
{
    func_name  = "se_sequence",        -- function identity
    call_type  = "m_call",             -- dispatch type
    func_index = 3,                    -- index into mod.main_fns
    node_index = 0,                    -- DFS pre-order index

    params = {                          -- non-callable parameters only
        { type = "uint", value = 42 },
        { type = "field_ref", value = "timeout" },
        { type = "str_hash", value = { hash = 12345, str = "key" } },
    },

    children = {                        -- callable children only
        { func_name = "se_log", call_type = "o_call", ... },
        { func_name = "se_fork", call_type = "m_call", ... },
    },
}
```

Builtins access params by 1-based index (`node.params[1]`) and children by 0-based index via the `child_invoke(inst, node, idx, ...)` helper (which internally does `node.children[idx + 1]`).

---

## 10. DFS Annotation

The `annotate_node` function performs a depth-first pre-order traversal at module creation time, assigning two critical indices to each node:

### 10.1 `node_index` — State Array Index

A 0-based sequential counter assigned in DFS pre-order. Used to index `inst.node_states[node_index]` for per-node runtime state (flags, state, user_data).

### 10.2 `func_index` — Function Array Index

Resolved by searching the appropriate function name list (`oneshot_funcs`, `main_funcs`, or `pred_funcs`) for the node's `func_name`. Used to index `mod.oneshot_fns[func_index]`, `mod.main_fns[func_index]`, or `mod.pred_fns[func_index]` during dispatch.

The annotation asserts if a function name is not found in the expected list — this catches pipeline errors early, before any ticking occurs.

### 10.3 Tree Node Count

The pipeline provides `tree.node_count` which must match the total number of nodes in the DFS traversal. This is used by `new_instance()` to pre-allocate the `node_states` array.

---

## 11. Module Data Format

The `module_data` table is the pipeline's output — the LuaJIT equivalent of the C SEXB binary. It contains everything needed to create modules and instances:

### 11.1 Structure

```lua
module_data = {
    -- Tree definitions
    trees = {
        zone_init = {
            name       = "zone_init",
            name_hash  = 0xABCD1234,      -- FNV-1a for spawn lookups
            node_count = 15,               -- total nodes in DFS traversal
            pointer_count = 3,             -- pt_m_call slots needed
            record_name = "zone_state",    -- blackboard record reference
            nodes = { ... },               -- array of root nodes
        },
        -- ... more trees
    },

    -- Deterministic tree ordering (Lua tables don't guarantee iteration order)
    tree_order = { "zone_init", "zone_tick", "zone_cleanup" },

    -- Function name lists (order determines func_index)
    oneshot_funcs = { "se_log", "se_set_field", "se_load_dictionary", ... },
    main_funcs    = { "se_sequence", "se_fork", "se_chain_flow", ... },
    pred_funcs    = { "se_field_eq", "se_pred_and", "se_true", ... },

    -- Record definitions for blackboard initialization
    records = {
        zone_state = {
            fields = {
                config_ptr  = { type = "ptr64",  default = nil, offset = 0 },
                zone_id     = { type = "uint32", default = 0,   offset = 8 },
                timeout_ms  = { type = "uint32", default = 5000, offset = 12 },
                threshold   = { type = "float",  default = 75.5, offset = 16 },
            }
        }
    },

    -- Optional constants table
    constants = { ... },
}
```

### 11.2 Comparison with SEXB Binary

| SEXB Section | module_data Equivalent |
|-------------|----------------------|
| `sexb_header_t` (32 bytes) | Implicit in table structure |
| `sexb_directory_t` (8 offsets) | Not needed — direct table access |
| Tree entries (24 bytes each) | `module_data.trees[name]` tables |
| Record entries (12 bytes each) | `module_data.records[name]` tables |
| Field entries (12 bytes each) | `records[name].fields[field_name]` tables |
| String data (aligned, null-terminated) | Native Lua strings |
| Constant entries + data | `module_data.constants` table |
| Function hashes (uint32_t[]) | `module_data.oneshot_funcs` etc. (name lists) |
| Parameter arrays (s_expr_param_t[]) | `node.params[]` Lua table arrays |

The LuaJIT format trades the C format's zero-copy ROM efficiency for human-readability, dynamic typing, and simpler tooling. There is no binary parsing step — the pipeline outputs a Lua table that is directly usable.

---

## 12. Error Handling

### 12.1 Error Strategy

The LuaJIT outer engine uses `assert` and `error` for all error conditions. Unlike the C version which uses a mixed strategy (EXCEPTION for fatal errors, return codes for operational failures), the LuaJIT version raises Lua errors uniformly. The caller can wrap calls in `pcall` or `xpcall` for recovery.

### 12.2 Annotation Errors

```lua
-- Unknown function name during DFS annotation:
assert(node.func_index ~= nil,
    "annotate: unknown main function: " .. tostring(fname))
```

These fire at module creation time, catching pipeline errors before any instances are created.

### 12.3 Validation Errors

```lua
-- new_instance() with unregistered functions:
error("new_instance: unregistered functions:\n" ..
      "  [main] se_custom_composite\n" ..
      "  [oneshot] se_custom_init")
```

The full list of missing functions is reported at once, not one at a time.

### 12.4 Runtime Errors

```lua
-- Missing function during dispatch:
assert(fn, "invoke_main: no function for: " .. tostring(node.func_name))

-- Bad child index:
assert(child, "child_invoke: bad index " .. idx)

-- Missing tree for spawn:
assert(name, string.format("spawn: unknown tree hash 0x%08x", hash))
```

These fire during execution and propagate up the Lua call stack. The caller's `pcall` wrapper determines whether the error is recoverable.

### 12.3 Comparison with C Error Handling

| C Pattern | LuaJIT Equivalent |
|-----------|-------------------|
| `S_EXPR_ERR_*` error codes | Lua error strings |
| `SEXB_ERR_*` loader errors | Not applicable (no binary loader) |
| `module.error_code/hash/index` | Error message includes all details |
| `EXCEPTION()` → watchdog reset | `error()` → Lua error propagation |
| `s_engine_error_str()` | Error message is the string itself |
| `printf` diagnostics | `print()` or error message content |

---

## 13. Complete Initialization Example

```lua
local se_runtime = require("se_runtime")

-- 1. Merge all builtin modules
local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_verify"),
    require("se_builtins_spawn"),
    require("se_builtins_dict"),
    require("se_builtins_quads"),
    require("se_builtins_return_codes"),
    require("se_builtins_stack"),
    -- Custom application functions:
    { my_sensor_read = function(inst, node) ... end }
)

-- 2. Create module (annotates trees, builds maps, registers functions)
local mod = se_runtime.new_module(module_data, fns)

-- 3. Optionally inject custom time source
mod.get_time = function() return my_monotonic_clock() end

-- 4. Create tree instance (validates module, allocates state)
local inst = se_runtime.new_instance(mod, "zone_init")

-- 5. Optionally attach stack
inst.stack = require("se_stack").new_stack(256)

-- 6. Optionally set user context
inst.user_ctx = my_application_handle

-- 7. Tick loop (caller-owned)
local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
while true do
    local result = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)

    -- Drain event queue
    while se_runtime.event_count(inst) > 0 do
        local tt, eid, edata = se_runtime.event_pop(inst)
        result = se_runtime.tick_once(inst, eid, edata)
    end

    -- Check for completion
    if result == se_runtime.SE_FUNCTION_TERMINATE then break end

    -- Application-specific timing
    sleep(0.010)  -- 10ms tick period
end
```

---

## 14. Summary

The LuaJIT outer engine collapses the C outer engine's binary loader, allocator interface, hash-based function binding, explicit ownership tracking, and parameter navigation into a handful of Lua table operations. Module creation annotates a pipeline-generated tree structure and builds name→index maps. Function registration matches names case-insensitively. Validation reports all missing functions at once. Instance creation allocates node states, pointer slots, and blackboard fields as plain Lua tables. The garbage collector handles all cleanup.

The single largest simplification is the elimination of parameter navigation. Because the pipeline pre-separates callable children from non-callable parameters, the entire `s_expr_skip_param` / `brace_idx` / `s_expr_count_params` subsystem — which is the C outer engine's core contribution — is replaced by direct array indexing on `node.params` and `node.children`.