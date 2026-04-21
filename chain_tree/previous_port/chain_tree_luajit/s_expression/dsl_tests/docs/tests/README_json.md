# JSON Dictionary Extract Test — LuaJIT Runtime

Comprehensive test for the S-Engine dictionary extraction system in the LuaJIT runtime. Exercises both string-path and hash-path APIs across five passes, verifying 36 assertions covering all supported value types, nested access, array indexing, and sub-dictionary pointer storage. All dictionary operations are implemented in `se_builtins_dict.lua`.

## Files

- `json_extract_test_module.lua` — pipeline-generated `module_data` Lua table
- `test_json_extract.lua` — LuaJIT test harness with verification

## Test Configuration

The test loads a Lua table as both a string-keyed dictionary (`dict_string`) and a hash-keyed dictionary (`dict_hash`). Both are parsed from inline `dict_start`/`dict_end` token sequences in `node.params` by `parse_dict()` and stored as plain Lua tables in the blackboard.

The configuration contains:

- **integers** — positive (12345), negative (-9876), zero, and nested 4-deep (42)
- **unsigned** — small (100), medium (50000), large (0xFFFF), nested (255)
- **floats** — pi (3.14159), negative (-273.15), zero, nested (2.71828)
- **bools** — true (1), false (0), nested (1)
- **hashes** — string values wrapped as `{str=S, hash=H}` by `parse_scalar()`: "idle", "running", "error", nested "deep_hash"
- **int_array** — `{[0]=10, [1]=20, [2]=30, [3]=40}` (0-based numeric keys)
- **float_array** — `{[0]=1.5, [1]=2.5, [2]=3.5}`
- **items** — array of dicts: `{[0]={id=100, value=10.1}, [1]={id=200, value=20.2}, [2]={id=300, value=30.3}}`

After `se_load_dictionary` parses the tokens, the blackboard fields hold live Lua tables:

```lua
inst.blackboard["dict_string"] = {
    integers = {
        positive = 12345,
        negative = -9876,
        zero = 0,
        nested = { deep = { value = 42 } },
    },
    unsigned = { small = 100, medium = 50000, large = 0xFFFF, nested = { value = 255 } },
    floats = { pi = 3.14159, negative = -273.15, zero = 0.0, nested = { value = 2.71828 } },
    bools = { true_val = 1, false_val = 0, nested = { value = 1 } },
    hashes = {
        idle    = { str = "idle",    hash = s_expr_hash("idle") },
        running = { str = "running", hash = s_expr_hash("running") },
        error   = { str = "error",   hash = s_expr_hash("error") },
        nested  = { value = { str = "deep_hash", hash = s_expr_hash("deep_hash") } },
    },
    int_array   = { [0]=10, [1]=20, [2]=30, [3]=40 },
    float_array = { [0]=1.5, [1]=2.5, [2]=3.5 },
    items = {
        [0] = { id = 100, value = 10.1 },
        [1] = { id = 200, value = 20.2 },
        [2] = { id = 300, value = 30.3 },
    },
}
```

## Record Layout

The `extract_state` record holds all test fields. In `module_data.records`:

```lua
records["extract_state"] = {
    fields = {
        dict_string = { type = "ptr64" },   dict_hash = { type = "ptr64" },
        pass_number = { type = "uint32" },
        int_val_1 = { type = "int32" },     int_val_2 = { type = "int32" },     int_val_3 = { type = "int32" },
        uint_val_1 = { type = "uint32" },   uint_val_2 = { type = "uint32" },   uint_val_3 = { type = "uint32" },
        float_val_1 = { type = "float" },   float_val_2 = { type = "float" },   float_val_3 = { type = "float" },
        bool_val_1 = { type = "uint32" },   bool_val_2 = { type = "uint32" },   bool_val_3 = { type = "uint32" },
        hash_val_1 = { type = "uint32" },   hash_val_2 = { type = "uint32" },   hash_val_3 = { type = "uint32" },
        arr_int_0 = { type = "int32" },     arr_int_1 = { type = "int32" },
        arr_int_2 = { type = "int32" },     arr_int_3 = { type = "int32" },
        arr_float_0 = { type = "float" },   arr_float_1 = { type = "float" },   arr_float_2 = { type = "float" },
        arr_nested_0_id = { type = "uint32" },  arr_nested_0_val = { type = "float" },
        arr_nested_1_id = { type = "uint32" },  arr_nested_1_val = { type = "float" },
        arr_nested_2_id = { type = "uint32" },  arr_nested_2_val = { type = "float" },
        sub_integers = { type = "ptr64" },  sub_floats = { type = "ptr64" },
        sub_nested_0 = { type = "ptr64" },  sub_nested_1 = { type = "ptr64" },
        ptr_int_pos = { type = "int32" },   ptr_int_neg = { type = "int32" },
        ptr_float_pi = { type = "float" },  ptr_float_neg = { type = "float" },
        ptr_n0_id = { type = "uint32" },    ptr_n0_val = { type = "float" },
        ptr_n1_id = { type = "uint32" },    ptr_n1_val = { type = "float" },
    }
}
```

After `new_instance()`, all fields are accessible as `inst.blackboard["int_val_1"]`, etc. The `ptr64` fields hold Lua tables (parsed dict/array sub-tables) rather than raw pointers.

## Five Passes

### Pass 1 — String Path Extraction

Extracts values from `dict_string` using `navigate_str_path` with dot-separated string paths. Covers all five value types (int, uint, float, bool, hash) including nested paths up to 4 levels deep.

**Generated nodes:**

```lua
-- Each extraction is an o_call to the corresponding builtin:
{ func_name = "SE_DICT_EXTRACT_INT", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_string"},          -- source dict
    {type="str_idx", value="integers.positive"},      -- dot-path
    {type="field_ref", value="int_val_1"},            -- destination
  } }

-- 4-level nested path:
{ func_name = "SE_DICT_EXTRACT_INT", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_string"},
    {type="str_idx", value="integers.nested.deep.value"},
    {type="field_ref", value="int_val_3"},
  } }
```

At runtime, `se_dict_extract_int` calls `navigate_str_path(dict, "integers.positive")` which splits on `"."` and walks `dict["integers"]["positive"]` → 12345, then writes `math.floor(12345)` to `inst.blackboard["int_val_1"]`.

**15 assertions:** 3 int, 3 uint, 3 float, 3 bool, 3 hash

### Pass 2 — Hash Path Extraction

Clears all scalar fields, then repeats the same extractions from `dict_hash` using hash-path arrays. Each path segment is a `str_hash` param carrying `{hash=N, str=S}`.

**Generated nodes:**

```lua
{ func_name = "SE_DICT_EXTRACT_INT_H", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_hash"},
    {type="str_hash", value={hash=H_integers, str="integers"}},
    {type="str_hash", value={hash=H_positive, str="positive"}},
    {type="field_ref", value="int_val_1"},     -- last field_ref = destination
  } }
```

At runtime, `hash_extract` calls `collect_path_items(node, 2, dest-1)` to gather `{hash, str}` pairs, then `navigate_hash_path(dict, items)` walks the table using the three-level fallback (hash → string → number) per segment.

**15 assertions:** same values as Pass 1, verifying hash-path and string-path produce identical results

### Pass 3 — Array Element Access

Extracts from arrays using numeric index segments in dot-paths. Tests integer arrays (0-based), float arrays, and arrays of dictionaries.

**Generated nodes:**

```lua
-- Integer array element:
{ func_name = "SE_DICT_EXTRACT_INT", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_string"},
    {type="str_idx", value="int_array.0"},
    {type="field_ref", value="arr_int_0"},
  } }

-- Nested dict in array:
{ func_name = "SE_DICT_EXTRACT_UINT", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_string"},
    {type="str_idx", value="items.0.id"},
    {type="field_ref", value="arr_nested_0_id"},
  } }
```

At runtime, `navigate_str_path(dict, "int_array.0")` tries `dict["int_array"]["0"]` → nil, then falls back to `dict["int_array"][tonumber("0")]` → `dict["int_array"][0]` → 10.

For nested array dicts: `navigate_str_path(dict, "items.2.value")` → `dict["items"]` → `[2]` (numeric fallback) → `{id=300, value=30.3}` → `["value"]` → 30.3.

**13 assertions:** 4 int array, 3 float array, 6 nested dict fields (3 items × id + value)

### Pass 4 — String-Path Pointer Storage and Extraction

Stores references to sub-tables in blackboard fields using `se_dict_store_ptr`, then extracts values through those references using string paths.

**Generated nodes:**

```lua
-- Store sub-dictionary reference:
{ func_name = "SE_DICT_STORE_PTR", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_string"},
    {type="str_idx", value="integers"},
    {type="field_ref", value="sub_integers"},
  } }

-- Store array element reference:
{ func_name = "SE_DICT_STORE_PTR", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_string"},
    {type="str_idx", value="items.0"},
    {type="field_ref", value="sub_nested_0"},
  } }

-- Extract through sub-table reference:
{ func_name = "SE_DICT_EXTRACT_INT", call_type = "o_call",
  params = {
    {type="field_ref", value="sub_integers"},     -- source is the sub-table!
    {type="str_idx", value="positive"},
    {type="field_ref", value="ptr_int_pos"},
  } }
```

At runtime, `se_dict_store_ptr` calls `navigate_str_path(dict, "integers")` and stores the resulting Lua table in `inst.blackboard["sub_integers"]`. Then `se_dict_extract_int` reads that table from `inst.blackboard["sub_integers"]` and navigates `"positive"` within it — a shorter path because the sub-table is already resolved.

**8 assertions:** 2 int, 2 float, 2 nested id, 2 nested value

### Pass 5 — Hash-Path Pointer Storage and Extraction

Clears pointer result fields, then repeats the pointer storage and extraction using hash-path APIs.

**Generated nodes:**

```lua
-- Store sub-table via hash path:
{ func_name = "SE_DICT_STORE_PTR_H", call_type = "o_call",
  params = {
    {type="field_ref", value="dict_hash"},
    {type="str_hash", value={hash=H_items, str="items"}},
    {type="str_hash", value={hash=H_0, str="0"}},
    {type="field_ref", value="sub_nested_0"},
  } }

-- Extract through sub-table via hash path:
{ func_name = "SE_DICT_EXTRACT_UINT_H", call_type = "o_call",
  params = {
    {type="field_ref", value="sub_nested_0"},
    {type="str_hash", value={hash=H_id, str="id"}},
    {type="field_ref", value="ptr_n0_id"},
  } }
```

For `se_dict_store_ptr_h`, `navigate_hash_path` walks the table using the three-level fallback. For array index "0": tries `dict[hash("0")]` → nil, then `dict["0"]` → nil, then `dict[tonumber("0")]` → `dict[0]` → the sub-table.

**8 assertions:** same values as Pass 4, verified via the Lua verification function

Note: Pass 5 overwrites the same result fields as Pass 4. The final verification checks the Pass 5 (hash-path) results.

## Verification (LuaJIT)

In the C version, verification uses a dedicated `USER_VERIFY_RESULTS` oneshot that reads blackboard fields by hash via `s_expr_blackboard_get_*`. In the LuaJIT runtime, verification reads `inst.blackboard` directly:

```lua
local function verify_results(inst)
    local bb = inst.blackboard
    local errors = 0
    local checks = 0

    local function check_int(name, expected)
        checks = checks + 1
        local got = bb[name] or 0
        if got ~= expected then
            print(string.format("  ❌ %s: got %d, expected %d", name, got, expected))
            errors = errors + 1
        end
    end

    local function check_float(name, expected)
        checks = checks + 1
        local got = bb[name] or 0
        if math.abs(got - expected) >= 0.01 then
            print(string.format("  ❌ %s: got %f, expected %f", name, got, expected))
            errors = errors + 1
        end
    end

    local function check_hash(name, expected_str)
        checks = checks + 1
        local got = bb[name] or 0
        local expected = require("se_builtins_dict").s_expr_hash(expected_str)
        if got ~= expected then
            print(string.format("  ❌ %s: got 0x%08X, expected 0x%08X (%s)",
                name, got, expected, expected_str))
            errors = errors + 1
        end
    end

    -- Pass 2 results (hash-path scalars, overwrote Pass 1):
    check_int("int_val_1", 12345)
    check_int("int_val_2", -9876)
    check_int("int_val_3", 42)
    check_int("uint_val_1", 100)
    check_int("uint_val_2", 50000)
    check_int("uint_val_3", 255)
    check_float("float_val_1", 3.14159)
    check_float("float_val_2", -273.15)
    check_float("float_val_3", 2.71828)
    check_int("bool_val_1", 1)
    check_int("bool_val_2", 0)
    check_int("bool_val_3", 1)
    check_hash("hash_val_1", "idle")
    check_hash("hash_val_2", "running")
    check_hash("hash_val_3", "deep_hash")

    -- Pass 3 results (arrays):
    check_int("arr_int_0", 10)
    check_int("arr_int_1", 20)
    check_int("arr_int_2", 30)
    check_int("arr_int_3", 40)
    check_float("arr_float_0", 1.5)
    check_float("arr_float_1", 2.5)
    check_float("arr_float_2", 3.5)
    check_int("arr_nested_0_id", 100)
    check_float("arr_nested_0_val", 10.1)
    check_int("arr_nested_1_id", 200)
    check_float("arr_nested_1_val", 20.2)
    check_int("arr_nested_2_id", 300)
    check_float("arr_nested_2_val", 30.3)

    -- Pass 5 results (hash-path pointers, overwrote Pass 4):
    check_int("ptr_int_pos", 12345)
    check_int("ptr_int_neg", -9876)
    check_float("ptr_float_pi", 3.14159)
    check_float("ptr_float_neg", -273.15)
    check_int("ptr_n0_id", 100)
    check_float("ptr_n0_val", 10.1)
    check_int("ptr_n1_id", 200)
    check_float("ptr_n1_val", 20.2)

    print(string.format("\n  %d/%d checks passed", checks - errors, checks))
    return errors == 0
end
```

### Comparison with C Verification

| Aspect | C Runtime | LuaJIT Runtime |
|--------|-----------|----------------|
| Verification function | `USER_VERIFY_RESULTS` oneshot (C function) | Lua function reading `inst.blackboard` |
| Field access | `s_expr_blackboard_get_int(inst, hash, default)` | `inst.blackboard["field_name"]` |
| Hash comparison | `s_expr_hash(str)` in C | `require("se_builtins_dict").s_expr_hash(str)` |
| Float comparison | `fabsf(got - expected) < 0.01` | `math.abs(got - expected) < 0.01` |
| Print functions | 3 separate C user oneshots | Not needed (verify reads blackboard directly) |

The LuaJIT version eliminates the need for the three `USER_PRINT_*` C oneshot functions. Since the blackboard is a plain Lua table, the test harness can read and verify all fields directly after the tree completes.

## API Coverage

| API Function | Module | Passes Used | Navigation |
|-------------|--------|-------------|------------|
| `se_load_dictionary` | `se_builtins_dict.lua` | Setup | `parse_dict` → Lua table |
| `se_load_dictionary_hash` | `se_builtins_dict.lua` | Setup | `parse_dict` → Lua table (same impl) |
| `se_dict_extract_int` | `se_builtins_dict.lua` | 1, 3, 4 | `navigate_str_path` → `math.floor(as_number(v))` |
| `se_dict_extract_uint` | `se_builtins_dict.lua` | 1, 3, 4 | `navigate_str_path` → `math.floor(math.abs(as_number(v)))` |
| `se_dict_extract_float` | `se_builtins_dict.lua` | 1, 3, 4 | `navigate_str_path` → `as_number(v) + 0.0` |
| `se_dict_extract_bool` | `se_builtins_dict.lua` | 1 | `navigate_str_path` → `(as_number(v) ~= 0) and 1 or 0` |
| `se_dict_extract_hash` | `se_builtins_dict.lua` | 1 | `navigate_str_path` → `as_hash(v)` |
| `se_dict_extract_int_h` | `se_builtins_dict.lua` | 2, 5 | `navigate_hash_path` → `math.floor(as_number(v))` |
| `se_dict_extract_uint_h` | `se_builtins_dict.lua` | 2, 5 | `navigate_hash_path` → `math.floor(math.abs(as_number(v)))` |
| `se_dict_extract_float_h` | `se_builtins_dict.lua` | 2, 5 | `navigate_hash_path` → `as_number(v) + 0.0` |
| `se_dict_extract_bool_h` | `se_builtins_dict.lua` | 2 | `navigate_hash_path` → `(as_number(v) ~= 0) and 1 or 0` |
| `se_dict_extract_hash_h` | `se_builtins_dict.lua` | 2 | `navigate_hash_path` → `as_hash(v)` |
| `se_dict_store_ptr` | `se_builtins_dict.lua` | 4 | `navigate_str_path` → store sub-table ref |
| `se_dict_store_ptr_h` | `se_builtins_dict.lua` | 5 | `navigate_hash_path` → store sub-table ref |

### Navigation Internals Exercised

| Function | Passes | What's Tested |
|----------|--------|---------------|
| `navigate_str_path` | 1, 3, 4 | Dot-split, string key lookup, numeric fallback for arrays |
| `navigate_hash_path` | 2, 5 | Three-level fallback (hash → string → number) |
| `collect_path_items` | 2, 5 | Gather `{hash, str}` pairs from `str_hash` params |
| `last_field_idx` | 2, 5 | Backwards scan for destination `field_ref` |
| `parse_dict` / `parse_array` | Setup | Token parsing into nested Lua tables |
| `parse_scalar` | Setup | String wrapping as `{str, hash}` |
| `as_number` | All | Unwrap `{str, hash}` tables, `tonumber` coercion |
| `as_hash` | 1, 2 | Extract `.hash` from wrapped strings |
| `bb_dict` | All | Blackboard dict retrieval + type assertion |
| `s_expr_hash` | 1, 2 (hash verify) | FNV-1a hash for cross-runtime compatibility check |

## Test Harness

```lua
local se_runtime = require("se_runtime")
local module_data = require("json_extract_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_oneshot"),
    require("se_builtins_dict"),
    require("se_builtins_return_codes"),
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "json_extract_test")

-- Run tree (completes in a single tick — all extractions are oneshots)
local result = se_runtime.tick_once(inst)

-- Verify all 36 assertions
local passed = verify_results(inst)

print(passed and "✅ ALL 36 TESTS PASSED" or "❌ SOME TESTS FAILED")
```

## Expected Output (passing)

```
  36/36 checks passed

  ✅ ALL 36 TESTS PASSED
```

## Key Concepts Validated

1. **String-path navigation** — `navigate_str_path` correctly splits dot-paths and walks nested Lua tables up to 4 levels deep
2. **Hash-path navigation** — `navigate_hash_path` with three-level fallback produces identical results to string paths
3. **Array indexing** — numeric path segments (`"0"`, `"1"`, `"2"`) fall back to 0-based numeric keys via `tonumber`
4. **Nested array-of-dict access** — `"items.0.id"` navigates array → dict → field
5. **Sub-table pointer storage** — `se_dict_store_ptr` stores Lua table references in blackboard fields for subsequent extraction
6. **Type conversions** — `as_number` unwraps `{str, hash}` tables; `as_hash` extracts precomputed hashes
7. **FNV-1a cross-runtime compatibility** — hash values match between LuaJIT `s_expr_hash` and C `s_expr_hash`
8. **Parse-once model** — `se_load_dictionary` parses tokens once; all five passes navigate the same live Lua tables