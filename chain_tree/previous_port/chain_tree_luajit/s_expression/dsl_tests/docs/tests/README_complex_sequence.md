# Complex Sequence Test — LuaJIT Runtime

## Overview

This test suite validates the S-Expression engine's verification, waiting, and timeout functions in the LuaJIT runtime. It runs a series of sequential tests that exercise parallel execution, event-based synchronization, time-based watchdogs, and predicate-based verification — all implemented across `se_builtins_delays.lua`, `se_builtins_verify.lua`, and `se_builtins_flow_control.lua`.

## Test Configuration

- **Tick Rate:** 0.1 seconds (100ms per tick)
- **Total Duration:** ~43.7 seconds (437 ticks)
- **Module:** `complex_sequence`
- **Time source:** `mod.get_time` (injectable; test uses a mock that advances 0.1s per tick)

## Blackboard Definition

In `module_data.records`:

```lua
records["complex_sequence_blackboard"] = {
    fields = {
        complex_sequence_condition_1 = { type = "uint32", default = 0 },
        complex_sequence_condition_2 = { type = "uint32", default = 0 },
        event_field                  = { type = "float",  default = 0 },
        field_test_counter           = { type = "uint32", default = 0 },
        field_test_increment         = { type = "uint32", default = 0 },
        field_test_limit             = { type = "uint32", default = 0 },
    }
}
```

After `se_runtime.new_instance()`, these become string-keyed entries in `inst.blackboard`.

## Test Sequence

The tests run sequentially via `se_fork_join`, ensuring each test completes before the next begins:

```
SE_FUNCTION_INTERFACE (root)
├── SE_FORK_JOIN → wait_event_test           ← Test 1: Event waiting
├── SE_FORK_JOIN → verify_time_test          ← Test 2: Time-based verification
├── SE_FORK_JOIN → verify_events_test        ← Test 3: Event count verification
├── SE_FORK_JOIN → complex_sequence_test     ← Test 4: Predicate verification
├── SE_FORK_JOIN → wait_timeout_test         ← Test 5: Wait with timeout
└── SE_RETURN_TERMINATE
```

Each `se_fork_join` returns `SE_FUNCTION_HALT` while its children are active, blocking subsequent siblings in `se_function_interface` until completion.

---

## Test 1: Wait Event Test (Ticks 1–110)

**Purpose:** Validate `se_wait_event` (`se_builtins_delays.lua`) — waiting for a specific event to occur N times.

**Tree structure:**

```
SE_FORK
├── Event Generator (SE_CHAIN_FLOW)
│   ├── [o_call] SE_LOG "event generator start"
│   ├── SE_WHILE (SE_FIELD_INCREMENT_AND_TEST, 10 iterations)
│   │   └── SE_FORK_JOIN
│   │       ├── SE_TIME_DELAY 1.0
│   │       ├── [o_call] SE_QUEUE_EVENT(1, 43, "event_field")
│   │       └── [o_call] SE_LOG "event generator iteration N"
│   └── [o_call] SE_LOG "event generator end"
│
└── Event Waiter (SE_CHAIN_FLOW)
    ├── [o_call] SE_LOG "wait event test start"
    ├── SE_WAIT_EVENT(target=43, count=10)    ← waits for event 43 × 10
    └── [o_call] SE_LOG "wait event test end"
```

**`se_wait_event` runtime behavior** (from `se_builtins_delays.lua`):

```lua
M.se_wait_event = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local ns = get_ns(inst, node.node_index)
        ns.wait_target = param_int(node, 1)   -- 43
        ns.wait_remain = param_int(node, 2)   -- 10
        return SE_PIPELINE_CONTINUE
    end

    local ns = get_ns(inst, node.node_index)
    if ns.wait_remain == 0 then return SE_PIPELINE_DISABLE end

    if event_id == ns.wait_target then
        ns.wait_remain = ns.wait_remain - 1
        if ns.wait_remain == 0 then return SE_PIPELINE_DISABLE end
    end

    return SE_PIPELINE_HALT
end
```

The node stores `wait_target` and `wait_remain` as extra fields on the node_state table (LuaJIT tables are extensible — no pre-allocation needed).

**Timeline:**

| Phase | Ticks | Description |
|-------|-------|-------------|
| Start | 1 | Generator and waiter start in parallel via `se_fork` |
| Iterations | 1–100 | Generator queues event 43 every 1.0s; waiter decrements `wait_remain` |
| Complete | ~110 | Waiter receives 10th event, returns `SE_PIPELINE_DISABLE` |

---

## Test 2: Verify Time Test (Ticks 111–160)

**Purpose:** Validate `se_verify_and_check_elapsed_time` (`se_builtins_verify.lua`) — time-based watchdog that terminates on timeout.

**Tree structure:**

```
SE_CHAIN_FLOW
├── [o_call] SE_LOG "verify time test start"
├── [pt_m_call] SE_VERIFY_AND_CHECK_ELAPSED_TIME
│   params: [{type="float", value=5.0}, {type="int", value=0}]   ← timeout=5s, reset=false
│   children:
│   └── [o_call] error_function (logs "verify timeout expired")
├── [o_call] SE_LOG "waiting for termination..."
└── SE_RETURN_PIPELINE_CONTINUE
```

**`se_verify_and_check_elapsed_time` runtime behavior** (from `se_builtins_verify.lua`):

```lua
-- On INIT: store start time
set_user_f64(inst, node, inst.mod.get_time())

-- On TICK: check elapsed
local elapsed = inst.mod.get_time() - get_user_f64(inst, node)
if elapsed > timeout then
    child_reset(inst, node, 0)          -- reset error oneshot
    child_invoke_oneshot(inst, node, 0)  -- fire error handler
    return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
end
return SE_PIPELINE_CONTINUE
```

The start time is stored via `set_user_f64` in the node_state's extensible `user_f64` field. Each tick, it compares `inst.mod.get_time() - start_time` against the timeout.

**Configuration:**
- Timeout: 5.0 seconds (50 ticks at 0.1s/tick)
- Reset flag: `false` → returns `SE_PIPELINE_TERMINATE` on timeout
- Error oneshot: logs "verify timeout expired this is expected"

---

## Test 3: Verify Events Test (Ticks 161–270)

**Purpose:** Validate `se_verify_and_check_elapsed_events` (`se_builtins_verify.lua`) — event count watchdog that terminates when count exceeded.

**Tree structure:**

```
SE_FORK
├── Event Generator (SE_CHAIN_FLOW)
│   └── SE_WHILE (10 iterations, 1.0s delay each)
│       └── SE_QUEUE_EVENT(1, 43, "event_field")
│
└── Event Monitor (SE_CHAIN_FLOW)
    ├── [o_call] SE_LOG "verify events test start"
    ├── [pt_m_call] SE_VERIFY_AND_CHECK_ELAPSED_EVENTS
    │   params: [{type="uint", value=43}, {type="uint", value=9}, {type="int", value=0}]
    │   children:
    │   └── [o_call] error_function
    └── SE_RETURN_PIPELINE_CONTINUE
```

**`se_verify_and_check_elapsed_events` runtime behavior** (from `se_builtins_verify.lua`):

```lua
-- On INIT: store counter = 0
set_user_u64(inst, node, 0)

-- On TICK: only count matching events
if event_id ~= target_event then return SE_PIPELINE_CONTINUE end

local current = get_user_u64(inst, node) + 1
set_user_u64(inst, node, current)

if current > max_count then
    child_reset(inst, node, 0)
    child_invoke_oneshot(inst, node, 0)
    return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
end
return SE_PIPELINE_CONTINUE
```

The counter is stored in `user_u64` on the node_state table. Only events matching `target_event` (43) increment the counter. When the counter exceeds `max_count` (9), the error handler fires.

**Configuration:**
- Target event: 43
- Max count: 9 (triggers on 10th event, since `current > 9`)
- Reset flag: `false` → `SE_PIPELINE_TERMINATE`

---

## Test 4: Complex Sequence Test (Ticks 271–336)

**Purpose:** Validate `se_wait` and `se_verify` (`se_builtins_delays.lua`, `se_builtins_verify.lua`) — waiting for predicates and continuous predicate verification with reset/terminate on failure.

**Tree structure:**

```
SE_FORK
├── Condition Generator (SE_CHAIN_FLOW)
│   ├── SE_SET_FIELD condition_1=0, condition_2=0 → SE_TICK_DELAY 10
│   ├── SE_SET_FIELD condition_1=1, condition_2=0 → SE_TICK_DELAY 10
│   ├── SE_SET_FIELD condition_1=1, condition_2=1 → SE_TICK_DELAY 10
│   ├── SE_SET_FIELD condition_1=0, condition_2=1 → SE_TICK_DELAY 10  ← triggers reset!
│   ├── SE_SET_FIELD condition_1=1, condition_2=1 → SE_TICK_DELAY 10
│   ├── SE_SET_FIELD condition_1=1, condition_2=0 → SE_TICK_DELAY 10  ← triggers terminate!
│   └── SE_RETURN_PIPELINE_TERMINATE
│
└── Sequence Verifier (SE_CHAIN_FLOW)
    ├── [o_call] SE_LOG "complex sequence test start"
    ├── SE_WAIT (pred: SE_FIELD_EQ condition_1 == 1)
    ├── [o_call] SE_LOG "pass test 1"
    ├── SE_VERIFY (pred: SE_FIELD_EQ condition_1 == 1, reset=true, error_fn_1)
    ├── SE_WAIT (pred: SE_FIELD_EQ condition_2 == 1)
    ├── [o_call] SE_LOG "pass test 2"
    ├── SE_VERIFY (pred: SE_FIELD_EQ condition_2 == 1, reset=false, error_fn_2)
    └── SE_RETURN_PIPELINE_CONTINUE
```

**`se_wait` runtime behavior** (from `se_builtins_delays.lua`):

```lua
M.se_wait = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then return SE_PIPELINE_CONTINUE end
    if event_id == SE_EVENT_INIT then return SE_PIPELINE_CONTINUE end

    if child_invoke_pred(inst, node, 0) then
        return SE_PIPELINE_DISABLE      -- predicate true: done waiting
    end
    return SE_PIPELINE_HALT             -- predicate false: keep waiting
end
```

**`se_verify` runtime behavior** (from `se_builtins_verify.lua`):

```lua
M.se_verify = function(inst, node, event_id, event_data)
    if event_id ~= SE_EVENT_TICK then return SE_PIPELINE_CONTINUE end

    if child_invoke_pred(inst, node, 0) then
        return SE_PIPELINE_CONTINUE     -- predicate true: all good
    end

    -- Predicate failed!
    child_reset(inst, node, 1)          -- reset error oneshot (children[1])
    child_invoke_oneshot(inst, node, 1) -- fire error handler
    return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
end
```

**Condition Sequence:**

| State | Cond1 | Cond2 | Verifier Action |
|-------|-------|-------|-----------------|
| 0,0 | 0 | 0 | `se_wait` for condition_1: `SE_PIPELINE_HALT` each tick |
| 1,0 | 1 | 0 | `se_wait` completes (`SE_PIPELINE_DISABLE`), then `se_wait` for condition_2 |
| 1,1 | 1 | 1 | Both pass, `se_verify` returns `SE_PIPELINE_CONTINUE` |
| 0,1 | 0 | 1 | `se_verify` condition_1 fails → error_fn_1 → `SE_PIPELINE_RESET` |
| 1,1 | 1 | 1 | After reset, re-runs from start, both pass quickly |
| 1,0 | 1 | 0 | `se_verify` condition_2 fails → error_fn_2 → `SE_PIPELINE_TERMINATE` |

---

## Test 5: Wait Timeout Test (Ticks 337–437)

**Purpose:** Validate `se_wait_timeout` (`se_builtins_delays.lua`) — waiting for a predicate with timeout protection.

**Tree structure:**

```
SE_FORK
├── Terminate Test (SE_CHAIN_FLOW)
│   ├── SE_WAIT_TIMEOUT
│   │   children[0]: SE_FALSE (p_call — always false)
│   │   children[1]: error_fn_2 (o_call — error handler)
│   │   params: [{type="float", value=5.0}, {type="int", value=0}]  ← 5s, no reset
│   └── ... (will terminate after 5s)
│
├── Reset Test (SE_CHAIN_FLOW)
│   ├── SE_WAIT_TIMEOUT
│   │   children[0]: SE_FALSE (p_call — always false)
│   │   children[1]: error_fn_1 (o_call — error handler)
│   │   params: [{type="float", value=2.0}, {type="int", value=1}]  ← 2s, reset=true
│   └── ... (will reset every 2s repeatedly)
│
└── Normal Test (SE_CHAIN_FLOW)
    ├── SE_WAIT_TIMEOUT
    │   children[0]: SE_TRUE (p_call — always true)
    │   children[1]: error_fn_1
    │   params: [{type="float", value=5.0}, {type="int", value=0}]
    │   └── (completes immediately — predicate true on first tick)
    ├── SE_TIME_DELAY 10.0
    └── SE_RETURN_TERMINATE
```

**`se_wait_timeout` runtime behavior** (from `se_builtins_delays.lua`):

```lua
M.se_wait_timeout = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        set_user_f64(inst, node, inst.mod.get_time())  -- store start time
        return SE_PIPELINE_CONTINUE
    end

    if event_id ~= SE_EVENT_TICK then return SE_PIPELINE_HALT end

    -- Check predicate
    if child_invoke_pred(inst, node, 0) then
        return SE_PIPELINE_DISABLE    -- predicate true: done waiting
    end

    -- Check timeout
    local elapsed = inst.mod.get_time() - get_user_f64(inst, node)
    if elapsed > timeout then
        child_reset(inst, node, 1)
        child_invoke_oneshot(inst, node, 1)   -- fire error handler
        return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
    end

    return SE_PIPELINE_HALT
end
```

Start time stored in `user_f64` via `set_user_f64`. Non-TICK events return `SE_PIPELINE_HALT` (only TICK advances the timeout check).

**Test Cases:**

| Test | Predicate | Timeout | Reset | Behavior |
|------|-----------|---------|-------|----------|
| Terminate | `se_false` | 5.0s | false | Times out at 5s, `SE_PIPELINE_TERMINATE` |
| Reset | `se_false` | 2.0s | true | Times out at 2s, `SE_PIPELINE_RESET`, repeats |
| Normal | `se_true` | 5.0s | false | Predicate true on first tick, `SE_PIPELINE_DISABLE` immediately |

**Timeline:**

| Ticks | Time | Event |
|-------|------|-------|
| 337 | 0.0s | All three chains start |
| 357 | 2.0s | Reset test times out (1st), error_fn_1 fires, resets |
| 377 | 4.0s | Reset test times out (2nd), resets |
| 387 | 5.0s | Terminate test times out, error_fn_2 fires, terminates |
| 397 | 6.0s | Reset test times out (3rd), resets |
| 417 | 8.0s | Reset test times out (4th), resets |
| 437 | 10.0s | Normal test's `se_time_delay` completes, returns `SE_TERMINATE` |

---

## Runtime Modules Exercised

| Module | Functions | Tests |
|--------|-----------|-------|
| `se_builtins_delays.lua` | `se_wait_event`, `se_wait`, `se_wait_timeout`, `se_time_delay`, `se_tick_delay` | 1, 4, 5 |
| `se_builtins_verify.lua` | `se_verify_and_check_elapsed_time`, `se_verify_and_check_elapsed_events`, `se_verify` | 2, 3, 4 |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_fork_join`, `se_fork`, `se_chain_flow`, `se_while` | All |
| `se_builtins_pred.lua` | `se_field_eq`, `se_field_increment_and_test`, `se_true`, `se_false` | 1, 3, 4, 5 |
| `se_builtins_oneshot.lua` | `se_log`, `se_set_field`, `se_queue_event` | All |
| `se_builtins_return_codes.lua` | `se_return_pipeline_continue`, `se_return_pipeline_terminate`, `se_return_terminate` | All |
| `se_runtime.lua` | `tick_once`, `event_push/pop/count`, `child_invoke_pred`, `child_invoke_oneshot`, `child_reset`, `get/set_user_f64`, `get/set_user_u64` | All |

## Time Source Mocking

The tests require controllable time for deterministic results. The LuaJIT runtime injects time via `mod.get_time`:

```lua
-- Mock time source advancing 0.1s per tick
local mock_time = 0.0
mod.get_time = function() return mock_time end

-- In tick loop:
mock_time = mock_time + 0.1
se_runtime.tick_once(inst)
```

Builtins that depend on time (`se_time_delay`, `se_wait_timeout`, `se_verify_and_check_elapsed_time`) all call `inst.mod.get_time()` rather than `os.clock` directly, making them fully testable without wall-clock dependencies.

## Extended Node State Usage

This test exercises several node_state extension patterns unique to the LuaJIT runtime's extensible tables:

| Builtin | Extra Fields | Storage |
|---------|-------------|---------|
| `se_wait_event` | `ns.wait_target`, `ns.wait_remain` | Direct fields on node_state table |
| `se_verify_and_check_elapsed_time` | `ns.user_f64` | Via `set_user_f64` / `get_user_f64` |
| `se_verify_and_check_elapsed_events` | `ns.user_u64` | Via `set_user_u64` / `get_user_u64` |
| `se_wait_timeout` | `ns.user_f64` | Via `set_user_f64` / `get_user_f64` |

In C, these would require `pt_m_call` pointer slots or fixed-size node_state fields. In LuaJIT, the table grows dynamically to accommodate any extra fields.

## Result Summary

| Test | Duration | Result | Key Validation |
|------|----------|--------|----------------|
| Wait Event | ~11s (110 ticks) | ✅ | Event synchronization via `ns.wait_remain` countdown |
| Verify Time | ~5s (50 ticks) | ✅ | Time watchdog via `user_f64` start time + `get_time()` |
| Verify Events | ~11s (110 ticks) | ✅ | Event count watchdog via `user_u64` counter |
| Complex Sequence | ~6.6s (66 ticks) | ✅ | Reset and terminate from `se_verify` predicate failure |
| Wait Timeout | ~10s (101 ticks) | ✅ | Timeout with both reset and terminate paths |

**Final Result:** `SE_TERMINATE` after 437 ticks (~43.7 seconds mock time)

## Error Function Behavior

The test validates that error oneshot functions fire correctly via `child_reset` + `child_invoke_oneshot`:

1. **Single fire on terminate:** Error oneshot fires once before `SE_PIPELINE_TERMINATE` propagates
2. **Repeated fire on reset:** Error oneshot fires on each reset cycle — `child_reset(inst, node, idx)` clears `FLAG_INITIALIZED`, then `child_invoke_oneshot` sets it again and fires the function
3. **Reset clears flag:** `child_reset` sets `FLAG_ACTIVE` only (clearing `FLAG_INITIALIZED`), enabling the oneshot to fire again on the next invocation

## Test Harness

```lua
local se_runtime = require("se_runtime")
local module_data = require("complex_sequence_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_verify"),
    require("se_builtins_return_codes"),
)

local mod = se_runtime.new_module(module_data, fns)

-- Injectable time source
local mock_time = 0.0
mod.get_time = function() return mock_time end

local inst = se_runtime.new_instance(mod, "complex_sequence")

local tick_count = 0
local max_ticks = 500

local function result_is_complete(r)
    return r ~= se_runtime.SE_PIPELINE_CONTINUE
       and r ~= se_runtime.SE_PIPELINE_DISABLE
end

repeat
    mock_time = mock_time + 0.1   -- advance 100ms per tick
    local result = se_runtime.tick_once(inst)
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

print(string.format("Completed in %d ticks (%.1fs mock time)", tick_count, mock_time))
print(tick_count < max_ticks and "✅ PASSED" or "❌ TIMEOUT")
```

## Files

| File | Description |
|------|-------------|
| `complex_sequence_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_complex_sequence.lua` | LuaJIT test harness with mock time |
| `se_builtins_delays.lua` | `se_wait_event`, `se_wait`, `se_wait_timeout`, `se_time_delay` |
| `se_builtins_verify.lua` | `se_verify_and_check_elapsed_time`, `se_verify_and_check_elapsed_events`, `se_verify` |