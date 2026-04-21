# Why the S Engine — LuaJIT Runtime

## Origin: ChainTree and the Need for S_Engine

### ChainTree Background

ChainTree is a behavior tree system developed before the S_Engine. It provides hierarchical control flow for embedded systems — sequences, selectors, parallel nodes, and state machines — with each leaf node implemented as a compiled C function.

ChainTree works well for high-level orchestration, but it struggles with modularity at the leaf level. Many embedded control tasks involve repetitive operations that differ only in parameters: configuring GPIO pins, setting up UART channels, reading ADC values, writing registers. Each variation requires its own C function, leading to:

- **Function explosion** — hundreds of small C functions that do nearly identical things with different constants
- **Poor reuse** — "set pin as output" can't easily be parameterized and shared across different ports
- **Tight coupling** — the behavior tree structure is locked to specific hardware layouts
- **Difficult composition** — combining boolean logic on hardware states (e.g., "wait until pin A AND pin B are both high") requires custom composite nodes

Even simple operations that differ only in a register address or bit mask become separate compiled functions, because ChainTree leaves have no built-in mechanism for parameterized, composable logic.

### S_Engine as Microcode

The S_Engine was initially developed as a microcode layer for ChainTree leaf nodes. Instead of writing a separate C function for each hardware operation, a small set of primitives (e.g., `gpio_mode`, `write_register`) could be composed through interpreted S-expression programs. ChainTree's virtual function table dispatches to either a native C function or an S_Engine program transparently:

```
Virtual Function Table
┌────────────────┬─────────────────────────────────────┐
│ Name           │ Implementation                      │
├────────────────┼─────────────────────────────────────┤
│ motor_init     │ C function: motor_init_fn()         │
│ sensor_read    │ C function: sensor_read_fn()        │
│ gpio_setup     │ S_Engine: gpio_setup tree           │
│ pump_cycle     │ S_Engine: pump_cycle tree           │
│ check_inputs   │ S_Engine: check_inputs tree         │
└────────────────┴─────────────────────────────────────┘
```

This eliminated the function explosion problem. A system that previously needed dozens of nearly-identical C leaf functions could instead share a single engine with parameterized tree structures.

### Standalone Engine

As the S_Engine matured, it became clear that it was capable of operating as a standalone control engine, not just as microcode beneath ChainTree. The S_Engine now supports:

- Full behavior tree patterns (sequences, selectors, state machines, parallel nodes)
- Stack-based parameter passing with frame variables
- Function dictionaries for runtime-dispatched subroutines
- Blackboard records for shared state
- Cross-tree composition (spawning, ticking, and communicating between trees)
- Expression compilation for arithmetic and bitwise operations

The S_Engine can be used as a microcode layer under ChainTree, as a standalone embedded control engine (C runtime), as a development/testing/server runtime (LuaJIT), or combinations thereof — with the C and LuaJIT runtimes producing identical behavior tree by tree.

---

## The LuaJIT Runtime

The LuaJIT runtime is a semantically equivalent port of the C S_Engine. It replaces the flat compiled parameter arrays and binary token format with structured Lua tables, while preserving identical execution semantics — the same trees produce the same results in both runtimes.

### Why LuaJIT?

| Concern | C Runtime | LuaJIT Runtime |
|---------|-----------|----------------|
| Target platform | 32KB ARM Cortex-M to servers | Development machines, servers, CI |
| Memory model | Zero heap allocation, pre-allocated pools | GC-managed Lua tables |
| Test cycle | Cross-compile → flash → debug via JTAG | Edit → run → see results instantly |
| Tree authoring | YAML/JSON → pipeline → SEXB binary → C arrays | YAML/JSON → pipeline → Lua table → direct execution |
| Debugging | Printf, watchdog reset, JTAG | Lua error messages, pcall, print |
| Performance | Deterministic, cache-friendly flat arrays | LuaJIT JIT compilation, hash-table lookups |

The LuaJIT runtime exists primarily for:

1. **Rapid development** — test tree logic without cross-compilation or hardware
2. **Pipeline validation** — verify that the YAML/JSON pipeline produces correct trees
3. **Test harness** — run the full Python DSL test suite (tests 5–22) against the LuaJIT runtime
4. **Server deployment** — run S_Engine trees on Linux/server targets where LuaJIT's performance is more than adequate
5. **Reference implementation** — the LuaJIT code is easier to read and audit than the C equivalent

### Structural Differences from C

The fundamental shift from C to LuaJIT is the replacement of flat binary token streams with nested Lua table trees:

```
C Runtime:
  YAML/JSON → Pipeline → SEXB binary → flat s_expr_param_t[] in ROM
  Navigation via brace_idx, skip_param, OPEN_CALL/CLOSE pairs
  Functions bound by FNV-1a hash → function pointer lookup

LuaJIT Runtime:
  YAML/JSON → Pipeline → module_data Lua table
  Navigation via node.children[] and node.params[] (pre-separated)
  Functions bound by name → case-insensitive string matching
```

This eliminates the entire token navigation subsystem (`s_expr_skip_param`, `brace_idx`, `OPEN_CALL`/`CLOSE` matching) because the pipeline does the structural separation at compile time.

---

## Why S-Expressions?

### Evolution from Flow Control

The S_Engine wasn't the first approach. Earlier iterations used a flow control model with explicit opcodes for branching, looping, and sequencing — essentially a small bytecode VM. This was removed because S-expressions proved far more efficient in both code size and execution speed.

The flow control model required:
- Explicit branch targets and jump calculations
- Separate opcodes for if/else/while/for constructs
- Complex state tracking for nested control flow
- Redundant encoding of structure that was implicit in the tree

S-expressions encode control flow structurally. A `se_sequence` node's children execute in order — no jump opcodes needed. An `se_if_then_else` node has exactly three children: predicate, consequent, alternative. The structure *is* the control flow.

```
Flow control approach (abandoned):
  LOAD_PRED 0
  JUMP_IF_FALSE label_else
  CALL func_a
  JUMP label_end
label_else:
  CALL func_b
label_end:

S-expression approach (current, as Lua tree node):
  { func_name = "se_if_then_else", call_type = "m_call",
    children = {
      { func_name = "pred_0", call_type = "p_call", ... },
      { func_name = "func_a", call_type = "m_call", ... },
      { func_name = "func_b", call_type = "m_call", ... },
    }
  }
```

The S-expression version uses fewer nodes, executes faster (no branch misprediction), and is easier to debug (tree structure visible in the module data).

### Tcl-Like Evaluation Model

The S_Engine evaluation model is inspired by Tcl rather than Lisp. In Tcl, **the called function decides how to process its arguments**. Arguments are not evaluated before the call — the function receives them as unevaluated tokens and chooses what to do.

This is fundamentally different from Lisp's model where arguments are evaluated before the function sees them (unless explicitly quoted).

In the S_Engine, composite nodes like `se_if_then_else`, `se_sequence`, `se_state_machine`, and `se_while` receive their children as node tables. The composite's implementation decides:
- Which children to evaluate (via `child_invoke`, `child_invoke_pred`)
- In what order
- How many times
- Whether to evaluate at all

This enables **creative control structures through new functions**, not through macros or quoting:

```lua
-- In the LuaJIT runtime, each of these is a Lua function that
-- iterates its node.children[] according to its own logic:

-- se_while: evaluate pred, if true execute body, repeat
-- se_sequence: execute children one at a time in order
-- se_fork: execute all children in parallel
-- se_state_machine: dispatch to one child based on field value
-- se_trigger_on_change: detect edge transitions in a predicate
-- se_cond: multi-branch conditional with (pred, action) pairs
```

Each of these is just a Lua function that interprets its `node.children` appropriately. No macro system, no quoting rules, no evaluation order surprises. Adding a new control structure means writing one new function and registering it.

### Avoiding Lisp's Quoting Complexity

Lisp's power comes with complexity. Quoting, quasiquoting, unquote, and unquote-splicing create a notation burden that's particularly painful for non-Lisp developers writing embedded control logic.

The S_Engine sidesteps this entirely. Since functions control their own argument evaluation, there's no need for quoting mechanisms. What the pipeline produces is what gets stored in the tree. In the LuaJIT runtime, children are plain Lua tables — no special syntax needed to prevent or force evaluation.

### The DSL: Making S-Expressions Palatable

Raw S-expressions are tedious to write and error-prone. The DSL provides an authoring environment (originally Python, now also LuaJIT pipeline stages) that generates the tree structures:

```lua
-- DSL source (compiled by pipeline to module_data)
se_sequence({
    se_log("motor_init: starting"),
    oneshot("gpio_mode", PORTA, 0, OUTPUT_PP),
    oneshot("gpio_mode", PORTA, 1, OUTPUT_PP),
    oneshot("pwm_config", TIMER1, CH1, 20000, 8),
    oneshot("pwm_enable", TIMER1, CH1),
    se_log("motor_init: complete"),
})
```

This compiles to a tree node in `module_data`:

```lua
{ func_name = "se_sequence", call_type = "m_call",
  children = {
    { func_name = "se_log", call_type = "o_call",
      params = { {type="str_ptr", value="motor_init: starting"} } },
    { func_name = "gpio_mode", call_type = "o_call",
      params = { {type="uint", value=PORTA}, {type="uint", value=0},
                 {type="uint", value=OUTPUT_PP} } },
    -- ... more children ...
  }
}
```

The DSL provides:
- **Readable syntax** — familiar to embedded developers
- **Compile-time validation** — catch errors before deployment
- **Automatic structure** — children and params separated by pipeline
- **Function registration** — type checking for primitives
- **Multiple output targets** — Lua tables for LuaJIT runtime, C arrays/SEXB for C runtime

The developer writes natural DSL code; the pipeline emits efficient tree structures. No Lisp knowledge required.

### Summary: Why This Approach

| Aspect | Flow Control VM | Lisp S-Expressions | Tcl-Style S_Engine |
|--------|-----------------|--------------------|--------------------|
| Control flow encoding | Explicit jumps | Structure + macros | Structure + functions |
| Argument evaluation | Eager | Eager (unless quoted) | Lazy (function decides) |
| New control structures | New opcodes | Macros | New Lua/C functions |
| Quoting complexity | N/A | High | None |
| Authoring | Assembly-like | Raw parens | DSL → pipeline |
| Code size | Largest | Medium | Smallest |
| Debugging | Opaque | Readable | Readable |

---

## Node Representation in LuaJIT

### Node Table Structure

In the C runtime, every element is an `s_expr_param_t` — a compact tagged-union token (8 bytes on 32-bit, 16 on 64-bit). In the LuaJIT runtime, the equivalent is a **node table** with explicit fields:

```lua
{
    func_name    = "se_chain_flow",       -- function name (string)
    func_hash    = 0xFFC1FAA4,            -- FNV-1a hash (C cross-reference)
    call_type    = "m_call",              -- dispatch type (string)
    order        = 0,                     -- sibling position (0-based)
    param_count  = 0,                     -- informational
    pointer_index = nil,                  -- pointer slot (pt_m_call only)
    node_index   = 5,                     -- DFS pre-order index (assigned at module creation)
    func_index   = 2,                     -- index into mod.main_fns[] (assigned at module creation)
    params       = { ... },               -- non-callable parameters
    children     = { ... },               -- callable child nodes
}
```

### Call Types

The C `type` byte encodes opcode + flags in a single byte. The LuaJIT runtime uses explicit string `call_type` values:

| C Type Byte | C Interpretation | LuaJIT `call_type` | Description |
|-------------|-----------------|---------------------|-------------|
| `0x08` | ONESHOT | `"o_call"` | Fire-once function |
| `0x48` | ONESHOT + SURVIVES_RESET | `"io_call"` | Fire-once, survives tree reset |
| `0x09` | MAIN | `"m_call"` | Tick function with INIT/TICK/TERMINATE lifecycle |
| `0x89` | MAIN + POINTER | `"pt_m_call"` | Tick function with pointer slot storage |
| `0x0A` | PRED | `"p_call"` | Simple predicate (boolean) |
| `0x4A` | PRED + SURVIVES_RESET | `"p_call_composite"` | Composite predicate with child predicates |

The flag bits (POINTER, SURVIVES_RESET) are absorbed into the call_type string rather than requiring bitmask operations.

### Parameter Tables

Non-callable parameters live in `node.params[]`. Each is a table with `type` and `value`:

| C Opcode | C Name | LuaJIT `type` string | `value` type | Description |
|----------|--------|---------------------|--------------|-------------|
| `0x00` | INT | `"int"` | number | Signed integer |
| `0x01` | UINT | `"uint"` | number | Unsigned integer |
| `0x02` | FLOAT | `"float"` | number | Float |
| `0x03` | STR_HASH | `"str_hash"` | `{hash=N, str=S}` | String with precomputed FNV-1a |
| `0x0B` | FIELD | `"field_ref"` | string (field name) | Blackboard field reference |
| `0x0C` | RESULT | `"result"` | number | Result code literal |
| `0x0D` | STR_IDX | `"str_idx"` | string | Interned string |
| — | — | `"str_ptr"` | string | String pointer (same as str_idx in Lua) |
| `0x0E` | CONST_REF | `"const_ref"` | any | Constants table reference |
| `0x10` | OPEN_DICT | `"dict_start"` | — | Dictionary structure open |
| `0x11` | CLOSE_DICT | `"dict_end"` | — | Dictionary structure close |
| `0x12` | OPEN_KEY | `"dict_key"` | string | Dictionary key (string name) |
| — | — | `"dict_key_hash"` | number | Dictionary key (FNV-1a hash) |
| `0x13` | CLOSE_KEY | `"end_dict_key"` | — | Dictionary key terminator |
| `0x14` | OPEN_ARRAY | `"array_start"` | — | Array structure open |
| `0x15` | CLOSE_ARRAY | `"array_end"` | — | Array structure close |
| `0x18` | STACK_TOS | `"stack_tos"` | number (offset) | Stack TOS-relative |
| `0x19` | STACK_LOCAL | `"stack_local"` | number (index) | Stack frame local |
| `0x1A` | NULL | — | — | Null/unused |
| `0x1B` | STACK_PUSH | `"stack_push"` | — | Push destination |
| `0x1C` | STACK_POP | `"stack_pop"` | — | Pop source |

### What's Eliminated

Several C token types have no LuaJIT equivalent because the pipeline handles their concerns at compile time:

| C Token | Purpose in C | Why Not Needed in LuaJIT |
|---------|-------------|--------------------------|
| `OPEN_CALL` (0x07) | Bracket function call start | Children are in `node.children[]` |
| `CLOSE` (0x06) | Bracket matching end | Nesting is implicit in Lua tables |
| `OPEN` (0x05) | Generic open bracket | No flat-stream structure to bracket |
| `SLOT` (0x04) | Legacy | Removed |
| `OPEN_TUPLE` / `CLOSE_TUPLE` | Fixed-size group | Not used in LuaJIT runtime |
| `brace_idx` field | O(1) skip over nested structures | No flat stream to skip |
| `index_to_pointer` field | Pointer array index | `node.pointer_index` (explicit node field) |
| `node_index` in param union | State array index | `node.node_index` (explicit node field) |
| `func_index` in param union | Function table index | `node.func_index` (explicit node field) |

The key insight: in C, the `s_expr_param_t` union must encode *everything* — function identity, structural brackets, values, field references — in a single 8-byte token. In LuaJIT, these concerns are separated into distinct fields on the node table (`func_name`, `call_type`, `children`, `params`, `node_index`, `func_index`, `pointer_index`).

---

## Node Runtime State

### Node States in LuaJIT

Every function node has a per-instance state table at `inst.node_states[node_index]`:

```lua
inst.node_states[i] = {
    flags     = 0x01,   -- FLAG_ACTIVE
    state     = 0,      -- user state machine value (0–255)
    user_data = 0,      -- dispatch tracking, counters
    -- Extensible: builtins can add user_u64, user_f64, cached_fn, etc.
}
```

### Flags

| Flag | Value | Meaning |
|------|-------|---------|
| `FLAG_ACTIVE` | `0x01` | Currently executing; dispatched on tick |
| `FLAG_INITIALIZED` | `0x02` | Oneshot function has completed |
| `FLAG_EVER_INIT` | `0x04` | Has been initialized at least once (survives reset) |
| `FLAG_ERROR` | `0x08` | Node is in error state |
| Bits 4–7 | `0xF0` | Available for user-defined flags |

Flag manipulation uses LuaJIT's `bit.*` library:

```lua
local bit = require("bit")
local band, bor, bnot = bit.band, bit.bor, bit.bnot

-- Check if active:
if band(ns.flags, FLAG_ACTIVE) ~= 0 then ...

-- Set initialized:
ns.flags = bor(ns.flags, FLAG_INITIALIZED)

-- Clear active:
ns.flags = band(ns.flags, bnot(FLAG_ACTIVE))

-- Preserve user flags, set active + ever_init:
ns.flags = bor(band(ns.flags, FLAGS_USER), FLAG_ACTIVE, FLAG_EVER_INIT)
```

### Pointer Array

Most nodes only need the flags/state/user_data fields. Nodes with `call_type = "pt_m_call"` also use a pointer slot for persistent storage larger than what node_state provides:

```lua
inst.pointer_array[node.pointer_index] = {
    ptr = nil,    -- Lua value (child instance, table, etc.)
    u64 = 0,      -- unsigned 64-bit
    i64 = 0,      -- signed 64-bit
    f64 = 0.0,    -- float 64-bit
}
```

Accessed via `se_runtime.get_u64/set_u64`, `get_f64/set_f64` etc. The `inst.pointer_base` and `inst.in_pointer_call` context is saved/restored across nested invocations.

### Extensible Node State

Unlike C where `s_expr_node_state_t` is a fixed 4-byte struct, LuaJIT node_states are Lua tables that builtins can extend freely:

```lua
-- se_builtins_delays.lua adds wait_target/wait_remain:
ns.wait_target = param_int(node, 1)
ns.wait_remain = param_int(node, 2)

-- se_builtins_spawn.lua adds cached_fn:
ns.cached_fn = inst.blackboard[field_name]

-- se_runtime.lua provides user_u64/user_f64:
ns.user_u64 = 0
ns.user_f64 = 0.0
```

No pre-allocation needed — Lua tables grow dynamically.

### Memory Layout Comparison

```
C Runtime:
  node_states[]:     [flags0][flags1]...[flagsN]      4 bytes each (packed)
  pointer_array[]:   [slot0][slot1]...[slotM]          8 bytes each (union)
  Total: N*4 + M*8 bytes

LuaJIT Runtime:
  inst.node_states[]:  [table0][table1]...[tableN]     GC-managed tables
  inst.pointer_array[]: [table0][table1]...[tableM]    GC-managed tables
  Total: GC overhead per table (not directly comparable)
```

The LuaJIT version trades compact memory layout for extensibility and dynamic typing.

---

## The S_Engine as Microcode Layer

### Architecture (LuaJIT Variant)

The LuaJIT S_Engine can serve as a microcode layer beneath ChainTree just as the C version does, but the integration pattern differs:

```
ChainTree Architecture (LuaJIT deployment)
┌─────────────────────────────────────────────────────────┐
│                    ChainTree Walker                      │
│            (behavior tree traversal engine)              │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ C Leaf   │    │ Lua Leaf │    │ Virtual  │
    │ Function │    │ Function │    │ Function │
    └──────────┘    └──────────┘    └─────┬────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │   S_Engine   │
                                   │  (LuaJIT     │
                                   │   runtime)   │
                                   └──────────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                    ┌──────────┐    ┌──────────┐    ┌──────────┐
                    │ Tree     │    │ Tree     │    │ Tree     │
                    │ Instance │    │ Instance │    │ Instance │
                    │ (inst)   │    │ (inst)   │    │ (inst)   │
                    └──────────┘    └──────────┘    └──────────┘
```

In the LuaJIT runtime, "S-expression programs in ROM" become tree instances created by `se_runtime.new_instance(mod, tree_name)`. The module_data table replaces ROM arrays.

### Boolean Composition on Hardware

The predicate system enables composable boolean logic without custom functions:

```lua
-- Tree structure for: wait until both limit switches triggered
-- se_wait
--   children[0]: se_pred_and (p_call_composite)
--     children[0]: gpio_read(PORTA, 4)   (p_call)
--     children[1]: gpio_read(PORTA, 5)   (p_call)

-- Tree structure for: complex safety interlock
-- se_if_then_else
--   children[0]: se_pred_or (p_call_composite)
--     children[0]: se_pred_not
--       children[0]: gpio_read(EMERGENCY_STOP)
--     children[1]: se_pred_and
--       children[0]: field_gt(current_sense, 500)
--       children[1]: field_lt(temp_sense, 80)
--   children[1]: motor_disable (o_call)
--   children[2]: motor_enable (o_call)
```

These compositions execute as Lua function calls on nested child arrays — each predicate evaluates its children and combines the boolean results.

### Benefits

| Aspect | Traditional BT Leaves | S_Engine (LuaJIT) |
|--------|----------------------|-------------------|
| Code size | One C/Lua function per operation | Shared runtime + tree definitions |
| Modularity | Poor — functions tightly coupled | High — builtins compose freely |
| Configuration | Rewrite code for changes | Data-driven tree structures |
| Boolean logic | Custom composite nodes | Built-in AND/OR/NOT predicates |
| Debugging | Breakpoints in leaf functions | Inspect node_states, blackboard, tree structure |
| Testing | Requires hardware or mocks | LuaJIT runtime runs on development machine |

---

## Execution Model

### Three Function Types

The S_Engine supports three function types, mapping to call_type strings:

| Type | Call Types | Lifecycle | Purpose |
|------|-----------|-----------|---------|
| **ONESHOT** | `o_call`, `io_call` | Runs once per activation | Setup, I/O binding, field writes |
| **MAIN** | `m_call`, `pt_m_call` | INIT → TICK* → TERMINATE | Composites, state machines, delays |
| **PRED** | `p_call`, `p_call_composite` | Stateless boolean | Guards, conditions, boolean logic |

### Execution Order Per Tick

```
1. invoke_main called on root node
   │
   ├─ If not FLAG_INITIALIZED:
   │     Set FLAG_INITIALIZED
   │     Call fn(inst, node, SE_EVENT_INIT, nil)
   │
   ├─ Call fn(inst, node, event_id, event_data)
   │     → result code (0–17)
   │
   └─ If result == SE_PIPELINE_DISABLE:
         Call fn(inst, node, SE_EVENT_TERMINATE, nil)
         Clear FLAG_ACTIVE
```

Within composites, children are dispatched according to the composite's logic:
- `se_sequence`: one child at a time, advance on completion
- `se_fork` / `se_chain_flow`: all active children each tick
- `se_while`: predicate → body → repeat
- `se_state_machine`: dispatch to one child based on field value

### State Storage

The engine maintains minimal state per active node:

```lua
-- Per node: flags + state + user_data (+ extensible fields)
inst.node_states[node_index] = { flags=0x01, state=0, user_data=0 }

-- Per pt_m_call node: additional pointer slot
inst.pointer_array[pointer_index] = { ptr=nil, u64=0, i64=0, f64=0.0 }

-- Shared: blackboard record fields
inst.blackboard["temperature"] = 25.5

-- Optional: parameter stack for frame_allocate / se_call / quads
inst.stack = se_stack.new_stack(256)
```

---

## Design Notes

- **Children pre-separated by pipeline** — eliminates brace matching, skip_param, and OPEN_CALL/CLOSE token navigation entirely
- **String-keyed fields** — blackboard access is `inst.blackboard[name]` rather than byte-offset pointer arithmetic
- **Name-based function binding** — case-insensitive string matching replaces FNV-1a hash lookup tables
- **GC-managed memory** — no explicit allocation, deallocation, or ownership tracking
- **Extensible node state** — Lua tables grow dynamically; builtins add fields as needed
- **Cross-runtime compatibility** — FNV-1a hashes in module_data (`func_hash`, `name_hash`) match C values exactly, enabling cross-reference between C debug dumps and LuaJIT module data
- **Tcl-like lazy evaluation** — composite functions control child evaluation, enabling new control structures through new Lua functions without macros or quoting
- **S_Engine provides composable logic** that eliminates the need for hundreds of small leaf functions, whether implemented in C or Lua