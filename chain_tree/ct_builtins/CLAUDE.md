# ct_builtins

The CFL operator library. Each module implements one operator family —
main/boolean/one-shot fns following the signatures in
`ct_runtime/registry.py`. The single public entry point is
`register_all_builtins(registry)`, which the DSL builder calls automatically
when constructing a `ChainTree`.

## Module map

| Module | Operator family | Key fns |
|---|---|---|
| `column.py` | Generic container parent | CFL_COLUMN_MAIN / _INIT / _TERM |
| `control.py` | Trivial control-flow mains (return-a-fixed-code) and CFL_NULL no-ops | CFL_CONTINUE / CFL_HALT / CFL_TERMINATE / CFL_RESET / CFL_DISABLE / CFL_TERMINATE_SYSTEM mains |
| `wait.py` | Time- and event-driven waits | CFL_WAIT_TIME, CFL_WAIT_MAIN + CFL_WAIT_FOR_EVENT aux |
| `verify.py` | Assertion leaf | CFL_VERIFY |
| `time_window.py` | Wall-clock time-of-day window | CFL_TIME_WINDOW_CHECK |
| `state_machine.py` | One-of-N child states + transition events | CFL_STATE_MACHINE_MAIN/_INIT, CFL_CHANGE_STATE / _TERMINATE_ / _RESET_ one-shots |
| `sequence_til.py` | Pass-on-first-success / fail-on-first-failure containers | CFL_SEQUENCE_PASS_MAIN / FAIL_MAIN, CFL_MARK_SEQUENCE |
| `supervisor.py` | Erlang-style restart policies | CFL_SUPERVISOR_MAIN/_INIT (ONE_FOR_ONE / ONE_FOR_ALL / REST_FOR_ALL) |
| `exception.py` | 3-stage MAIN→RECOVERY→FINALIZE catch + heartbeat | CFL_EXCEPTION_CATCH_MAIN, CFL_RAISE_EXCEPTION, CFL_HEARTBEAT_* |
| `streaming.py` | Schema-tagged event pipelines | CFL_STREAMING_SINK / TAP / FILTER / TRANSFORM_PACKET |
| `controlled.py` | Client-server RPC over directed events | CFL_CONTROLLED_SERVER_MAIN, CFL_CONTROLLED_CLIENT_MAIN/_INIT |
| `se_bridge.py` | CFL nodes that own s_engine modules / instances / ticks | SE_MODULE_LOAD / SE_TREE_CREATE / SE_TICK |
| `system.py` | Generic utility one-shots | CFL_LOG_MESSAGE, CFL_BLACKBOARD_SET, CFL_EMIT_STREAMING |

## Calling conventions (from `ct_runtime/registry.py`)

| Call type | Signature |
|---|---|
| main | `fn(handle, bool_fn_name, node, event) -> str` (CFL code) |
| boolean | `fn(handle, node, event_type, event_id, event_data) -> bool` |
| one-shot | `fn(handle, node) -> None` |

`handle` is the KB handle (`{"name", "root", "blackboard", "engine"}`). Use
`handle["blackboard"]` for shared state (identity-shared with s_engine via
the bridge), `handle["engine"]` for the engine-level facilities (registry,
event queue, clocks, logger).

## Per-operator data layout

Each operator's `node["data"]` schema is documented inline at the top of its
module. The DSL's `asm_*` / `define_*` methods are the canonical way to
construct these — hand-rolled `make_node` callers should mirror those data
keys exactly.

## Universal contracts

1. **Boolean fns must filter `CFL_TERMINATE_EVENT`.** `disable_node` fires
   the boolean during teardown; failing to filter causes phantom counter
   bumps or re-entrant work. The built-ins (sequence_til, supervisor,
   streaming, controlled) all do this internally.
2. **Main fns return CFL_* codes**, never CT_* signals. `execute_node` does
   the translation.
3. **One-shots fire at INIT** (and `_TERM` on disable). They have no return
   value; side-effecting only.
4. **`auto_start` flag is informational** for column/state — current built-ins
   enable all children unconditionally at INIT. Reserved for parents like
   gate_node that selectively activate (not yet ported).

## Adding a new operator

1. Write the main / boolean / one-shot fns in a new module (or extend an
   existing one).
2. Register them in `__init__.py`'s `register_all_builtins`.
3. Add a DSL leaf in `ct_dsl/builder.py` (`asm_*` for leaves, `define_* /
   end_*` for frame-style containers).
4. Document `node["data"]` schema in the module docstring.
5. Add tests in `tests/test_<feature>.py`.

## Quirks worth knowing

- **Streaming filter target must be an ANCESTOR of filter+sink.** Emitting
  to the sink directly bypasses upstream filter siblings. See
  `feedback_streaming_filter_target` memory.
- **`asm_raise_exception` is async.** It posts a high-pri event; pair with
  `asm_halt()` to actually abort siblings on the current tick. See
  `feedback_raise_then_halt` memory.
- **Server in controlled-node** is "transparent" (CFL_CONTINUE on no
  match) so it doesn't block siblings while waiting; it polls children
  on each TIMER until they all disable, then sends the response.
- **state_machine reorders children at end_state_machine** so that
  `current_state_index` lines up with the declared `state_names` order
  regardless of the `define_state(...)` call order.
