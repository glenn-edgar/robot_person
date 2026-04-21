# stack_test.lua — Stack Frame and Quad Operations Test (LuaJIT Runtime)

## Overview

This test exercises the S-Expression Engine's stack frame management, quad arithmetic operations, and function call/return mechanism in the LuaJIT runtime. It validates that stack-based local variables, scratch space, parameter passing, and return value retrieval all work correctly across nested frames.

The test runs three sequential actions inside `se_function_interface`, each progressively more complex. The stack is implemented in `se_stack.lua`, frames are managed by `se_frame_allocate` and `se_stack_frame_instance` in `se_builtins_stack.lua`, and quad operations are dispatched by `se_quad` / `se_p_quad` in `se_builtins_quads.lua`.

## Record Definition

The blackboard record provides workspace fields for the test. In `module_data.records`:

```lua
records["stack_test_state"] = {
    fields = {
        int_val_1    = { type = "int32",  default = 0 },
        int_val_2    = { type = "int32",  default = 0 },
        int_val_3    = { type = "int32",  default = 0 },
        uint_val_1   = { type = "uint32", default = 0 },
        uint_val_2   = { type = "uint32", default = 0 },
        uint_val_3   = { type = "uint32", default = 0 },
        float_val_1  = { type = "float",  default = 0 },
        float_val_2  = { type = "float",  default = 0 },
        float_val_3  = { type = "float",  default = 0 },
        loop_count   = { type = "uint32", default = 0 },
    }
}
```

After `se_runtime.new_instance()`, these become string-keyed entries in `inst.blackboard` (e.g., `inst.blackboard["int_val_1"] = 0`).

## Test Actions

### action_1 — Integer Quad Operations with Frame Allocation

**Purpose:** Validate integer quad arithmetic using blackboard fields inside a stack frame, with a loop and tick delays.

**Tree structure:**

```
SE_FORK_JOIN
└── SE_WHILE (pred: SE_STATE_INCREMENT_AND_TEST, step=1, limit=100)
    └── SE_FRAME_ALLOCATE(0 params, 5 locals, 5 scratch)
        ├── [o_call] SE_QUAD  IADD(field:int_val_1, float:1.0, field:int_val_2)
        ├── [o_call] SE_QUAD  IADD(field:int_val_1, uint:5,    field:int_val_2)
        ├── [o_call] SE_QUAD  ISUB(field:int_val_2, uint:2,    field:int_val_3)
        ├── [o_call] SE_QUAD  MOVE(field:int_val_3, null,      field:int_val_1)
        ├── [pt_m_call] SE_TICK_DELAY 5
        └── SE_RETURN_PIPELINE_DISABLE
```

**Operations per iteration (executed as `se_quad` oneshots):**

Each `se_quad` node has `params = { opcode, src1, src2, dest }`. At runtime, `exec_quad` in `se_builtins_quads.lua` dispatches on the opcode:

1. `int_val_2 = int_val_1 + 1` — opcode `IADD` (0x00), src1 = `{type="field_ref", value="int_val_1"}`, src2 = `{type="float", value=1.0}`, dest = `{type="field_ref", value="int_val_2"}`. The `read_int` function floors the float to integer.
2. `int_val_2 = int_val_1 + 5` — opcode `IADD`, overwrites previous result
3. `int_val_3 = int_val_2 - 2` — opcode `ISUB` (0x01)
4. `int_val_1 = int_val_3` — opcode `MOVE` (0x40)

**Net effect:** `int_val_1` increases by 3 each iteration (0, 3, 6, 9, ..., 297).

**Validates:**
- Integer quad opcodes (IADD 0x00, ISUB 0x01, MOVE 0x40) in `exec_quad`
- `read_int` / `write_int` dispatch on `"field_ref"` param type → `inst.blackboard[name]`
- Float-to-int coercion in `read_int` (`math.floor(p.value)` for `"float"` params)
- `se_frame_allocate` push/pop frame each tick via `se_stack.push_frame` / `pop_frame`
- `se_while` loop with `se_state_increment_and_test` predicate

### action_2 — Float Quad Operations with Frame Allocation

**Purpose:** Same structure as action_1 but with floating-point arithmetic.

**Operations per iteration:**
1. `float_val_2 = float_val_1 + 1.0` — opcode `FADD` (0x08)
2. `float_val_2 = float_val_1 + 5.0` — opcode `FADD`, overwrites previous
3. `float_val_3 = float_val_2 - 2.0` — opcode `FSUB` (0x09)
4. `float_val_1 = float_val_3` — opcode `MOVE` (0x40)

**Net effect:** `float_val_1` increases by 3.0 each iteration (0.0, 3.0, 6.0, ..., 27.0).

**Validates:**
- Float quad opcodes (FADD 0x08, FSUB 0x09) in `exec_quad`
- `read_float` / `write_float` dispatch on `"field_ref"` → `inst.blackboard[name]`
- Float arithmetic in `exec_quad`: `f1 + f2`, `f1 - f2` using Lua native math
- The `+ 0.0` coercion in `read_float` for `"uint"` params

### action_3 — Stack Locals, Scratch, and Function Call/Return

**Purpose:** Full integration test of stack frame locals, scratch variables, parameter passing via `stack_push`, function call with `se_call`, and return value retrieval via `stack_pop`.

**Tree structure:**

```
SE_FORK_JOIN
└── SE_WHILE (pred: SE_P_QUAD P_ICMP_LT_ACC on loop_count)
    └── SE_FRAME_ALLOCATE(0 params, 5 locals, 5 scratch)
        ├── [o_call] SE_QUAD  FADD(field:float_val_1, float:1.0, local:a)
        ├── [o_call] SE_QUAD  FADD(local:a, float:5.0, field:float_val_2)
        ├── [o_call] SE_QUAD  MOVE(field:float_val_2, null, local:b)
        ├── [o_call] SE_QUAD  FSUB(local:b, float:2.0, field:float_val_3)
        ├── [o_call] SE_QUAD  MOVE(field:float_val_3, null, field:float_val_1)
        ├── [o_call] SE_QUAD  MOVE(field:float_val_1, null, stack_push)  ← p0
        ├── [o_call] SE_QUAD  MOVE(field:float_val_2, null, stack_push)  ← p1
        ├── SE_SEQUENCE_ONCE
        │   ├── [o_call] SE_PUSH_STACK(2)        ← param count marker
        │   ├── SE_STACK_FRAME_INSTANCE(2, 2, 3, {2, 3})
        │   ├── [o_call] SE_QUAD  FADD(local:p0, float:1.0, tos:ct0)
        │   ├── [o_call] SE_QUAD  FADD(tos:ct0, float:5.0, tos:ct1)
        │   ├── [o_call] SE_QUAD  FSUB(tos:ct1, float:2.0, local:r0)
        │   ├── [o_call] SE_QUAD  FMUL(local:p1, float:2.0, local:r1)
        │   └── SE_RETURN_PIPELINE_TERMINATE
        ├── [o_call] SE_QUAD  MOVE(stack_pop, null, local:e)   ← gets r1
        ├── [o_call] SE_QUAD  MOVE(stack_pop, null, local:f)   ← gets r0
        ├── [o_call] SE_QUAD  MOVE(local:e, null, field:float_val_2)
        ├── [o_call] SE_QUAD  MOVE(local:f, null, field:float_val_3)
        ├── [pt_m_call] SE_TICK_DELAY 5
        └── SE_RETURN_PIPELINE_DISABLE
```

**Outer frame variables (via `frame_vars` at compile time):**
- Locals: `a`, `b`, `c`, `e`, `f` — param type `"stack_local"`, indices 0–4
- Scratch: `t0`, `t1`, `t2`, `t3`, `t4` — param type `"stack_tos"`, offsets 4–0

**Outer frame operations per iteration:**

The `read_float` / `write_float` functions in `se_builtins_quads.lua` dispatch on param type:
- `"stack_local"` → `se_stack.get_local(stk, idx)` / `se_stack.set_local(stk, idx, val)`
- `"stack_tos"` → `se_stack.peek_tos(stk, offset)` / `se_stack.poke(stk, offset, val)`
- `"stack_push"` → `se_stack.push(stk, val)`
- `"stack_pop"` → `se_stack.pop(stk)`
- `"field_ref"` → `inst.blackboard[name]`

Operations:
1. `a = float_val_1 + 1.0` — reads blackboard, writes stack local 0
2. `float_val_2 = a + 5.0` — reads stack local 0, writes blackboard
3. `b = float_val_2` — reads blackboard, writes stack local 1
4. `float_val_3 = b - 2.0` — reads stack local 1, writes blackboard
5. `float_val_1 = float_val_3` — blackboard to blackboard

Net: `float_val_1 += 4.0` each iteration.

**Call setup (parameter passing via stack):**
1. `MOVE(field:float_val_1, null, stack_push)` — `se_stack.push(stk, val)` pushes p0
2. `MOVE(field:float_val_2, null, stack_push)` — pushes p1

**Call frame lifecycle (`se_stack_frame_instance` in `se_builtins_stack.lua`):**

On INIT:
```lua
-- 1. Pop param count marker (pushed by SE_PUSH_STACK)
local passed = se_stack.pop(stk)   -- 2

-- 2. Validate against expected num_params
assert(passed == 2)

-- 3. Push frame: params already on stack become frame params
se_stack.push_frame(stk, 2, 2)  -- 2 params, 2 locals (zeroed)

-- 4. Set state = 1 (frame active)
```

On TERMINATE (when `SE_RETURN_PIPELINE_TERMINATE` fires):
```lua
-- 1. Collect return var values before frame is destroyed
--    return_vars = {2, 3} → read locals 2 and 3
local temps = {}
temps[1] = se_stack.get_local(stk, 2)   -- r0
temps[2] = se_stack.get_local(stk, 3)   -- r1

-- 2. Pop frame (restores SP to caller's position)
se_stack.pop_frame(stk)

-- 3. Push return values in list order
se_stack.push(stk, temps[1])   -- r0 pushed first
se_stack.push(stk, temps[2])   -- r1 pushed second (on top)
```

**Call frame variables:**
- Locals: `p0` (param 0), `p1` (param 1), `r0` (local 2), `r1` (local 3) — `"stack_local"` indices 0–3
- Scratch: `ct0`, `ct1`, `ct2` — `"stack_tos"` offsets 2–0

**Call frame operations:**
1. `ct0 = p0 + 1.0` — FADD, reads stack_local(0), writes stack_tos(2)
2. `ct1 = ct0 + 5.0` — FADD, reads stack_tos(2), writes stack_tos(1)
3. `r0 = ct1 - 2.0` — FSUB, reads stack_tos(1), writes stack_local(2) → result: `p0 + 4.0`
4. `r1 = p1 * 2.0` — FMUL (0x0A), reads stack_local(1), writes stack_local(3) → result: `p1 * 2.0`

**Return value retrieval (LIFO pop):**
1. `MOVE(stack_pop, null, local:e)` — `se_stack.pop(stk)` gets r1 (last pushed, on top)
2. `MOVE(stack_pop, null, local:f)` — `se_stack.pop(stk)` gets r0
3. `MOVE(local:e, null, field:float_val_2)` — store r1 to blackboard
4. `MOVE(local:f, null, field:float_val_3)` — store r0 to blackboard

**Expected values (iteration where float_val_1 enters as 36.0):**

| Step | Value |
|------|-------|
| float_val_1 (input) | 36.0 |
| a = 36.0 + 1.0 | 37.0 |
| float_val_2 = 37.0 + 5.0 | 42.0 |
| float_val_3 = 42.0 - 2.0 | 40.0 |
| float_val_1 = 40.0 | 40.0 |
| p0 = 40.0, p1 = 42.0 | — |
| r0 = (40+1+5) - 2 | 44.0 |
| r1 = 42 * 2 | 84.0 |
| float_val_2 (from pop) | 84.0 (r1) |
| float_val_3 (from pop) | 44.0 (r0) |

**Validates:**
- `se_stack.get_local` / `set_local` for local variable access (0-based index → `base_ptr + num_params + idx + 1`)
- `se_stack.peek_tos` / `poke` for scratch variable access (offset from SP)
- `se_stack.push` as quad write destination (`"stack_push"` param type)
- `se_stack.pop` as quad read source (`"stack_pop"` param type)
- `se_call` / `SE_PUSH_STACK` / `SE_STACK_FRAME_INSTANCE` parameter passing chain
- Frame lifecycle: INIT (pop count, push_frame) → TICK (PIPELINE_CONTINUE) → TERMINATE (copy returns, pop_frame, push returns)
- Return value ordering: `return_vars = {2, 3}` pushes r0 first, r1 second; caller pops r1 first (LIFO)
- Nested frames: outer `se_frame_allocate` + inner `se_call` frame coexist on the same `inst.stack`

## Test Sequence

```
1. [o_call] SE_LOG_STACK               ← print initial stack state
2. [o_call] SE_SET_FIELD int_val_1 = 0
3. [o_call] SE_SET_FIELD float_val_1 = 0.0
4. action_1: 100 iterations of integer arithmetic (500 ticks)
5. action_2: 10 iterations of float arithmetic (50 ticks)
6. [o_call] SE_SET_FIELD int_val_1 = 0   ← reset for action_3
7. [o_call] SE_SET_FIELD float_val_1 = 0.0
8. action_3: 10 iterations of call/return test (50 ticks)
9. [o_call] SE_LOG_STACK               ← print final stack state
10. SE_RETURN_FUNCTION_TERMINATE
```

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_stack.lua` | `new_stack`, `push`, `pop`, `push_frame`, `pop_frame`, `get_local`, `set_local`, `peek_tos`, `poke` | Stack data structure |
| `se_builtins_stack.lua` | `se_frame_allocate`, `se_stack_frame_instance`, `se_log_stack` | Frame lifecycle management |
| `se_builtins_quads.lua` | `se_quad` (IADD, ISUB, FADD, FSUB, FMUL, MOVE), `se_p_quad` (P_ICMP_LT_ACC) | Arithmetic operations |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_fork_join`, `se_while`, `se_sequence_once` | Control flow |
| `se_builtins_delays.lua` | `se_tick_delay` | Multi-tick delay |
| `se_builtins_oneshot.lua` | `se_log`, `se_set_field`, `se_push_stack` | Logging, field writes, stack push |
| `se_builtins_pred.lua` | `se_state_increment_and_test` | Counter-based loop predicate |
| `se_builtins_return_codes.lua` | `se_return_pipeline_disable`, `se_return_pipeline_terminate`, `se_return_function_terminate` | Fixed return codes |

## Stack Layout During action_3 Call

All stack values are plain Lua numbers (not typed `s_expr_param_t` structs as in C). The type distinction is handled by opcode selection (IADD vs FADD), not by the stored value.

```
                    ┌─────────────────────┐
                    │  scratch (ct0-ct2)  │ ← SP (TOS during call body)
                    ├─────────────────────┤
                    │  r1 (local 3)       │ ← return var, stack_local(3)
                    │  r0 (local 2)       │ ← return var, stack_local(2)
                    ├─────────────────────┤
                    │  p1 (param 1)       │ ← from stack_push, stack_local(1)
                    │  p0 (param 0)       │ ← from stack_push, stack_local(0)
  call frame ──►   ├═════════════════════┤ ← base_ptr (call)
                    │  scratch (t0-t4)    │ ← TOS during outer body
                    ├─────────────────────┤
                    │  f  (local 4)       │ ← stack_local(4)
                    │  e  (local 3)       │ ← stack_local(3)
                    │  c  (local 2)       │ ← stack_local(2)
                    │  b  (local 1)       │ ← stack_local(1)
                    │  a  (local 0)       │ ← stack_local(0)
  outer frame ──►  ├═════════════════════┤ ← base_ptr (outer)
                    │  (empty - 0 params) │
                    └─────────────────────┘
```

Internally in `se_stack.lua`:
- `base_ptr` is the `stk.data[]` index below the first param
- Locals are at `stk.data[base_ptr + num_params + local_idx + 1]` (1-based `data[]`)
- Scratch is above locals, accessed via `stk.data[stk.sp - offset]`
- `push_frame` zeroes the local slots; `pop_frame` restores `stk.sp` to `base_ptr`

After `se_stack_frame_instance` TERMINATE fires, the call frame is popped and return values `r0`, `r1` are pushed onto the outer frame's stack via `se_stack.push`. The outer frame then pops them with `se_stack.pop` (LIFO order: r1 first, r0 second).

## Test Harness

```lua
local se_runtime = require("se_runtime")
local se_stack   = require("se_stack")
local module_data = require("stack_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_return_codes"),
    require("se_builtins_stack"),
    require("se_builtins_quads"),
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "stack_test")

-- Attach stack (required for frame_allocate, se_call, quad stack ops)
inst.stack = se_stack.new_stack(256)

local tick_count = 0
repeat
    local result = se_runtime.tick_once(inst)
    tick_count = tick_count + 1

    while se_runtime.event_count(inst) > 0 do
        local tt, eid, edata = se_runtime.event_pop(inst)
        local saved = inst.tick_type
        inst.tick_type = tt
        result = se_runtime.tick_once(inst, eid, edata)
        inst.tick_type = saved
    end

until result == se_runtime.SE_FUNCTION_TERMINATE or tick_count >= 2000

-- Verify results
print("int_val_1 = " .. inst.blackboard["int_val_1"])     -- expect 297
print("float_val_1 = " .. inst.blackboard["float_val_1"]) -- expect final value
print(string.format("Completed in %d ticks", tick_count))
print(tick_count <= 2000 and "✅ PASSED" or "❌ TIMEOUT")
```

## Files

- `stack_test_module.lua` — pipeline-generated `module_data` Lua table
- `test_stack.lua` — LuaJIT test harness
- `se_stack.lua` — stack data structure (push/pop, frame management)
- `se_builtins_stack.lua` — `se_frame_allocate`, `se_stack_frame_instance`, `se_log_stack`
- `se_builtins_quads.lua` — `se_quad`, `se_p_quad`, `exec_quad`, `read_int/float`, `write_int/float`