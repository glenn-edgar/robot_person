# Controlled Node Patterns

Controlled nodes allow external clients to enable/disable subtrees at runtime, with optional exception handling for error recovery.

## Basic Controlled Node

A controlled node container wraps child columns that can be activated by client commands:

```lua
ct:define_controlled_node_container("drone_controller")

    ct:define_controlled_node("fly_up", false)
        ct:asm_log_message("flying up")
        ct:asm_wait_time(3.0)
        ct:asm_log_message("altitude reached")
    ct:end_controlled_node()

    ct:define_controlled_node("fly_down", false)
        ct:asm_log_message("descending")
        ct:asm_wait_time(3.0)
        ct:asm_log_message("landed")
    ct:end_controlled_node()

    ct:define_controlled_node("fly_straight", false)
        ct:asm_log_message("cruising")
        ct:asm_halt()
    ct:end_controlled_node()

ct:end_controlled_node_container()
```

The second parameter to `define_controlled_node` is `auto_start` — set to `false` so nodes wait for client activation.

## Client Control

A separate column acts as the client, enabling and disabling controlled nodes by reference:

```lua
local client_col = ct:define_column("client", nil, nil, nil, nil, nil, true)

    ct:asm_log_message("activating fly_up")
    ct:asm_enable_nodes({fly_up_node})
    ct:asm_wait_time(5.0)

    ct:asm_log_message("switching to fly_straight")
    ct:asm_disable_nodes({fly_up_node})
    ct:asm_enable_nodes({fly_straight_node})
    ct:asm_wait_time(10.0)

    ct:asm_log_message("activating fly_down")
    ct:asm_disable_nodes({fly_straight_node})
    ct:asm_enable_nodes({fly_down_node})
    ct:asm_wait_time(5.0)

    ct:asm_terminate_system()

ct:end_column(client_col)
```

## Client Controlled Node

For programmatic control via a boolean function:

```lua
ct:define_client_controlled_node("mission_controller", "MISSION_BOOLEAN_FN")
    ct:define_controlled_node("waypoint_1", false)
        -- ...
    ct:end_controlled_node()
    ct:define_controlled_node("waypoint_2", false)
        -- ...
    ct:end_controlled_node()
ct:end_client_controlled_node()
```

The boolean function receives events and returns `true` to indicate completion. It can enable/disable child nodes programmatically based on mission state.

## With Exception Handling

Controlled nodes can be wrapped in exception handlers for error recovery:

```lua
ct:define_exception_handler("flight_handler")

    ct:define_main_column("flight_main")
        ct:define_controlled_node_container("flight_modes")
            ct:define_controlled_node("takeoff", true)
                ct:asm_log_message("taking off")
                ct:asm_wait_time(3.0)
                -- If sensor fails here, exception propagates to handler
            ct:end_controlled_node()
        ct:end_controlled_node_container()
    ct:end_main_column()

    ct:define_recovery_column("emergency_land")
        ct:asm_log_message("emergency landing")
        ct:asm_wait_time(2.0)
    ct:end_recovery_column()

    ct:define_finalize_column("shutdown")
        ct:asm_log_message("motors off")
    ct:end_finalize_column()

ct:end_exception_handler()
```

## Typed Client/Server RPC Pattern (Avro Ports)

For type-safe request/response communication using Avro packet ports:

### DSL Definition
```lua
-- Define ports (schema verified at compile time)
local req_port = ct:make_control_port("drone_control", "fly_straight_request", 0, "FLY_STRAIGHT_REQ")
local rsp_port = ct:make_control_port("drone_control", "fly_straight_response", 1, "FLY_STRAIGHT_RSP")

-- Server (controlled node with typed ports)
ct:controlled_node_container("drone_controller")
    ct:controlled_node("fly_straight", "fly_node", "FLY_MONITOR", {},
        req_port, rsp_port)
        ct:asm_log_message("flying straight")
        ct:asm_wait_time(2.0)
        ct:asm_log_message("flight complete")
    ct:end_controlled_node()
ct:end_controlled_node_container()

-- Client (sends request, waits for response)
ct:client_controlled_node("fly_straight", "ON_FLY_COMPLETE", {},
    req_port, rsp_port)
```

### User Function Signatures (CFL Runtime)
```lua
-- Server boolean (monitor): called with request data
function FLY_MONITOR(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end
    return true  -- accept request
end

-- Client boolean: called with response data
function ON_FLY_COMPLETE(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end
    -- Check response_port event match
    local ns = require("cfl_common").get_node_state(handle, node_idx)
    if ns.response_port and event_id == ns.response_port.event_id then
        return true  -- command complete
    end
    return false
end
```

## Runtime Implementation (`runtime/cfl_builtins.lua`)

### Client Activation Sequence (CFL_CLIENT_CONTROLLED_NODE_MAIN)
1. Enable server node + all ancestors (sets CT_FLAG_USER3 | CT_FLAG_USER2)
2. Call server init one-shot and boolean with CFL_INIT_EVENT
3. Store client node_idx on server's node_state for response routing
4. Send request event (high priority) to server
5. Return CFL_HALT (wait for response)

### Server Execution (CFL_CONTROLLED_NODE_MAIN)
1. Match request event by event_id + event_type == STREAMING_DATA
2. Call boolean (user processes request)
3. Enable all children (processing pipeline)
4. Return CFL_HALT until children complete
5. On term: send response to client via high-priority event

### Port/Packet Support
- Ports decoded from node_data by `cfl_streaming.decode_port()`
- Request packet created as Lua table `{ aux_data = ... }` during client init
- Response packet sent as Lua table `{ success = true }` or FFI cdata
- Schema hash matching via `cfl_streaming.event_matches()` for FFI packets

## Use Cases

- **ROS planner flight modes**: fly_straight, fly_arc, fly_up, fly_down with typed request/response
- **Robot arm sequences**: pick, place, home — external planner controls sequence with data payloads
- **Manufacturing steps**: setup, process, inspect — operator controls progression
- **Mission compiler**: sequential client commands with exception handling

## Test Reference

- **Test 23 (twenty_seventh_test)**: 4 sequential flight commands (straight, arc, up, down) — full client/server lifecycle
- **Test 24 (twenty_eighth_test)**: Client controlled node with exception handling
- **Test 25 (twenty_ninth_test)**: Multiple controlled node patterns

Run with: `luajit dsl_tests/incremental_binary/test_cfl.lua 23`

See [README_incremental_binary.md](README_incremental_binary.md) for the full test list.
