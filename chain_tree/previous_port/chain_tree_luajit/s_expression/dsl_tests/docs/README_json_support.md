# S-Engine JSON Dictionary System — LuaJIT Runtime

## Overview

The S-Engine JSON dictionary system provides **structured configuration data** for the ChainTree LuaJIT runtime. Lua tables from the YAML/JSON DSL pipeline are compiled into inline parameter token sequences (`dict_start`, `dict_key`, value, `end_dict_key`, `dict_end`) stored in `node.params`. At runtime, `se_load_dictionary` parses these tokens into plain Lua tables and stores them in the blackboard. Extraction builtins then navigate these tables to populate individual blackboard fields.

## Strategy

The system follows a three-layer architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│  DSL / Pipeline Layer                                           │
│  - YAML/JSON → LuaJIT pipeline compiles config into             │
│    dict_start/dict_key/value/end_dict_key/dict_end tokens       │
│    stored in node.params arrays                                 │
├─────────────────────────────────────────────────────────────────┤
│  Oneshot Functions (se_builtins_dict.lua)                       │
│  - se_load_dictionary, se_dict_extract_int, etc.                │
│  - Parse tokens → Lua tables, navigate and extract values       │
├─────────────────────────────────────────────────────────────────┤
│  Navigation Helpers (se_builtins_dict.lua internal)             │
│  - parse_dict / parse_array — token stream → Lua table          │
│  - navigate_str_path — dot-path navigation                      │
│  - navigate_hash_path — FNV-1a hash-path navigation             │
│  - s_expr_hash — LuaJIT-safe FNV-1a 32-bit hash                │
└─────────────────────────────────────────────────────────────────┘
```

### Core Concept

1. **Load**: Parse inline `dict_start..dict_end` tokens from `node.params` into a plain Lua table and store it in a blackboard field.
2. **Extract**: Navigation functions walk the Lua table by dot-path or hash-path to locate a value.
3. **Store**: The extracted value (converted to the requested type) is written into a destination blackboard field.

In the LuaJIT runtime, dictionaries are **live Lua tables** in the blackboard — not ROM pointers. The parsing happens once (in the `se_load_dictionary` oneshot), and all subsequent extractions operate on native Lua table lookups. This trades the C version's zero-copy ROM residence for Lua's fast hash-table access and dynamic typing.

## File Organization

```
├── se_builtins_dict.lua          # Dictionary load, extract, navigate, hash
├── se_builtins_oneshot.lua       # General oneshot functions (field writes, logging)
├── se_builtins_spawn.lua         # se_load_function, se_exec_dict_*, function dict dispatch
├── se_runtime.lua                # Core engine, param accessors, field_get/field_set
└── se_stack.lua                  # Parameter stack (used by quad operand reads)
```

All dictionary functionality lives in `se_builtins_dict.lua`. The spawn module (`se_builtins_spawn.lua`) handles function dictionary dispatch (`se_exec_dict_dispatch`, `se_exec_dict_fn_ptr`, `se_exec_dict_internal`).

## Token Format in node.params

The pipeline compiles dictionary literals into a token sequence stored in `node.params`:

| Token Type | `params[i].type` | `params[i].value` | Description |
|------------|------------------|--------------------|-------------|
| `dict_start` | `"dict_start"` | — | Dictionary open |
| `dict_end` | `"dict_end"` | — | Dictionary close |
| `dict_key` | `"dict_key"` | string (key name) | String-keyed entry |
| `dict_key_hash` | `"dict_key_hash"` | number (FNV-1a hash) | Hash-keyed entry |
| `end_dict_key` | `"end_dict_key"` | — | Key entry terminator |
| `array_start` | `"array_start"` | — | Array open |
| `array_end` | `"array_end"` | — | Array close |
| `int` | `"int"` | number | Signed integer value |
| `uint` | `"uint"` | number | Unsigned integer value |
| `float` | `"float"` | number | Float value |
| `str_idx` | `"str_idx"` | string | String value (interned) |
| `str_ptr` | `"str_ptr"` | string | String value (pointer) |
| `str_hash` | `"str_hash"` | `{hash=N, str=S}` | String with precomputed hash |

## Parsing: Tokens → Lua Tables

The `parse_dict` and `parse_array` functions in `se_builtins_dict.lua` are mutually recursive parsers that walk the token sequence and produce plain Lua tables:

**Dictionary parsing** produces tables with string keys (from `dict_key`) or numeric hash keys (from `dict_key_hash`):

```lua
-- Input tokens: dict_start, dict_key("zone"), dict_start, dict_key("id"), int(42),
--               end_dict_key, dict_end, end_dict_key, dict_end
-- Result:
{ zone = { id = 42 } }
```

**Array parsing** produces tables with 0-based numeric keys:

```lua
-- Input tokens: array_start, int(10), int(20), int(30), array_end
-- Result:
{ [0] = 10, [1] = 20, [2] = 30 }
```

**String values** are wrapped as `{str=S, hash=H}` tables with precomputed FNV-1a hashes by `parse_scalar`:

```lua
-- Input token: str_idx("idle")
-- Result:
{ str = "idle", hash = 2361389976 }
```

## DSL Helper Functions

### Dictionary Loading

```lua
-- Load dictionary with string keys (human-readable, debuggable)
se_load_dictionary(blackboard_field, lua_table)

-- Load dictionary with hash keys (same implementation in LuaJIT)
se_load_dictionary_hash(blackboard_field, lua_table)
```

In the LuaJIT runtime, both functions share the same implementation (`load_dict_impl`). The distinction between string-keyed and hash-keyed dictionaries matters at the pipeline level (which token types are emitted), but the parser handles both transparently.

### String Path Extraction

Navigate using dot-separated paths like `"system.config.timeout"`:

```lua
se_dict_extract_int(dict_field, path, dest_field)
se_dict_extract_uint(dict_field, path, dest_field)
se_dict_extract_float(dict_field, path, dest_field)
se_dict_extract_bool(dict_field, path, dest_field)
se_dict_extract_hash(dict_field, path, dest_field)
```

### Hash Path Extraction

Navigate using pre-computed key hashes. In the node.params, each path segment is a `str_hash` param carrying `{hash=N, str=S}`. The last param is a `field_ref` for the destination:

```lua
se_dict_extract_int_h(dict_field, {"key1", "key2", "key3"}, dest_field)
se_dict_extract_uint_h(dict_field, {"key1", "key2"}, dest_field)
se_dict_extract_float_h(dict_field, {"key1", "key2"}, dest_field)
se_dict_extract_bool_h(dict_field, {"key1", "key2"}, dest_field)
se_dict_extract_hash_h(dict_field, {"key1", "key2"}, dest_field)
```

### Sub-table Reference

Store a reference to a nested dict or array in a blackboard field for later navigation:

```lua
se_dict_store_ptr(dict_field, path, dest_field)         -- string path
se_dict_store_ptr_h(dict_field, {"key1", "key2"}, dest_field)  -- hash path
```

### Function Dictionary

Build a `{hash → closure}` dispatch table from child subtrees:

```lua
se_load_function_dict(dest_field, {
    write_register = <child subtree 1>,
    read_modify_write = <child subtree 2>,
})
```

## Builtin Parameter Layouts

### se_load_dictionary / se_load_dictionary_hash

```
params[1] = field_ref     — Destination blackboard field name
params[2] = dict_start    — Start of inline token stream
params[3..N] = tokens     — dict_key, values, end_dict_key, nested structures
params[N+1] = dict_end    — End of token stream
```

Implementation calls `parse_dict(params, 2)` and stores the result in `inst.blackboard[field_name]`.

### se_dict_extract_* (string path)

```
params[1] = field_ref     — Source dict blackboard field
params[2] = str_idx       — Dot-path string (e.g., "zone.timeout")
params[3] = field_ref     — Destination blackboard field
```

Implementation reads the dict from `inst.blackboard`, calls `navigate_str_path(dict, path)`, converts the result to the requested type, and writes to the destination field.

### se_dict_extract_*_h (hash path)

```
params[1] = field_ref     — Source dict blackboard field
params[2..N-1] = str_hash — Path key hashes ({hash=N, str=S} tables)
params[N] = field_ref     — Destination blackboard field (last field_ref found)
```

Implementation uses `collect_path_items` to gather `{hash, str}` pairs, then `navigate_hash_path` to walk the table.

### se_load_function_dict

```
params[1] = field_ref     — Destination blackboard field
params[2] = dict_start
params[3] = dict_key "fn_name_1"    → children[1]
params[4] = end_dict_key
params[5] = dict_key "fn_name_2"    → children[2]
...
params[N] = dict_end
children[1..M] = subtree roots (one per dict_key)
```

Implementation collects `dict_key` names in order, pairs each with the corresponding child, and builds `dict[s_expr_hash(name)] = closure(child)`.

## Navigation Internals

### String Path: `navigate_str_path(dict, path)`

Splits the path on `"."` and walks the table:

```lua
-- For path "zone.config.timeout":
--   cur = dict["zone"]
--   cur = cur["config"]
--   cur = cur["timeout"]
-- Returns the final value, or nil if any step fails.

-- Numeric fallback for arrays:
-- For path "items.0.id":
--   cur = dict["items"]
--   cur["0"] is nil → try tonumber("0") → cur[0]  (0-based array key)
--   cur = cur["id"]
```

### Hash Path: `navigate_hash_path(dict, path_items)`

Walks the table using a three-level fallback per path segment:

```lua
-- For each {hash=H, str=S} in path_items:
--   1. Try cur[H]          — hash key (dict_key_hash tables)
--   2. Try cur[S]          — string key fallback
--   3. Try cur[tonumber(S)] — numeric index fallback (arrays)
```

This ensures hash paths work seamlessly with both dict-keyed tables (where keys are hashes) and array-indexed tables (where keys are 0-based numbers).

### FNV-1a Hash: `s_expr_hash(str)`

LuaJIT-safe 32-bit FNV-1a hash with prime decomposition to avoid float64 overflow:

```lua
local function s_expr_hash(str)
    local h = 2166136261   -- FNV offset basis
    for i = 1, #str do
        h = bit.bxor(h, str:byte(i))
        -- 16777619 = 2^24 + 403; decompose to keep intermediates < 2^53
        h = bit.tobit(bit.lshift(h, 24) + h * 403)
    end
    if h < 0 then h = h + 4294967296 end   -- unsigned normalization
    return h
end
```

This produces identical hashes to the C `s_expr_hash()` function, ensuring cross-runtime compatibility.

## Registration

All dictionary functions are registered through the standard `merge_fns` / `register_fns` mechanism:

```lua
local se_dict = require("se_builtins_dict")
local se_spawn = require("se_builtins_spawn")

local fns = se_runtime.merge_fns(
    se_dict,    -- se_load_dictionary, se_dict_extract_*, se_load_function_dict
    se_spawn,   -- se_exec_dict_dispatch, se_exec_dict_fn_ptr, se_exec_dict_internal
    -- ... other builtin modules ...
)

local mod = se_runtime.new_module(module_data, fns)
```

Function names are matched case-insensitively (`NAME:upper()`) against the module's function lists. The module exports:

```lua
-- From se_builtins_dict.lua (M table):
M.se_load_dictionary          -- oneshot
M.se_load_dictionary_hash     -- oneshot (same impl)
M.se_dict_extract_int         -- oneshot
M.se_dict_extract_uint        -- oneshot
M.se_dict_extract_float       -- oneshot
M.se_dict_extract_bool        -- oneshot
M.se_dict_extract_hash        -- oneshot
M.se_dict_extract_int_h       -- oneshot
M.se_dict_extract_uint_h      -- oneshot
M.se_dict_extract_float_h     -- oneshot
M.se_dict_extract_bool_h      -- oneshot
M.se_dict_extract_hash_h      -- oneshot
M.se_dict_store_ptr           -- oneshot
M.se_dict_store_ptr_h         -- oneshot
M.se_load_function_dict       -- oneshot
M.s_expr_hash                 -- utility (not a registered builtin)
```

## Usage Example

### DSL Code (Pipeline Input)

```lua
local zone_config = {
    zone = {
        id = 42,
        timeout = 5000,
        threshold = 75.5,
        enabled = 1,
        state = "idle"
    },
    hardware = {
        gpio_pin = 17,
        adc_channel = 3
    }
}
```

### Tree Definition (Pipeline Output — module_data)

The pipeline compiles the above into a tree with nodes like:

```lua
{
    func_name = "se_sequence",
    call_type = "m_call",
    children = {
        -- Child 0: load dictionary
        { func_name = "se_load_dictionary", call_type = "o_call",
          params = {
            {type="field_ref", value="config_ptr"},
            {type="dict_start"},
            {type="dict_key", value="zone"},
            {type="dict_start"},
            {type="dict_key", value="id"},
            {type="uint", value=42},
            {type="end_dict_key"},
            -- ... more tokens ...
            {type="dict_end"},
            {type="end_dict_key"},
            {type="dict_end"},
          }
        },
        -- Child 1: extract uint
        { func_name = "se_dict_extract_uint", call_type = "o_call",
          params = {
            {type="field_ref", value="config_ptr"},
            {type="str_idx", value="zone.id"},
            {type="field_ref", value="zone_id"},
          }
        },
        -- ... more extraction children ...
    }
}
```

### Runtime Behavior

```lua
-- 1. se_load_dictionary fires as oneshot:
--    parse_dict(node.params, 2) → Lua table
--    inst.blackboard["config_ptr"] = { zone = { id=42, ... }, hardware = { ... } }

-- 2. se_dict_extract_uint fires as oneshot:
--    dict = inst.blackboard["config_ptr"]
--    val = navigate_str_path(dict, "zone.id")  → 42
--    inst.blackboard["zone_id"] = math.floor(math.abs(42))  → 42

-- 3. Subsequent TICK events use blackboard fields directly:
--    se_field_gt checks inst.blackboard["sensor_value"] > inst.blackboard["threshold"]
```

### Alternative with Hash Paths

```lua
-- Pipeline emits str_hash params instead of str_idx:
{ func_name = "se_dict_extract_uint_h", call_type = "o_call",
  params = {
    {type="field_ref", value="config_ptr"},
    {type="str_hash", value={hash=s_expr_hash("zone"), str="zone"}},
    {type="str_hash", value={hash=s_expr_hash("id"), str="id"}},
    {type="field_ref", value="zone_id"},
  }
}

-- Runtime: collect_path_items gathers [{hash=H1,str="zone"}, {hash=H2,str="id"}]
-- navigate_hash_path walks dict[H1]["id"] (or fallback chain) → 42
```

## Function Dictionary System

The function dictionary system allows compile-time binding of named functions to hash-keyed dispatch tables, used by the spawn module for runtime function dispatch.

### Building a Function Dictionary

`se_load_function_dict` (oneshot) pairs `dict_key` names from `node.params` with child subtrees from `node.children`:

```lua
-- For each dict_key name and corresponding child:
dict[s_expr_hash(key_name)] = function(calling_inst, exec_node, eid, edata)
    return se_runtime.invoke_any(calling_inst, child_node, eid, edata)
end
```

The resulting table is stored in `inst.blackboard[field_name]`.

### Dispatching from a Function Dictionary

Three dispatch builtins in `se_builtins_spawn.lua`:

| Function | Key Source | Description |
|----------|-----------|-------------|
| `se_exec_dict_dispatch` | Compile-time `str_hash` param | Load dict on INIT, dispatch by fixed hash key each TICK |
| `se_exec_dict_fn_ptr` | Runtime blackboard field | Load dict on INIT, read key from field each TICK |
| `se_exec_dict_internal` | Compile-time `str_hash` param | Use `inst.current_dict` (set by parent), dispatch by key |

All three look up `dict[key]`, assert the entry is a function, call it with `(inst, node, event_id, event_data)`, and convert `SE_PIPELINE_DISABLE` to `SE_PIPELINE_CONTINUE` (keeping the dict node alive across ticks).

## Creating Custom Dictionary Handlers

When the built-in extraction functions don't meet your needs, register a custom LuaJIT oneshot:

### Example: Extract Array of Integers

```lua
local function user_extract_int_array(inst, node)
    local params = node.params or {}
    assert(#params >= 4, "user_extract_int_array: need dict_field, path, base_field, count")

    -- Read parameters
    local dict_field = params[1].value   -- field_ref: blackboard key holding dict
    local path       = params[2].value   -- str_idx: dot-path to array
    local base_field = params[3].value   -- field_ref: base name for numbered fields
    local count      = params[4].value   -- uint: max elements to extract

    -- Get dict from blackboard
    local dict = inst.blackboard[dict_field]
    assert(dict and type(dict) == "table",
        "user_extract_int_array: dict not found in " .. tostring(dict_field))

    -- Navigate to array (reuse the dict module's navigation)
    local cur = dict
    for key in path:gmatch("[^%.]+") do
        if type(cur) ~= "table" then return end
        local v = cur[key]
        if v == nil then
            local n = tonumber(key)
            if n then v = cur[n] end
        end
        cur = v
    end
    if type(cur) ~= "table" then return end

    -- Extract 0-based array elements into numbered blackboard fields
    for i = 0, count - 1 do
        local v = cur[i]
        if v == nil then break end
        -- Handle {str=S, hash=H} wrappers
        if type(v) == "table" and v.str then
            v = math.floor(tonumber(v.str) or 0)
        else
            v = math.floor(tonumber(v) or 0)
        end
        inst.blackboard[base_field .. "_" .. i] = v
    end
end
```

### Register and Use

```lua
-- Register alongside standard builtins
local fns = se_runtime.merge_fns(
    require("se_builtins_dict"),
    require("se_builtins_oneshot"),
    -- ...
    { user_extract_int_array = user_extract_int_array }
)
local mod = se_runtime.new_module(module_data, fns)
```

The pipeline emits a node referencing `"user_extract_int_array"` in the module's `oneshot_funcs` list, and the engine dispatches it like any other oneshot.

## Performance Characteristics

### String Paths vs Hash Paths

| Aspect | String Paths | Hash Paths |
|--------|--------------|------------|
| Lookup | `gmatch` split + table key lookup | Direct hash key + fallback chain |
| Path parsing | Runtime dot-split (`gmatch`) | Pre-collected `{hash, str}` pairs |
| Debugging | Human-readable path strings | Requires hash↔name mapping |
| Array access | Automatic numeric fallback | Three-level fallback (hash → string → number) |
| Best for | Development, debugging, simple configs | Production, deep nesting, hot paths |

In the LuaJIT runtime, both paths ultimately resolve to Lua table lookups. The hash path advantage is smaller than in C (where it avoids `strcmp`), but it still eliminates the `gmatch` string splitting overhead.

### Memory Layout

Dictionaries are **live Lua tables** in memory after parsing. Unlike the C version where dictionaries live in ROM as flat `s_expr_param_t` arrays, the LuaJIT version allocates GC-managed tables during the `se_load_dictionary` oneshot. This trades zero-copy ROM access for faster Lua-native table lookups during extraction.

### Typical Use Pattern

```lua
-- INIT phase: load dictionary once (parses tokens → Lua table)
se_load_dictionary("config_ptr", config_table)

-- INIT phase: extract all needed values once (table lookups → blackboard writes)
se_dict_extract_int("config_ptr", "timeout", "timeout_field")
se_dict_extract_float("config_ptr", "threshold", "threshold_field")

-- TICK phase: use blackboard fields directly (no dictionary access)
se_field_gt("sensor_value", "threshold_field")
```

After extraction, the dictionary table can remain in the blackboard for dynamic access (e.g., `se_dict_store_ptr` to get sub-table references), or custom builtins can access it directly via `inst.blackboard[field]`.

## Type Conversion Rules

Each extraction function applies a specific conversion to the navigated value:

| Function | Conversion | Default |
|----------|-----------|---------|
| `se_dict_extract_int` | `math.floor(as_number(v))` | `0` |
| `se_dict_extract_uint` | `math.floor(math.abs(as_number(v)))` | `0` |
| `se_dict_extract_float` | `as_number(v) + 0.0` | `0.0` |
| `se_dict_extract_bool` | `(as_number(v) ~= 0) and 1 or 0` | `0` |
| `se_dict_extract_hash` | `as_hash(v)` — extracts `.hash` from `{str,hash}` tables | `0` |
| `se_dict_store_ptr` | Identity (must be table) | `nil` |

The `as_number` helper handles `{str=S, hash=H}` wrappers by extracting `tonumber(v.str)`, and plain values via `tonumber(v)`. The `as_hash` helper extracts `.hash` from wrapped strings, computes `s_expr_hash(v)` for plain strings, or floors numeric values.

## Error Handling

The LuaJIT runtime uses `assert` for error detection, matching the C `EXCEPTION` fail-fast model:

```lua
-- Missing blackboard field:
assert(d and type(d) == "table",
    "se_dict: blackboard field '" .. tostring(fname) ..
    "' is not a dict table (got " .. type(d) .. ")")

-- Missing hash path destination:
assert(dest and dest > 2,
    "se_dict_extract_h: missing hash path or dest field")

-- Key count / child count mismatch in function dict:
assert(#keys == #children,
    string.format("se_load_function_dict: %d keys but %d children",
        #keys, #children))
```

Navigation functions (`navigate_str_path`, `navigate_hash_path`) return `nil` for missing paths rather than asserting — the extraction builtins then apply default values (`0`, `0.0`, `nil`).

## Summary

The S-Engine LuaJIT dictionary system provides:

- **Structured configuration** — Lua tables parsed from inline param tokens, stored in blackboard fields
- **Dual navigation** — String dot-paths for readability, hash paths for performance
- **Type-safe extraction** — Dedicated builtins for int, uint, float, bool, hash, and sub-table reference
- **Function dictionaries** — Hash-keyed dispatch tables built from child subtrees, used by the spawn module
- **FNV-1a compatibility** — Identical hash output to the C implementation via LuaJIT-safe prime decomposition
- **Extensible** — Custom oneshot functions have full access to parsed Lua tables for arbitrary processing
- **Cross-runtime equivalence** — Identical behavior to the C implementation, tree by tree, result code by result code