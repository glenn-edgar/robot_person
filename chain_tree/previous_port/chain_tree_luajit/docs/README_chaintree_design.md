# ChainTree: From Behavior Trees to Control Flow Graphs

## The Problem with Behavior Trees

A standard behavior tree (BT) defines a fixed traversal policy at each composite node:

- **Sequence**: tick children left-to-right, stop on failure
- **Selector/Fallback**: tick children left-to-right, stop on success
- **Parallel**: tick all children, succeed/fail based on policy

The tree walker drives execution — it decides which child to visit next based on the composite type. Leaf nodes (actions, conditions) execute and return SUCCESS, FAILURE, or RUNNING.

This works well for reactive AI (game NPCs, robot behaviors) but breaks down for **control flow orchestration** — managing hardware sequences, lifecycle protocols, exception handling, state machines, and streaming pipelines where:

1. A parent needs to **dynamically control** which children run, not follow a fixed policy
2. Children need different **lifecycle phases** (init, run, terminate) with cleanup guarantees
3. The system needs **reset semantics** — restart a subtree without destroying state
4. Multiple unrelated subsystems need to run **concurrently within the same tree**
5. The traversal must work in **bounded memory** on 32KB microcontrollers

## ChainTree's Core Insight

**In ChainTree, nodes are not behavior tree composites — they are control flow functions that manage their children.**

A ChainTree node is a quad of four functions:

```
┌─────────────────────────────────────────┐
│              ChainTree Node             │
│                                         │
│  init_fn()     — called once on enable  │
│  main_fn()     — called every tick      │
│  aux_fn()      — boolean decision fn    │
│  term_fn()     — called on disable      │
│                                         │
│  children[]    — child node links       │
│  parent        — parent node index      │
│  node_data     — JSON payload (ROM)     │
└─────────────────────────────────────────┘
```

The **main function** determines how children are managed:

- `cfl_column_main` — tick children sequentially, disable when all done
- `cfl_fork_main` — tick all children in parallel
- `cfl_state_machine_main` — enable/disable children based on state field
- `cfl_join_main` — wait for a specific sibling to disable
- `cfl_se_engine_main` — tick an s-engine tree, children controlled by the s-engine

The tree walker doesn't know about sequences or selectors. It simply:
1. Visits each enabled node in DFS order
2. Calls the node's main function
3. The main function returns a **walker directive** (`CT_CONTINUE`, `CT_SKIP_CHILDREN`, `CT_STOP_SIBLINGS`, `CT_STOP_ALL`)

This inverts the control: **the parent function decides child execution, not the walker.**

## The Column: Default Sequential Flow

The most common pattern is the **column** — ChainTree's replacement for the behavior tree sequence:

```lua
local col = ct:define_column("mission", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 1: initializing")
    ct:asm_wait_time(5.0)
    ct:asm_log_message("step 2: executing")
    ct:asm_one_shot_handler("DO_WORK", {})
    ct:asm_log_message("step 3: complete")
    ct:asm_terminate_system()
ct:end_column(col)
```

How the column main function works:

```
Column Init:  enable all children
Column Main:  for each child link:
                if child is enabled → return CFL_CONTINUE (keep ticking)
              all children disabled → return CFL_DISABLE (column done)
```

Each child is a leaf node with a main function that returns:
- `CFL_CONTINUE` — "I'm still active, tick me again"
- `CFL_DISABLE` — "I'm done, disable me"
- `CFL_HALT` — "stop processing siblings this tick"

When a leaf returns `CFL_DISABLE`, the column's next tick finds the next enabled child and continues. This creates sequential flow without any sequencing logic in the walker.

**Key difference from behavior trees:** In a BT sequence, the sequence node tracks which child is "current." In ChainTree, there is no cursor — the column simply scans for the first enabled child. A child that finishes disables itself. The column doesn't know or care about ordering — it emerges from the enable/disable pattern.

## The Tree Walker

ChainTree uses an iterative depth-first tree walker optimized for bounded memory:

```
for each tick:
    walk the tree starting from root
    for each node visited:
        if node not enabled → skip node and children
        if node not initialized → call init_fn, set initialized flag
        call main_fn → get return code
        map return code to walker directive:
            CFL_CONTINUE  → CT_CONTINUE (visit children)
            CFL_HALT      → CT_STOP_SIBLINGS (stop this level)
            CFL_DISABLE   → CT_SKIP_CHILDREN (disable, skip subtree)
            CFL_TERMINATE → terminate parent subtree
            CFL_RESET     → terminate and re-init parent
```

The walker needs no heap allocation — it uses a fixed-size stack bounded by the maximum tree depth (typically < 16 levels on embedded systems).

## Node Lifecycle

Every ChainTree node goes through a strict lifecycle:

```
   DISABLED ──enable──→ ENABLED
       │                    │
       │              init_fn() called
       │              aux_fn(INIT) called
       │              INITIALIZED flag set
       │                    │
       │              main_fn() called each tick
       │                    │
       │              returns CFL_DISABLE or
       │              parent terminates subtree
       │                    │
       │              term_fn() called
       │              flags cleared
       │                    │
       └────────────────────┘
```

The init/term guarantee is critical for hardware control — a valve opened in `init_fn` will always be closed in `term_fn`, even if the parent is terminated by an exception handler.

## Parent-Controlled Sequencing

Unlike behavior trees where the composite type determines traversal, ChainTree lets any main function control children arbitrarily:

### State Machine
The state machine main function reads a field value and enables/disables children by index:

```
State Machine Main:
    read state field from blackboard
    if state changed:
        disable current state's children
        enable new state's children
    tick enabled children
```

### Fork (Parallel)
Same implementation as column — enable all children, wait for all to disable:

```
Fork Main:
    for each child: if enabled → return CFL_CONTINUE
    all done → return CFL_DISABLE
```

### Supervisor
Monitors children and restarts them on failure:

```
Supervisor Main:
    if child terminated unexpectedly:
        apply restart strategy (one_for_one, one_for_all, rest_for_all)
        re-enable and re-init affected children
    tick children
```

### S-Engine Composite
Delegates child control to an embedded s-expression engine:

```
SE Engine Main:
    tick s-engine tree
    s-engine calls cfl_enable_child(n) / cfl_disable_children()
    return CFL_CONTINUE (so walker visits the enabled children)
```

## How ChainTree Differs from BTs

| Aspect | Behavior Tree | ChainTree |
|--------|--------------|-----------|
| **Traversal** | Walker decides (sequence/selector/parallel) | Node's main function decides |
| **Child ordering** | Implicit (left-to-right) | Emergent (enable/disable pattern) |
| **Lifecycle** | Leaf returns SUCCESS/FAILURE/RUNNING | Node has init/main/term/aux quad |
| **Cleanup** | None guaranteed | term_fn always called on disable |
| **State** | Blackboard (shared) | Blackboard + per-node arena + JSON data (ROM) |
| **Reset** | Re-run from root | Reset subtree, re-init children |
| **Memory** | Dynamic (recursive) | Fixed (iterative DFS, bounded stack) |
| **Composites** | Fixed set (sequence, selector, parallel) | Any main function = any control flow |
| **Concurrency** | Parallel node only | Any node can enable multiple children |

## The Knowledge Base Pattern

ChainTree organizes tests/programs as **knowledge bases** (KBs). Each KB is an independent tree with its own root gate node. Multiple KBs can be loaded from a single binary image, and the application selects which to run:

```c
cfl_runtime_reset(handle);
cfl_add_test_by_index(handle, 0);   // activate KB 0
cfl_runtime_run(handle);             // tick loop until terminate
```

The gate node at the root selectively enables children based on auto-start flags, allowing incremental test development — comment out tests in the DSL, rebuild, run only what's needed.

## Event System

ChainTree has a two-priority event queue. Events are delivered to all enabled nodes on each tick:

- **Timer events** — generated every tick (CFL_TIMER_EVENT = 4)
- **Second/minute/hour events** — wall-clock aligned
- **Named events** — user-generated, targeted or broadcast
- **Internal events** — posted by nodes to the queue for next tick

The main function receives the event_id and event_data as parameters. Nodes that don't care about events (like columns) ignore them. Nodes that need events (like wait_for_event) check the event_id and act accordingly.

## Memory Model

ChainTree targets 32KB–8GB systems with a layered memory model:

| Allocator | Purpose | Lifetime |
|-----------|---------|----------|
| `cfl_perm` | Permanent bump allocator | Runtime lifetime |
| `cfl_heap` | General heap with coalescing | Dynamic |
| `cfl_heap_arena` | Per-node arena (up to 254) | Node lifetime |
| ROM/Flash | Binary image, JSON data, constants | Eternal |

Node data (JSON payloads, configuration) lives in ROM — zero-copy, no allocation needed. Per-node mutable state is allocated from arenas. The blackboard is allocated from `cfl_perm` at startup.

## Summary

ChainTree is not a behavior tree — it's a **control flow graph engine** where:

1. **Nodes are functions**, not fixed composite types
2. **Parents control children** through enable/disable, not walker traversal
3. **Sequential flow is the default** (column pattern), not a special composite
4. **Lifecycle is guaranteed** — init/term always paired
5. **Memory is bounded** — iterative walker, arena allocators, ROM data
6. **Everything is extensible** — write a new main function, get a new control flow pattern
