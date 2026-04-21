# S-Expression Engine DSL Reference

The S-Expression Engine DSL is a LuaJIT-based language for defining tick-driven behavior trees that compile to zero-copy binary modules. Trees run either standalone or inside ChainTree via the `se_engine`/`se_engine_link` bridge nodes.

For the complete DSL specification, see [s_expression/dsl_tests/docs/README_DSL.md](s_expression/README_DSL.md).

## Quick Reference

### Module Structure

```lua
local mod = start_module("my_module")
use_32bit()    -- or use_64bit()

RECORD("my_blackboard")
    FIELD("counter", "int32")
    FIELD("temperature", "float")
    FIELD("name", "uint32")
    PTR64_FIELD("data_ptr", "my_data")
END_RECORD()

start_tree("my_tree")
    use_record("my_blackboard")
    se_function_interface(function()
        -- tree body
    end)
end_tree("my_tree")

return end_module(mod)
```

### Field Types
- `int32`, `uint32`, `float` — basic types (minimum 4 bytes)
- `PTR64_FIELD("name", "target_type")` — 64-bit pointer field
- `CHAR_ARRAY("name", size)` — fixed-size string buffer

Note: `bool`, `uint8`, `uint16` are not supported — use `int32`/`uint32`.

### Constant Records

```lua
CONST("my_defaults", "my_blackboard")
    VALUE("counter", 0)
    VALUE("temperature", 20.5)
END_CONST()
```

### Composites

```lua
se_function_interface(function() ... end)   -- tree entry point
se_sequence(function() ... end)             -- sequential execution
se_chain_flow(function() ... end)           -- pipeline processing
se_fork(function() ... end)                 -- parallel execution
se_fork_join(function() ... end)            -- parallel, waits for completion
se_state_machine("field", cases)            -- field-based state dispatch
se_field_dispatch("field", cases)           -- field-based case dispatch
se_event_dispatch(cases)                    -- event-based dispatch
se_trigger_on_change(init, pred, then_fn, else_fn)  -- edge-triggered
```

### State Machine / Dispatch Pattern

```lua
local cases = {}
cases[1] = function()
    se_case(0, function()
        se_sequence(function()
            se_chain_flow(function()
                se_log("State 0")
                se_tick_delay(100)
                se_set_field("state", 1)
                se_return_pipeline_disable()
            end)
        end)
    end)
end
cases[2] = function()
    se_case(1, function()
        -- ...
    end)
end

se_state_machine("state", cases)
```

### Event Dispatch Pattern

```lua
local evt = {}
evt[1] = function()
    se_event_case(0xEE01, function()
        se_log("Timer event")
        se_return_halt()
    end)
end
evt[2] = function()
    se_event_case('default', function()
        se_return_continue()
    end)
end

se_event_dispatch(evt)
```

### Timing and Events

```lua
se_tick_delay(50)                   -- hold for N ticks
se_time_delay(2.5)                  -- hold for N seconds
se_wait_event(event_id, timeout)    -- wait for specific event
se_internal_event(event_id, data)   -- queue internal event (s-engine)
```

### Field Operations

```lua
se_set_field("counter", 42)         -- set field (int/float auto-detected)
se_i_set_field("counter", 0)        -- set on init only
se_increment_field("counter", 1)    -- increment
se_decrement_field("counter", 1)    -- decrement
se_log("message")                   -- log with timestamp
```

### Return Codes

Three scopes — each has CONTINUE, HALT, TERMINATE, RESET, DISABLE, SKIP_CONTINUE:

```lua
-- Application scope (propagates to caller)
se_return_continue()
se_return_halt()
se_return_terminate()

-- Function scope (stops at se_function_interface boundary)
se_return_function_continue()
se_return_function_halt()
se_return_function_terminate()

-- Pipeline scope (stops at current composite)
se_return_pipeline_continue()
se_return_pipeline_halt()
se_return_pipeline_disable()
se_return_pipeline_reset()
```

For complete return code documentation, see [s_expression/dsl_tests/docs/README_return_codes.md](s_expression/README_return_codes.md).

### Predicates

```lua
se_pred_or()             -- OR composite
se_pred_and()            -- AND composite
se_pred_not()            -- NOT composite
se_true()                -- always true
se_false()               -- always false
se_field_eq("f", val)    -- field == value
se_field_gt("f", val)    -- field > value
se_check_event(id)       -- event matches
```

For predicate composition, see [s_expression/dsl_tests/docs/README_predicate_system.md](s_expression/README_predicate_system.md).

### Raw Function Calls

```lua
local c = o_call("MY_ONESHOT")      -- oneshot (void return)
    int(42)
    flt(3.14)
    field_ref("my_field")
    nested_field_ref("nested.path")
    str_ptr("string value")
    str("hashed string")
    uint(0xFF)
end_call(c)

local m = m_call("MY_MAIN")         -- main (returns s_expr_result_t)
end_call(m)

local p = p_call("MY_PRED")         -- predicate (returns bool)
end_call(p)

local i = io_call("MY_INIT_ONLY")   -- oneshot, only fires on INIT
end_call(i)
```

### CFL Bridge Helpers (ChainTree Integration)

When running inside ChainTree via `se_engine`, these helpers control ChainTree nodes:

```lua
cfl_enable_children()               -- enable all ChainTree children
cfl_disable_children()              -- disable all ChainTree children
cfl_i_disable_children()            -- disable on init
cfl_enable_child(index)             -- enable specific child
cfl_disable_child(index)            -- disable specific child
cfl_internal_event(event_id, data)  -- post to ChainTree event queue

-- Bitmask predicates (read ChainTree runtime bitmask)
local p = cfl_s_bit_or_start()
    cfl_bit_entry(0, 1)             -- bit indices
end_call(p)

-- JSON reads (from ChainTree node data into s-engine blackboard)
cfl_json_read_float("field", "json.path")
cfl_json_read_uint("field", "json.path")
cfl_json_read_string_buf("field", "json.path")
cfl_json_read_string_ptr("field", "json.path")
cfl_json_read_bool("field", "json.path")

-- Constant record copy
cfl_copy_const_full("const_name")
cfl_copy_const("field", "const_name")
```

For the complete helper reference, see [s_expression/lua_dsl/se_helpers_dir/se_chain_tree.lua](README_cfl_bridge.md).

## Detailed Documentation

The S-Expression engine has extensive documentation:

| Document | Description |
|----------|-------------|
| [README_DSL.md](s_expression/README_DSL.md) | Complete DSL specification |
| [README_return_codes.md](s_expression/README_return_codes.md) | Three-tier return code system |
| [README_predicate_system.md](s_expression/README_predicate_system.md) | Composable predicate API |
| [README_user_defined_functions.md](s_expression/README_user_defined_functions.md) | User function interface |
| [README_composite_functions.md](s_expression/composite_functions/README_composite_functions.md) | Composite function reference |
| [README_top_design.md](s_expression/README_top_design.md) | Architecture overview |
| [README_inner_engine_design.md](s_expression/README_inner_engine_design.md) | Evaluation engine internals |
