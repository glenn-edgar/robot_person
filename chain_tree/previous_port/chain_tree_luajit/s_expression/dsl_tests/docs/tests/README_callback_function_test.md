# Callback Function Test — LuaJIT Runtime

## Overview

This test demonstrates the S-expression engine's ability to store and execute callable s-expressions via blackboard fields. A function is defined as a Lua closure over a child subtree, loaded into a blackboard field at runtime, and then executed indirectly through that field reference.

## Mechanism

### se_load_function (io_call oneshot)

Stores a Lua closure wrapping a child subtree into a blackboard field. The closure captures the child node table and calls `se_runtime.invoke_any()` when invoked.

- **DSL**: `se_load_function(blackboard_field, fn)`
- **Builtin**: `se_load_function` in `se_builtins_spawn.lua`
- **Call type**: `io_call` (oneshot that survives tree reset — runs once per lifetime)

**Implementation:**

```lua
M.se_load_function = function(inst, node)
    local field_name = param_field_name(node, 1)
    local child = node.children and node.children[1]
    assert(child and child.node_index,
        "se_load_function: no child subtree to load")

    local child_node = child

    -- Build closure that invokes the child subtree
    local fn = function(calling_inst, _exec_node, eid, edata)
        return se_runtime.invoke_any(calling_inst, child_node, eid, edata)
    end

    inst.blackboard[field_name] = fn
end
```

Unlike the C version which stores a ROM pointer to a compiled param array, the LuaJIT version stores a Lua closure. The closure captures the child node table by reference — no allocation beyond the closure itself.

### se_exec_fn (m_call main)

Reads the callable closure from the blackboard field and invokes it each tick. Caches the function reference in `ns.cached_fn` on INIT for fast TICK access. Maps `SE_PIPELINE_DISABLE` to `SE_PIPELINE_CONTINUE` so completion of the inner callable does not disable the caller.

- **DSL**: `se_exec_function(blackboard_field)`
- **Builtin**: `se_exec_fn` in `se_builtins_spawn.lua`
- **Call type**: `m_call` (main with INIT/TICK/TERMINATE lifecycle)

**Implementation:**

```lua
M.se_exec_fn = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local field_name = param_field_name(node, 1)
        local fn = inst.blackboard[field_name]
        assert(type(fn) == "function",
            "se_exec_fn: blackboard field is not a function: " .. tostring(field_name))
        -- Cache for fast TICK access
        get_ns(inst, node.node_index).cached_fn = fn
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: invoke the cached closure
    local fn = get_ns(inst, node.node_index).cached_fn
    local result = fn(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE

    -- DISABLE → CONTINUE: keep caller alive after inner callable completes
    if result == SE_PIPELINE_DISABLE then
        result = SE_PIPELINE_CONTINUE
    end

    return result
end
```

## Test Structure

### Blackboard Record

```lua
records["callback_function_blackboard"] = {
    fields = {
        fn_ptr = { type = "ptr64", default = 0 },
    }
}
```

In the LuaJIT runtime, `inst.blackboard["fn_ptr"]` holds a Lua closure (not a typed pointer). The `ptr64` type annotation is informational for C cross-reference.

### Tree Structure

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_LOG "callback test started"
│
├── [io_call] SE_LOAD_FUNCTION                      ← stores closure in blackboard
│   params: [{type="field_ref", value="fn_ptr"}]
│   children:
│   └── SE_SEQUENCE_ONCE                            ← the callable subtree
│       ├── [o_call] SE_LOG "callback function called"
│       ├── [o_call] SE_LOG "do some stack work"
│       └── [o_call] SE_LOG "call a dictionary function"
│
├── [m_call] SE_EXEC_FN                             ← invokes closure from blackboard
│   params: [{type="field_ref", value="fn_ptr"}]
│
└── SE_RETURN_FUNCTION_TERMINATE
```

### Execution Flow

1. `se_function_interface` INIT: resets all children, sets state to RUNNING
2. **Tick 1**: iterates children in order:
   - `se_log("callback test started")` — oneshot fires, prints message
   - `se_load_function("fn_ptr", ...)` — io_call oneshot fires:
     - Captures `children[1]` (the `se_sequence_once` subtree)
     - Builds closure: `fn = function(inst, node, eid, edata) return invoke_any(inst, child_node, eid, edata) end`
     - Stores: `inst.blackboard["fn_ptr"] = fn`
   - `se_exec_fn("fn_ptr")` — m_call INIT:
     - Reads `inst.blackboard["fn_ptr"]` → the closure
     - Validates it's a function
     - Caches in `get_ns(inst, node.node_index).cached_fn`
   - `se_exec_fn("fn_ptr")` — m_call TICK:
     - Calls `cached_fn(inst, node, SE_EVENT_TICK, nil)`
     - Closure calls `invoke_any(inst, se_sequence_once_node, SE_EVENT_TICK, nil)`
     - `se_sequence_once` fires all children in one tick:
       - `se_log("callback function called")` — prints
       - `se_log("do some stack work")` — prints
       - `se_log("call a dictionary function")` — prints
     - `se_sequence_once` returns `SE_PIPELINE_DISABLE`
     - `invoke_any` propagates `SE_PIPELINE_DISABLE`
     - `se_exec_fn` maps `SE_PIPELINE_DISABLE` → `SE_PIPELINE_CONTINUE`
   - `se_return_function_terminate()` — returns `SE_FUNCTION_TERMINATE`
3. `se_function_interface` propagates `SE_FUNCTION_TERMINATE` to caller

## Expected Output

```
[SE_LOG] callback test started
[SE_LOG] callback function called
[SE_LOG] do some stack work
[SE_LOG] call a dictionary function
Tick 1: result=FUNCTION_TERMINATE
```

## Key Design Points

- **Indirection**: The callable is not invoked directly in the tree. It is stored as a Lua closure in the blackboard and dispatched at runtime, enabling callback patterns and configurable behavior.

- **Closure capture**: The LuaJIT version captures the child node table by reference in a Lua closure. This is the equivalent of the C version's ROM pointer storage — but more flexible since the closure can capture any Lua state.

- **DISABLE → CONTINUE mapping**: `se_exec_fn` converts `SE_PIPELINE_DISABLE` to `SE_PIPELINE_CONTINUE`. Without this, the inner callable completing would deactivate `se_exec_fn` itself (via `invoke_main`'s automatic TERMINATE on DISABLE). The mapping keeps the exec node alive for repeated invocations.

- **Function caching**: On INIT, `se_exec_fn` reads the closure from the blackboard and caches it in `ns.cached_fn`. This avoids a blackboard lookup on every tick — the cached reference is a direct Lua function pointer.

- **io_call semantics**: `se_load_function` uses `io_call` (survives reset) rather than `o_call`. This means the closure is stored once for the entire lifetime of the tree instance, even across resets. The `FLAG_EVER_INIT` guard in `invoke_oneshot` prevents re-execution.

## Comparison with C Implementation

| Aspect | C Runtime | LuaJIT Runtime |
|--------|-----------|----------------|
| Stored value | `s_expr_param_t*` pointer to ROM param array | Lua closure over child node table |
| Storage location | PTR64 blackboard field (raw pointer cast) | `inst.blackboard["fn_ptr"]` (Lua value) |
| Allocation | None (pointer to ROM) | Closure allocation (one-time, GC-managed) |
| Node state reset | `se_exec_fn` resets all callable nodes before invocation | `invoke_any` handles lifecycle via `invoke_main` |
| Invocation | `s_expr_invoke_any(inst, params, ...)` on param array | `fn(inst, node, eid, edata)` → `invoke_any(inst, child_node, ...)` |
| Field type | `uint64_t` cast to `s_expr_param_t*` | Plain Lua function value |

## Related Functions

| DSL Function | LuaJIT Builtin | Module | Type | Purpose |
|---|---|---|---|---|
| `se_load_function` | `se_load_function` | `se_builtins_spawn.lua` | `io_call` | Store closure in blackboard |
| `se_exec_function` | `se_exec_fn` | `se_builtins_spawn.lua` | `m_call` | Execute closure from blackboard |
| `se_load_function_dict` | `se_load_function_dict` | `se_builtins_dict.lua` | `o_call` | Build `{hash → closure}` dict in blackboard |
| `se_exec_dict_fn` | `se_exec_dict_dispatch` | `se_builtins_spawn.lua` | `m_call` | Execute dict entry by compile-time key hash |
| `se_exec_dict_fn_ptr` | `se_exec_dict_fn_ptr` | `se_builtins_spawn.lua` | `m_call` | Execute dict entry by runtime blackboard key |
| `se_exec_dict_internal` | `se_exec_dict_internal` | `se_builtins_spawn.lua` | `m_call` | Execute sibling dict entry (uses `inst.current_dict`) |

## Test Harness

```lua
local se_runtime = require("se_runtime")
local module_data = require("callback_function_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_oneshot"),
    require("se_builtins_spawn"),
    require("se_builtins_return_codes"),
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "callback_function")

local result = se_runtime.tick_once(inst)
print(string.format("Tick 1: result=%s",
    result == se_runtime.SE_FUNCTION_TERMINATE and "FUNCTION_TERMINATE"
    or tostring(result)))

assert(result == se_runtime.SE_FUNCTION_TERMINATE, "Expected FUNCTION_TERMINATE")
print("✅ PASSED")
```

## Files

| File | Description |
|------|-------------|
| `callback_function_test_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_callback_function.lua` | LuaJIT test harness |
| `se_builtins_spawn.lua` | `se_load_function`, `se_exec_fn` implementations |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_sequence_once` |