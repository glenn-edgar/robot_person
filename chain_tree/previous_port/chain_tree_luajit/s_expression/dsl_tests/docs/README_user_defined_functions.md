# User-Defined External Functions — LuaJIT Runtime

## Overview

The S-Expression engine supports **user-defined functions** that extend the engine with application-specific functionality. In the LuaJIT runtime, external functions are plain Lua functions that follow the same signatures as builtins and are registered through the same `merge_fns` / `register_fns` mechanism. No code generation, header files, or registration tables are needed — just write a Lua function and include it in the function table.

This allows extending the engine with:
- Hardware control (via FFI or Lua bindings)
- Custom I/O operations
- Application-specific logic
- Integration with external systems (NATS, PostgreSQL, MQTT)
- Custom composite control structures

## How It Works

### 1. Declare in DSL / Pipeline

The pipeline includes the function name in the module's function lists (`oneshot_funcs`, `main_funcs`, or `pred_funcs`) and references it from tree nodes:

```lua
-- In module_data (pipeline output):
M.oneshot_funcs = { "SE_LOG", "SE_SET_FIELD", "CFL_DISABLE_CHILDREN", "CFL_ENABLE_CHILD" }
--                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
--                                             user-defined functions alongside builtins

-- In tree node:
{ func_name = "CFL_DISABLE_CHILDREN", call_type = "o_call",
  params = {}, children = {} }

{ func_name = "CFL_ENABLE_CHILD", call_type = "o_call",
  params = { {type="int", value=2} },
  children = {} }
```

### 2. Implement as Lua Functions

Write functions matching the appropriate signature for their call type:

```lua
-- Oneshot: fn(inst, node) — no return value
local function cfl_disable_children(inst, node)
    print("cfl_disable_children")
    -- TODO: actual implementation
end

-- Oneshot with parameters: fn(inst, node)
local function cfl_enable_child(inst, node)
    local params = node.params or {}
    assert(#params >= 1, "cfl_enable_child: need at least one parameter")

    local child_index = params[1].value
    print("cfl_enable_child: enabling child " .. child_index)
    -- TODO: actual implementation
end
```

### 3. Register with Module

Include the functions in the table passed to `new_module` or `register_fns`:

```lua
local se_runtime = require("se_runtime")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    -- ... other builtins ...

    -- User-defined functions mixed in alongside builtins:
    {
        cfl_disable_children = cfl_disable_children,
        cfl_enable_child     = cfl_enable_child,
    }
)

local mod = se_runtime.new_module(module_data, fns)
```

That's it. No header files, no registration tables, no hash computation, no code generation. The `register_fns` mechanism matches function names case-insensitively against the module's function lists.

### 4. Validation

When `se_runtime.new_instance(mod, tree_name)` is called, it automatically validates that every function in the module's lists has been registered. If any are missing, it errors with the complete list:

```
new_instance: unregistered functions:
  [oneshot] cfl_disable_children
  [oneshot] cfl_enable_child
```

This catches registration gaps at instance creation time, not at runtime during execution.

## Comparison with C Workflow

| Step | C Runtime | LuaJIT Runtime |
|------|-----------|----------------|
| Declare in DSL | `o_call("CFL_ENABLE_CHILD")` | Same DSL, or pipeline produces module_data |
| Code generation | Pipeline generates `_user_functions.h` + `_user_registration.c` | Not needed |
| Function signature | `void fn(inst, params, count, event_type, event_id, event_data)` | `fn(inst, node)` |
| Parameter access | `params[0].int_val` (C struct union) | `node.params[1].value` (Lua table) |
| Hash computation | FNV-1a hash in generated registration table | Not needed — name-based matching |
| Registration | `s_expr_module_register_oneshot(module, &table)` via callback | `merge_fns({ name = fn })` |
| Validation | `s_expr_module_validate()` checks hash slots | `validate_module()` checks name→index slots |
| Files generated | 2 (header + registration source) | 0 |

## Function Types

### Oneshot Functions

Declared with `o_call` or `io_call` in the pipeline. Signature: `fn(inst, node)` — no return value.

```lua
-- Pipeline node:
{ func_name = "MY_ONESHOT", call_type = "o_call",
  params = { {type="int", value=42}, {type="str_ptr", value="hello"} },
  children = {} }

-- Implementation:
local function my_oneshot(inst, node)
    local val = node.params[1].value           -- 42
    local msg = node.params[2].value           -- "hello"
    print("my_oneshot: " .. msg .. " = " .. val)
end
```

The runtime handles the fire-once semantics — `invoke_oneshot` checks `FLAG_INITIALIZED` (for `o_call`) or `FLAG_EVER_INIT` (for `io_call`) and skips if already fired. The function itself doesn't need to check.

### Main Functions

Declared with `m_call` or `pt_m_call`. Signature: `fn(inst, node, event_id, event_data)` → result code.

```lua
-- Pipeline node:
{ func_name = "MY_MAIN", call_type = "m_call",
  params = { {type="int", value=100} },
  children = {} }

-- Implementation:
local se_runtime = require("se_runtime")

local function my_main(inst, node, event_id, event_data)
    if event_id == se_runtime.SE_EVENT_INIT then
        -- Initialize state
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    if event_id == se_runtime.SE_EVENT_TERMINATE then
        -- Cleanup
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    -- SE_EVENT_TICK: do the work
    local threshold = node.params[1].value   -- 100
    local sensor = inst.blackboard["sensor_value"] or 0

    if sensor > threshold then
        return se_runtime.SE_PIPELINE_DISABLE   -- complete
    end

    return se_runtime.SE_PIPELINE_CONTINUE      -- still running
end
```

The `invoke_main` dispatch handles the INIT/TICK/TERMINATE lifecycle automatically:
- First call: sends `SE_EVENT_INIT`, then the actual event
- On `SE_PIPELINE_DISABLE`: sends `SE_EVENT_TERMINATE` and clears `FLAG_ACTIVE`
- The function just responds to the event it receives

### Predicate Functions

Declared with `p_call` or `p_call_composite`. Signature: `fn(inst, node)` → boolean.

```lua
-- Pipeline node:
{ func_name = "MY_PREDICATE", call_type = "p_call",
  params = { {type="field_ref", value="value"} },
  children = {} }

-- Implementation:
local function my_predicate(inst, node)
    local field_name = node.params[1].value
    local v = inst.blackboard[field_name] or 0
    return v > 0
end
```

Predicates are stateless boolean evaluators. They receive no event_id — just `inst` and `node`.

### Pointer-Based Main Functions

Declared with `pt_m_call`. Same signature as `m_call`, but the node has a `pointer_index` and the runtime sets up `inst.pointer_base` / `inst.in_pointer_call` before calling:

```lua
-- Pipeline node:
{ func_name = "MY_PT_MAIN", call_type = "pt_m_call",
  pointer_index = 0,
  params = { {type="int", value=5} },
  children = {} }

-- Implementation (can use pointer slot for persistent storage):
local se_runtime = require("se_runtime")

local function my_pt_main(inst, node, event_id, event_data)
    if event_id == se_runtime.SE_EVENT_INIT then
        -- Store initial value in pointer slot
        se_runtime.set_u64(inst, node, 0)
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    if event_id == se_runtime.SE_EVENT_TERMINATE then
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    -- TICK: use pointer slot as counter
    local count = se_runtime.get_u64(inst, node)
    local limit = node.params[1].value
    count = count + 1
    se_runtime.set_u64(inst, node, count)

    if count >= limit then
        return se_runtime.SE_PIPELINE_DISABLE
    end
    return se_runtime.SE_PIPELINE_CONTINUE
end
```

### IO-Call Functions (Survives Reset)

Declared with `io_call`. Same signature as `o_call`, but the runtime uses `FLAG_EVER_INIT` instead of `FLAG_INITIALIZED` as the fire-once guard. The function runs once for the *lifetime* of the tree instance, even across resets:

```lua
-- Pipeline node:
{ func_name = "MY_IO_INIT", call_type = "io_call",
  params = {},
  children = {} }

-- Implementation:
local function my_io_init(inst, node)
    -- This runs exactly once, ever, even if the tree is reset
    print("one-time hardware initialization")
end
```

## Accessing Parameters

Parameters are in `node.params[]`, a 1-based Lua array of `{type, value}` tables. Access them directly or use the runtime helpers:

### Direct Access

```lua
local function my_function(inst, node)
    local params = node.params or {}

    -- Check parameter count
    assert(#params >= 2, "my_function: need 2 parameters")

    -- Access by index (1-based)
    local int_val   = params[1].value           -- number
    local str_val   = params[2].value           -- string
    local field_name = params[3].value          -- string (for field_ref)

    -- Check type if needed
    if params[1].type == "int" or params[1].type == "uint" then
        -- integer parameter
    elseif params[1].type == "float" then
        -- float parameter
    elseif params[1].type == "field_ref" then
        -- blackboard field name
    end
end
```

### Using Runtime Helpers

The `se_runtime` module exports parameter accessors that handle type coercion:

```lua
local se_runtime = require("se_runtime")

local function my_function(inst, node)
    -- Integer with coercion (string → number)
    local n = se_runtime.param_int(node, 1)

    -- Float with coercion
    local f = se_runtime.param_float(node, 2)

    -- String (handles str_hash → .str extraction)
    local s = se_runtime.param_str(node, 3)

    -- Field name (for field_ref params)
    local fname = se_runtime.param_field_name(node, 1)

    -- Read blackboard field (with string→number coercion)
    local v = se_runtime.field_get(inst, node, 1)

    -- Write blackboard field
    se_runtime.field_set(inst, node, 1, 42)
end
```

## Parameter Types

| Pipeline `type` | `value` type | Access | Description |
|----------------|-------------|--------|-------------|
| `"int"` | number | `params[i].value` or `param_int(node, i)` | Signed integer |
| `"uint"` | number | `params[i].value` or `param_int(node, i)` | Unsigned integer |
| `"float"` | number | `params[i].value` or `param_float(node, i)` | Float |
| `"str_ptr"` | string | `params[i].value` or `param_str(node, i)` | String literal |
| `"str_idx"` | string | `params[i].value` or `param_str(node, i)` | Interned string |
| `"str_hash"` | `{hash, str}` | `params[i].value.str` or `param_str(node, i)` | String with hash |
| `"field_ref"` | string | `param_field_name(node, i)` | Blackboard field name |
| `"stack_local"` | number | via `se_stack.get_local` | Stack frame local |
| `"stack_tos"` | number | via `se_stack.peek_tos` | Stack TOS offset |
| `"const_ref"` | any | `inst.mod.module_data.constants[key]` | Constants reference |

## Accessing Instance State

User functions have full access to the tree instance:

```lua
local function my_function(inst, node)
    -- Blackboard (string-keyed table)
    local temp = inst.blackboard["temperature"]
    inst.blackboard["output"] = temp * 1.5

    -- Node state (per-node flags, state, user_data)
    local ns = se_runtime.get_ns(inst, node.node_index)
    ns.user_data = ns.user_data + 1

    -- User context (application-defined, set by caller after new_instance)
    local app = inst.user_ctx
    if app and app.hardware then
        app.hardware:write_register(0x40, 0x01)
    end

    -- Module data
    local records = inst.mod.module_data.records

    -- Time
    local now = inst.mod.get_time()

    -- Stack (if present)
    if inst.stack then
        local se_stack = require("se_stack")
        local top_val = se_stack.peek_tos(inst.stack, 0)
    end

    -- Event queue
    se_runtime.event_push(inst, 0xFFFF, 42, nil)
end
```

## Accessing Children

User-defined composites (main functions with children) can invoke their children using the child API:

```lua
local se_runtime = require("se_runtime")

local function my_composite(inst, node, event_id, event_data)
    if event_id == se_runtime.SE_EVENT_INIT then
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    if event_id == se_runtime.SE_EVENT_TERMINATE then
        se_runtime.children_terminate_all(inst, node)
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    -- TICK: invoke children
    local children = node.children or {}

    for i = 1, #children do
        local child = children[i]
        local idx = i - 1   -- 0-based for child_invoke

        -- Invoke child (dispatches by call_type automatically)
        local r = se_runtime.child_invoke(inst, node, idx, event_id, event_data)

        -- Invoke as predicate specifically
        -- local pred_result = se_runtime.child_invoke_pred(inst, node, idx)

        -- Invoke as oneshot specifically
        -- se_runtime.child_invoke_oneshot(inst, node, idx)

        -- Handle result code
        if r == se_runtime.SE_PIPELINE_DISABLE then
            se_runtime.child_terminate(inst, node, idx)
        elseif r == se_runtime.SE_PIPELINE_TERMINATE then
            se_runtime.children_terminate_all(inst, node)
            return se_runtime.SE_PIPELINE_TERMINATE
        end
    end

    return se_runtime.SE_PIPELINE_CONTINUE
end
```

Available child helpers:

| Function | Purpose |
|----------|---------|
| `child_count(node)` | Number of callable children |
| `child_invoke(inst, node, idx, event_id, event_data)` | Invoke by 0-based index via `invoke_any` |
| `child_invoke_pred(inst, node, idx)` | Invoke child as predicate → boolean |
| `child_invoke_oneshot(inst, node, idx)` | Invoke child as oneshot |
| `child_terminate(inst, node, idx)` | Send TERMINATE to child |
| `child_reset(inst, node, idx)` | Reset child flags |
| `child_reset_recursive(inst, node, idx)` | Recursively reset child subtree |
| `children_terminate_all(inst, node)` | Terminate all children (reverse order) |
| `children_reset_all(inst, node)` | Reset all children |

## Event Handling Patterns

### Oneshot Pattern

Oneshots don't receive events — the runtime handles fire-once semantics. The function body runs exactly once:

```lua
local function my_oneshot(inst, node)
    -- This entire body runs once per activation (o_call)
    -- or once per lifetime (io_call)
    local val = se_runtime.param_int(node, 1)
    inst.blackboard["config_value"] = val
end
```

### Main Function Pattern

Main functions receive all three event types:

```lua
local function my_main(inst, node, event_id, event_data)
    -- INIT: set up state
    if event_id == se_runtime.SE_EVENT_INIT then
        se_runtime.get_ns(inst, node.node_index).user_data = 0
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    -- TERMINATE: clean up
    if event_id == se_runtime.SE_EVENT_TERMINATE then
        return se_runtime.SE_PIPELINE_CONTINUE
    end

    -- TICK: do work
    local ns = se_runtime.get_ns(inst, node.node_index)
    ns.user_data = ns.user_data + 1

    if ns.user_data >= 10 then
        return se_runtime.SE_PIPELINE_DISABLE   -- triggers auto-TERMINATE
    end

    return se_runtime.SE_PIPELINE_CONTINUE
end
```

### Predicate Pattern

Predicates are stateless booleans:

```lua
local function my_predicate(inst, node)
    local field_name = se_runtime.param_field_name(node, 1)
    local threshold  = se_runtime.param_int(node, 2)
    local value      = inst.blackboard[field_name] or 0
    return value > threshold
end
```

## Function Name Convention

- **Pipeline / module_data**: `UPPER_SNAKE_CASE` (e.g., `"CFL_ENABLE_CHILD"`)
- **Lua function key**: `lower_snake_case` (e.g., `cfl_enable_child`)

Registration is case-insensitive — `register_fns` uppercases all keys before matching against the module's function lists. So `cfl_enable_child` matches `CFL_ENABLE_CHILD` in the module's `oneshot_funcs`.

## File Organization

Unlike the C workflow which generates header and registration files, the LuaJIT workflow keeps everything in Lua:

```
project/
├── module_data/
│   └── my_module.lua               # Pipeline output (module_data)
├── builtins/
│   ├── se_runtime.lua               # Core engine
│   ├── se_stack.lua                 # Parameter stack
│   ├── se_builtins_flow_control.lua # Flow control composites
│   ├── se_builtins_pred.lua         # Predicates
│   ├── se_builtins_oneshot.lua      # Oneshot builtins
│   └── ... (other builtin modules)
├── user/
│   ├── user_functions.lua           # User-defined functions
│   └── hardware_interface.lua       # Hardware-specific functions
└── test/
    └── test_harness.lua             # Test runner
```

**user_functions.lua:**

```lua
local se_runtime = require("se_runtime")
local M = {}

M.cfl_disable_children = function(inst, node)
    -- implementation
end

M.cfl_enable_child = function(inst, node)
    local child_index = node.params[1].value
    -- implementation
end

M.my_sensor_read = function(inst, node)
    -- Read sensor via user_ctx hardware handle
    local hw = inst.user_ctx
    local channel = se_runtime.param_int(node, 1)
    local value = hw:adc_read(channel)
    se_runtime.field_set(inst, node, 2, value)
end

return M
```

**test_harness.lua:**

```lua
local se_runtime = require("se_runtime")
local module_data = require("my_module")
local user_fns = require("user_functions")

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
    user_fns   -- user functions merged in
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "my_tree")

-- Tick loop
for _ = 1, 100 do
    local result = se_runtime.tick_once(inst)
    if result == se_runtime.SE_FUNCTION_TERMINATE then break end
end
```

## Example: Chain Flow Control Functions

### cfl_disable_children

Disables all children in the current chain flow context:

```lua
-- Pipeline node:
{ func_name = "CFL_DISABLE_CHILDREN", call_type = "o_call",
  params = {}, children = {} }

-- Implementation:
local function cfl_disable_children(inst, node)
    -- Access parent's children through user_ctx or custom mechanism
    print("cfl_disable_children: disabling all children")
end
```

### cfl_enable_child

Enables a specific child by index:

```lua
-- Pipeline node:
{ func_name = "CFL_ENABLE_CHILD", call_type = "o_call",
  params = { {type="int", value=0} },
  children = {} }

-- Implementation:
local function cfl_enable_child(inst, node)
    local child_index = node.params[1].value
    print("cfl_enable_child: enabling child " .. child_index)
end
```

## Summary

1. **Write** Lua functions matching the appropriate signature (`fn(inst, node)` for oneshots/preds, `fn(inst, node, event_id, event_data)` for mains)
2. **Include** the function name in `module_data`'s function lists (handled by pipeline)
3. **Register** via `merge_fns` alongside builtins
4. **Validate** automatically when `new_instance` is called

No code generation, no header files, no hash tables, no registration callbacks. The same function table mechanism that registers builtins handles user functions identically. The only distinction between a builtin and a user function is which Lua module exports it.