# Reading Pipeline-Generated Module Data Files

## Overview

The S-Expression LuaJIT pipeline generates a `module_data` Lua file (e.g., `loop_test_module.lua`) that provides a complete, human-readable representation of the compiled tree structure. This file is the LuaJIT equivalent of the C debug dump (`xxx_dump_32.h`) — it serves as both the runtime input *and* the debugging artifact. Unlike the C version where the debug dump is a separate file from the binary, the LuaJIT module data is directly executable and inspectable.

This file is invaluable for:

- Debugging tree structure issues
- Understanding parameter encoding and node relationships
- Verifying function registration requirements
- Tracing execution flow
- Confirming parent-child nesting and call_type assignments

## Comparison with C Debug Dump

| C Debug Dump (`xxx_dump_32.h`) | LuaJIT Module Data (`xxx_module.lua`) |
|-------------------------------|---------------------------------------|
| Flat parameter array with index numbers | Nested Lua table tree (children inside parents) |
| OPEN_CALL/CLOSE pairs bracket each function | `children = { ... }` arrays hold nested nodes |
| Type codes (0x07, 0x08, 0x09, 0x0A, 0x0B) | String types (`"m_call"`, `"o_call"`, `"p_call"`, `"field_ref"`) |
| `brace_idx` offsets for structure skipping | Not needed — nesting is explicit in table structure |
| Column-formatted comment block | Executable Lua source |
| Separate from binary (`.h` vs `.sexb`) | *Is* the runtime data — one file serves both roles |
| Requires hex decoding to read | Human-readable Lua tables |

## File Sections

### 1. Module Header

```lua
M.name         = "loop_test"
M.name_hash    = 0xD1A777D8
M.pointer_size = 4
M.debug        = true
```

| Field | Description |
|-------|-------------|
| `name` | Module name from DSL source |
| `name_hash` | FNV-1a hash of module name (used for spawn lookups) |
| `pointer_size` | Target pointer size in bytes (4 = 32-bit, 8 = 64-bit) |
| `debug` | Whether debug information is included |

### 2. Function Lists

```lua
M.oneshot_funcs = { "SE_SET_FIELD", "SE_LOG", "SE_LOG_INT", "SE_INC_FIELD" }
M.main_funcs    = { "SE_FUNCTION_INTERFACE", "SE_FORK_JOIN", "SE_WHILE",
                    "SE_CHAIN_FLOW", "SE_TICK_DELAY",
                    "SE_RETURN_PIPELINE_DISABLE", "SE_RETURN_TERMINATE" }
M.pred_funcs    = { "SE_STATE_INCREMENT_AND_TEST",
                    "SE_FIELD_INCREMENT_AND_TEST" }
```

Three ordered lists define every function the module requires. **Position determines `func_index`** — the first entry is index 0, the second is index 1, etc. At module creation time, `se_runtime.new_module()` builds name→index maps from these lists and `annotate_node()` assigns each node's `func_index` by searching the appropriate list.

| List | Call Types | Signature |
|------|-----------|-----------|
| `oneshot_funcs` | `o_call`, `io_call` | `fn(inst, node)` — no return |
| `main_funcs` | `m_call`, `pt_m_call` | `fn(inst, node, event_id, event_data)` → result code |
| `pred_funcs` | `p_call`, `p_call_composite` | `fn(inst, node)` → boolean |

**Debugging use:** If `se_runtime.new_instance()` reports unregistered functions, check these lists against the function tables passed to `merge_fns()`. Every name here must appear (case-insensitively) in the registered functions.

### 3. String Table

```lua
M.string_table = {
    "loop_sequence_fn start",
    "outer_sequence_counter %d",
    "inner_sequence_fn start",
    "inner_sequence_counter %d",
    "inner_sequence_fn end",
    "loop_sequence_fn end"
}
M.string_index = {
    ["inner_sequence_counter %d"] = 3,
    ["inner_sequence_fn end"]     = 4,
    ["inner_sequence_fn start"]   = 2,
    ["loop_sequence_fn end"]      = 5,
    ["loop_sequence_fn start"]    = 0,
    ["outer_sequence_counter %d"] = 1,
}
```

| Field | Description |
|-------|-------------|
| `string_table` | 0-based ordered array of all string literals used in the module |
| `string_index` | Reverse lookup: string content → 0-based index |

In the LuaJIT runtime, strings are carried directly in `node.params` as `str_ptr` or `str_idx` values rather than referenced by index. The string table exists for C code generation compatibility and debugging — the runtime does not use it during execution.

### 4. Tree Order

```lua
M.tree_order = { "loop_test" }
M.trees = {}
```

`tree_order` provides deterministic iteration order for trees (Lua tables don't guarantee key order). Each entry names a tree in `M.trees`.

### 5. Record Definitions

```lua
M.record_order = { "loop_test_blackboard" }
M.records      = {}
M.records["loop_test_blackboard"] = {
    name      = "loop_test_blackboard",
    name_hash = 0x033C03AC,
    size      = 20,
    align     = 4,
    fields    = {
        { name="outer_sequence_counter", name_hash=0x24954557,
          type="uint32", offset=0,  size=4, ... },
        { name="inner_sequence_counter", name_hash=0xD0B76C4E,
          type="uint32", offset=4,  size=4, ... },
        { name="field_test_counter",     name_hash=0x6542B7E7,
          type="uint32", offset=8,  size=4, ... },
        { name="field_test_increment",   name_hash=0x696CDE6A,
          type="uint32", offset=12, size=4, ... },
        { name="field_test_limit",       name_hash=0x1CAA35D8,
          type="uint32", offset=16, size=4, ... },
    },
}
```

| Field | Description |
|-------|-------------|
| `name` | Record name, referenced by `tree.record_name` |
| `name_hash` | FNV-1a hash for C compatibility |
| `size` | Total record size in bytes (C layout; informational in Lua) |
| `align` | Memory alignment (C layout; informational in Lua) |
| `fields` | Ordered array of field descriptors |

Each field descriptor:

| Field | Description |
|-------|-------------|
| `name` | Field name — used as the blackboard key in LuaJIT |
| `name_hash` | FNV-1a hash for C cross-reference |
| `type` | C type name (`uint32`, `float`, `ptr64`, etc.) |
| `offset` | Byte offset in C struct (informational in Lua) |
| `size` | Field size in bytes (informational in Lua) |
| `is_pointer` | Whether this is a pointer field |

**Debugging use:** When a blackboard field isn't found or has the wrong type, check the record definition. The `name` strings here must exactly match the `field_ref` values used in node params.

### 6. Constants, Events

```lua
M.const_order = {}
M.constants   = {}
M.events      = {}
M.event_names = {}
```

Optional sections for ROM constants and named events. Empty in many modules.

## Tree Structure (Main Section)

This is the core of the module data — the nested node tree that defines the program.

### Node Fields

Each node is a Lua table with these fields:

```lua
{
    func_name    = "SE_CHAIN_FLOW",     -- Function name (matches function lists)
    func_hash    = 0xFFC1FAA4,          -- FNV-1a hash (for C cross-reference)
    call_type    = "m_call",            -- Dispatch type
    order        = 3,                   -- Sibling order (0-based among parent's children)
    param_count  = 0,                   -- Number of non-callable params
    pointer_index = nil,                -- Pointer slot index (pt_m_call only)
    params       = { ... },             -- Non-callable parameters
    children     = { ... },             -- Callable child nodes
}
```

| Field | Description |
|-------|-------------|
| `func_name` | Human-readable function name; must appear in the appropriate function list |
| `func_hash` | FNV-1a hash of `func_name`; used for C binary cross-reference only |
| `call_type` | One of: `"m_call"`, `"pt_m_call"`, `"o_call"`, `"io_call"`, `"p_call"`, `"p_call_composite"` |
| `order` | Position among siblings (0-based); determines execution order in sequences/forks |
| `param_count` | Count of entries in `params[]`; informational (use `#node.params` at runtime) |
| `pointer_index` | Index into `inst.pointer_array` for `pt_m_call` nodes; `nil` for others |
| `params` | Array of non-callable parameter tables |
| `children` | Array of callable child node tables (recursively nested) |

### Call Types

| Call Type | Function Type | Description |
|-----------|--------------|-------------|
| `m_call` | MAIN | Standard main function with INIT/TICK/TERMINATE lifecycle |
| `pt_m_call` | MAIN | Pointer-based main function — uses `pointer_index` for persistent storage |
| `o_call` | ONESHOT | Fire-once function, runs once per reset cycle |
| `io_call` | ONESHOT | Fire-once function, survives tree reset (runs once ever) |
| `p_call` | PRED | Simple predicate, no child predicates |
| `p_call_composite` | PRED | Composite predicate with child predicates in `children[]` |

### Parameter Types

Each entry in `node.params` is a table with `type`, `value`, and `order`:

```lua
{ type = "field_ref", value = "outer_sequence_counter", order = 0 }
{ type = "uint",      value = 0,                        order = 1 }
{ type = "int",       value = 3,                        order = 0 }
{ type = "str_ptr",   value = "loop_sequence_fn start",  order = 0 }
```

| Param Type | Value Type | Description |
|-----------|------------|-------------|
| `"int"` | number | Signed integer literal |
| `"uint"` | number | Unsigned integer literal |
| `"float"` | number | Float literal |
| `"str_ptr"` | string | String literal (carried inline) |
| `"str_idx"` | string | String literal (by index reference) |
| `"str_hash"` | table `{hash, str}` | String with precomputed FNV-1a hash |
| `"field_ref"` | string | Blackboard field name |
| `"nested_field_ref"` | string | Nested blackboard field name |
| `"result"` | number | Result code literal |
| `"dict_start"` | — | Dictionary structure open |
| `"dict_end"` | — | Dictionary structure close |
| `"dict_key"` | string | Dictionary key (string name) |
| `"dict_key_hash"` | number | Dictionary key (FNV-1a hash) |
| `"end_dict_key"` | — | Dictionary key terminator |
| `"array_start"` | — | Array structure open |
| `"array_end"` | — | Array structure close |
| `"stack_tos"` | number | Stack top-of-stack offset |
| `"stack_local"` | number | Stack local variable index |
| `"stack_pop"` | — | Stack pop operation |
| `"stack_push"` | — | Stack push operation |
| `"const_ref"` | any | Constants table reference |

## Reading the Tree Structure

### Nesting = Indentation

The tree structure is explicit in the Lua table nesting. Each `children = { ... }` block contains the child nodes, which themselves may contain children:

```lua
-- Root: SE_FUNCTION_INTERFACE
{
    func_name="SE_FUNCTION_INTERFACE", call_type="m_call",
    children={
        -- Child 0: SE_SET_FIELD (oneshot)
        { func_name="SE_SET_FIELD", call_type="o_call",
          params={ {type="field_ref", value="outer_sequence_counter"},
                   {type="uint", value=0} } },

        -- Child 1: SE_SET_FIELD (oneshot)
        { func_name="SE_SET_FIELD", call_type="o_call", ... },

        -- Child 2: SE_FORK_JOIN (main, contains nested tree)
        { func_name="SE_FORK_JOIN", call_type="m_call",
          children={
              -- Grandchild: SE_WHILE
              { func_name="SE_WHILE", call_type="m_call",
                children={
                    -- Predicate child
                    { func_name="SE_STATE_INCREMENT_AND_TEST",
                      call_type="p_call", ... },
                    -- Body child
                    { func_name="SE_FORK_JOIN", call_type="m_call", ... },
                } },
          } },

        -- Child 3: second SE_FORK_JOIN
        { func_name="SE_FORK_JOIN", call_type="m_call", ... },

        -- Child 4: SE_RETURN_TERMINATE
        { func_name="SE_RETURN_TERMINATE", call_type="m_call", ... },
    },
}
```

### Pointer Functions (pt_m_call)

Nodes with `call_type = "pt_m_call"` have a non-nil `pointer_index` that identifies their slot in `inst.pointer_array`:

```lua
{ func_name="SE_TICK_DELAY", call_type="pt_m_call",
  pointer_index=0,                    -- uses inst.pointer_array[0]
  params={ {type="int", value=3} },   -- 3 tick delay
}
```

Multiple `pt_m_call` nodes in the same tree each get a unique `pointer_index`. In the example module, four `SE_TICK_DELAY` nodes use indices 0–3, matching `tree.pointer_count = 4`.

### Function Parameters

Parameters follow the function reference in `node.params`. Reading them requires knowing the function's expected signature:

```lua
-- SE_SET_FIELD: params[1]=field_ref (destination), params[2]=value
{ func_name="SE_SET_FIELD", call_type="o_call",
  params={
    {type="field_ref", value="outer_sequence_counter"},  -- destination field
    {type="uint", value=0},                              -- value to write
  } }

-- SE_LOG: params[1]=str_ptr (message string)
{ func_name="SE_LOG", call_type="o_call",
  params={
    {type="str_ptr", value="loop_sequence_fn start"},
  } }

-- SE_LOG_INT: params[1]=str_ptr (format string), params[2]=field_ref (value)
{ func_name="SE_LOG_INT", call_type="o_call",
  params={
    {type="str_ptr", value="outer_sequence_counter %d"},
    {type="field_ref", value="outer_sequence_counter"},
  } }

-- SE_TICK_DELAY: params[1]=int (tick count)
{ func_name="SE_TICK_DELAY", call_type="pt_m_call",
  pointer_index=0,
  params={
    {type="int", value=3},
  } }

-- SE_STATE_INCREMENT_AND_TEST: params[1]=uint (increment), params[2]=uint (limit)
{ func_name="SE_STATE_INCREMENT_AND_TEST", call_type="p_call",
  params={
    {type="uint", value=1},   -- increment by 1 each call
    {type="uint", value=10},  -- limit: stop after 10
  } }

-- SE_FIELD_INCREMENT_AND_TEST: params[1..3]=field_ref (counter, increment, limit)
{ func_name="SE_FIELD_INCREMENT_AND_TEST", call_type="p_call",
  params={
    {type="field_ref", value="field_test_counter"},     -- counter field
    {type="field_ref", value="field_test_increment"},   -- increment field
    {type="field_ref", value="field_test_limit"},       -- limit field
  } }
```

### Predicate Children

Predicates appear as children of main function nodes. The `call_type` distinguishes them:

```lua
-- SE_WHILE: children[1]=predicate, children[2]=body
{ func_name="SE_WHILE", call_type="m_call",
  children={
    -- children[1]: predicate (p_call)
    { func_name="SE_STATE_INCREMENT_AND_TEST", call_type="p_call",
      params={ {type="uint",value=1}, {type="uint",value=10} } },
    -- children[2]: body (m_call)
    { func_name="SE_FORK_JOIN", call_type="m_call", children={...} },
  } }
```

The `se_while` builtin calls `child_invoke_pred(inst, node, 0)` for the predicate and `child_invoke(inst, node, 1, eid, edata)` for the body. The 0-based child indices map to 1-based Lua array positions.

## Tracing Execution

To trace how a tree executes, follow the nesting structure:

### Example: loop_test Module

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_SET_FIELD  outer_sequence_counter = 0
├── [o_call] SE_SET_FIELD  inner_sequence_counter = 0
├── SE_FORK_JOIN
│   └── SE_WHILE (pred: SE_STATE_INCREMENT_AND_TEST, step=1, limit=10)
│       └── SE_FORK_JOIN
│           └── SE_CHAIN_FLOW
│               ├── [o_call] SE_LOG "loop_sequence_fn start"
│               ├── [o_call] SE_LOG_INT "outer_sequence_counter %d"
│               ├── [o_call] SE_INC_FIELD outer_sequence_counter
│               ├── SE_CHAIN_FLOW (inner loop body)
│               │   ├── [o_call] SE_LOG "inner_sequence_fn start"
│               │   ├── [o_call] SE_LOG_INT "inner_sequence_counter %d"
│               │   ├── [o_call] SE_INC_FIELD inner_sequence_counter
│               │   ├── [pt_m_call] SE_TICK_DELAY 3  (ptr=0)
│               │   ├── [o_call] SE_LOG "inner_sequence_fn end"
│               │   └── SE_RETURN_PIPELINE_DISABLE
│               ├── [pt_m_call] SE_TICK_DELAY 5  (ptr=1)
│               ├── [o_call] SE_LOG "loop_sequence_fn end"
│               └── SE_RETURN_PIPELINE_DISABLE
├── SE_FORK_JOIN (field-based loop variant)
│   ├── [o_call] SE_SET_FIELD  field_test_increment = 1
│   ├── [o_call] SE_SET_FIELD  field_test_limit = 10
│   └── SE_WHILE (pred: SE_FIELD_INCREMENT_AND_TEST)
│       └── SE_FORK_JOIN
│           └── SE_CHAIN_FLOW
│               ├── ... (same structure as above, ptr=2,3)
└── SE_RETURN_TERMINATE
```

### Reading Execution Flow

1. **Start at root**: The first node in `tree.nodes[1]` is always the root. Here it's `SE_FUNCTION_INTERFACE`.
2. **Follow children in order**: The `order` field within each child determines execution sequence (though array position already reflects this).
3. **Identify call types**: `o_call` nodes fire once during INIT; `m_call`/`pt_m_call` nodes persist across ticks; `p_call` nodes are evaluated as booleans.
4. **Track pointer indices**: `pt_m_call` nodes with different `pointer_index` values use separate persistent storage slots.
5. **Match params to signatures**: Each function's `params` array follows its documented parameter layout.

## Debugging Tips

### Finding a Function

Search for `func_name` to find all invocations:

```bash
grep 'func_name="SE_TICK_DELAY"' loop_test_module.lua
```

### Checking Function Registration

Compare the function lists against your registered builtins:

```bash
# Extract all required function names
grep -oP 'func_name="\K[^"]+' loop_test_module.lua | sort -u
```

Then verify each appears in your `merge_fns()` call. Any name not present will cause `new_instance()` to error with a clear missing-function message.

### Verifying Blackboard Fields

Check that every `field_ref` param references a field defined in the record:

```bash
# Extract all field_ref values
grep -oP 'type="field_ref",value="\K[^"]+' loop_test_module.lua | sort -u

# Extract all record field names
grep -oP 'name="\K[^"]+(?=",name_hash)' loop_test_module.lua | sort -u
```

Every `field_ref` value should appear as a `name` in the record's `fields` array.

### Counting Nodes

The `tree.node_count` should match the total number of nodes in the DFS traversal. You can verify:

```bash
# Count all func_name occurrences (one per node)
grep -c 'func_name=' loop_test_module.lua
```

This count should equal `tree.node_count` (42 in the example).

### Checking Pointer Indices

Each `pointer_index` in the tree should be unique and less than `tree.pointer_count`:

```bash
grep -oP 'pointer_index=\K\d+' loop_test_module.lua | sort -n
# Should produce: 0, 1, 2, 3 (and pointer_count should be 4)
```

### Verifying Parent-Child Relationships

Unlike the C dump where you must match OPEN_CALL/CLOSE pairs by index arithmetic, the LuaJIT module data makes parent-child relationships explicit through nesting. If you're unsure what a node's parent is, look at which `children = { ... }` array contains it.

### Cross-Referencing with C Debug Dump

When debugging across C and LuaJIT runtimes, use `func_hash` values to match nodes:

```lua
-- LuaJIT module data:
{ func_name="SE_CHAIN_FLOW", func_hash=0xFFC1FAA4, ... }
```

```c
// C debug dump:
*   49  OPEN_CALL[0x07]     29      0  SE_CHAIN_FLOW hash=0xFFC1FAA4
```

The `func_hash` values are identical because both use FNV-1a on the same function name strings.

## Programmatic Inspection

Since the module data is a standard Lua table, you can inspect it programmatically:

```lua
local md = require("loop_test_module")

-- List all required functions
print("=== Required Functions ===")
for _, name in ipairs(md.oneshot_funcs) do print("  [oneshot] " .. name) end
for _, name in ipairs(md.main_funcs)    do print("  [main]    " .. name) end
for _, name in ipairs(md.pred_funcs)    do print("  [pred]    " .. name) end

-- Walk tree and print structure
local function dump_tree(node, indent)
    indent = indent or ""
    local tag = node.call_type
    if node.pointer_index then
        tag = tag .. " ptr=" .. node.pointer_index
    end
    print(string.format("%s[%s] %s", indent, tag, node.func_name))

    -- Print params
    for _, p in ipairs(node.params or {}) do
        print(string.format("%s  param: %s = %s", indent, p.type, tostring(p.value)))
    end

    -- Recurse into children
    for _, child in ipairs(node.children or {}) do
        dump_tree(child, indent .. "  ")
    end
end

for _, tree_name in ipairs(md.tree_order) do
    print("\n=== Tree: " .. tree_name .. " ===")
    local tree = md.trees[tree_name]
    print(string.format("  nodes=%d  pointers=%d  record=%s",
        tree.node_count, tree.pointer_count, tree.record_name or "none"))
    for _, root in ipairs(tree.nodes) do
        dump_tree(root, "  ")
    end
end
```

This produces output like:

```
=== Tree: loop_test ===
  nodes=42  pointers=4  record=loop_test_blackboard
  [m_call] SE_FUNCTION_INTERFACE
    [o_call] SE_SET_FIELD
      param: field_ref = outer_sequence_counter
      param: uint = 0
    [o_call] SE_SET_FIELD
      param: field_ref = inner_sequence_counter
      param: uint = 0
    [m_call] SE_FORK_JOIN
      [m_call] SE_WHILE
        [p_call] SE_STATE_INCREMENT_AND_TEST
          param: uint = 1
          param: uint = 10
        [m_call] SE_FORK_JOIN
          ...
```

This is often more useful than reading the raw Lua source, especially for large trees.

## Summary

The LuaJIT module data file replaces both the C SEXB binary and the C debug dump with a single, human-readable, executable Lua table. The tree structure is represented as nested node tables with explicit `children` arrays rather than flat parameter streams with OPEN_CALL/CLOSE bracket pairs. Parameter types are readable strings rather than hex codes. Function references are names rather than hash indices. The file can be inspected visually, searched with grep, or walked programmatically — and it is the exact same artifact that the runtime loads and executes.