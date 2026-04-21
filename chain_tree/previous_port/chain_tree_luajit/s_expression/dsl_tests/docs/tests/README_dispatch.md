# Dispatch Test — LuaJIT Runtime

## Overview

This test demonstrates the S-Engine's event-driven architecture by combining three dispatch mechanisms running in parallel:

1. **se_event_dispatch** (`se_builtins_dispatch.lua`) — handles user events from the queue
2. **se_field_dispatch** (`se_builtins_dispatch.lua`) — reacts to blackboard field changes
3. **se_state_machine** (`se_builtins_dispatch.lua`) — generates events and drives state transitions

The test shows how these components interact to create a reactive, event-driven system within the LuaJIT runtime.

## Test Structure

### Blackboard Record

In `module_data.records`:

```lua
records["state_machine_blackboard"] = {
    fields = {
        state        = { type = "int32", default = 0 },
        event_data_1 = { type = "float", default = 0 },
        event_data_2 = { type = "float", default = 0 },
        event_data_3 = { type = "float", default = 0 },
        event_data_4 = { type = "float", default = 0 },
    }
}
```

After `se_runtime.new_instance()`, these become `inst.blackboard["state"]`, `inst.blackboard["event_data_1"]`, etc.

### Event Constants

```lua
local USER_EVENT_TYPE = 1
local USER_EVENT_1 = 1
local USER_EVENT_2 = 2
local USER_EVENT_3 = 3
local USER_EVENT_4 = 4
```

### Tree Architecture

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_SET_FIELD state = 0
├── [o_call] SE_LOG "State machine test started"
│
├── SE_EVENT_DISPATCH                          ← handles queued events
│   ├── case 1 (USER_EVENT_1): handler + set state=1
│   ├── case 2 (USER_EVENT_2): handler
│   ├── case 3 (USER_EVENT_3): handler + set state=2
│   ├── case 4 (USER_EVENT_4): handler
│   └── case -1 (default): SE_RETURN_PIPELINE_HALT
│
├── SE_FIELD_DISPATCH (field: "state")         ← reacts to state field changes
│   ├── case 1: field_actions[1] (logs + display)
│   ├── case 2: field_actions[2] (logs + display)
│   └── case -1 (default): field_actions[3] (default handler)
│
└── SE_STATE_MACHINE (field: "state")          ← generates events
    ├── case 0: delay 20, queue events 1+2, set state=1
    ├── case 1: delay 20, queue events 3+4, set state=2
    └── case 2: delay 20, SE_RETURN_TERMINATE
```

All three composites run **in parallel** within `se_function_interface`.

## Component Interactions

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SE_FUNCTION_INTERFACE                           │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ SE_EVENT_        │  │ SE_FIELD_        │  │ SE_STATE_MACHINE    │ │
│  │ DISPATCH         │  │ DISPATCH         │  │ (field: "state")   │ │
│  │                  │  │ (field: "state") │  │                     │ │
│  │ case 1:          │  │                  │  │  case 0:            │ │
│  │   display+log    │  │ case 1:          │  │   queue_event(1)   │ │
│  │   → state=1      │  │   field_actions  │  │   queue_event(2)   │ │
│  │                  │  │   [1] runs       │  │   state=1          │ │
│  │ case 3:          │  │                  │  │                     │ │
│  │   display+log    │  │ case 2:          │  │  case 1:            │ │
│  │   → state=2      │  │   field_actions  │  │   queue_event(3)   │ │
│  │                  │  │   [2] runs       │  │   queue_event(4)   │ │
│  │ default:         │  │                  │  │   state=2          │ │
│  │   halt (no-op)   │  │ default:         │  │                     │ │
│  │                  │  │   field_actions   │  │  case 2:            │ │
│  │                  │  │   [3] runs       │  │   → TERMINATE       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Dispatch Mechanisms

### se_event_dispatch (`se_builtins_dispatch.lua`)

Dispatches based on `event_id`. Stateless — no branch tracking, each event independently matched:

```lua
M.se_event_dispatch = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT or event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    -- Search params for matching case value
    for i = 1, #params do
        local case_val = params[i].value
        if case_val == event_id then
            return invoke_and_handle_result(inst, node, i - 1, event_id, event_data)
        end
        if case_val == -1 then
            default_child_idx = i - 1
        end
    end

    -- No match → default case
    if default_child_idx then
        return invoke_and_handle_result(inst, node, default_child_idx, event_id, event_data)
    end

    error("se_event_dispatch: no matching handler for event_id=" .. tostring(event_id))
end
```

During regular ticks (`event_id = SE_EVENT_TICK = 0xFFFF`), no case matches → default fires (typically `SE_RETURN_PIPELINE_HALT`). During user event ticks, the matching handler fires.

### se_field_dispatch (`se_builtins_dispatch.lua`)

Dispatches based on a blackboard field value. Stateful — tracks the active branch in `ns.user_data` and handles branch switching with terminate/reset:

```lua
-- Read field value
local val = field_get(inst, node, 1)   -- inst.blackboard["state"]
val = math.floor(tonumber(val) or 0)

-- Search case values (params[2..N] map to children[0..N-2])
for i = 2, #params do
    local case_val = params[i].value
    if math.floor(case_val) == val then
        action_child_idx = i - 2
        break
    end
    if case_val == -1 then
        default_child_idx = i - 2
    end
end

-- Branch change: terminate old, reset new
if action_child_idx ~= prev_child_idx then
    if prev_child_idx ~= nil and prev_child_idx ~= SENTINEL then
        child_terminate(inst, node, prev_child_idx)
        child_reset_recursive(inst, node, prev_child_idx)
    end
    child_reset_recursive(inst, node, action_child_idx)
    ns.user_data = action_child_idx
end
```

The key difference from `se_state_machine`: `se_field_dispatch` handles `SE_PIPELINE_RESET` differently — it terminates and resets the child, then returns `SE_PIPELINE_CONTINUE`.

### se_state_machine (`se_builtins_dispatch.lua`)

Same dispatch logic as `se_field_dispatch` (read field → match case → branch switch) but with different result handling. `SE_FUNCTION_HALT` from a child is translated to `SE_PIPELINE_HALT`, and pipeline completion codes (DISABLE/TERMINATE/RESET) all result in terminate+reset of the child with `SE_PIPELINE_CONTINUE` returned.

## Execution Flow

### Phase 1: State 0 (Ticks 1–21)

1. State machine reads `inst.blackboard["state"] == 0`, dispatches to case 0
2. `se_event_dispatch` receives `SE_EVENT_TICK` (0xFFFF) each tick — no case matches, default fires (`SE_RETURN_PIPELINE_HALT`)
3. `se_field_dispatch` reads `inst.blackboard["state"] == 0`, dispatches to default case (`field_actions[3]`)
4. After 20 ticks, state 0's body:
   - `se_set_field("event_data_1", 1.1)` → `inst.blackboard["event_data_1"] = 1.1`
   - `se_set_field("event_data_2", 2.2)` → `inst.blackboard["event_data_2"] = 2.2`
   - `se_queue_event(1, 1, "event_data_1")` → pushes `{tick_type=1, event_id=1, event_data="event_data_1"}`
   - `se_queue_event(1, 2, "event_data_2")` → pushes `{tick_type=1, event_id=2, event_data="event_data_2"}`

### Phase 2: Event Processing After Tick 21

The tick loop drains the event queue (save/set/restore `inst.tick_type`):

1. **USER_EVENT_1** → `se_event_dispatch` case 1:
   - `display_event_info` shows event data
   - `se_set_field("state", 1)` → `inst.blackboard["state"] = 1`

2. **USER_EVENT_2** → `se_event_dispatch` case 2:
   - `display_event_info` shows event data
   - No state change

### Phase 3: State 1 (Ticks 22–42)

1. State machine reads `inst.blackboard["state"] == 1`, terminates case 0 branch, resets and dispatches case 1
2. `se_field_dispatch` detects `state == 1`, terminates default branch, resets and dispatches `field_actions[1]`
3. After 20 ticks, queues `USER_EVENT_3` and `USER_EVENT_4`

### Phase 4: Event Processing After Tick 42

1. **USER_EVENT_3** → `se_event_dispatch` case 3:
   - `display_event_info` shows event data (3.3)
   - `se_set_field("state", 2)` → `inst.blackboard["state"] = 2`

2. **USER_EVENT_4** → `se_event_dispatch` case 4:
   - `display_event_info` shows event data (4.4)

### Phase 5: State 2 — Termination

1. State machine reads `inst.blackboard["state"] == 2`, switches to case 2
2. `se_field_dispatch` detects `state == 2`, switches to `field_actions[2]`
3. After 20 ticks, state 2 returns `SE_TERMINATE` (application code 2)
4. `se_function_interface` propagates `SE_TERMINATE` — tree terminates

## User-Defined Function: display_event_info

In the LuaJIT runtime, `event_data` is a **blackboard field name string** (not a byte offset pointer). The function reads the value from the blackboard by name:

```lua
local function display_event_info(inst, node)
    -- In LuaJIT, event_data is a field name string
    local field_name = inst.current_event_data
    local event_id = inst.current_event_id

    print(string.format("[display_event_info] Event ID: %d", event_id))

    if field_name then
        local value = inst.blackboard[field_name]
        print(string.format("[display_event_info] Field: %s = %s",
            tostring(field_name), tostring(value)))
    end
end
```

### Comparison with C Event Data Access

| Aspect | C Runtime | LuaJIT Runtime |
|--------|-----------|----------------|
| `event_data` type | `void*` (byte offset cast) | String (blackboard field name) |
| Access pattern | `(float*)((uint8_t*)blackboard + offset)` | `inst.blackboard[field_name]` |
| Type safety | None (raw pointer cast) | Lua dynamic typing |
| Alignment risk | Yes (ARM hard fault possible) | None |

## Tick Loop Implementation

The standard LuaJIT event processing pattern:

```lua
local se_runtime = require("se_runtime")

local function result_is_complete(r)
    return r ~= se_runtime.SE_PIPELINE_CONTINUE
       and r ~= se_runtime.SE_PIPELINE_DISABLE
end

local tick_count = 0
local max_ticks = 100

repeat
    local result = se_runtime.tick_once(inst, se_runtime.SE_EVENT_TICK, nil)
    tick_count = tick_count + 1

    -- Process queued events
    while se_runtime.event_count(inst) > 0 and not result_is_complete(result) do
        local tick_type, event_id, event_data = se_runtime.event_pop(inst)

        -- Save, set, execute, restore
        local saved_tick_type = inst.tick_type
        inst.tick_type = tick_type

        local event_result = se_runtime.tick_once(inst, event_id, event_data)

        inst.tick_type = saved_tick_type

        if result_is_complete(event_result) then
            result = event_result
            break
        end
    end

until result_is_complete(result) or tick_count >= max_ticks
```

The save/set/restore of `inst.tick_type` is essential for `se_event_dispatch` to distinguish user event ticks from regular ticks.

## se_field_dispatch vs se_state_machine

Both read the same blackboard field and dispatch to case children. The differences:

| Aspect | `se_state_machine` | `se_field_dispatch` |
|--------|-------------------|---------------------|
| `SE_FUNCTION_HALT` from child | Translates to `SE_PIPELINE_HALT` | Propagates as-is |
| `SE_PIPELINE_RESET` from child | Terminate + reset child, return `SE_PIPELINE_CONTINUE` | Terminate + reset child, return `SE_PIPELINE_CONTINUE` |
| Other pipeline results | Terminate + reset child, return `SE_PIPELINE_CONTINUE` | Return child result directly |
| Branch tracking | `ns.user_data` with `SENTINEL = 0xFFFF` | Same |
| Typical use | State machines where branch completion restarts | Field-reactive dispatch where results propagate |

Both use the same branch-switching logic: `child_terminate` + `child_reset_recursive` on the old branch, `child_reset_recursive` on the new branch.

## Complete Test Harness

```lua
local se_runtime = require("se_runtime")
local module_data = require("dispatch_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_return_codes"),
    -- User-defined functions:
    {
        display_event_info = function(inst, node)
            local field_name = inst.current_event_data
            local event_id = inst.current_event_id
            print(string.format("[display_event_info] Event ID: %d", event_id))
            if field_name then
                local value = inst.blackboard[field_name]
                print(string.format("[display_event_info] Field: %s = %s",
                    tostring(field_name), tostring(value)))
            end
        end,
    }
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "dispatch_test")

local tick_count = 0
local max_ticks = 100

local function result_is_complete(r)
    return r ~= se_runtime.SE_PIPELINE_CONTINUE
       and r ~= se_runtime.SE_PIPELINE_DISABLE
end

repeat
    local result = se_runtime.tick_once(inst, se_runtime.SE_EVENT_TICK, nil)
    tick_count = tick_count + 1

    while se_runtime.event_count(inst) > 0 and not result_is_complete(result) do
        local tt, eid, edata = se_runtime.event_pop(inst)
        local saved = inst.tick_type
        inst.tick_type = tt
        local er = se_runtime.tick_once(inst, eid, edata)
        inst.tick_type = saved
        if result_is_complete(er) then
            result = er
            break
        end
    end

until result_is_complete(result) or tick_count >= max_ticks

-- Verify
assert(inst.blackboard["state"] == 2,
    "Expected state=2, got " .. tostring(inst.blackboard["state"]))
print(string.format("Completed in %d ticks", tick_count))
print(tick_count < max_ticks and "✅ PASSED" or "❌ TIMEOUT")
```

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_builtins_dispatch.lua` | `se_event_dispatch`, `se_field_dispatch`, `se_state_machine` | All three dispatch mechanisms |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_chain_flow` | Parallel container, sequential steps |
| `se_builtins_delays.lua` | `se_tick_delay` | Delays between state transitions |
| `se_builtins_oneshot.lua` | `se_log`, `se_set_field`, `se_queue_event` | Logging, field writes, event queueing |
| `se_builtins_return_codes.lua` | `se_return_pipeline_halt`, `se_return_terminate` | Fixed return codes |
| `se_runtime.lua` | `tick_once`, `event_push/pop/count`, `field_get`, `child_invoke`, `child_terminate`, `child_reset_recursive` | Core dispatch, event queue, child lifecycle |

## Files

| File | Description |
|------|-------------|
| `dispatch_test_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_dispatch.lua` | LuaJIT test harness |
| `se_builtins_dispatch.lua` | `se_event_dispatch`, `se_field_dispatch`, `se_state_machine` |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_chain_flow` |

## Key Concepts Demonstrated

1. **Parallel composites** — three dispatch mechanisms running simultaneously within `se_function_interface`, each seeing the same events and blackboard state
2. **Event generation** — state machine generates events via `se_queue_event`, pushing `{tick_type, event_id, field_name}` entries
3. **Event handling** — `se_event_dispatch` matches `event_id` against case params during event ticks (not regular ticks)
4. **Field name as event data** — LuaJIT passes `"event_data_1"` (string) as event_data, not a byte offset; handlers read `inst.blackboard[field_name]`
5. **State transitions via events** — events trigger `se_set_field("state", N)` which changes `inst.blackboard["state"]`, detected by both `se_field_dispatch` and `se_state_machine` on the next tick
6. **Save/set/restore pattern** — `inst.tick_type` saved before event processing, set to the event's tick_type, restored after — essential for `se_event_dispatch` routing
7. **Branch switching** — both `se_field_dispatch` and `se_state_machine` track active branch in `ns.user_data` (SENTINEL = 0xFFFF for none) and terminate+reset on branch change
8. **User-defined oneshot** — `display_event_info` registered via `merge_fns`, reads event context from `inst.current_event_id` and `inst.current_event_data`

## Test Pass Criteria

The test passes when:
- Tree terminates normally (result is `SE_TERMINATE` or `SE_FUNCTION_TERMINATE`)
- `inst.blackboard["state"] == 2` (state machine progressed 0 → 1 → 2)
- Events are properly generated by `se_queue_event` and drained by the tick loop
- `se_field_dispatch` reacts to state changes with branch switching
- Total ticks < max_ticks (100)