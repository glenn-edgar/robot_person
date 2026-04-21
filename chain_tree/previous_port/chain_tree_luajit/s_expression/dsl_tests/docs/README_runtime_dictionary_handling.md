# Dictionary Subsystem Design Document — LuaJIT Runtime

## 1. Overview

The dictionary subsystem provides two parallel navigation APIs for accessing nested key-value structures parsed from inline parameter token sequences in `node.params`. Both operate on the same underlying Lua tables produced by `parse_dict()` / `parse_array()` — they differ only in how keys are specified at the call site.

- **String path** (`navigate_str_path`) — keys specified as dot-separated path strings, split at runtime by `gmatch`. Designed for JSON-style configuration access and debugging convenience. Path segments are matched as string keys first, with numeric fallback for arrays.

- **Hash path** (`navigate_hash_path`) — keys specified as pre-computed `{hash, str}` pairs collected from `str_hash` params. Designed for performance-critical paths where key hashes are known at compile time. Uses a three-level fallback: hash key → string key → numeric index.

Both APIs share the same parsed table structure and provide identical typed extraction, blackboard integration, and sub-table reference capabilities. All dictionary functionality lives in `se_builtins_dict.lua`.

### Comparison with C Implementation

| C Dictionary Subsystem | LuaJIT Equivalent |
|----------------------|-------------------|
| Flat `OPEN_DICT`/`OPEN_KEY`/`CLOSE_KEY`/`CLOSE_DICT` token traversal | `parse_dict()` converts tokens to Lua table once; navigation operates on live tables |
| `brace_idx` for O(1) skip over nested structures | Not needed — Lua table nesting is implicit |
| `se_dicts_find()` / `se_dicth_find()` — linear scan of `OPEN_KEY` tokens | Lua table key lookup: `cur[key]` (hash table internally) |
| Two separate C files (`se_dict_string.c`, `se_dict_hash.c`) | Single file (`se_builtins_dict.lua`) with two navigation functions |
| Zero-copy traversal of ROM parameter arrays | Parsed once into GC-managed Lua tables, then native table lookups |
| `s_expr_param_t*` pointer returned from resolution | Plain Lua value returned (number, string wrapper, or table) |

---

## 2. Parsed Table Structure

The pipeline emits `dict_start` / `dict_key` / value / `end_dict_key` / `dict_end` token sequences in `node.params`. At runtime, `se_load_dictionary` calls `parse_dict()` which converts these tokens into plain Lua tables stored in the blackboard.

### Dictionary Tables

Keys are strings (from `dict_key` tokens) or numbers (from `dict_key_hash` tokens). Values are scalars, nested dicts, or nested arrays:

```lua
-- Parsed from token sequence:
{
    hw = {
        gpio = {
            mode = 1,
            pin = 17,
        },
        adc_channel = 3,
    },
    timeout = 5000,
    label = { str = "idle", hash = 2361389976 },
}
```

### Array Tables

Arrays use **0-based numeric keys** (not Lua's conventional 1-based indexing):

```lua
-- Parsed from array_start..array_end tokens:
{ [0] = 10, [1] = 20, [2] = 30 }
```

### String Value Wrapping

`parse_scalar()` wraps `str_idx` and `str_ptr` values as `{str=S, hash=H}` tables with precomputed FNV-1a hashes:

```lua
-- Token: {type="str_idx", value="idle"}
-- Parsed result:
{ str = "idle", hash = 2361389976 }
```

This wrapping enables `se_dict_extract_hash` to extract the hash directly and `as_number()` to attempt numeric conversion of the string content.

---

## 3. Path Resolution

### 3.1 String Path Resolution (`navigate_str_path`)

Splits a dot-separated path string on `"."` and walks the table one key at a time:

```lua
local function navigate_str_path(dict, path)
    local cur = dict
    for key in path:gmatch("[^%.]+") do
        if type(cur) ~= "table" then return nil end
        local v = cur[key]
        if v == nil then
            local n = tonumber(key)
            if n then v = cur[n] end   -- 0-based numeric fallback for arrays
        end
        cur = v
    end
    return cur
end
```

For each segment:
1. Try `cur[key]` as a string key (works for dict tables)
2. If nil, try `cur[tonumber(key)]` as a numeric key (works for array tables with 0-based indices like `"items.0.id"`)

```lua
-- Example: resolve "hw.gpio.mode" through nested dicts
local val = navigate_str_path(dict, "hw.gpio.mode")  -- → 1
```

### 3.2 Hash Path Resolution (`navigate_hash_path`)

Takes a pre-collected array of `{hash, str}` items and walks the table using a three-level fallback per segment:

```lua
local function navigate_hash_path(dict, path_items)
    local cur = dict
    for _, item in ipairs(path_items) do
        if type(cur) ~= "table" then return nil end
        local v = cur[item.hash]                       -- 1. hash key
        if v == nil and item.str then
            v = cur[item.str]                           -- 2. string key fallback
            if v == nil then
                local n = tonumber(item.str)
                if n then v = cur[n] end                -- 3. numeric index fallback
            end
        end
        cur = v
    end
    return cur
end
```

The three-level fallback handles:
- **Dict tables with hash keys** (from `dict_key_hash` pipeline output) — step 1 matches
- **Dict tables with string keys** (from `dict_key` pipeline output) — step 2 matches
- **Array tables with numeric keys** — step 3 matches (e.g., hash("0") → "0" → 0)

```lua
-- Example: same lookup, path items from str_hash params
local items = { {hash=H_hw, str="hw"}, {hash=H_gpio, str="gpio"}, {hash=H_mode, str="mode"} }
local val = navigate_hash_path(dict, items)  -- → 1
```

### 3.3 Path Item Collection (`collect_path_items`)

Hash-path extraction builtins use `collect_path_items()` to gather `{hash, str}` pairs from the node's params between the source field_ref and the destination field_ref:

```lua
local function collect_path_items(node, start_idx, end_idx)
    local items = {}
    local params = node.params or {}
    for i = start_idx, end_idx do
        local p = params[i]
        if not p then break end
        if type(p.value) == "table" then
            -- str_hash: value = {hash=N, str=S}
            items[#items + 1] = { hash = p.value.hash, str = p.value.str }
        else
            -- dict_key_hash: plain number
            items[#items + 1] = { hash = p.value, str = nil }
        end
    end
    return items
end
```

### 3.4 Single-Level Lookup Performance

In the C implementation, single-level lookup is a linear scan through `OPEN_KEY` tokens comparing `str_hash` values — O(n) in the number of keys at that level.

In LuaJIT, single-level lookup is a **Lua table key access** — `cur[key]` — which is a hash table lookup internally, giving amortized O(1) per level. This is a significant performance improvement over the C version for dictionaries with many keys at the same level.

---

## 4. Typed Value Extraction

Both path types share the same set of extraction builtins. Each navigates to a value, then applies a type conversion:

### 4.1 Conversion Helpers

```lua
local function as_number(v)
    if type(v) == "table" and v.str then return tonumber(v.str) or 0 end
    return tonumber(v) or 0
end

local function as_hash(v)
    if type(v) == "table" and v.hash then return v.hash end
    if type(v) == "string" then return s_expr_hash(v) end
    return math.floor(tonumber(v) or 0)
end
```

### 4.2 Extraction Functions

| Builtin | Path Type | Output | Conversion |
|---------|-----------|--------|------------|
| `se_dict_extract_int` | string | integer | `math.floor(as_number(v))` |
| `se_dict_extract_uint` | string | unsigned int | `math.floor(math.abs(as_number(v)))` |
| `se_dict_extract_float` | string | float | `as_number(v) + 0.0` |
| `se_dict_extract_bool` | string | 0 or 1 | `(as_number(v) ~= 0) and 1 or 0` |
| `se_dict_extract_hash` | string | hash number | `as_hash(v)` |
| `se_dict_extract_int_h` | hash | integer | Same as above |
| `se_dict_extract_uint_h` | hash | unsigned int | Same |
| `se_dict_extract_float_h` | hash | float | Same |
| `se_dict_extract_bool_h` | hash | 0 or 1 | Same |
| `se_dict_extract_hash_h` | hash | hash number | Same |
| `se_dict_store_ptr` | string | table ref | Identity; nil if not a table |
| `se_dict_store_ptr_h` | hash | table ref | Identity; nil if not a table |

All extraction builtins return a default value (`0`, `0.0`, or `nil`) when navigation fails (value not found):

```lua
-- String-path example:
M.se_dict_extract_int = function(inst, node)
    local d = bb_dict(inst, node, 1)                        -- dict from blackboard
    local v = navigate_str_path(d, param_str(node, 2))      -- navigate path
    inst.blackboard[param_field_name(node, 3)] =
        v ~= nil and math.floor(as_number(v)) or 0          -- convert + write
end

-- Hash-path example:
local function hash_extract(inst, node, conv)
    local d    = bb_dict(inst, node, 1)                     -- dict from blackboard
    local dest = last_field_idx(node)                       -- find dest field_ref
    local path = collect_path_items(node, 2, dest - 1)      -- gather {hash,str} pairs
    local v    = navigate_hash_path(d, path)                -- navigate
    inst.blackboard[param_field_name(node, dest)] = conv(v)  -- convert + write
end
```

### 4.3 Comparison with C Typed Extraction

| C Function | LuaJIT Equivalent | Notes |
|-----------|-------------------|-------|
| `se_dicts_get_int(dict, mod, path, default)` | `se_dict_extract_int` oneshot | C returns value; Lua writes to blackboard |
| `se_dicth_get_int(dict, hashes, depth, default)` | `se_dict_extract_int_h` oneshot | Same |
| `se_dicts_get_string_ptr(dict, mod, path)` | Not directly available | Use `navigate_str_path` + unwrap `{str,hash}` |
| `se_dicts_get_dict(dict, mod, path)` | `se_dict_store_ptr` | Stores sub-table reference in blackboard |
| `se_dicts_get_callable(dict, mod, path)` | Not applicable | Callables are in `node.children`, not in dicts |

The key difference: C extraction functions return values to the caller. LuaJIT extraction builtins are oneshots that write directly to blackboard fields. For programmatic access outside of builtins, use `navigate_str_path` / `navigate_hash_path` directly on the blackboard table.

---

## 5. Iteration

Since parsed dictionaries and arrays are plain Lua tables, iteration uses standard Lua patterns rather than specialized iterator structs.

### 5.1 Dictionary Iteration

```lua
-- Iterate all keys in a dict table:
local dict = inst.blackboard["config_ptr"]
for key, value in pairs(dict) do
    -- key: string (from dict_key) or number (from dict_key_hash)
    -- value: number, {str,hash} table, or nested table
    print(tostring(key) .. " = " .. tostring(value))
end
```

### 5.2 Array Iteration

Arrays use 0-based numeric keys, so iterate with a counter:

```lua
-- Iterate 0-based array:
local arr = navigate_str_path(dict, "zones")
local i = 0
while arr[i] ~= nil do
    local elem = arr[i]
    -- process element
    i = i + 1
end
```

### 5.3 Comparison with C Iterators

| C Pattern | LuaJIT Equivalent |
|-----------|-------------------|
| `se_dicth_iter_t iter; se_dicth_iter_init(&iter, dict)` | `for key, value in pairs(dict) do` |
| `se_dicth_iter_next(&iter, &key, &value)` | Next iteration of `pairs()` |
| `se_dicth_iter_reset(&iter)` | Re-enter the `pairs()` loop |
| `se_arrayh_iter_t aiter; se_arrayh_iter_init(&aiter, arr)` | `local i = 0; while arr[i] ~= nil do` |
| `se_arrayh_iter_next(&aiter, &elem, &idx)` | `local elem = arr[i]; i = i + 1` |

The C iterators track position, end boundary, and entry index in a struct. In LuaJIT, `pairs()` and numeric counting replace all of this.

---

## 6. Blackboard Integration

Dictionaries are stored in blackboard fields by name. The `bb_dict()` helper retrieves and validates them:

```lua
local function bb_dict(inst, node, param_idx)
    local fname = param_field_name(node, param_idx)
    local d = inst.blackboard[fname]
    assert(d and type(d) == "table",
        "se_dict: blackboard field '" .. tostring(fname) ..
        "' is not a dict table (got " .. type(d) .. ")")
    return d
end
```

The typical pattern:

```lua
-- 1. Load dictionary into blackboard (oneshot, runs once during INIT)
se_load_dictionary("config_ptr", config_table)
-- inst.blackboard["config_ptr"] = { ... parsed Lua table ... }

-- 2. Extract values into individual fields (oneshots, run once during INIT)
se_dict_extract_int("config_ptr", "timeout", "timeout_ms")
-- inst.blackboard["timeout_ms"] = 5000

-- 3. Use fields during TICK (no dictionary access needed)
se_field_gt("sensor_value", "timeout_ms")
```

### Comparison with C Blackboard Integration

| C Pattern | LuaJIT Equivalent |
|-----------|-------------------|
| Blackboard field stores `uint64_t` cast to `s_expr_param_t*` pointer | Blackboard field stores Lua table directly |
| `se_dicth_from_instance(inst, FIELD_OFFSET)` reads pointer via byte offset | `inst.blackboard["config_ptr"]` reads table by name |
| Alignment-sensitive `uint64_t` dereference | No alignment concern — Lua values are GC-managed references |
| Zero-copy: dict lives in ROM, pointer references it | Dict is a live Lua table in memory (parsed from tokens on load) |

The C alignment bug (§8.1 in the C document) does not exist in the LuaJIT version because Lua tables are accessed by reference, not by casting byte offsets to pointer types.

---

## 7. Function Dictionary

In addition to data dictionaries, the subsystem supports **function dictionaries** — tables that map FNV-1a hashes to closures over child subtrees:

```lua
M.se_load_function_dict = function(inst, node)
    -- Collect dict_key names in order from params
    local keys = {}
    for i = 1, #params do
        if params[i].type == "dict_key" then
            keys[#keys + 1] = params[i].value
        end
    end

    -- Build dictionary: hash(key_name) → closure
    local dict = {}
    for i = 1, #keys do
        local key_hash   = s_expr_hash(keys[i])
        local child_node = children[i]
        dict[key_hash] = function(calling_inst, exec_node, eid, edata)
            return se_runtime.invoke_any(calling_inst, child_node, eid, edata)
        end
    end

    inst.blackboard[fname] = dict
end
```

Function dictionaries are consumed by the spawn module's dispatch builtins (`se_exec_dict_dispatch`, `se_exec_dict_fn_ptr`, `se_exec_dict_internal`), which look up entries by hash and call them as main functions.

---

## 8. FNV-1a Hash

Both path types ultimately depend on FNV-1a hashing for key comparison (string paths hash each segment; hash paths carry pre-computed hashes). The LuaJIT implementation decomposes the FNV prime to avoid float64 overflow:

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

This produces identical hashes to the C `s_expr_hash()` function, ensuring cross-runtime compatibility for function dictionaries, spawn tree lookups, and hash-path navigation.

---

## 9. Issues and Design Notes

### 9.1 No Equivalent of C Bug §8.1 (Alignment Fault)

The C `se_dicts_from_blackboard` casts an arbitrary `blackboard + offset` to `uint64_t*` and dereferences, which can hard-fault on ARM Cortex-M with unaligned offsets. The LuaJIT version stores dict tables as Lua values in `inst.blackboard[field_name]` — no pointer arithmetic, no alignment concern.

### 9.2 No Equivalent of C Issue §8.2 (Hash-Path Array Reverse-Lookup)

The C hash-path API brute-forces up to 256 hash computations to convert a hash back to a numeric array index. The LuaJIT `navigate_hash_path` avoids this entirely by using a three-level fallback: try the hash as a key first, then the original string, then `tonumber(string)`. Since path items carry both `hash` and `str`, the string-to-number conversion is direct.

### 9.3 No Code Duplication (C Issues §8.4, §8.5)

The C implementation has duplicated `skip_value()` and `find_hash()` functions across two source files. The LuaJIT version has a single navigation module with shared helpers.

### 9.4 Parse-Once vs Zero-Copy Tradeoff

The C subsystem provides zero-copy traversal of ROM-resident parameter arrays — dictionaries are never copied, never allocated, and the binary data can live in flash. The LuaJIT version parses tokens into Lua tables once (during `se_load_dictionary`) and stores them in the GC-managed heap. This trades ROM efficiency for faster subsequent access (Lua hash table lookup is amortized O(1) vs C's O(n) linear key scan per level).

### 9.5 String Wrapping Overhead

Every string value in a parsed dictionary is wrapped as `{str=S, hash=H}` by `parse_scalar()`. This enables hash extraction without re-hashing, but adds a table allocation per string value. For dictionaries with many string values, this contributes GC pressure. In practice, dictionaries are loaded once during INIT and the strings are extracted into blackboard fields, so the per-tick cost is zero.

### 9.6 `last_field_idx` Linear Scan

Hash-path extraction builtins use `last_field_idx(node)` to find the destination `field_ref` param by scanning backwards through `node.params`:

```lua
local function last_field_idx(node)
    local params = node.params or {}
    for i = #params, 1, -1 do
        local t = params[i].type
        if t == "field_ref" or t == "nested_field_ref" then return i end
    end
    return nil
end
```

This is O(n) in param count but n is typically small (3–6 params per extraction node).

---

## 10. Performance Characteristics

| Operation | String Path | Hash Path |
|-----------|------------|-----------|
| Path parsing | O(path_len) `gmatch` split per call | Zero (pre-collected `{hash, str}` pairs) |
| Per-level dict lookup | O(1) Lua table hash lookup | O(1) Lua table hash lookup (with fallback chain) |
| Per-level array access | O(1) `tonumber` + table index | O(1) three-level fallback (hash → string → number) |
| Token parsing | O(n) once during `se_load_dictionary` | O(n) once during `se_load_dictionary` |
| Subsequent access | Native Lua table operations | Native Lua table operations |
| Memory overhead | One Lua table tree per loaded dictionary | Same |
| GC pressure | Table allocations during parse; zero during extract | Same |

Both path types are read-only after parsing — extraction builtins traverse the Lua table without modification. The parsed table persists in the blackboard for the lifetime of the tree instance.

---

## 11. Complete API Reference

### Parse Functions (internal to `se_builtins_dict.lua`)

| Function | Description |
|----------|-------------|
| `parse_dict(params, start_i)` | Parse `dict_start..dict_end` tokens → Lua table with string or hash keys |
| `parse_array(params, start_i)` | Parse `array_start..array_end` tokens → Lua table with 0-based numeric keys |
| `parse_scalar(p)` | Parse single value token; wraps strings as `{str, hash}` |

### Navigation Functions (internal)

| Function | Description |
|----------|-------------|
| `navigate_str_path(dict, path)` | Dot-path walk with numeric fallback for arrays |
| `navigate_hash_path(dict, path_items)` | Hash-path walk with three-level fallback |
| `collect_path_items(node, start, end)` | Collect `{hash, str}` pairs from node params |
| `last_field_idx(node)` | Find last `field_ref` param index (destination) |
| `bb_dict(inst, node, param_idx)` | Retrieve and validate dict from blackboard |

### Hash Function (exported)

| Function | Description |
|----------|-------------|
| `s_expr_hash(str)` | FNV-1a 32-bit hash, LuaJIT-safe prime decomposition |

### Extraction Builtins (registered as oneshots)

| Function | Path Type | Output |
|----------|-----------|--------|
| `se_load_dictionary` / `se_load_dictionary_hash` | — | Parse tokens → blackboard table |
| `se_dict_extract_int` / `_h` | string / hash | Integer to blackboard field |
| `se_dict_extract_uint` / `_h` | string / hash | Unsigned int to blackboard field |
| `se_dict_extract_float` / `_h` | string / hash | Float to blackboard field |
| `se_dict_extract_bool` / `_h` | string / hash | Boolean (0/1) to blackboard field |
| `se_dict_extract_hash` / `_h` | string / hash | Hash number to blackboard field |
| `se_dict_store_ptr` / `_h` | string / hash | Sub-table reference to blackboard field |
| `se_load_function_dict` | — | `{hash → closure}` table to blackboard field |

---

## 12. Summary

The LuaJIT dictionary subsystem provides two navigation patterns for the same underlying Lua table data: string dot-paths for convenience and debugging, hash paths for compile-time key resolution. The core difference from the C implementation is the **parse-once model** — tokens are converted to Lua tables during `se_load_dictionary`, and all subsequent navigation operates on native Lua hash-table lookups rather than linear scans through flat token arrays. This eliminates the C version's `brace_idx` skip machinery, iterator structs, and alignment-sensitive blackboard pointer access, while providing amortized O(1) per-level lookup instead of O(n).