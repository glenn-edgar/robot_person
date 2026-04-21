# Loop Test — Nested Loop Execution Example (LuaJIT Runtime)

## Overview

This test demonstrates nested `se_while` loops with both state-based and field-based counter predicates in the LuaJIT runtime. It validates the loop control flow, predicate initialization, and proper termination behavior of the S-Expression engine. The loops are implemented by `se_while` in `se_builtins_flow_control.lua`, with predicates from `se_builtins_pred.lua`.

## Module Data

The pipeline generates a `module_data` table (see `loop_test_module.lua`) containing:

```lua
M.oneshot_funcs = { "SE_SET_FIELD", "SE_LOG", "SE_LOG_INT", "SE_INC_FIELD" }
M.main_funcs    = { "SE_FUNCTION_INTERFACE", "SE_FORK_JOIN", "SE_WHILE",
                    "SE_CHAIN_FLOW", "SE_TICK_DELAY",
                    "SE_RETURN_PIPELINE_DISABLE", "SE_RETURN_TERMINATE" }
M.pred_funcs    = { "SE_STATE_INCREMENT_AND_TEST", "SE_FIELD_INCREMENT_AND_TEST" }
```

## Blackboard Record

In `module_data.records`:

```lua
records["loop_test_blackboard"] = {
    fields = {
        outer_sequence_counter = { type = "uint32", default = 0 },
        inner_sequence_counter = { type = "uint32", default = 0 },
        field_test_counter     = { type = "uint32", default = 0 },
        field_test_increment   = { type = "uint32", default = 0 },
        field_test_limit       = { type = "uint32", default = 0 },
    }
}
```

After `se_runtime.new_instance()`, these become `inst.blackboard["outer_sequence_counter"]`, etc.

## Tree Structure

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_SET_FIELD outer_sequence_counter = 0
├── [o_call] SE_SET_FIELD inner_sequence_counter = 0
│
├── SE_FORK_JOIN                                      ← blocking: runs first 10 iterations
│   └── SE_WHILE
│       ├── children[0]: SE_STATE_INCREMENT_AND_TEST (p_call)
│       │   params: [{type="uint", value=1}, {type="uint", value=10}]
│       └── children[1]: SE_FORK_JOIN (body)
│           └── SE_CHAIN_FLOW (loop_sequence_fn)
│               ├── [o_call] SE_LOG "loop_sequence_fn start"
│               ├── [o_call] SE_LOG_INT "outer_sequence_counter %d"
│               ├── [o_call] SE_INC_FIELD outer_sequence_counter
│               ├── SE_CHAIN_FLOW (inner_sequence_fn)
│               │   ├── [o_call] SE_LOG "inner_sequence_fn start"
│               │   ├── [o_call] SE_LOG_INT "inner_sequence_counter %d"
│               │   ├── [o_call] SE_INC_FIELD inner_sequence_counter
│               │   ├── [pt_m_call] SE_TICK_DELAY 3
│               │   ├── [o_call] SE_LOG "inner_sequence_fn end"
│               │   └── SE_RETURN_PIPELINE_DISABLE
│               ├── [pt_m_call] SE_TICK_DELAY 5
│               ├── [o_call] SE_LOG "loop_sequence_fn end"
│               └── SE_RETURN_PIPELINE_DISABLE
│
├── SE_FORK_JOIN                                      ← blocking: runs second 10 iterations
│   ├── [o_call] SE_SET_FIELD field_test_increment = 1
│   ├── [o_call] SE_SET_FIELD field_test_limit = 10
│   └── SE_WHILE
│       ├── children[0]: SE_FIELD_INCREMENT_AND_TEST (p_call)
│       │   params: [{type="field_ref", value="field_test_counter"},
│       │            {type="field_ref", value="field_test_increment"},
│       │            {type="field_ref", value="field_test_limit"}]
│       └── children[1]: SE_FORK_JOIN (body — same loop_sequence_fn)
│           └── SE_CHAIN_FLOW ...
│
└── SE_RETURN_TERMINATE
```

## se_while Runtime Behavior

From `se_builtins_flow_control.lua`:

```lua
M.se_while = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)

    if event_id == SE_EVENT_INIT then
        ns.state = 0   -- SE_WHILE_EVAL_PRED
        return SE_PIPELINE_CONTINUE
    end

    -- EVAL_PRED state: check predicate
    if ns.state == 0 then
        if not child_invoke_pred(inst, node, 0) then
            return SE_PIPELINE_DISABLE    -- predicate false: loop done
        end
        -- Pred true: reset body and enter RUN_BODY
        child_reset_recursive(inst, node, 1)
        ns.state = 1   -- SE_WHILE_RUN_BODY
    end

    -- RUN_BODY state: tick the body child
    local r = child_invoke(inst, node, 1, event_id, event_data)

    if r == SE_PIPELINE_CONTINUE
    or r == SE_PIPELINE_HALT
    or r == SE_PIPELINE_SKIP_CONTINUE then
        return SE_FUNCTION_HALT     -- body still running, keep alive across ticks
    end

    if r == SE_PIPELINE_DISABLE
    or r == SE_PIPELINE_TERMINATE
    or r == SE_PIPELINE_RESET then
        -- Body complete: terminate, reset, loop back to predicate
        child_terminate(inst, node, 1)
        child_reset_recursive(inst, node, 1)
        ns.state = 0   -- SE_WHILE_EVAL_PRED
        return SE_PIPELINE_HALT     -- re-evaluate pred next tick
    end
end
```

Key mechanics:
- `ns.state` alternates between `0` (EVAL_PRED) and `1` (RUN_BODY)
- Body returns `SE_FUNCTION_HALT` while running (via inner `se_tick_delay`) → `se_while` returns `SE_FUNCTION_HALT` to keep the fork_join alive
- Body returns `SE_PIPELINE_DISABLE` when complete → `se_while` terminates + resets body, goes back to EVAL_PRED
- When predicate returns false → `se_while` returns `SE_PIPELINE_DISABLE` (loop done)

## Execution Profile Analysis

### Phase 1: First se_fork_join (Ticks 1–110)

The first `se_fork_join` blocks (`SE_FUNCTION_HALT`) until all 10 iterations of `loop_test_fn_1` complete.

**Per-iteration breakdown:**

| Step | Ticks | Description |
|------|-------|-------------|
| Iteration start | 1 | Oneshots fire: "loop_sequence_fn start", log counter, increment |
| Inner sequence | 1 | Oneshots fire: "inner_sequence_fn start", log, increment |
| Inner delay | 3 | `se_tick_delay(3)` — `SE_FUNCTION_HALT` propagates up |
| Inner complete | 1 | "inner_sequence_fn end", `SE_PIPELINE_DISABLE` |
| Outer delay | 5 | `se_tick_delay(5)` — `SE_FUNCTION_HALT` propagates up |
| Iteration end | 1 | "loop_sequence_fn end", `SE_PIPELINE_DISABLE`, while loops back |

**Ticks per iteration:** ~11 ticks

**Total for 10 iterations:** ~110 ticks

**Predicate behavior:** `se_state_increment_and_test` uses `ns.user_data` on its node_state table as the counter. Each call increments by `param_int(node, 1)` (= 1) and tests against `param_int(node, 2)` (= 10). Returns `true` while counter ≤ limit, `false` when counter > limit (resets counter to 0):

```lua
M.se_state_increment_and_test = function(inst, node)
    local ns        = get_ns(inst, node.node_index)
    local increment = param_int(node, 1)   -- 1
    local limit     = param_int(node, 2)   -- 10
    ns.user_data = (ns.user_data or 0) + increment
    if ns.user_data > limit then
        ns.user_data = 0
        return false   -- stop loop
    end
    return true        -- continue loop
end
```

### Phase 2: Second se_fork_join (Ticks 111–220)

The second `se_fork_join` runs `loop_test_fn_2`, which first sets up field-based loop parameters via oneshots, then enters `se_while` with a field-based predicate.

**Setup oneshots:**
- `se_set_field("field_test_increment", 1)` → `inst.blackboard["field_test_increment"] = 1`
- `se_set_field("field_test_limit", 10)` → `inst.blackboard["field_test_limit"] = 10`

**Predicate behavior:** `se_field_increment_and_test` reads all three values from blackboard fields each call:

```lua
M.se_field_increment_and_test = function(inst, node)
    local counter   = field_get(inst, node, 1) or 0   -- inst.blackboard["field_test_counter"]
    local increment = field_get(inst, node, 2) or 1   -- inst.blackboard["field_test_increment"]
    local limit     = field_get(inst, node, 3) or 0   -- inst.blackboard["field_test_limit"]
    counter = counter + increment
    se_runtime.field_set(inst, node, 1, counter)       -- write back to blackboard
    return counter <= limit
end
```

**Ticks per iteration:** ~11 ticks (same pattern as first loop)

**Total for 10 iterations:** ~110 ticks

### Phase 3: Termination (Tick 221)

After both `se_fork_join` blocks complete, `se_return_terminate()` returns `SE_TERMINATE` (application code 2). `se_function_interface` propagates this to the caller.

### Summary

| Phase | Ticks | Description |
|-------|-------|-------------|
| First loop (state counter) | 1–110 | 10 iterations × ~11 ticks |
| Second loop (field counter) | 111–220 | 10 iterations × ~11 ticks |
| Termination | 221 | `SE_RETURN_TERMINATE` |
| **Total** | **221** | |

## Key Observations

### Counter Values

The `outer_sequence_counter` and `inner_sequence_counter` blackboard fields are **not** reset between the two loops — they are shared fields in `inst.blackboard`:

```
outer_sequence_counter 0    (iteration 1, first loop)
inner_sequence_counter 0
...
outer_sequence_counter 9    (iteration 10, first loop)
inner_sequence_counter 9
outer_sequence_counter 10   (iteration 1, second loop)
inner_sequence_counter 10
...
outer_sequence_counter 19   (iteration 10, second loop)
inner_sequence_counter 19
```

### Field-Based Loop Configuration

The second loop demonstrates runtime-configurable loop parameters. All three values (`counter`, `increment`, `limit`) are blackboard field references (`{type="field_ref", value="..."}`) rather than fixed constants:

```lua
-- The predicate node's params:
params = {
    {type="field_ref", value="field_test_counter"},     -- counter: read + write
    {type="field_ref", value="field_test_increment"},   -- increment: read
    {type="field_ref", value="field_test_limit"},       -- limit: read
}
```

This pattern allows:
- Dynamic loop counts based on runtime conditions
- Modifying increment during loop execution (any oneshot could write to `field_test_increment`)
- Adjusting limit based on external factors

### Blocking Behavior

The `se_fork_join` composites ensure sequential execution. `se_fork_join` returns `SE_FUNCTION_HALT` while any MAIN child is active. Since `SE_FUNCTION_HALT` is a function-level code (range 6–11), `se_function_interface` propagates it immediately without invoking subsequent children:

1. First loop runs to completion (all 10 iterations)
2. `se_fork_join` returns `SE_PIPELINE_DISABLE` → `se_function_interface` terminates it
3. Second loop starts
4. After second loop completes, `se_return_terminate()` executes

### Tick Timing Within an Iteration

Each iteration shows consistent timing within `se_chain_flow`:

| Tick Offset | Event |
|-------------|-------|
| +0 | Iteration starts: oneshots fire (log, increment), inner chain_flow starts |
| +1 to +3 | Inner `se_tick_delay(3)` — `SE_FUNCTION_HALT` propagates up through chain_flow → fork_join → while → fork_join → function_interface |
| +4 | Inner delay completes (`SE_PIPELINE_DISABLE`), inner chain_flow returns `SE_PIPELINE_DISABLE` |
| +5 to +9 | Outer `se_tick_delay(5)` — same halt propagation |
| +10 | Outer delay completes, "loop_sequence_fn end" logs, `SE_RETURN_PIPELINE_DISABLE` fires, body complete |

The `+1` at the boundary accounts for the tick where `se_while` evaluates the predicate and resets the body for the next iteration.

## Predicate Comparison

### se_state_increment_and_test (`se_builtins_pred.lua`)

- **Storage:** `ns.user_data` on the predicate's node_state table (extensible Lua table field)
- **Parameters:** 2 `uint` params (increment=1, limit=10) — fixed at compile time
- **Auto-reset:** Resets counter to 0 when limit exceeded
- **Visibility:** Private to the predicate node
- **Iterations:** 10 (counter goes 1→10, returns false at 11)

### se_field_increment_and_test (`se_builtins_pred.lua`)

- **Storage:** Three blackboard fields (`inst.blackboard["field_test_counter"]`, etc.)
- **Parameters:** 3 `field_ref` params (counter, increment, limit) — runtime-configurable
- **Auto-reset:** Does not reset counter (caller manages via `se_set_field`)
- **Visibility:** All fields visible and modifiable by any function in the tree
- **Iterations:** 10 (counter goes 1→10, returns false at 11)

### Key Difference

| Aspect | State-Based | Field-Based |
|--------|-------------|-------------|
| Increment | Fixed `uint` param: `1` | Field reference: `"field_test_increment"` |
| Limit | Fixed `uint` param: `10` | Field reference: `"field_test_limit"` |
| Counter storage | `ns.user_data` (node-private) | `inst.blackboard["field_test_counter"]` |
| Runtime modifiable | No | Yes (any oneshot can write the fields) |
| Reset behavior | Auto-resets to 0 on limit exceeded | Caller must reset via `se_set_field` |
| Use case | Simple fixed loops | Dynamic/adaptive loops |

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_fork_join`, `se_while`, `se_chain_flow` | Control flow, blocking, looping |
| `se_builtins_pred.lua` | `se_state_increment_and_test`, `se_field_increment_and_test` | Loop predicates |
| `se_builtins_delays.lua` | `se_tick_delay` | Multi-tick delay (pointer slot u64 counter) |
| `se_builtins_oneshot.lua` | `se_log`, `se_log_int`, `se_set_field`, `se_inc_field` | Logging, field writes |
| `se_builtins_return_codes.lua` | `se_return_pipeline_disable`, `se_return_terminate` | Fixed return codes |
| `se_runtime.lua` | `tick_once`, `invoke_main`, `invoke_pred`, `child_invoke`, `child_invoke_pred`, `child_terminate`, `child_reset_recursive`, `get_ns`, `field_get`, `field_set` | Core dispatch, child lifecycle |

## Test Validation

1. ✅ **Nested loops** — inner `se_chain_flow` inside outer `se_chain_flow`, both inside `se_while`
2. ✅ **Blocking fork_join** — second loop waits for first to complete (`SE_FUNCTION_HALT` blocks siblings)
3. ✅ **State-based counter** — `se_state_increment_and_test` counts correctly via `ns.user_data`
4. ✅ **Field-based counter** — `se_field_increment_and_test` with 3 `field_ref` params reads/writes blackboard
5. ✅ **Runtime configuration** — increment and limit set via `se_set_field` before loop
6. ✅ **se_tick_delay** — proper `SE_FUNCTION_HALT` propagation and resumption
7. ✅ **Oneshot execution** — logs fire once per chain activation (reset by `child_reset_recursive` in `se_while`)
8. ✅ **Termination** — clean exit with `SE_TERMINATE` after both loops complete

## Test Harness

```lua
local se_runtime = require("se_runtime")
local module_data = require("loop_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_return_codes"),
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "loop_test")

local tick_count = 0
local max_ticks = 300

repeat
    local result = se_runtime.tick_once(inst)
    tick_count = tick_count + 1
until result == se_runtime.SE_TERMINATE
    or result == se_runtime.SE_FUNCTION_TERMINATE
    or tick_count >= max_ticks

-- Verify
assert(inst.blackboard["outer_sequence_counter"] == 20,
    "Expected outer=20, got " .. tostring(inst.blackboard["outer_sequence_counter"]))
assert(inst.blackboard["inner_sequence_counter"] == 20,
    "Expected inner=20, got " .. tostring(inst.blackboard["inner_sequence_counter"]))

print(string.format("Completed in %d ticks", tick_count))
print(tick_count < max_ticks and "✅ PASSED" or "❌ TIMEOUT")
```

## Files

| File | Description |
|------|-------------|
| `loop_test_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_loop.lua` | LuaJIT test harness |
| `se_builtins_flow_control.lua` | `se_while`, `se_fork_join`, `se_chain_flow` |
| `se_builtins_pred.lua` | `se_state_increment_and_test`, `se_field_increment_and_test` |
| `se_builtins_delays.lua` | `se_tick_delay` |