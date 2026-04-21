# SE User Functions

S-Engine user functions run inside the S-Expression engine, not directly in ChainTree. They are registered via the module registry and dispatched by the SE tick loop.

## SE Function Types

### Oneshot

```lua
fn(inst, node) -> nil
```

Called once when the SE node is first reached. Use for initialization, I/O commands, state writes.

### Main

```lua
fn(inst, node, event_id, event_data) -> se_return_code
```

Called every tick for active SE nodes. Must handle `SE_EVENT_INIT` and `SE_EVENT_TERMINATE` events (typically return `SE_CONTINUE`). Returns an SE return code (`se.SE_CONTINUE`, `se.SE_HALT`, `se.SE_DISABLE`, `se.SE_TERMINATE`).

### Predicate

```lua
fn(inst, node, event_id, event_data) -> boolean
```

Guards for conditional execution. Return true/false to control flow.

## Parameter Access

```lua
local se = require("se_runtime")

-- Read integer parameter at 1-based index
local motor_id = se.param_int(node, 1)

-- Read string parameter
local name = se.param_str(node, 1)

-- Read/write instance fields
local val = se.field_get(inst, node, 1)
se.field_set(inst, node, 1, new_value)

-- Per-node state
local ns = se.get_ns(inst, node.node_index)
ns.counter = 0

-- Push events to SE event queue
se.event_push(inst, tick_type, event_id, event_data)

-- Event count check
local count = se.event_count(inst)
```

## Event Handling

SE functions receive events through the `event_id` parameter. Standard SE events:

- `se.SE_EVENT_INIT` -- node initialization
- `se.SE_EVENT_TERMINATE` -- node cleanup
- `se.SE_EVENT_TICK` (= 4, matches `CFL_TIMER_EVENT`) -- normal tick

CFL events like `CFL_SECOND_EVENT` (5), `CFL_MINUTE_EVENT` (6) pass through directly when the SE instance is ticked by the ChainTree bridge.

User-defined events use custom integer IDs (e.g., `0xEE01` for timer, `0xEE02` for button). Push them with `se.event_push()` and dispatch them by checking `event_id` in main functions.

## Registration

SE user functions are registered by passing a `user_fns` table to `se_bridge.register_def`:

```lua
local se_user_fns = require("se_user_functions")

se_bridge.register_def(reg, "module_name", module_data, se_user_fns)
```

The `user_fns` table is a flat name-to-function map. Function names must match those referenced in the compiled S-Engine module data.

Alternatively, register via a boolean function callback in the DSL:

```lua
ct:se_module_load("module_name", "USER_REGISTER_S_FUNCTIONS")
```

The boolean function `USER_REGISTER_S_FUNCTIONS` is called during module load to register user functions.

## Examples from se_user_functions.lua

### Oneshot: motor control

```lua
M.TEST_31_SET_MOTOR = function(inst, node)
    if #node.params < 2 then return end
    local motor_id = se.param_int(node, 1)
    local speed    = se.param_int(node, 2)
    print(string.format("TEST_31_SET_MOTOR: MOTOR[%d] = %d", motor_id, speed))
end
```

### Oneshot: field write

```lua
M.TEST_31_SET_STATE = function(inst, node)
    if #node.params < 2 then return end
    local value = se.param_int(node, 2)
    se.field_set(inst, node, 1, value)
end
```

### Main: threshold check

```lua
M.TEST_32_CHECK_THRESHOLD = function(inst, node, event_id, event_data)
    if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
        return se.SE_CONTINUE
    end
    if #node.params < 2 then return se.SE_TERMINATE end
    if event_id == EVT_SENSOR then
        local reading = tonumber(event_data) or 0
        local threshold = se.param_int(node, 2)
        if reading > threshold then
            print(string.format("SENSOR: ABOVE THRESHOLD (%d > %d)", reading, threshold))
        end
    end
    return se.SE_CONTINUE
end
```

### Main: internal event generation

```lua
M.TEST_32_GENERATE_INTERNAL_EVENTS = function(inst, node, event_id, event_data)
    if event_id == se.SE_EVENT_INIT then
        local ns = se.get_ns(inst, node.node_index)
        ns.counter = 0
        return se.SE_CONTINUE
    end
    if event_id == se.SE_EVENT_TERMINATE then return se.SE_CONTINUE end
    if event_id ~= CFL_TIMER_EVENT then return se.SE_CONTINUE end

    local ns = se.get_ns(inst, node.node_index)
    ns.counter = (ns.counter or 0) + 1

    if ns.counter % 100 == 0 then
        se.event_push(inst, 0, EVT_TIMER, 0)
    end
    -- ... additional event generation based on counter
    return se.SE_CONTINUE
end
```

### Oneshot: I/O stubs

```lua
M.TEST_32_ENABLE_BUZZER = function(inst, node) print("BUZZER: ENABLED") end
M.TEST_32_DISABLE_ALL_OUTPUTS = function(inst, node) print("OUTPUTS: ALL DISABLED") end
M.TEST_32_TOGGLE_LED = function(inst, node)
    local led_id = se.param_int(node, 1)
    print(string.format("LED[%d]: TOGGLED", led_id))
end
```
