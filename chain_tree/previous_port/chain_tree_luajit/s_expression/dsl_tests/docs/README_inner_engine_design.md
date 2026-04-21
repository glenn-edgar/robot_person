# S-Expression Engine (s_engine) — LuaJIT Runtime Design Document

## 1. Overview

The s_engine LuaJIT runtime is a faithful port of the C inner evaluation core for the ChainTree architecture. It provides a compact, deterministic execution engine for evaluating S-expression programs, targeting LuaJIT 2.1 as a high-level host for development, testing, and server-class deployments while maintaining semantic equivalence with the embedded C reference implementation.

The engine uses a **modified Tcl execution model**: programs are defined by a single root function that controls all evaluation. Parameters are structured Lua tables produced by the YAML/JSON DSL pipeline — **not evaluated** until builtin functions explicitly inspect them. This is analogous to Tcl's "everything is a command" philosophy, but with Lisp-style S-expression syntax for nesting, and a tree-of-tables representation replacing the C flat parameter arrays.

There is no tree walker. The engine enters through a single root function via `se_runtime.tick_once()`. That root function — typically a composite like `se_sequence`, `se_fork`, or `se_chain_flow` — explicitly invokes its children, which may in turn invoke their children. The program structure emerges entirely from how functions choose to evaluate their parameters.

### Key Design Principles

- **Semantic equivalence with C** — identical inputs produce identical results; every builtin mirrors its C counterpart behavior, result code by result code.
- **Deterministic execution** — no hidden state, no randomness, no dependency on garbage collection timing.
- **Fail-fast via `assert`** — invalid states raise Lua errors rather than propagating corrupt data, mirroring the C `EXCEPTION` macro behavior.
- **Parameters are data until evaluated** — functions receive structured param tables and decide what to do with them: invoke children as callables, read values, pass to sub-functions, or ignore.
- **Tree-of-tables, not flat arrays** — the LuaJIT runtime operates on a hierarchical Lua table structure (`node.children`, `node.params`) rather than the C flat `s_expr_param_t` array. Brace skipping is unnecessary; children and params are pre-separated by the pipeline.

### Relationship to the C Implementation

The LuaJIT runtime is not a transpilation. It is a structural port that exploits Lua's dynamic typing and table semantics to simplify the machinery while preserving exact behavioral semantics:

| C Concept | LuaJIT Equivalent |
|-----------|-------------------|
| `s_expr_param_t` flat array | `node.params[]` — 1-based Lua array of `{type, value}` tables |
| `brace_idx` / `s_expr_skip_param` | Not needed — children are pre-separated in `node.children[]` |
| `s_expr_node_state_t` (4-byte struct) | `inst.node_states[i]` — Lua table with `flags`, `state`, `user_data` + extensible fields |
| `s_expr_slot_t` (8-byte union) | `inst.pointer_array[i]` — table with `.ptr`, `.u64`, `.f64` fields |
| `module_def_t` (ROM) | `module_data` — Lua table from YAML/JSON pipeline |
| `module_t` (RAM) | `mod` — runtime table with resolved function arrays |
| `tree_instance_t` | `inst` — runtime table with node_states, blackboard, event queue |
| `EXCEPTION(msg)` | `assert(cond, msg)` or `error(msg)` |
| `#define` result code constants | `M.SE_PIPELINE_CONTINUE = 12` etc. (module-level constants) |

---

## 2. Architecture

### 2.1 Layer Diagram

```
┌─────────────────────────────────────────────────────┐
│  Application / ChainTree Nodes                      │
│  (behavior tree composites, state machines)          │
├─────────────────────────────────────────────────────┤
│  Builtin Modules (se_builtins_*.lua)                │
│  (flow_control, dispatch, delays, spawn, oneshot,   │
│   pred, verify, quads, dict, return_codes, stack)   │
├─────────────────────────────────────────────────────┤
│  se_runtime.lua  — Core engine                      │
│  (module/instance lifecycle, dispatch, child API,   │
│   parameter accessors, event queue, tick entry)     │
├─────────────────────────────────────────────────────┤
│  se_stack.lua  — Per-tree parameter stack           │
│  (frames, locals, params, scratch, push/pop)        │
├─────────────────────────────────────────────────────┤
│  module_data  — Pipeline output (Lua tables)        │
│  (trees, function lists, records, constants)        │
└─────────────────────────────────────────────────────┘
```

### 2.2 Execution Model: Modified Tcl

The s_engine borrows from three language traditions:

| Tradition | What s_engine takes |
|-----------|-------------------|
| **Lisp** | S-expression nesting syntax, prefix notation, code-as-data |
| **Tcl** | Parameters are tokenized but not evaluated; functions control evaluation of their arguments |
| **Behavior Trees** | MAIN/ONESHOT/PRED function types, tick-driven lifecycle, result code propagation |

**Key difference from the C implementation:** Parameters are structured Lua tables rather than flat binary arrays. No `brace_idx` or skip-param logic is needed because the pipeline pre-separates callable children into `node.children[]` and non-callable parameters into `node.params[]`. This eliminates the entire parameter-navigation machinery while preserving identical semantics.

### 2.3 Program Structure

A program is a single root callable. All behavior emerges from how that root function and its descendants evaluate their parameters:

```lua
-- Tree structure as Lua tables (produced by pipeline from YAML/JSON):
{
    func_name  = "se_sequence",
    call_type  = "m_call",
    params     = {},
    children   = {
        { func_name="se_log", call_type="o_call",
          params={{type="str_idx", value="init complete"}} },
        { func_name="se_field_gt", call_type="p_call",
          params={{type="field_ref", value="sensor"},
                  {type="int", value=42}} },
        { func_name="se_state_machine", call_type="m_call",
          params={...}, children={...} },
    }
}
```

At runtime, `se_runtime.tick_once()` invokes the root `se_sequence`. The sequence function calls `child_invoke()` on each child in order. Each child function receives its own structured arguments and decides how to use them.

### 2.4 Compilation Pipeline

```
  YAML / JSON DSL source
       │
       ▼
  LuaJIT Pipeline (stage1–stage6)
       │
       ├─ Parses and validates tree definitions
       ├─ Resolves function names to index positions
       ├─ Separates callable children from non-callable params
       ├─ Computes node counts, pointer counts
       │
       ▼
  module_data (Lua table)
       │
       ├─ trees: { [name] = tree_def, ... }
       ├─ tree_order: { name1, name2, ... }
       ├─ oneshot_funcs, main_funcs, pred_funcs: ordered name lists
       ├─ records: { [name] = { fields = { ... } } }
       ├─ constants: { ... }
       │
       ▼
  se_runtime.new_module(module_data, fns)
       │  ├─ Annotates nodes (DFS node_index, func_index)
       │  ├─ Builds name→index maps for function registration
       │  └─ Builds trees_by_hash for spawn lookups
       │
       ▼
  se_runtime.new_instance(mod, tree_name)
       │  ├─ Validates all functions registered
       │  ├─ Allocates node_states[0..N-1]
       │  ├─ Allocates pointer_array[0..P-1]
       │  ├─ Initializes blackboard from record descriptor
       │  └─ Initializes event queue
       │
       ▼
  Runtime: tick loop owned by caller
       se_runtime.tick_once(inst, event_id, event_data)
```

---

## 3. Core Data Structures

### 3.1 Node Table — The Universal Program Element

Every node in a tree is a Lua table with these fields:

| Field | Type | Purpose |
|-------|------|---------|
| `func_name` | string | Builtin function name (e.g. `"se_sequence"`) |
| `call_type` | string | One of: `"m_call"`, `"pt_m_call"`, `"o_call"`, `"io_call"`, `"p_call"`, `"p_call_composite"` |
| `params` | array | 1-based array of `{type, value}` param tables |
| `children` | array | 1-based array of child node tables (callables only) |
| `node_index` | integer | 0-based DFS pre-order index (assigned by `annotate_node`) |
| `func_index` | integer | 0-based index into the module's function array for this call_type |
| `pointer_index` | integer | Index into `pointer_array` (pt_m_call only) |

**Parameter table layout:**

Each entry in `node.params` is a table with `type` and `value`:

| `type` | `value` type | Purpose |
|--------|-------------|---------|
| `"int"` | number | Signed integer literal |
| `"uint"` | number | Unsigned integer literal |
| `"float"` | number | Float literal |
| `"str_idx"` | string | Interned string reference |
| `"str_ptr"` | string | String pointer (same as str_idx in Lua) |
| `"str_hash"` | table `{hash, str}` | String with precomputed FNV-1a hash |
| `"field_ref"` | string | Blackboard field name |
| `"nested_field_ref"` | string | Nested blackboard field name |
| `"result"` | number | Result code literal |
| `"dict_start"` / `"dict_end"` | — | Dictionary structure delimiters |
| `"dict_key"` / `"dict_key_hash"` | string / number | Dictionary key token |
| `"end_dict_key"` | — | Dictionary key terminator |
| `"array_start"` / `"array_end"` | — | Array structure delimiters |
| `"stack_tos"` | number | Stack top-of-stack offset |
| `"stack_local"` | number | Stack local variable index |
| `"stack_pop"` | — | Stack pop operation |
| `"stack_push"` | — | Stack push operation |
| `"const_ref"` | any | Reference to constants table |
| `"list_start"` | table `{items}` | List structure (used by stack frame return vars) |

### 3.2 Node State — `inst.node_states[i]`

Each function node has a per-instance state table at its `node_index`:

| Field | Type | Purpose |
|-------|------|---------|
| `flags` | integer | System flags (bits 3:0) + user flags (bits 7:4) |
| `state` | integer | User state machine value (0–255) |
| `user_data` | integer | Dispatch tracking, counters, etc. |
| `user_u64` | number | Extended 64-bit unsigned storage (optional) |
| `user_f64` | number | Extended 64-bit float storage (optional) |
| `cached_fn` | function | Cached function reference (used by se_exec_fn) |

**System flags** (identical to C):

| Flag | Value | Meaning |
|------|-------|---------|
| `FLAG_ACTIVE` | `0x01` | Node will be dispatched on tick |
| `FLAG_INITIALIZED` | `0x02` | Node has received `SE_EVENT_INIT` |
| `FLAG_EVER_INIT` | `0x04` | Node has ever been initialized (survives reset) |
| `FLAG_ERROR` | `0x08` | Node is in error state |

### 3.3 Pointer Slot — `inst.pointer_array[i]`

A Lua table replacing the C `s_expr_slot_t` union for `pt_m_call` functions that need persistent storage larger than node_state provides:

```lua
{ ptr = nil, u64 = 0, i64 = 0, f64 = 0.0 }
```

Accessed via `se_runtime.get_u64/set_u64`, `get_f64/set_f64` etc. The `inst.pointer_base` and `inst.in_pointer_call` context is saved/restored across nested invocations, exactly mirroring the C implementation.

### 3.4 Tree Instance — `inst`

The central runtime table:

| Field | Type | Purpose |
|-------|------|---------|
| `mod` | table | Module reference (shared function tables, time fn, module_data) |
| `tree` | table | Tree definition from module_data |
| `node_states` | table | `[0..N-1]` → node state tables |
| `node_count` | integer | Total nodes in tree |
| `pointer_array` | table | `[0..P-1]` → pointer slot tables |
| `pointer_count` | integer | Number of pointer slots |
| `blackboard` | table | `[field_name]` → value (typed record binding) |
| `current_node_index` | integer | Currently executing node |
| `current_event_id` | integer | Current event being processed |
| `current_event_data` | any | Current event payload |
| `in_pointer_call` | boolean | True inside pt_m_call dispatch |
| `pointer_base` | integer | Current pointer array index |
| `stack` | table/nil | Optional parameter stack (`se_stack.new_stack()`) |
| `tick_type` | integer | Event type for current tick cycle |
| `event_queue` | table | Circular buffer entries |
| `event_queue_head` | integer | Head index |
| `event_queue_count` | integer | Current count |
| `current_dict` | table/nil | Active function dictionary (set by exec_dict builtins) |
| `user_ctx` | any | Application-defined context |

### 3.5 Module — `mod`

| Field | Type | Purpose |
|-------|------|---------|
| `module_data` | table | Pipeline output (trees, function lists, records, constants) |
| `oneshot_fns` | table | `[0-based index]` → Lua function |
| `main_fns` | table | `[0-based index]` → Lua function |
| `pred_fns` | table | `[0-based index]` → Lua function |
| `_oneshot_idx` | table | `NAME_UPPER` → 0-based index (for registration) |
| `_main_idx` | table | `NAME_UPPER` → 0-based index |
| `_pred_idx` | table | `NAME_UPPER` → 0-based index |
| `trees_by_hash` | table | `[hash]` → tree_name (for spawn lookups) |
| `get_time` | function | Wall-clock time source (default: `os.clock`, injectable) |

---

## 4. Tick and Dispatch

### 4.1 Entry Point

The engine has a single entry point per tick:

```lua
local result = se_runtime.tick_once(inst, event_id, event_data)
```

- `event_id` defaults to `SE_EVENT_TICK` (`0xFFFF`) if nil.
- This invokes the root function only. The root function invokes its children, and so on.
- There is no automatic traversal — all control flow is explicit.
- **The caller owns the tick loop**, the event queue drain loop, and all completion predicates. The runtime does not define when to stop ticking.

### 4.2 Three Function Types

| Type | Call Types | Signature | Returns | Lifecycle | Purpose |
|------|-----------|-----------|---------|-----------|---------|
| **MAIN** | `m_call`, `pt_m_call` | `fn(inst, node, event_id, event_data)` | result code (integer) | INIT → TICK* → TERMINATE | Long-lived nodes (composites, state machines) |
| **ONESHOT** | `o_call`, `io_call` | `fn(inst, node)` | void | Runs once per reset cycle | Setup, I/O binding, one-time actions |
| **PRED** | `p_call`, `p_call_composite` | `fn(inst, node)` | boolean | Stateless | Guards, conditions, predicates |

### 4.3 MAIN Function Three-Phase Lifecycle

```
invoke_main(inst, node, event_id, event_data)
    │
    ├─ Save/restore pointer context (pt_m_call only)
    │   inst.pointer_base = node.pointer_index
    │   inst.in_pointer_call = true
    │
    ├─ PHASE 1: INITIALIZATION (first call only)
    │   if FLAG_INITIALIZED not set:
    │       set FLAG_INITIALIZED
    │       fn(inst, node, SE_EVENT_INIT, nil)
    │
    ├─ PHASE 2: REGULAR EVENT
    │   result = fn(inst, node, event_id, event_data)
    │
    └─ PHASE 3: TERMINATION (if result == SE_PIPELINE_DISABLE)
        fn(inst, node, SE_EVENT_TERMINATE, nil)
        clear FLAG_ACTIVE
```

Inactive nodes (FLAG_ACTIVE == 0) return `SE_PIPELINE_CONTINUE` transparently.

### 4.4 ONESHOT Execution Model

Oneshot functions run exactly once per lifecycle. The guard flag depends on `call_type`:

- **`o_call`** (normal oneshot): Checks `FLAG_INITIALIZED`. Runs once after each reset.
- **`io_call`** (survives reset): Checks `FLAG_EVER_INIT`. Runs once for the entire lifetime of the tree instance, surviving resets.

### 4.5 Result Code Hierarchy

Results are organized into three tiers (identical numeric values to C):

| Tier | Range | Constants | Meaning |
|------|-------|-----------|---------|
| **Application** | 0–5 | `SE_CONTINUE` .. `SE_SKIP_CONTINUE` | Propagate to application level |
| **Function** | 6–11 | `SE_FUNCTION_CONTINUE` .. `SE_FUNCTION_SKIP_CONTINUE` | Scoped to function internals |
| **Pipeline** | 12–17 | `SE_PIPELINE_CONTINUE` .. `SE_PIPELINE_SKIP_CONTINUE` | Scoped to composite node pipeline |

Special event IDs:

| Constant | Value | Purpose |
|----------|-------|---------|
| `SE_EVENT_TICK` | `0xFFFF` | Normal tick event |
| `SE_EVENT_INIT` | `0xFFFE` | Initialization event |
| `SE_EVENT_TERMINATE` | `0xFFFD` | Termination event |

### 4.6 `invoke_any` — Universal Dispatch

The `invoke_any` function dispatches by `call_type`, providing a uniform interface for composites that don't know what type of child they're invoking:

```lua
invoke_any(inst, node, event_id, event_data)
    m_call / pt_m_call  →  invoke_main(...)   →  result code
    o_call / io_call    →  invoke_oneshot(...) →  SE_PIPELINE_CONTINUE
    p_call / p_call_composite → invoke_pred(...) →  CONTINUE or HALT
```

### 4.7 Context Save/Restore

All dispatch functions save and restore `current_node_index`, `in_pointer_call`, and `pointer_base` on the Lua call stack via local variables, enabling safe re-entrant invocation from composite nodes that call children.

---

## 5. Child API

Functions that act as composites use these helpers to control their children. All child indices are **0-based** externally (matching C convention); internal Lua access is `+1`.

### 5.1 Enumeration and Invocation

| Function | Purpose |
|----------|---------|
| `child_count(node)` | Number of callable children |
| `child_invoke(inst, node, idx, event_id, event_data)` | Invoke Nth child via `invoke_any` |
| `child_invoke_pred(inst, node, idx)` | Invoke child as predicate → boolean |
| `child_invoke_oneshot(inst, node, idx)` | Invoke child as oneshot (fire-once) |

### 5.2 Lifecycle Control

| Function | Purpose |
|----------|---------|
| `child_terminate(inst, node, idx)` | Send TERMINATE to child (MAIN only, if INITIALIZED) |
| `child_reset(inst, node, idx)` | Reset child: set ACTIVE, clear state/user_data |
| `child_reset_recursive(inst, node, idx)` | Recursively reset entire child subtree |
| `children_terminate_all(inst, node)` | Terminate all children in reverse order, then reset |
| `children_reset_all(inst, node)` | Reset all children without terminating |

---

## 6. Builtin Function Modules

### 6.1 Flow Control (`se_builtins_flow_control.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_sequence` | m_call | Sequential child execution; advances on completion |
| `se_sequence_once` | m_call | Fire all children once in a single tick |
| `se_function_interface` | m_call | Top-level parallel dispatcher (FUNCTION-level codes) |
| `se_fork` | m_call | Parallel execution; DISABLE when all MAIN complete |
| `se_fork_join` | m_call | Parallel; FUNCTION_HALT while any child active |
| `se_chain_flow` | m_call | Tick all active children with full result dispatch |
| `se_while` | m_call | Loop: pred → body → repeat; DISABLE when pred false |
| `se_if_then_else` | m_call | Conditional: pred re-evaluated each tick |
| `se_cond` | m_call | Multi-branch conditional: (pred, action) pairs |
| `se_trigger_on_change` | m_call | Edge-triggered dispatch on predicate transitions |

### 6.2 Dispatch (`se_builtins_dispatch.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_event_dispatch` | m_call | Dispatch to child by event_id; stateless; default case = -1 |
| `se_state_machine` | m_call | Dispatch by blackboard field; tracks active branch with terminate/reset on transition |
| `se_field_dispatch` | m_call | Like state_machine; different RESET handling |

### 6.3 Delays (`se_builtins_delays.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_tick_delay` | pt_m_call | Delay N ticks (pointer slot u64) |
| `se_time_delay` | pt_m_call | Delay N seconds wall-clock (pointer slot f64) |
| `se_wait_event` | m_call | Wait for event_id to occur N times |
| `se_wait` | m_call | Wait until predicate child becomes true |
| `se_wait_timeout` | pt_m_call | Wait for predicate with timeout watchdog |
| `se_nop` | m_call | Returns SE_DISABLE unconditionally |

### 6.4 Oneshot (`se_builtins_oneshot.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_log`, `se_log_int`, `se_log_float`, `se_log_field` | o_call | Diagnostic logging |
| `se_set_field`, `se_set_field_float` | o_call | Write constant to blackboard field |
| `se_inc_field`, `se_dec_field` | o_call | Increment/decrement field |
| `se_set_hash`, `se_set_hash_field` | o_call | Write hash value to field |
| `se_set_external_field` | o_call | Write value into child tree's blackboard |
| `se_queue_event` | o_call | Push event onto instance event queue |
| `se_push_stack` | o_call | Push value onto parameter stack |

### 6.5 Predicates (`se_builtins_pred.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_pred_and`, `se_pred_or`, `se_pred_not` | p_call | Boolean combinators |
| `se_pred_nor`, `se_pred_nand`, `se_pred_xor` | p_call | Extended combinators |
| `se_true`, `se_false` | p_call | Constants |
| `se_check_event` | p_call | True if current event matches param |
| `se_field_eq/ne/gt/ge/lt/le` | p_call | Field comparison against constant |
| `se_field_in_range` | p_call | Field within inclusive range |
| `se_field_increment_and_test` | p_call | Increment counter, test against limit |
| `se_state_increment_and_test` | p_call | Increment node_state counter, test against limit |

### 6.6 Dictionary (`se_builtins_dict.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_load_dictionary` / `se_load_dictionary_hash` | o_call | Parse inline dict tokens → blackboard table |
| `se_dict_extract_int/uint/float/bool/hash` | o_call | String-path extraction from dict |
| `se_dict_extract_int_h/uint_h/float_h/bool_h/hash_h` | o_call | Hash-path extraction from dict |
| `se_dict_store_ptr` / `se_dict_store_ptr_h` | o_call | Store sub-dict reference |
| `se_load_function_dict` | o_call | Build `{hash → closure}` function dictionary |

The dictionary module includes an FNV-1a 32-bit hash implementation (`s_expr_hash`) that decomposes the prime 16777619 as `(h << 24) + h * 403` to avoid float64 overflow — a LuaJIT-specific concern since LuaJIT uses `bit.tobit` for 32-bit wrapping.

### 6.7 Spawn (`se_builtins_spawn.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_spawn_and_tick_tree` | pt_m_call | Create + tick child tree with event queue drain |
| `se_spawn_tree` | pt_m_call | Create child tree, store in blackboard field |
| `se_tick_tree` | m_call | Tick a spawned child tree + drain its event queue |
| `se_load_function` | io_call | Store closure over child subtree into blackboard |
| `se_exec_fn` | m_call | Execute function stored in blackboard field |
| `se_exec_dict_internal` | m_call | Execute entry from `inst.current_dict` by hash key |
| `se_exec_dict_dispatch` | m_call | Load dict from blackboard, dispatch by compile-time key |
| `se_exec_dict_fn_ptr` | m_call | Like dispatch, but key comes from blackboard field at runtime |

### 6.8 Verify (`se_builtins_verify.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_verify_and_check_elapsed_time` | pt_m_call | Timeout watchdog with error handler |
| `se_verify_and_check_elapsed_events` | pt_m_call | Event count watchdog with error handler |
| `se_verify` | m_call | Predicate watchdog: fires error on failure |

### 6.9 Return Codes (`se_builtins_return_codes.lua`)

Fixed-return functions for all 18 result codes across all three tiers. Generated by a `make_return(code)` factory. INIT and TERMINATE are silently ignored.

### 6.10 Quads (`se_builtins_quads.lua`)

Three-address arithmetic/logical instructions:

| Function | Type | Description |
|----------|------|-------------|
| `se_quad` | o_call | `dest = op(src1, src2)` — integer, float, bitwise, logical, math ops |
| `se_p_quad` | p_call | Same computation, returns `dest != 0`; includes accumulate variants |

Operand reads support: `int`, `uint`, `float`, `field_ref`, `stack_tos`, `stack_local`, `stack_pop`, `const_ref`. Destination writes support: `field_ref`, `stack_tos`, `stack_local`, `stack_push`.

Opcodes cover: integer arithmetic (add/sub/mul/div/mod/neg), float arithmetic, bitwise (and/or/xor/not/shl/shr), integer comparison, float comparison, logical combinators, move, transcendental math (sqrt/pow/exp/log/trig/hyperbolic), integer math (abs/min/max), float min/max.

### 6.11 Stack (`se_builtins_stack.lua`)

| Function | Type | Description |
|----------|------|-------------|
| `se_frame_allocate` | m_call | Custom parallel orchestrator with stack frame lifecycle |
| `se_frame_free` | m_call | Pop top stack frame on INIT only |
| `se_stack_frame_instance` | m_call | Stack frame for `se_call` wrapper (validate arity, push frame, return vars) |
| `se_log_stack` | o_call | Diagnostic: print stack state |

---

## 7. Parameter Stack (`se_stack.lua`)

The optional per-tree stack provides Lua-style 1-based internal indexing with 0-based external API for frame-relative access:

### 7.1 API

```lua
local se_stack = require("se_stack")
local stk = se_stack.new_stack(capacity)

se_stack.push(stk, value)
se_stack.push_int(stk, n)
local v = se_stack.pop(stk)
local v = se_stack.peek_tos(stk, offset)    -- offset=0 → top
se_stack.poke(stk, offset, value)

se_stack.push_frame(stk, num_params, num_locals) → bool
se_stack.pop_frame(stk)
local v = se_stack.get_local(stk, local_idx)     -- 0-based
se_stack.set_local(stk, local_idx, value)
local v = se_stack.get_param(stk, param_idx)      -- 0-based
```

### 7.2 Frame Layout

```
  ┌─────────────┐  ← base_ptr
  │ param 0     │
  │ param 1     │
  │ ...         │
  │ param N-1   │  ← num_params
  │ local 0     │
  │ local 1     │  (zeroed on push)
  │ ...         │
  │ local M-1   │  ← num_locals
  ├─────────────┤  ← scratch_base
  │ scratch...  │
  │             │  ← sp
  └─────────────┘
```

Stack entries are plain Lua values (numbers, strings, nil). Frame records are stored in a `frames[]` array with a `frame_count` tracking depth. `pop_frame` restores `sp` to `base_ptr` (before params).

---

## 8. Event Queue

A per-instance circular buffer (capacity 16) for deferring events:

```lua
-- Internal representation:
inst.event_queue[index] = {
    tick_type  = uint16,   -- event type for tick context
    event_id   = uint16,   -- event identifier
    event_data = any       -- payload (must remain valid until consumed)
}
```

**API:** `se_runtime.event_push(inst, tick_type, event_id, event_data)`, `event_pop(inst)`, `event_count(inst)`, `event_clear(inst)`.

Head/count management with modular arithmetic. The queue is initialized in `new_instance()` and cleared on full tree reset.

The caller is responsible for draining the event queue after each tick. The `tick_with_event_queue` helper in `se_builtins_spawn.lua` shows the canonical drain pattern:

```lua
local result = se_runtime.tick_once(child, event_id, event_data)
while se_runtime.event_count(child) > 0
      and not result_is_complete(result) do
    local tt, eid, edata = se_runtime.event_pop(child)
    result = se_runtime.tick_once(child, eid, edata)
end
```

---

## 9. Blackboard / Field Access

Trees bind a typed record as a blackboard. Fields are accessed by name (string key) rather than byte offset:

```lua
-- Read:  node.params[i].type == "field_ref", .value == "sensor_temp"
local v = inst.blackboard["sensor_temp"]

-- Write:
inst.blackboard["sensor_temp"] = 42
```

The `field_get` accessor coerces string values to numbers so arithmetic predicates work correctly regardless of how the blackboard was initialized (JSON parsers may produce strings for numbers).

Record descriptors in `module_data.records[name]` define fields with names, types, offsets, and defaults. The blackboard is initialized from these defaults in `new_instance()`.

---

## 10. Module System

### 10.1 Module Creation

```lua
local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_verify"),
    require("se_builtins_spawn"),
    require("se_builtins_dict"),
    require("se_builtins_quads"),
    require("se_builtins_return_codes"),
    require("se_builtins_stack"),
    custom_functions
)
local mod = se_runtime.new_module(module_data, fns)
```

### 10.2 Function Registration

Functions are registered by name. `register_fns()` performs case-insensitive matching (`NAME:upper()`) against the module's function lists. Unknown names are silently ignored — they may belong to a different module.

### 10.3 Validation

`validate_module(mod)` checks that every function referenced by the module has been registered. Returns `ok, missing` where `missing` is a list of `{name, kind}` records. `new_instance()` calls this automatically and errors with the complete missing-function list.

### 10.4 DFS Annotation

`annotate_node()` performs a DFS traversal of each tree, assigning `node_index` (0-based pre-order) and `func_index` (resolved from the module's function name lists). This happens once at module creation time.

---

## 11. FNV-1a Hash

The dictionary module provides a LuaJIT-safe FNV-1a 32-bit hash:

```lua
local function s_expr_hash(str)
    local h = 2166136261   -- FNV offset basis
    for i = 1, #str do
        h = bit.bxor(h, str:byte(i))
        -- h * 16777619 mod 2^32, decomposed to avoid float64 overflow:
        h = bit.tobit(bit.lshift(h, 24) + h * 403)
    end
    if h < 0 then h = h + 4294967296 end   -- unsigned normalization
    return h
end
```

The prime 16777619 is decomposed as `2^24 + 403` because LuaJIT's `bit.lshift` returns signed 32-bit values and `h * 16777619` would overflow float64 precision for large `h`. The decomposition keeps all intermediate products within float64 exact range (< 2^53).

---

## 12. Differences from C Implementation

| Aspect | C | LuaJIT |
|--------|---|--------|
| Parameter storage | Flat `s_expr_param_t[]` in ROM (8/16 bytes each) | Lua table array `node.params[]` |
| Child navigation | `brace_idx` + `s_expr_skip_param` for O(1) skip | Pre-separated `node.children[]`; no skip needed |
| Node state | 4-byte packed struct (flags, state, user_data) | Lua table with named fields + extensible extra fields |
| Memory model | Zero heap allocation during tick; pre-allocated pools | GC-managed Lua tables; no explicit allocation control |
| Error handling | `EXCEPTION` macro → spin for watchdog | `assert()` / `error()` → Lua error propagation |
| Type system | `_Static_assert`, `uint8_t`, `int32_t` etc. | Dynamic typing; `bit.*` for 32-bit operations |
| Pointer arithmetic | Direct byte offset into blackboard struct | String-keyed table lookup |
| Thread safety | Not thread-safe; per-core ownership | Same — single-coroutine access assumed |
| Tick loop | Caller-owned (same) | Caller-owned (same) |
| Time source | Platform-specific (injectable) | `mod.get_time` (default `os.clock`, injectable) |

---

## 13. Thread Safety

The LuaJIT runtime is **not thread-safe**, same as the C implementation. A tree instance must be ticked from a single Lua coroutine or thread. The event queue push/pop operations are not atomic.

For multi-instance deployments, each instance should be ticked independently. Cross-instance communication should go through NATS JetStream, MQTT, or PostgreSQL at the ChainTree layer, not through shared s_engine state.

---

## 14. Summary

The s_engine LuaJIT runtime is a semantically equivalent port of the C inner evaluation core, replacing flat binary parameter arrays with structured Lua tables and byte-offset field access with string-keyed lookups. Programs are defined by a single root function invoked via `se_runtime.tick_once()`. That function — and every function it calls — receives structured but unevaluated parameters, giving each builtin full control over argument interpretation. The Tcl-style evaluation model, the three-tier result code hierarchy, the three function types (MAIN/ONESHOT/PRED), and the exact lifecycle semantics are preserved. The caller owns the tick loop, event queue drain, and completion predicates.

The runtime is organized across 12 Lua modules: `se_runtime` (core engine), `se_stack` (parameter stack), and 10 builtin modules covering flow control, dispatch, delays, predicates, oneshots, dictionary operations, spawning/function execution, verification, three-address quads, return code generators, and stack frame management.