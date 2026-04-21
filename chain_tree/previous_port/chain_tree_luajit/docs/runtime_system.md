# Runtime System

The dict-based runtime is implemented in six modules under `runtime_dict/`. All node data is plain Lua tables keyed by ltree path strings.

## Module Architecture

```
ct_runtime.lua           -- Top-level: create, reset, add_test, run (event loop)
  ct_engine.lua          -- Node execution: init/main/term dispatch, tree walker
    ct_walker.lua        -- Iterative DFS tree walker
  ct_common.lua          -- Node helpers: get_children, enable/disable, node state
  ct_loader.lua          -- JSON IR loading, function registration, validation
  ct_definitions.lua     -- Constants: return codes, event IDs, walker codes
```

## ct_runtime.lua

Top-level lifecycle and event loop.

### API

```lua
local handle = ct_runtime.create(params, handle_data)
ct_runtime.reset(handle)
ct_runtime.add_test(handle, kb_name)
ct_runtime.run(handle)
ct_runtime.delete_test(handle, kb_name)
```

- `create(params, handle_data)` -- builds the runtime handle from loader output. `params` contains `delta_time` (seconds per tick, default 0.1) and `max_ticks` (default 5000).
- `reset(handle)` -- clears event queue, resets all node control flags, restores blackboard defaults, resets bitmask and timer.
- `add_test(handle, kb_name)` -- activates a knowledge base by name. Enables the KB root node.
- `run(handle)` -- main event loop (described below).

### Event Loop

The `run()` function loops while any KB is active and tick count is below `max_ticks`:

1. **Sleep** -- `usleep(delta_time * 1000000)` via FFI
2. **Advance time** -- increment `tick_count` and `timestamp`
3. **Detect time boundaries** -- second/minute/hour crossings
4. **Generate events** -- for each active KB, push to event queue:
   - `CFL_TIMER_EVENT` (every tick)
   - `CFL_SECOND_EVENT` (on second boundary)
   - `CFL_MINUTE_EVENT` (on minute boundary)
   - `CFL_HOUR_EVENT` (on hour boundary)
5. **Drain event queue** -- pop events FIFO, call `engine.execute_event()` for each. If the result is `CFL_TERMINATE_SYSTEM`, deactivate that KB.

Events are simple tables: `{ node_id = ltree_string, event_id = integer, event_data = any }`.

## ct_engine.lua

Node execution engine. Dispatches init/main/term functions, manages node enable/disable lifecycle.

### execute_event(handle, root_id, event_id, event_data)

Walks the tree rooted at `root_id` using the DFS walker. For each enabled node:

1. **If not initialized**: run init one-shot (`initialization_function_name`), mark initialized, run aux boolean with `CFL_INIT_EVENT`.
2. **Call main function**: `main_fn(handle, bool_fn, node, event_id, event_data)` where `bool_fn` is the resolved aux boolean function.
3. **Map return code to walker action**:

| Return Code | Walker Action |
|-------------|--------------|
| `CFL_CONTINUE` | continue to children |
| `CFL_HALT` | `STOP_SIBLINGS` -- skip remaining siblings |
| `CFL_DISABLE` | terminate node + skip children |
| `CFL_RESET` | reset parent subtree |
| `CFL_TERMINATE` | terminate parent subtree |
| `CFL_SKIP_CONTINUE` | continue but skip this node's children |
| `CFL_TERMINATE_SYSTEM` | stop entire walk |

### terminate_node_tree(handle, node_id)

Collects all enabled+initialized nodes in DFS order, reverses the list, then disables each (running term one-shot and aux boolean with `CFL_TERMINATE_EVENT`). Reverse order ensures children terminate before parents.

### Other functions

- `init_test(handle, kb_name)` -- enables the KB root node
- `enable_node(handle, node_id)` -- sets `ct_control.enabled = true`
- `node_is_enabled(handle, node_id)` -- checks `ct_control.enabled`

## ct_walker.lua

Iterative DFS tree walker using an explicit stack. Each stack entry is `{ node_id, child_index }`. The `apply_func` callback returns a walker control code:

- `true` -- continue (visit children)
- `"SKIP_CHILDREN"` -- do not visit this node's children
- `"STOP_SIBLINGS"` -- skip remaining siblings at this level
- `"STOP_BRANCH"` -- stop processing this branch entirely
- `"STOP_ALL"` -- abort the entire walk

The walker supports `save_context`/`restore_context` for nested walks (used during termination inside an active walk).

## ct_loader.lua

Loads JSON IR via `cjson`, builds the runtime data structures.

### API

```lua
local handle_data = loader.load(json_path)
loader.register_functions(handle_data, builtins, user_fns)
local ok, missing = loader.validate(handle_data, kb_name)
```

- `load(json_path)` -- reads JSON, scrubs `cjson.null` values, builds node tables with `ct_control` fields, extracts KB metadata, event strings, blackboard definitions. Returns `handle_data`.
- `register_functions(handle_data, ...)` -- merges `main`, `one_shot`, and `boolean` tables from each argument into `handle_data.main_functions`, `handle_data.one_shot_functions`, `handle_data.boolean_functions`.
- `validate(handle_data, kb_name)` -- checks that every function name referenced by nodes in the given KB has a registered implementation. Returns `true` or `false, missing_list`.

## ct_common.lua

Shared helpers:

- `get_children(node)` -- returns list of child ltree strings from `node.label_dict.links`
- `enable_children(handle, node_id)` -- enables all children
- `disable_children(handle, node_id)` -- disables all children (clears enabled + initialized)
- `any_child_enabled(handle, node_id)` -- returns boolean
- `enable_child(handle, node_id, child_link_index)` -- enables child by 1-based index
- `alloc_node_state(handle, node_id)` -- creates `handle.node_state[node_id]` if absent, returns it
- `get_node_state(handle, node_id)` -- returns existing node state or nil
- `get_parent_id(node)` -- returns parent ltree string

## ct_definitions.lua

Constants used throughout the runtime:

### Return codes (strings)

```lua
CFL_CONTINUE         = "CFL_CONTINUE"
CFL_HALT             = "CFL_HALT"
CFL_TERMINATE        = "CFL_TERMINATE"
CFL_RESET            = "CFL_RESET"
CFL_DISABLE          = "CFL_DISABLE"
CFL_SKIP_CONTINUE    = "CFL_SKIP_CONTINUE"
CFL_TERMINATE_SYSTEM = "CFL_TERMINATE_SYSTEM"
```

### Event IDs (integers)

```lua
CFL_INIT_EVENT       = 0
CFL_TERMINATE_EVENT  = 1
CFL_TIMER_EVENT      = 4
CFL_SECOND_EVENT     = 5
CFL_MINUTE_EVENT     = 6
CFL_HOUR_EVENT       = 7
-- ... plus exception, heartbeat, state machine events
```

### Walker control codes

```lua
CT_CONTINUE      = true
CT_SKIP_CHILDREN = "SKIP_CHILDREN"
CT_STOP_SIBLINGS = "STOP_SIBLINGS"
CT_STOP_BRANCH   = "STOP_BRANCH"
CT_STOP_ALL      = "STOP_ALL"
```

## Handle Structure

The runtime handle (created by `ct_runtime.create`) contains:

```lua
handle = {
    nodes             = { [ltree_string] = node_table },
    main_functions    = { [name] = fn },
    one_shot_functions = { [name] = fn },
    boolean_functions = { [name] = fn },
    kb_table          = { [kb_name] = { root_node, node_ids } },
    event_strings     = { [name] = integer_id },
    idx_to_ltree      = { [integer] = ltree_string },
    ltree_to_index    = { [ltree_string] = integer },
    event_queue       = { },       -- FIFO list of event tables
    node_state        = { },       -- per-node mutable state
    active_tests      = { },       -- active KB names
    bitmask           = 0,         -- integer bitmask for data flow
    blackboard        = { },       -- mutable shared state
    timestamp         = 0.0,       -- current simulation time
    delta_time        = 0.1,       -- seconds per tick
    tick_count        = 0,
    max_ticks         = 5000,
}
```
