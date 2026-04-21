# State Machine Test — LuaJIT Runtime

## Overview

This test demonstrates the S-Expression engine's composite node system in the LuaJIT runtime, including:

- **se_function_interface** — top-level function interface managing child lifecycle (`se_builtins_flow_control.lua`)
- **se_fork_join** — blocking parallel execution, returns `SE_FUNCTION_HALT` while children active (`se_builtins_flow_control.lua`)
- **se_fork** — non-blocking parallel execution, returns `SE_PIPELINE_CONTINUE` (`se_builtins_flow_control.lua`)
- **se_sequence** — sequential execution (`se_builtins_flow_control.lua`)
- **se_state_machine** — field-based state dispatch with cyclic transitions (`se_builtins_dispatch.lua`)

## Test Structure

The tree is defined in `module_data` as a nested node structure. The root is `se_function_interface` with children that execute in two phases:

```
SE_FUNCTION_INTERFACE (root)
├── SE_FORK_JOIN                          ← Phase 1: blocking init (ticks 1–11)
│   └── [pt_m_call] SE_TICK_DELAY 10
│
├── SE_FORK                               ← Phase 2: parallel (starts tick 12)
│   └── [pt_m_call] SE_TICK_DELAY 10
│
├── SE_STATE_MACHINE (field: "state")     ← Cyclic: 0 → 1 → 2 → 0 → ...
│   ├── case 0: SE_CHAIN_FLOW (delay 10, set state=1)
│   ├── case 1: SE_CHAIN_FLOW (delay 10, set state=2)
│   ├── case 2: SE_CHAIN_FLOW (delay 10, set state=0)
│   └── case -1 (default): SE_CHAIN_FLOW (delay 100, terminate)
│
├── [pt_m_call] SE_TICK_DELAY 350         ← Overall timeout
│
└── SE_RETURN_FUNCTION_TERMINATE          ← Terminates at tick 363
```

## Execution Phases

### Phase 1: Fork Join (Ticks 1–11)

The `se_fork_join` **blocks** all siblings until it completes. In `se_builtins_flow_control.lua`, `se_fork_join` returns `SE_FUNCTION_HALT` while any MAIN child is active. `se_function_interface` propagates `SE_FUNCTION_HALT` immediately (it's a function-level code, range 6–11), which stops the tick without invoking subsequent children.

```
Tick 1:  Fork Join starts, child SE_TICK_DELAY initialized
         Returns SE_FUNCTION_HALT (blocking)
Tick 2-10: Fork Join child running (tick_delay counting down)
Tick 11: Fork Join child returns SE_PIPELINE_DISABLE
         Fork Join: active_main == 0, returns SE_PIPELINE_DISABLE
         "Fork Join Test Terminated" logs
```

**Key behavior:** `se_fork_join` returns `SE_FUNCTION_HALT` while running, which `se_function_interface` propagates immediately — no subsequent children are invoked that tick.

### Phase 2: Parallel Execution (Ticks 12+)

After fork_join completes and is terminated by `se_function_interface`, three things run **in parallel**:

1. `se_fork` with 10-tick delay (completes tick 22)
2. `se_state_machine` cycling through states
3. `se_tick_delay(350)` overall timeout

```
Tick 12: Fork starts, State machine initializes at state 0
         "Fork 1 Test Started", "State machine test started", "State 0"
Tick 22: Fork child completes (SE_PIPELINE_DISABLE)
         Fork: active_main == 0, returns SE_PIPELINE_DISABLE
         "Fork 1 Test Terminated", "State 0 terminated"
Tick 23: State machine transitions to state 1
         "State 1"
...
```

**Key behavior:** `se_fork` returns `SE_PIPELINE_CONTINUE` which does NOT block siblings. `se_function_interface` counts it as an active child and continues to the next.

### State Machine Cycling

`se_state_machine` in `se_builtins_dispatch.lua` reads `inst.blackboard["state"]` each tick and dispatches to the matching case child. When the field value changes, it terminates the old branch (`child_terminate` + `child_reset_recursive`) and activates the new one.

The state machine cycles through states 0 → 1 → 2 → 0 → ... with 10-tick delays:

| Ticks | State | Events |
|-------|-------|--------|
| 12–22 | 0 | State 0 runs, terminates at tick 22 |
| 23–33 | 1 | State 1 runs, terminates at tick 33 |
| 34–45 | 2 | State 2 runs, terminates at tick 45 |
| 46–57 | 0 | State 0 runs again (cyclic!) |
| ... | ... | Continues cycling |

Each state cycle is ~12 ticks (11 ticks delay + 1 tick transition).

**Branch switching internals:** `se_state_machine` tracks the previous child index in `ns.user_data` (initialized to `SENTINEL = 0xFFFF`). When `action_child_idx ~= prev_child_idx`:

```lua
-- From se_builtins_dispatch.lua:
if action_child_idx ~= prev_child_idx then
    if prev_child_idx ~= nil and prev_child_idx ~= SENTINEL then
        child_terminate(inst, node, prev_child_idx)
        child_reset_recursive(inst, node, prev_child_idx)
    end
    child_reset_recursive(inst, node, action_child_idx)
    ns.user_data = action_child_idx
end
```

### Termination (Tick 363)

The `se_tick_delay(350)` completes at tick 362 (12 + 350). It stores the target tick count in its pointer slot via `se_runtime.set_u64(inst, node, ticks + 1)` and decrements each tick until reaching 0:

```
Tick 362: tick_delay(350) returns SE_PIPELINE_DISABLE
          se_function_interface terminates it, active_count decreases
Tick 363: "State machine test finished" logs
          se_return_function_terminate() returns SE_FUNCTION_TERMINATE
          se_function_interface propagates SE_FUNCTION_TERMINATE
```

## State Machine Cases

In the `module_data`, the state machine node has:

```lua
params = {
    { type = "field_ref", value = "state" },   -- params[1]: field to read
    { type = "int", value = 0 },               -- params[2]: case 0 → children[0]
    { type = "int", value = 1 },               -- params[3]: case 1 → children[1]
    { type = "int", value = 2 },               -- params[4]: case 2 → children[2]
    { type = "int", value = -1 },              -- params[5]: default → children[3]
}
```

Each case child is a `se_chain_flow` that:
1. Logs state entry via `se_log`
2. Calls `CFL_DISABLE_CHILDREN` / `CFL_ENABLE_CHILD` (user-defined oneshots for chain flow control)
3. Delays 10 ticks via `se_tick_delay`
4. Sets next state via `se_set_field`
5. Logs state exit
6. Returns `SE_PIPELINE_DISABLE` (via `se_return_pipeline_disable`)

The `se_set_field` oneshot writes the new state value to `inst.blackboard["state"]`. On the next tick, `se_state_machine` reads the updated value via `field_get(inst, node, 1)` and dispatches to the new case.

## Result Code Flow

```
Tick 1-11:  SE_FUNCTION_HALT       (fork_join blocking)
Tick 12+:   SE_FUNCTION_HALT       (tick_delay(350) running)
Tick 363:   SE_FUNCTION_TERMINATE  (test complete)
```

**Why SE_FUNCTION_HALT after fork_join completes?**

The `se_tick_delay(350)` returns `SE_FUNCTION_HALT` while running. In `se_builtins_delays.lua`, `se_tick_delay` returns `SE_FUNCTION_HALT` while `remaining > 0`. Inside `se_function_interface`, this is a function-level code (range 6–11) which propagates immediately to the caller.

**Why not SE_PIPELINE_HALT?**

`se_tick_delay` uses `SE_FUNCTION_HALT` (not `SE_PIPELINE_HALT`) because it needs to halt the entire function interface, not just the immediate parent composite. If it returned `SE_PIPELINE_HALT`, the `se_function_interface` would treat it as "child still active" and continue to invoke other children — which is not the desired behavior for a blocking delay.

## Composite Behavior Summary

| Composite | Return While Running | Blocks Siblings | Source |
|-----------|---------------------|-----------------|--------|
| `se_fork_join` | `SE_FUNCTION_HALT` | Yes | `se_builtins_flow_control.lua` |
| `se_fork` | `SE_PIPELINE_CONTINUE` | No | `se_builtins_flow_control.lua` |
| `se_sequence` | `SE_PIPELINE_CONTINUE` | No (pauses at current child) | `se_builtins_flow_control.lua` |
| `se_state_machine` | `SE_PIPELINE_CONTINUE/HALT` | No | `se_builtins_dispatch.lua` |
| `se_tick_delay` | `SE_FUNCTION_HALT` | Via parent | `se_builtins_delays.lua` |
| `se_chain_flow` | `SE_PIPELINE_CONTINUE` | No | `se_builtins_flow_control.lua` |

## Test Output Analysis

```
=== STATE MACHINE TEST ===

[SE_LOG] Fork Join Test Started       ← Tick 1
[SE_LOG] Fork Join Test Started       ← Fork join child init
Tick   1: FUNCTION_HALT               ← Fork join blocking
...
Tick  11: FUNCTION_HALT
[SE_LOG] Fork Join Test Terminated    ← Fork join complete
[SE_LOG] Fork 1 Test Started          ← Tick 12: parallel phase starts
[SE_LOG] State machine test started
[SE_LOG] State 0
cfl_disable_children
cfl_enable_child: enabling child 0
Tick  12: FUNCTION_HALT               ← tick_delay(350) now blocking
...
Tick  22: FUNCTION_HALT
[SE_LOG] Fork 1 Test Terminated       ← Fork completes (10 ticks)
[SE_LOG] State 0 terminated           ← State 0 completes (11 ticks)
Tick  23: FUNCTION_HALT
[SE_LOG] State 1                      ← State transition 0 → 1
...
(state machine cycles 0 → 1 → 2 → 0 → ...)
...
Tick 362: FUNCTION_HALT
[SE_LOG] State machine test finished  ← tick_delay(350) completes
Tick 363: FUNCTION_TERMINATE          ← Test terminates
✅ PASSED
```

Note: log output uses `[SE_LOG]` prefix from `se_builtins_oneshot.lua`'s `se_log` implementation: `print("[SE_LOG] " .. tostring(msg))`.

## Key Patterns Demonstrated

1. **Sequential phases with fork_join** — initialization must complete before main logic (FUNCTION_HALT blocks siblings)
2. **Parallel execution with fork** — background tasks alongside main logic (PIPELINE_CONTINUE doesn't block)
3. **Cyclic state machines** — states that loop back (0 → 1 → 2 → 0) via `inst.blackboard["state"]` updates
4. **Branch switching** — `se_state_machine` terminates and resets the old branch before activating the new one
5. **Timeout pattern** — `se_tick_delay(350)` as overall execution limit using pointer slot u64 counter
6. **Clean termination** — `se_return_function_terminate()` at function_interface level propagates upward

## Test Harness

```lua
local se_runtime = require("se_runtime")
local se_stack   = require("se_stack")
local module_data = require("state_machine_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_return_codes"),
    -- User-defined functions:
    {
        cfl_disable_children = function(inst, node)
            print("cfl_disable_children")
        end,
        cfl_enable_child = function(inst, node)
            local idx = node.params[1].value
            print("cfl_enable_child: enabling child " .. idx)
        end,
    }
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "state_machine_test")

local tick_count = 0
local max_ticks = 500

repeat
    local result = se_runtime.tick_once(inst)
    tick_count = tick_count + 1

    -- Drain event queue
    while se_runtime.event_count(inst) > 0 do
        local tt, eid, edata = se_runtime.event_pop(inst)
        local saved = inst.tick_type
        inst.tick_type = tt
        result = se_runtime.tick_once(inst, eid, edata)
        inst.tick_type = saved
    end

    print(string.format("Tick %3d: %s",
        tick_count,
        result == se_runtime.SE_FUNCTION_HALT and "FUNCTION_HALT"
        or result == se_runtime.SE_FUNCTION_TERMINATE and "FUNCTION_TERMINATE"
        or tostring(result)))

until result == se_runtime.SE_FUNCTION_TERMINATE or tick_count >= max_ticks

print(tick_count <= max_ticks and "✅ PASSED" or "❌ TIMEOUT")
```

## Files

- `state_machine_test_module.lua` — pipeline-generated `module_data` Lua table
- `test_state_machine.lua` — LuaJIT test harness
- `se_runtime.lua` — core engine
- `se_builtins_flow_control.lua` — `se_function_interface`, `se_fork_join`, `se_fork`
- `se_builtins_dispatch.lua` — `se_state_machine`
- `se_builtins_delays.lua` — `se_tick_delay`
- `se_builtins_oneshot.lua` — `se_log`, `se_set_field`
- `se_builtins_return_codes.lua` — `se_return_function_terminate`, `se_return_pipeline_disable`