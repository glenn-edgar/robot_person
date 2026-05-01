# s_engine — ChainTree S-Expression Engine (Python port)

A Python port of the ChainTree S-Expression behavior-tree engine. Trees are
plain Python dicts; the DSL is in-process Python; the engine is a small set
of pure functions with no external dependencies.

This port is the canonical reference for all non-Zig ports going forward.
Where the LuaJIT port and this spec differ, this code wins — the LuaJIT
port carries C-era artifacts (stack machine, quad compiler, hash dispatch,
pointer slots) that don't belong in Python.

## Quick start

```bash
# one-time: install python3.12-venv (needs sudo)
sudo apt install -y python3.12-venv

# from the repo root
source enter_venv.sh      # activates .venv, sets PYTHONPATH to s_engine/
pytest tests/             # 190 tests should pass
```

## Minimal example

```python
import se_dsl as dsl
from se_runtime import new_module, new_instance_from_tree, push_event, run_until_idle
import time

plan = dsl.sequence(
    dsl.log("starting"),
    dsl.dict_inc("hits", delta=3),
    dsl.if_then_else(
        dsl.dict_gt("hits", 0),
        dsl.dict_set("verdict", "ok"),
        dsl.dict_set("verdict", "zero"),
    ),
)

mod = new_module(dictionary={"hits": 0})
inst = new_instance_from_tree(mod, plan)
push_event(inst, "tick", {"timestamp": time.monotonic_ns()})
run_until_idle(inst)

print(mod["dictionary"])
# → {'hits': 3, 'verdict': 'ok'}
```

## Layout

```
s_engine/
├── README.md              # this file
├── se_runtime/            # engine core
│   ├── codes.py           # 18 return-code constants (3 families)
│   ├── module.py          # new_module, load_module
│   ├── instance.py        # new_instance*, push_event, pop_event
│   ├── dispatch.py        # invoke_any / invoke_main / invoke_oneshot / invoke_pred
│   ├── lifecycle.py       # child_invoke / child_terminate / child_reset helpers
│   ├── tick.py            # tick_once, run_until_idle, crash trap
│   ├── serialize.py       # serialize_tree / deserialize_tree (JSON wire)
│   └── emit.py            # emit_module_file (.py source emission)
├── se_builtins/           # operator implementations
│   ├── flow_control.py    # sequence, fork, chain_flow, while, if_then_else, cond, ...
│   ├── dispatch.py        # event_dispatch, state_machine, dict_dispatch
│   ├── pred.py            # pred_and/or/not, dict_eq/gt/in_range, counters, ...
│   ├── delays.py          # time_delay, wait_event, wait_timeout, nop, ...
│   ├── verify.py          # verify, verify_and_check_elapsed_{time,events}
│   ├── oneshot.py         # log, dict_set, dict_inc, queue_event, dict_load
│   ├── return_codes.py    # 18 m_call leaves, one per code
│   ├── nested_call.py     # se_call_tree (replaces the LuaJIT spawn family)
│   └── time_window.py     # se_wait_until_in/out_of_time_window + se_in_time_window
├── se_dsl/                # DSL wrappers + macros
│   ├── __init__.py        # make_node() + flat public surface
│   ├── primitives.py      # ~67 DSL wrappers, one per builtin
│   └── macros/
│       ├── tier1.py       # template macros: with_timeout, guarded_action, ...
│       └── tier2.py       # pattern macros: retry_with_backoff, state_machine_from_table
└── tests/                 # 190 unit + integration tests
```

## The four concerns

### 1. Construct

```python
import se_dsl as dsl

plan = dsl.sequence(
    dsl.on_event("sensor.ready", dsl.dict_set("state", "armed")),
    dsl.while_loop(dsl.dict_lt("tick_count", 10),
                   dsl.sequence_once(dsl.dict_inc("tick_count"))),
    dsl.log("done"),
)
```

Every DSL call returns a plain Python dict — inspect it, splice it, modify
at runtime, pass to the engine.

### 2. Run

```python
from se_runtime import new_module, new_instance, register_tree
from se_runtime import push_event, tick_once, run_until_idle

mod = new_module(
    dictionary={"tick_count": 0},
    constants={"MAX_FLOW": 10.0},
    logger=print,             # default
    get_time=None,            # monotonic ns; defaults to time.monotonic_ns
    get_wall_time=None,       # Linux 64-bit epoch seconds; defaults to int(time.time())
    timezone=None,            # tzinfo for local-time operators; None = system local
    crash_callback=None,      # optional
)
register_tree(mod, "main", plan)

inst = new_instance(mod, "main")
push_event(inst, "tick", {"timestamp": time.monotonic_ns()})
run_until_idle(inst)
```

### 3. Observe

- `mod["dictionary"]` — mutable shared state; read/write directly
- `mod["constants"]` — immutable (`MappingProxyType`); raises on write
- `mod["logger"]` — any callable; `log()` and `dict_log()` oneshots call it
- `mod["crash_callback"]` — observes fn exceptions then exception re-raises

### 4. Persist / transport

```python
import json
from se_runtime import serialize_tree, deserialize_tree, emit_module_file, load_module
from se_builtins import BUILTIN_REGISTRY

# JSON wire for NATS / MQTT / HTTP
wire = serialize_tree(plan)
msg = json.dumps(wire)
# recipient:
plan = deserialize_tree(json.loads(msg), fn_registry=BUILTIN_REGISTRY)

# Or emit a Python source file for version control
emit_module_file(mod, "modules/irrigation_main.py",
                 header="Irrigation plan, season 2026-04")

# later, in another process:
from modules import irrigation_main
mod = load_module(irrigation_main.MODULE)
```

`fn_registry` is the trust boundary for wire deserialization — only fns
explicitly registered can be referenced. No arbitrary code execution.

## The DSL surface (75 public names)

| Category | Functions |
|---|---|
| **Flow control** (14) | `sequence`, `sequence_once`, `function_interface`, `fork`, `fork_join`, `chain_flow`, `while_loop`, `if_then_else`, `if_then`, `cond`, `case`, `trigger_on_change`, `on_rising_edge`, `on_falling_edge` |
| **Dispatch** (3) | `event_dispatch`, `state_machine`, `dict_dispatch` |
| **Predicates — composite** (6) | `pred_and`, `pred_or`, `pred_not`, `pred_nor`, `pred_nand`, `pred_xor` |
| **Predicates — constants/event** (3) | `true_pred`, `false_pred`, `check_event` |
| **Predicates — dict** (6) | `dict_eq`, `dict_ne`, `dict_gt`, `dict_ge`, `dict_lt`, `dict_le` |
| **Predicates — range/counter** (3) | `dict_in_range`, `dict_inc_and_test`, `state_inc_and_test` |
| **Delays / timing** (5) | `time_delay`, `wait_event`, `wait`, `wait_timeout`, `nop` |
| **Verify / watchdogs** (3) | `verify`, `verify_and_check_elapsed_time`, `verify_and_check_elapsed_events` |
| **Time window** (3) | `wait_until_in_time_window`, `wait_until_out_of_time_window` (m_call wait leaves), `in_time_window` (p_call predicate) |
| **Side effects** (6) | `log`, `dict_log`, `dict_set`, `dict_inc`, `queue_event`, `dict_load` |
| **Return-code leaves** (18) | `return_continue`, `return_disable`, …, `return_pipeline_skip_continue` |
| **Nested trees** (1) | `call_tree(tree_or_name)` |
| **Macros — tier 1** (5) | `with_timeout`, `guarded_action`, `if_dict`, `on_event`, `every_n_ticks` |
| **Macros — tier 2** (2) | `retry_with_backoff`, `state_machine_from_table` |

## User-written functions

Any plain Python callable can be a node. Four shapes:

```python
def my_m_call(inst, node, event_id, event_data) -> int: ...    # returns SE_*
def my_pred(inst, node) -> bool: ...                            # strict bool
def my_o_call(inst, node) -> None: ...                          # fire once per activation
def my_io_call(inst, node) -> None: ...                         # fire once per instance lifetime
```

Wrap with `dsl.make_node(fn, call_type, params=..., children=...)`.

User fns read/write `inst["module"]["dictionary"][key]` directly — no
accessor layer.

## Time-window operators

Three operators for gating on local wall-clock time. Wall clock is read via
`module["get_wall_time"]()` (Linux 64-bit epoch seconds) and converted using
`module["timezone"]` (`None` = system local; pass a `zoneinfo.ZoneInfo` or
`datetime.timezone` to pin it).

| Operator | Call type | Returns | Use |
|---|---|---|---|
| `wait_until_in_time_window(start, end)` | m_call | HALT while OUT, DISABLE on entry | wait inside `chain_flow` / `sequence` until window opens |
| `wait_until_out_of_time_window(start, end)` | m_call | HALT while IN, DISABLE on exit | hold off until window closes — pair after a one-shot to fire once per window |
| `in_time_window(start, end)` | p_call | bool | predicate for `if_then_else`, `cond`, state-machine guards, `on_rising_edge`, etc. Use `pred_not(in_time_window(...))` for the inverse. |

```python
from zoneinfo import ZoneInfo
import se_dsl as dsl

mod = new_module(timezone=ZoneInfo("America/Los_Angeles"), ...)

# Predicate gating — runs the action only during business hours.
plan = dsl.if_then(
    dsl.in_time_window({"hour": 9, "dow": 0}, {"hour": 17, "dow": 4}),
    dsl.log("inside business hours"),
)

# Wait-shaped composition — fire once per business-hours window.
fire_once_per_day = dsl.chain_flow(
    dsl.wait_until_in_time_window({"hour": 9}, {"hour": 17}),
    dsl.log("good morning"),
    dsl.wait_until_out_of_time_window({"hour": 9}, {"hour": 17}),
)
# Wrap in a parent that RESETs `fire_once_per_day` to re-arm next day.
```

Window shape — uniform per-field masks across {hour, minute, sec, dow, dom}:

- Both `start[f]` and `end[f]` present → field ∈ [start[f], end[f]]
  inclusive; wrap allowed when `end[f] < start[f]`
  (e.g. `minute 50..10` means `[50..59] ∪ [0..10]`).
- Both absent → field unconstrained.
- Exactly one present → `ValueError` (paired-or-absent rule).

Final answer = AND of all five per-field checks. Engine code does not write
to `dictionary` — these operators are pure samplers/gates.

## Execution model

- Engine runs one tree instance at a time
- Events are `(event_id: str, event_data: dict)` pairs
- Two priority queues (high drained first)
- One event runs the outer tree to completion (no preemption)
- INIT fires lazily when dispatch first reaches a node
- Lifecycle: INIT → event dispatch → TERMINATE on PIPELINE_DISABLE
- Exceptions are hard crashes; `crash_callback` observes but can't suppress

## Return codes

Three concentric families × 6 variants = 18 codes:

| Family | Range | Scope |
|---|---|---|
| **Application** | 0–5 | Engine ↔ external caller (escape) |
| **Function** | 6–11 | Tree ↔ tree (cross-boundary) |
| **Pipeline** | 12–17 | Node ↔ node within a tree |

Variants: `_CONTINUE` `_HALT` `_TERMINATE` `_RESET` `_DISABLE` `_SKIP_CONTINUE`.

Operator dispatch tables remap between families as needed — e.g.
`se_sequence` rewrites a child's `SE_FUNCTION_HALT` to `SE_PIPELINE_HALT` on
the way out. See `se_builtins/flow_control.py`.

## Tests

```bash
pytest tests/ -v
```

- **Unit tests**: every engine component and every builtin, with dispatch
  tables exercised individually
- **Integration tests** (`tests/test_integration.py`): 7 end-to-end scenarios
  ported from the LuaJIT `dsl_tests/` — callback indirection, fork with
  event generator + waiter, verify watchdogs, wait_timeout, parallel
  dispatch, car-window state machine

190 tests, ~0.1s to run.

## Two operating modes (planned)

The engine is currently a library; the runner layer is not yet built.

- **Standalone exe** — a supervisor generates tick events on a cadence and
  runs the tree to completion
- **Externally fed** — an external source (NATS/MQTT/HTTP/stdin) pushes
  events into a long-lived engine instance

Both modes will share a `se_runtime/runner.py` that wraps `push_event` +
`run_until_idle` with a tick scheduler and graceful shutdown.

## Reference

The design spec lives at `../continue.md`. It documents every operator,
every call-type semantic, every open item, and the decisions that produced
the Python surface.

The LuaJIT reference implementation:
`~/knowledge_base_container/luajit_programs_and_containers/building_blocks/s_expression_luajit/`.
Use `lua_runtime/se_runtime.lua` and
`lua_runtime/se_builtins_flow_control.lua` as the primary references for
dispatch semantics and tie-breaking edge cases.
