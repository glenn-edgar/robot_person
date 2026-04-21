local ColumnFlow = require("lua_support.column_flow")
local fnv1a      = require("lua_support.fnv1a")

local ControlledNodes = setmetatable({}, { __index = ColumnFlow })
ControlledNodes.__index = ControlledNodes

--[[
    DSL for defining controlled (dead) nodes and their clients.

    Controlled nodes are dormant nodes that exist structurally within a container
    but do not receive ChainTree events until activated by a client node. This
    implements a client-server model where:

    - Server (controlled_node): Holds behavior, receives events when enabled
    - Client (client_controlled_node): Initiates activation, receives completion/exceptions
    - Container (controlled_node_container): Structural owner, memory scope

    Lifecycle:
        1. Client calls initialization method on server
        2. Client calls aux function with init event
        3. Client calls main function with configuration event (request_port data)
        4. Client sets enabled/initialized flags
        5. Server receives events, executes behavior
        6. Server sends completion event with response_port data
        7. Server clears flags, returns to dead state

    Exception routing:
        Exceptions in controlled nodes route to the client, not the structural
        parent. If unhandled, they bubble up the client's tree.

    Lifecycle coupling:
        If a client terminates, its controlled node is also terminated.
        One client controls exactly one server (enforced at runtime).
]]

function ControlledNodes.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, ControlledNodes)
end

--- Create a port definition for typed buffer communication.
---
--- Ports define the data contract between client and server nodes.
--- Buffer types are defined in .h files using Avro-style schemas,
--- identified by file name, record name, and handler ID.
--- The schema_hash is FNV-1a of "<file>.h:<record>" matching the C runtime.
---
--- @param file_name string   Name of .h file (without extension) containing buffer definition
--- @param record_name string  Name of the record type within the file
--- @param handler_id number  Identifier for specific buffer type within file
--- @param event string       Event name that carries this buffer data
--- @return table  Port definition with schema_hash, handler_id, and event_id
function ControlledNodes:make_control_port(file_name, record_name, handler_id, event)
    if type(file_name) ~= "string" then
        error("file_name must be a string (e.g. 'drone_control')")
    end
    if type(record_name) ~= "string" then
        error("record_name must be a string (e.g. 'fly_straight_request')")
    end
    if type(handler_id) ~= "number" then
        error("handler_id must be a number")
    end
    if type(event) ~= "string" then
        error("event must be a string")
    end
    -- Compute per-record hash: FNV-1a of "<file>.h:<record>"
    local hash_key = file_name .. ".h:" .. record_name
    local schema_hash = fnv1a.schema_hash(file_name, record_name)
    -- Convert to signed int32 for JSON round-trip through json_extract_int32_runtime
    if schema_hash > 0x7FFFFFFF then
        schema_hash = schema_hash - 0x100000000
    end
    local event_id = self.ctb:register_event(event)
    return { schema_hash = schema_hash, handler_id = handler_id, event_id = event_id }
end

--- Validate that a port is fully defined.
---
--- @param port table       Port dictionary to validate
--- @param port_name string  Name of port for error messages
--- @param node_name string  Name of node for error messages
function ControlledNodes:_validate_port_defined(port, port_name, node_name)
    if not port or next(port) == nil then
        error(port_name .. " must be defined for " .. node_name)
    end
    local required_fields = { "schema_hash", "handler_id", "event_id" }
    for _, field in ipairs(required_fields) do
        if port[field] == nil then
            error(port_name .. " missing required field '" .. field .. "' for " .. node_name)
        end
    end
end

--- Validate that client and server port definitions match.
---
--- @param port_name string   Name of port for error messages
--- @param client_port table  Client's port definition
--- @param server_port table  Server's port definition
--- @param api_name string    API name for error messages
function ControlledNodes:_validate_port_match(port_name, client_port, server_port, api_name)
    local fields = { "schema_hash", "handler_id" }
    for _, field in ipairs(fields) do
        if client_port[field] ~= server_port[field] then
            error(string.format(
                "%s %s mismatch for api '%s': client=%s, server=%s",
                port_name, field, api_name,
                tostring(client_port[field]), tostring(server_port[field])
            ))
        end
    end
end
--- Define a container for controlled nodes.
---
--- Containers provide structural ownership and memory scope for controlled
--- nodes. They do not control activation - that is the client's responsibility.
--- Containers auto-start with the tree.
---
--- @param column_name string  Identifier for this container in the tree
--- @return string  Node identifier for the created container
function ControlledNodes:controlled_node_container(column_name)
    return self:define_column(
        column_name,
        "CFL_CONTROLLED_NODE_CONTAINER_MAIN",
        "CFL_CONTROLLED_NODE_CONTAINER_INIT",
        "CFL_CONTROLLED_NODE_CONTAINER_TERM",
        "CFL_NULL",
        {},      -- column_data
        true     -- auto_start
    )
end

--- Define a controlled (dead) node within a container.
---
--- Controlled nodes are dormant until activated by a client. They exist
--- structurally in the tree with memory allocated, but do not receive
--- ChainTree events until enabled.
---
--- Must be defined as a child of a controlled_node_container.
--- Must be defined before its client_controlled_node.
---
--- @param api_name string  Registry key for client binding. Must be unique.
--- @param column_name string  Identifier for this node in the tree
--- @param aux_function_name string  C function name for aux event handling
--- @param aux_data table  Static configuration passed to aux function
--- @param request_port table  Typed buffer definition for activation data (from client)
--- @param response_port table  Typed buffer definition for completion data (to client)
--- @return string  Node identifier for the created controlled node
function ControlledNodes:controlled_node(api_name, column_name, aux_function_name, aux_data,
                                          request_port, response_port)
    -- Validate ports are defined
    self:_validate_port_defined(request_port, "request_port", column_name)
    self:_validate_port_defined(response_port, "response_port", column_name)

    -- Validate parent is a container
    local ltree_stack = self.ctb.ltree_stack
    local parent_node = ltree_stack[#ltree_stack]
    local parent_data = self.ctb.yaml_data[parent_node]

    local parent_main_function = parent_data.label_dict.main_function_name
    if parent_main_function ~= "CFL_CONTROLLED_NODE_CONTAINER_MAIN" then
        error("Parent node " .. parent_node .. " is not a controlled node container")
    end

    local column_data = {
        request_port = request_port,
        response_port = response_port,
        aux_data = aux_data,
    }

    local return_value = self:define_column(
        column_name,
        "CFL_CONTROLLED_NODE_MAIN",
        "CFL_CONTROLLED_NODE_INIT",
        "CFL_CONTROLLED_NODE_TERM",
        aux_function_name,
        column_data,
        false   -- auto_start
    )

    self.ctb:register_node_alias(api_name, return_value)
    return return_value
end

--- Define a client node that controls a dead node.
---
--- @param api_name string  Registry key matching a controlled_node
--- @param aux_function_name string  C function name for aux event handling
--- @param aux_data table  Static configuration passed to aux function
--- @param request_port table  Typed buffer definition for activation data
--- @param response_port table  Typed buffer definition for completion data
--- @return string  Node identifier for the created client node
function ControlledNodes:client_controlled_node(api_name, aux_function_name, aux_data,
                                                 request_port, response_port)
    -- Validate client ports are defined
    self:_validate_port_defined(request_port, "request_port", api_name)
    self:_validate_port_defined(response_port, "response_port", api_name)

    -- Get server node - use ltree for yaml lookup, index for C code
    local server_ltree = self.ctb:get_ltree_by_alias(api_name)
    local server_node_index = self.ctb:get_node_by_alias(api_name)
    local server_data = self.ctb.yaml_data[server_ltree]

    -- column_data is in node_dict, not label_dict
    local server_column_data = server_data.node_dict.column_data

    -- Get server ports
    local server_request_port = server_column_data.request_port
    local server_response_port = server_column_data.response_port

    -- Validate ports match server
    self:_validate_port_match("request_port", request_port, server_request_port, api_name)
    self:_validate_port_match("response_port", response_port, server_response_port, api_name)

    local node_data = {
        request_port = request_port,
        response_port = response_port,
        aux_data = aux_data,
        api_name = api_name,
        server_node_index = server_node_index,
    }

    return self:define_column_link(
        "CFL_CLIENT_CONTROLLED_NODE_MAIN",
        "CFL_CLIENT_CONTROLLED_NODE_INIT",
        aux_function_name,
        "CFL_CLIENT_CONTROLLED_NODE_TERM",
        node_data,
        "CLIENT"  -- label
    )
end

return ControlledNodes