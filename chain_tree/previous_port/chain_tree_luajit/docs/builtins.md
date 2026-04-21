# Built-in Functions

`ct_builtins.lua` provides all built-in main, one-shot, and boolean functions for the dict-based runtime. Ported from `cfl_builtins.lua` + `cfl_state_machine.lua`.

## Function Signatures

```lua
-- Main: called every tick for enabled+initialized nodes
fn(handle, bool_fn, node, event_id, event_data) -> return_code_string

-- One-shot: called once (init or term)
fn(handle, node) -> nil

-- Boolean: auxiliary function, called by main or on init/term events
fn(handle, node, event_id, event_data) -> boolean
```

Key differences from C-record style: `bool_fn` is the actual function reference, `node` is the full table, return codes are strings.

## Main Functions

### Constant returns

| Function | Returns |
|----------|---------|
| `CFL_NULL` | `CFL_CONTINUE` |
| `CFL_DISABLE` | `CFL_DISABLE` |
| `CFL_HALT` | `CFL_HALT` |
| `CFL_RESET` | `CFL_RESET` |
| `CFL_TERMINATE` | `CFL_TERMINATE` |
| `CFL_TERMINATE_SYSTEM` | `CFL_TERMINATE_SYSTEM` |

### Column / gate

| Function | Behavior |
|----------|----------|
| `CFL_COLUMN_MAIN` | On timer: check bool_fn (true = disable), check any child enabled (none = disable), else continue |
| `CFL_GATE_NODE_MAIN` | Alias for `CFL_COLUMN_MAIN` |
| `CFL_FORK_MAIN` | Alias for `CFL_COLUMN_MAIN` |
| `CFL_LOCAL_ARENA_MAIN` | Alias for `CFL_COLUMN_MAIN` |
| `CFL_SEQUENCE_START_MAIN` | Alias for `CFL_COLUMN_MAIN` |
| `CFL_CONTROLLED_NODE_CONTAINER_MAIN` | Alias for `CFL_COLUMN_MAIN` |

### Verify

| Function | Behavior |
|----------|----------|
| `CFL_VERIFY` | Checks bool_fn each tick. On false: calls error handler one-shot, returns RESET or TERMINATE |

### Wait

| Function | Behavior |
|----------|----------|
| `CFL_WAIT` | Halts until bool_fn returns true (disable) or timeout event count reached (calls error handler, RESET or TERMINATE) |
| `CFL_WAIT_TIME` | Halts until `handle.timestamp >= wait_time_out`. Timer-only |

### Join

| Function | Behavior |
|----------|----------|
| `CFL_JOIN_MAIN` | Halts until target node is disabled, then disables self |
| `CFL_JOIN_SEQUENCE_ELEMENT` | Alias for `CFL_JOIN_MAIN` |

### Sequence

| Function | Behavior |
|----------|----------|
| `CFL_SEQUENCE_PASS_MAIN` | Steps through children. Advances to next on child failure (false). Stops on child success (true). Calls finalize one-shot when done. |
| `CFL_SEQUENCE_FAIL_MAIN` | Steps through children. Advances to next on child success (true). Stops on child failure (false). Calls finalize one-shot when done. |

### Loop

| Function | Behavior |
|----------|----------|
| `CFL_FOR_MAIN` | Re-enables single child until iteration count (`number_of_iterations`) is reached |
| `CFL_WHILE_MAIN` | Re-enables single child while bool_fn returns true |

### Watchdog

| Function | Behavior |
|----------|----------|
| `CFL_WATCH_DOG_MAIN` | Counts timer events. On timeout: calls wd_fn one-shot, returns RESET or TERMINATE |

### Data flow mask

| Function | Behavior |
|----------|----------|
| `CFL_DF_MASK_MAIN` | Enables/disables children based on bitmask conditions (required bits set AND excluded bits clear). Returns `CFL_SKIP_CONTINUE` when conditions not met |

### Supervisor

| Function | Behavior |
|----------|----------|
| `CFL_SUPERVISOR_MAIN` | Monitors children. Per-child leaky bucket failure tracking. Termination types: `0` one_for_one, `1` one_for_all, `2` rest_for_all. Calls finalize on failure window exceeded |

### Recovery

| Function | Behavior |
|----------|----------|
| `CFL_RECOVERY_MAIN` | Step-based recovery state machine with states: eval (check skip), wait (child running), parallel_enable, parallel_wait |

### Exception

| Function | Behavior |
|----------|----------|
| `CFL_EXCEPTION_CATCH_ALL_MAIN` | On RAISE_EXCEPTION_EVENT: calls bool_fn, if caught calls logging one-shot and continues, else forwards to parent |
| `CFL_EXCEPTION_CATCH_MAIN` | On RAISE_EXCEPTION_EVENT: checks exception_id match, routes to child steps. On SET_EXCEPTION_STEP_EVENT: advances step counter |

### Event logging

| Function | Behavior |
|----------|----------|
| `CFL_EVENT_LOGGER` | Checks incoming event_id against configured event_ids list. Prints timestamped message on match |

### State machine

| Function | Behavior |
|----------|----------|
| `CFL_STATE_MACHINE_MAIN` | Manages state transitions via CHANGE_STATE_EVENT. Enables one child at a time (the active state). RESET_STATE_MACHINE_EVENT restarts. TERMINATE_STATE_MACHINE_EVENT disables |
| `CFL_SM_EVENT_FILTERING_MAIN` | State machine variant with event ID filtering per state |

### Streaming

| Function | Behavior |
|----------|----------|
| `CFL_STREAMING_TAP_MAIN` | Passes streaming data through bool_fn (tap/observe), continues |
| `CFL_STREAMING_FILTER_MAIN` | Bool_fn returns false to block, true to pass data downstream |
| `CFL_STREAMING_SINK_MAIN` | Terminal consumer of streaming data |
| `CFL_STREAMING_TRANSFORM_MAIN` | Accumulates packets, emits transformed output |
| `CFL_STREAMING_COLLECTOR_MAIN` | Collects packets across ports into a container, emits when full |
| `CFL_STREAMING_VERIFY_MAIN` | Verifies streaming data against constraints via bool_fn |

### Controlled nodes

| Function | Behavior |
|----------|----------|
| `CFL_CONTROLLED_NODE_MAIN` | Managed by external controller (e.g., SE engine). Stays alive, enable/disable of children handled externally |

## One-Shot Functions

### Init one-shots

| Function | Behavior |
|----------|----------|
| `CFL_COLUMN_INIT` | Enables all children of the column node |
| `CFL_COLUMN_NULL` | No-op |
| `CFL_LOG_MESSAGE` | Prints timestamped log message from `node.node_dict.message` |
| `CFL_WAIT_TIME_INIT` | Computes `wait_time_out = timestamp + node_dict.wait_time` |
| `CFL_WAIT_INIT` | Sets up timeout count and error handler from node_dict |
| `CFL_VERIFY_INIT` | Sets up error function and reset flag from node_dict |
| `CFL_JOIN_INIT` | Resolves target node ltree from join link data |
| `CFL_SEQUENCE_PASS_INIT` / `CFL_SEQUENCE_FAIL_INIT` | Enables first child, initializes sequence tracking |
| `CFL_FOR_INIT` | Enables first child, reads iteration count |
| `CFL_WHILE_INIT` | Enables first child |
| `CFL_WATCH_DOG_INIT` | Reads watchdog config from node_dict |
| `CFL_DF_MASK_INIT` | Reads required/excluded bitmask values |
| `CFL_SUPERVISOR_INIT` | Enables all children, initializes per-child failure arrays |
| `CFL_STATE_MACHINE_INIT` | Enables initial state (first child) |
| `CFL_STREAMING_*_INIT` | Various streaming pipeline initializers |
| `CFL_EVENT_LOGGER_INIT` | Resolves event name strings to integer IDs |

### Term one-shots

| Function | Behavior |
|----------|----------|
| `CFL_COLUMN_TERM` | Terminates all child subtrees |
| `CFL_CONTROLLED_NODE_TERM` | Same as `CFL_COLUMN_TERM` |

## Boolean Functions

| Function | Behavior |
|----------|----------|
| `CFL_NULL` | Returns false |
| `CFL_FALSE` | Returns false |
| `CFL_TRUE` | Returns true |
| `CFL_COLUMN_NULL` | Returns false |
| `CFL_BITMASK_WAIT` | Returns true when all required bits set in `handle.bitmask` |
| `CFL_BITMASK_VERIFY` | Same as `CFL_BITMASK_WAIT` |
