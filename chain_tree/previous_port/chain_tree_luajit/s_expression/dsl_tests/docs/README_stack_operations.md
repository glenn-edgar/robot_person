# Stack Frame and Quad Operations — DSL & Runtime Reference (LuaJIT)

## Theory of Operation

The S-Expression Engine executes behavior trees tick-by-tick. Each tick traverses the tree, invoking nodes according to their type. Stack frame management and quad operations integrate into this tick-driven model to provide local variables, scratch space, function calls with parameter passing, and three-address arithmetic — all implemented as pure Lua table operations in the LuaJIT runtime.

### Tick-Based Execution Model

A single tick proceeds as follows:

1. The caller invokes `se_runtime.tick_once(inst, SE_EVENT_TICK, nil)`.
2. `invoke_main` dispatches the root node (typically `se_function_interface`).
3. `se_function_interface` iterates its active children, invoking each via `child_invoke`.
4. Each child returns a result code that determines its fate:
   - **APPLICATION codes (0–5):** Propagated immediately to the caller, ending the tick.
   - **FUNCTION codes (6–11):** Propagated immediately to the caller, ending the tick.
   - **PIPELINE codes (12–17):** Handled internally (continue, halt, disable, terminate, reset, skip).
5. Active children that return `SE_PIPELINE_CONTINUE` or `SE_PIPELINE_HALT` remain active for the next tick.
6. Children returning `SE_PIPELINE_DISABLE` or `SE_PIPELINE_TERMINATE` are terminated and removed.
7. When no active children remain, `se_function_interface` returns `SE_FUNCTION_DISABLE`.

Within a single tick, `se_frame_allocate` pushes a stack frame before executing its children and pops it after. This means local variables and scratch space exist only for the duration of that one tick — they are recreated on every tick. Persistent state lives in the blackboard (record fields) or in node state tables.

### Three-Layer Result Code Architecture

Result codes are organized into three propagation layers:

| Range | Layer | Scope |
|-------|-------|-------|
| 0–5 | APPLICATION | Exits the entire tree |
| 6–11 | FUNCTION | Exits current function boundary |
| 12–17 | PIPELINE | Internal to parent node only |

Each layer has the same six outcomes: CONTINUE, HALT, TERMINATE, RESET, DISABLE, SKIP_CONTINUE. The layer determines how far up the tree the result propagates.

### Stack Frame Lifecycle

Stack frames are transient within a tick. The frame lifecycle for `se_frame_allocate`:

```
TICK START
  ├── se_stack.push_frame(stk, num_params, num_locals)
  ├── push scratch slots (zeroed): se_stack.push_int(stk, 0) × scratch_depth
  ├── execute children (quads, control flow, calls)
  ├── se_stack.pop_frame(stk)  (restores SP to pre-frame position)
  └── return result
TICK END
```

For `se_call` (via `se_stack_frame_instance`), the lifecycle spans multiple ticks:

```
TICK N (INIT):     se_stack.pop(stk) to get param count,
                   se_stack.push_frame(stk, num_params, num_locals)
TICK N+1..M:       children execute with frame active
TICK M+1 (TERM):   copy return vars to temp, pop_frame, push returns
```

---

## Stack Architecture

### Implementation: `se_stack.lua`

The stack is a Lua table with 1-based internal indexing:

```lua
local stk = se_stack.new_stack(capacity)
-- stk.data = {}         -- 1-based array of values
-- stk.sp = 0            -- next free slot (0 = empty)
-- stk.capacity = N
-- stk.frames = {}       -- 1-based array of frame records
-- stk.frame_count = 0
```

Stack entries are plain Lua values (numbers, strings, nil) — not typed param structs as in C. The type distinction (int vs float) is handled by the quad read/write functions, not by the stack itself.

### Frame Layout

When a stack frame is created, the stack region is organized as:

```
base_ptr → [param 0] [param 1] ... [param N-1]   ← already on stack
           [local 0] [local 1] ... [local M-1]    ← zeroed on push_frame
           [scratch 0] [scratch 1] ...             ← TOS-relative
                                              ← SP (grows upward)
```

The frame record stored in `stk.frames[frame_count]` tracks:

```lua
{
    base_ptr     = base_ptr,      -- index below first param
    num_params   = num_params,
    num_locals   = num_locals,
    scratch_base = stk.sp,        -- SP after locals (scratch starts here)
    saved_sp     = stk.sp,        -- for pop restoration
}
```

### Addressing Modes

| Mode | API | Addressing | Lifetime |
|------|-----|------------|----------|
| `stack_local` | `se_stack.get_local(stk, idx)` / `set_local(stk, idx, v)` | `base_ptr + num_params + idx + 1` (1-based) | Persistent across ticks (`se_call` only) |
| `stack_tos` | `se_stack.peek_tos(stk, offset)` / `poke(stk, offset, v)` | `sp - offset` (0 = top) | Within current tick only |
| `stack_push` | `se_stack.push(stk, value)` | `++sp; data[sp] = value` | Until consumed |
| `stack_pop` | `se_stack.pop(stk)` | `value = data[sp]; sp--` | Destructive read |
| `stack_param` | `se_stack.get_param(stk, idx)` | `base_ptr + idx + 1` (1-based) | Within frame lifetime |

### Parameter Types in node.params

Quad operands in `node.params` carry a `type` string that the runtime dispatches on:

| Param Type | Description |
|-----------|-------------|
| `"stack_tos"` | Read/write relative to stack top; `value` = offset |
| `"stack_local"` | Read/write relative to frame base; `value` = local index |
| `"stack_push"` | Write destination: push onto stack |
| `"stack_pop"` | Read source: pop from stack |
| `"field_ref"` | Read/write blackboard field; `value` = field name |
| `"int"` | Integer literal; `value` = number |
| `"uint"` | Unsigned integer literal; `value` = number |
| `"float"` | Float literal; `value` = number |
| `"const_ref"` | ROM constant; `value` = constants table key |

---

## DSL Functions

### se_frame_allocate(num_params, num_locals, scratch_depth, ...)

Allocates a stack frame per-tick around child nodes. The frame is pushed at the start of each tick and popped at the end, so locals and scratch are volatile across ticks.

**DSL:**
```lua
se_frame_allocate(0, 5, 5, function()
    local v = frame_vars({"a", "b", "c", "d", "e"}, {"t0", "t1", "t2", "t3", "t4"})
    quad_iadd(field_val("x"), int_val(1), v.a)()
end)
```

**Parameters:**
- `num_params` — Parameters already on stack (usually 0 for top-level frames)
- `num_locals` — Local variable slots to allocate (zeroed each tick)
- `scratch_depth` — Scratch slots pushed above locals
- `...` — Child functions to execute within the frame

**LuaJIT Runtime (`se_builtins_stack.lua`):**

On each TICK:

```lua
-- 1. Push stack frame
assert(se_stack.push_frame(stk, num_params, num_locals),
    "se_frame_allocate: stack push failed")

-- 2. Push scratch slots (zeroed)
for _ = 1, scratch_depth do
    se_stack.push_int(stk, 0)
end

-- 3. Iterate children
for i = 1, #children do
    local child = children[i]
    local ct = child.call_type

    -- Oneshot: fire and terminate (don't count as active)
    if ct == "o_call" or ct == "io_call" then
        invoke_oneshot(inst, child)
        child_terminate(inst, node, i - 1)

    -- Pred: evaluate and terminate (don't count as active)
    elseif ct == "p_call" or ct == "p_call_composite" then
        invoke_pred(inst, child)
        child_terminate(inst, node, i - 1)

    -- Main: invoke and handle pipeline result
    else
        local r = invoke_any(inst, child, event_id, event_data)
        -- ... handle result codes (see full implementation) ...
    end
end

-- 4. Pop stack frame
se_stack.pop_frame(stk)
return (active_count == 0) and SE_PIPELINE_DISABLE or SE_PIPELINE_CONTINUE
```

On TERMINATE: terminates all children, does not touch the stack.

On INIT: returns `SE_PIPELINE_CONTINUE` (no frame action).

**Critical detail:** Because the frame is pushed and popped every tick, local variables do not persist. Use blackboard fields for state that must survive across ticks.

### se_call(num_params, num_locals, scratch_depth, return_vars, body_fns)

Function call with parameter passing via the stack and return value retrieval. Creates a persistent frame that lives across multiple ticks.

**DSL:**
```lua
-- Push parameters before the call
quad_mov(field_val("x"), stack_push_ref())()
quad_mov(field_val("y"), stack_push_ref())()

-- Call with 2 params, 2 locals, 3 scratch, return locals 2 and 3
se_call(2, 2, 3, {2, 3}, {
    function()
        local cv = frame_vars({"p0", "p1", "r0", "r1"}, {"t0", "t1", "t2"})
        quad_fadd(cv.p0, cv.p1, cv.r0)()
        quad_fmul(cv.p0, float_val(2.0), cv.r1)()
    end
})

-- Pop return values (reverse order — last in return_vars is on top)
quad_mov(stack_pop_ref(), local_dest_1)()
quad_mov(stack_pop_ref(), local_dest_0)()
```

**Parameters:**
- `num_params` — Number of values already pushed onto the stack
- `num_locals` — Additional local slots (zeroed on init)
- `scratch_depth` — Compile-time scratch depth (for validation only)
- `return_vars` — List of local indices whose values are returned to caller
- `body_fns` — Table of functions forming the call body

**How it works:**

`se_call` emits the following tree structure:

```
se_sequence_once
  ├── se_push_stack(num_params)       ← pushes param count marker
  ├── se_stack_frame_instance(...)    ← manages frame lifecycle
  └── body_fn children                ← user code
```

### se_stack_frame_instance (low-level)

The runtime node that manages the call frame lifecycle. Not typically called directly — `se_call` wraps it.

**LuaJIT Runtime (`se_builtins_stack.lua`):**

On INIT:

```lua
-- 1. Pop the parameter count marker from the stack
local passed = se_stack.pop(stk) or 0

-- 2. Validate it matches expected num_params
if passed ~= num_params then
    error(string.format(
        "se_stack_frame_instance: param mismatch: expected %d got %d",
        num_params, passed))
end

-- 3. Push frame (params are already on the stack)
assert(se_stack.push_frame(stk, num_params, num_locals),
    "se_stack_frame_instance: frame push failed")

-- 4. Set node state to 1 (frame active)
set_state(inst, node, 1)
return SE_PIPELINE_CONTINUE
```

On TICK: Returns `SE_PIPELINE_CONTINUE` (frame stays active).

On TERMINATE:

```lua
if get_state(inst, node) == 1 then
    -- 1. Collect return var values before frame is destroyed
    local ret_list = (node.params or {})[4]
    if ret_list and ret_list.type == "list_start" then
        local temps = {}
        for _, rp in ipairs(ret_list.items or {}) do
            local local_idx = rp.value
            temps[#temps + 1] = se_stack.get_local(stk, local_idx)
        end
        -- 2. Pop the frame (restores SP to caller's position)
        se_stack.pop_frame(stk)
        -- 3. Push return values from temp buffer
        for _, v in ipairs(temps) do
            se_stack.push(stk, v)
        end
    else
        se_stack.pop_frame(stk)
    end
end
set_state(inst, node, 0)
return SE_PIPELINE_CONTINUE
```

Return values are pushed in list order, so `{2, 3}` pushes local 2 first, then local 3. The caller pops in reverse: first `stack_pop` gets local 3 (top), second gets local 2.

### se_sequence_once(...)

Executes all children in sequence within a single tick, then disables itself.

**DSL:**
```lua
se_sequence_once(
    function() quad_mov(int_val(0), field_val("x"))() end,
    function() quad_iadd(field_val("x"), int_val(1), field_val("y"))() end
)
```

**LuaJIT Runtime (`se_builtins_flow_control.lua`):**

On TICK:
1. Iterates all children in order
2. Oneshots and preds: invoke and continue
3. Main nodes: invoke; break if result is not `SE_PIPELINE_CONTINUE` or `SE_PIPELINE_DISABLE`
4. After all children execute, terminates all initialized children
5. Returns `SE_PIPELINE_DISABLE`

On TERMINATE: Terminates all initialized children, resets state.

On INIT: Sets `ns.state = 0`.

This node is used internally by `se_call` to ensure the frame body and `se_stack_frame_instance` execute together, with proper terminate sequencing.

### se_function_interface(body_fn)

Top-level function entry point. Manages the lifecycle of all children as a fork-join with function-level result handling.

**DSL:**
```lua
se_function_interface(function()
    action_1()
    action_2()
    se_return_terminate()
end)
```

**LuaJIT Runtime (`se_builtins_flow_control.lua`):**

On INIT: Sets `ns.state = FORK_STATE_RUNNING`, resets all callable children.

On TICK:
1. Iterates active children
2. APPLICATION/FUNCTION results (0–11): propagated immediately, tick ends
3. PIPELINE results handled internally:
   - CONTINUE/HALT → child stays active, `active_count++`
   - DISABLE/TERMINATE → child terminated
   - RESET → child terminated then reset, `active_count++`
   - SKIP_CONTINUE → `active_count++`, break loop
4. When `active_count == 0`, returns `SE_FUNCTION_DISABLE`

On TERMINATE: Terminates all children via `children_terminate_all`.

### frame_vars(locals, scratch)

Compile-time helper that creates named references to stack frame slots. Each declaration supports optional type annotations for the expression compiler's type inference.

**DSL:**
```lua
local v = frame_vars({"a:float", "b:int", "c"}, {"t0:float", "t1"})
-- v.a = closure emitting stack_local(0)     v.a_type = "float"
-- v.b = closure emitting stack_local(1)     v.b_type = "int"
-- v.c = closure emitting stack_local(2)     v.c_type = "int" (default)
-- v.t0 = closure emitting stack_tos(1)      v.t0_type = "float"
-- v.t1 = closure emitting stack_tos(0)      v.t1_type = "int" (default)
-- v._local_count = 3
-- v._scratch_count = 2
```

Returns a table of closure functions, each emitting the appropriate parameter type when called. These closures are used as arguments to quad operations and as the `vars` parameter to `quad_expr` / `quad_pred`.

**TOS indexing note:** Scratch variables are addressed from the top of the stack downward. The last scratch in the list is TOS offset 0 (top), the first is at the highest offset. This matches the C convention where scratch slots are pushed in order and accessed via TOS-relative offsets.

### se_log_stack()

Debug utility that prints the current stack state.

**DSL:**
```lua
se_log_stack()
```

**LuaJIT Runtime (`se_builtins_stack.lua`):** Prints capacity, free space, stack pointer, frame count, and current frame details (base_ptr, num_params, num_locals, scratch_base).

```lua
M.se_log_stack = function(inst, node)
    local stk = inst.stack
    if not stk then
        print("SE_LOG_STACK: no stack on instance")
        return
    end
    print(string.format("SE_LOG_STACK: stack capacity = %d", stk.capacity))
    print(string.format("SE_LOG_STACK: stack free space = %d", stk.capacity - stk.sp))
    print(string.format("SE_LOG_STACK: stack stack pointer = %d", stk.sp))
    print(string.format("SE_LOG_STACK: stack frame count = %d", stk.frame_count))
    -- ... frame details if frame_count > 0 ...
end
```

### se_frame_free (low-level)

Pops the top stack frame on `SE_EVENT_INIT` only. All other events return `SE_PIPELINE_CONTINUE`. This mirrors a quirk in the C implementation where the TERMINATE branch is unreachable.

```lua
M.se_frame_free = function(inst, node, event_id, event_data)
    if event_id ~= SE_EVENT_INIT then
        return SE_PIPELINE_CONTINUE
    end
    if inst.stack then
        se_stack.pop_frame(inst.stack)
    end
    return SE_PIPELINE_CONTINUE
end
```

---

## Quad Operations

### Architecture

Quad operations are three-address instructions: `dest = op(src1, src2)`. They execute as oneshot nodes (`se_quad`, call_type `o_call`) — fire once per activation, no persistent state. Predicate variants (`se_p_quad`, call_type `p_call`) return a boolean.

Each quad node has four params:

```lua
params = {
    { type = "uint", value = opcode },   -- params[1]: operation code
    { type = ...,    value = ... },       -- params[2]: src1 operand
    { type = ...,    value = ... },       -- params[3]: src2 operand (or unused for unary)
    { type = ...,    value = ... },       -- params[4]: dest operand
}
```

**DSL core function:**
```lua
se_quad(opcode, src1_fn, src2_fn, dest_fn)
```

All four arguments are closure functions that emit parameters when called (the deferred emission pattern). The helpers return a closure that must be invoked with `()`:

```lua
quad_fadd(field_val("x"), float_val(1.0), local_ref(0))()
--                                                      ^^ fires the closure
```

### Parameter Factories

| Factory | Emits (param type) | Description |
|---------|--------------------|-------------|
| `field_val(name)` | `"field_ref"` | Blackboard field by name |
| `local_ref(idx)` | `"stack_local"` | Frame local by 0-based index |
| `tos_ref(offset)` | `"stack_tos"` | Scratch by TOS offset (0 = top) |
| `int_val(v)` | `"int"` | Signed integer constant |
| `uint_val(v)` | `"uint"` | Unsigned integer constant |
| `float_val(v)` | `"float"` | Float constant |
| `const_val(name)` | `"const_ref"` | Constants table reference |
| `hash_val(s)` | `"str_hash"` | FNV-1a hash of string |
| `null_val()` | — | Null/unused (for unary ops) |
| `stack_push_ref()` | `"stack_push"` | Write destination: push onto stack |
| `stack_pop_ref()` | `"stack_pop"` | Read source: pop from stack |

### LuaJIT Runtime Read/Write

The `read_int` and `read_float` functions in `se_builtins_quads.lua` dispatch on the param type to read operand values:

```lua
local function read_int(inst, p)
    if not p then return 0 end
    local t = p.type
    if t == "int" or t == "uint" then return p.value
    elseif t == "float"             then return math.floor(p.value)
    elseif t == "field_ref" or t == "nested_field_ref" then
        return inst.blackboard[p.value] or 0
    elseif t == "stack_tos" then
        return se_stack.peek_tos(inst.stack, p.value or 0) or 0
    elseif t == "stack_local" then
        return se_stack.get_local(inst.stack, p.value or 0) or 0
    elseif t == "stack_pop" then
        return se_stack.pop(inst.stack) or 0
    elseif t == "const_ref" then
        local consts = inst.mod.module_data and inst.mod.module_data.constants
        if consts and p.value then
            local v = consts[p.value]
            return type(v) == "number" and math.floor(v) or 0
        end
        return 0
    end
    return 0
end
```

`read_float` follows the same pattern but coerces to float (`+ 0.0`).

**Write dispatch (`write_int` / `write_float`):**

| Param Type | Action |
|-----------|--------|
| `"field_ref"` | `inst.blackboard[p.value] = val` |
| `"stack_tos"` | `se_stack.poke(inst.stack, p.value, val)` |
| `"stack_local"` | `se_stack.set_local(inst.stack, p.value, val)` |
| `"stack_push"` | `se_stack.push(inst.stack, val)` — increments SP |

### Comparison with C Read/Write

| C Pattern | LuaJIT Equivalent |
|-----------|-------------------|
| `(type*)((uint8_t*)blackboard + field_offset)` | `inst.blackboard[p.value]` (string key) |
| `s_expr_stack_peek_tos(stack, offset)` | `se_stack.peek_tos(stk, offset)` |
| `s_expr_stack_get_local(stack, index)` | `se_stack.get_local(stk, index)` |
| `s_expr_stack_push(stack, &param)` | `se_stack.push(stk, value)` |
| `module->constants[index]` | `inst.mod.module_data.constants[key]` |

The key difference: C stores typed `s_expr_param_t` values (8/16 bytes with type tag) on the stack. LuaJIT stores plain Lua values (numbers). Type distinction is handled by the quad opcode selection (int ops vs float ops), not by the stack storage.

### Quad Execution

The `exec_quad` function in `se_builtins_quads.lua` is a large opcode dispatch:

```lua
local function exec_quad(inst, opcode, src1p, src2p, destp)
    local i1, i2, f1, f2, r

    -- Integer arithmetic
    if     opcode == 0x00 then  -- IADD
        i1 = read_int(inst, src1p); i2 = read_int(inst, src2p)
        r = i1 + i2; write_int(inst, destp, r); return r
    elseif opcode == 0x01 then  -- ISUB
        i1 = read_int(inst, src1p); i2 = read_int(inst, src2p)
        r = i1 - i2; write_int(inst, destp, r); return r

    -- Float arithmetic
    elseif opcode == 0x08 then  -- FADD
        f1 = read_float(inst, src1p); f2 = read_float(inst, src2p)
        write_float(inst, destp, f1 + f2)
        return (f1 + f2 ~= 0) and 1 or 0

    -- Bitwise (via LuaJIT bit.* library)
    elseif opcode == 0x10 then  -- BIT_AND
        i1 = read_int(inst, src1p); i2 = read_int(inst, src2p)
        r = bit.band(i1, i2); write_int(inst, destp, r); return r

    -- ... 60+ more opcodes ...
    end
    error(string.format("se_quad: unknown opcode 0x%02x", opcode))
end
```

Bitwise operations use LuaJIT's `bit.*` library (`bit.band`, `bit.bor`, `bit.bxor`, `bit.bnot`, `bit.lshift`, `bit.rshift`), which operate on 32-bit signed integers. Shift amounts are masked to 5 bits (`band(shift, 0x1F)`).

Float math functions use Lua's `math.*` library. Hyperbolic functions (`sinh`, `cosh`, `tanh`) are computed manually since LuaJIT doesn't provide them:

```lua
-- FSINH (0x60):
local e = math.exp(f1); local v = (e - 1/e) / 2
-- FCOSH (0x61):
local e = math.exp(f1); local v = (e + 1/e) / 2
-- FTANH (0x62):
local e = math.exp(2 * f1); local v = (e - 1) / (e + 1)
```

### SE_QUAD Oneshot Entry Point

```lua
M.se_quad = function(inst, node)
    local params = node.params or {}
    assert(#params >= 4, "se_quad: requires 4 params (opcode, src1, src2, dest)")
    exec_quad(inst, params[1].value, params[2], params[3], params[4])
end
```

### SE_P_QUAD Predicate Entry Point

```lua
M.se_p_quad = function(inst, node)
    local params = node.params or {}
    assert(#params >= 4, "se_p_quad: requires 4 params")
    local opcode = params[1].value

    -- Accumulate variants (0x40–0x4D): dest += cmp_result; return cmp_result != 0
    if opcode >= 0x40 and opcode <= 0x4D then
        -- ... accumulate dispatch ...
        local prev = read_int(inst, destp)
        write_int(inst, destp, prev + cmp_result)
        return cmp_result ~= 0
    end

    -- Non-accumulate: compute via exec_quad, return dest != 0
    local result = exec_quad(inst, opcode, src1p, src2p, destp)
    return result ~= 0
end
```

### Opcode Reference

#### Integer Arithmetic

| Opcode | Value | Operation |
|--------|-------|-----------|
| IADD | 0x00 | dest = src1 + src2 |
| ISUB | 0x01 | dest = src1 - src2 |
| IMUL | 0x02 | dest = src1 × src2 |
| IDIV | 0x03 | dest = src1 / src2 |
| IMOD | 0x04 | dest = src1 % src2 |
| INEG | 0x05 | dest = -src1 |

#### Float Arithmetic

| Opcode | Value | Operation |
|--------|-------|-----------|
| FADD | 0x08 | dest = src1 + src2 |
| FSUB | 0x09 | dest = src1 - src2 |
| FMUL | 0x0A | dest = src1 × src2 |
| FDIV | 0x0B | dest = src1 / src2 |
| FMOD | 0x0C | dest = fmod(src1, src2) |
| FNEG | 0x0D | dest = -src1 |

#### Bitwise (Integer, via `bit.*` library)

| Opcode | Value | Operation |
|--------|-------|-----------|
| BIT_AND | 0x10 | dest = bit.band(src1, src2) |
| BIT_OR | 0x11 | dest = bit.bor(src1, src2) |
| BIT_XOR | 0x12 | dest = bit.bxor(src1, src2) |
| BIT_NOT | 0x13 | dest = bit.bnot(src1) |
| BIT_SHL | 0x14 | dest = bit.lshift(src1, src2 & 0x1F) |
| BIT_SHR | 0x15 | dest = bit.rshift(src1, src2 & 0x1F) |

#### Integer Comparison (dest = 1 or 0)

| Opcode | Value | Operation |
|--------|-------|-----------|
| ICMP_EQ | 0x20 | dest = (src1 == src2) ? 1 : 0 |
| ICMP_NE | 0x21 | dest = (src1 ≠ src2) ? 1 : 0 |
| ICMP_LT | 0x22 | dest = (src1 < src2) ? 1 : 0 |
| ICMP_LE | 0x23 | dest = (src1 ≤ src2) ? 1 : 0 |
| ICMP_GT | 0x24 | dest = (src1 > src2) ? 1 : 0 |
| ICMP_GE | 0x25 | dest = (src1 ≥ src2) ? 1 : 0 |

#### Float Comparison (dest = 1 or 0)

| Opcode | Value | Operation |
|--------|-------|-----------|
| FCMP_EQ | 0x28 | dest = (src1 == src2) ? 1 : 0 |
| FCMP_NE | 0x29 | dest = (src1 ≠ src2) ? 1 : 0 |
| FCMP_LT | 0x2A | dest = (src1 < src2) ? 1 : 0 |
| FCMP_LE | 0x2B | dest = (src1 ≤ src2) ? 1 : 0 |
| FCMP_GT | 0x2C | dest = (src1 > src2) ? 1 : 0 |
| FCMP_GE | 0x2D | dest = (src1 ≥ src2) ? 1 : 0 |

#### Logical (dest = 1 or 0)

| Opcode | Value | Operation |
|--------|-------|-----------|
| LOG_AND | 0x30 | dest = (src1 ≠ 0 and src2 ≠ 0) ? 1 : 0 |
| LOG_OR | 0x31 | dest = (src1 ≠ 0 or src2 ≠ 0) ? 1 : 0 |
| LOG_NOT | 0x32 | dest = (src1 == 0) ? 1 : 0 |
| LOG_NAND | 0x33 | dest = ¬(src1 ≠ 0 and src2 ≠ 0) ? 1 : 0 |
| LOG_NOR | 0x34 | dest = ¬(src1 ≠ 0 or src2 ≠ 0) ? 1 : 0 |
| LOG_XOR | 0x35 | dest = ((src1 ≠ 0) ≠ (src2 ≠ 0)) ? 1 : 0 |

#### Move

| Opcode | Value | Operation |
|--------|-------|-----------|
| MOVE | 0x40 | dest = src1 |
| MOV | 0x6E | dest = src1 (alias) |

#### Float Math Functions (via `math.*`)

| Opcode | Value | Operation | Lua |
|--------|-------|-----------|-----|
| FSQRT | 0x50 | dest = √src1 | `math.sqrt(f1)` |
| FPOW | 0x51 | dest = src1^src2 | `f1 ^ f2` |
| FEXP | 0x52 | dest = e^src1 | `math.exp(f1)` |
| FLOG | 0x53 | dest = ln(src1) | `math.log(f1)` |
| FLOG10 | 0x54 | dest = log₁₀(src1) | `math.log(f1, 10)` |
| FLOG2 | 0x55 | dest = log₂(src1) | `math.log(f1, 2)` |
| FABS | 0x56 | dest = \|src1\| | `math.abs(f1)` |

#### Trigonometric (radians, via `math.*`)

| Opcode | Value | Operation | Lua |
|--------|-------|-----------|-----|
| FSIN | 0x58 | dest = sin(src1) | `math.sin(f1)` |
| FCOS | 0x59 | dest = cos(src1) | `math.cos(f1)` |
| FTAN | 0x5A | dest = tan(src1) | `math.tan(f1)` |
| FASIN | 0x5B | dest = arcsin(src1) | `math.asin(f1)` |
| FACOS | 0x5C | dest = arccos(src1) | `math.acos(f1)` |
| FATAN | 0x5D | dest = arctan(src1) | `math.atan(f1)` |
| FATAN2 | 0x5E | dest = atan2(src1, src2) | `math.atan(f1, f2)` |

#### Hyperbolic (manual computation)

| Opcode | Value | Operation | Lua |
|--------|-------|-----------|-----|
| FSINH | 0x60 | dest = sinh(src1) | `(e - 1/e) / 2` where `e = math.exp(f1)` |
| FCOSH | 0x61 | dest = cosh(src1) | `(e + 1/e) / 2` |
| FTANH | 0x62 | dest = tanh(src1) | `(e - 1) / (e + 1)` where `e = math.exp(2*f1)` |

#### Integer Math

| Opcode | Value | Operation |
|--------|-------|-----------|
| IABS | 0x68 | dest = \|src1\| |
| IMIN | 0x69 | dest = min(src1, src2) |
| IMAX | 0x6A | dest = max(src1, src2) |

#### Float Min/Max

| Opcode | Value | Operation |
|--------|-------|-----------|
| FMIN | 0x6C | dest = min(src1, src2) |
| FMAX | 0x6D | dest = max(src1, src2) |

### Predicate Accumulate Variants (SE_P_QUAD only)

These opcodes are only valid in `se_p_quad` nodes. They add the comparison result (0 or 1) to the current dest value before writing, enabling multi-condition counting:

#### Integer Accumulate

| Opcode | Value | Operation |
|--------|-------|-----------|
| P_ICMP_EQ_ACC | 0x40 | dest += (src1 == src2) ? 1 : 0 |
| P_ICMP_NE_ACC | 0x41 | dest += (src1 ≠ src2) ? 1 : 0 |
| P_ICMP_LT_ACC | 0x42 | dest += (src1 < src2) ? 1 : 0 |
| P_ICMP_LE_ACC | 0x43 | dest += (src1 ≤ src2) ? 1 : 0 |
| P_ICMP_GT_ACC | 0x44 | dest += (src1 > src2) ? 1 : 0 |
| P_ICMP_GE_ACC | 0x45 | dest += (src1 ≥ src2) ? 1 : 0 |

#### Float Accumulate

| Opcode | Value | Operation |
|--------|-------|-----------|
| P_FCMP_EQ_ACC | 0x48 | dest += (src1 == src2) ? 1 : 0 |
| P_FCMP_NE_ACC | 0x49 | dest += (src1 ≠ src2) ? 1 : 0 |
| P_FCMP_LT_ACC | 0x4A | dest += (src1 < src2) ? 1 : 0 |
| P_FCMP_LE_ACC | 0x4B | dest += (src1 ≤ src2) ? 1 : 0 |
| P_FCMP_GT_ACC | 0x4C | dest += (src1 > src2) ? 1 : 0 |
| P_FCMP_GE_ACC | 0x4D | dest += (src1 ≥ src2) ? 1 : 0 |

---

## Constraints and Rules

**Do not mix `stack_push`/`stack_pop` with `stack_tos` in the same sequence.** Push and pop modify SP, which invalidates TOS-relative offsets. Use push/pop only for call setup and return retrieval, after all scratch-based computation is complete.

**`se_frame_allocate` locals are volatile.** The frame is recreated every tick. Use blackboard fields for persistent state.

**`se_call` locals are persistent.** The frame created by `se_stack_frame_instance` lives across ticks until the call body completes and the terminate event fires.

**Return value pop order is reversed.** `return_vars = {2, 3}` pushes local 2 then local 3. First `stack_pop` gets local 3 (top), second pop gets local 2.

**Quad helpers return closures.** Always invoke with `()`:
```lua
quad_fadd(a, b, c)()   -- correct: emits the node
quad_fadd(a, b, c)     -- wrong: returns unevaluated closure
```

**`se_frame_allocate` is a pipeline node.** It does not create a function boundary. To create a function boundary (for `SE_FUNCTION_HALT` propagation), wrap in `se_fork_join` or `se_function_interface`.

**Stack values are plain Lua numbers.** Unlike C where stack slots are typed `s_expr_param_t` structs (8/16 bytes), LuaJIT stack entries are plain Lua values. The int/float distinction is handled by opcode selection (IADD vs FADD), not by the stored value.

**Attach stack before ticking.** The stack is optional on tree instances. Trees using `se_frame_allocate`, `se_call`, `se_quad` with stack operands, or `se_push_stack` must have a stack attached:
```lua
local inst = se_runtime.new_instance(mod, "tree_name")
inst.stack = se_stack.new_stack(256)  -- required before first tick
```