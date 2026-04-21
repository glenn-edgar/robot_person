# S_Engine Return Codes — LuaJIT Runtime

## Overview

The S_Engine uses a layered return code system that maps to three distinct scopes of control flow. Each layer serves a different purpose in the execution hierarchy, from ChainTree event propagation down to internal pipeline sequencing. The numeric values and semantics are identical between the C and LuaJIT runtimes — any tree produces the same result codes in both.

## The Three Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                      ChainTree Walker                           │
│                   (behavior tree engine)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ APPLICATION RESULT CODES (0–5)
                           │ (SE_CONTINUE, SE_HALT, SE_TERMINATE, ...)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     S_Engine Function                           │
│              (se_function_interface boundary)                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           │ FUNCTION RESULT CODES (6–11)
                           │ (SE_FUNCTION_CONTINUE, SE_FUNCTION_HALT, ...)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Pipeline Composites                          │
│    (se_sequence, se_chain_flow, se_fork, se_state_machine, ...) │
└─────────────────────────────────────────────────────────────────┘
                           │
                           │ PIPELINE RESULT CODES (12–17)
                           │ (SE_PIPELINE_CONTINUE, SE_PIPELINE_HALT, ...)
                           │
                           ▼
                    ┌──────────────┐
                    │ Child Nodes  │
                    └──────────────┘
```

## Result Code Definitions

All result codes are defined as module-level constants in `se_runtime.lua`:

```lua
-- APPLICATION RESULT CODES (pass through to ChainTree)
M.SE_CONTINUE               = 0
M.SE_HALT                   = 1
M.SE_TERMINATE              = 2
M.SE_RESET                  = 3
M.SE_DISABLE                = 4
M.SE_SKIP_CONTINUE          = 5

-- FUNCTION RESULT CODES (handled at function boundary)
M.SE_FUNCTION_CONTINUE      = 6
M.SE_FUNCTION_HALT          = 7
M.SE_FUNCTION_TERMINATE     = 8
M.SE_FUNCTION_RESET         = 9
M.SE_FUNCTION_DISABLE       = 10
M.SE_FUNCTION_SKIP_CONTINUE = 11

-- PIPELINE RESULT CODES (handled by composite nodes)
M.SE_PIPELINE_CONTINUE      = 12
M.SE_PIPELINE_HALT          = 13
M.SE_PIPELINE_TERMINATE     = 14
M.SE_PIPELINE_RESET         = 15
M.SE_PIPELINE_DISABLE       = 16
M.SE_PIPELINE_SKIP_CONTINUE = 17
```

Each tier has **six codes** with parallel semantics: CONTINUE, HALT, TERMINATE, RESET, DISABLE, and SKIP_CONTINUE. The numeric values form three contiguous ranges of 6, making tier detection a simple range check.

---

## Application Result Codes (0–5)

These codes pass through the S_Engine unchanged. They originate from ChainTree's event system and control tree-level propagation. When a node returns one of these codes, the S_Engine forwards it directly to the ChainTree walker.

```lua
SE_CONTINUE           = 0   -- Normal execution, continue to next tick
SE_HALT               = 1   -- Pause execution, retain state
SE_TERMINATE          = 2   -- Complete execution, trigger termination
SE_RESET              = 3   -- Restart from initial state
SE_DISABLE            = 4   -- Deactivate node, skip future ticks
SE_SKIP_CONTINUE      = 5   -- Skip remaining siblings, parent continues
```

### Semantics

| Code | Tree Effect | State Effect |
|------|-------------|--------------|
| `SE_CONTINUE` | Walker proceeds normally | Node remains active |
| `SE_HALT` | Walker pauses this branch | Node retains current state |
| `SE_TERMINATE` | Walker terminates this subtree | Termination handlers run |
| `SE_RESET` | Walker resets this subtree | All nodes re-initialize |
| `SE_DISABLE` | Walker skips this node | Node marked inactive |
| `SE_SKIP_CONTINUE` | Walker skips siblings | Parent composite continues |

### Pass-Through Behavior

Pipeline composites propagate application codes directly to their parent without interpretation. In the LuaJIT runtime, every composite checks for application codes before handling pipeline codes:

```lua
-- From se_sequence in se_builtins_flow_control.lua:
local r = child_invoke(inst, node, s, event_id, event_data)

-- Application codes (0-5): propagate immediately
if r <= SE_SKIP_CONTINUE then
    return r
end
```

This ensures the S_Engine is a transparent layer — ChainTree events flow through without the S_Engine needing to understand their full semantics.

---

## Function Result Codes (6–11)

These codes affect the **entire S-expression function** currently executing. They are generated by nodes within the S-expression and processed by function-level composites like `se_function_interface`.

```lua
SE_FUNCTION_CONTINUE      = 6    -- Function still running normally
SE_FUNCTION_HALT          = 7    -- Halt the entire S-expression function
SE_FUNCTION_TERMINATE     = 8    -- Terminate the entire S-expression function
SE_FUNCTION_RESET         = 9    -- Reset the entire S-expression function
SE_FUNCTION_DISABLE       = 10   -- Disable the entire S-expression function
SE_FUNCTION_SKIP_CONTINUE = 11   -- Skip remaining siblings at function level
```

### Use Case: Exception-Like Control Flow

Function-level codes provide a way to escape from deeply nested structures without unwinding through each layer manually:

```lua
-- Deep nesting - how does inner node abort the whole function?
-- Tree structure:
--   se_function_interface
--     se_chain_flow
--       se_fork
--         se_if_then_else
--           pred: critical_error_detected
--           then: se_return_function_terminate   ← escapes everything
--           else: normal_operation
```

Without function-level codes, the `critical_error_detected` path would need to return a code that each parent composite understands and propagates. With `SE_FUNCTION_TERMINATE`, it escapes directly to the function boundary.

### Processing by se_function_interface

`se_function_interface` in `se_builtins_flow_control.lua` is the primary function-level composite. It handles function codes from its children:

```lua
-- From se_function_interface:
local r = child_invoke(inst, node, idx, event_id, event_data)

-- Non-pipeline codes: propagate immediately
if r < SE_PIPELINE_CONTINUE then
    return r   -- includes all application and function codes
end

-- Pipeline codes handled locally:
if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
    active_count = active_count + 1
elseif r == SE_PIPELINE_DISABLE or r == SE_PIPELINE_TERMINATE then
    child_terminate(inst, node, idx)
elseif r == SE_PIPELINE_RESET then
    child_terminate(inst, node, idx)
    child_reset(inst, node, idx)
    active_count = active_count + 1
elseif r == SE_PIPELINE_SKIP_CONTINUE then
    active_count = active_count + 1
    skip = true
end
```

When all children complete, `se_function_interface` returns `SE_FUNCTION_DISABLE`. While children are still active, it returns `SE_FUNCTION_CONTINUE`.

### Dedicated Return-Code Builtins

`se_builtins_return_codes.lua` provides trivial builtins that return a fixed code on every TICK, generated by a factory function:

```lua
local function make_return(code)
    return function(inst, node, event_id, event_data)
        if event_id == SE_EVENT_INIT      then return end
        if event_id == SE_EVENT_TERMINATE then return end
        return code
    end
end

M.se_return_function_continue      = make_return(se_runtime.SE_FUNCTION_CONTINUE)
M.se_return_function_halt          = make_return(se_runtime.SE_FUNCTION_HALT)
M.se_return_function_terminate     = make_return(se_runtime.SE_FUNCTION_TERMINATE)
M.se_return_function_reset         = make_return(se_runtime.SE_FUNCTION_RESET)
M.se_return_function_disable       = make_return(se_runtime.SE_FUNCTION_DISABLE)
M.se_return_function_skip_continue = make_return(se_runtime.SE_FUNCTION_SKIP_CONTINUE)
```

These are used as leaf nodes in the tree to force a specific return at any point.

### FUNCTION_HALT in Composites

Several composites translate `SE_FUNCTION_HALT` to `SE_PIPELINE_HALT` when they encounter it from a child, keeping the function alive across ticks:

```lua
-- From se_chain_flow:
if r == SE_FUNCTION_HALT then
    return SE_PIPELINE_HALT
end

-- From se_fork / se_fork_join:
if r == SE_FUNCTION_HALT then r = SE_PIPELINE_HALT end
```

This allows a child to signal "I'm not done yet" in a way that halts the current tick but keeps the parent composite active for the next tick.

---

## Pipeline Result Codes (12–17)

These codes are internal to **composite nodes** that sequence children: `se_sequence`, `se_chain_flow`, `se_fork`, `se_state_machine`, `se_while`, etc. They control how the composite manages its child execution.

```lua
SE_PIPELINE_CONTINUE      = 12   -- Child still active, composite continues
SE_PIPELINE_HALT          = 13   -- Pause this tick, resume next tick
SE_PIPELINE_TERMINATE     = 14   -- Terminate this composite
SE_PIPELINE_RESET         = 15   -- Reset composite children, restart
SE_PIPELINE_DISABLE       = 16   -- Child completed normally (deactivate)
SE_PIPELINE_SKIP_CONTINUE = 17   -- Skip remaining siblings this tick
```

### SE_PIPELINE_DISABLE: Normal Completion

`SE_PIPELINE_DISABLE` is the standard "I'm done" signal. When a main function returns this code, the `invoke_main` dispatch automatically sends `SE_EVENT_TERMINATE` and clears the node's `FLAG_ACTIVE`:

```lua
-- From invoke_main in se_runtime.lua:
if result == SE_PIPELINE_DISABLE then
    inst.current_node_index = node.node_index
    fn(inst, node, SE_EVENT_TERMINATE, nil)
    ns.flags = band(ns.flags, bnot(FLAG_ACTIVE))
end
```

### Composite Handling Patterns

Each composite type interprets pipeline codes according to its own semantics. Here are the patterns used across the LuaJIT builtins:

#### se_sequence — Advance on Completion

```lua
-- From se_sequence:
if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
    return SE_PIPELINE_CONTINUE   -- child still running, pause sequence

elseif r == SE_PIPELINE_DISABLE
    or r == SE_PIPELINE_TERMINATE
    or r == SE_PIPELINE_RESET then
    -- child complete: terminate and advance to next
    child_terminate(inst, node, s)
    ns.state = s + 1

elseif r == SE_PIPELINE_SKIP_CONTINUE then
    return SE_PIPELINE_CONTINUE   -- pause this tick
end
```

When all children complete, `se_sequence` returns `SE_PIPELINE_DISABLE`.

#### se_chain_flow — Parallel with Full Dispatch

```lua
-- From se_chain_flow:
if r == SE_PIPELINE_CONTINUE then
    active_count = active_count + 1

elseif r == SE_PIPELINE_HALT then
    return SE_PIPELINE_CONTINUE

elseif r == SE_PIPELINE_DISABLE then
    child_terminate(inst, node, idx)

elseif r == SE_PIPELINE_TERMINATE then
    children_terminate_all(inst, node)
    return SE_PIPELINE_TERMINATE

elseif r == SE_PIPELINE_RESET then
    children_terminate_all(inst, node)
    children_reset_all(inst, node)
    return SE_PIPELINE_CONTINUE

elseif r == SE_PIPELINE_SKIP_CONTINUE then
    active_count = active_count + 1
    skip = true
end
```

When `active_count` reaches 0, `se_chain_flow` returns `SE_PIPELINE_DISABLE`.

#### se_state_machine — Branch Switching

```lua
-- From se_state_machine:
-- On branch change: terminate old branch, reset new one
if action_child_idx ~= prev_child_idx then
    if prev_child_idx ~= nil and prev_child_idx ~= SENTINEL then
        child_terminate(inst, node, prev_child_idx)
        child_reset_recursive(inst, node, prev_child_idx)
    end
    child_reset_recursive(inst, node, action_child_idx)
    ns.user_data = action_child_idx
end

-- Invoke and translate:
local r = child_invoke(inst, node, action_child_idx, event_id, event_data)

if r == SE_FUNCTION_HALT then
    return SE_PIPELINE_HALT
end

if r == SE_PIPELINE_DISABLE
or r == SE_PIPELINE_TERMINATE
or r == SE_PIPELINE_RESET then
    child_terminate(inst, node, action_child_idx)
    child_reset_recursive(inst, node, action_child_idx)
    return SE_PIPELINE_CONTINUE
end
```

#### se_while — Loop Control

```lua
-- From se_while:
-- Body still running:
if r == SE_PIPELINE_CONTINUE
or r == SE_PIPELINE_HALT
or r == SE_PIPELINE_SKIP_CONTINUE then
    return SE_FUNCTION_HALT   -- keep body alive across ticks

-- Body complete: loop back to predicate
elseif r == SE_PIPELINE_DISABLE
    or r == SE_PIPELINE_TERMINATE
    or r == SE_PIPELINE_RESET then
    child_terminate(inst, node, 1)
    child_reset_recursive(inst, node, 1)
    ns.state = SE_WHILE_EVAL_PRED
    return SE_PIPELINE_HALT   -- re-evaluate pred next tick
end
```

### Use Cases

**SE_PIPELINE_DISABLE — Normal child completion:**

Every main function that finishes its work returns `SE_PIPELINE_DISABLE`. The `invoke_main` dispatch layer sends TERMINATE and deactivates the node automatically.

**SE_PIPELINE_TERMINATE — Early exit:**

```lua
-- In a sequence, stop early when goal is achieved:
--   se_sequence
--     try_method_a
--     se_return_pipeline_terminate   ← stops sequence here
--     try_method_b                   ← never reached
```

**SE_PIPELINE_RESET — Retry loop:**

```lua
-- In se_chain_flow, child returns RESET:
-- All children get terminated + reset, composite returns CONTINUE
-- This effectively restarts the entire composite from scratch
```

**SE_PIPELINE_SKIP_CONTINUE — Skip remaining siblings:**

```lua
-- In se_chain_flow or se_fork, a child returns SKIP_CONTINUE:
-- The composite breaks out of its child iteration loop for this tick
-- but counts the child as active (composite stays alive)
```

---

## Code Propagation Summary

```
Child returns result code
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Is it a PIPELINE code (12–17)?                                │
│   YES → Composite handles internally, does NOT propagate      │
│         CONTINUE → child active, count it                     │
│         HALT → pause tick, composite returns CONTINUE         │
│         DISABLE → child done, terminate it                    │
│         TERMINATE → end composite (or all children)           │
│         RESET → terminate+reset children, restart             │
│         SKIP_CONTINUE → break child loop, stay active         │
│   NO  → Continue checking                                     │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Is it a FUNCTION code (6–11)?                                 │
│   YES → Propagated to function boundary                       │
│         Some composites translate FUNCTION_HALT → PIPELINE_HALT│
│         se_function_interface returns FUNCTION_* to caller     │
│   NO  → Continue checking                                     │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Is it an APPLICATION code (0–5)?                              │
│   YES → Pass through to ChainTree unchanged                   │
│         Every composite propagates these immediately:          │
│         if r <= SE_SKIP_CONTINUE then return r end            │
└───────────────────────────────────────────────────────────────┘
```

### Tier Detection in Code

Composites detect tiers using simple range comparisons:

```lua
-- Application codes (0–5): propagate immediately
if r <= SE_SKIP_CONTINUE then return r end

-- Function codes (6–11): some composites translate, others propagate
if r >= SE_FUNCTION_CONTINUE and r <= SE_FUNCTION_SKIP_CONTINUE then
    if r == SE_FUNCTION_HALT then return SE_PIPELINE_HALT end
    return r
end

-- Pipeline codes (12–17): handle locally
if r < SE_PIPELINE_CONTINUE then
    return r   -- non-pipeline code, propagate
end
-- ... handle pipeline codes ...
```

The most common check is `if r < SE_PIPELINE_CONTINUE then return r end` which propagates all application and function codes in one comparison.

---

## invoke_main: The DISABLE → TERMINATE Gateway

A critical piece of the return code system is the `invoke_main` function in `se_runtime.lua`. It intercepts `SE_PIPELINE_DISABLE` and automatically runs the TERMINATE lifecycle phase:

```lua
invoke_main = function(inst, node, event_id, event_data)
    -- ... INIT phase, TICK phase ...
    local result = fn(inst, node, event_id, event_data)
    result = result or SE_PIPELINE_CONTINUE

    -- DISABLE triggers automatic termination
    if result == SE_PIPELINE_DISABLE then
        fn(inst, node, SE_EVENT_TERMINATE, nil)
        ns.flags = band(ns.flags, bnot(FLAG_ACTIVE))
    end

    return result
end
```

This means:
- A function returning `SE_PIPELINE_DISABLE` signals "I'm done."
- The runtime automatically calls the function with `SE_EVENT_TERMINATE`.
- The node's `FLAG_ACTIVE` is cleared, preventing future dispatch.
- The parent composite sees `SE_PIPELINE_DISABLE` and handles it (typically by removing the child from its active set).

Other pipeline codes (`TERMINATE`, `RESET`) propagate upward intact — the node stays active so the parent composite can decide how to handle them.

---

## Return Code Builtins

`se_builtins_return_codes.lua` provides a complete set of trivial builtins for all 18 codes, generated by a factory:

```lua
-- Application level
M.se_return_continue          = make_return(SE_CONTINUE)
M.se_return_halt              = make_return(SE_HALT)
M.se_return_terminate         = make_return(SE_TERMINATE)
M.se_return_reset             = make_return(SE_RESET)
M.se_return_disable           = make_return(SE_DISABLE)
M.se_return_skip_continue     = make_return(SE_SKIP_CONTINUE)

-- Function level
M.se_return_function_continue      = make_return(SE_FUNCTION_CONTINUE)
M.se_return_function_halt          = make_return(SE_FUNCTION_HALT)
M.se_return_function_terminate     = make_return(SE_FUNCTION_TERMINATE)
M.se_return_function_reset         = make_return(SE_FUNCTION_RESET)
M.se_return_function_disable       = make_return(SE_FUNCTION_DISABLE)
M.se_return_function_skip_continue = make_return(SE_FUNCTION_SKIP_CONTINUE)

-- Pipeline level
M.se_return_pipeline_continue      = make_return(SE_PIPELINE_CONTINUE)
M.se_return_pipeline_halt          = make_return(SE_PIPELINE_HALT)
M.se_return_pipeline_terminate     = make_return(SE_PIPELINE_TERMINATE)
M.se_return_pipeline_reset         = make_return(SE_PIPELINE_RESET)
M.se_return_pipeline_disable       = make_return(SE_PIPELINE_DISABLE)
M.se_return_pipeline_skip_continue = make_return(SE_PIPELINE_SKIP_CONTINUE)
```

All 18 builtins silently ignore `SE_EVENT_INIT` and `SE_EVENT_TERMINATE` (returning `nil`, which `invoke_main` defaults to `SE_PIPELINE_CONTINUE`), and return their fixed code on every TICK.

---

## Design Rationale

### Why Three Layers?

1. **Separation of concerns**: ChainTree doesn't need to know about S_Engine internals. Pipeline composites don't need to know about function boundaries.

2. **Composability**: New composite types can define their own interpretation of pipeline codes without affecting the rest of the system. For example, `se_field_dispatch` handles `SE_PIPELINE_RESET` differently from `se_state_machine`.

3. **Efficiency**: Pipeline codes are handled locally with no propagation overhead. The range check `if r < SE_PIPELINE_CONTINUE then return r end` is a single comparison that handles all 12 non-pipeline codes.

4. **Clarity**: When reading code, the return code tells you exactly what scope it affects:
   - `SE_CONTINUE` → tree level (ChainTree)
   - `SE_FUNCTION_RESET` → function level (se_function_interface boundary)
   - `SE_PIPELINE_TERMINATE` → composite level (immediate parent only)

### Why Six Codes Per Tier?

Each tier mirrors the same six verbs — CONTINUE, HALT, TERMINATE, RESET, DISABLE, SKIP_CONTINUE — at different scopes. This parallel structure means the same mental model applies at every level, and composites that need to translate between tiers have a natural mapping.

### Relationship to ChainTree Events

ChainTree has its own event system (`SE_EVENT_INIT`, `SE_EVENT_TICK`, `SE_EVENT_TERMINATE`). The application result codes map to ChainTree's expected return values:

| ChainTree Expectation | S_Engine Code |
|-----------------------|---------------|
| Continue normal execution | `SE_CONTINUE` (0) |
| Pause and retain state | `SE_HALT` (1) |
| Complete and cleanup | `SE_TERMINATE` (2) |
| Restart from scratch | `SE_RESET` (3) |
| Deactivate this branch | `SE_DISABLE` (4) |
| Skip siblings | `SE_SKIP_CONTINUE` (5) |

The S_Engine's function and pipeline codes are internal implementation details that ChainTree never sees.

---

## Quick Reference

```lua
-- se_runtime.lua result code constants:

-- APPLICATION (0–5): pass through to ChainTree
SE_CONTINUE               = 0    -- Normal, continue
SE_HALT                   = 1    -- Pause, retain state
SE_TERMINATE              = 2    -- Complete, cleanup
SE_RESET                  = 3    -- Restart
SE_DISABLE                = 4    -- Deactivate
SE_SKIP_CONTINUE          = 5    -- Skip siblings

-- FUNCTION (6–11): handled at function boundary
SE_FUNCTION_CONTINUE      = 6    -- Function running normally
SE_FUNCTION_HALT          = 7    -- Halt entire function
SE_FUNCTION_TERMINATE     = 8    -- Terminate entire function
SE_FUNCTION_RESET         = 9    -- Reset entire function
SE_FUNCTION_DISABLE       = 10   -- Disable entire function
SE_FUNCTION_SKIP_CONTINUE = 11   -- Skip siblings at function level

-- PIPELINE (12–17): handled by composite nodes
SE_PIPELINE_CONTINUE      = 12   -- Child active, composite continues
SE_PIPELINE_HALT          = 13   -- Pause tick, resume next tick
SE_PIPELINE_TERMINATE     = 14   -- Terminate composite
SE_PIPELINE_RESET         = 15   -- Reset children, restart
SE_PIPELINE_DISABLE       = 16   -- Child completed normally
SE_PIPELINE_SKIP_CONTINUE = 17   -- Skip remaining siblings this tick
```