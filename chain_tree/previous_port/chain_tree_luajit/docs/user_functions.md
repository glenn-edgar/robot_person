# User Functions (ChainTree)

User functions extend the dict runtime with application-specific behavior. They are organized into three categories matching the built-in function types.

## Function Types and Signatures

### Main functions

```lua
fn(handle, bool_fn, node, event_id, event_data) -> return_code_string
```

Called every tick for enabled+initialized nodes. Must return a string return code (`"CFL_CONTINUE"`, `"CFL_HALT"`, `"CFL_DISABLE"`, `"CFL_RESET"`, `"CFL_TERMINATE"`, `"CFL_SKIP_CONTINUE"`, `"CFL_TERMINATE_SYSTEM"`).

### One-shot functions

```lua
fn(handle, node) -> nil
```

Called once during node initialization or termination.

### Boolean functions

```lua
fn(handle, node, event_id, event_data) -> boolean
```

Called by main functions as auxiliary checks, or on init/terminate events. Should handle `CFL_INIT_EVENT` (event_id=0) and `CFL_TERMINATE_EVENT` (event_id=1) explicitly.

## Registration

User functions are registered via `loader.register_functions()`:

```lua
local M = { main = {}, one_shot = {}, boolean = {} }

M.one_shot.MY_INIT = function(handle, node) ... end
M.main.MY_MAIN = function(handle, bool_fn, node, event_id, event_data) ... end
M.boolean.MY_CHECK = function(handle, node, event_id, event_data) ... end

-- In test harness:
loader.register_functions(handle_data, builtins, M)
```

Multiple function tables can be passed to `register_functions`. They are merged in order; later registrations override earlier ones for the same name.

## Node Access Patterns

### Node data

```lua
local node_id = node.label_dict.ltree_name      -- ltree path string
local parent  = node.label_dict.parent           -- parent ltree string
local links   = node.label_dict.links            -- child ltree strings
local nd      = node.node_dict                   -- runtime config data
local msg     = nd.message                       -- custom fields from DSL
local ud      = nd.column_data.user_data         -- user_data from DSL
```

### Per-node mutable state

```lua
local common = require("ct_common")

-- Allocate (creates if absent)
local ns = common.alloc_node_state(handle, node_id)

-- Read (returns nil if absent)
local ns = common.get_node_state(handle, node_id)

-- Store arbitrary data
ns.my_counter = 0
ns.my_flag = true
```

Node state is keyed by ltree string in `handle.node_state` and is cleared when the node is disabled/terminated.

### Handle fields

```lua
handle.timestamp          -- current simulation time (float)
handle.bitmask            -- integer bitmask for data flow
handle.blackboard         -- shared mutable state table
handle.event_queue        -- push events: table.insert(handle.event_queue, {...})
handle.nodes[ltree]       -- lookup any node by ltree path
handle.ltree_to_index     -- ltree string to integer index (for display)
```

## Examples from user_functions_dict.lua

### One-shot: valve activation

```lua
M.one_shot.ACTIVATE_VALVE = function(handle, node)
    local state = node.node_dict and node.node_dict.state
    if state == "open" then
        print("Valve is open")
    end
end
```

### Boolean: while loop condition

```lua
M.boolean.WHILE_TEST = function(handle, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then return false end

    if event_id == defs.CFL_INIT_EVENT then
        ns.loop_count = node.node_dict and node.node_dict.user_data
            and node.node_dict.user_data.count or 0
        return false
    end
    if event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    if (ns.current_iteration or 0) >= ns.loop_count then
        return false
    end
    return true
end
```

### Main: event filtering

```lua
M.main.SM_EVENT_FILTERING_MAIN = function(handle, bool_fn, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if ns and event_id == ns.event_id then
        return defs.CFL_CONTINUE
    end
    return defs.CFL_CONTINUE
end
```

### Streaming packet functions

The test suite includes FFI-based Avro packet functions for streaming pipelines:

- `GENERATE_AVRO_PACKET` -- one-shot that creates a packet and sends as event
- `PACKET_FILTER` -- boolean that checks packet fields, returns false to block
- `PACKET_TAP` -- boolean that logs packet data, returns true to pass through
- `PACKET_TRANSFORM` -- boolean that accumulates and averages packets
- `PACKET_SINK_A` / `PACKET_SINK_B` -- boolean consumers (raw / filtered)
- `PACKET_COLLECTOR` -- boolean that collects packets across ports
- `PACKET_VERIFY_X_RANGE` -- boolean that validates packet x field range

### Drone control functions

Controlled node client/server pattern:

- `ON_FLY_STRAIGHT_COMPLETE` / `ON_FLY_ARC_COMPLETE` / etc. -- boolean: returns true when response event received
- `fly_straight_monitor` / `fly_arc_monitor` / etc. -- boolean server-side: accepts requests
- `UPDATE_FLY_STRAIGHT_FINAL` / etc. -- one-shot finalization (no-ops)
