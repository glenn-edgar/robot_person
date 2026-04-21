# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Directory Is

`/home/gedgar/robot_person/chain_tree/` is a staging area for a new port of the ChainTree S-Expression engine. It currently contains **only reference material** under `previous_port/`. There is no buildable or runnable code at this level yet — new-port source will be added here.

The enclosing repo is `/home/gedgar/robot_person/` (`robot_person`). The git root, `.venv`, `enter_venv.sh`, and the canonical Python port all live in the parent directory.

## Canonical Reference (outside this directory)

- **`../s_engine/`** — the **canonical Python port**. If new code here needs to mirror engine semantics, this is the source of truth. Not the LuaJIT port.
- **`../continue.md`** — authoritative design specification. Read before making any engine-level design decisions.
- **`../README.md`** — top-level project layout and status (173 tests passing as of the spec).
- **`../enter_venv.sh`** — `source` this from the repo root to activate `.venv` and set `PYTHONPATH` to `s_engine/`. Required before `pytest tests/` in `s_engine`.

Per `continue.md`: where the LuaJIT port and the Python spec differ, **the Python port wins**. The LuaJIT port carries C-era artifacts (stack machine, quad compiler, FNV-1a hash dispatch, blackboard abstraction, per-node-state parallel arrays) that are deliberately dropped in Python.

## Reference Ports Under `previous_port/`

Both are historical — consult them for semantics, do not modify them as part of forward work unless asked.

### `previous_port/chain_tree_luajit/`

Pure-LuaJIT port of ChainTree (unified behavior tree / state machine / sequential flow engine). Has its own `CLAUDE.md` with detailed module-level notes. Highlights:

- **Two-stage pipeline**: Lua DSL → JSON IR (via `s_build_json.sh`), then JSON IR loaded at runtime by `runtime/cfl_json_loader.lua`. No binary image step.
- **Runtime modules** in `runtime/cfl_*.lua`: `cfl_runtime` (top-level), `cfl_engine` (KB activation, node execution), `cfl_tree_walker` (iterative DFS), `cfl_event_queue` (dual-priority), `cfl_builtins` (all built-in main/boolean/one-shot fns), `cfl_state_machine`, `cfl_streaming`, `cfl_blackboard`, `cfl_timer`.
- **Function signatures** (mirrored by Python port):
  - Main: `fn(handle, bool_fn_idx, node_idx, event_type, event_id, event_data) -> return_code`
  - Boolean: `fn(handle, node_idx, event_type, event_id, event_data) -> bool`
  - One-shot: `fn(handle, node_idx) -> nil`
- **Return codes**: `CFL_CONTINUE(0) CFL_HALT(1) CFL_TERMINATE(2) CFL_RESET(3) CFL_DISABLE(4) CFL_SKIP_CONTINUE(5) CFL_TERMINATE_SYSTEM(6)`.
- **S-Expression subsystem** under `s_expression/` is the closest analogue to the new Python `s_engine` — consult it alongside `../s_engine/` when resolving semantics questions.
- **Tests**: `luajit dsl_tests/incremental_binary/test_cfl.lua [kb_name_or_index|all]` (requires `luajit` and `cjson`).

### `previous_port/chain_tree_python/`

Earlier Python port built around a **YAML intermediate representation** (very different shape from the canonical `s_engine` port, which uses Python dicts directly). Two halves:

- **Build side** (`chain_tree_yaml/chain_tree_build/`): fluent DSL (`ct.asm_log_message`, `ct.asm_wait_time`, `ct.define_column`, …) that emits `basic_tests.yaml`. Entry point: `chain_tree_build_test.py`.
- **Run side** (`chain_tree_yaml/chain_tree_run/`): loads that YAML and executes it. Entry point: `chain_tree_run_test.py`:
  ```python
  ex_sequencer = ExecutionSequencer(yaml_file_name="basic_tests.yaml",
                                    wait_seconds=0.25,
                                    LispSequencer=LispSequencer)
  my_user_functions = MyUserFunctions(execution_sequencer=ex_sequencer)
  ex_sequencer.run_sequencial_tests(ex_sequencer.list_kbs())
  ```
- **User functions** (`chain_tree_user_functions.py`): registered via `es.add_one_shot_function(name, fn, description=...)` / `add_boolean_function(...)` / `add_main_function(...)`. Oneshot signature: `fn(handle, node)`; boolean signature: `fn(handle, node, event_id, event_data)`.
- **LispSequencer** (`s_functions/lisp_sequencer.py`): S-expression control-flow interpreter with three function prefixes — `@void` (side effect), `?boolean` (predicate), `!control` (returns code). Built-in forms: `pipeline`, `dispatch`, `if`, `cond`, `debug`. Supports macros (`define_macro`, `use_macro`, `check_lisp_instruction_with_macros`) and Mako `<%def>` loading (`load_template_defs('file.mako')` — filename only, directory comes from `template_dirs`).
- **Node model**: ltree-style dot-separated paths (e.g. `kb.my_test.GATE_root._0`). Nodes carry `label_dict` (structural: `ltree_name`, `parent_ltree_name`, `links`) and `node_dict` (runtime state).
- **Two copies of `s_functions/`** exist — `common_parts/s_functions/` and `chain_tree_yaml/s_functions/`. They have diverged; the one imported by runnable code is `chain_tree_yaml/s_functions/`.

## Engine Concepts Shared Across All Ports

These shape all three code bases and the spec in `../continue.md`:

- **Three call types**: main (returns a control code), boolean (returns `bool`), one-shot (side effect). The Python `s_engine` splits one-shot into `o_call` (per-activation) and `io_call` (per-instance lifetime).
- **Return-code families** (`s_engine` refinement): Application (0–5, engine ↔ caller), Function (6–11, tree ↔ tree), Pipeline (12–17, node ↔ node). Variants: `_CONTINUE _HALT _TERMINATE _RESET _DISABLE _SKIP_CONTINUE`. Operators remap between families (e.g. `sequence` rewrites child `SE_FUNCTION_HALT` → `SE_PIPELINE_HALT`).
- **Lifecycle**: lazy `INIT` on first dispatch → event dispatch → `TERMINATE` on `PIPELINE_DISABLE`. One event runs the outer tree to completion (no preemption). Two priority queues, high drained first.
- **Exception model** (LuaJIT): 3-stage MAIN → RECOVERY → FINALIZE pipeline with heartbeat monitoring (`CFL_TURN_HEARTBEAT_ON`, `CFL_HEARTBEAT_EVENT`, `CFL_HEARTBEAT_TIMEOUT`). The Python port models this differently — check `continue.md` before porting exception logic.

## Working in This Directory

- No commands build or test anything at this level today. Test/build commands belong to one of the sibling trees (`../s_engine/` via `pytest tests/` from the repo root after sourcing `enter_venv.sh`, or the LuaJIT/legacy-Python references inside `previous_port/`).
- If asked to "port X from the old code" or "mirror Y from the reference": read `../continue.md` first, use `../s_engine/` as the structural template, and consult `previous_port/` only for semantics/tie-breakers. Do not replicate C-era artifacts (stack machine, FNV hashing, flat param arrays, quad compiler, blackboard) in new Python code — they are explicitly dropped.
- The older `previous_port/chain_tree_python/` YAML pipeline is **not** the shape the canonical port takes. Do not copy its YAML IR, ExecutionSequencer, or ltree path scheme into new work unless the user explicitly asks for them.
