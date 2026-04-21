# Advanced Primitive Test — LuaJIT Runtime

## Overview

This test is a derivative of the Dispatch Test that extends the original event-driven state machine with additional S-Engine primitives. It retains the core `se_event_dispatch` + `se_state_machine` structure from the dispatch test and adds exercising of `se_if_then_else` and `se_cond` — the two predicate-driven branching constructs in `se_builtins_flow_control.lua`.

## Relationship to Dispatch Test

The dispatch test combines three parallel mechanisms: `se_event_dispatch`, `se_field_dispatch`, and `se_state_machine`. This derivative makes two structural changes:

1. **Removed** `se_field_dispatch` — the field-reactive dispatch is dropped to focus the test on predicate-based branching.
2. **Added** `se_if_then_else` and `se_cond` — event handlers now use predicate children (`se_check_event`) to demonstrate conditional branching within event processing and as a standalone parallel instruction.

The state machine and event dispatch remain identical in structure.

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

After `se_runtime.new_instance()`, these become string-keyed entries in `inst.blackboard`.

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
├── SE_EVENT_DISPATCH                     ← handles queued events
│   ├── case 1: handler with se_if_then_else
│   ├── case 2: handler (log + display)
│   ├── case 3: handler (log + display + set state)
│   ├── case 4: handler with se_if_then_else
│   └── case -1 (default): SE_RETURN_PIPELINE_HALT
│
├── SE_COND                               ← predicate dispatch (NEW)
│   ├── (se_check_event(1,3), action)     ← pred/action pair
│   ├── (se_check_event(2), action)
│   ├── (se_check_event(4), action)
│   └── (se_true, default action)         ← default case
│
├── SE_STATE_MACHINE (field: "state")     ← generates events
│   ├── case 0: delay 20, queue events 1+2, set state=1
│   ├── case 1: delay 20, queue events 3+4, set state=2
│   └── case 2: delay 20, SE_RETURN_TERMINATE
│
└── [implicit: all run in parallel within se_function_interface]
```

Compared to the dispatch test, `se_field_dispatch` is replaced by `SE_COND` which exercises Lisp-style predicate-driven conditional dispatch.

## New Primitives Tested

### se_if_then_else (`se_builtins_flow_control.lua`)

Used inside event handlers to demonstrate predicate-driven branching within an event action. In the tree structure:

```lua
-- Node structure for se_if_then_else:
{ func_name = "SE_IF_THEN_ELSE", call_type = "m_call",
  children = {
    -- children[0]: predicate (p_call or p_call_composite)
    { func_name = "SE_CHECK_EVENT", call_type = "p_call",
      params = {
        { type = "uint", value = 1 },   -- matches USER_EVENT_1
        -- OR: { type = "uint", value = 3 } for multi-event check
      } },
    -- children[1]: then branch
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call", children = { ... } },
    -- children[2]: else branch
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call", children = { ... } },
  } }
```

Two event handlers (for USER_EVENT_1 and USER_EVENT_4) embed `se_if_then_else` to test:

- **Predicate as child node** — `se_check_event` is a `p_call` child at index 0, evaluated by `child_invoke_pred(inst, node, 0)` each tick
- **Multi-event predicates** — `se_check_event` with params matching USER_EVENT_1 or USER_EVENT_3 checks `inst.current_event_id` against each param value
- **Branch selection** — `se_if_then_else` invokes `child_invoke(inst, node, 1, ...)` for then-branch or `child_invoke(inst, node, 2, ...)` for else-branch based on predicate result

**Runtime behavior** (from `se_builtins_flow_control.lua`):

```lua
-- Predicate re-evaluated every tick:
local condition = child_invoke_pred(inst, node, 0)

if condition then
    r = child_invoke(inst, node, 1, event_id, event_data)   -- then branch
elseif has_else then
    r = child_invoke(inst, node, 2, event_id, event_data)   -- else branch
end
```

On `SE_PIPELINE_RESET` or `SE_PIPELINE_DISABLE` from either branch, both branches are terminated and reset — ensuring clean state for the next evaluation.

### se_cond (`se_builtins_flow_control.lua`)

The `SE_COND` node exercises Lisp-style conditional dispatch as a standalone instruction running in parallel with the event dispatch and state machine. Children are arranged as (pred, action) pairs at even/odd indices:

```lua
-- Node structure for se_cond:
{ func_name = "SE_COND", call_type = "m_call",
  children = {
    -- children[0]: pred for case 1 (p_call)
    { func_name = "SE_CHECK_EVENT", call_type = "p_call",
      params = { {type="uint", value=1}, {type="uint", value=3} } },
    -- children[1]: action for case 1 (m_call)
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call",
      children = {
        { func_name = "SE_LOG", call_type = "o_call",
          params = { {type="str_ptr", value="Matched EVENT_1 or EVENT_3"} } },
        -- ... display + reset
      } },

    -- children[2]: pred for case 2
    { func_name = "SE_CHECK_EVENT", call_type = "p_call",
      params = { {type="uint", value=2} } },
    -- children[3]: action for case 2
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call", children = { ... } },

    -- children[4]: pred for case 3
    { func_name = "SE_CHECK_EVENT", call_type = "p_call",
      params = { {type="uint", value=4} } },
    -- children[5]: action for case 3
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call", children = { ... } },

    -- children[6]: default pred (SE_TRUE)
    { func_name = "SE_TRUE", call_type = "p_call", params = {}, children = {} },
    -- children[7]: default action
    { func_name = "SE_CHAIN_FLOW", call_type = "m_call",
      children = {
        { func_name = "SE_RETURN_PIPELINE_RESET", call_type = "m_call" },
      } },
  } }
```

**Runtime behavior** (from `se_builtins_flow_control.lua`):

```lua
-- Scan (pred, action) pairs; first true pred wins
local matched_action = NO_CHILD
local i = 1   -- 1-based Lua index
while i <= n do
    local child = children[i]
    if child.call_type == "p_call" or child.call_type == "p_call_composite" then
        local pred_result = child_invoke_pred(inst, node, i - 1)
        if pred_result and matched_action == NO_CHILD then
            matched_action = i   -- 0-based action child index
            break
        end
        i = i + 2   -- skip past action
    else
        i = i + 1
    end
end
```

On branch change (`matched_action ~= ns.user_data`), the old action is terminated and reset, then the new action is terminated and reset before invocation — ensuring clean state per branch switch.

This tests:
- **First-match semantics** — predicates evaluated in order, first true wins
- **Predicate children at even indices** — `se_check_event` as `p_call` nodes
- **Default case** — `SE_TRUE` predicate always matches as fallback
- **Branch tracking** — `ns.user_data` tracks the active action child index (`NO_CHILD = 0xFFFF` when no match)
- **Parallel operation** — `se_cond` runs alongside `se_event_dispatch` and `se_state_machine` within `se_function_interface`

### se_check_event (`se_builtins_pred.lua`)

The predicate used by both `se_if_then_else` and `se_cond`. Checks if `inst.current_event_id` matches any of its params:

```lua
M.se_check_event = function(inst, node)
    local p = (node.params or {})[1]
    if not p then return false end
    local check_id = (type(p.value) == "table") and p.value.hash or p.value
    return inst.current_event_id == check_id
end
```

For multi-event checks (matching EVENT_1 or EVENT_3), the pipeline generates a composite predicate wrapping multiple `se_check_event` nodes in `se_pred_or`:

```lua
{ func_name = "SE_PRED_OR", call_type = "p_call_composite",
  children = {
    { func_name = "SE_CHECK_EVENT", call_type = "p_call",
      params = { {type="uint", value=1} } },
    { func_name = "SE_CHECK_EVENT", call_type = "p_call",
      params = { {type="uint", value=3} } },
  } }
```

### Event Display Functions

Shared action subtrees used by both `se_if_then_else` branches. In the tree they appear as `SE_CHAIN_FLOW` children:

```
-- Then branch:
SE_CHAIN_FLOW
├── [o_call] SE_LOG "if then branch start"
├── [o_call] DISPLAY_EVENT_INFO           ← user-defined oneshot
├── [o_call] SE_LOG "if then branch end"
└── SE_RETURN_PIPELINE_RESET

-- Else branch:
SE_CHAIN_FLOW
├── [o_call] SE_LOG "if else branch start"
├── [o_call] DISPLAY_EVENT_INFO
├── [o_call] SE_LOG "if else branch end"
└── SE_RETURN_PIPELINE_RESET
```

## Execution Flow

### Phase 1: State 0 (Ticks 1–21)

1. State machine starts in state 0 (via `se_set_field("state", 0)`)
2. `se_cond` evaluates predicates each tick — `inst.current_event_id == SE_EVENT_TICK (0xFFFF)`, so no `se_check_event` matches; default case runs (`SE_RETURN_PIPELINE_RESET`)
3. `se_event_dispatch` receives `SE_EVENT_TICK` each tick — no case matches event_id 0xFFFF, so default case runs (`SE_RETURN_PIPELINE_HALT`)
4. After 20 ticks, state 0's body:
   - Sets `inst.blackboard["event_data_1"] = 1.1`
   - Sets `inst.blackboard["event_data_2"] = 2.2`
   - Calls `se_queue_event(1, USER_EVENT_1, "event_data_1")`
   - Calls `se_queue_event(1, USER_EVENT_2, "event_data_2")`
   - Sets `inst.blackboard["state"] = 1`

### Phase 2: Event Processing After State 0

The tick loop drains the event queue (save/set/restore `inst.tick_type`):

1. **USER_EVENT_1** → `se_event_dispatch` case 1:
   - Calls `DISPLAY_EVENT_INFO` (shows event_data_1 = 1.1)
   - `se_if_then_else`: `se_check_event` with params {1, 3} — `inst.current_event_id == 1` → **true** → **then branch** fires
   - Then branch logs "if then branch start", calls `DISPLAY_EVENT_INFO`, logs "if then branch end"
   - Sets `inst.blackboard["state"] = 1`

   Meanwhile, `se_cond` also processes EVENT_1: the first case `se_check_event(1,3)` matches → logs "Matched EVENT_1 or EVENT_3" + `DISPLAY_EVENT_INFO`

2. **USER_EVENT_2** → `se_event_dispatch` case 2:
   - Calls `DISPLAY_EVENT_INFO` (shows event_data_2 = 2.2)

   Meanwhile, `se_cond`: the second case `se_check_event(2)` matches → logs + displays

### Phase 3: State 1 (Ticks 22–42)

1. State machine reads `inst.blackboard["state"] == 1`, dispatches to state 1 case
2. After 20 ticks, queues `USER_EVENT_3` and `USER_EVENT_4`

### Phase 4: Event Processing After State 1

1. **USER_EVENT_3** → `se_event_dispatch` case 3:
   - Calls `DISPLAY_EVENT_INFO` (shows event_data_3 = 3.3)
   - Sets `inst.blackboard["state"] = 2`

   `se_cond`: first case `se_check_event(1,3)` matches EVENT_3 → logs + displays

2. **USER_EVENT_4** → `se_event_dispatch` case 4:
   - `se_if_then_else`: `se_check_event` with params {1, 3} — `inst.current_event_id == 4` → **false** → **else branch** fires
   - Else branch logs "if else branch start", calls `DISPLAY_EVENT_INFO`, logs "if else branch end"

   `se_cond`: third case `se_check_event(4)` matches → logs + displays

### Phase 5: State 2 — Termination

1. State machine reads `inst.blackboard["state"] == 2`, dispatches to state 2 case
2. After 20 ticks, returns `SE_TERMINATE` (application code 2)
3. `se_function_interface` propagates `SE_TERMINATE` — tree terminates

## Component Interactions

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SE_FUNCTION_INTERFACE                           │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │ SE_EVENT_        │  │ SE_COND          │  │ SE_STATE_MACHINE    │ │
│  │ DISPATCH         │  │ (predicate       │  │ (field: "state")   │ │
│  │                  │  │  dispatch)       │  │                     │ │
│  │ case 1:          │  │                  │  │  case 0:            │ │
│  │   if_then_else   │  │ check(1,3):     │  │   queue_event(1)   │ │
│  │   (check 1|3)    │  │   log+display   │  │   queue_event(2)   │ │
│  │   → state=1      │  │                  │  │   state=1          │ │
│  │                  │  │ check(2):        │  │                     │ │
│  │ case 3:          │  │   log+display   │  │  case 1:            │ │
│  │   → state=2      │  │                  │  │   queue_event(3)   │ │
│  │                  │  │ check(4):        │  │   queue_event(4)   │ │
│  │ case 4:          │  │   log+display   │  │   state=2          │ │
│  │   if_then_else   │  │                  │  │                     │ │
│  │   (check 1|3)    │  │ default:         │  │  case 2:            │ │
│  │                  │  │   reset (no-op)  │  │   → TERMINATE       │ │
│  │ default: halt    │  │                  │  │                     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## LuaJIT Test Harness

```lua
local se_runtime = require("se_runtime")
local module_data = require("advanced_primitive_test_module")

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
            print(string.format("DISPLAY_EVENT_INFO: event_id=%s data=%s",
                tostring(inst.current_event_id),
                tostring(inst.current_event_data and
                    inst.blackboard[inst.current_event_data] or "nil")))
        end,
    }
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "advanced_primitive_test")

local tick_count = 0
local max_ticks = 100

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

-- Verify
assert(inst.blackboard["state"] == 2,
    "Expected state=2, got " .. tostring(inst.blackboard["state"]))
print(string.format("Completed in %d ticks", tick_count))
print(tick_count < max_ticks and "✅ PASSED" or "❌ TIMEOUT")
```

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_if_then_else`, `se_cond`, `se_chain_flow` | Control flow and branching |
| `se_builtins_dispatch.lua` | `se_event_dispatch`, `se_state_machine` | Event routing and state dispatch |
| `se_builtins_pred.lua` | `se_check_event`, `se_true`, `se_pred_or` | Predicate evaluation |
| `se_builtins_oneshot.lua` | `se_log`, `se_set_field`, `se_queue_event` | Logging, field writes, event queueing |
| `se_builtins_delays.lua` | `se_tick_delay` | Multi-tick delay in state cases |
| `se_builtins_return_codes.lua` | `se_return_pipeline_halt`, `se_return_pipeline_reset`, `se_return_terminate` | Fixed return codes |
| `se_runtime.lua` | `tick_once`, `event_push/pop/count`, `invoke_pred`, `child_invoke_pred` | Core dispatch and event queue |

## Files

| File | Description |
|------|-------------|
| `advanced_primitive_test_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_advanced_primitive.lua` | LuaJIT test harness |
| `se_builtins_flow_control.lua` | `se_if_then_else`, `se_cond` implementations |
| `se_builtins_dispatch.lua` | `se_event_dispatch`, `se_state_machine` |
| `se_builtins_pred.lua` | `se_check_event`, `se_true`, `se_pred_or` |

## Key Concepts Demonstrated

1. **se_if_then_else with predicate children** — predicate is a `p_call` child node evaluated by `child_invoke_pred` each tick, not a boolean value
2. **se_cond parallel operation** — Lisp-style conditional dispatch runs alongside event dispatch and state machine within `se_function_interface`
3. **Reusable action subtrees** — then/else branch node trees shared across multiple event handler contexts
4. **Multi-event predicates** — `se_pred_or` wrapping multiple `se_check_event` children matches any listed event ID
5. **se_cond default case** — `SE_TRUE` predicate as `p_call` child ensures fallback always matches
6. **Event generation and dual handling** — state machine generates events consumed by both `se_event_dispatch` (case matching on event_id) and `se_cond` (predicate matching on `inst.current_event_id`)
7. **Branch tracking in se_cond** — `ns.user_data` tracks active action child; branch switch triggers `child_terminate` + `child_reset_recursive` on old branch

## Differences from Dispatch Test

| Aspect | Dispatch Test | Advanced Primitive Test |
|--------|--------------|------------------------|
| Module name | `dispatch_test` | `advanced_primitive_test` |
| Parallel composites | event_dispatch + field_dispatch + state_machine | event_dispatch + se_cond + state_machine |
| se_field_dispatch | Yes | No |
| se_if_then_else | No | Yes (inside event handlers) |
| se_cond | No | Yes (standalone parallel instruction) |
| Event handler complexity | Simple log + display + set_field | Includes conditional branching via predicate children |
| Predicate types used | None (dispatch is value-based) | `se_check_event`, `se_pred_or`, `se_true` |

## Test Pass Criteria

The test passes when:

- Tree terminates normally (result is `SE_TERMINATE` or `SE_FUNCTION_TERMINATE`)
- `inst.blackboard["state"] == 2` (state machine progressed 0 → 1 → 2)
- Events are properly generated by `se_queue_event` and drained by tick loop
- `se_if_then_else` selects correct branch based on `inst.current_event_id`
- `se_cond` matches correct case for each event via `se_check_event` predicates
- Total ticks < max_ticks (100)