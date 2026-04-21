local ColumnFlow = require("lua_support.column_flow")

local BasicCfLinks = setmetatable({}, { __index = ColumnFlow })
BasicCfLinks.__index = BasicCfLinks

function BasicCfLinks.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, BasicCfLinks)
end

function BasicCfLinks:asm_one_shot_handler(one_shot_fn, one_shot_data)
    self:define_column_link("CFL_DISABLE", one_shot_fn, "CFL_NULL", "CFL_NULL", one_shot_data)
end

function BasicCfLinks:asm_bidirectional_one_shot_handler(one_shot_fn, termination_fn, one_shot_data)
    self:define_column_link("CFL_CONTINUE", one_shot_fn, "CFL_NULL", termination_fn, one_shot_data)
end

function BasicCfLinks:asm_log_message(message)
    if type(message) ~= "string" then
        error("message must be a string")
    end
    local message_data = { message = message }
    self:asm_one_shot_handler("CFL_LOG_MESSAGE", message_data)
end

function BasicCfLinks:asm_reset()
    self:define_column_link("CFL_RESET", "CFL_NULL", "CFL_NULL", "CFL_NULL", {})
end

function BasicCfLinks:asm_terminate()
    self:define_column_link("CFL_TERMINATE", "CFL_NULL", "CFL_NULL", "CFL_NULL", {})
end

function BasicCfLinks:asm_halt()
    self:define_column_link("CFL_HALT", "CFL_NULL", "CFL_NULL", "CFL_NULL", {})
end

function BasicCfLinks:asm_disable()
    self:define_column_link("CFL_DISABLE", "CFL_NULL", "CFL_NULL", "CFL_NULL", {})
end

function BasicCfLinks:asm_terminate_system()
    self:define_column_link("CFL_TERMINATE_SYSTEM", "CFL_NULL", "CFL_NULL", "CFL_NULL", {})
end

function BasicCfLinks:asm_send_system_event(event_id, event_data)
    event_id = self.ctb:register_event(event_id)
    local data = { event_id = event_id, event_data = event_data }
    self:asm_one_shot_handler("CFL_SEND_SYSTEM_EVENT", data)
end

function BasicCfLinks:asm_send_named_event(node_id, event_id, event_data)
    if type(node_id) ~= "string" then
        error("Node id must be a string")
    end
    if type(event_id) ~= "string" then
        error("Event id must be a string")
    end
    if type(event_data) ~= "table" then
        error("Event data must be a table")
    end
    if self:verify_node_id(node_id) then
        error("Node id is not valid ltree node id")
    end
    node_id = self.ctb:get_node_index(node_id)
    event_id = self.ctb:register_event(event_id)
    local data = { node_id = node_id, event_id = event_id, event_data = event_data }
    self:asm_one_shot_handler("CFL_SEND_NAMED_EVENT", data)
end

function BasicCfLinks:asm_send_immediate_event(node_id, event_id, event_data)
    if type(node_id) ~= "string" then
        error("Node id must be a string")
    end
    if type(event_id) ~= "string" then
        error("Event id must be a string")
    end
    if type(event_data) ~= "table" then
        error("Event data must be a table")
    end
    if self:verify_node_id(node_id) then
        error("Node id is not valid ltree node id")
    end
    node_id = self.ctb:get_node_index(node_id)
    event_id = self.ctb:register_event(event_id)
    local data = { node_id = node_id, event_id = event_id, event_data = event_data }
    self:asm_one_shot_handler("CFL_SEND_IMMEDIATE_EVENT", data)
end

function BasicCfLinks:asm_send_parent_event(level, event_id, event_data)
    if level < 0 then
        error("Level must be greater than 0")
    end

    local parent_path = self.ctb.ltree_stack

    if #parent_path <= level then
        error("Level is too high")
    end

    -- Python: parent_path[:level][-1]  →  last element of the first `level` elements
    -- That is parent_path[level] (1-indexed in Lua)
    local event_path = parent_path[level]
    event_id = self.ctb:register_event(event_id)
    event_path = self.ctb:get_node_index(event_path)
    self:asm_send_named_event(event_path, event_id, event_data)
end

function BasicCfLinks:asm_enable_nodes(nodes)
    local temp_nodes = {}
    for i = 1, #nodes do
        temp_nodes[#temp_nodes + 1] = self.ctb:get_node_index(nodes[i])
    end
    self:asm_one_shot_handler("CFL_ENABLE_NODES", { nodes = temp_nodes })
end

function BasicCfLinks:asm_disable_nodes(nodes)
    local temp_nodes = {}
    for i = 1, #nodes do
        temp_nodes[#temp_nodes + 1] = self.ctb:get_node_index(nodes[i])
    end
    self:asm_one_shot_handler("CFL_DISABLE_NODES", { nodes = temp_nodes })
end

function BasicCfLinks:asm_event_logger(message, events)
    if type(message) ~= "string" then
        error("Message must be a string")
    end
    if type(events) ~= "table" then
        error("Events must be a table")
    end
    local temp_events = {}
    for i = 1, #events do
        temp_events[#temp_events + 1] = self.ctb:register_event(events[i])
    end
    return self:define_column_link("CFL_EVENT_LOGGER", "CFL_EVENT_LOGGER_INIT",
        "CFL_NULL", "CFL_EVENT_LOGGER_TERM",
        { message = message, events = temp_events })
end

--- wd_time_count is the time count in seconds
function BasicCfLinks:asm_watch_dog_node(wd_time_count, wd_reset, wd_fn, wd_fn_data)
    if type(wd_time_count) ~= "number" then
        error("Watchdog time out must be a number")
    end
    if type(wd_reset) ~= "boolean" then
        error("Watchdog reset must be a boolean")
    end

    local wd_data = {
        wd_time_count = wd_time_count,
        wd_reset = wd_reset,
        wd_fn = wd_fn,
        wd_fn_data = wd_fn_data,
    }

    if wd_fn ~= nil then
        self.ctb:add_one_shot_function(wd_fn)
    end

    return self:define_column_link("CFL_WATCH_DOG_MAIN", "CFL_WATCH_DOG_INIT",
        "CFL_NULL", "CFL_WATCH_DOG_TERM", wd_data)
end

function BasicCfLinks:asm_node_element(main_function, initialization_function, aux_function,
                                        termination_function, node_data)
    initialization_function = initialization_function or "CFL_NULL"
    aux_function = aux_function or "CFL_NULL"
    termination_function = termination_function or "CFL_NULL"
    node_data = node_data or {}

    if type(main_function) ~= "string" then
        error("Main function must be a string")
    end
    if type(initialization_function) ~= "string" then
        error("Initialization function must be a string")
    end
    if type(aux_function) ~= "string" then
        error("Aux function must be a string")
    end
    if type(termination_function) ~= "string" then
        error("Termination function must be a string")
    end
    if type(node_data) ~= "table" then
        error("Node data must be a table")
    end

    return self:define_column_link(main_function, initialization_function,
        aux_function, termination_function, node_data)
end

function BasicCfLinks:asm_enable_watch_dog(node_id)
    if type(node_id) ~= "string" then
        error("Node id must be a string")
    end
    local node_data = self.ctb.yaml_data[node_id]
    if node_data == nil then
        error("Node id is not valid chain tree node id")
    end
    local main_function_name = node_data.label_dict.main_function_name
    if main_function_name ~= "CFL_WATCH_DOG_MAIN" then
        error("Node is not a watch dog node")
    end
    node_id = self.ctb:get_node_index(node_id)
    return self:asm_one_shot_handler("CFL_ENABLE_WATCH_DOG", { node_id = node_id })
end

function BasicCfLinks:asm_disable_watch_dog(node_id)
    if type(node_id) ~= "string" then
        error("Node id must be a string")
    end
    local node_data = self.ctb.yaml_data[node_id]
    if node_data == nil then
        error("Node id is not valid ltree node id")
    end
    local main_function_name = node_data.label_dict.main_function_name
    if main_function_name ~= "CFL_WATCH_DOG_MAIN" then
        error("Node is not a watch dog node")
    end
    node_id = self.ctb:get_node_index(node_id)
    return self:asm_one_shot_handler("CFL_DISABLE_WATCH_DOG", { node_id = node_id })
end

function BasicCfLinks:asm_pat_watch_dog(node_id)
    if type(node_id) ~= "string" then
        error("Node id must be a string")
    end
    local node_data = self.ctb.yaml_data[node_id]
    if node_data == nil then
        error("Node id is not valid ltree node id")
    end
    node_id = self.ctb:get_node_index(node_id)
    return self:asm_one_shot_handler("CFL_PAT_WATCH_DOG", { node_id = node_id })
end

function BasicCfLinks:asm_start_stop_tests(stop_tests, start_tests)
    if type(stop_tests) ~= "table" then
        error("Stop tests must be a table")
    end
    if type(start_tests) ~= "table" then
        error("Start tests must be a table")
    end
    local test_data = { stop_tests = stop_tests, start_tests = start_tests }
    self:asm_one_shot_handler("CFL_START_STOP_TESTS", test_data)
    self:asm_wait_for_event("CFL_TIMER_EVENT", 2)
end

return BasicCfLinks