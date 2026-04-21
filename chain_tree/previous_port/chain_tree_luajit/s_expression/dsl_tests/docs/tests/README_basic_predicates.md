# Basic Primitive Test — Trigger On Change & Predicates (LuaJIT Runtime)

## Overview

This test validates the S-Engine's edge detection system (`se_trigger_on_change` in `se_builtins_flow_control.lua`) combined with composable predicates (`se_pred_and`, `se_pred_or`, `se_pred_not` in `se_builtins_pred.lua`). It demonstrates how to build reactive systems that respond to boolean state transitions.

## Test Objectives

1. **User-Defined Predicates** — test custom predicates that read external state via `inst.user_ctx`
2. **Composable Predicates** — test AND, OR, NOT predicate combinators from `se_builtins_pred.lua`
3. **Edge Detection** — test `se_trigger_on_change` for rising and falling edge detection
4. **Action Invocation** — verify actions fire correctly on state transitions
5. **Repeated Triggers** — verify actions reset and can fire again on subsequent edges

## Architecture

### Two-Variable Event System

The test uses **two separate tables** to avoid conflicts:

```lua
local bitmap = { value = 0 }           -- Input: test_bit predicate reads this
local trigger_events = { value = 0 }   -- Output: oneshot functions write this
```

| Variable | Purpose | Who Writes | Who Reads |
|----------|---------|------------|-----------|
| `bitmap.value` | Simulated hardware/sensor state | Test harness | `test_bit` predicate |
| `trigger_events.value` | Event tracking for verification | Oneshot functions | Test harness |

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TEST HARNESS                                │
│                                                                     │
│   bitmap.value = 0x01       ──────────────────────┐                │
│   trigger_events.value = 0                         │                │
│   se_runtime.tick_once(inst)                       │                │
│   check: trigger_events.value                      │                │
│                                                    ▼                │
│                        ┌──────────────────────────────────────┐    │
│                        │           BEHAVIOR TREE              │    │
│                        │                                      │    │
│                        │  se_trigger_on_change                │    │
│                        │      │                               │    │
│                        │      ├─► predicate: test_bit(0)      │    │
│                        │      │       │                       │    │
│                        │      │       └─► reads bitmap ◄──────┼────┘
│                        │      │           via inst.user_ctx   │
│                        │      │                               │    │
│                        │      ├─► rising action:              │    │
│                        │      │       on_bit0_rise()          │    │
│                        │      │           │                   │    │
│                        │      │           └─► writes ─────────┼────┐
│                        │      │           trigger_events      │    │
│                        │      │                               │    │
│                        │      └─► falling action:             │    │
│                        │              on_bit0_fall()          │    │
│                        │                  │                   │    │
│                        │                  └─► writes ─────────┼────┤
│                        │                  trigger_events      │    │
│                        └──────────────────────────────────────┘    │
│                                                                     │
│   verify: bit.band(trigger_events.value, EVENT_BIT0_RISE) ◄───────┘
└─────────────────────────────────────────────────────────────────────┘
```

### Connection via user_ctx

The `test_bit` predicate accesses the bitmap through the tree instance's `user_ctx`:

```lua
-- Test setup
inst.user_ctx = bitmap

-- In test_bit predicate
local bm = inst.user_ctx
local bit_index = node.params[1].value
local result = bit.band(bm.value, bit.lshift(1, bit_index)) ~= 0
return result
```

## Tree Structure

```
SE_FUNCTION_INTERFACE (root)
│
├── SE_TRIGGER_ON_CHANGE (initial_state=0)        ← Trigger 1: single bit
│   ├── children[0]: TEST_BIT(0)                   (p_call — predicate)
│   ├── children[1]: SE_CHAIN_FLOW                 (m_call — rising action)
│   │   ├── [o_call] ON_BIT0_RISE
│   │   ├── [o_call] SE_LOG "ON_BIT0_RISE"
│   │   └── SE_RETURN_CONTINUE
│   └── children[2]: SE_CHAIN_FLOW                 (m_call — falling action)
│       ├── [o_call] ON_BIT0_FALL
│       ├── [o_call] SE_LOG "ON_BIT0_FALL"
│       └── SE_RETURN_CONTINUE
│
├── SE_TRIGGER_ON_CHANGE (initial_state=0)        ← Trigger 2: AND
│   ├── children[0]: SE_PRED_AND (p_call_composite)
│   │   ├── TEST_BIT(1) (p_call)
│   │   └── TEST_BIT(2) (p_call)
│   ├── children[1]: SE_CHAIN_FLOW (rising)
│   │   └── [o_call] ON_BITS_12_RISE
│   └── children[2]: SE_CHAIN_FLOW (falling)
│       └── [o_call] ON_BITS_12_FALL
│
├── SE_TRIGGER_ON_CHANGE (initial_state=0)        ← Trigger 3: OR
│   ├── children[0]: SE_PRED_OR (p_call_composite)
│   │   ├── TEST_BIT(3) (p_call)
│   │   └── TEST_BIT(4) (p_call)
│   ├── children[1]: rising action
│   └── children[2]: falling action
│
├── SE_TRIGGER_ON_CHANGE (initial_state=1)        ← Trigger 4: NOT (inverted)
│   ├── children[0]: SE_PRED_NOT (p_call_composite)
│   │   └── TEST_BIT(5) (p_call)
│   ├── children[1]: rising action (bit5 cleared)
│   └── children[2]: falling action (bit5 set)
│
└── SE_RETURN_CONTINUE
```

### Trigger Configuration

| Trigger | Predicate | `call_type` | Initial State | Rising Action | Falling Action |
|---------|-----------|-------------|---------------|---------------|----------------|
| 1 | `TEST_BIT(0)` | `p_call` | 0 | ON_BIT0_RISE | ON_BIT0_FALL |
| 2 | `SE_PRED_AND(TEST_BIT(1), TEST_BIT(2))` | `p_call_composite` | 0 | ON_BITS_12_RISE | ON_BITS_12_FALL |
| 3 | `SE_PRED_OR(TEST_BIT(3), TEST_BIT(4))` | `p_call_composite` | 0 | ON_BITS_34_RISE | ON_BITS_34_FALL |
| 4 | `SE_PRED_NOT(TEST_BIT(5))` | `p_call_composite` | 1 | ON_BIT5_CLEAR | ON_BIT5_SET |

## se_trigger_on_change Runtime Behavior

From `se_builtins_flow_control.lua`:

```lua
M.se_trigger_on_change = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)

    -- INIT: read initial state from params[1]
    if event_id == SE_EVENT_INIT then
        local initial = param_int(node, 1)
        ns.state = (initial ~= 0) and 1 or 0
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: evaluate predicate, detect edges
    local current = child_invoke_pred(inst, node, 0)   -- children[0] = predicate
    local prev = ns.state
    local current_val = current and 1 or 0

    local rising  = (prev == 0 and current_val == 1)
    local falling = (prev ~= 0 and current_val == 0)
    ns.state = current_val

    if rising then
        -- Terminate + reset falling action, restart rising action
        child_terminate(inst, node, 2)
        child_reset(inst, node, 2)
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        return trigger_invoke_and_handle(inst, node, 1, event_id, event_data)

    elseif falling and #(node.children or {}) >= 3 then
        -- Terminate + reset rising action, restart falling action
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        child_terminate(inst, node, 2)
        child_reset(inst, node, 2)
        return trigger_invoke_and_handle(inst, node, 2, event_id, event_data)
    end

    return SE_PIPELINE_CONTINUE
end
```

Key mechanics:
- `ns.state` tracks previous predicate value (0 or 1)
- Edge detection: `rising = (prev == 0 and current == 1)`, `falling = (prev ~= 0 and current == 0)`
- On edge: terminate+reset both actions, then invoke the appropriate one
- The terminate+reset ensures actions can fire again on subsequent edges

## User Functions

### Predicate: test_bit

Reads a specific bit from the bitmap via `inst.user_ctx`:

```lua
local bit = require("bit")

local function test_bit(inst, node)
    local bm = inst.user_ctx
    assert(bm, "test_bit: no user_ctx (bitmap)")
    local bit_index = node.params[1].value
    return bit.band(bm.value, bit.lshift(1, bit_index)) ~= 0
end
```

In the `module_data`, this appears as:

```lua
{ func_name = "TEST_BIT", call_type = "p_call",
  params = { {type="int", value=0} },   -- bit index
  children = {} }
```

### Oneshot: Event Tracking

Each oneshot sets its corresponding bit in `trigger_events`:

```lua
local EVENT_BIT0_RISE   = bit.lshift(1, 0)
local EVENT_BIT0_FALL   = bit.lshift(1, 1)
local EVENT_BITS12_RISE = bit.lshift(1, 2)
local EVENT_BITS12_FALL = bit.lshift(1, 3)
local EVENT_BITS34_RISE = bit.lshift(1, 4)
local EVENT_BITS34_FALL = bit.lshift(1, 5)
local EVENT_BIT5_CLEAR  = bit.lshift(1, 6)
local EVENT_BIT5_SET    = bit.lshift(1, 7)

local function on_bit0_rise(inst, node)
    print("  >> ON_BIT0_RISE")
    trigger_events.value = bit.bor(trigger_events.value, EVENT_BIT0_RISE)
end

local function on_bit0_fall(inst, node)
    print("  >> ON_BIT0_FALL")
    trigger_events.value = bit.bor(trigger_events.value, EVENT_BIT0_FALL)
end
-- ... etc for all 8 event oneshots
```

These are registered via `merge_fns`:

```lua
local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_return_codes"),
    {
        test_bit        = test_bit,
        on_bit0_rise    = on_bit0_rise,
        on_bit0_fall    = on_bit0_fall,
        on_bits_12_rise = on_bits_12_rise,
        on_bits_12_fall = on_bits_12_fall,
        on_bits_34_rise = on_bits_34_rise,
        on_bits_34_fall = on_bits_34_fall,
        on_bit5_clear   = on_bit5_clear,
        on_bit5_set     = on_bit5_set,
    }
)
```

## Test Cases

### Test 1–2: Simple Bit Rising/Falling

```lua
-- Set bit 0 → should trigger ON_BIT0_RISE
bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 0))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BIT0_RISE) ~= 0)

-- Clear bit 0 → should trigger ON_BIT0_FALL
bitmap.value = bit.band(bitmap.value, bit.bnot(bit.lshift(1, 0)))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BIT0_FALL) ~= 0)
```

### Test 3–5: AND Predicate

```lua
-- Set bit 1 only → AND should NOT trigger
bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 1))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS12_RISE) == 0)  -- no event

-- Set bit 2 → now AND is true, should trigger
bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 2))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS12_RISE) ~= 0)  -- rising!

-- Clear bit 1 → AND becomes false
bitmap.value = bit.band(bitmap.value, bit.bnot(bit.lshift(1, 1)))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS12_FALL) ~= 0)  -- falling!
```

The AND predicate (`se_pred_and` in `se_builtins_pred.lua`) short-circuits: it iterates `node.children` and returns `false` on the first child that returns `false`:

```lua
M.se_pred_and = function(inst, node)
    for _, child in ipairs(node.children or {}) do
        if not invoke_pred(inst, child) then return false end
    end
    return true
end
```

### Test 6–9: OR Predicate

```lua
-- Set bit 3 → OR becomes true
bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 3))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS34_RISE) ~= 0)  -- rising!

-- Set bit 4 also → OR still true, no new trigger (no edge)
bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 4))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS34_RISE) == 0)   -- no event

-- Clear bit 3 → OR still true via bit 4 (no edge)
bitmap.value = bit.band(bitmap.value, bit.bnot(bit.lshift(1, 3)))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS34_FALL) == 0)   -- no event

-- Clear bit 4 → OR now false
bitmap.value = bit.band(bitmap.value, bit.bnot(bit.lshift(1, 4)))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BITS34_FALL) ~= 0)   -- falling!
```

The OR predicate (`se_pred_or`) short-circuits in the opposite direction: returns `true` on the first child that returns `true`.

### Test 10–11: NOT Predicate (Inverted Logic)

The NOT trigger starts with `initial_state=1` because `NOT bit5` is true when bit5=0. The `params[1]` in the node carries this initial state:

```lua
-- params[1] = {type="uint", value=1}  ← initial_state = 1
-- On INIT: ns.state = 1
```

```lua
-- Set bit 5 → NOT bit5 becomes false (falling edge)
bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 5))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BIT5_SET) ~= 0)    -- falling action

-- Clear bit 5 → NOT bit5 becomes true (rising edge)
bitmap.value = bit.band(bitmap.value, bit.bnot(bit.lshift(1, 5)))
trigger_events.value = 0
se_runtime.tick_once(inst)
assert(bit.band(trigger_events.value, EVENT_BIT5_CLEAR) ~= 0)  -- rising action
```

The NOT predicate (`se_pred_not`) inverts its single child:

```lua
M.se_pred_not = function(inst, node)
    local child = (node.children or {})[1]
    assert(child, "se_pred_not: no child")
    return not invoke_pred(inst, child)
end
```

### Test 12–14: Repeated Triggers

Verifies that actions reset properly and can fire again. The `se_trigger_on_change` implementation calls `child_terminate` + `child_reset` on both action branches before invoking the triggered one, ensuring oneshot children (`o_call`) have their `FLAG_INITIALIZED` cleared and can fire again:

```lua
-- Toggle bit 0 multiple times
for cycle = 1, 3 do
    bitmap.value = bit.bor(bitmap.value, bit.lshift(1, 0))
    trigger_events.value = 0
    se_runtime.tick_once(inst)
    assert(bit.band(trigger_events.value, EVENT_BIT0_RISE) ~= 0,
        "cycle " .. cycle .. ": expected rise")

    bitmap.value = bit.band(bitmap.value, bit.bnot(bit.lshift(1, 0)))
    trigger_events.value = 0
    se_runtime.tick_once(inst)
    assert(bit.band(trigger_events.value, EVENT_BIT0_FALL) ~= 0,
        "cycle " .. cycle .. ": expected fall")
end
```

## Expected Output

```
=== Test Trigger On Change ===
--- Initial tick (bitmap=0x00000000) ---
  events fired: 0x00
--- Set bit 0 (bitmap=0x00000000 -> 0x00000001) ---
  >> ON_BIT0_RISE
  events fired: 0x01
--- Clear bit 0 (bitmap=0x00000001 -> 0x00000000) ---
  >> ON_BIT0_FALL
  events fired: 0x02
--- Set bit 1 only (bitmap=0x00000000 -> 0x00000002) ---
  events fired: 0x00
--- Set bit 2 (bitmap=0x00000002 -> 0x00000006) ---
  >> ON_BITS_12_RISE (bit1 AND bit2)
  events fired: 0x04
...
  ✅ PASSED: All edge triggers working correctly
```

## Complete Test Harness

```lua
local se_runtime = require("se_runtime")
local bit = require("bit")
local module_data = require("basic_primitive_test_module")

-- External state
local bitmap = { value = 0 }
local trigger_events = { value = 0 }

local EVENT_BIT0_RISE   = bit.lshift(1, 0)
local EVENT_BIT0_FALL   = bit.lshift(1, 1)
local EVENT_BITS12_RISE = bit.lshift(1, 2)
local EVENT_BITS12_FALL = bit.lshift(1, 3)
local EVENT_BITS34_RISE = bit.lshift(1, 4)
local EVENT_BITS34_FALL = bit.lshift(1, 5)
local EVENT_BIT5_CLEAR  = bit.lshift(1, 6)
local EVENT_BIT5_SET    = bit.lshift(1, 7)

-- User-defined functions
local function test_bit(inst, node)
    local bm = inst.user_ctx
    local bit_index = node.params[1].value
    return bit.band(bm.value, bit.lshift(1, bit_index)) ~= 0
end

local function make_event_oneshot(name, flag)
    return function(inst, node)
        print("  >> " .. name)
        trigger_events.value = bit.bor(trigger_events.value, flag)
    end
end

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_return_codes"),
    {
        test_bit        = test_bit,
        on_bit0_rise    = make_event_oneshot("ON_BIT0_RISE", EVENT_BIT0_RISE),
        on_bit0_fall    = make_event_oneshot("ON_BIT0_FALL", EVENT_BIT0_FALL),
        on_bits_12_rise = make_event_oneshot("ON_BITS_12_RISE", EVENT_BITS12_RISE),
        on_bits_12_fall = make_event_oneshot("ON_BITS_12_FALL", EVENT_BITS12_FALL),
        on_bits_34_rise = make_event_oneshot("ON_BITS_34_RISE", EVENT_BITS34_RISE),
        on_bits_34_fall = make_event_oneshot("ON_BITS_34_FALL", EVENT_BITS34_FALL),
        on_bit5_clear   = make_event_oneshot("ON_BIT5_CLEAR", EVENT_BIT5_CLEAR),
        on_bit5_set     = make_event_oneshot("ON_BIT5_SET", EVENT_BIT5_SET),
    }
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "basic_primitive_test")
inst.user_ctx = bitmap

-- Helper
local function tick_and_check(expected, msg)
    trigger_events.value = 0
    se_runtime.tick_once(inst)
    if expected == 0 then
        assert(trigger_events.value == 0,
            msg .. ": expected no events, got " ..
            string.format("0x%02x", trigger_events.value))
    else
        assert(bit.band(trigger_events.value, expected) ~= 0,
            msg .. ": expected " .. string.format("0x%02x", expected) ..
            ", got " .. string.format("0x%02x", trigger_events.value))
    end
end

print("=== Test Trigger On Change ===")

-- Initial tick
se_runtime.tick_once(inst)

-- Test 1: rising edge on bit 0
bitmap.value = bit.bor(bitmap.value, 0x01)
tick_and_check(EVENT_BIT0_RISE, "bit0 rise")

-- Test 2: falling edge on bit 0
bitmap.value = bit.band(bitmap.value, bit.bnot(0x01))
tick_and_check(EVENT_BIT0_FALL, "bit0 fall")

-- Test 3: AND partial (bit 1 only)
bitmap.value = bit.bor(bitmap.value, 0x02)
tick_and_check(0, "bit1 only, AND should not trigger")

-- Test 4: AND complete (bit 1 + bit 2)
bitmap.value = bit.bor(bitmap.value, 0x04)
tick_and_check(EVENT_BITS12_RISE, "bits 1+2 AND rise")

-- Test 5: AND broken (clear bit 1)
bitmap.value = bit.band(bitmap.value, bit.bnot(0x02))
tick_and_check(EVENT_BITS12_FALL, "bits 1+2 AND fall")

-- ... more tests for OR, NOT, repeated triggers ...

print("✅ PASSED: All edge triggers working correctly")
```

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_trigger_on_change`, `se_chain_flow` | Control flow and edge detection |
| `se_builtins_pred.lua` | `se_pred_and`, `se_pred_or`, `se_pred_not` | Composable boolean combinators |
| `se_builtins_oneshot.lua` | `se_log` | Logging |
| `se_builtins_return_codes.lua` | `se_return_continue` | Fixed return code |
| `se_runtime.lua` | `tick_once`, `invoke_pred`, `child_invoke_pred`, `child_terminate`, `child_reset` | Core dispatch and child lifecycle |

## Key Concepts Demonstrated

1. **User-defined predicates** — `test_bit` reads external state via `inst.user_ctx`, matching the `fn(inst, node) → bool` signature
2. **Composable predicates** — `se_pred_and`, `se_pred_or`, `se_pred_not` iterate `node.children` with short-circuit evaluation
3. **Edge detection** — `se_trigger_on_change` tracks `ns.state` (0 or 1) and compares against predicate result each tick
4. **Initial state** — `params[1]` configures starting state, preventing spurious triggers (e.g., NOT trigger starts at 1)
5. **Action reset** — `child_terminate` + `child_reset` on edge clears `FLAG_INITIALIZED` on oneshot children, enabling repeated triggers
6. **Two-variable pattern** — separate input (`bitmap` via `user_ctx`) and output (`trigger_events` via closure capture) for clean testing
7. **Closure-based oneshot factory** — `make_event_oneshot` generates oneshot functions sharing the same `trigger_events` table via closure capture

## Files

| File | Description |
|------|-------------|
| `basic_primitive_test_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_basic_primitive.lua` | LuaJIT test harness |
| `se_builtins_flow_control.lua` | `se_trigger_on_change` implementation |
| `se_builtins_pred.lua` | `se_pred_and`, `se_pred_or`, `se_pred_not` |

## Usage Pattern

This test demonstrates a common embedded systems pattern adapted for LuaJIT:

1. **Hardware State** → stored in `inst.user_ctx` table (or read from actual hardware via FFI)
2. **Predicates** → `p_call` children evaluate hardware conditions via `invoke_pred`
3. **Triggers** → `se_trigger_on_change` detects rising/falling edges in `ns.state`
4. **Actions** → `m_call` children respond to transitions (set flags, log, update state)

This is useful for:
- Button debouncing and edge detection
- Sensor threshold monitoring
- Multi-condition alarm systems (AND/OR combinators)
- State machine input processing