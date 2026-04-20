# ChainTree S-Expression Engine — Python Port: Design Specification

## Purpose of This Document

This is a **complete design specification** for a Python port of the ChainTree
S-Expression behavior tree engine. It was worked out incrementally in a
chat/design session against the LuaJIT reference port. Hand this to a Claude
Code session along with access to the LuaJIT source and use it as the
authoritative design contract.

**Do not write code until you have read this entire document.** The design
decisions here are deliberate and several of them override what a naive port
of the LuaJIT would produce.

---

## Reference Implementation

The LuaJIT port is the reference. Path in the repo:

```
knowledge_base_container/luajit_programs_and_containers/building_blocks/s_expression_luajit/
├── CLAUDE.md                         # existing LuaJIT port notes
├── continue.md                       # existing LuaJIT port continuation notes
├── lua_runtime/                      # pure-Lua execution engine
│   ├── se_runtime.lua                # PRIMARY REFERENCE — engine core
│   ├── se_builtins_flow_control.lua  # PRIMARY REFERENCE — operator semantics
│   ├── se_builtins_dispatch.lua
│   ├── se_builtins_pred.lua
│   ├── se_builtins_oneshot.lua
│   ├── se_builtins_return_codes.lua
│   ├── se_builtins_delays.lua
│   ├── se_builtins_verify.lua
│   ├── se_builtins_dict.lua
│   ├── se_builtins_spawn.lua         # DO NOT PORT (see below)
│   ├── se_builtins_quads.lua         # DO NOT PORT (see below)
│   ├── se_builtins_stack.lua         # DO NOT PORT (see below)
│   └── se_stack.lua                  # DO NOT PORT (see below)
├── lua_dsl/                          # DSL compiler (reference for emitter shape)
└── dsl_tests/                        # worked examples of tree definitions
```

**Use `se_runtime.lua` and `se_builtins_flow_control.lua` as the primary
references.** They define the tick model, lifecycle, and core operator
semantics. The C source referenced in those files (`s_engine_eval.c`,
`s_engine_node.c`, etc.) is the original implementation if a tie-breaker is
needed.

**Note:** Glenn Edgar established that the Python port is the canonical
reference for all non-Zig ports going forward. If there is a conflict between
the LuaJIT behavior and the semantics specified here, **this specification
wins**. The LuaJIT port carries C-era artifacts (flat param arrays, integer
event IDs, FNV-1a hash dispatch, stack machine, quad expression compiler,
blackboard abstraction, per-node-state parallel array) that are unnecessary
in Python.

---

## What Is Dropped From the LuaJIT Port

These subsystems are **not ported** to Python. Do not port them.

| Subsystem | LuaJIT file(s) | Why dropped |
|---|---|---|
| Stack machine | `se_stack.lua`, `se_builtins_stack.lua` | C-era artifact; Python has native lists and closures |
| Quad expression compiler | `se_builtins_quads.lua` | C-era optimization; Python expressions are expressions |
| Equation DSL | helper in `lua_dsl/` | Subsumed by plain Python callables |
| Spawn builtin family | `se_builtins_spawn.lua` | Replaced by a single nested-tick primitive |
| Tree hash index | `trees_by_hash`, `name_hash` | Plain dict lookup by tree name |
| FNV-1a hash dispatch | everywhere | Python dict hashing is already O(1) |
| Blackboard abstraction | `inst.blackboard` | Collapsed into the module dictionary |
| `field_ref` / `nested_field_ref` param types | DSL, param accessors | Plain string keys into the module dictionary |
| Parallel `node_states[]` array | `se_runtime.lua` | State lives directly on each node dict |
| DFS `node_index` annotation | `annotate_node` in `se_runtime.lua` | No parallel array to index into |
| `pt_m_call` pointer-slot call type | `se_runtime.lua` | Python closures and dict state replace it |
| `p_call_composite` call type | `se_runtime.lua` | Merged into `p_call` — predicates can have children naturally |
| Integer event IDs | everywhere | Event IDs are strings |
| `FLAG_ERROR` bit | `se_runtime.lua` | Exceptions are hard crashes — no recovery flag |
| Function dictionaries | `se_builtins_dict.lua` (function loading) | Python imports replace the dynamic fn dictionary |
| Hash-keyed dictionary extractors (`se_dict_extract_*_h`) | `se_builtins_dict.lua` | Python dict is already string-keyed |
| Type-split dictionary extractors (`se_dict_extract_int/uint/float/bool/hash`) | `se_builtins_dict.lua` | Python values are self-typed |

---

## Architecture Overview

### Execution Model

The Python port is **one-step**: DSL functions return tree dicts in the same
process where the engine runs, and the engine consumes them directly. There
is no required compile-and-load step. Construction and execution happen
together. This enables **dynamic runtime planning** — an LLM, a planner, an
operator command, or any Python code can construct or modify trees at
runtime and hand them to the engine immediately.

A static-emission path (DSL output → `.py` file → later import) is supported
as an optional serialization helper for cases that want a durable,
version-controlled plan artifact. It's the same DSL functions and the same
engine input shape; only the storage between construction and ticking
differs.

### Layering

```
Engine  (runs exactly one tree instance at a time)
  │
  └── Module  (unit of deployment; emitted by the DSL as a .py file)
        ├── dictionary   (flat, mutable, shared runtime state; dict[str, Any])
        ├── constants    (flat, immutable shared; MappingProxyType)
        ├── trees        (dict[str, tree_root_node])
        ├── get_time     (callable; returns 64-bit monotonic ns timestamp)
        └── crash_callback  (optional callable)
```

### Node shape (every node is a dict)

```python
{
    "fn":          <callable>,             # the function implementing the node
    "call_type":   "m_call" | "o_call" | "io_call" | "p_call",
    "params":      {<name>: <value>, ...}, # dict keyed by param name, raw Python values
    "children":    [<node>, ...],          # list of directly nested child dicts
    "active":      True,                   # starts True, cleared on DISABLE
    "initialized": False,                  # starts False, set on first INIT, cleared on reset
    "ever_init":   False,                  # starts False, set once, survives reset
    "state":       0,                      # operator-specific state (int, index, etc.)
    "user_data":   None,                   # operator-specific extended state
    "deadline":    None,                   # optional — only on timing nodes
}
```

Children are directly nested. The tree *is* the structure. There is no
external name registry, no `node_index`, no parallel state array. Each node
carries its own state inline.

### Call types (4, down from 6 in LuaJIT)

| call_type | Signature | Lifecycle | Returns |
|---|---|---|---|
| `m_call` | `fn(inst, node, event_id, event_data) -> int` | Full INIT/TICK/TERMINATE | Three-family return code (see below) |
| `o_call` | `fn(inst, node)` | Fires once per activation; reset clears `initialized` | None |
| `io_call` | `fn(inst, node)` | Fires once per instance lifetime; `ever_init` survives reset | None |
| `p_call` | `fn(inst, node) -> bool` | No lifecycle; stateless by contract | Strict `True`/`False` |

`p_call` is deliberately separate from `m_call`. Collapsing them would cause
silent wrong-behavior because Python `True`/`False` compare equal to 1/0 and
would match result codes `SE_HALT`/`SE_CONTINUE`. The distinct dispatch path
is load-bearing.

`o_call` vs `io_call` is a semantic distinction that was added to the LuaJIT
port after initial design based on real usage needs. Preserve it.

---

## Events

Events are `(event_id, event_data)` pairs where `event_id` is a string and
`event_data` is a Python dict.

### Reserved event IDs

| event_id | Meaning |
|---|---|
| `"init"` | Lifecycle — sent internally by the engine when a node first becomes initialized |
| `"tick"` | Heartbeat / polling event (seconds-scale in Python, not milliseconds) |
| `"terminate"` | Lifecycle — sent when a node is being torn down |

User event IDs are any other string. Convention: lowercase with `.` or `:` or
`_` separators (e.g., `"sensor.temperature.updated"`, `"operator:cmd:start"`).

### Event data

`event_data` is a plain Python dict. By convention, timestamped events include
a `"timestamp"` key with a 64-bit monotonic nanosecond value. Tick events
always include this. Non-tick events may include it if the producer chooses.

Timing operators look up `event_data.get("timestamp")`. If absent, they fall
back to `inst.module["get_time"]()` at that moment.

### Event queues

Two queues at the engine level:

- **High priority queue** — drained first
- **Normal priority queue** — drained after high is empty

The engine processes one event at a time to completion (no preemption). When
the outer tick function returns, the engine pulls the next event.

Tick events are pushed onto the normal queue by an external timer or
scheduler. The engine itself does not generate ticks.

---

## Return Codes (Three Families)

Return codes exist in three concentric scopes:

| Family | Range | Scope | Meaning |
|---|---|---|---|
| Application | 0–5 | Engine ↔ external caller | Escape up to the system running the engine |
| Function | 6–11 | Tree ↔ tree (nested) | Propagate across tree boundaries inside the engine |
| Pipeline | 12–17 | Node ↔ node inside one tree | Normal sequence/selector/pipeline composition |

Within each family, the 6 codes are:

| Variant | Meaning |
|---|---|
| `*_CONTINUE` (0) | Keep running; not yet complete |
| `*_HALT` (1) | Caller should halt but stay active |
| `*_TERMINATE` (2) | Caller should terminate cleanly |
| `*_RESET` (3) | Caller should reset (reinitialize subtree) |
| `*_DISABLE` (4) | Caller completed successfully; deactivate |
| `*_SKIP_CONTINUE` (5) | Skip the rest of the current pass but stay active |

So 18 total codes:

```
SE_CONTINUE                  = 0
SE_HALT                      = 1
SE_TERMINATE                 = 2
SE_RESET                     = 3
SE_DISABLE                   = 4
SE_SKIP_CONTINUE             = 5

SE_FUNCTION_CONTINUE         = 6
SE_FUNCTION_HALT             = 7
SE_FUNCTION_TERMINATE        = 8
SE_FUNCTION_RESET            = 9
SE_FUNCTION_DISABLE          = 10
SE_FUNCTION_SKIP_CONTINUE    = 11

SE_PIPELINE_CONTINUE         = 12
SE_PIPELINE_HALT             = 13
SE_PIPELINE_TERMINATE        = 14
SE_PIPELINE_RESET            = 15
SE_PIPELINE_DISABLE          = 16
SE_PIPELINE_SKIP_CONTINUE    = 17
```

Match these values exactly to the LuaJIT port. Parent control functions
dispatch differently depending on which family a child returned. In
particular, `SE_FUNCTION_HALT` emerging into a pipeline-scoped parent maps to
`SE_PIPELINE_HALT`. See `se_builtins_flow_control.lua:61-141` for the
canonical dispatch table inside `se_sequence`.

---

## Lifecycle

### Initialization

- All nodes start with `active=True`, `initialized=False`, `ever_init=False`
- Init is **lazy**, fired from inside the dispatch function when a node is
  first invoked. The engine or walker does not eagerly walk the tree to init
- For `m_call`: on first entry, fn is called with `event_id="init"`, then
  immediately called again with the actual event. `initialized` is set between.
- For `o_call`: fn is called (without event args) if `initialized` is False,
  then `initialized` is set True. The fn runs exactly once per activation.
- For `io_call`: same as `o_call` but checks `ever_init` instead. `ever_init`
  survives reset, so the fn runs exactly once per instance lifetime.
- For `p_call`: no init, ever. Pure function.

### Termination

- When a parent terminates a child on `SE_PIPELINE_DISABLE` (or similar
  completion code), it calls the child's fn with `event_id="terminate"` if
  the child was an initialized `m_call`. Oneshots and preds do not receive
  terminate events.
- After terminate returns, the parent clears the child's `initialized`,
  `state`, `user_data`. `active` is also cleared if the child is being
  deactivated.

### Reset

- Resetting a child restores `active=True`, `initialized=False`, `state=0`,
  `user_data=None`. Preserves `ever_init`.
- Recursive reset descends into the subtree and resets every node.
- `children_reset_all` resets all children of a control node.

Mirror helper semantics from LuaJIT `se_runtime.lua:470-545`.

---

## Dispatch

The central dispatcher is `invoke_any(inst, node, event_id, event_data)`:

```
if call_type == "m_call":
    → invoke_main (full lifecycle, returns result code)
elif call_type == "o_call":
    → invoke_oneshot (uses `initialized` flag)
    returns SE_PIPELINE_CONTINUE
elif call_type == "io_call":
    → invoke_oneshot_survives (uses `ever_init` flag)
    returns SE_PIPELINE_CONTINUE
elif call_type == "p_call":
    → invoke_pred (pure bool)
    returns SE_PIPELINE_CONTINUE if True, SE_PIPELINE_HALT if False
```

Control functions (sequence, selector, parallel, etc.) call
`invoke_any` on their children. They **are** the walker — there is no
separate tree traversal machinery. Each control fn decides when and in what
order its children are invoked, what to do with returned codes, and whether
to terminate or reset children.

---

## The Module Dictionary (replaces blackboard)

There is no blackboard abstraction. The module holds a single flat dict at
`module["dictionary"]`. All shared mutable state lives there. Keys are
strings; values are any Python value.

There is no `field_get` / `field_set` accessor abstraction. Node fns access
the dictionary via `inst.module["dictionary"][key]` and
`inst.module["dictionary"][key] = value` directly.

Naming discipline is the responsibility of the DSL and the application. The
engine enforces nothing on key naming. (Dot-separated names like
`"irrigation.zone1.flow_rate"` are fine by convention; may map to ltree paths
in downstream integration but that's outside the engine's concern.)

## The Module Constants

`module["constants"]` is a `types.MappingProxyType` over a dict populated by
the DSL at compile time. Read-only. Attempts to write raise `TypeError`.

Keys must not collide with `module["dictionary"]` keys. The module loader
should check this and fail at load time if there is overlap.

---

## Tree-to-Tree Calls

Simplified from the LuaJIT spawn family. A single primitive supports nested
tree calls:

- Caller fn creates a **child instance** of a tree (separate node state, own
  event queue, shares the module's dictionary and constants — TBD whether the
  dictionary is shared or copied; **shared is the LuaJIT convention**)
- Ticks the child synchronously inside the caller's current event
- Drains the child's internal event queue until complete or suspended
- Returns the result code to the caller's control fn

The child is nested on the Python call stack, not queued for later execution.
The caller's outer event does not return until the child has completed or
suspended with a pipeline code.

See `se_builtins_spawn.lua:tick_with_event_queue` for the drain pattern. Do
**not** port the hash-indexed tree registry, the dictionary-driven dispatch
builtin, or any of the other spawn complexity. A "call this tree" node is
just a user fn (or one thin builtin) that closes over a reference to the
target tree.

---

## Exception Handling

Exceptions from any fn are **hard crashes**:

1. Engine catches at the `invoke_any` boundary (or at the outer tick boundary)
2. If `module["crash_callback"]` is set, call it with context:
   `crash_callback(inst, node, event_id, event_data, exception, traceback)`
3. Procedure exits. No recovery. No error code bubbling. No `FLAG_ERROR`.

The crash callback is for **display / logging only**. It cannot suppress the
crash or influence control flow. It observes, presents (console, log file,
NATS message, whatever the application chooses), and returns. The engine
then re-raises (or otherwise terminates).

Robust operation is the responsibility of the level above the engine —
process supervisor, systemd unit, container orchestrator — not the engine.

---

## DSL Output Format

The DSL is **in-process Python**. DSL functions (`sequence(...)`,
`with_timeout(...)`, etc.) return tree dicts directly. The engine consumes
tree dicts directly. There is no required compile step, no separate emitter
binary, no `.py` file artifact between DSL and engine. Construction and
execution happen in the same Python process.

This enables **dynamic runtime planning**: an LLM, a planner, an operator
command, or any Python code can construct or modify trees at runtime and
hand them to the engine. The engine has no notion of "compiled" vs. "loaded"
— it just consumes well-formed tree dicts.

### Two Workflows (Same DSL, Same Engine)

#### Workflow A: Dynamic (primary)

DSL functions return tree dicts; pass directly to the engine.

```python
from se_dsl import sequence, guarded_action, with_timeout, log
from se_runtime import new_module, new_instance_from_tree, push_event, run_until_idle
import time

# Construct the module dict (or load it from a registry)
module = new_module(
    dictionary={"zone1_active": False, "flow_rate": 0.0},
    constants={"MAX_FLOW": 10.0},
    fn_registry=user_function_registry,  # name -> callable, for any deserialized trees
)

# Construct a plan at runtime
plan = sequence(
    guarded_action(zone_ready_pred, start_irrigation),
    with_timeout(monitor_flow, seconds=300, on_timeout=alert_operator),
)

# Hand to the engine and run
inst = new_instance_from_tree(module, plan)
push_event(inst, "tick", {"timestamp": time.monotonic_ns()})
run_until_idle(inst)
```

This is the workflow that supports AI-composed plans, runtime plan
splicing, REPL-driven development, plan negotiation over NATS, and
incremental test fixtures.

#### Workflow B: Static-emission (optional)

For cases that want a durable, version-controlled, hand-inspectable plan
artifact, the DSL output can be serialized to a `.py` file:

```python
from se_dsl import sequence, with_timeout, emit_module_file

module = build_irrigation_module()  # constructs the full module dict

emit_module_file(
    module,
    output_path="modules/irrigation_main.py",
    header="# Irrigation control plan, season 2026-04",
)
```

The emitted file is a Python module containing imports and a `MODULE` dict
literal:

```python
# Irrigation control plan, season 2026-04
# Generated <timestamp>. Do not edit by hand.

from se_runtime import (
    SE_CONTINUE, SE_PIPELINE_DISABLE, ...
)
from se_builtins_flow_control import se_sequence, se_if_then_else, ...
from user_functions import zone_ready_pred, start_irrigation, ...

MODULE = {
    "dictionary": {"zone1_active": False, "flow_rate": 0.0},
    "constants": {"MAX_FLOW": 10.0},
    "trees": {
        "main": {
            "fn": se_sequence,
            "call_type": "m_call",
            "params": {},
            "children": [...],
            "active": True, "initialized": False, "ever_init": False,
            "state": 0, "user_data": None,
        },
    },
    "get_time": None,
    "crash_callback": None,
}
```

This file can be:
- Committed to version control as a deployment artifact
- Diff-reviewed across plan revisions
- Imported into another process where the dynamic-construction code is not available
- Loaded by `load_module(MODULE)` exactly as if it had been built dynamically

The static-emission path is a **serialization helper**, not a separate
build pipeline. The DSL functions are the same, the resulting tree dicts
are the same, the engine input is the same. Only the storage/transport
between construction and ticking differs.

#### Workflow B uses Workflow A's DSL

There is no second DSL syntax for static emission. The serializer walks the
tree dict produced by ordinary DSL calls and writes its `repr()` (with
function references rendered as imports). A plan you build dynamically can
always be snapshotted to a file later if you decide it's worth keeping.

### When To Use Which

| Use case | Workflow |
|---|---|
| AI-composed plans | A (dynamic) |
| Runtime plan splicing / negotiation | A (dynamic) |
| Tests, REPL exploration | A (dynamic) |
| Stable, audited deployment plans | B (static-emission) |
| Cross-process plan transfer | B (static-emission) or NATS-serialized dict |
| Long-lived irrigation/SCADA schedules | B (static-emission) for the baseline; A for ad-hoc adjustments |

### Plan Serialization for Network Transport

For NATS / MQTT / file-based plan transfer **without** going through Python
file emission, the tree dict can be serialized as JSON with function
references stored as names:

```python
# Sender
plan = sequence(...)
wire = serialize_tree(plan)   # walks dict, replaces fn objects with fn.__name__
nats.publish("plans.zone1.update", json.dumps(wire))

# Receiver (must have the fn_registry that maps names to callables)
wire = json.loads(msg.data)
plan = deserialize_tree(wire, fn_registry=user_function_registry)
inst = new_instance_from_tree(module, plan)
```

The `fn_registry` is the trust boundary: only fns explicitly registered can
be referenced by name. Arbitrary code execution is not possible — the
serialized form contains only structure and parameter values, never code.

### DSL Function Conventions

DSL functions live in a `se_dsl/` module. Each function returns a node dict
with all required fields populated (use the `make_node()` helper from the
Macros section). DSL functions compose: arguments to a control-node DSL
call are themselves node dicts produced by other DSL calls.

```python
def sequence(*children):
    return make_node(
        fn=se_sequence,
        call_type="m_call",
        params={},
        children=list(children),
    )

def guarded_action(predicate, action):
    return make_node(
        fn=se_if_then_else,
        call_type="m_call",
        params={},
        children=[predicate, action],
    )
```

Macros (Tier 1 templates, Tier 2 patterns) are simply more DSL functions
with richer expansion logic. There is no syntactic distinction between "a
DSL primitive" and "a macro" — both are Python functions returning node
dicts.

---

## Operator Specifications (The Language)

The operators below are the language. Each is defined by: its call type,
its children convention, its params, its return family, and its state.

### Flow Control Operators (`se_builtins_flow_control`)

#### `se_sequence` (m_call)

Executes children in order. Advances when current child completes.

- **Children**: Any mix of call types.
- **Params**: none.
- **State**: `state` = current child index (0-based).
- **Lifecycle**: INIT sets `state=0`. TERMINATE terminates the active child.
- **TICK**: while current child exists, invoke it:
  - `o_call`/`io_call`/`p_call` child → invoke, advance state
  - `m_call` child → invoke; dispatch on result code family:
    - Application code (0–5): propagate unchanged
    - Function code (6–11): propagate; `SE_FUNCTION_HALT` → `SE_PIPELINE_HALT` on the way out
    - `SE_PIPELINE_CONTINUE`/`_HALT`: child still running → return `SE_PIPELINE_CONTINUE` (pause)
    - `SE_PIPELINE_DISABLE`/`_TERMINATE`/`_RESET`: child complete → terminate child, advance
    - `SE_PIPELINE_SKIP_CONTINUE`: pause this tick
- **Return**: `SE_PIPELINE_DISABLE` when all children complete; otherwise `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_flow_control.lua:61-141`.

#### `se_sequence_once` (m_call)

Fires all children in a single tick, then terminates them all.

- **Children**: any mix.
- **Params**: none.
- **State**: `state` (0 before, incremented per child fired).
- **TICK**: iterate all children, fire each one; on non-CONTINUE/non-DISABLE main result, break.
- **Return**: always `SE_PIPELINE_DISABLE` at the end (even if broken early).

Reference: `se_builtins_flow_control.lua:149-202`.

#### `se_function_interface` (m_call)

Top-level parallel dispatcher. All children run in parallel; returns
`SE_FUNCTION_DISABLE` when all main children complete.

- **Children**: any mix.
- **Params**: none.
- **State**: fork state (RUNNING=1, COMPLETE=2).
- **INIT**: reset all children, set state=RUNNING. Return `SE_FUNCTION_CONTINUE`.
- **TERMINATE**: terminate all children, state=COMPLETE.
- **TICK**: invoke each active child; track active count. Returns `SE_FUNCTION_DISABLE` when no mains remain active, else `SE_FUNCTION_CONTINUE`.
- **Return family**: FUNCTION (outermost tree entry point).

Reference: `se_builtins_flow_control.lua:210-289`.

#### `se_fork` (m_call)

Parallel execution. Similar to function_interface but returns pipeline-scoped codes.

- **Children**: any mix.
- **Params**: none.
- **State**: fork state.
- **TICK**: invoke each active main child; handle terminate/reset signals; count active mains.
- **Return**: `SE_PIPELINE_DISABLE` when no mains active; `SE_PIPELINE_CONTINUE` otherwise.
- `SE_FUNCTION_HALT` from a child maps to `SE_PIPELINE_HALT`.

Reference: `se_builtins_flow_control.lua:297-399`.

#### `se_fork_join` (m_call)

Parallel; returns `SE_FUNCTION_HALT` while any main child is still active,
`SE_PIPELINE_DISABLE` when all complete.

- **Children**: any mix.
- **Params**: none.
- **State**: fork state.
- **Semantics**: parent-join. While any main child is running, the fork_join
  halts the pipeline (so nothing after it runs), then releases when the last
  child completes.

Reference: `se_builtins_flow_control.lua:408-490`.

#### `se_chain_flow` (m_call)

ChainTree's canonical "run all active children on every event" operator.
Each active child gets every event until it disables itself.

- **Children**: any mix.
- **Params**: none.
- **State**: none (stateless — walks active children each tick).
- **TICK**: for each active child, invoke. Dispatch:
  - `o_call`/`io_call`/`p_call` → fire and terminate
  - `m_call` → handle result as in `se_sequence`, except `SE_PIPELINE_HALT` (from this child) → return `SE_PIPELINE_CONTINUE` (bubble out of this tick but stay active), and `SE_PIPELINE_RESET` terminates + resets all siblings.
- **Return**: `SE_PIPELINE_DISABLE` when no active children remain; `SE_PIPELINE_CONTINUE` otherwise.

Reference: `se_builtins_flow_control.lua:499-581`.

#### `se_while` (m_call)

Loop: `children[0] = predicate`, `children[1] = body`.

- **Children**: exactly 2 (pred first, body second).
- **Params**: none.
- **State**: 0=EVAL_PRED, 1=RUN_BODY.
- **TICK**:
  - EVAL_PRED: evaluate predicate. False → `SE_PIPELINE_DISABLE` (loop done). True → state=RUN_BODY, fall through.
  - RUN_BODY: invoke body. If body returns DISABLE/TERMINATE → body complete, reset body, state=EVAL_PRED, return `SE_PIPELINE_HALT` (pause, next tick re-eval pred). Otherwise return `SE_FUNCTION_HALT` (body still running).
- **Return**: `SE_PIPELINE_DISABLE` when pred is false; `SE_FUNCTION_HALT` while body runs; `SE_PIPELINE_HALT` between iterations.

Reference: `se_builtins_flow_control.lua:592-648`.

#### `se_if_then_else` (m_call)

- **Children**: 2 or 3. `children[0] = predicate`, `children[1] = then-branch`, `children[2] = else-branch` (optional).
- **Params**: none.
- **State**: 0=EVAL_PRED, 1=RUN_THEN, 2=RUN_ELSE, 3=DONE.
- **TICK**:
  - EVAL_PRED: evaluate pred; choose branch or, if no else branch and pred false, return `SE_PIPELINE_DISABLE`.
  - RUN_THEN/RUN_ELSE: invoke branch; on completion, state=DONE, return `SE_PIPELINE_DISABLE`.

Reference: `se_builtins_flow_control.lua:655-716`.

#### `se_cond` (m_call)

Multi-branch. Children are grouped as `(pred, action, pred, action, ...)` pairs, optionally ending in a single action (else).

- **Children**: pairs of (pred, action), optional trailing action.
- **Params**: `{"has_else": bool}` — whether there's a trailing else action.
- **State**: current evaluated action index (or sentinel for "still searching").
- **TICK**: on first tick, scan predicates in order. First true → state=that action's index. Invoke chosen action until it completes. If no pred true and no else → `SE_PIPELINE_DISABLE` immediately.

Reference: `se_builtins_flow_control.lua:723-834`.

#### `se_trigger_on_change` (pt_m_call → m_call in Python)

Edge-triggered action. `children[0] = predicate`, `children[1] = rising action`, `children[2] = falling action` (optional).

- **Children**: 2 or 3.
- **Params**: `{"initial": 0 or 1}` — initial assumed predicate state.
- **State**: last predicate value (0 or 1).
- **INIT**: state = params["initial"].
- **TICK**: evaluate pred. Compare to last state:
  - Rising edge (was 0, now 1): terminate+reset both actions, invoke rising action.
  - Falling edge (was 1, now 0, has_falling): terminate+reset both actions, invoke falling action.
  - No edge: return `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_flow_control.lua:841-900`.

### Dispatch Operators (`se_builtins_dispatch`)

#### `se_event_dispatch` (m_call)

Routes events by `event_id` string to specific children.

- **Children**: one per mapped event_id.
- **Params**: `{"mapping": {<event_id_string>: <child_index>, ...}}`
- **State**: last-invoked child index (or sentinel).
- **TICK**: look up `event_id` in mapping. Match → invoke that child; no match → `SE_PIPELINE_CONTINUE` (passthrough, subtree unaffected). INIT/TERMINATE propagate to whatever children are active under normal lifecycle rules.

Reference: `se_builtins_dispatch.lua:94-145`.

#### `se_state_machine` (m_call)

State machine where each state is a child. `event_id` + current state selects the transition.

- **Children**: one per state.
- **Params**: `{"transitions": {(state_name, event_id): next_state_name, ...}, "initial": state_name}`
- **State**: current state name.
- **TICK**: if `(current_state, event_id)` is in transitions, transition: terminate current child, set state to next, invoke new child. Else pass event to current child.

Reference: `se_builtins_dispatch.lua:148-268`.

#### `se_field_dispatch` (m_call)

Dispatch based on a dictionary field value rather than event_id.

- **Children**: one per mapped field value.
- **Params**: `{"key": <dict_key>, "mapping": {<value>: <child_index>, ...}}`
- **TICK**: read `inst.module["dictionary"][key]`, look up in mapping, invoke corresponding child (or passthrough if unmapped).

Reference: `se_builtins_dispatch.lua:271-355`.

### Predicate Operators (`se_builtins_pred`)

All are `p_call`, signature `fn(inst, node) -> bool`.

#### Composite predicates (`se_pred_and`, `se_pred_or`, `se_pred_not`, `se_pred_nor`, `se_pred_nand`, `se_pred_xor`)

- **Children**: `p_call` children whose bools are combined.
- `se_pred_and`: True iff all children True. Short-circuits.
- `se_pred_or`: True iff any child True. Short-circuits.
- `se_pred_not`: Requires exactly 1 child; negates.
- `se_pred_nor`: `not or`.
- `se_pred_nand`: `not and`.
- `se_pred_xor`: True iff odd number of children True.

#### Constant predicates

- `se_true` — always True
- `se_false` — always False

#### Event predicate

- `se_check_event` — params: `{"event_id": str}`. Returns True if `inst.current_event_id` matches.

#### Field-comparison predicates

All take params `{"key": <dict_key>, "value": <compare_to>}`:

- `se_field_eq` — True if `dictionary[key] == value`
- `se_field_ne` — `!=`
- `se_field_gt` — `>`
- `se_field_ge` — `>=`
- `se_field_lt` — `<`
- `se_field_le` — `<=`

#### Range predicate

- `se_field_in_range` — params: `{"key", "min", "max"}`. True if `min <= dictionary[key] <= max`.

#### Counter predicates

- `se_field_increment_and_test` — params: `{"key", "threshold"}`. Increments `dictionary[key]` by 1, returns True if `>= threshold`.
- `se_state_increment_and_test` — params: `{"threshold"}`. Increments the node's own `state`, returns True if `>= threshold`.

Reference: `se_builtins_pred.lua`.

### Delay / Timing Operators (`se_builtins_delays`)

#### `se_tick_delay` (m_call)

**Drop from Python port.** Tick-count-based delays don't make sense at
seconds-scale tick rates. Delete this operator. If applications need a
"wait N events" semantic, use `se_verify_and_check_elapsed_events` pattern
with `event_id="tick"`.

#### `se_time_delay` (m_call)

Wait for a duration from activation.

- **Params**: `{"seconds": float}`.
- **State**: `user_data["deadline"]` = init time + seconds.
- **INIT**: compute deadline using `event_data.get("timestamp")` if present else `inst.module["get_time"]()`.
- **TICK**: on each tick event, read `event_data["timestamp"]`; return `SE_PIPELINE_DISABLE` if deadline passed, else `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_delays.lua:85-120`.

#### `se_wait_event` (m_call)

Wait for a specific event.

- **Params**: `{"event_id": str}`.
- **TICK**: returns `SE_PIPELINE_CONTINUE` until matching event arrives; `SE_PIPELINE_DISABLE` when it does.

Reference: `se_builtins_delays.lua:123-157`.

#### `se_wait` (m_call)

Generic wait — suspends until any non-tick event arrives.

- **Params**: `{"include_tick": bool}` — whether tick events count.
- **TICK**: `SE_PIPELINE_CONTINUE` if ignoring ticks; `SE_PIPELINE_DISABLE` on any qualifying event.

Reference: `se_builtins_delays.lua:173-205`.

#### `se_wait_timeout` (m_call)

Wait for a specific event OR a timeout, whichever first.

- **Params**: `{"event_id": str, "seconds": float}`.
- **State**: `user_data["deadline"]`.
- **INIT**: compute deadline.
- **TICK**: if event matches → `SE_PIPELINE_DISABLE`. If deadline passed → `SE_PIPELINE_TERMINATE` (caller sees the distinction between success and timeout via the terminate code). Else `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_delays.lua:208-240`.

#### `se_nop` (m_call)

No-op. Returns `SE_PIPELINE_DISABLE` immediately. Placeholder or alignment.

### Verify Operators (`se_builtins_verify`)

#### `se_verify` (m_call)

Evaluates a predicate every tick; invokes an error action on failure.

- **Children**: `children[0] = predicate`, `children[1] = error oneshot`.
- **Params**: `{"reset_flag": bool}` — on failure, RESET if True else TERMINATE.
- **TICK**: invoke pred child; if False, reset+invoke error child; return `SE_PIPELINE_RESET` or `SE_PIPELINE_TERMINATE`. Else `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_verify.lua:155-183`.

#### `se_verify_and_check_elapsed_time` (m_call)

Runs a subtree with a timeout; fires error on timeout.

- **Children**: `children[0] = error oneshot`.
- **Params**: `{"timeout_seconds": float, "reset_flag": bool}`.
- **State**: `user_data["start_time"]`.
- **INIT**: capture start time.
- **TICK**: if elapsed > timeout, reset+invoke error, return RESET or TERMINATE. Else `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_verify.lua:64-100`.

#### `se_verify_and_check_elapsed_events` (m_call)

Count occurrences of a specific event; fire error if exceeded.

- **Children**: `children[0] = error oneshot`.
- **Params**: `{"target_event_id": str, "max_count": int, "reset_flag": bool}`.
- **State**: `user_data["count"]`.
- **INIT**: count = 0.
- **TICK**: if event_id matches target, increment; if > max, reset+invoke error, return RESET or TERMINATE. Else `SE_PIPELINE_CONTINUE`.

Reference: `se_builtins_verify.lua:109-145`.

### Oneshot Operators (`se_builtins_oneshot`)

All are `o_call` or `io_call` — fire once, no return.

#### Logging

- `se_log` — params: `{"message": str}`. Logs message.
- `se_log_int` — params: `{"message": str, "value": int}`. Logs formatted.
- `se_log_float` — params: `{"message": str, "value": float}`.
- `se_log_field` — params: `{"message": str, "key": str}`. Logs `dictionary[key]`.

Logging destination is pluggable — Python should accept a logger callable on the module (default: `print`).

#### Dictionary writes

- `se_set_field` — params: `{"key": str, "value": Any}`. Writes.
- `se_set_field_float` — alias, Python type coercion makes these equivalent; keep both names for DSL compatibility.
- `se_inc_field` — params: `{"key": str, "delta": int/float}`. In-place increment. Delta defaults to 1.
- `se_dec_field` — params: `{"key": str, "delta": int/float}`. In-place decrement.

**Drop `se_set_hash`, `se_set_hash_field`, `se_set_external_field`, `se_push_stack`, `se_load_function_dict`** — hash-keyed dictionary, external field access, and stack/function-dict are all C-era artifacts not needed in Python.

#### Event emission

- `se_queue_event` — params: `{"event_id": str, "priority": "high"|"normal", "data": dict}`. Pushes an event onto the engine's event queue. Allows trees to generate events consumed by other subtrees.

Reference: `se_builtins_oneshot.lua`.

### Return Code Operators (`se_builtins_return_codes`)

Trivial `m_call` operators that return a fixed code on every tick:

One for each of the 18 codes:
`se_return_continue`, `se_return_halt`, ..., `se_return_pipeline_skip_continue`.

Useful as leaf nodes that inject a specific control code into a sequence.

Reference: `se_builtins_return_codes.lua`.

### Dictionary Operators (`se_builtins_dict`)

The LuaJIT family had many operators because of type-tagged params and hash
keys. In Python, collapse to a minimal set:

- `se_load_dictionary` (io_call) — params: `{"source": dict}`. Merges `source`
  into `inst.module["dictionary"]` at init. Used for startup initialization
  when a tree needs additional dict entries beyond what the DSL emitted.
- **Drop** all the `se_dict_extract_*` typed variants — Python fns just read
  from `inst.module["dictionary"]` directly.
- **Drop** all the `_h` hashed-key variants — keys are strings, Python dict
  handles it.
- **Drop** `se_dict_store_ptr` — pointer semantics are meaningless in Python.

---

## Engine API (public)

### Module construction

```python
# Construct a module dict from explicit parts (dynamic workflow)
mod = se_runtime.new_module(
    dictionary={...},          # initial dict state (will become mutable)
    constants={...},           # immutable; will be wrapped in MappingProxyType
    fn_registry={...},         # name -> callable, for serialized-tree deserialization
    get_time=None,             # defaults to time.monotonic_ns
    crash_callback=None,       # optional
)

# Or load a pre-built module dict (static-emission workflow)
mod = se_runtime.load_module(MODULE_dict)
  # wraps constants in MappingProxyType
  # validates no dict/constants key collision
  # defaults get_time to time.monotonic_ns if None
```

Both produce the same in-memory module shape. `new_module` is the dynamic
construction path; `load_module` is the static-loaded path.

### Tree registration and instance creation

```python
# Register a tree under a name in the module (for tree-to-tree calls by name)
se_runtime.register_tree(mod, "recovery", recovery_tree_dict)

# Create an instance from a registered tree name
inst = se_runtime.new_instance(mod, "main")

# Or create an instance directly from a tree dict (no registration step)
inst = se_runtime.new_instance_from_tree(mod, plan_tree_dict)
  # used when the plan is constructed at runtime and not stored under a name
```

### Event push and tick

```python
# Push an event onto the appropriate queue
se_runtime.push_event(inst, event_id, event_data, priority="normal")
  # priority: "high" or "normal"

# Run one tick event (external caller owns the pump)
result = se_runtime.tick_once(inst, event_id, event_data)
  # runs the outer fn for this one event, to completion
  # drains the internal event queue before returning

# Run the full event loop until queue is empty or completion predicate
se_runtime.run_until_idle(inst)

# Helper: check whether a tree has completed
se_runtime.is_complete(result) -> bool
  # True if result is DISABLE, TERMINATE, or application code < CONTINUE
```

### Plan serialization (for network transport)

```python
# Serialize a tree dict to a wire-safe form (fn objects → name strings)
wire = se_runtime.serialize_tree(plan_dict)
json_str = json.dumps(wire)

# Deserialize from a wire form using a registered fn lookup
plan_dict = se_runtime.deserialize_tree(wire, fn_registry=mod["fn_registry"])
```

The `fn_registry` is the trust boundary for deserialization — only
explicitly registered fns can be referenced.

### Static-emission helper (optional)

```python
# Emit a module dict to a Python file for archival / version control
se_runtime.emit_module_file(
    module_dict,
    output_path="modules/irrigation_main.py",
    header="# Optional comment block at top of file",
)
```

---

## Implementation Order

Recommended build order:

1. **Result codes and event IDs** — just constants
2. **Module constructor** — `new_module`, constants wrapping, validation
3. **Instance constructor** — `new_instance` and `new_instance_from_tree`, event queue initialization
4. **Core dispatch** — `invoke_any`, `invoke_main`, `invoke_oneshot`, `invoke_pred`
5. **Child helpers** — `child_invoke`, `child_terminate`, `child_reset`, `children_reset_all`, `children_terminate_all`
6. **Event queue** — push/pop on high and normal queues
7. **Tick entry point** — `tick_once`, `run_until_idle`
8. **Exception trap and crash callback**
9. **Predicate builtins** (simplest family, no lifecycle)
10. **Return code builtins** (even simpler)
11. **Oneshot builtins** (logging, field writes, event emission)
12. **Flow control builtins** (sequence first, then selector-family, then parallel family, then loop family)
13. **Dispatch builtins** (event, field, state-machine)
14. **Delay builtins** (timestamp-based)
15. **Verify builtins** (timestamp- and event-count-based)
16. **Nested tree-call primitive** (spawn replacement — single function)
17. **DSL functions** — `make_node()` helper, then one DSL function per builtin operator (`sequence`, `selector`, `if_then_else`, etc.) returning fully-formed node dicts
18. **Tier 1 macros** — `with_timeout`, `guarded_action`, `log_and_continue`, etc., as additional DSL functions
19. **Plan serialization** — `serialize_tree` / `deserialize_tree` with `fn_registry` resolution
20. **`load_module()`** — for the static-emission workflow (consumes a pre-built `MODULE` dict)
21. **`emit_module_file()`** — serializes a module dict to a `.py` file (static-emission helper)
22. **Tests** — port `dsl_tests/` progressively using the dynamic workflow

---

## Test Porting Strategy

The LuaJIT port has `dsl_tests/` with worked tree definitions and harnesses.
The test DSL files will need translation to the Python DSL output format, but
the harnesses and expected behaviors transfer directly. Port tests in
ascending complexity:

1. `callback_function` — simplest user fn integration
2. `complex_sequence` — exercises sequence semantics
3. `function_dictionary` — exercises function registration (though Python does this via imports)
4. `dispatch` — exercises event dispatch
5. `external_tree_test` — exercises tree-to-tree calls (nested instances)
6. `advanced_primitive_test` — combinations

Skip tests that exercise stack/quads/equations — those subsystems are not ported.

---

## Macros (DSL-Level, Compile-Time)

Macros are a first-class concept in this DSL because the DSL emits Python
source. **Macros expand at DSL-emit time, not at engine runtime.** The engine
only ever sees fully-expanded trees. This keeps the engine minimal and lets
macros be arbitrarily complex (full Python) without runtime cost.

**Architectural fit.** Trees are data (Python dicts). The DSL is the code
that emits them. A macro is just a DSL function that takes partial node
specs and returns fully-formed node specs (or subtrees). This is exactly how
Lisp macros work — they take expressions, return expressions, get expanded
before evaluation. The S-expression DSL gains genuine Lisp-family power
without any new engine machinery.

**Macros are not call types.** `m_call` / `o_call` / `io_call` / `p_call`
are runtime dispatch categories. Macros are a compile-time mechanism for
emitting nodes of those types. A single macro expansion may produce a tree
containing many nodes of mixed call types — that's just structure, not a
new category.

### Three Tiers of Macro

#### Tier 1: Template Macros (recommended, port now)

Pre-baked subtree shapes with parameters. The 80% case — readable DSL,
reusable patterns, no engine changes.

```python
def with_timeout(action_node, seconds, on_timeout_node):
    """Wrap an action with a timeout error handler."""
    return {
        "fn": se_wait_timeout,
        "call_type": "m_call",
        "params": {"seconds": seconds, "event_id": "completion"},
        "children": [action_node, on_timeout_node],
        "active": True, "initialized": False, "ever_init": False,
        "state": 0, "user_data": None,
    }

def guarded_action(predicate_node, action_node):
    """Run action only if predicate is true."""
    return {
        "fn": se_if_then_else,
        "call_type": "m_call",
        "params": {},
        "children": [predicate_node, action_node],
        "active": True, "initialized": False, "ever_init": False,
        "state": 0, "user_data": None,
    }
```

Usage:

```python
tree = with_timeout(
    action     = guarded_action(zone_ready_pred, start_irrigation_action),
    seconds    = 30,
    on_timeout = log_error_action("Zone start timed out"),
)
```

The DSL emits the fully-expanded tree dict. The engine sees only structure.

**Implementation guidance**: define a `dsl_macros/` directory in the DSL
package. Each macro is a Python function returning a node dict. The DSL
author imports macros and calls them when constructing trees. No magic — the
expansion is just function composition.

#### Tier 2: Pattern Macros (useful, port when needed)

Emit varying structure based on parameters. Loop unrolling, conditional
inclusion, parameterized N-element compositions.

```python
def retry_with_backoff(action_factory, attempts, base_delay_seconds):
    """Generate a sequence of N retry attempts with exponential backoff."""
    children = []
    for i in range(attempts):
        if i > 0:
            delay = base_delay_seconds * (2 ** (i - 1))
            children.append(time_delay(delay))
        children.append(action_factory(attempt=i))
    return sequence(*children)

def state_machine_from_table(transitions, initial_state):
    """Build an se_state_machine from a high-level transition table.

    transitions: list of (from_state, event_id, to_state, action_node) tuples
    """
    states_seen = set()
    state_actions = {}
    transition_map = {}
    for (frm, ev, to, action) in transitions:
        states_seen.update([frm, to])
        state_actions.setdefault(frm, action)  # action runs while in `frm`
        transition_map[(frm, ev)] = to
    children = [state_actions[s] for s in sorted(states_seen)]
    return {
        "fn": se_state_machine,
        "call_type": "m_call",
        "params": {"transitions": transition_map, "initial": initial_state},
        "children": children,
        "active": True, "initialized": False, "ever_init": False,
        "state": 0, "user_data": None,
    }
```

Usage:

```python
tree = retry_with_backoff(
    action_factory     = lambda attempt: connect_to_nats(attempt_num=attempt),
    attempts           = 3,
    base_delay_seconds = 2.0,
)
```

**Caution**: pattern macros that read from `module["constants"]` create
compile-time-vs-runtime confusion. If the constant changes, the DSL must be
re-emitted. Document loudly which constants are macro inputs (compile-time
only) versus which are runtime configuration values.

#### Tier 3: Reader Macros / Syntax Extensions (defer)

Operator overloading or custom parsing for compact DSL surface:

```python
# Instead of:
se_pred_and(p1, se_pred_or(p2, p3))

# Hypothetical reader-macro syntax:
p1 & (p2 | p3)
```

This requires either a custom parser or operator-overloaded predicate-node
classes. **Do not port this in the initial Python port.** Revisit only if
the DSL is being used heavily by people other than the author and the
verbosity becomes a real friction point. The complexity-to-payoff ratio is
unfavorable until then.

### Macro Hygiene

Two rules to keep macros from creating subtle bugs:

1. **Macros must produce nodes with all required fields populated.** A
   helper like `make_node(fn, call_type, params=None, children=None)` that
   fills in `active=True`, `initialized=False`, `ever_init=False`,
   `state=0`, `user_data=None` is the right base layer. All macros build on
   it. Prevents missing-field bugs from creeping in via macro-emitted nodes.

2. **Macros must not share mutable node dicts.** Each call must produce a
   fresh dict tree (deep-construct, not deep-copy of a shared template). A
   shared template would cause runtime state mutations on one node to bleed
   into another instance — the kind of bug that takes days to trace.

### Inspectability

Because macros expand at DSL-emit time, the emitted Python file shows the
fully-expanded tree. A developer reading the generated module file sees
exactly what will run, not a chain of macro calls. This is a feature: the
generated file is the ground truth for debugging, and any macro abstraction
is recoverable by reading the DSL source if needed.

### Implementation Order for Macros

1. Define `make_node()` base helper (Tier 1 prerequisite)
2. Build template macros for the common idioms used in `dsl_tests/`
   (sequence, selector, with_timeout, guarded_action, log_and_continue)
3. Migrate the test DSL files to use the macros — verify the emitted output
   is identical to the hand-written version
4. Add pattern macros only when a specific need arises
5. Defer Tier 3 indefinitely

---

## Open Items / Design Notes — RESOLVED 2026-04-20

All five items below were resolved during implementation. See `s_engine/`
for the as-built code and `s_engine/README.md` for the user-facing surface.

1. **Shared vs. copied module dictionary across nested tree calls.** ✅
   RESOLVED: shared. Child instance created via `call_tree` takes the
   parent's module directly — dictionary, constants, logger, get_time,
   trees registry are all the same objects. No isolation knob added.

2. **Per-event vs. per-tick timestamp semantics.** ✅
   RESOLVED: operators use `event_data.get("timestamp")` with fallback to
   `inst.module["get_time"]()`. Additionally, `invoke_main` now forwards
   the caller's `event_data` into the INIT event (was `{}`), so timer
   operators see the triggering event's timestamp at INIT time.

3. **Crash callback signature.** ✅
   RESOLVED: `crash_callback(inst, node, event_id, event_data, exc, tb)`
   with `tb = traceback.format_exc()`. Callback is observe-only; exception
   re-raises unconditionally. See `se_runtime/tick.py`.

4. **Initial `state` and `user_data` values.** ✅
   RESOLVED: `make_node()` in `se_dsl/__init__.py` emits `state=0` and
   `user_data=None` for all nodes. Operators that need structured
   user_data (timing, state machines, etc.) initialize it in INIT.

5. **Event queue size limit.** ✅
   RESOLVED: unlimited by default; optional cap via
   `module["event_queue_limit"]`. `push_event` raises `OverflowError`
   on overflow.

## Additional design call that surfaced during implementation

6. **`call_tree` must deep-copy the target tree on INIT.** Because the
   Python port keeps per-node dispatch state (`active`, `initialized`,
   `state`, `user_data`) inline on the node dict, invoking the same
   subtree twice — or from two concurrent `call_tree` nodes — would
   clobber state. `se_call_tree` calls `copy.deepcopy(tree)` on INIT.
   `copy.deepcopy` treats fn references atomically (pointer-copies them),
   so behavior is identical but state slots are independent.

7. **`child_terminate` deactivates (not reactivates), and `invoke_main`'s
   self-DISABLE path clears `initialized`/`state`/`user_data`.** Together
   this prevents LuaJIT's double-fire of TERMINATE when a child returns
   DISABLE and the parent then calls `child_terminate`. A reactivation
   step happens explicitly in `children_terminate_all` (matches LuaJIT's
   "terminate-then-reset-all" pattern) and in `child_reset`.

8. **`invoke_pred` strict `bool()` cast.** Prevents a predicate returning
   `1` (truthy int) from being confused with `SE_HALT` (value 1) if the
   predicate were ever dispatched via the m_call path.

---

## Decisions Summary (the incremental chat record)

For traceability, here is the sequence of design decisions that produced this
spec, in the order they were made:

1. System is module-within-module: engine runs one tree; module holds dictionary, constants, trees.
2. Main loop issues logical events; tick is an event with timestamp data.
3. Events carry data dictionaries with `event_id`.
4. No preemption; each event runs outer fn to completion.
5. Two event queues: high priority and normal; high drained first.
6. ChainTree return codes apply (`SE_CONTINUE`, `SE_DISABLE`, etc.).
7. TCL-inspired control — control fns drive traversal.
8. Params are dicts; control nodes direct which children evaluate.
9. All nodes start `active=True`, `initialized=False`.
10. Walker sends init event when `initialized=False`; control fn selects child; walker monitors state and returns code.
11. Dict-per-node state (not parallel `node_states[]` array) — more efficient in Python.
12. Separate boolean flag fields per node (not bitfield).
13. Four call types: `m_call`, `o_call`, `io_call`, `p_call` (dropped `pt_m_call` and `p_call_composite`).
14. Three return code families retained (application / function / pipeline).
15. Tree-to-tree calls follow LuaJIT convention (nested separate instance, synchronous).
16. No blackboard — module dictionary is the shared state.
17. Params are dicts with raw Python values (no type-tagging).
18. Children are directly nested dicts (option A), owned by parent.
19. Module dictionary is flat.
20. Constants are separate from dictionary, immutable, and split at load.
21. Drop stack, quad tree, equation DSL, spawn family from the port.
22. Time is timestamp-based (64-bit monotonic); ticks carry timestamp.
23. Tick events carry a data dictionary; timestamp is a key in that dict.
24. Event IDs are strings.
25. Keep `se_event_dispatch` as a builtin (event subscription spirit preserved).
26. Predicates remain a distinct call type to avoid silent return-code confusion.
27. `o_call` vs `io_call` distinction preserved — important semantic.
28. Exceptions are hard crashes with crash_callback trace.
29. DSL functions return tree dicts; engine consumes tree dicts. Optional `.py` file emission supported.
30. All operators must be ported; this spec specifies them.
31. Macros are added at the DSL layer (compile-time), not the engine. Three tiers: template (port now), pattern (port when needed), reader/syntax (defer).
32. **Python implementation is one-step: DSL functions return tree dicts in-process, engine consumes them directly. No required compile-and-load step. This enables dynamic runtime planning — AI-composed plans, runtime splicing, REPL workflows.**
33. **Static-emission to `.py` files is supported as an optional serialization helper, not a required workflow. Same DSL, same engine input — only the storage between construction and ticking differs.**
34. **Plan transport over network (NATS/MQTT) uses dict serialization with fn names; receiver resolves names via a trusted `fn_registry`. Arbitrary code execution is not possible — wire format contains only structure and parameter values.**

---

## End of Specification
