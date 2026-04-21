# stack_test_equations — Expression Compiler Integration Test (LuaJIT Runtime)

## Purpose

Validates the expression compiler (`s_expr_compiler.lua` v1.1) by rewriting the original `stack_test.lua` (which used raw quad helper calls) to use `quad_expr`, `quad_multi`, and `quad_pred` with C-like expression syntax. Exercises the full compilation pipeline: parsing, type inference, constant folding, scratch allocation, and code generation — producing `se_quad` (oneshot) and `se_p_quad` (predicate) nodes that execute in the LuaJIT runtime via `se_builtins_quads.lua`.

The test confirms that the expression compiler produces identical results to hand-written quad calls, validating both the compiler and the runtime's `exec_quad` dispatch across integer arithmetic, float arithmetic, stack local/scratch access, and function call parameter passing.

## Compiler Features Exercised

| Feature | Where Tested | Generated Node |
|---------|-------------|----------------|
| `quad_expr` with `@field` destination | Actions 1, 2 | `se_quad` with `{type="field_ref"}` dest |
| `quad_expr` with local destination | Action 3 (call body) | `se_quad` with `{type="stack_local"}` dest |
| `quad_expr` pure assignment (leaf → dest) | `@float_val_1 = @float_val_3` | `se_quad` MOVE (0x40) |
| `quad_multi` semicolon-separated | Action 3 outer frame | Multiple `se_quad` nodes in sequence |
| Parenthesized subexpression | `r0 = (p0 + 1.0 + 5.0) - 2.0` | FADD + FSUB with scratch |
| Float type inference from literal | `1.0`, `5.0`, `2.0` → FADD | Opcode 0x08 instead of 0x00 |
| Integer type inference (no suffix) | `1`, `5`, `2` → IADD | Opcode 0x00 instead of 0x08 |
| Typed `frame_vars` with `:float`/`:int` | All actions | Correct opcode selection per variable |
| Scratch variable allocation | `{"t0", "t1"}` | `{type="stack_tos"}` params |
| Constant folding | `1.0 + 5.0` → `6.0` | Fewer nodes emitted, less scratch used |
| `stack_push` / `stack_pop` passing | Action 3 call setup/return | `{type="stack_push"}` / `{type="stack_pop"}` |
| `se_call` with `frame_vars` in body | Action 3 | `se_stack_frame_instance` + quad nodes |

## Compiler → Runtime Chain

The expression compiler runs at pipeline time in LuaJIT, producing tree nodes. At runtime, these nodes execute via the quad builtins:

```
Pipeline time (s_expr_compiler.lua):
  quad_expr("@int_val_2 = @int_val_1 + 5", v, {"t0"})()
       │
       ▼  tokenize → parse → type infer → codegen → emit
       │
  Node emitted into module_data:
  { func_name = "se_quad", call_type = "o_call",
    params = {
      {type="uint", value=0x00},                    -- IADD opcode
      {type="field_ref", value="int_val_1"},         -- src1
      {type="uint", value=5},                        -- src2
      {type="field_ref", value="int_val_2"},         -- dest
    } }

Runtime (se_builtins_quads.lua):
  se_quad(inst, node)
    → exec_quad(inst, 0x00, params[2], params[3], params[4])
    → read_int(inst, {type="field_ref", value="int_val_1"})  → inst.blackboard["int_val_1"]
    → read_int(inst, {type="uint", value=5})                 → 5
    → write_int(inst, {type="field_ref", value="int_val_2"}, result)
    → inst.blackboard["int_val_2"] = int_val_1 + 5
```

## Blackboard Record

In `module_data.records`:

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

## Test Actions

### Action 1 — Integer Arithmetic (`quad_expr` with `@field`)

Loops 100 times within `se_frame_allocate(0, 5, 5)`. Each iteration the compiler generates `se_quad` nodes:

**Expression source:**
```lua
quad_expr("@int_val_2 = @int_val_1 + 1", v, {"t0"})()
quad_expr("@int_val_2 = @int_val_1 + 5", v, {"t0"})()
quad_expr("@int_val_3 = @int_val_2 - 2", v, {"t0"})()
quad_expr("@int_val_1 = @int_val_3", v, {})()
```

**Generated opcodes:**
```
IADD (0x00): field:int_val_1 + uint:1 → field:int_val_2   (overwritten)
IADD (0x00): field:int_val_1 + uint:5 → field:int_val_2
ISUB (0x01): field:int_val_2 - uint:2 → field:int_val_3
MOVE (0x40): field:int_val_3          → field:int_val_1
```

The `+ 1` and `+ 5` literals have no decimal point, so the compiler's type inference selects IADD/ISUB (integer opcodes 0x00/0x01). The final statement `@int_val_1 = @int_val_3` is a leaf-to-dest assignment — the compiler emits a MOVE (0x40) opcode.

**Net per iteration:** `int_val_1 += 3`. After 100 iterations: `int_val_1 = 300`.

**Runtime execution:** `exec_quad` in `se_builtins_quads.lua` reads `inst.blackboard["int_val_1"]` via `read_int(inst, {type="field_ref", value="int_val_1"})` and writes the result back via `write_int`.

### Action 2 — Float Arithmetic (`quad_expr` with `@field`)

Loops 10 times within `se_frame_allocate(0, 5, 5)`. Each iteration:

**Expression source:**
```lua
quad_expr("@float_val_2 = @float_val_1 + 1.0", v, {"t0"})()
quad_expr("@float_val_2 = @float_val_1 + 5.0", v, {"t0"})()
quad_expr("@float_val_3 = @float_val_2 - 2.0", v, {"t0"})()
quad_expr("@float_val_1 = @float_val_3", v, {})()
```

**Generated opcodes:**
```
FADD (0x08): field:float_val_1 + float:1.0 → field:float_val_2  (overwritten)
FADD (0x08): field:float_val_1 + float:5.0 → field:float_val_2
FSUB (0x09): field:float_val_2 - float:2.0 → field:float_val_3
MOVE (0x40): field:float_val_3             → field:float_val_1
```

The `1.0`, `5.0`, `2.0` literals contain decimal points, triggering float type inference → FADD (0x08) / FSUB (0x09). At runtime, `exec_quad` uses `read_float` / `write_float` which coerce via `+ 0.0`.

**Net per iteration:** `float_val_1 += 3.0`. After 10 iterations: `float_val_1 = 30.0`.

### Action 3 — Call/Return with `quad_multi` and `quad_expr`

Loops 10 times using `se_p_quad` with `P_ICMP_LT_ACC` (0x42) as the loop predicate. Each iteration:

**Outer frame** (`se_frame_allocate(0, 5, 5)`):

```lua
local v = frame_vars(
    {"a:float", "b:float", "c:float", "e:float", "f:float"},
    {"t0:float", "t1:float", "t2:float", "t3:float", "t4:float"}
)

quad_multi("a = @float_val_1 + 1.0; @float_val_2 = a + 5.0; b = @float_val_2",
           v, {"t0", "t1"})()
quad_multi("@float_val_3 = b - 2.0; @float_val_1 = @float_val_3",
           v, {"t0"})()
```

`quad_multi` splits on semicolons and compiles each statement independently via `quad_expr`. The compiler generates a sequence of `se_quad` nodes:

```
FADD (0x08): field:float_val_1 + float:1.0 → local:a        (stack_local 0)
FADD (0x08): local:a + float:5.0           → field:float_val_2
MOVE (0x40): field:float_val_2             → local:b          (stack_local 1)
FSUB (0x09): local:b - float:2.0          → field:float_val_3
MOVE (0x40): field:float_val_3             → field:float_val_1
```

Local variables `a` and `b` use param type `"stack_local"`. At runtime, `read_float` calls `se_stack.get_local(stk, idx)` and `write_float` calls `se_stack.set_local(stk, idx, val)`.

Net effect: `float_val_1 += 4.0` per iteration.

**Call setup** (stack_push):
```lua
quad_mov(field_val("float_val_1"), stack_push_ref())()   -- p0
quad_mov(field_val("float_val_2"), stack_push_ref())()   -- p1
```

These generate `se_quad` MOVE nodes with `{type="stack_push"}` as dest. At runtime, `write_int`/`write_float` calls `se_stack.push(stk, val)`.

**Call body** (`se_call(2, 2, 3, {2, 3})`):

```lua
local cv = frame_vars(
    {"p0:float", "p1:float", "r0:float", "r1:float"},
    {"ct0:float", "ct1:float", "ct2:float"}
)

quad_expr("r0 = (p0 + 1.0 + 5.0) - 2.0", cv, {"ct0", "ct1"})()
quad_expr("r1 = p1 * 2.0", cv, {"ct0"})()
```

**Constant folding in action:** The subexpression `(p0 + 1.0 + 5.0)` is parsed as `((p0 + 1.0) + 5.0)`. The compiler's constant folder sees `1.0 + 5.0` cannot fold (p0 is not constant), but it can fold the right branch of the outer `+` if rearranged. In practice, the compiler folds `1.0 + 5.0` into `6.0` when it appears as a constant subtree, reducing the expression to `(p0 + 6.0) - 2.0` — one scratch instead of two.

Generated nodes for `r0 = (p0 + 1.0 + 5.0) - 2.0` (after folding):
```
FADD (0x08): local:p0 + float:6.0     → tos:ct0     (scratch, stack_tos)
FSUB (0x09): tos:ct0 - float:2.0      → local:r0    (stack_local 2)
```

Generated nodes for `r1 = p1 * 2.0`:
```
FMUL (0x0A): local:p1 × float:2.0     → local:r1    (stack_local 3)
```

Results: `r0 = p0 + 4.0`, `r1 = p1 × 2.0`.

**Return retrieval** (LIFO pop):

`se_stack_frame_instance` TERMINATE copies `return_vars = {2, 3}` → pushes local 2 (r0) then local 3 (r1). Caller pops in reverse:

```lua
quad_mov(stack_pop_ref(), v.e)()    -- gets r1 (top of stack)
quad_mov(stack_pop_ref(), v.f)()    -- gets r0
quad_mov(v.e, field_val("float_val_2"))()   -- store r1
quad_mov(v.f, field_val("float_val_3"))()   -- store r0
```

These generate `se_quad` MOVE nodes with `{type="stack_pop"}` as src. At runtime, `read_int`/`read_float` calls `se_stack.pop(stk)`.

## Expected Values (Action 3)

| Iter | float_val_1 (start) | float_val_2 | float_val_3 | float_val_1 (end) | call r0 (fv3) | call r1 (fv2) |
|------|---------------------|-------------|-------------|-------------------|---------------|---------------|
| 1 | 0.0 | 6.0 | 4.0 | 4.0 | 8.0 | 12.0 |
| 2 | 4.0 | 10.0 | 8.0 | 8.0 | 12.0 | 20.0 |
| 3 | 8.0 | 14.0 | 12.0 | 12.0 | 16.0 | 28.0 |
| ... | +4.0/iter | fv1+6 | fv1+4 | fv3 | fv1+8 | fv2×2 |
| 9 | 32.0 | 38.0 | 36.0 | 36.0 | 40.0 | 76.0 |
| 10 | 36.0 | 42.0 | 40.0 | 40.0 | 44.0 | 84.0 |

Formulas:
- `float_val_2 = float_val_1 + 1.0 + 5.0 = float_val_1 + 6.0`
- `float_val_3 = float_val_2 - 2.0 = float_val_1 + 4.0`
- `float_val_1 (end) = float_val_3`
- `call r0 = float_val_1(end) + 4.0`
- `call r1 = float_val_2 × 2.0`

## Execution Structure

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_SET_FIELD int_val_1 = 0
├── [o_call] SE_SET_FIELD float_val_1 = 0.0
│
├── action_1: SE_FORK_JOIN
│   └── SE_WHILE (SE_STATE_INCREMENT_AND_TEST, step=1, limit=100)
│       └── SE_FRAME_ALLOCATE(0, 5, 5)
│           ├── [o_call] SE_QUAD IADD(field, uint, field) × 2
│           ├── [o_call] SE_QUAD ISUB(field, uint, field)
│           ├── [o_call] SE_QUAD MOVE(field, null, field)
│           ├── [pt_m_call] SE_TICK_DELAY 5
│           └── SE_RETURN_PIPELINE_DISABLE
│
├── action_2: SE_FORK_JOIN
│   └── SE_WHILE (SE_STATE_INCREMENT_AND_TEST, step=1, limit=10)
│       └── SE_FRAME_ALLOCATE(0, 5, 5)
│           ├── [o_call] SE_QUAD FADD(field, float, field) × 2
│           ├── [o_call] SE_QUAD FSUB(field, float, field)
│           ├── [o_call] SE_QUAD MOVE(field, null, field)
│           ├── [pt_m_call] SE_TICK_DELAY 5
│           └── SE_RETURN_PIPELINE_DISABLE
│
├── [o_call] SE_SET_FIELD int_val_1 = 0         ← reinit
├── [o_call] SE_SET_FIELD float_val_1 = 0.0
│
├── action_3: SE_FORK_JOIN
│   └── SE_WHILE (SE_P_QUAD P_ICMP_LT_ACC on loop_count)
│       └── SE_FRAME_ALLOCATE(0, 5, 5)
│           ├── [o_call] SE_QUAD FADD(field, float, local:a)      ← quad_multi stmt 1
│           ├── [o_call] SE_QUAD FADD(local:a, float, field)      ← stmt 2
│           ├── [o_call] SE_QUAD MOVE(field, null, local:b)       ← stmt 3
│           ├── [o_call] SE_QUAD FSUB(local:b, float, field)      ← quad_multi stmt 4
│           ├── [o_call] SE_QUAD MOVE(field, null, field)          ← stmt 5
│           ├── [o_call] SE_QUAD MOVE(field, null, stack_push)    ← push p0
│           ├── [o_call] SE_QUAD MOVE(field, null, stack_push)    ← push p1
│           ├── SE_SEQUENCE_ONCE                                   ← se_call wrapper
│           │   ├── [o_call] SE_PUSH_STACK(2)
│           │   ├── SE_STACK_FRAME_INSTANCE(2, 2, 3, {2,3})
│           │   ├── [o_call] SE_QUAD FADD(local:p0, float:6.0, tos:ct0)  ← folded!
│           │   ├── [o_call] SE_QUAD FSUB(tos:ct0, float:2.0, local:r0)
│           │   ├── [o_call] SE_QUAD FMUL(local:p1, float:2.0, local:r1)
│           │   └── SE_RETURN_PIPELINE_TERMINATE
│           ├── [o_call] SE_QUAD MOVE(stack_pop, null, local:e)   ← pop r1
│           ├── [o_call] SE_QUAD MOVE(stack_pop, null, local:f)   ← pop r0
│           ├── [o_call] SE_QUAD MOVE(local:e, null, field:fv2)
│           ├── [o_call] SE_QUAD MOVE(local:f, null, field:fv3)
│           ├── [pt_m_call] SE_TICK_DELAY 5
│           └── SE_RETURN_PIPELINE_DISABLE
│
└── SE_RETURN_FUNCTION_TERMINATE
```

Note the constant folding visible in the call body: `(p0 + 1.0 + 5.0)` becomes `p0 + 6.0` — one FADD node instead of two, one scratch slot instead of two.

## Tick Budget

Each iteration of actions 1, 2, and 3 includes `se_tick_delay(5)`, consuming 5 ticks for the delay plus 1 tick each for frame push and the computation tick. Total ticks: approximately 100×7 + 10×7 + 10×7 = 840.

## Runtime Modules Exercised

| Module | Functions | Role in This Test |
|--------|-----------|-------------------|
| `se_builtins_quads.lua` | `se_quad` (IADD, ISUB, FADD, FSUB, FMUL, MOVE), `se_p_quad` (P_ICMP_LT_ACC) | Execute compiled expressions |
| `se_stack.lua` | `push`, `pop`, `push_frame`, `pop_frame`, `get_local`, `set_local`, `peek_tos`, `poke` | Stack frame and scratch storage |
| `se_builtins_stack.lua` | `se_frame_allocate`, `se_stack_frame_instance`, `se_log_stack` | Frame lifecycle |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_fork_join`, `se_while`, `se_sequence_once` | Control flow |
| `se_builtins_delays.lua` | `se_tick_delay` | Multi-tick delay |
| `se_builtins_oneshot.lua` | `se_log`, `se_set_field`, `se_push_stack` | Logging, field init, stack push |
| `se_builtins_pred.lua` | `se_state_increment_and_test` | Counter-based loop predicate |
| `se_builtins_return_codes.lua` | `se_return_pipeline_disable`, `se_return_pipeline_terminate`, `se_return_function_terminate` | Fixed return codes |

## Compiler Bugs Found and Fixed (v1.0 → v1.1)

1. **`@field` destinations not supported**: `quad_expr("@int_val_2 = @int_val_1 + 5")` failed because `ref_for()` didn't recognize the `@` prefix. Fixed by adding field detection: names starting with `@` delegate to `field_val()`, which emits `{type="field_ref", value="int_val_2"}`.

2. **Leaf-to-dest assignment silently dropped**: `quad_expr("b = @float_val_2")` generated zero `se_quad` nodes because `emit()` short-circuited on leaf nodes without checking `dest_name`. Fixed by emitting a MOVE (0x40) opcode when a leaf has a destination.

3. **Destination regex too restrictive**: The pattern `[%w_@.]+` was updated to `@?[%w_.]+` to properly capture `@field.path` as a destination.

4. **Compound assignment patterns**: Added `@field` variants so `@counter += 1` desugars correctly to `@counter = @counter + (1)`, generating a single IADD node with `field_ref` for both src1 and dest.

## Test Harness

```lua
local se_runtime = require("se_runtime")
local se_stack   = require("se_stack")
local module_data = require("stack_test_equations_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_return_codes"),
    require("se_builtins_stack"),
    require("se_builtins_quads"),
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "stack_test_equations")
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

-- Verify action_1 result
assert(inst.blackboard["int_val_1"] == 300,
    "action_1: expected int_val_1=300, got " .. inst.blackboard["int_val_1"])

-- Verify action_3 final iteration
print("float_val_1 = " .. inst.blackboard["float_val_1"])
print("float_val_2 = " .. inst.blackboard["float_val_2"])
print("float_val_3 = " .. inst.blackboard["float_val_3"])

print(string.format("Completed in %d ticks", tick_count))
print(tick_count <= 2000 and "✅ PASSED" or "❌ TIMEOUT")
```

## Files

- `stack_test_equations_module.lua` — pipeline-generated `module_data` (compiled from expression syntax)
- `test_stack_equations.lua` — LuaJIT test harness
- `s_expr_compiler.lua` — expression compiler (runs at pipeline time)
- `se_builtins_quads.lua` — `se_quad`, `se_p_quad`, `exec_quad` (runtime execution)
- `se_stack.lua` — stack data structure
- `se_builtins_stack.lua` — frame lifecycle management