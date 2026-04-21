# S-Engine User Event System — LuaJIT Runtime

## Overview

The S-Engine provides a user event system that enables behavior trees to generate and respond to internal events. Events are queued during tree execution and processed by the external tick loop, allowing for reactive event-driven programming within the behavior tree framework. The LuaJIT implementation uses a circular buffer of Lua tables, with identical semantics to the C version.

## Architecture

### Event Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        TICK LOOP (caller-owned)                 │
│                                                                 │
│  1. Regular Tick ──────────────────────────────────────────┐   │
│     se_runtime.tick_once(inst, SE_EVENT_TICK, nil)          │   │
│                                                             │   │
│          ┌──────────────────────────────────────┐          │   │
│          │        BEHAVIOR TREE                 │          │   │
│          │                                      │          │   │
│          │  se_state_machine ───────────────┐   │          │   │
│          │       │                          │   │          │   │
│          │       └─► se_queue_event() ──────┼───┼──► EVENT │   │
│          │                                  │   │    QUEUE │   │
│          │  se_event_dispatch ◄─────────────┘   │          │   │
│          │       │                              │          │   │
│          │       └─► (handles events)           │          │   │
│          └──────────────────────────────────────┘          │   │
│                                                             │   │
│  2. Check Queue ◄───────────────────────────────────────────┘   │
│     event_count = se_runtime.event_count(inst)                  │
│                                                                 │
│  3. Process Events (while event_count > 0)                      │
│     tt, eid, edata = se_runtime.event_pop(inst)                 │
│     saved = inst.tick_type; inst.tick_type = tt                  │
│     se_runtime.tick_once(inst, eid, edata)                      │
│     inst.tick_type = saved                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

1. **Event Queue** — circular buffer in tree instance (capacity 16 events)
2. **tick_type** — field on `inst` that distinguishes regular ticks from user events
3. **se_queue_event** — oneshot builtin that pushes events onto the queue
4. **se_event_dispatch** — composite that dispatches to handlers based on event_id
5. **Caller-owned drain loop** — the runtime does not automatically drain the queue

## Data Structures

### Tree Instance Event Fields

The event queue is initialized by `se_runtime.new_instance()` and stored directly on the `inst` table:

```lua
-- Initialized in new_instance():
inst.event_queue       = {}    -- circular buffer entries (0-based indexed)
inst.event_queue_head  = 0     -- head index
inst.event_queue_count = 0     -- current count

-- Set during tick:
inst.tick_type         = 0     -- SE_EVENT_TICK or user-defined tick type
inst.current_event_id  = 0     -- current event being processed
inst.current_event_data = nil  -- current event payload
```

### Queued Event Entry

Each entry in the circular buffer is a Lua table:

```lua
inst.event_queue[index] = {
    tick_type  = tick_type,   -- number: distinguishes event source
    event_id   = event_id,   -- number: application-defined event identifier
    event_data = event_data,  -- any: payload (typically a blackboard field name)
}
```

### Special Event IDs

```lua
-- Defined in se_runtime.lua:
SE_EVENT_TICK      = 0xFFFF   -- Regular tick
SE_EVENT_INIT      = 0xFFFE   -- Initialization
SE_EVENT_TERMINATE = 0xFFFD   -- Termination
-- User event IDs: any other number (application-defined)
```

The `tick_type` field is separate from `event_id` — it controls how `se_event_dispatch` routes events, while `event_id` is the specific event identifier passed to handlers.

## API Reference

### Queue Management (se_runtime.lua)

```lua
-- Push event onto queue
se_runtime.event_push(inst, tick_type, event_id, event_data)

-- Get number of queued events
local count = se_runtime.event_count(inst)

-- Pop event from queue (returns three values)
local tick_type, event_id, event_data = se_runtime.event_pop(inst)

-- Clear all queued events
se_runtime.event_clear(inst)
```

### Internal Implementation

The queue uses modular arithmetic on a fixed-size circular buffer:

```lua
local EVENT_QUEUE_SIZE = 16

local function eq_push(inst, tick_type, event_id, event_data)
    assert(inst.event_queue_count < EVENT_QUEUE_SIZE,
        "se_runtime: event_queue full")
    local tail = (inst.event_queue_head + inst.event_queue_count) % EVENT_QUEUE_SIZE
    inst.event_queue[tail] = {
        tick_type = tick_type,
        event_id = event_id,
        event_data = event_data
    }
    inst.event_queue_count = inst.event_queue_count + 1
end

local function eq_pop(inst)
    assert(inst.event_queue_count > 0, "se_runtime: event_queue empty")
    local e = inst.event_queue[inst.event_queue_head]
    inst.event_queue_head = (inst.event_queue_head + 1) % EVENT_QUEUE_SIZE
    inst.event_queue_count = inst.event_queue_count - 1
    return e.tick_type, e.event_id, e.event_data
end
```

### DSL Builtin: se_queue_event (oneshot)

Defined in `se_builtins_oneshot.lua`:

```lua
-- params[1] = tick_type (uint)
-- params[2] = event_id (uint)
-- params[3] = field_ref (blackboard field name passed as event_data)
M.se_queue_event = function(inst, node)
    local tt         = param_int(node, 1)
    local eid        = param_int(node, 2)
    local field_name = param_field_name(node, 3)  -- may be nil
    se_runtime.event_push(inst, tt, eid, field_name)
end
```

Note: in the LuaJIT runtime, `event_data` is typically a **field name string** (not a pointer to blackboard memory as in C). The event handler retrieves the actual value via `inst.blackboard[field_name]`.

## Usage

### 1. Define Event Constants

```lua
local USER_EVENT_TYPE = 1   -- tick_type for user events
local USER_EVENT_1 = 1      -- specific event IDs
local USER_EVENT_2 = 2
local USER_EVENT_3 = 3
```

### 2. Queue Events from Tree

Events are queued using `se_queue_event`, which takes:
- `tick_type` — distinguishes this event from regular ticks
- `event_id` — application-defined event identifier
- `field_name` — blackboard field name containing event data

In the pipeline output (module_data), this becomes:

```lua
-- Node that queues an event:
{ func_name = "SE_QUEUE_EVENT", call_type = "o_call",
  params = {
    { type = "uint", value = 1 },                    -- tick_type = USER_EVENT_TYPE
    { type = "uint", value = 1 },                    -- event_id = USER_EVENT_1
    { type = "field_ref", value = "event_data_1" },  -- field name as event_data
  },
  children = {} }
```

Typically used within a state machine case or sequence:

```lua
-- DSL pattern:
-- se_chain_flow
--   se_log("State 0 - generating events")
--   se_tick_delay(20)
--   se_set_field("event_data_1", 1.1)    ← set data in blackboard
--   se_set_field("event_data_2", 2.2)
--   se_queue_event(1, 1, "event_data_1") ← queue event referencing field
--   se_queue_event(1, 2, "event_data_2")
--   se_return_pipeline_reset()
```

### 3. Handle Events with se_event_dispatch

`se_event_dispatch` in `se_builtins_dispatch.lua` dispatches based on `event_id`. It checks each case value in its params against the incoming event_id:

```lua
-- Pipeline output for se_event_dispatch:
{ func_name = "SE_EVENT_DISPATCH", call_type = "m_call",
  params = {
    { type = "int", value = 1 },    -- case: USER_EVENT_1 → children[0]
    { type = "int", value = 2 },    -- case: USER_EVENT_2 → children[1]
    { type = "int", value = -1 },   -- case: default (-1) → children[2]
  },
  children = {
    -- children[0]: handler for USER_EVENT_1
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call",
      children = {
        { func_name = "SE_LOG", call_type = "o_call",
          params = { {type="str_ptr", value="Handling USER_EVENT_1"} } },
        { func_name = "SE_SET_FIELD", call_type = "o_call",
          params = { {type="field_ref", value="state"}, {type="int", value=1} } },
        { func_name = "SE_RETURN_PIPELINE_RESET", call_type = "m_call" },
      } },
    -- children[1]: handler for USER_EVENT_2
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call",
      children = { ... } },
    -- children[2]: default handler (regular ticks)
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call",
      children = {
        { func_name = "SE_RETURN_PIPELINE_HALT", call_type = "m_call" },
      } },
  } }
```

### 4. Implement Tick Loop

The caller owns the tick loop and must drain the event queue after each tick. This is the canonical pattern:

```lua
local se_runtime = require("se_runtime")

local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
local tick_count = 0
local max_ticks = 1000

local function result_is_complete(result)
    return result ~= se_runtime.SE_PIPELINE_CONTINUE
       and result ~= se_runtime.SE_PIPELINE_DISABLE
end

repeat
    -- 1. Regular tick
    local result = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)
    tick_count = tick_count + 1

    -- 2. Process queued events
    local event_count = se_runtime.event_count(inst)

    while event_count > 0 and not result_is_complete(result) do
        -- Pop event from queue
        local tick_type, event_id, event_data = se_runtime.event_pop(inst)

        -- Save, set, execute, restore tick_type
        local saved_tick_type = inst.tick_type
        inst.tick_type = tick_type

        local event_result = se_runtime.tick_once(inst, event_id, event_data)

        inst.tick_type = saved_tick_type

        if result_is_complete(event_result) then
            result = event_result
            break
        end

        event_count = se_runtime.event_count(inst)
    end

until result_is_complete(result) or tick_count >= max_ticks
```

**Critical:** The save/set/restore of `inst.tick_type` is essential. Without it, `se_event_dispatch` cannot distinguish regular ticks from user event ticks.

## How se_event_dispatch Works

The `se_event_dispatch` implementation in `se_builtins_dispatch.lua`:

```lua
M.se_event_dispatch = function(inst, node, event_id, event_data)
    -- INIT/TERMINATE: nothing to do
    if event_id == SE_EVENT_INIT or event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    local params   = node.params or {}
    local default_child_idx = nil

    -- Search for matching case value
    for i = 1, #params do
        local case_val = params[i].value
        if type(case_val) == "number" then
            local child_idx = i - 1   -- 0-based for child_invoke

            if case_val == event_id then
                return invoke_and_handle_result(inst, node, child_idx, event_id, event_data)
            end

            if case_val == -1 then
                default_child_idx = child_idx
            end
        end
    end

    -- No exact match — try default
    if default_child_idx then
        return invoke_and_handle_result(inst, node, default_child_idx, event_id, event_data)
    end

    error("se_event_dispatch: no matching event handler for event_id=" .. tostring(event_id))
end
```

### Dispatch Behavior

During a **regular tick** (`SE_EVENT_TICK = 0xFFFF`), the event_id is `0xFFFF`. Since no case param will have value `0xFFFF`, the default case (-1) fires — typically a `se_return_pipeline_halt` that does nothing.

During a **user event tick**, the event_id is the user-defined value (e.g., 1, 2, 3). The dispatcher matches this against case params and invokes the corresponding child handler.

| tick_type | event_id | Dispatch Target |
|-----------|----------|----------------|
| `SE_EVENT_TICK` (0xFFFF) | 0xFFFF | Default case (-1): typically no-op halt |
| User-defined (e.g., 1) | User event ID (e.g., 1) | Matching case: event handler |

### invoke_and_handle_result

The helper processes the child's result code:

```lua
local function invoke_and_handle_result(inst, node, child_idx, event_id, event_data)
    local r = child_invoke(inst, node, child_idx, event_id, event_data)

    -- Non-PIPELINE codes propagate directly
    if r < SE_PIPELINE_CONTINUE then return r end

    if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
        return r
    end

    -- DISABLE/TERMINATE/RESET: terminate+reset child, return CONTINUE
    if r == SE_PIPELINE_DISABLE
    or r == SE_PIPELINE_TERMINATE
    or r == SE_PIPELINE_RESET then
        child_terminate(inst, node, child_idx)
        child_reset_recursive(inst, node, child_idx)
        return SE_PIPELINE_CONTINUE
    end

    if r == SE_PIPELINE_SKIP_CONTINUE then
        return SE_PIPELINE_CONTINUE
    end

    return SE_PIPELINE_CONTINUE
end
```

This means event handlers that return `SE_PIPELINE_RESET` or `SE_PIPELINE_DISABLE` are terminated and reset for the next event — they don't accumulate state between events.

## Event Data in LuaJIT

### Difference from C

In the C runtime, `event_data` is a `void*` pointer — typically pointing to a blackboard field's memory address. In the LuaJIT runtime, `event_data` is a **blackboard field name string**. The event handler accesses the actual value through the blackboard table:

```lua
-- Queueing (in se_queue_event oneshot):
se_runtime.event_push(inst, tick_type, event_id, "sensor_reading")
-- event_data = "sensor_reading" (string, not a pointer)

-- Handling (in event handler or user function):
local field_name = inst.current_event_data   -- "sensor_reading"
local value = inst.blackboard[field_name]     -- the actual sensor value
```

This is simpler and safer than C's raw pointer approach — no alignment concerns, no dangling pointers, and the field name is self-documenting.

### Setting Event Data Before Queueing

The typical pattern sets the blackboard field, then queues an event referencing it:

```lua
-- Tree nodes in sequence:
--   se_set_field("sensor_data", 25.5)          ← write value to blackboard
--   se_queue_event(1, SENSOR_EVENT, "sensor_data")  ← queue event with field name
```

The event handler retrieves the data:

```lua
-- In a custom event handler function:
local function handle_sensor_event(inst, node, event_id, event_data)
    -- event_data was set by tick_once from the queue pop
    local field_name = inst.current_event_data
    local reading = inst.blackboard[field_name]
    print("Sensor reading: " .. tostring(reading))
    return se_runtime.SE_PIPELINE_CONTINUE
end
```

## Complete Example

### Module Data (Pipeline Output)

```lua
-- module_data structure for an event-driven controller:
M.oneshot_funcs = { "SE_LOG", "SE_SET_FIELD", "SE_QUEUE_EVENT" }
M.main_funcs = {
    "SE_FUNCTION_INTERFACE", "SE_CHAIN_FLOW", "SE_EVENT_DISPATCH",
    "SE_STATE_MACHINE", "SE_TICK_DELAY",
    "SE_RETURN_PIPELINE_RESET", "SE_RETURN_PIPELINE_HALT",
    "SE_RETURN_TERMINATE"
}
M.pred_funcs = {}
```

### Tree Structure

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_SET_FIELD state = 0
│
├── SE_EVENT_DISPATCH
│   ├── case 1 (SENSOR_EVENT): SE_CHAIN_FLOW
│   │   ├── [o_call] SE_LOG "Sensor event received"
│   │   ├── [o_call] SE_SET_FIELD state = 1
│   │   └── SE_RETURN_PIPELINE_RESET
│   │
│   ├── case 2 (TIMER_EVENT): SE_CHAIN_FLOW
│   │   ├── [o_call] SE_LOG "Timer event received"
│   │   └── SE_RETURN_PIPELINE_RESET
│   │
│   ├── case 3 (ALARM_EVENT): SE_CHAIN_FLOW
│   │   ├── [o_call] SE_LOG "ALARM!"
│   │   ├── [o_call] SE_SET_FIELD state = 99
│   │   └── SE_RETURN_PIPELINE_RESET
│   │
│   └── case -1 (default): SE_CHAIN_FLOW
│       └── SE_RETURN_PIPELINE_HALT
│
├── SE_STATE_MACHINE (field: "state")
│   ├── case 0: SE_CHAIN_FLOW
│   │   ├── [o_call] SE_LOG "Idle - checking sensors"
│   │   ├── [pt_m_call] SE_TICK_DELAY 10
│   │   ├── [o_call] SE_SET_FIELD sensor_data = 25.5
│   │   ├── [o_call] SE_QUEUE_EVENT(1, 1, "sensor_data")  ← generates event
│   │   └── SE_RETURN_PIPELINE_RESET
│   │
│   └── case 1: SE_CHAIN_FLOW
│       ├── ... (process sensor data)
│       └── SE_RETURN_PIPELINE_RESET
│
└── SE_RETURN_TERMINATE
```

### Tick Loop

```lua
local se_runtime = require("se_runtime")

-- Create module and instance
local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_oneshot"),
    require("se_builtins_dispatch"),
    require("se_builtins_delays"),
    require("se_builtins_return_codes"),
    -- ... other builtins ...
)
local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "event_demo")

-- Run tick loop
local tick_count = 0
local max_ticks = 500

local function result_is_complete(r)
    return r ~= se_runtime.SE_PIPELINE_CONTINUE
       and r ~= se_runtime.SE_PIPELINE_DISABLE
end

repeat
    local result = se_runtime.tick_once(inst, se_runtime.SE_EVENT_TICK, nil)
    tick_count = tick_count + 1

    -- Drain event queue
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

print(string.format("Completed after %d ticks", tick_count))
```

## Cross-Tree Events (se_builtins_spawn.lua)

The spawn builtins use the same event queue mechanism for child trees. `se_spawn_and_tick_tree` and `se_tick_tree` both drain the child's event queue after ticking:

### tick_with_event_queue (internal helper)

```lua
local function tick_with_event_queue(child, event_id, event_data)
    local result = se_runtime.tick_once(child, event_id, event_data)

    local event_count = se_runtime.event_count(child)
    while event_count > 0 and not result_is_complete(result) do
        local tick_type, ev_id, ev_data = se_runtime.event_pop(child)

        local saved_tick_type = child.tick_type
        child.tick_type = tick_type

        local event_result = se_runtime.tick_once(child, ev_id, ev_data)

        child.tick_type = saved_tick_type

        if result_is_complete(event_result) then
            result = event_result
            break
        end

        event_count = se_runtime.event_count(child)
    end

    return result
end
```

`se_spawn_and_tick_tree` additionally drains the **parent's** event queue and forwards events to the child, enabling cross-tree event propagation.

## Configuration

### Queue Size

Default queue capacity is 16 events, defined in `se_runtime.lua`:

```lua
local EVENT_QUEUE_SIZE = 16
```

The queue is a circular buffer using head/count management. If you need more capacity, modify this constant before creating instances.

### Error Handling

| Error | Behavior |
|-------|----------|
| Queue full on push | `assert` failure: `"se_runtime: event_queue full"` |
| Queue empty on pop | `assert` failure: `"se_runtime: event_queue empty"` |

Both are fatal errors caught by Lua's error propagation. The caller can wrap the tick loop in `pcall` for recovery.

## Comparison with C Implementation

| Aspect | C Runtime | LuaJIT Runtime |
|--------|-----------|----------------|
| Queue storage | `s_expr_queued_event_t` C struct array (inline in instance) | Lua table array on `inst.event_queue` |
| event_data type | `void*` (raw pointer to blackboard memory) | Any Lua value (typically field name string) |
| Queue size | `#define S_EXPR_EVENT_QUEUE_SIZE 16` | `local EVENT_QUEUE_SIZE = 16` |
| Push/pop | `s_expr_event_push/pop` C functions | `se_runtime.event_push/pop` Lua functions |
| Error on full | `EXCEPTION()` → watchdog reset | `assert()` → Lua error |
| tick_type field | `uint16_t` on C struct | Number on Lua table |
| Tick loop | C `do/while` with pointer dereferences | Lua `repeat/until` with table access |
| Drain pattern | Identical logic | Identical logic |

The event flow, queue semantics, tick_type save/restore pattern, and drain loop structure are all identical between C and LuaJIT.

## Best Practices

1. **Always drain the queue after each tick** — events generated during a tick should be processed before the next tick to maintain responsive behavior.

2. **Always provide a default case in se_event_dispatch** — with value `-1`. Regular ticks (event_id = 0xFFFF) won't match any user event case, so the default handler runs. Typically returns `SE_PIPELINE_HALT` to do nothing on regular ticks.

3. **Save/set/restore tick_type** — essential for `se_event_dispatch` to distinguish event ticks from regular ticks. Without this, all ticks look the same to the dispatcher.

4. **Store event data in blackboard fields** — set the field value before queueing the event. The event_data carries the field name, and the handler reads the value from the blackboard.

5. **Process all events before next tick** — continue popping until the queue is empty or the tree terminates. Events may generate more events (the queue can grow during processing).

6. **Use result_is_complete to stop early** — if an event handler returns a completing result (TERMINATE, RESET, HALT), stop processing further events.

## Comparison with External Events

| Aspect | Internal Events (queue) | External Events |
|--------|------------------------|-----------------|
| Source | Tree via `se_queue_event` oneshot | Application code via `se_runtime.event_push` |
| Timing | Processed after generating tick | Injected before or between ticks |
| Data | Blackboard field name (string) | Any Lua value |
| Use case | Inter-component communication within tree | Hardware interrupts, network messages, timers |

External events can be injected by calling `se_runtime.event_push(inst, tick_type, event_id, data)` directly from application code, or by calling `se_runtime.tick_once(inst, custom_event_id, custom_data)` to deliver an event immediately without queueing.