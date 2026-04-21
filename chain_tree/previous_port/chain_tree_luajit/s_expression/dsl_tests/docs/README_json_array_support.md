## Array Handling

### Array Structure in LuaJIT Runtime

Arrays are parsed from inline `array_start` / `array_end` token sequences in `node.params` by `se_builtins_dict.lua`'s `parse_array()`. The result is a plain Lua table with **0-based numeric keys**:

```lua
-- Parsed result of an array with 4 elements:
{ [0] = 10, [1] = 20, [2] = 30, [3] = 3.14 }

-- Nested dict inside array:
{ [0] = 10,
  [1] = 20,
  [2] = { some_key = "value", count = 5 } }
```

The `parse_array()` function in `se_builtins_dict.lua` handles recursive nesting — arrays can contain dicts, dicts can contain arrays, to arbitrary depth.

### DSL Array Syntax

Arrays in the YAML/JSON knowledge base are compiled to `array_start` / `array_end` token sequences in `node.params`:

```lua
local config = {
    -- Simple array of integers
    thresholds = {10, 20, 30, 40, 50},

    -- Array of floats
    calibration = {1.0, 1.5, 2.0, 2.5},

    -- Mixed types (valid but less common)
    mixed = {42, 3.14, "label"},

    -- Array of dictionaries
    zones = {
        {id = 1, name = "north", enabled = 1},
        {id = 2, name = "south", enabled = 0},
        {id = 3, name = "east", enabled = 1},
    },

    -- Nested arrays
    matrix = {
        {1, 2, 3},
        {4, 5, 6},
        {7, 8, 9},
    }
}
```

After `se_load_dictionary` processes these tokens, the blackboard field holds a plain Lua table — dicts use string keys, arrays use 0-based numeric keys, and string values are wrapped as `{str=S, hash=H}` tables with precomputed FNV-1a hashes.

### Accessing Arrays via String Path

The `navigate_str_path()` function in `se_builtins_dict.lua` splits dot-delimited paths and walks the nested table structure. Numeric path segments fall back to 0-based numeric key lookup for arrays:

```lua
-- Access array element by index (0-based in path)
se_dict_extract_int("config_ptr", "thresholds.0", "thresh_0")
se_dict_extract_int("config_ptr", "thresholds.1", "thresh_1")
se_dict_extract_int("config_ptr", "thresholds.2", "thresh_2")

-- Access nested dict in array
se_dict_extract_int("config_ptr", "zones.0.id", "zone0_id")
se_dict_extract_int("config_ptr", "zones.1.id", "zone1_id")
se_dict_extract_hash("config_ptr", "zones.0.name", "zone0_name_hash")

-- Access nested array element
se_dict_extract_int("config_ptr", "matrix.1.2", "matrix_1_2")  -- row 1, col 2 = 6
```

**How `navigate_str_path` resolves array indices:**

```lua
-- For path "matrix.1.2":
--   Step 1: cur = dict["matrix"]        → the outer array table
--   Step 2: cur["1"] is nil → try tonumber("1") → cur[1]  → the inner array {4,5,6}
--   Step 3: cur["2"] is nil → try tonumber("2") → cur[2]  → 6
```

### Hash Path Array Access

For hash paths, `navigate_hash_path()` tries the hash key first, then falls back to string key, then numeric index. This handles arrays reached via hash paths where the pipeline emits `hash("0")`, `hash("1")`, etc.:

```lua
-- Using hash path (params carry str_hash values with {hash=N, str=S})
se_dict_extract_int_h("config_ptr", {"thresholds", "0"}, "thresh_0")
se_dict_extract_int_h("config_ptr", {"zones", "0", "id"}, "zone0_id")
se_dict_extract_int_h("config_ptr", {"matrix", "1", "2"}, "matrix_1_2")
```

**How `navigate_hash_path` resolves array indices:**

```lua
-- For path item {hash=hash("0"), str="0"}:
--   Step 1: try cur[hash("0")]  → nil (arrays use numeric keys, not hash keys)
--   Step 2: try cur["0"]        → nil (arrays use numeric keys, not string keys)
--   Step 3: try tonumber("0")   → cur[0] → found!
```

This three-level fallback ensures hash paths work seamlessly with both dict-keyed and array-indexed tables.

### Runtime Array Iteration in LuaJIT

Since parsed arrays are plain Lua tables with 0-based numeric keys, iteration uses standard Lua patterns:

#### Direct Index Access
```lua
-- After se_load_dictionary, dict is in blackboard:
local dict = inst.blackboard["config_ptr"]
local thresholds = dict["thresholds"]  -- or navigate_str_path(dict, "thresholds")

-- Access by index (0-based)
local first = thresholds[0]   -- 10
local second = thresholds[1]  -- 20
```

#### Counting Elements
```lua
-- 0-based arrays: count by scanning until nil
local function array_count(arr)
    local n = 0
    while arr[n] ~= nil do n = n + 1 end
    return n
end

local count = array_count(thresholds)  -- 5
```

#### Iterating All Elements
```lua
-- Iterate 0-based array
local i = 0
while thresholds[i] ~= nil do
    print(string.format("[%d] = %s", i, tostring(thresholds[i])))
    i = i + 1
end
```

#### Iterating Array of Dicts
```lua
local zones = navigate_str_path(dict, "zones")
local i = 0
while zones[i] ~= nil do
    local zone = zones[i]
    local id = zone["id"]              -- number
    local name = zone["name"]          -- {str="north", hash=...}
    local name_str = (type(name) == "table") and name.str or tostring(name)
    print(string.format("zone[%d]: id=%d name=%s", i, id, name_str))
    i = i + 1
end
```

### Built-in Array Helpers

The standard `se_dict_extract_*` builtins extract single values by path. For arrays, there are several approaches:

#### Option 1: Extract Elements Individually

```lua
-- Record definition:
-- config_ptr: PTR64
-- cal_0..cal_3: float fields

se_sequence({
    se_load_dictionary("config_ptr", config),
    se_dict_extract_float("config_ptr", "calibration.0", "cal_0"),
    se_dict_extract_float("config_ptr", "calibration.1", "cal_1"),
    se_dict_extract_float("config_ptr", "calibration.2", "cal_2"),
    se_dict_extract_float("config_ptr", "calibration.3", "cal_3"),
})
```

#### Option 2: Use `se_dict_store_ptr` to Get Array Reference

Extract the array sub-table into a blackboard field, then access elements from it:

```lua
-- Store array reference in blackboard
se_dict_store_ptr("config_ptr", "calibration", "cal_array_ptr")

-- Now cal_array_ptr holds the Lua array table
-- Access via custom oneshot or subsequent dict_extract calls
```

#### Option 3: Create Custom LuaJIT Array Handler

For dynamic or large arrays, register a custom oneshot function:

```lua
-- Custom oneshot: extract float array into numbered blackboard fields
local function user_extract_float_array(inst, node)
    local params = node.params or {}
    assert(#params >= 3, "user_extract_float_array: need dict_field, path, base_field, count")

    local dict_field = params[1].value
    local path       = params[2].value
    local base_field = params[3].value
    local count      = params[4].value

    local dict = inst.blackboard[dict_field]
    assert(dict and type(dict) == "table",
        "user_extract_float_array: dict not found in " .. tostring(dict_field))

    -- Navigate to the array
    local se_dict = require("se_builtins_dict")
    local arr = se_dict.navigate_str_path and
                se_dict.navigate_str_path(dict, path)

    if not arr or type(arr) ~= "table" then return end

    -- Extract elements into numbered blackboard fields
    for i = 0, count - 1 do
        local v = arr[i]
        if v == nil then break end
        local field_name = base_field .. "_" .. i
        if type(v) == "table" and v.str then
            inst.blackboard[field_name] = tonumber(v.str) or 0.0
        else
            inst.blackboard[field_name] = (tonumber(v) or 0.0) + 0.0
        end
    end
end
```

#### Option 4: Inline Lua Processing in Custom Oneshot

For full flexibility, process arrays directly in a custom function:

```lua
-- Custom oneshot: process array of valve configs
local function user_load_valve_configs(inst, node)
    local dict_field = node.params[1].value
    local dict = inst.blackboard[dict_field]
    assert(dict and type(dict) == "table")

    -- Navigate to valves array
    local valves = dict["valves"]
    if not valves or type(valves) ~= "table" then return end

    -- Process each valve config
    local i = 0
    while valves[i] ~= nil do
        local v = valves[i]
        local id      = v["id"] or 0
        local pin     = v["pin"] or 0
        local timeout = v["timeout"] or 0

        -- Store in numbered blackboard fields
        inst.blackboard["valve_id_" .. i]      = id
        inst.blackboard["valve_pin_" .. i]     = pin
        inst.blackboard["valve_timeout_" .. i] = timeout

        i = i + 1
    end
    inst.blackboard["valve_count"] = i
end
```

### Array of Structures Pattern

For arrays of dictionaries, the common pattern extracts each dict's fields:

**Configuration:**
```lua
local config = {
    valves = {
        {id = 1, pin = 10, timeout = 5000},
        {id = 2, pin = 11, timeout = 3000},
        {id = 3, pin = 12, timeout = 4000},
    }
}
```

**Custom Handler (registered as oneshot):**
```lua
local function user_extract_valve_array(inst, node)
    local params = node.params or {}
    local dict_field = params[1].value
    local max_count  = params[2].value or 16

    local dict = inst.blackboard[dict_field]
    if not dict or type(dict) ~= "table" then return end

    local valves = dict["valves"]
    if not valves or type(valves) ~= "table" then return end

    local i = 0
    while valves[i] ~= nil and i < max_count do
        local v = valves[i]
        if type(v) == "table" then
            -- Extract scalar values (handle {str=S, hash=H} wrappers)
            local function as_int(val)
                if type(val) == "table" and val.str then
                    return math.floor(tonumber(val.str) or 0)
                end
                return math.floor(tonumber(val) or 0)
            end

            inst.blackboard["valve_" .. i .. "_id"]      = as_int(v["id"])
            inst.blackboard["valve_" .. i .. "_pin"]     = as_int(v["pin"])
            inst.blackboard["valve_" .. i .. "_timeout"] = as_int(v["timeout"])
        end
        i = i + 1
    end
    inst.blackboard["valve_count"] = i
end
```

**Registration:**
```lua
local fns = se_runtime.merge_fns(
    -- ... standard builtins ...
    { user_extract_valve_array = user_extract_valve_array }
)
```

### String Values in Arrays

When `parse_scalar()` encounters a `str_idx` or `str_ptr` param inside an array, it wraps the string as `{str=S, hash=H}` with a precomputed FNV-1a hash. Code that reads array elements must handle this:

```lua
local function unwrap_value(v)
    if type(v) == "table" and v.str then
        return v.str    -- extract the string
    end
    return v            -- number or nil
end

-- Example: reading mixed array
local arr = dict["mixed"]  -- {[0]=42, [1]=3.14, [2]={str="label", hash=...}}
local s = unwrap_value(arr[2])  -- "label"
```

### Navigation Functions Summary

| Function | Module | Description |
|----------|--------|-------------|
| `parse_dict(params, start_i)` | se_builtins_dict | Parse dict_start..dict_end tokens → Lua table |
| `parse_array(params, start_i)` | se_builtins_dict | Parse array_start..array_end tokens → 0-based Lua table |
| `parse_scalar(p)` | se_builtins_dict | Parse single value; wraps strings as `{str, hash}` |
| `navigate_str_path(dict, path)` | se_builtins_dict | Dot-path navigation with numeric fallback for arrays |
| `navigate_hash_path(dict, items)` | se_builtins_dict | Hash-path navigation with string and numeric fallback |
| `collect_path_items(node, start, end)` | se_builtins_dict | Collect `{hash, str}` pairs from node params |
| `s_expr_hash(str)` | se_builtins_dict | FNV-1a 32-bit hash (LuaJIT-safe decomposition) |

### Extraction Builtins Summary

| Function | Path Type | Output Type | Description |
|----------|-----------|-------------|-------------|
| `se_dict_extract_int` | string | integer | Extract and floor to int |
| `se_dict_extract_uint` | string | unsigned int | Extract and abs+floor |
| `se_dict_extract_float` | string | float | Extract as float |
| `se_dict_extract_bool` | string | 0/1 | Extract as boolean (nonzero = 1) |
| `se_dict_extract_hash` | string | hash number | Extract string hash or numeric |
| `se_dict_extract_int_h` | hash | integer | Hash-path int extraction |
| `se_dict_extract_uint_h` | hash | unsigned int | Hash-path uint extraction |
| `se_dict_extract_float_h` | hash | float | Hash-path float extraction |
| `se_dict_extract_bool_h` | hash | 0/1 | Hash-path boolean extraction |
| `se_dict_extract_hash_h` | hash | hash number | Hash-path hash extraction |
| `se_dict_store_ptr` | string | table ref | Store sub-table reference |
| `se_dict_store_ptr_h` | hash | table ref | Hash-path sub-table reference |
| `se_load_dictionary` | — | table | Parse inline tokens → blackboard |
| `se_load_dictionary_hash` | — | table | Same as above (same impl in Lua) |
| `se_load_function_dict` | — | `{hash→fn}` | Build function dictionary from children |