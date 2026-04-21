# S-Engine Predicate System — LuaJIT Runtime

## Overview

The S-Engine predicate system provides composable boolean logic for behavior trees. Predicates are Lua functions that return `true` or `false` and can be combined using logical operators (AND, OR, NOT, etc.) to build complex conditions. In the LuaJIT runtime, predicates operate on pre-separated `node.children` arrays rather than scanning flat binary parameter streams, eliminating the need for `s_expr_skip_param` and `s_expr_param_is_predicate` machinery.

## Architecture

### Two-Layer Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PIPELINE / DSL LAYER                            │
│                                                                     │
│   YAML/JSON → LuaJIT pipeline produces tree nodes with:            │
│   - call_type = "p_call" (simple) or "p_call_composite" (nested)   │
│   - node.children[] contains child predicates (pre-separated)       │
│   - node.params[] contains non-callable parameters                  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LUAJIT RUNTIME LAYER                              │
│                                                                     │
│   se_builtins_pred.lua — Predicate implementations                  │
│     se_pred_and(), se_pred_or(), se_pred_not(), etc.               │
│     All: fn(inst, node) → bool                                      │
│                                                                     │
│   se_runtime.lua — Dispatch infrastructure                          │
│     invoke_pred(inst, node) — call pred function, return bool       │
│     child_invoke_pred(inst, node, idx) — invoke child as pred       │
└─────────────────────────────────────────────────────────────────────┘
```

Unlike the C version which has a three-layer design (DSL → binary parameter stream → C runtime), the LuaJIT version eliminates the binary parameter stream entirely. The pipeline pre-separates child predicates into `node.children[]`, so composite predicates simply iterate their children array.

## Predicate Function Signature

All predicates share the same signature:

```lua
-- fn(inst, node) → bool
-- No event_id parameter. No state mutation. Pure boolean evaluation.
```

This is simpler than the C signature which passes `event_type`, `event_id`, and `event_data` (all unused by predicates). The LuaJIT runtime strips these away at the dispatch layer — `invoke_pred` calls `fn(inst, node)` directly.

## Node Structure

### Simple Predicate (`p_call`)

```lua
{
    func_name  = "se_field_gt",
    call_type  = "p_call",
    func_index = 4,          -- index into mod.pred_fns
    node_index = 7,          -- index into inst.node_states
    params     = {
        { type = "field_ref", value = "sensor_value" },
        { type = "int", value = 42 },
    },
    children   = {},          -- no children for simple predicates
}
```

### Composite Predicate (`p_call_composite`)

```lua
{
    func_name  = "se_pred_and",
    call_type  = "p_call_composite",
    func_index = 0,
    node_index = 5,
    params     = {},          -- composites typically have no params
    children   = {
        -- Child predicates (pre-separated by pipeline)
        { func_name = "se_field_gt", call_type = "p_call",
          params = {{type="field_ref", value="temp"}, {type="int", value=100}},
          children = {} },
        { func_name = "se_field_lt", call_type = "p_call",
          params = {{type="field_ref", value="pressure"}, {type="int", value=500}},
          children = {} },
    },
}
```

### `p_call` vs `p_call_composite`

| Call Type | Usage | Children |
|-----------|-------|----------|
| `p_call` | Simple predicate — no nested predicates | `node.children` is empty; `node.params` has value parameters |
| `p_call_composite` | Composite predicate with child predicates | `node.children` contains nested predicate nodes |

Both are dispatched identically by `invoke_pred` — the distinction exists for pipeline validation and DSL tooling, not runtime behavior.

## Builtin Predicate Implementations

All implementations live in `se_builtins_pred.lua`. Each is a Lua function registered in the module's `M` table.

### SE_PRED_AND — Short-Circuit Conjunction

Returns `true` only if ALL child predicates return `true`. Short-circuits on first `false`.

```lua
M.se_pred_and = function(inst, node)
    for _, child in ipairs(node.children or {}) do
        if not invoke_pred(inst, child) then return false end
    end
    return true   -- all children true (or no children)
end
```

**Truth Table:**

| A | B | A AND B |
|---|---|---------|
| F | F | F |
| F | T | F |
| T | F | F |
| T | T | T |

### SE_PRED_OR — Short-Circuit Disjunction

Returns `true` if ANY child predicate returns `true`. Short-circuits on first `true`.

```lua
M.se_pred_or = function(inst, node)
    for _, child in ipairs(node.children or {}) do
        if invoke_pred(inst, child) then return true end
    end
    return false   -- no children true (or no children)
end
```

**Truth Table:**

| A | B | A OR B |
|---|---|--------|
| F | F | F |
| F | T | T |
| T | F | T |
| T | T | T |

### SE_PRED_NOT — Logical Negation

Inverts the result of its single child predicate.

```lua
M.se_pred_not = function(inst, node)
    local child = (node.children or {})[1]
    assert(child, "se_pred_not: no child")
    return not invoke_pred(inst, child)
end
```

**Truth Table:**

| A | NOT A |
|---|-------|
| F | T |
| T | F |

### SE_PRED_NOR — Negated OR

Returns `true` only if ALL children are `false`. Equivalent to `NOT(OR(...))`.

```lua
M.se_pred_nor = function(inst, node)
    return not M.se_pred_or(inst, node)
end
```

**Truth Table:**

| A | B | A NOR B |
|---|---|---------|
| F | F | T |
| F | T | F |
| T | F | F |
| T | T | F |

### SE_PRED_NAND — Negated AND

Returns `true` if ANY child is `false`. Equivalent to `NOT(AND(...))`.

```lua
M.se_pred_nand = function(inst, node)
    return not M.se_pred_and(inst, node)
end
```

**Truth Table:**

| A | B | A NAND B |
|---|---|----------|
| F | F | T |
| F | T | T |
| T | F | T |
| T | T | F |

### SE_PRED_XOR — Exclusive OR

Returns `true` if an odd number of children are `true`. This matches standard multi-input XOR behavior (parity check).

```lua
M.se_pred_xor = function(inst, node)
    local count = 0
    for _, child in ipairs(node.children or {}) do
        if invoke_pred(inst, child) then count = count + 1 end
    end
    return (count % 2) == 1
end
```

**Truth Table (2 inputs):**

| A | B | A XOR B |
|---|---|---------|
| F | F | F |
| F | T | T |
| T | F | T |
| T | T | F |

**Multi-input behavior:** Returns `true` when the count of `true` children is odd. Note this differs from the C implementation which returns `true` only when exactly one child is `true` — the LuaJIT version uses standard parity-based XOR semantics.

### SE_TRUE / SE_FALSE — Constants

```lua
M.se_true  = function() return true  end
M.se_false = function() return false end
```

## Field Comparison Predicates

These simple predicates (`p_call`) compare a blackboard field against a constant parameter. They use `field_get` for type-coercing blackboard access and `param_int` / `param_float` for parameter reading.

### Integer Comparisons

```lua
-- params[1] = field_ref,  params[2] = int (comparison value)

M.se_field_eq = function(inst, node)
    return field_get(inst, node, 1) == param_int(node, 2)
end

M.se_field_ne = function(inst, node)
    return field_get(inst, node, 1) ~= param_int(node, 2)
end

M.se_field_gt = function(inst, node)
    return (field_get(inst, node, 1) or 0) > param_int(node, 2)
end

M.se_field_ge = function(inst, node)
    return (field_get(inst, node, 1) or 0) >= param_int(node, 2)
end

M.se_field_lt = function(inst, node)
    return (field_get(inst, node, 1) or 0) < param_int(node, 2)
end

M.se_field_le = function(inst, node)
    return (field_get(inst, node, 1) or 0) <= param_int(node, 2)
end
```

### Range Check

```lua
-- params[1] = field_ref,  params[2] = low,  params[3] = high  (inclusive)
M.se_field_in_range = function(inst, node)
    local v   = field_get(inst, node, 1) or 0
    local low = param_int(node, 2)
    local hi  = param_int(node, 3)
    return v >= low and v <= hi
end
```

### Event Check

```lua
-- True if inst.current_event_id matches params[1] (uint or str_hash)
M.se_check_event = function(inst, node)
    local p = (node.params or {})[1]
    if not p then return false end
    local check_id = (type(p.value) == "table") and p.value.hash or p.value
    return inst.current_event_id == check_id
end
```

### Increment-and-Test Predicates

These predicates mutate state — they are the exception to the "predicates are stateless" rule, used for loop control.

```lua
-- se_field_increment_and_test: adds increment to counter each call
-- params[1] = counter field_ref, params[2] = increment field_ref, params[3] = limit field_ref
-- Returns true while counter <= limit; false when counter > limit
M.se_field_increment_and_test = function(inst, node)
    local counter   = field_get(inst, node, 1) or 0
    local increment = field_get(inst, node, 2) or 1
    local limit     = field_get(inst, node, 3) or 0
    counter = counter + increment
    se_runtime.field_set(inst, node, 1, counter)
    return counter <= limit
end

-- se_state_increment_and_test: uses node_state.user_data as counter
-- params[1] = increment (uint), params[2] = limit (uint)
-- Returns true while counter <= limit; resets to 0 when exceeded
M.se_state_increment_and_test = function(inst, node)
    local ns        = get_ns(inst, node.node_index)
    local increment = param_int(node, 1)
    local limit     = param_int(node, 2)
    ns.user_data = (ns.user_data or 0) + increment
    if ns.user_data > limit then
        ns.user_data = 0
        return false
    end
    return true
end
```

## Runtime Dispatch Infrastructure

### `invoke_pred(inst, node)`

The core dispatch function in `se_runtime.lua`. Looks up the predicate function by `node.func_index` and calls it:

```lua
invoke_pred = function(inst, node)
    local fn = inst.mod.pred_fns[node.func_index]
    assert(fn, "invoke_pred: no function for: " .. tostring(node.func_name))
    inst.current_node_index = node.node_index
    return fn(inst, node) and true or false   -- normalize to boolean
end
```

The `and true or false` ensures the return value is always a proper Lua boolean, regardless of what the predicate function returns.

### `child_invoke_pred(inst, node, idx)`

Convenience wrapper for composites and main functions that need to evaluate a child predicate by 0-based index:

```lua
local function child_invoke_pred(inst, node, idx)
    local child = (node.children or {})[idx + 1]   -- 0-based → 1-based
    assert(child, "child_invoke_pred: bad index " .. idx)
    return invoke_pred(inst, child)
end
```

### `invoke_any` — Predicate Path

When `invoke_any` encounters a `p_call` or `p_call_composite` node, it dispatches via `invoke_pred` and converts the boolean result to a pipeline code:

```lua
-- In invoke_any:
elseif ct == "p_call" or ct == "p_call_composite" then
    return invoke_pred(inst, node)
        and SE_PIPELINE_CONTINUE
        or  SE_PIPELINE_HALT
```

This means composites that call `child_invoke(inst, node, idx, eid, edata)` on a predicate child get `SE_PIPELINE_CONTINUE` (true) or `SE_PIPELINE_HALT` (false) rather than a boolean — the conversion is transparent.

## Comparison with C Implementation

| Aspect | C | LuaJIT |
|--------|---|--------|
| Function signature | `fn(inst, params, count, event_type, event_id, event_data)` | `fn(inst, node)` |
| Child iteration | `s_expr_skip_param` loop over flat param stream | `for _, child in ipairs(node.children)` |
| Child detection | `s_expr_param_is_predicate(&params[i])` | Not needed — `node.children` only contains callables |
| Child invocation | `s_expr_invoke_pred(inst, params, i)` | `invoke_pred(inst, child)` |
| Registration | `{hash, fn_ptr}` pair in static table | `{name = fn}` in Lua table via `merge_fns` |
| XOR semantics | Exactly one true | Odd count true (standard parity XOR) |

The elimination of `s_expr_skip_param` and `s_expr_param_is_predicate` is the most significant simplification. In C, composite predicates must scan a flat token stream, detect predicate markers, invoke them, and skip over their parameter ranges. In LuaJIT, children are pre-separated — the loop is a simple `ipairs` over `node.children`.

## Usage Patterns

### Simple Predicate in a Wait Node

```lua
-- Tree node structure (pipeline output):
{
    func_name = "se_wait", call_type = "m_call",
    children = {
        -- children[0]: predicate
        { func_name = "se_field_gt", call_type = "p_call",
          params = {
            {type="field_ref", value="temperature"},
            {type="int", value=100},
          },
          children = {} },
    }
}

-- At runtime, se_wait calls:
--   child_invoke_pred(inst, node, 0)
-- which invokes se_field_gt(inst, child_node) → true/false
```

### Composite Predicate in Trigger

```lua
-- (temp > 100) AND (pressure < 500)
{
    func_name = "se_trigger_on_change", call_type = "m_call",
    params = { {type="uint", value=0} },   -- initial_state = 0
    children = {
        -- children[0]: predicate (composite AND)
        { func_name = "se_pred_and", call_type = "p_call_composite",
          children = {
            { func_name = "se_field_gt", call_type = "p_call",
              params = {{type="field_ref", value="temp"}, {type="int", value=100}} },
            { func_name = "se_field_lt", call_type = "p_call",
              params = {{type="field_ref", value="pressure"}, {type="int", value=500}} },
          }
        },
        -- children[1]: rising action
        { func_name = "se_log", call_type = "o_call",
          params = {{type="str_idx", value="condition met!"}} },
        -- children[2]: falling action
        { func_name = "se_log", call_type = "o_call",
          params = {{type="str_idx", value="condition cleared"}} },
    }
}
```

### Deeply Nested: (A AND B) OR (C AND D)

```lua
{
    func_name = "se_pred_or", call_type = "p_call_composite",
    children = {
        { func_name = "se_pred_and", call_type = "p_call_composite",
          children = {
            { func_name = "se_field_eq", call_type = "p_call",
              params = {{type="field_ref", value="mode"}, {type="int", value=1}} },
            { func_name = "se_field_gt", call_type = "p_call",
              params = {{type="field_ref", value="level"}, {type="int", value=50}} },
          }
        },
        { func_name = "se_pred_and", call_type = "p_call_composite",
          children = {
            { func_name = "se_field_eq", call_type = "p_call",
              params = {{type="field_ref", value="mode"}, {type="int", value=2}} },
            { func_name = "se_field_gt", call_type = "p_call",
              params = {{type="field_ref", value="level"}, {type="int", value=75}} },
          }
        },
    }
}

-- Runtime evaluation:
-- se_pred_or iterates children:
--   child[1]: se_pred_and → iterates its children:
--     se_field_eq(mode == 1) → true
--     se_field_gt(level > 50) → true
--     → AND returns true
--   → OR short-circuits, returns true (skips second AND branch)
```

## User-Defined Predicates

Custom predicates follow the same signature and register through `merge_fns`:

```lua
-- Custom predicate: test if a specific bit is set in a bitmap field
local function test_bit(inst, node)
    local bitmap = inst.blackboard["bitmap"] or 0
    local bit_index = se_runtime.param_int(node, 1)
    return bit.band(bitmap, bit.lshift(1, bit_index)) ~= 0
end

-- Register alongside builtins
local fns = se_runtime.merge_fns(
    require("se_builtins_pred"),
    { test_bit = test_bit }
)
```

The pipeline must include `"test_bit"` in `module_data.pred_funcs` for nodes that reference it. Custom predicates can be used as children of composite predicates just like builtins.

## Predicate Summary Table

| Predicate | Children | Short-Circuit | Result |
|-----------|----------|---------------|--------|
| `se_pred_and` | 0..N | Yes (first false) | All true → true |
| `se_pred_or` | 0..N | Yes (first true) | Any true → true |
| `se_pred_not` | 1 | N/A | Inverts child |
| `se_pred_nor` | 0..N | Yes (first true) | All false → true |
| `se_pred_nand` | 0..N | Yes (first false) | Any false → true |
| `se_pred_xor` | 0..N | No (must count all) | Odd count true → true |
| `se_true` | 0 | N/A | Always true |
| `se_false` | 0 | N/A | Always false |
| `se_field_eq` | 0 | N/A | field == param |
| `se_field_ne` | 0 | N/A | field != param |
| `se_field_gt` | 0 | N/A | field > param |
| `se_field_ge` | 0 | N/A | field >= param |
| `se_field_lt` | 0 | N/A | field < param |
| `se_field_le` | 0 | N/A | field <= param |
| `se_field_in_range` | 0 | N/A | low <= field <= high |
| `se_check_event` | 0 | N/A | event_id matches param |
| `se_field_increment_and_test` | 0 | N/A | counter <= limit (mutates) |
| `se_state_increment_and_test` | 0 | N/A | counter <= limit (mutates node_state) |

## Design Principles

1. **Composability** — predicates nest arbitrarily deep via `node.children`
2. **Short-circuit evaluation** — AND/OR stop early for efficiency
3. **Uniform signature** — all predicates are `fn(inst, node) → bool`
4. **Pre-separated children** — pipeline eliminates runtime parameter scanning
5. **Stateless** — predicates don't maintain state (except increment_and_test variants)
6. **User-extensible** — custom predicates register identically to builtins
7. **Boolean normalization** — `invoke_pred` ensures return value is always `true`/`false`