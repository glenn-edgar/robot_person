# ChainTree Development Roadmap

Live plan for ongoing work on the `chain_tree/` Python port. Updated as items
land or priorities shift. Tier 1 = small/local; Tier 3 = architectural.

For current state and what's already built, see `continue.md`.

---

## Tier 1 — finish the port

Small, self-contained additions. Each is one session or less.

| Item | Effort | Leverage | Why |
|---|---|---|---|
| **Real-world end-to-end test** (`tests/test_kitchen_sink.py`, ~150 lines): one realistic scenario combining ≥6 operators (e.g., supervised state machine with timeout recovery + streaming sensor sink + RPC) | S | high | Flushes out integration bugs the per-feature unit tests can't see; serves as documentation-by-example |
| **Per-package CLAUDE.md docs** (4 docs, ~80 lines each, for `ct_runtime/`, `ct_builtins/`, `ct_dsl/`, `ct_bridge/`) | S | high | Future AI agents working in the codebase need these; cheap insurance |
| **Streaming `collect` + `sink_collected`** — multi-port packet accumulator | M | medium | Completes the streaming family; the only operator type still incomplete |
| **`asm_streaming_verify`** | S | low | Streaming-aware assertion; nice to have |
| **Controlled-node client timeout** (kwarg on `asm_client_controlled_node`) | S | medium | Removes the "client hangs forever" footgun; can wrap with `timeout_wrap` macro internally |

---

## Tier 2 — runner and persistence

Turn chain_tree from "library you import" into "tool you run."

| Item | Effort | Leverage | Why |
|---|---|---|---|
| **One-step runner / CLI** — `python -m chain_tree my_test.py` style: imports the user file, finds its `ChainTree` instance, runs it, exits with status code based on KB completion | M | very high | The original `project_next_tasks` memory item; turns this into a usable test orchestrator |
| **Tree serialization** — `serialize(chain_tree) → dict` and `deserialize(dict) → chain_tree`, callable references via fn_registry. Mirror s_engine's pattern. | M | medium | Enables snapshot dumping, network transport, debug inspection |
| **`validate(chain_tree)` helper** — separate from `run()`'s fail-fast resolution; also checks structural invariants (e.g., exception_handler has 3 children, state_machine has all states defined). Surfaces bugs at build time with better error messages. | S | medium | Currently each operator's INIT does its own validation; consolidating gives uniform error messages |
| **More macros** — `retry_until_success` (sequence_til + verify), `parallel_actions` (true fork — needs a fork node type if not column-aliased), `state_machine_from_table` | S–M | low | Pure convenience |

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

Five subpackages, ~12 test files, ~67 tests, no top-level `__init__.py`,
all green (also verified s_engine 190/190 still green at each step).
