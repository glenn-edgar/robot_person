# ct_runtime

CFL engine core: node shape, dispatch loop, walker, dual-priority event queue,
and the user-function registries. No DSL, no built-in operators, no s_engine
bridge — those live in sibling packages.

## Module map

| Module | Responsibility |
|---|---|
| `codes.py` | All string constants — CFL_* return codes, event IDs, event types, walker signals (CT_*), priorities. Also `is_valid_cfl_code` validator. |
| `node.py` | `make_node` / `link_children` / `enabled_children` / `is_leaf` / `walk_ancestors`. Centralizes the canonical node-dict shape. |
| `event_queue.py` | Dual-priority FIFO (`high` / `normal` deques). High drained first; missing/unrecognized priority defaults to normal. `make_event` constructs the wire-shape dict. |
| `walker.py` | Iterative pre-order DFS. Pure mechanism; holds no engine state. The visit callback returns CT_* signals to steer the walk. |
| `registry.py` | Two parallel registries (CFL-side: main/boolean/one_shot; s_engine-side: m_call/p_call/o_call/io_call) plus `descriptions`. Distinct namespaces — the same name in CFL vs. s_engine doesn't collide. |
| `engine.py` | The dispatch glue: `new_engine`, KB lifecycle (`new_kb`/`add_kb`/`activate_kb`/`delete_kb`), `enable_node` / `disable_node` / `terminate_node_tree`, the `execute_node` per-node logic that translates CFL codes to walker signals, the top-level `run` main loop, and timer / boundary event generation. |

## Public API

The package re-exports the common surface from `__init__.py`. Typical user
entry points:

```python
import ct_runtime as ct

engine = ct.new_engine(tick_period=0.25, get_wall_time=..., timezone=...)
ct.add_main(engine["registry"], "MY_MAIN", my_main_fn)

root = ct.make_node(name="root", main_fn_name="MY_MAIN")
kb = ct.new_kb("k", root)
ct.add_kb(engine, kb)
ct.run(engine, starting=["k"])
```

Most users never touch this directly — the DSL (`ct_dsl.ChainTree`) wraps it.

## Conventions

- **Node identity is the dict reference.** No name registry, no parallel state
  array. A node is found by walking up via `node["parent"]` to the root, which
  carries a `_kb` back-pointer set by `add_kb`.
- **`ct_control` is engine-managed**, `data` is user-facing. Built-in main fns
  read/write `data`; user fns should treat `ct_control` as read-only.
- **Walker signals (`CT_*`) ≠ CFL return codes (`CFL_*`).** `execute_node` is
  the only place that translates between them. Don't return CT_* from a main
  fn or CFL_* from a visit callback.

## Engine lifecycle

`new_engine()` builds a handle holding the event queue, registry, KB table,
and clock callables. `run(engine, starting=[...])` loops:

1. `generate_timer_events` — one CFL_TIMER_EVENT per active KB; plus
   CFL_SECOND/MINUTE/HOUR_EVENT when the wall-clock floor crosses a boundary.
   First tick after activation has no baseline and emits no boundary events.
2. `drain` — process the queue until empty, high-priority first. Events
   enqueued during a drain are picked up in the same drain pass.
3. `_prune_disabled_kbs` — KBs whose root is no longer enabled get a full
   `delete_kb`, which runs `terminate_node_tree` for proper child-before-parent
   teardown.
4. `sleep(tick_period)`.

## Quirks worth knowing

- **`terminate_node_tree` collects ALL enabled nodes**, not enabled+initialized.
  Spec said "+initialized" but that misses uninitialized siblings still listed
  as enabled, which would otherwise re-fire after the parent was supposedly
  torn down.
- **Boolean fns are called with CFL_TERMINATE_EVENT** during `disable_node`
  teardown. They MUST filter that event_id (return False) or you'll get
  phantom counter increments / re-entrant logic. Documented contract; see
  `feedback_terminate_event_filter` memory.
- **CFL_RESET on the root** restarts the whole KB: `terminate_node_tree(root)`
  then `enable_node(root)` and CT_STOP_ALL. CFL_RESET on a non-root resets
  just the parent.
- **`get_wall_time` / `timezone` are engine-level**, not module-level. They're
  used by the time-window wait leaves and forwarded into s_engine modules built via
  the bridge so both sides see the same clock.
- **Crash callback is observe-only.** `_handle_crash` calls it inside a
  `try/except BaseException` so a buggy callback can't suppress the crash;
  exceptions always re-raise out of `execute_node`.

## What lives elsewhere

- Built-in main / boolean / one-shot fns: `ct_builtins/`.
- DSL (fluent `ChainTree` builder + macros): `ct_dsl/`.
- s_engine bridge fns (CFL ↔ s_engine plumbing): `ct_bridge/`.
