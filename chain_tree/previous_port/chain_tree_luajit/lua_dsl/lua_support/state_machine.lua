local ColumnFlow = require("lua_support.column_flow")
local json_null = setmetatable({}, { __tostring = function() return "null" end })

local StateMachine = setmetatable({}, { __index = ColumnFlow })
StateMachine.__index = StateMachine

function StateMachine.new(ctb)
    local self = ColumnFlow.new(ctb)
    self.sm_stack = {}
    self.sm_name_dict = {}
    return setmetatable(self, StateMachine)
end

function StateMachine:initialize_state_machine_stack()
    self.sm_stack = {}
    self.sm_name_dict = {}
end

function StateMachine:add_sm_name_dict(sm_name)
    if self.sm_name_dict[sm_name] then
        error("State machine " .. sm_name .. " already exists")
    end
    self.sm_name_dict[sm_name] = true
end

function StateMachine:check_for_balance_sm()
    if #self.sm_stack ~= 0 then
        error("State machines have not been closed")
    end
end

function StateMachine:define_state_machine(column_name, sm_name, state_names, initial_state,
                                            auto_start, aux_function_name)
    aux_function_name = aux_function_name or "CFL_STATE_MACHINE_NULL"

    self:add_sm_name_dict(sm_name)

    local state_node = self:define_column(
        column_name,
        "CFL_STATE_MACHINE_MAIN",
        "CFL_STATE_MACHINE_INIT",
        "CFL_STATE_MACHINE_TERM",
        aux_function_name,
        {},          -- column_data
        auto_start,
        "SM_" .. string.sub(sm_name, 1, 4)  -- label
    )

    self:_initialize_state_links(state_node, sm_name, state_names, initial_state)
    self.sm_stack[#self.sm_stack + 1] = sm_name
    return state_node
end

function StateMachine:define_state(state_name, column_data)
    if type(state_name) ~= "string" then
        error("State name must be a string")
    end
    column_data = column_data or {}
    if type(column_data) ~= "table" then
        error("Column data must be a table")
    end

    local state_node = self:define_column(
        state_name,
        nil, nil, nil, nil,  -- use defaults
        column_data,
        nil,                 -- auto_start default
        "STATE_" .. string.sub(state_name, 1, 4)  -- label
    )

    local state_node_id = self.ctb:get_node_index(state_node)
    self:_add_state_link(state_name, state_node_id)
    return state_node
end

function StateMachine:terminate_state_machine(sm_node_id)
    if type(sm_node_id) ~= "string" then
        error("State machine node id must be a string")
    end
    self:asm_one_shot_handler("CFL_TERMINATE_STATE_MACHINE", { sm_node_id = sm_node_id })
end

function StateMachine:reset_state_machine(sm_node_id)
    if type(sm_node_id) ~= "string" then
        error("State machine node id must be a string")
    end
    self:asm_one_shot_handler("CFL_RESET_STATE_MACHINE", { sm_node_id = sm_node_id })
end

function StateMachine:change_state(sm_node_id, new_state, sync_event_id)
    if type(sm_node_id) ~= "string" then
        error("State machine node id must be a string")
    end
    if type(new_state) ~= "string" then
        error("New state must be a string")
    end
    if #self.sm_stack == 0 then
        error("State machine not defined")
    end

    if sync_event_id ~= nil then
        sync_event_id = self.ctb:register_event(sync_event_id)
    end

    local node_id = self.ctb:get_node_index(sm_node_id)
    local node_data = {
        node_id = node_id,
        new_state = new_state,
    }
    node_data.sync_event_id = sync_event_id or json_null

    self:asm_one_shot_handler("CFL_CHANGE_STATE", node_data)
end
function StateMachine:end_state_machine(state_node, sm_name)
    if #self.sm_stack == 0 then
        error("State machine not defined")
    end

    local popped_sm = table.remove(self.sm_stack)
    if popped_sm ~= sm_name then
        error("State machine mismatch")
    end

    local ref_data = self.ctb.yaml_data[state_node]

    if not ref_data.label_dict.state_links then
        error("state machine not found")
    end

    local state_names = ref_data.label_dict.state_names
    local defined_states = ref_data.label_dict.defined_states

    if #state_names ~= #defined_states then
        error("State states are not defined")
    end

    -- Build a set of defined states for fast lookup
    local defined_set = {}
    for i = 1, #defined_states do
        defined_set[defined_states[i]] = true
    end

    for i = 1, #state_names do
        if not defined_set[state_names[i]] then
            error("State link not found for " .. state_names[i])
        end
    end

    -- Find initial_state index (0-based to match Python's list.index())
    local initial_state = ref_data.label_dict.initial_state
    local initial_state_number = nil
    for i = 1, #state_names do
        if state_names[i] == initial_state then
            initial_state_number = i - 1  -- 0-based like Python
            break
        end
    end

    ref_data.node_dict.column_data.initial_state_number = initial_state_number

    -- Copy state_names into column_data
    local names_copy = {}
    for i = 1, #state_names do names_copy[i] = state_names[i] end
    ref_data.node_dict.column_data.state_names = names_copy

    self:end_column(state_node)
end

--- Private: initialize state link structures on a state machine node.
--- (Python name-mangled as __initialize_state_links)
function StateMachine:_initialize_state_links(state_node, sm_name, state_names, initial_state)
    if type(state_node) ~= "string" then
        error("State node must be a string")
    end
    if type(sm_name) ~= "string" then
        error("State machine name must be a string")
    end
    if type(state_names) ~= "table" then
        error("State names must be a table")
    end

    local ref_data = self.ctb.yaml_data[state_node]

    -- Check initial_state is in state_names
    local found = false
    for i = 1, #state_names do
        if state_names[i] == initial_state then
            found = true
            break
        end
    end
    if not found then
        error("Initial state " .. initial_state .. " not found in state names")
    end

    ref_data.label_dict.initial_state = initial_state
    ref_data.label_dict.sm_name = sm_name
    ref_data.label_dict.state_links = {}
    ref_data.label_dict.state_names = state_names
    ref_data.label_dict.defined_states = {}

    self.ctb.yaml_data[state_node] = ref_data
end

--- Protected: add a state link to the parent state machine node.
function StateMachine:_add_state_link(state, node_id)
    if #self.sm_stack == 0 then
        error("State machine not defined")
    end
    if type(node_id) ~= "number" then
        error("node_id must be a number")
    end

    -- ltree_stack[-2] in Python → second from top
    local stack = self.ctb.ltree_stack
    local ref_node = stack[#stack - 1]
    local ref_data = self.ctb.yaml_data[ref_node]

    if not ref_data.label_dict.state_links then
        error("state machine not found")
    end

    -- Check state is in state_names
    local state_names = ref_data.label_dict.state_names
    local found = false
    for i = 1, #state_names do
        if state_names[i] == state then found = true; break end
    end
    if not found then
        error("State not defined")
    end

    -- Check state not already defined
    local defined = ref_data.label_dict.defined_states
    for i = 1, #defined do
        if defined[i] == state then
            error("State already defined")
        end
    end

    defined[#defined + 1] = state
    local links = ref_data.label_dict.state_links
    links[#links + 1] = node_id

    self.ctb.yaml_data[ref_node] = ref_data
end

return StateMachine