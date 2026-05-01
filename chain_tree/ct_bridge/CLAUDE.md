# ct_bridge

s_engine-side functions that an s_engine tree calls to reach back into the
CFL engine. The matching CFL-side glue (the three CFL node types
`SE_MODULE_LOAD` / `SE_TREE_CREATE` / `SE_TICK`) lives in
`ct_builtins/se_bridge.py`; this package is exclusively the s_engine-side
half of the boundary.

## Public surface

```python
from ct_bridge import BRIDGE_FN_REGISTRY
```

`BRIDGE_FN_REGISTRY` is the canonical `{name: callable}` map merged into
every s_engine module built by `SE_MODULE_LOAD_INIT`. User-supplied
fn_registries override on name conflict — bridge fns yield to user names.

In-memory s_engine trees can also import the callables directly from
`ct_bridge.fns` and pass them as the `fn` field of `make_node`. Use
direct imports for in-process trees; rely on the registry for serialized
trees that arrive over NATS / from a file.

## Bridge fn signatures

s_engine call types and their canonical signatures:

| Call type | Signature |
|---|---|
| o_call | `fn(inst, node) -> None` |
| io_call | `fn(inst, node) -> None` (fires once per instance lifetime) |
| p_call | `fn(inst, node) -> bool` |
| m_call | `fn(inst, node, event_id, event_data) -> int` (SE_PIPELINE_*) |

All bridge fns find their CFL context via fields stamped on the s_engine
instance by the matching CFL builtins:

```
inst["module"]["dictionary"]    KB blackboard (shared by reference)
inst["_cfl_kb"]                 KB handle
inst["_cfl_engine"]             engine handle
inst["cfl_tick_node"]           the owning se_tick CFL node (None until first tick)
```

`SE_TREE_CREATE_INIT` stamps `_cfl_kb` and `_cfl_engine`; `SE_TICK_MAIN`
stamps `cfl_tick_node` on every tick.

## Available fns

| Group | Fns |
|---|---|
| Child control | `cfl_enable_child`, `cfl_disable_child`, `cfl_enable_children`, `cfl_disable_children`, `cfl_i_disable_children`, `cfl_wait_child_disabled` |
| Bitmap / blackboard | `cfl_set_bits`, `cfl_clear_bits`, `cfl_read_bit`, `cfl_s_bit_and / _or / _nor / _nand / _xor` |
| Internal events | `cfl_internal_event`, `cfl_internal_event_high` |
| Logging | `cfl_log` |

Each fn's `node["params"]` schema is documented inline in `fns.py`.

## How the boundary is shaped

Identity-shared blackboard:

- `SE_MODULE_LOAD_INIT` calls `s_engine.new_module(dictionary=handle["blackboard"])`,
  but `new_module` defensively copies its `dictionary` arg. The init fn
  reassigns `module["dictionary"] = handle["blackboard"]` after construction
  to restore identity-equality. **This is load-bearing**: writes from
  s_engine-side fns must be visible to CFL fns and vice versa with no
  copy-back step.

Engine clock forwarding:

- `SE_MODULE_LOAD_INIT` forwards `engine["get_wall_time"]` and
  `engine["timezone"]` into `new_module`. CFL's wall-clock leaves
  (`cfl_wait_until_in/out_of_time_window`) and s_engine's window operators
  see the same clock and TZ. **The two sides do not share semantics by
  design** — CFL has no sampler/blackboard-write operator; if you need an
  in-window predicate inside an s_engine tree, use s_engine's facilities,
  not the bridge.

Tree-call lifetime:

- `SE_TREE_CREATE_INIT` deep-copies the tree (via s_engine's
  `new_instance_from_tree`) so per-node dispatch state is independent
  across instances. The instance dies when the KB blackboard is dropped;
  Python GC handles cleanup.

## Quirks worth knowing

- **Bridge fns must run inside an `se_tick` MAIN dispatch.** Outside that
  context `inst["cfl_tick_node"]` is None and the helper raises. The
  fn signatures match s_engine's expectation but they are useless when
  invoked from arbitrary s_engine trees that aren't hosted by SE_TICK.
- **User fn names override bridge names** in `BRIDGE_FN_REGISTRY` because
  `SE_MODULE_LOAD_INIT` does `dict(BRIDGE_FN_REGISTRY); user.update(...)`.
  This is intentional — user fn surfaces lock in even if a future bridge
  fn with the same name is added.
- **`cfl_internal_event_high` is a thin wrapper** that copies `node["params"]`
  with `priority="high"` and re-calls `cfl_internal_event`. Priority is
  the only difference; the dispatch path is identical.
