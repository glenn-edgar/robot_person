# ChainTree Python Port — Current State

A Python implementation of the ChainTree (CFL) behavior-tree / state-machine /
pipeline engine, bridging into the s_engine S-Expression subsystem at
`../s_engine/`. Status as of 2026-04-27: feature-complete against spec v1
(see `DESIGN.md`); 67 tests pass. Public DSL entry: `from ct_dsl import ChainTree`.

For the original 1414-line design spec — the "why" behind every architectural
choice — see `DESIGN.md` (renamed from this file's predecessor). For the
forward-looking development plan, see `ROADMAP.md`.

---

## Quick start

```bash
source ../enter_venv.sh        # activates venv
cd chain_tree
pytest tests/                  # 67 tests, ~70ms
```

Minimal example:

```python
from ct_dsl import ChainTree

ct = ChainTree(tick_period=0.1)

ct.start_test("hello")
ct.asm_log_message("starting")
ct.asm_wait_time(0.5)
ct.asm_log_message("done")
ct.asm_terminate()
ct.end_test()

ct.run(starting=["hello"])
```

`ChainTree(tick_period=, sleep=, get_time=, logger=, crash_callback=)` — all
constructor args have sensible defaults; tests typically stub `sleep` and
`get_time` for determinism.

---

## Architecture

Five sibling subpackages, each importable as a top-level module
(see Spec Deviation #1 for why no top-level `chain_tree/__init__.py`):

| Package | Role | Key files |
|---|---|---|
| `ct_runtime` | engine, walker, event queue, registry, termination, main loop | `engine.py`, `walker.py`, `event_queue.py`, `registry.py`, `node.py`, `codes.py` |
| `ct_builtins` | CFL_* main / init / term / boolean fns implementing every node type | 12 modules — one per operator family |
| `ct_dsl` | Fluent stateful builder (`ChainTree` class) + parametric macros | `builder.py`, `macros.py` |
| `ct_bridge` | s_engine-side bridge fns registered into module fn_registry | `fns.py` |
| `tests` | Per-feature tests | 12 files, 67 tests |

For each subsystem's design rationale, see `DESIGN.md`.

---

## Operator catalog

| Operator | DSL constructor | One-liner |
|---|---|---|
| Column / fork container | `define_column / end_column` | scans children; CONTINUE while any enabled, else DISABLE |
| Wait time | `asm_wait_time(seconds)` | HALT until elapsed since INIT, then DISABLE |
| Wait for event | `asm_wait_for_event(event_id, count, timeout, error_fn, reset_flag)` | counts target events; on timeout fires error_fn + TERMINATE/RESET |
| Verify (assertion) | `asm_verify(bool_fn, error_fn, reset_flag)` | aux true → CONTINUE, false → fire error_fn + TERMINATE/RESET |
| State machine | `define_state_machine(states, initial)` + `define_state / end_state` + `asm_change_state(sm, target)` | parent of state columns; CFL_CHANGE_STATE_EVENT high-pri toggles which state is enabled |
| Sequence-til pass | `define_sequence_til_pass / asm_mark_sequence_pass(seq) / asm_mark_sequence_fail(seq) / end_sequence_til_pass` | sequential children with early-exit on first pass |
| Sequence-til fail | `define_sequence_til_fail / ... / end_sequence_til_fail` | early-exit on first fail (mirror of pass) |
| Supervisor | `define_supervisor(termination_type, restart_enabled, max_reset_number, reset_window, finalize_fn)` | Erlang-style restart on child failure; ONE_FOR_ONE / ONE_FOR_ALL / REST_FOR_ALL; sliding-window monotonic-time limit |
| Exception handler | `define_exception_handler(boolean_filter_fn, logging_fn) / define_main_column / define_recovery_column / define_finalize_column / asm_raise_exception(id, data) / asm_turn_heartbeat_on(timeout) / asm_heartbeat_event` | 3-stage MAIN→RECOVERY→FINALIZE pipeline; heartbeat timeout escalates MAIN→RECOVERY |
| Streaming sink/tap | `asm_streaming_sink(port, fn) / asm_streaming_tap(port, fn)` | match inport → call user boolean; transparent on no-match |
| Streaming filter | `asm_streaming_filter(port, predicate)` | match inport → predicate False ⇒ CFL_HALT (blocks downstream) |
| Streaming transform | `asm_streaming_transform(inport, outport, fn)` | match inport → user emits transformed packet on outport |
| Controlled-node RPC | `define_controlled_server(req_port, resp_port, handler, response_data) / end_controlled_server` + `asm_client_controlled_node(server, req_port, resp_port, request_data, response_handler)` | client sends request high-pri to server; server activates children, polls, sends response on completion |
| s_engine bridge | `asm_se_module_load(key, trees) / asm_se_tree_create(key, module_key, tree_name) / define_se_tick(tree_key, aux_fn) / end_se_tick` | three-node decomposition; aux fn drives s_engine instance per CFL tick |

**Built-in leaves:** `asm_one_shot(name, data)`, `asm_log_message(msg)`,
`asm_blackboard_set(key, value)`, `asm_terminate()`, `asm_halt()`,
`asm_disable()`, `asm_reset()`, `asm_terminate_system()`, `asm_emit_streaming(target, port, payload)` (test helper).

**Test brackets:** `start_test(name) → root_node` / `end_test()`. A "test" IS a KB; `start_test` returns the root node ref, useful for streaming `target=root` patterns.

---

## DSL macros

Five parametric subtree helpers in `ct_dsl.macros` — free Python functions
taking `ChainTree` as first arg. Meant as starting points; copy/extend
rather than treating as stable API.

| Macro | Use |
|---|---|
| `repeat_n(ct, name, action, count, between_seconds, action_data)` | N copies of an action with optional `wait_time` between |
| `every_n_seconds(ct, name, action, period_seconds, action_data)` | periodic forever via action → wait → asm_reset loop |
| `timeout_wrap(ct, name, build_main, timeout_ticks, on_timeout, on_finalize, logging_fn)` | exception+heartbeat scaffold; caller passes a `build_main(ct)` callback |
| `guarded_action(ct, predicate_fn, action, action_data, error_fn)` | verify + one-shot |
| `wait_then_act(ct, event_id, action, count, action_data)` | wait_for_event + one-shot |

```python
from ct_dsl import macros
macros.repeat_n(ct, "loop", "BUMP", count=5, between_seconds=0.1)
```

---

## Spec deviations

Items where the implementation differs from `DESIGN.md`'s text, with rationale:

1. **No top-level `chain_tree/__init__.py`.** Pytest auto-detects packages by
   `__init__.py` presence and tries to import the parent before `conftest.py`
   can extend `sys.path`, breaking `from ct_runtime import ...` style. Each
   subpackage is its own top-level module instead. Matches sibling
   `s_engine/`'s convention. Public DSL entry: `from ct_dsl import ChainTree`.

2. **`terminate_node_tree` collects ALL enabled nodes**, not enabled+initialized
   per spec. When terminate fires mid-walk (e.g., from a verify failure mid-column),
   sibling nodes the walker hasn't visited yet are enabled-but-uninitialized;
   the spec's filter would leave them enabled and the walker would still visit
   them after the parent was supposedly torn down. `disable_node` already
   handles both cases correctly (init → fire fns; uninit → just clear flag).

3. **`_prune_disabled_kbs` calls `delete_kb`** (which runs `terminate_node_tree`),
   not just `active_kbs.remove`. Per the spec's main-loop pseudo. Without this,
   leftover children from `CFL_TERMINATE` on a root would persist with stale
   enabled flags.

4. **`new_module(dictionary=...)` defensively copies the dict.** For bridge
   identity-sharing, `SE_MODULE_LOAD_INIT` reassigns
   `module["dictionary"] = handle["blackboard"]` after construction. Without
   this reassignment, CFL writes are invisible to s_engine and vice versa.

5. **`asm_raise_exception` is async.** The leaf enqueues a high-priority
   `CFL_RAISE_EXCEPTION_EVENT` and returns `CFL_DISABLE` (yaml-port convention).
   Subsequent siblings in the same column STILL run on the current tick before
   the catch processes the event. Documented "raise then halt" idiom: place
   `asm_halt()` after `asm_raise_exception` to block remaining siblings until
   the catch tears down the MAIN column.

6. **Streaming filter requires emit's target to be an ancestor** of both filter
   and sink. The walker starts at `event["target"]` and descends through
   `enabled_children` — targeting the sink directly bypasses upstream
   filter/transform nodes. For pipelines, target the column root (captured
   from `start_test()` return value); for direct delivery with no upstream,
   target the consumer.

---

## User contracts

Recurring gotchas when writing user fns; see DESIGN.md for the full
spec contracts.

- **Boolean fns are called with `event_id=CFL_TERMINATE_EVENT, event_data=None`**
  during `disable_node` teardown. Filter by event_id (or guard against
  `event_data is None`) — `dict(None)` raises TypeError. Affects every user
  boolean: aux fns, request/response handlers, filters, predicates.
- **`asm_raise_exception` is async** — see deviation #5.
- **Streaming filter target must be ancestor** — see deviation #6.
- **`event_data` is the user's payload dict.** For streaming, the optional
  `_schema` tag is present. For controlled-node, the client's `_client_node`
  ref is added so the server knows where to respond.

---

## Known limitations

| Item | Workaround | Tracked in |
|---|---|---|
| Streaming `collect` / `sink_collected` / `verify` variants not built | Use existing sink/tap/filter/transform | ROADMAP Tier 1 |
| Controlled-node server: single in-flight request per server (client_node ref overwrites) | Spawn a new server per request via supervisor restart | ROADMAP Tier 1 |
| Controlled-node: no exception forwarding to client | Wrap server children in their own exception_handler | — |
| Controlled-node: no client timeout (HALTs forever) | Wrap client in `timeout_wrap` macro | ROADMAP Tier 1 |
| No DSL-level "container" controlled node | Use a regular column | — |
| No explicit fork node type | Use a column; behaviorally equivalent if children CONTINUE rather than HALT | — |
| No one-step CLI runner (build script + run) | Write a Python entry point manually | ROADMAP Tier 2 |
| No tree serialization | Inspect the dict structure directly | ROADMAP Tier 2 |
| DB-backed test storage | TBD | ROADMAP Tier 3 |

---

## Test inventory

12 test files, 67 tests. Run from `chain_tree/`:

```
tests/test_runtime_smoke.py       — 5  walker, queue, terminate ordering, registry validation
tests/test_dsl_smoke.py           — 10 brackets, leaves, stack-balance failures, unresolved fn names
tests/test_se_bridge_smoke.py     —  3 SE module load + tree create + tick; identity-shared blackboard
tests/test_wait_verify.py         —  5 wait_for_event timeout/error_fn; verify pass/fail/reset
tests/test_state_machine.py       —  7 traffic-light cycle, reset, terminate, DSL validation
tests/test_sequence_til.py        —  5 pass/fail polarity, exhaust attempts, missing mark
tests/test_supervisor.py          —  6 ONE_FOR_ONE / ONE_FOR_ALL / REST_FOR_ALL, sliding window
tests/test_exception.py           —  8 normal flow, raise→recovery, filter forward, heartbeat
tests/test_streaming.py           —  5 sink, schema match, filter, transform
tests/test_controlled.py          —  3 round-trip RPC with schema-tagged ports
tests/test_boundary_events.py     —  4 SECOND/MINUTE/HOUR boundary detection
tests/test_macros.py              —  6 repeat_n, every_n_seconds, timeout_wrap, guarded, wait_then_act
```

---

## Resumption — immediate next steps

(See `ROADMAP.md` for Tier 2/3 longer-horizon work.)

1. **End-to-end realistic test** (`tests/test_kitchen_sink.py`): combine ≥6
   operators in one scenario (e.g., supervised state machine with timeout
   recovery + streaming sensor sink + RPC). Surfaces integration bugs the
   per-feature unit tests miss; serves as documentation-by-example.
2. **Per-package CLAUDE.md docs** (4 files, ~80 lines each) for AI agents
   working in `ct_runtime/`, `ct_builtins/`, `ct_dsl/`, `ct_bridge/`.
3. **Streaming `collect` + `sink_collected`** — multi-port packet accumulator;
   completes the streaming family.
4. **Controlled-node `timeout` kwarg** on `asm_client_controlled_node` —
   removes the client-hangs-forever footgun (use `timeout_wrap` internally).

---

## Pointers

- `DESIGN.md` — original 1414-line design spec; the "why" behind every
  architectural choice. Authoritative for semantics questions.
- `ROADMAP.md` — Tier 1/2/3 development plan + open questions for the user.
- `../s_engine/` — the Python S-Expression engine this port bridges into.
- `../continue.md` — parent-level project spec (s_engine + ChainTree port).
- `previous_port/chain_tree_luajit/` — LuaJIT reference port; canonical for
  semantic tie-breakers (per `../CLAUDE.md`).
- `previous_port/chain_tree_python/` — older yaml-IR Python port; useful for
  semantic refs but NOT a structural template (its YAML IR pipeline is the
  shape we explicitly dropped).
