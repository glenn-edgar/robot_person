# ct_dsl

Fluent stateful builder for CFL knowledge-bases. The single public entry
point is the `ChainTree` class in `builder.py`; macros are Python functions
in `macros.py` that emit subtree fragments via the same builder methods.

## Public surface

```python
from ct_dsl import ChainTree

chain = ChainTree(
    tick_period=0.25,
    logger=print,
    get_time=time.monotonic,        # for tick scheduling / wait_time
    get_wall_time=int_epoch_fn,     # for time-window wait leaves + s_engine bridge
    timezone=zoneinfo.ZoneInfo("..."),
    sleep=time.sleep,
    crash_callback=...,
)

chain.add_main / add_boolean / add_one_shot      # CFL-side user fns
chain.add_se_main / add_se_pred / add_se_one_shot / add_se_io_one_shot

chain.start_test(name)               # opens a KB; auto-named root column
  chain.asm_log_message(...)
  chain.asm_blackboard_set(k, v)
  chain.asm_one_shot(name, data=...)
  chain.asm_wait_time(seconds)
  chain.asm_wait_for_event(event_id, count=, timeout=, error_fn=, ...)
  chain.asm_verify(bool_fn_name, error_fn=, reset_flag=)
  chain.asm_wait_until_in_time_window(start, end)
  chain.asm_wait_until_out_of_time_window(start, end)
  chain.asm_terminate / asm_halt / asm_disable / asm_reset / asm_terminate_system
  chain.define_column(name) / end_column()
  chain.define_state_machine(...) / define_state / end_state / end_state_machine
  chain.define_supervisor(...) / end_supervisor
  chain.define_exception_handler / define_main/recovery/finalize_column / ...
  chain.define_sequence_til_pass / fail / asm_mark_sequence_pass / fail
  chain.asm_streaming_sink / tap / filter / transform / emit_streaming
  chain.define_controlled_server / asm_client_controlled_node
  chain.asm_se_module_load / asm_se_tree_create / define_se_tick / end_se_tick
chain.end_test()

chain.run(starting=[kb_name, ...])    # enters the engine main loop
```

## Builder model

State on the `ChainTree` instance:

- `engine` — the `ct_runtime.new_engine` handle.
- `_frames` — stack of open frames; top is the "current parent". Each
  `define_*` pushes a frame, each `end_*` pops it.
- `_kb_names`, `_link_counter` — name uniqueness + auto-generated link names.

Every `asm_*` leaf attaches to the current parent via `link_children`. Every
`define_*` opens a new frame whose node is added under the previous parent
and becomes the new parent.

Frame kinds carry a `kind` tag so that `_pop` can verify the user closes the
right frame: `"test"`, `"column"`, `"se_tick"`, `"state_machine"`, `"state"`,
`"supervisor"`, `"exception_handler"`, `"exception_main" / "_recovery" /
"_finalize"`, `"controlled_server"`, `"seq_pass"`, `"seq_fail"`.

## Validation

- **Stack balance**: `_pop` raises immediately if the wrong frame is being
  closed.
- **Unique KB names**: `start_test` adds to `_kb_names`; collision raises.
- **Unresolved fn references**: `run()` calls `_validate_unresolved` which
  walks every KB tree and confirms every `main_fn_name` / `boolean_fn_name`
  / `init_fn_name` / `term_fn_name` resolves in the registry. Raises
  `LookupError` at runtime entry, before the first tick fires.
- **State-machine completeness**: `end_state_machine` checks all declared
  states have a `define_state` block; missing states raise. Children are
  reordered to declared order so the SM's index is stable.
- **Exception-handler completeness**: `end_exception_handler` requires
  exactly one MAIN, one RECOVERY, one FINALIZE column.

## Macros

`ct_dsl.macros` contains five starter examples — `repeat_n`,
`every_n_seconds`, `timeout_wrap`, `guarded_action`, `wait_then_act` —
each a plain function taking a `ChainTree` and emitting subtree fragments
via the existing builder methods. Copy and extend; they are not a stable
API surface.

## Conventions

- **`_NULL` is the sentinel** for "no fn" in any of the four name slots
  (main / boolean / init / term). `register_all_builtins` registers
  `cfl_null_boolean` / `cfl_null_one_shot` under `"CFL_NULL"` so the engine
  can call them safely as no-ops if a slot is left at `_NULL`.
- **`asm_*` returns the leaf node ref**; `define_*` returns the frame node
  ref. Both are useful for cross-references — e.g. `asm_change_state(sm, ...)`
  takes the SM ref returned by `define_state_machine`, and
  `asm_client_controlled_node(server, ...)` takes the server ref returned by
  `define_controlled_server`.
- **`add_se_*` methods register fns into the s_engine-side registry** which
  is forwarded into modules built by `asm_se_module_load`. CFL-side and
  s_engine-side namespaces are disjoint.
