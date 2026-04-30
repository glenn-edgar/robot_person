# ChainTree Development Roadmap

Live plan for ongoing work on the `chain_tree/` Python port. Updated as items
land or priorities shift. Tier 1 = small/local; Tier 3 = architectural.

For current state and what's already built, see `continue.md`.

---

## Tier 1 — finish the port  ✅ DONE 2026-04-27

All five Tier 1 items landed. Test count 67 → 103 (+36).

| Item | Status | Notes |
|---|---|---|
| **Real-world end-to-end test** (`tests/test_kitchen_sink.py`) | ✅ | Supervised state machine + RPC + streaming + time-window gate; 1 test, 11+ operators |
| **Per-package CLAUDE.md docs** | ✅ | `ct_runtime/`, `ct_builtins/`, `ct_dsl/`, `ct_bridge/` (~85 lines each) |
| **Streaming `collect` + `sink_collected`** | ✅ | `CFL_STREAMING_COLLECT_PACKET` + `_SINK_COLLECTED` + DSL + 6 tests |
| **Controlled-node client timeout** | ✅ | `timeout` / `error_fn` / `reset_flag` kwargs on `asm_client_controlled_node`; 3 added tests |
| **`asm_streaming_verify`** | ✅ | `CFL_STREAMING_VERIFY_PACKET` predicate-on-port assertion + 4 tests |

---

## Tier 2 — runner and persistence  ✅ DONE 2026-04-27

All four items landed. Test count 103 → 129 (+26).

| Item | Status | Notes |
|---|---|---|
| **One-step runner / CLI** | ✅ | New `ct_runner/` package: `python -m ct_runner my_test.py [--var=name] [--starting=k1,k2]`. Uses importlib.util to load the user file, finds the ChainTree by attribute, calls run(); exit 0 on clean drain / 1 otherwise. 8 tests. |
| **Tree serialization** | ✅ | `ct_runtime/serialize.py`: `serialize_tree`, `deserialize_tree`, `serialize_chain_tree`, `deserialize_into`. Internal cross-refs (sm_node / server_node / target_node / parent_node) replaced with `{"_node_ref": <id>}` markers; ct_control/parent/_kb stripped + rebuilt. 6 tests. |
| **`validate(chain_tree)` helper** | ✅ | `ChainTree.validate()` runs unresolved-fn check + structural invariants (exception_handler has 3 children, state_machine declared/defined match, controlled_server has work, sequence_til has marks somewhere) + cross-ref typing (sm_node points to a state_machine, server_node to a controlled_server). `run()` calls it before the loop. 8 tests. |
| **More macros** | ✅ | `retry_until_success` (uses new `asm_mark_sequence_if` helper), `state_machine_from_table` (build SM from `(from, event, to, action)` tuples). Skipped `parallel_actions` (would need a fork operator that's not yet ported). 4 added tests. |

---

## Tier 3 — architectural

Bigger items that change shape, not just add code.

| Item | Effort | Leverage | Why |
|---|---|---|---|
| **DB-backed test storage** — spec mentions but punted: schema (Postgres?), query API (`reference_test("name")` resolves at build time), snapshot/restore semantics | L | high (industrial-first) | Per project goal memory: "Postgres leaves, industrial first." Likely the bridge to real product use |
| **Postgres leaves** — leaf node that runs SQL, writes result to blackboard. Connection pooling, transaction semantics | L | high | Same goal — enables real device-control scenarios |
| **Async event injection** — engine is currently sync polling. Real sensor/UI integration needs an external thread feeding events into `engine.event_queue`. Locking strategy, threadsafe `enqueue` | L | high | Required for any non-test deployment |
| **Performance benchmarks** — measure tick latency, events/sec for typical workloads. Identify hot paths (walker? `terminate_node_tree` DFS twice?) | M | medium | Cheap insurance before someone hits a wall in production |
| **Visualization** — `dump_dot(chain_tree)` → graphviz file showing tree structure + current enabled-state | S | low | Debugging aid |

---

## Open questions for the user

These shape Tier 3 priority order — until answered, Tier 3 items can be picked
opportunistically but the order is uncertain.

1. **What are the "5 new features"** referenced in the project goal memory
   (`Python s-engine port, Python-native, S-expression macros, Postgres leaves,
   5 new features, industrial first`)? Currently unspecified. Knowing them
   would let us add them as Tier 1/2/3 items rather than discovering scope
   later.
2. **What's the industrial-first deployment target?** The first concrete use
   case determines whether the Tier 2 runner or Tier 3 async/DB comes first.
3. **Is the radical-based vocabulary work for s_expression macros**
   (per the now-deleted `project_next_tasks.md` memory item 2) still planned?
   That work is in `s_engine/`, not `chain_tree/`, but it might affect whether
   we expand chain_tree macros now or wait for s_engine's vocabulary changes.

---

## Tier sequencing rationale

- **Tier 1 first** — low risk, finishes the port, creates documentation
  (end-to-end test + CLAUDE.md docs) that helps everything else. Each item
  is ≤1 session.
- **Tier 2 next** — the one-step runner is the highest-leverage missing piece
  for using chain_tree as a real tool. Persistence and validation come along
  for the ride. Each item is 1–2 sessions.
- **Tier 3 last** — these depend on the user's open-question answers and on
  Tier 2's runner being in place (DB storage and async injection both want a
  runner to host them). Each item is multi-session.

Within a tier, prefer items by leverage column (`high` > `medium` > `low`).

---

## Done items

In rough chronological order, with test count at the milestone:

| Milestone | Tests | Notes |
|---|---|---|
| Runtime layer (event queue, walker, engine, termination) | 5 | initial pass; phase-1 filter + pruning bugs caught and fixed |
| Builtins (column, control, wait_time, log, blackboard_set) + DSL (start_test/define_column/asm_*/run) | 15 | first end-to-end: `ChainTree` class drives an actual KB |
| s_engine bridge (3 CFL nodes + 17 cfl_* fns + DSL methods) | 18 | identity-shared blackboard worked-around `new_module` defensive copy |
| `wait_for_event` + `verify` (event-driven wait + assertion) | 23 | `terminate_node_tree` engine bug uncovered + fixed |
| State machine (3 states + transitions + reset/terminate) | 30 | high-pri events to SM; declared-order child reordering at end_state_machine |
| `sequence_til_pass` / `sequence_til_fail` + mark_sequence | 35 | per-spec slow polling pattern; missing-mark raises at runtime |
| Supervisor (3 policies + sliding-window failure counter) | 41 | per-child failure detection; ONE_FOR_ONE / ONE_FOR_ALL / REST_FOR_ALL distinct semantics |
| Exception catch + heartbeat (3-stage MAIN/RECOVERY/FINALIZE) | 49 | "raise then halt" idiom documented; heartbeat-timeout MAIN→RECOVERY |
| Streaming (sink/tap/filter/transform) | 54 | filter-needs-ancestor-target gotcha documented |
| Controlled-node RPC | 57 | client→server→work→response→client cycle; single in-flight per server |
| Boundary timer events (SECOND/MINUTE/HOUR) | 61 | first-tick-no-baseline correctness |
| DSL macros (repeat_n / every_n_seconds / timeout_wrap / guarded_action / wait_then_act) | 67 | starting-point examples; meant to be copied/extended |
| `CFL_TIME_WINDOW_CHECK` + bridge plumbing (engine `get_wall_time`/`timezone` forwarded to s_engine modules) | 89 | 16 unit + 6 integration tests; native + bridged sides agree |
| Kitchen-sink end-to-end test | 90 | supervised SM + RPC + streaming + time-window gate in one scenario |
| Streaming `collect` + `sink_collected` (multi-port join) | 96 | latest-wins per-inport; emits combined `{event_id: packet}` on outport |
| Controlled-node client timeout (`timeout`/`error_fn`/`reset_flag` kwargs) | 99 | mirrors `cfl_wait_main` escalation; removes the "client hangs forever" footgun |
| `asm_streaming_verify` | 103 | predicate-on-port assertion; non-matching events transparent |
| Per-package CLAUDE.md docs (`ct_runtime` / `_builtins` / `_dsl` / `_bridge`) | 103 | ~85 lines each; documents conventions, gotchas, public API |
| One-step CLI runner (`ct_runner/`) | 111 | `python -m ct_runner my_test.py`; importlib.util-based load; 8 tests |
| Tree (de)serialization (`ct_runtime/serialize.py`) | 117 | `_node_ref` ID encoding for internal cross-refs; round-trips through JSON; 6 tests |
| `ChainTree.validate()` build-time helper | 125 | unresolved-fn + structural + cross-ref-type checks; `run()` calls it first; 8 tests |
| Macros: `retry_until_success` + `state_machine_from_table` | 129 | new `asm_mark_sequence_if` helper underpins retry; SM builds from a flat tuple table; 4 tests |

Six subpackages (added `ct_runner`), ~19 test files, 129 tests, no top-level
`__init__.py`, all green (also verified s_engine 190/190 still green at
each step).
