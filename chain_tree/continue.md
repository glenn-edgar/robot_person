# ChainTree Python Port — Design Specification

This is the authoritative design spec for a Python port of the full
ChainTree (CFL) engine — behavior trees, state machines, columns,
controlled nodes, exception catch + heartbeat, streaming, templates,
sequence-til, data-flow, etc.

The port lives under `chain_tree/` (this directory). It uses
`../s_engine/` as its embedded S-expression subsystem via a bridge,
analogous to the LuaJIT `runtime/cfl_se_bridge.lua`.

Read this document and the two reference implementations before writing
code:

- **LuaJIT reference** — `previous_port/chain_tree_luajit/runtime/cfl_*.lua`
  (event queue, engine, tree walker, timer, runtime top-level). This is
  the canonical behavior source. Where this spec and the LuaJIT code
  agree, that's the contract.
- **Python S-expression port** — `../s_engine/` — defines the embedded
  S-expression engine that CFL bridges into.

---

## What is dropped from the yaml Python port

The earlier port at `previous_port/chain_tree_python/chain_tree_yaml/`
was targeted at producing a YAML IR that C / Zig / other-language
runtimes could consume. That concern is gone. Specifically:

- **No YAML intermediate.** DSL → executable Python dicts directly.
- **No JSON IR step.** No `cfl_json_loader` equivalent.
- **No ltree string paths** (`kb.my_test.GATE_root._0`). Node identity
  is the Python dict reference itself.
- **No flat node-index array** (luajit's `handle.flash_handle.nodes[i]`
  indexed integer map). Traversal uses Python references directly.
- **No stack machine / quad compiler / FNV-1a hash dispatch /
  blackboard byte-offset abstraction.** All C-era artifacts.
- **No runtime templates.** The yaml port's parametric-subtree feature
  (`template_def` / `end_template_def`, `TemplateFunctions`, per-instance
  `input_data_dict` / `output_data_dict`, `FINALIZE_TEMPLATE_RESULTS`,
  `LOAD_TEMPLATE_DATA`, etc.) is **not** ported. Parametric subtrees
  are instead "macros" — plain Python functions that invoke the fluent
  builder to emit a fresh subtree at build time. See the DSL section
  for details.

---

## Engine model

### Blackboard

Each KB has a Python dict as its blackboard. The blackboard is the
mutable per-KB state everything reads and writes. It is shared by
reference with `s_engine` when that KB invokes an S-expression subtree:
`s_engine_module["dictionary"]` *is* the KB's blackboard dict.

### Multi-KB

Multiple KBs run concurrently on a single engine handle. They share:

- the engine's event queue pair (one pair, not per-KB)
- the wall-clock timer
- the user-function registry

They do **not** share blackboards.

### Event queue

Single shared pair of queues on the engine handle: one **high priority**,
one **normal priority**. LuaJIT uses ring buffers; the Python version
can use `collections.deque` — the buffer data structure is not part of
the contract, only the priority semantics.

**Pop order:** high drained before normal. `pop()` returns the oldest
high-priority event if any exist, otherwise the oldest normal-priority
event.

**Drain discipline:** within one outer iteration, pop and execute until
both queues are empty. Events enqueued *during* event handlers are
processed in the same drain phase (before the next wall-clock sleep).

### Event shape

```python
event = {
    "target":     <node dict>,         # the node the walker starts from
    "event_type": <str>,                # e.g. "CFL_EVENT_TYPE_NULL", "_PTR", "_NODE_ID"
    "event_id":   <str>,                # e.g. "CFL_SECOND_EVENT", "WAIT_FOR_EVENT"
    "data":       <Any>,                # arbitrary payload
    "priority":   "high" | "normal",
}
```

**Every event is directed** at a specific node (`target`). There is no
broadcast sentinel. "Broadcast to all active KBs" is implemented by
iterating active KBs and enqueueing one directed event per KB root.

Timer ticks enqueue one event per active KB, targeted at that KB's
root node dict, at normal priority.

Directed events (e.g., state machine `CFL_CHANGE_STATE`) target a
specific node. `send_immediate_event` = same, but high priority.

### Tick cadence and main loop

The tick period is an input parameter to `engine.create()` in seconds
(fractional allowed, e.g. `0.25`). One wall-clock sleep per outer
iteration.

```python
while engine.has_active_kbs():
    engine.timer_tick()                       # updates wall-clock, computes changed mask
    for kb in engine.active_kbs:
        engine.generate_timer_events(kb, tick_result)   # enqueues CFL_TIMER_EVENT + changed CFL_*_EVENT

    while engine.queue_nonempty():
        event = engine.pop()                  # high first, then normal
        if event["event_id"] == "CFL_TERMINATE_SYSTEM_EVENT":
            engine.shutdown_all()             # terminate every KB, return
            return
        engine.execute_event(event)

    # After drain: any KB whose root is no longer enabled → delete it.
    for kb in list(engine.active_kbs):
        if not engine.node_is_enabled(kb.root):
            engine.delete_kb(kb)

    engine.sleep(engine.delta_time)
```

Mirrors `cfl_runtime.lua` `M.run` with the LuaJIT flat-index loop
replaced by Python references.

### Walker

- Iterative DFS (no recursion).
- Visits **enabled children only** via a `get_forward_enabled_links(node)`
  callback that returns the currently-enabled child list.
- Each visit calls `execute_node(node, event, level)` which runs
  INIT-if-needed, then the main fn, and maps the returned CFL code to a
  walker signal.

Walker signals (port of `CT_*` from `cfl_tree_walker.lua`):
`CT_CONTINUE`, `CT_SKIP_CHILDREN`, `CT_STOP_SIBLINGS`, `CT_STOP_ALL`.

### Per-node state on the node dict

Each node dict carries **two** state sub-dicts, with different
audiences:

- **`node["ct_control"]`** — engine-managed. Engine writes; user fns
  treat as read-only. Minimum shape:
  ```python
  node["ct_control"] = {
      "enabled":     False,
      "initialized": False,
      # result_status / result_data / sequence_state /
      # supervisor_state / exception_state / stream_state / etc.
      # added per feature as those subsystems are specified.
  }
  ```

- **`node["data"]`** — user-facing r/w per-node dictionary. Populated
  at DSL-build time with any node config the user passed
  (`user_data`, `column_data`, function-specific args), and freely
  mutated by the node's own main / boolean / one-shot fns at runtime.
  Private to this node — not implicitly shared with siblings or
  children. Cross-node state belongs in `kb["blackboard"]` instead.

Option A: state lives *on the node dict*. The tree is not shared
across engines; mutating nodes in place is fine and matches the yaml
port's convention. The transient "marked for termination" flag that
LuaJIT uses on `backup_flags[i]` is **not** stored here — it lives in
a local Python list during `terminate_node_tree` and disappears when
the call returns.

### Three layers user fns can touch

```python
def my_fn(handle, node, event_type, event_id, event_data):
    # Per-node private:
    node["data"]["counter"] = node["data"].get("counter", 0) + 1

    # KB-wide shared (same dict as s_engine's module["dictionary"]):
    handle["blackboard"]["sensor_ready"] = True

    # Engine state — read only, engine manages:
    if node["ct_control"]["initialized"]:
        ...
```

### Per-node-type conventions

**Each CFL node type defines its own contract** for how `node["data"]`
is laid out and how the aux fn (if any) is used. The schema of
`node["data"]` and the meaning of aux-fn calls/returns are local to
each node type — not a global convention. Examples from the yaml /
LuaJIT ports:

- `CFL_COLUMN_MAIN` — `node["data"]` holds column config (`auto_start`,
  `column_data`). Aux fn optional; if present, called as an early-out
  boolean.
- `CFL_WAIT_FOR_EVENT_MAIN` — `node["data"]` holds `event_id`,
  `event_count`, `reset_flag`, `timeout`, `error_fn`, `error_data`.
- `CFL_SEQUENCE_PASS_MAIN` / `FAIL_MAIN` — `node["data"]["sequence_state"]`
  holds `current_sequence_index`, `sequence_results`,
  `finalize_fn_name`. Aux fn is an early-out (`True` → `CFL_DISABLE`).
- `CFL_SUPERVISOR_MAIN` — `node["data"]["supervisor_data"]` holds
  restart policy, `max_reset_number`, `reset_window`, etc. Aux fn is
  an early-out.
- `CFL_EXCEPTION_CATCH_MAIN` — `node["data"]["exception_state"]` holds
  stage, catch-links, heartbeat state. Aux fn is the boolean filter
  ("unhandled, forward up" vs "handled here").
- `se_tick` — `node["data"]["return_code"]` is the channel through
  which the aux fn reports its CFL code. Aux fn is the full
  interaction driver.

When specifying a new node type, document its `node["data"]` schema
and aux-fn contract up front. Do **not** assume any global convention.

### Return code → walker signal mapping

Exact mapping from `cfl_engine.lua` `execute_node`:

| CFL return code | Walker signal | Side effect on engine |
|---|---|---|
| `CFL_CONTINUE`         | `CT_CONTINUE`       | — |
| `CFL_HALT`             | `CT_STOP_SIBLINGS`  | — |
| `CFL_SKIP_CONTINUE`    | `CT_SKIP_CHILDREN`  | — |
| `CFL_DISABLE`          | `CT_SKIP_CHILDREN`  | `terminate_node_tree(self)` |
| `CFL_RESET`            | `CT_CONTINUE`       | `terminate_node_tree(parent)`; `enable_node(parent)` |
| `CFL_TERMINATE`        | `CT_SKIP_CHILDREN` (if parent) / `CT_STOP_ALL` (root) | if parent exists: `terminate_node_tree(parent)`; else `disable_node(self)` |
| `CFL_TERMINATE_SYSTEM` | `CT_STOP_ALL`       | `engine.cfl_engine_flag = False`; `terminate_node_tree(start)` |

`CFL_FUNCTION_*` codes from the yaml port (`CFL_FUNCTION_RETURN`,
`CFL_FUNCTION_HALT`, `CFL_FUNCTION_TERMINATE`) are **not** CFL-level
codes in the LuaJIT port. They are bridge-only — an `s_engine` leaf may
return them, and the bridge translates them into CFL codes at the
boundary. The outer walker never sees them directly.

### Termination — single unified path

One function, `terminate_node_tree(subtree_root)`, handles every case:

- Mid-execution subtree teardown (from `CFL_DISABLE`)
- `CFL_RESET`'s parent teardown
- KB-level teardown (from `delete_kb` / `CFL_TERMINATE_SYSTEM`)

The KB teardown is **not** a second path. `delete_kb(kb)` just calls
`terminate_node_tree(kb.root)`.

Because "terminate or reset any subtree at any time" is always allowed,
there can be no pre-computed per-KB pre-order cache — the visit order
must be determined on demand by the walker.

**Phase 1 — record.** Run the walker from `subtree_root` following the
enabled-children callback. The phase-1 visit callback appends each
enabled + initialized node to a local Python list `term_list` in **DFS
pre-order** (root first, then children left-to-right, depth-first).
Already-disabled branches are skipped by the walker; they do not appear
in `term_list`.

**Phase 2 — deliver.** Iterate `term_list` in **reverse**. This is
reverse topological order for the tree: children before parents, later
siblings before earlier siblings. For each node:

1. Clear `node["ct_control"]["enabled"]` and `["initialized"]`.
2. If the node has an aux/boolean function, call it once with
   `event_id = "CFL_TERMINATE_EVENT"` (the terminate event delivery).
3. If the node has a term one-shot function, call it once.

**Short-circuits** (mirror LuaJIT's `disable_node`):

- If `subtree_root` is not initialized, return immediately — nothing to
  tear down.
- If `subtree_root` is a leaf, skip the walker and call the equivalent
  of `disable_node` on it directly.
- Within phase 2, the per-node action is a no-op if the node is somehow
  already not enabled+initialized (defensive, matches LuaJIT).

**Invariant the user cares about:** the terminate event is *always*
delivered to children before parents. The phase-1/phase-2 split
explicitly preserves this.

### `CFL_RESET`

Exactly `terminate_node_tree(parent) + enable_node(parent)`. The parent
is now enabled but not initialized, so the next time the walker reaches
it, INIT fires fresh, then the main fn runs.

### `CFL_TERMINATE_SYSTEM`

Two paths:

- Returned from a main fn → walker gets `CT_STOP_ALL`; engine sets
  `cfl_engine_flag = False`; `terminate_node_tree(event.target)` runs.
- Delivered as an event (`CFL_TERMINATE_SYSTEM_EVENT` in queue) → the
  outer drain loop catches this before dispatching, tears down every
  active KB, and returns from `engine.run()`.

---

## DSL

### Shape — Model A (fluent stateful builder)

A behavior tree is deep and branchy; constructing one with a pure
expression-returning DSL forces awkward nesting. All reference ports
(LuaJIT, C, Zig, old yaml Python) use a fluent stateful builder, and
so does this port.

```python
ct = ChainTree()

ct.start_test("first_test")

col = ct.define_column("activate_valve", auto_start=True)
ct.asm_one_shot("ACTIVATE_VALVE", {"state": "open"})
ct.asm_log_message("Valve activated")
ct.asm_terminate()
ct.end_column(col)

# ... more columns, state machines, controlled nodes, etc.

ct.end_test()
```

The builder maintains an internal push/pop stack representing the
current insertion point. Every `asm_*` call appends a leaf at the
current point; every `define_*` / `end_*` pair pushes and pops a
container.

Bracket pairs carried over from the yaml port (scope to be confirmed):

- `start_test` / `end_test`
- `define_column` / `end_column`
- `define_s_node_control` / `end_s_node_control`
- `controlled_node_container` / `end_controlled_node_container`
- `controlled_node` / `end_controlled_node`
- `state_machine` / `end_state_machine`, `define_state` / `end_state`
- `exception_catch` / `end_exception_catch`, `define_recovery` /
  `end_recovery`, `define_finalize` / `end_finalize`
- `sequence_til` / `end_sequence_til`

### User functions are name-registered Python callables

User functions are plain Python callables. They are **not** DSL trees
(DSL trees are the CFL behavior tree and s_engine subtrees). They are
**not** foreign / FFI functions — they run in the same Python process.
The DSL references them by string name; the engine resolves names
against its registries at load time and fails fast on any unresolved
reference.

Two parallel registries, mirroring the LuaJIT pattern:

**CFL-side registry** — for functions invoked by the CFL walker as
leaf main / boolean / one-shot callbacks:

```python
engine.add_one_shot("ACTIVATE_VALVE",  activate_valve_fn,  description="Opens the valve")
engine.add_boolean ("WHILE_TEST",      while_test_fn)
engine.add_main    ("MY_MAIN",         my_main_fn)
```

**s_engine-side registry** — for functions invoked inside s_engine
subtrees (`m_call`, `p_call`, `o_call`, `io_call` leaves). These are
registered into the s_engine module the same way `s_engine` already
supports via its per-module function tables. Distinct namespace from
CFL-side — the same name may mean different functions in the two
registries without collision.

**Baked into the engine runtime** (users never register these):

- All CFL builtins: `CFL_COLUMN_MAIN`, `CFL_SEQUENCE_PASS_MAIN`,
  `CFL_SUPERVISOR_MAIN`, `CFL_EXCEPTION_CATCH_MAIN`,
  `CFL_STREAMING_SINK_PACKET`, `CFL_CONTROLLED_NODE_MAIN`, etc.
- CFL↔SE bridge oneshots/preds/mains: `CFL_SET_BITS` / `CFL_CLEAR_BITS`
  / `CFL_READ_BIT` / `CFL_S_BIT_AND` / `CFL_ENABLE_CHILDREN` /
  `CFL_INTERNAL_EVENT` / `CFL_WAIT_CHILD_DISABLED` / etc.
- Standard s_engine builtins: `sequence`, `fork`, `while_loop`,
  `dict_eq`, `pred_and`, `log`, `dict_set`, `time_delay`, etc.

### CFL-side function signatures (mirror LuaJIT, Python idioms)

- **Main:** `fn(handle, boolean_fn_name, node, event) -> str`
  (returns a CFL code, e.g. `"CFL_CONTINUE"`)
- **Boolean:** `fn(handle, node, event_type, event_id, event_data) -> bool`
- **One-shot:** `fn(handle, node) -> None`

The `event` parameter is the full event dict described in the Engine
model section.

### s_engine-side function signatures

Per `../s_engine/`:

- **`m_call`:** `fn(inst, node, event_id, event_data) -> int`
  (returns an SE_* code)
- **`p_call`:** `fn(inst, node) -> bool`
- **`o_call`:** `fn(inst, node) -> None` — per-activation
- **`io_call`:** `fn(inst, node) -> None` — per-instance lifetime

### Parameterized subtrees = Python "macros"

Reusable parametric subtrees are just Python functions that, when
called, invoke the fluent builder to emit a subtree:

```python
def retry_column(ct, name, action_fn, max_attempts, wait_seconds):
    col = ct.define_column(name, auto_start=True)
    ct.asm_one_shot("DICT_SET", {"key": "attempts", "value": 0})
    seq = ct.define_sequence_til_pass_node("try")
    for _ in range(max_attempts):
        ct.define_column(f"attempt")
        ct.asm_one_shot(action_fn)
        ct.asm_wait_time(wait_seconds)
        ct.end_column(...)
    ct.end_sequence_node("try")
    ct.end_column(col)
```

Expansion happens at DSL-build time. There is no runtime template
subsystem, no `template_def` DSL bracket, no per-instance
`input_data_dict` / `output_data_dict` / `FINALIZE_TEMPLATE_RESULTS`.
This is the "templates-as-macros" substitute promised in the "dropped"
section above.

### Resolution timing

**Fail-fast at engine load.** When the engine consumes the builder, it
walks every node's function references and verifies each string
resolves to an entry in the CFL-side or s_engine-side registry (as
appropriate for the node type). Any unresolved reference aborts load
with a clear error, before any KB starts running. Matches LuaJIT's
JSON-loader validation step.

---

## Packets, ports, streaming, controlled nodes

The LuaJIT port has an elaborate Avro-packet subsystem (fixed-layout C
structs, 16-byte packed header `timestamp + schema_hash + seq +
source_node`, FFI cdata, FNV-1a schema hashing, `.h` / `_ffi.lua` /
`_bin.h` code generation from `c_avro_packets/avro_dsl.lua`). **All of
that is dropped in Python.** It exists in LuaJIT only because the target
was embedded C with zero-copy wire decode; in-process Python has no use
for it.

### Packet = event-data dict

A "packet" is whatever the user put in `event["data"]`. If typed
multiplexing is useful, the payload self-identifies with a tag:

```python
event["data"] = {
    "_schema": "accelerometer_reading",   # optional; identifies payload shape
    "_source": emitting_node,             # optional; who produced it
    "x": 1.0, "y": 2.0, "z": 9.81,        # application fields
}
```

No FFI, no wire header, no schema-hash generator, no `.h` files.

### Port = Python dict

```python
port = {
    "schema":     "accelerometer_reading",   # str; matched against data["_schema"]
    "handler_id": 0,
    "event_id":   "SENSOR_EVENT",
}
```

Schema is a plain Python string; there is no need for FNV-1a or any
hash since we're in-process. If the user does not want typed
multiplexing, `port["schema"]` may be omitted and only `event_id`
matches.

### Matching predicate

```python
def event_matches(event, port):
    if event["event_type"] != "CFL_EVENT_TYPE_STREAMING_DATA":
        return False
    if event["event_id"] != port["event_id"]:
        return False
    if "schema" in port and event["data"].get("_schema") != port["schema"]:
        return False
    return True
```

### Streaming node types

Carried over from LuaJIT, implemented as CFL builtins on top of
`event_matches`. Semantics unchanged — only the matching implementation
is different.

| Node | Main function | Behavior |
|------|---------------|----------|
| Sink | `CFL_STREAMING_SINK_PACKET` | match inport → call user boolean |
| Tap | `CFL_STREAMING_TAP_PACKET` | match inport → call user boolean (non-blocking observation) |
| Filter | `CFL_STREAMING_FILTER_PACKET` | match inport → call user boolean → `False` returns `CFL_HALT` |
| Transform | `CFL_STREAMING_TRANSFORM_PACKET` | match inport → call user boolean (user transforms + emits on outport) |
| Collect | `CFL_STREAMING_COLLECT_PACKETS` | match any of N inports → accumulate → emit collected event when full |
| Sink-collected | `CFL_STREAMING_SINK_COLLECTED_PACKETS` | match collected event → call user boolean → reset container |
| Verify | `CFL_STREAMING_VERIFY_PACKET` | delegate to user boolean for matched packets |

### Emitting a streaming event

```python
engine.enqueue({
    "target":     consumer_node,
    "event_type": "CFL_EVENT_TYPE_STREAMING_DATA",
    "event_id":   port["event_id"],
    "data":       packet_dict,
    "priority":   "normal",
})
```

Same as any other CFL event. No special code path.

### Controlled nodes (client-server RPC)

Built entirely on top of directed CFL events with dict payloads. Client
enqueues a **request** event targeting the server node; server
processes and enqueues a **response** event targeting the client node.
If the user wants typed ports, request/response payloads carry
`_schema` tags and the matcher is `event_matches`. If not, the payload
is a plain dict and matching is just `event_type + event_id`.

This means controlled nodes and streaming nodes are **the same
mechanism at the core** — directed events with dict payloads and
optional typed-port matching. The difference is only in the node-type
semantics layered on top (one-shot RPC activation vs. pipeline
matching).

### Dropped from LuaJIT

- `c_avro_packets/avro_dsl.lua` and all generated `.h` / `_ffi.lua` /
  `_bin.h` artifacts
- `cfl_avro_header_t` packed struct
- FNV-1a schema hash computation (use Python string equality)
- `get_schema_hash` FFI cdata path — payloads are always Python dicts
- Signed/unsigned hash comparison gymnastics

---

## Supervisor and sequence-til

Three specialized parent-main builtins carried over from the yaml and
LuaJIT ports. None require new engine primitives — they are pure
orchestration on top of enable/disable, timer-tick dispatch, per-node
`ct_control` state, and `terminate_node_tree`.

### Supervisor (`CFL_SUPERVISOR_MAIN`)

Erlang/OTP-style supervisor. Monitors children; when all have finished,
consults restart policy and optionally restarts them.

- **Trigger:** `event_id == "CFL_TIMER_EVENT"`. Other events pass with
  `CFL_CONTINUE`.
- **Aux boolean** (if defined) fires first. Returning `True` disables
  the supervisor. Returning `False` falls through to the scan.
- **Scan:** iterate child links; if any child still `enabled`, return
  `CFL_CONTINUE`.
- **When all children done:** increment `reset_count`; fire finalize
  one-shot (if configured).
  - If `restart_enabled` is false → `CFL_DISABLE`.
  - If `restart_enabled` is true and `reset_limited_enabled` is true
    and `reset_count >= max_reset_number` (within the sliding window)
    → `CFL_DISABLE`.
  - Else → re-enable children according to the termination policy and
    return `CFL_CONTINUE`.
- **Termination policies** (select per-supervisor at define time):
  - `ONE_FOR_ONE` — restart only the children that disabled (yaml port
    treats the common case of all-done identically; single-child
    restart is implicit from per-child disable events).
  - `ONE_FOR_ALL` — terminate any still-running sibling, then restart
    all children.
  - `REST_FOR_ALL` — terminate and restart the failing child and all
    children *after* it in declaration order.

### Sliding-window failure counter

Carry over `SupervisorFailureCounter` from the yaml port almost
verbatim (`previous_port/chain_tree_python/chain_tree_yaml/chain_tree_run/ct_run/supervisor_failure_counter.py`).
Two changes:

- Replace `datetime.now()` with `time.monotonic()` so the time source
  matches `../s_engine/`'s default (`time.monotonic_ns`). Record
  failures as floats (seconds since arbitrary epoch) instead of
  `datetime` objects.
- The sliding window is `reset_window` seconds, measured on monotonic
  time, not wall clock — invariant to system-clock adjustments.

API: `record_failure()`, `record_success()`, `is_threshold_exceeded()`,
`get_failure_count()`, `reset()`.

### `sequence_til_pass` (`CFL_SEQUENCE_PASS_MAIN`)

Sequential children with early-exit on first pass. Used for
retry-with-fallback, "try each strategy until one works."

- **Trigger:** `event_id == "CFL_TIMER_EVENT"`.
- **Per-node state** on `node["ct_control"]["sequence_state"]`:
  ```python
  {
      "current_sequence_index": 0,
      "sequence_results":       [],     # bool per child
      "final_status":           None,
      "finalize_fn_name":       "...",  # optional
  }
  ```
- **Semantics:** active child still enabled → `CFL_CONTINUE`. Once the
  active child disables:
  - Read `sequence_results[current_sequence_index]`.
  - If it's the last child → fire finalize, `CFL_DISABLE`.
  - If it's `False` (child failed) → `terminate_node_tree(active_child)`;
    advance index; enable next child; `CFL_CONTINUE`.
  - If it's `True` (child passed) → fire finalize, `CFL_DISABLE`. (Stop
    with success.)

### `sequence_til_fail` (`CFL_SEQUENCE_FAIL_MAIN`)

Mirror of `sequence_til_pass`. Advance while children pass, stop at
first failure. Used for "all must pass" verification pipelines that
want to report the first failure.

- Same state shape and trigger as `sequence_til_pass`.
- Advance condition is flipped: advance while `final_status == True`;
  stop on `False`.

### `CFL_SEQUENCE_START_MAIN`

Header/container node that wraps the sequence-til pipeline. Functions
like `CFL_COLUMN_MAIN` — enables child links in order. The start node
holds the aggregate status for downstream reporting
(`display_sequence_result`, `collect_to_json`, etc.).

### `CFL_MARK_SEQUENCE` (one-shot)

Child nodes call this to record their pass/fail result before
disabling. Records `(parent_node, link_index, result: bool, data)` into
the parent's `sequence_state.sequence_results[link_index]`. In Python:
takes a direct parent-node dict reference (no ltree string lookup);
no-op if the parent is not a sequence node.

### Sequence result storage

The yaml port has a separate `SequenceDataStorage` class keyed by
ltree strings that collects per-sequence results for reporting
(`display_sequence_result`, `collect_to_json`, `collect_to_list`).

In Python we drop the separate class. Results live on the parent
sequence node's `ct_control`:

```python
parent_node["ct_control"]["sequence_data"] = {
    "processed":         False,
    "results":           [],                  # [{element, status, data}, ...]
    "overall_status":    False,
    "failed_element":    0,
    "finalized_results": {},
}
```

Read/write via helpers in the runtime module (e.g.
`sequence.append_result(parent, child, status, data)`,
`sequence.collect_to_list(parent_root, filter)`).

Tree-building / filtering (the yaml port's `FilteredTreeBuilder`)
becomes a walker pass that collects nodes matching a predicate on
`main_function_name ∈ {"CFL_SEQUENCE_PASS_MAIN",
"CFL_SEQUENCE_FAIL_MAIN", "CFL_SEQUENCE_START_MAIN",
"CFL_SUPERVISOR_MAIN"}`.

### Scope

All three are **in scope for v1.** Cost is low (one main-fn per node
type, one helper module for result storage, one utility class for the
failure counter) and they enable the test-sequencing and
fault-tolerant-column patterns the yaml port already depends on.

---

## Exception catch and heartbeat

Follows the LuaJIT approach exactly. No new engine primitives; everything
rides on directed events + `terminate_node_tree` + `enable_node` + per-node
state.

### Three-stage pipeline

An exception-catch node owns three child links:

- `CFL_EXCEPTION_MAIN_LINK` — normal execution path.
- `CFL_EXCEPTION_RECOVERY_LINK` — activated on caught exception or
  heartbeat timeout.
- `CFL_EXCEPTION_FINALIZE_LINK` — activated after MAIN or RECOVERY
  completes, regardless of outcome.

State on `node["ct_control"]["exception_state"]`:

```python
{
    "exception_stage":         "MAIN" | "RECOVERY" | "FINALIZE",
    "catch_links":             {"MAIN": <node>, "RECOVERY": <node>, "FINALIZE": <node>},
    "parent_exception_node":   <node or None>,   # nearest ancestor catch
    "logging_fn_name":         "...",
    "boolean_filter_fn_name":  "...",
    "original_node_id":        <node or None>,   # set when exception handled
    # Heartbeat sub-state (optional):
    "heartbeat_enabled":       False,
    "heartbeat_time_out":      0,
    "heartbeat_count":         0,
    "step_count":              0,
}
```

### Events

Directed events, at the priorities shown:

| Event | Priority | Source | Meaning |
|---|---|---|---|
| `CFL_RAISE_EXCEPTION_EVENT` | **high** | `CFL_RAISE_EXCEPTION` one-shot in any child | Delivered to nearest ancestor catch node; `data = original_raising_node` |
| `CFL_TURN_HEARTBEAT_ON_EVENT` | normal | `CFL_TURN_HEARTBEAT_ON` one-shot | `data = timeout_in_ticks`; enables monitoring |
| `CFL_TURN_HEARTBEAT_OFF_EVENT` | normal | `CFL_TURN_HEARTBEAT_OFF` one-shot | Disables monitoring |
| `CFL_HEARTBEAT_EVENT` | normal | `CFL_HEARTBEAT_EVENT` one-shot (child) | "I'm alive"; resets counter |
| `CFL_SET_EXCEPTION_STEP_EVENT` | normal | step tracking (optional) | Records progress step |
| `CFL_TIMER_EVENT` | normal | timer | Drives heartbeat-timeout check |

### `CFL_EXCEPTION_CATCH_MAIN` behavior

- **On `CFL_RAISE_EXCEPTION_EVENT`:**
  - Run logging one-shot if configured.
  - Call boolean filter fn. If it returns `True` → **not handled here**:
    forward event up (high priority) to `parent_exception_node`; return
    `CFL_DISABLE`. If no parent and filter says not-handled, still
    `CFL_DISABLE` (propagation dead-ends).
  - If filter returns `False` → **handled**:
    - If `exception_stage == "MAIN"`: `terminate_node_tree(catch_links["MAIN"])`;
      set stage to `"RECOVERY"`; `enable_node(catch_links["RECOVERY"])`;
      return `CFL_CONTINUE`.
    - Else (already in RECOVERY or FINALIZE, can't re-handle): forward
      up; return `CFL_DISABLE`.

- **On `CFL_TURN_HEARTBEAT_ON_EVENT`:** set `heartbeat_enabled = True`,
  `heartbeat_time_out = event_data`, `heartbeat_count = 0`; return
  `CFL_CONTINUE`.

- **On `CFL_TURN_HEARTBEAT_OFF_EVENT`:** `heartbeat_enabled = False`;
  `CFL_CONTINUE`.

- **On `CFL_HEARTBEAT_EVENT`:** `heartbeat_count = 0`; `CFL_CONTINUE`.

- **On `CFL_SET_EXCEPTION_STEP_EVENT`:** `step_count = event_data`;
  `CFL_CONTINUE`.

- **On `CFL_TIMER_EVENT`:** if `heartbeat_enabled`, increment
  `heartbeat_count`. If it reaches `heartbeat_time_out` and we're in
  `MAIN`, perform the same `MAIN → RECOVERY` transition as the exception
  path; else `CFL_CONTINUE`.

### `CFL_EXCEPTION_CATCH_ALL_MAIN`

Simpler column-style variant: catches any raise event, logs it, calls
boolean filter; if handled, continues running children; on timer tick
with no enabled children, disables. Used when the three-stage
recovery/finalize distinction isn't needed.

### Parent-exception resolution

At init time, walk up the parent chain from the catch node until you
find another catch node (or hit root). Store that reference on
`exception_state.parent_exception_node`. This is what unhandled
forwards target. Done once, not per-event.

### `CFL_RAISE_EXCEPTION` (one-shot)

Walks up from the calling node's parent chain to find the nearest
exception-catch ancestor, then enqueues a high-priority
`CFL_RAISE_EXCEPTION_EVENT` targeting that node with
`data = <the raising node dict>`. If no ancestor catch is found, the
exception is unhandled — either raise Python-level (crash) or log and
ignore, to be decided.

### DSL

Bracket pair `define_exception_handler` / `end_exception_handler` with
inner `define_main_column` / `define_recovery_column` /
`define_finalize_column` scopes. Leaves: `asm_raise_exception`,
`asm_turn_heartbeat_on(timeout)`, `asm_turn_heartbeat_off`,
`asm_heartbeat_event`. Same surface as yaml port.

---

## Bitmap operations (dict-based)

LuaJIT stores CFL bits in two 64-bit integers (`handle.bitmask` and
`handle.shaddow_bitmask`) and manipulates them with `bor` / `band` /
`lshift`. Python drops the integer representation entirely.

### Per-KB named-bit dictionary

Each KB owns a **named-bit dict**:

```python
kb["bitmap"] = {
    "sensor_ready":   False,
    "valve_open":     True,
    "alarm_active":   False,
    # derived bits live in the same dict — see Data flow below
    "system_armed":   False,
}
```

No integer bitmask, no bit positions. Names only. Missing keys read as
`False` by convention.

### Shadow-bit semantics

LuaJIT distinguishes `bitmask` (the *visible* value read by predicates
this tick) from `shaddow_bitmask` (the value being written this tick).
At the start of each KB's tick, `bitmask` is promoted from
`shaddow_bitmask`. This means reads and writes in the same tick don't
observe each other — stable semantics across concurrent set/clear.

We mirror this with a pair:

```python
kb["bitmap"]        # visible this tick (read-only from predicates)
kb["bitmap_shadow"] # written this tick; promoted to bitmap at tick start
```

`engine.run()` promotes `bitmap_shadow → bitmap` before generating
timer events for that KB each iteration. If this complication proves
unnecessary for v1 workloads, it can collapse to a single `bitmap`
dict — revisit once we have tests.

### Bit operations (CFL builtins / bridge oneshots)

| Name | Args | Behavior |
|------|------|----------|
| `CFL_SET_BITS`   | `*names` | `for n in names: kb["bitmap_shadow"][n] = True` |
| `CFL_CLEAR_BITS` | `*names` | `for n in names: kb["bitmap_shadow"][n] = False` |
| `CFL_READ_BIT`   | `name` (pred) | `return kb["bitmap"].get(name, False)` |
| `CFL_S_BIT_AND`  | `*(names \| child preds)` | `all(resolve(x) for x in args)` |
| `CFL_S_BIT_OR`   | `*(names \| child preds)` | `any(resolve(x) for x in args)` |
| `CFL_S_BIT_NAND` | `*(names \| child preds)` | `not all(...)` |
| `CFL_S_BIT_NOR`  | `*(names \| child preds)` | `not any(...)` |
| `CFL_S_BIT_XOR`  | `*(names \| child preds)` | `sum(1 for x in args if resolve(x)) % 2 == 1` |

Where `resolve(x)` returns `kb["bitmap"].get(x, False)` for a string
name, or the child predicate's return value for a nested composite.

### Relationship to `s_engine` predicates

The `s_engine` port already provides the same semantic family as
first-class builtins:

- `dict_eq` / `dict_ne` / `dict_gt` / `dict_ge` / `dict_lt` / `dict_le`
  / `dict_in_range` — read `inst["module"]["dictionary"][key]` and
  compare.
- `pred_and` / `pred_or` / `pred_not` / `pred_nor` / `pred_nand` /
  `pred_xor` — composite logic over child predicates.

Because we share the KB blackboard with `s_engine` by reference
(`module["dictionary"] is kb["blackboard"]`), an s_engine predicate
tree can read CFL bits directly with no bridge code — **as long as the
bitmap dict lives in the blackboard or is accessible by known key.**

Two integration choices for the bitmap subsystem:

- **A. Store the bitmap at `kb["blackboard"]["_bitmap"]`** — s_engine
  predicates use `dict_eq({"key": ["_bitmap", "sensor_ready"], "value": True})`
  style (requires nested-key support in `dict_*`, not currently in
  s_engine), **or** we write thin CFL-bridge predicates (`CFL_READ_BIT`
  etc.) that look up `kb["bitmap"]` directly and are registered into
  the s_engine module's predicate table.

- **B. Flatten the bitmap into the blackboard itself** —
  `kb["blackboard"]["sensor_ready"] = True`. Then `dict_eq(key="sensor_ready",
  value=True)` works as-is, no bridge code needed.

B is simpler and aligns with s_engine's existing design. The "bitmap"
becomes nothing more than a naming convention for Boolean keys in the
blackboard. Chosen: **B**.

Under B, the CFL-side names (`CFL_SET_BITS`, `CFL_READ_BIT`,
`CFL_S_BIT_*`) become thin wrappers over the same `kb["blackboard"]`
dict — and s_engine trees can use `dict_eq` / `pred_and` directly on
those same keys. One namespace, two vocabularies (CFL naming for
legacy DSL compatibility, s_engine naming for S-expression trees).

---

## Data flow

Data flow in LuaJIT was bitmask-OR of active token bits
(`TokenDictionary.event_mask`). The yaml port simulated that with
auto-assigned integer bit masks (`token_mask[id] = 1, 2, 4, ...`).
**We drop both.** Python uses named Boolean keys in the KB blackboard —
the same dict used for the bitmap subsystem above.

### Source tokens

Any CFL one-shot that writes a Boolean into the blackboard produces a
"token". In practice:

- `CFL_SET_BITS` / `CFL_CLEAR_BITS` set named bits.
- User one-shots write via `kb["blackboard"][name] = value`.
- Events with `event_type == "CFL_EVENT_TYPE_STREAMING_DATA"` can set
  tokens through their sink boolean fn.

### Data-flow expressions

A DF expression evaluates a logical combination of named tokens and
writes the result into a *derived* named key in the same blackboard.
On every tick (or on every mutation, depending on node type), the
expression re-evaluates.

Two equivalent ASTs are supported:

- **List form** (yaml-port compatible):
  ```python
  expr = ["and", "sensor_ready",
                 ["or", "override_active", "armed"]]
  ```
  Evaluator reads leaf strings as blackboard keys, recursively evaluates
  nested lists, writes result.

- **`s_engine` predicate tree** (preferred for composability):
  ```python
  expr = pred_and(dict_eq("sensor_ready", True),
                  pred_or(dict_eq("override_active", True),
                          dict_eq("armed",           True)))
  ```
  Evaluate via `invoke_pred(inst, expr_tree)` against the shared
  `module["dictionary"]`.

The s_engine form is the canonical one — it short-circuits, composes
with existing s_engine trees, and leverages the predicate infrastructure
already built. The list form is a convenience for simple cases and may
be implemented as a thin `evaluate_expression(expr, blackboard)` helper
(port of yaml port's `TokenDictionary.evaluate_expression`).

### DF nodes

Two DSL-level constructs (carried over from yaml port):

- `DF_EXPRESSION` (boolean fn node) — evaluates expression on every
  event; returns result.
- `DF_MASK` — deferred for now (yaml port's impl was
  `raise Exception("DF_MASK is not implemented")`). If we revive it,
  semantics TBD.

### Derived-token writeback

When a data-flow expression evaluates to produce a derived token, the
result is written back to `kb["blackboard"][<derived_name>]`. The same
dict holds source tokens and derived tokens; any downstream predicate
can read either transparently.

Cycle detection is out of scope for v1 — users are responsible for
non-cyclic DAGs of derived tokens. If a cycle is desired (e.g.
feedback), users must stage it explicitly across ticks.

---

## S-Expression bridge to `../s_engine/`

Three decomposed CFL node types expose an `s_engine` tree to the CFL
walker. None of them special-case return-code mapping or auto-forward
events — those are the aux fn's responsibility. Framework is thin;
user code is explicit.

### Three node types

**`se_module_load`** — module lifecycle.
- `data = {"key": "...", "module": <s_engine module tree>}`.
- **Init:** construct an `s_engine` module (via `../s_engine/`'s
  `new_module` with `dictionary = kb["blackboard"]`, plus the
  baked-in bridge functions registered into the module's fn tables),
  store the module object at `kb["blackboard"][key]`.
- **Term:** delete `kb["blackboard"][key]`. Any surviving tree
  instances from this module should already have been torn down by
  their own `se_tree_create.term` (reverse-topo ordering guarantees
  this when module-load is an ancestor of the tree-create nodes).

**`se_tree_create`** — tree-instance lifecycle.
- `data = {"key": "...", "module_key": "...", "tree_name": "..."}`.
- **Init:** look up module at `kb["blackboard"][module_key]`;
  call `new_instance_from_tree` (or equivalent) to instantiate the
  named tree; stamp a back-reference to the owning `se_tick` node
  on the instance (`tree_instance.cfl_tick_node = ...`) so bridge fns
  can find the CFL parent for child-control operations; store the
  tree instance at `kb["blackboard"][key]`.
- **Term:** delete `kb["blackboard"][key]`.

**`se_tick`** — interaction node. **Composite** — its CFL children
are subtrees that the s_engine tree can enable/disable via bridge
oneshots. Use case (from LuaJIT `s_engine_test_2` test 0 / test 1):
an s_engine tree holding a bitmask trigger or state machine decides,
per tick, which CFL children should run.
- `data = {"tree_key": "...", "aux_fn": "USER_AUX_BOOL_NAME",
  "return_code": "CFL_CONTINUE"}`.
- **Main fn:**
  ```python
  def se_tick_main(handle, aux_fn_name, node, event):
      aux = handle.registry.boolean(aux_fn_name)
      aux(handle, node, event["event_type"], event["event_id"], event["data"])
      return node["data"].get("return_code", "CFL_CONTINUE")
  ```
  No automatic event push, no automatic `run_until_idle`. The aux fn
  drives everything: reads the incoming CFL event, pushes events into
  the s_engine tree, calls `run_until_idle`, reads/writes the
  blackboard, posts CFL events back, and writes its chosen CFL return
  code into `node["data"]["return_code"]`.

### Aux fn contract (for `se_tick` only)

```python
def user_aux(handle, node, event_type, event_id, event_data):
    # Look up the tree via blackboard:
    tree = handle["blackboard"][node["data"]["tree_key"]]

    # Receive: the incoming CFL event is (event_type, event_id, event_data).

    # Generate: push events into the s_engine tree, tick it, post
    # CFL events back, set/clear blackboard bits, etc. — all explicit.
    tree.push_event(event_id, event_data)
    tree.run_until_idle()

    # Store data on the node or blackboard as the application needs.
    node["data"]["last_event"] = event_id
    handle["blackboard"]["some_result"] = tree.module["dictionary"]["x"]

    # Issue return code via node dict (not via the Python return value).
    node["data"]["return_code"] = "CFL_CONTINUE"

    return True   # boolean return value is unused by se_tick
```

The aux fn is where CFL and s_engine semantics meet. Return-code
mapping is not a framework concern — the aux fn is Python and can
inspect s_engine's terminal code directly.

### Bridge functions baked into s_engine modules

When `se_module_load.init` constructs an s_engine module, it registers
the following functions into that module's `oneshot_fns` / `pred_fns` /
`main_fns` tables. Users never need to register these.

**Child control** (operate on the owning `se_tick` node's CFL
children; resolved via `tree_instance.cfl_tick_node`):
- `cfl_enable_child(i)` / `cfl_disable_child(i)` — index into CFL
  child list.
- `cfl_enable_children()` / `cfl_disable_children()` — all children.
- `cfl_i_disable_children()` — disable all on init.
- `cfl_wait_child_disabled(i)` — `HALT` until child `i` is disabled.

**Internal events** (post back into the CFL engine queue):
- `cfl_internal_event(event_id, event_data, priority="normal", target=None)`
  — enqueue a directed CFL event. `target` defaults to the owning
  `se_tick` node's parent or a sensible default.

**Bitmap / blackboard ops** — same semantics as the CFL-side builtins
(section "Bitmap operations"), acting on `kb["blackboard"]`:
- `cfl_set_bits(*names)` / `cfl_clear_bits(*names)`.
- `cfl_read_bit(name)` — p_call predicate.
- `cfl_s_bit_and/or/nor/nand/xor(*args)` — composite predicates over
  named bits or nested child predicates.

**Logging:**
- `cfl_log(msg)` — routes to the engine's configured logger.

**Dropped from LuaJIT bridge** (not applicable in Python):
- `cfl_json_read_int/uint/float/bool/string_buf/string_ptr` — no JSON
  IR at runtime; read directly from `kb["blackboard"]`.
- `cfl_copy_const` / `cfl_copy_const_full` — no ROM constants; use
  plain Python `dict.update`.
- `CFL_EXCEPTION` (hard-crash escape hatch) — raise a Python
  exception, let the engine's crash callback observe.

### Why three nodes, not one

The composite `se_engine` in LuaJIT bundles module-load + tree-create
+ tick into a single node. We decompose because:

- Module reuse — one load, many tree instances across different KBs.
- Tree sharing — one tree instance driven by multiple `se_tick` nodes.
- Lifecycle clarity — reverse-topo termination (`tick.term` →
  `tree_create.term` → `module_load.term`) maps naturally onto
  ancestor-order node placement in the DSL.

The yaml-port-legacy `se_tick + se_module_load + se_tree_load` triplet
in LuaJIT is the model we follow. The single-node `se_engine`
composite is not ported.

### DSL

```python
col = ct.define_column("sensor_pipeline", auto_start=True)

ct.asm_se_module_load(key="sensor_module", module=se_module_tree)
ct.asm_se_tree_create(key="primary_tree",
                      module_key="sensor_module",
                      tree_name="sensor_main")

tick = ct.define_se_tick(tree_key="primary_tree",
                         aux_fn="SENSOR_INJECTOR")
    ct.define_column("route_a")
        ct.asm_log_message("branch A selected by s-tree")
        ct.asm_halt()
    ct.end_column(...)
    ct.define_column("route_b")
        ct.asm_log_message("branch B selected by s-tree")
        ct.asm_halt()
    ct.end_column(...)
ct.end_se_tick(tick)

ct.end_column(col)
```

The s_engine tree running under `primary_tree` uses `cfl_enable_child(i)`
etc. to steer events into the CFL children of the `se_tick` node.

---

## Top-level API shape

There is **no build-time / runtime split.** The embedded-target ports
(LuaJIT, C, Zig) compile DSL to a binary or JSON IR on host and load
it on target; that distinction does not exist in Python. Everything
lives in one process with one object lifecycle.

### One `ChainTree` object, both builder and runtime

```python
ct = ChainTree(wait_seconds=0.25)

# Register user functions (two registries on the same object)
ct.add_one_shot("ACTIVATE_VALVE", activate_valve_fn,
                description="Opens the valve")
ct.add_boolean ("MY_COND",        my_cond_fn)
ct.add_main    ("MY_MAIN",        my_main_fn)
# s_engine-side user functions:
ct.add_se_one_shot("LOG_RESULT",  log_result_fn)
ct.add_se_pred    ("CHECK_STATE", check_state_fn)
ct.add_se_main    ("RUN_STEP",    run_step_fn)

# Define KBs (fluent builder; user-defined Python fns invoke asm_* on ct)
first_test(ct, "first_test")
second_test(ct, "second_test")

# Kick off
ct.run(starting=["first_test", "second_test"])
```

`run` internally: validates every string fn reference against the
registries (fail-fast if anything is unresolved), activates the KBs
in `starting`, and enters the main loop (timer tick → timer events per
KB → drain → sleep).

### DB-backed test storage

An optional persistence layer; **not** a build/runtime boundary. A
`ChainTree` can be serialized to JSON (analogous to `s_engine`'s
`serialize_tree` / `deserialize_tree`) and later reloaded. User-function
callables are not serialized — only their string names, which must be
re-registered in the reloaded ChainTree before `run`.

Tests reference stored tests at **DSL-build time**:

```python
ct.reference_test("stored_checkpoint_v1")   # DB lookup, splice in
```

The referenced tree is fetched from the DB, deserialized, and inserted
at the current fluent-builder position. At `run()` the tree is already
self-contained Python dicts — no runtime DB dependency. DB schema,
connection, and query API are TBD.

---

## Directory layout

```
chain_tree/
├── continue.md           # this spec
├── CLAUDE.md
├── __init__.py           # top-level ChainTree class re-export
├── ct_runtime/           # engine, event queue, timer, walker,
│                         # termination, multi-KB main loop
├── ct_builtins/          # CFL_* main/boolean/one-shot impls:
│                         # columns, wait_time / wait_for_event,
│                         # verify, state_machine, sequence_til,
│                         # supervisor, exception_catch, streaming,
│                         # controlled_node, se_module_load,
│                         # se_tree_create, se_tick
├── ct_dsl/               # fluent builder (stack, bracket pairs,
│                         # asm_* methods) split topically like the
│                         # yaml port: basic_cf_links, wait_cf_links,
│                         # verify_cf_links, column_flow,
│                         # state_machine, sequence_til, data_flow,
│                         # s_node_control, exception_handler
├── ct_bridge/            # baked-in s_engine-side bridge fns:
│                         # cfl_enable_child, cfl_internal_event,
│                         # cfl_set_bits, cfl_s_bit_and, cfl_log, ...
├── tests/
└── previous_port/        # reference material, unchanged
```

Four subpackages because CFL builtins (called by the CFL walker,
signature `(handle, bool_fn_name, node, event) → code`) and bridge
functions (registered into s_engine modules, signature
`(inst, node) → ...`) have different invocation conventions and
different audiences. Keeping them separate is self-documenting.

## Error handling and validation

**Fail early, fail fast. Don't hide errors. Errors are meant to be
fixed.** Every validation runs at the earliest moment the information
needed is available — never deferred.

### Rules

- **Stack balance** is checked at every `asm_*` / `define_*` / `end_*`
  call. A forgotten `end_column` surfaces at the next incompatible
  call with a message naming the expected vs. actual frame — not
  later, not at `run()`.
- **KB-name / column-name uniqueness** is checked at `start_test` /
  `define_column`, not at the end.
- **Function-name resolution**: when `asm_*` references a user fn
  string, resolve immediately against the appropriate registry if the
  function has been registered. If not yet registered at call time,
  record the reference and resolve at `ChainTree.run()` — the earliest
  point where all registrations must be present. Any unresolved name
  at `run()` aborts before the engine starts.
- **State-machine state references** are validated at
  `end_state_machine`, when the full list of declared states is
  known. Undefined transitions raise there.
- **Exception handler structure** (MAIN / RECOVERY / FINALIZE links
  all present) is validated at `end_exception_handler`.
- **Sequence-til invariants** (children have been properly marked with
  `CFL_MARK_SEQUENCE` before disabling) — cannot be statically verified
  at build time in general, so is checked at runtime per-tick; a
  missing mark raises immediately rather than silently defaulting.
- **Port / schema matches** for streaming and controlled-node ports
  are checked at the moment a sink/filter/transform references a
  port — if port metadata is inconsistent between the emitter and
  consumer, raise.

### Non-rules

- No error swallowing. If a user fn raises a Python exception, the
  engine propagates it to the configured crash callback (observer)
  and re-raises. No silent catch-log-continue paths.
- No "warnings that might be errors later." Warnings are for
  diagnostics; structural problems are errors.
- No sentinel return values for error conditions. Raise with a clear
  message naming the offending node, KB, and rule violated.

## Open items

Locked: engine execution model, walker semantics, termination
mechanics, per-node state convention, DSL shape, user-function
registration, top-level API (one `ChainTree`, build + run), feature
scope, bitmap + data-flow on shared blackboard, streaming/controlled
nodes on directed events, exception + heartbeat pipeline, CFL↔SE
bridge (three-node decomposition, aux-driven tick, baked-in bridge
fns), directory layout, error-handling principle (fail-early /
fail-fast). Still open:

1. **DB-backed test storage API** (schema, connection, query surface,
   invalidation semantics). Punted until a concrete use case. The
   `ChainTree.reference_test("stored_name")` hook is the intended DSL
   surface; persistence layer is TBD.

## Per-node-type schemas — deferred to implementation

`ct_control` and `data` field schemas are **defined with each node
type in `ct_builtins/`**, not enumerated in this spec. Every CFL
node type's implementation module documents its own schemas as the
first thing in the file:

```python
"""
CFL_SUPERVISOR_MAIN — restart-policy supervisor node.

node["data"] schema:
    {
        "supervisor_data": {
            "termination_type":      "ONE_FOR_ONE" | "ONE_FOR_ALL" | "REST_FOR_ALL",
            "reset_limited_enabled": bool,
            "max_reset_number":      int,
            "reset_window":          float,   # seconds, monotonic
            "finalize_function":     str,     # "CFL_NULL" or user-registered name
            "finalize_function_data": dict,
        },
        "user_data": dict,                    # free-form, user-supplied
    }

node["ct_control"] extensions:
    {
        "supervisor_state": {
            "reset_count":          int,
            "failure_counter":      SupervisorFailureCounter,
        },
    }

Aux fn contract: optional boolean early-out. Returning True from aux
disables the supervisor (CFL_DISABLE). Otherwise, see the supervisor
section of continue.md.
"""
```

The minimum schema all nodes share is:

```python
node["ct_control"] = {"enabled": bool, "initialized": bool}
node["data"]       = {...}   # node-type-specific, documented per type
```

## Design chronology

Pinned decisions, in the order they were made (for resumption
context):

1. Port scope: full ChainTree CFL engine (columns, state machines,
   streaming, controlled nodes, supervisor, sequence-til,
   exception+heartbeat, bitmap, data flow). Templates dropped.
2. Uses `../s_engine/` as the embedded S-expression subsystem via a
   bridge.
3. Drops from yaml port: YAML IR, JSON IR, ltree strings, flat node
   index, stack machine, quad compiler, FNV-1a hashing, blackboard
   byte offsets, Avro C-struct generation.
4. Execution model follows LuaJIT exactly: single shared high/normal
   event queue, directed events, timer ticks fan out per active KB,
   drain high-first-then-normal-until-empty-then-sleep.
5. Tick cadence is an input (fractional seconds).
6. Walker is iterative DFS, visits enabled-children only,
   return-code → walker-signal mapping per `cfl_engine.lua`.
7. Termination unified: `terminate_node_tree(root)` runs phase-1
   walker mark + phase-2 reverse-topological-order delivery. Works
   for any subtree at any time, including KB-level teardown.
8. Per-node state on node dicts: `node["ct_control"]` (engine state,
   read-only to user fns) + `node["data"]` (user r/w scratch and DSL
   config). Per-node-type contracts.
9. DSL shape: Model A (fluent stateful builder with push/pop stack).
10. User functions are Python callables, name-registered. Two
    registries: CFL-side (main/boolean/one-shot) and s_engine-side
    (m_call/p_call/o_call/io_call). CFL builtins + bridge fns baked
    into the engine runtime.
11. Parametric subtrees → Python functions emitting DSL (macros).
12. Top-level API: single `ChainTree` object. Build trees, register
    user fns, `.run(starting=[...])`. No build/runtime split.
13. Packets, ports, streaming, controlled nodes: all built on
    directed events + dict payloads + optional `_schema` tag.
    No FFI, no wire header.
14. Bitmap ops: dict-based, flattened into `kb["blackboard"]`. Same
    namespace as s_engine's `dictionary`. `s_engine`'s `dict_*` and
    `pred_*` work unmodified.
15. Data flow: evaluate logical expressions over blackboard bits;
    derived tokens written back to same blackboard.
16. Exception / heartbeat: LuaJIT-compatible 3-stage pipeline
    (MAIN / RECOVERY / FINALIZE). Heartbeat is a timer-driven
    timeout counter.
17. CFL↔SE bridge: three decomposed node types (`se_module_load` /
    `se_tree_create` / `se_tick`). `se_tick` is composite — the
    s_engine tree drives CFL children via `cfl_enable_child` etc.
    Aux fn is the full interaction driver; return code via
    `node["data"]["return_code"]`. Baked-in bridge fns for child
    control, internal events, bitmap ops, logging.
18. Directory layout: four subpackages (`ct_runtime`, `ct_builtins`,
    `ct_dsl`, `ct_bridge`).
19. Error handling: fail-early, fail-fast. No hidden errors. Every
    validation runs at the earliest moment the information is
    available.
20. Per-node-type schemas documented in implementation, not in this
    spec.

## Next session

Runtime work, then CFL/CFL-S function coverage, then DSL helpers and
macros:

1. **Finish the runtime** (`ct_runtime/`): engine handle, event queue
   pair, timer, walker, termination (`terminate_node_tree`), main
   loop, KB activation/teardown, user-fn registries.
2. **CFL functions** (`ct_builtins/` CFL-side): the full set of
   `CFL_*_MAIN` / `CFL_*_BOOLEAN` / `CFL_*_INIT` / `CFL_*_TERM`
   one-shots — column, wait_time, wait_for_event, verify,
   state_machine, sequence_start/pass/fail, supervisor,
   exception_catch + heartbeat, streaming node types,
   controlled_node, join_link, mark_sequence, raise_exception,
   heartbeat one-shots.
3. **CFL-S functions** (`ct_bridge/`): bridge functions baked into
   s_engine modules — `cfl_enable_child/disable_child`, `cfl_*_children`,
   `cfl_internal_event`, `cfl_set_bits/clear_bits`, `cfl_read_bit`,
   `cfl_s_bit_and/or/nor/nand/xor`, `cfl_log`.
4. **Helper DSL functions** (`ct_dsl/`): the `asm_*` leaves and
   `define_*`/`end_*` bracket pairs across all node categories, split
   topically like the yaml port (basic_cf_links, wait_cf_links,
   verify_cf_links, column_flow, state_machine, sequence_til,
   data_flow, s_node_control, exception_handler, streaming,
   controlled_node, se_bridge).
5. **DSL macros**: design pattern for parametric subtrees as Python
   helper functions. Worked examples (retry_column, timeout_wrap,
   guarded_action, state-machine-from-table) modeled on `s_engine`'s
   `se_dsl/macros/tier1.py` and `tier2.py`.

Open items remaining after this pass: DB-backed test storage API.
