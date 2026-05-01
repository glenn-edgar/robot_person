# CLAUDE.md

Guidance for Claude Code working in `/home/gedgar/robot_person/chain_tree/`.

## What This Directory Is

A working Python port of the ChainTree (CFL) behavior-tree / state-machine /
pipeline engine, bridging into the s_engine S-Expression subsystem at
`../s_engine/`. Tier 1 + Tier 2 of the port are complete (see `ROADMAP.md`).
Tier 3 (Postgres leaves, async event injection, perf, viz) is open.

The enclosing repo is `/home/gedgar/robot_person/`. The git root, `.venv`, and
`enter_venv.sh` live in the parent directory.

## Read these first

- **`continue.md`** — current state, public DSL, operator catalog, spec
  deviations, user contracts. Start here.
- **`DESIGN.md`** — original 1414-line design spec; the "why" behind every
  architectural choice. Authoritative for semantics questions.
- **`ROADMAP.md`** — Tier 1✅ / Tier 2✅ / Tier 3 open + open questions.
- Per-package `CLAUDE.md` in `ct_runtime/`, `ct_builtins/`, `ct_dsl/`,
  `ct_bridge/` — module-level conventions and gotchas.

## Layout

Five top-level subpackages (no top-level `chain_tree/__init__.py` — see
`continue.md` Spec Deviation #1):

| Package      | Role                                                                              |
|--------------|-----------------------------------------------------------------------------------|
| `ct_runtime` | engine, walker, event queue, registry, codes, node, termination, serialize       |
| `ct_builtins`| 12 modules — one per operator family (column, control, wait, state_machine, …)   |
| `ct_dsl`     | `ChainTree` fluent builder (`builder.py`) + parametric subtree macros            |
| `ct_bridge`  | s_engine-side bridge fns registered into module fn_registry                      |
| `ct_runner`  | `python -m ct_runner my_test.py` — importlib-based one-step CLI                  |
| `tests/`     | 19 files, 136 tests, ~0.25s                                                       |

Plus `previous_port/{chain_tree_luajit, chain_tree_python}` — historical
reference, do not modify unless asked.

## Commands

From the repo root:

```bash
source enter_venv.sh           # activates .venv, sets PYTHONPATH=s_engine/
cd chain_tree
pytest tests/                  # 136 tests, ~0.25s
```

`conftest.py` puts this directory on `sys.path` so subpackages import as
top-level modules (matches `s_engine/` convention).

Run a user-built KB:

```bash
python -m ct_runner my_test.py [--var=name] [--starting=k1,k2]
```

Minimal DSL example (full operator catalog in `continue.md`):

```python
from ct_dsl import ChainTree
ct = ChainTree(tick_period=0.1)
ct.start_test("hello")
ct.asm_log_message("starting")
ct.asm_wait_time(0.5)
ct.asm_terminate()
ct.end_test()
ct.run(starting=["hello"])
```

## Canonical reference (outside this directory)

- **`../s_engine/`** — the canonical Python S-Expression port that ChainTree
  bridges into. Source of truth for engine semantics. **Not** the LuaJIT port.
- **`../continue.md`** — parent-level project spec (s_engine + ChainTree port).
- **`../enter_venv.sh`** — venv activation; sets `PYTHONPATH=s_engine/`.

Per `../continue.md`: where the LuaJIT port and the Python spec differ, **the
Python port wins**. The LuaJIT port carries C-era artifacts (stack machine,
quad compiler, FNV-1a dispatch, blackboard abstraction, per-node-state parallel
arrays) that are deliberately dropped in Python — do not replicate them.

## Reference Ports Under `previous_port/`

Both are historical — consult for semantics, do not modify as part of forward
work unless asked.

### `previous_port/chain_tree_luajit/`

Pure-LuaJIT port. Has its own `CLAUDE.md` with detailed module-level notes.
Highlights:

- **Two-stage pipeline**: Lua DSL → JSON IR (via `s_build_json.sh`), then JSON
  IR loaded at runtime by `runtime/cfl_json_loader.lua`.
- **Runtime modules** in `runtime/cfl_*.lua`: `cfl_runtime`, `cfl_engine`,
  `cfl_tree_walker`, `cfl_event_queue`, `cfl_builtins`, `cfl_state_machine`,
  `cfl_streaming`, `cfl_blackboard`, `cfl_timer`.
- **Function signatures** (mirrored by Python port):
  - Main: `fn(handle, bool_fn_idx, node_idx, event_type, event_id, event_data) -> return_code`
  - Boolean: `fn(handle, node_idx, event_type, event_id, event_data) -> bool`
  - One-shot: `fn(handle, node_idx) -> nil`
- **Return codes**: `CFL_CONTINUE(0) CFL_HALT(1) CFL_TERMINATE(2) CFL_RESET(3) CFL_DISABLE(4) CFL_SKIP_CONTINUE(5) CFL_TERMINATE_SYSTEM(6)`.
- **S-Expression subsystem** under `s_expression/` is the closest analogue to
  `../s_engine/` — consult alongside it when resolving semantics questions.
- **Tests**: `luajit dsl_tests/incremental_binary/test_cfl.lua [kb_name_or_index|all]` (requires `luajit` and `cjson`).

### `previous_port/chain_tree_python/`

Earlier Python port built around a **YAML intermediate representation** — a
shape this canonical port explicitly dropped. Two halves:

- **Build side** (`chain_tree_yaml/chain_tree_build/`): fluent DSL emits
  `basic_tests.yaml`. Entry: `chain_tree_build_test.py`.
- **Run side** (`chain_tree_yaml/chain_tree_run/`): loads YAML and executes.
  Entry: `chain_tree_run_test.py`.
- **User functions** (`chain_tree_user_functions.py`): registered via
  `add_one_shot_function` / `add_boolean_function` / `add_main_function`.
  Oneshot signature: `fn(handle, node)`; boolean signature:
  `fn(handle, node, event_id, event_data)`.
- **LispSequencer** (`s_functions/lisp_sequencer.py`): S-expression interpreter
  with three function prefixes — `@void` (side effect), `?boolean` (predicate),
  `!control` (returns code). Built-in forms: `pipeline`, `dispatch`, `if`,
  `cond`, `debug`. Macros + Mako `<%def>` loading.
- **Node model**: ltree-style dot-separated paths (`kb.my_test.GATE_root._0`).
  Nodes carry `label_dict` (structural) and `node_dict` (runtime state).
- Two divergent copies of `s_functions/` exist; runnable code uses
  `chain_tree_yaml/s_functions/`.

Do not copy its YAML IR, ExecutionSequencer, or ltree path scheme into new
work unless the user explicitly asks.

## Engine Concepts Shared Across Ports

These shape all three codebases and the spec:

- **Three call types**: main (control code), boolean (`bool`), one-shot (side
  effect). The Python `s_engine` splits one-shot into `o_call` (per-activation)
  and `io_call` (per-instance lifetime).
- **Return-code families** (`s_engine` refinement): Application (0–5, engine ↔
  caller), Function (6–11, tree ↔ tree), Pipeline (12–17, node ↔ node).
  Variants: `_CONTINUE _HALT _TERMINATE _RESET _DISABLE _SKIP_CONTINUE`.
  Operators remap between families.
- **Lifecycle**: lazy `INIT` on first dispatch → event dispatch → `TERMINATE`
  on `PIPELINE_DISABLE`. One event runs the outer tree to completion (no
  preemption). Two priority queues, high drained first.
- **Exception model**: 3-stage MAIN → RECOVERY → FINALIZE pipeline with
  heartbeat monitoring. ChainTree's `asm_raise_exception` is async (enqueues
  high-pri event + returns DISABLE) — see `continue.md` deviation #5.

## Working here

- Read `continue.md` and the relevant package's `CLAUDE.md` before changing
  engine semantics.
- Use `../s_engine/` as the structural template; consult `previous_port/` only
  for semantics tie-breakers.
- Do not replicate C-era artifacts (stack machine, FNV hashing, flat param
  arrays, quad compiler, blackboard) in new Python code.
- Do not copy the YAML IR pipeline from `previous_port/chain_tree_python/`.
- After non-trivial changes, run `pytest tests/` here AND in `../s_engine/`
  (the bridge can break either side).
