local ColumnFlow = {}
ColumnFlow.__index = ColumnFlow

function ColumnFlow.new(ctb)
    local self = setmetatable({}, ColumnFlow)
    self.ctb = ctb
    return self
end

function ColumnFlow:define_local_arena(column_name, arena_size)
    return self:define_column(column_name,
        "CFL_LOCAL_ARENA_MAIN",
        "CFL_LOCAL_ARENA_INIT",
        "CFL_LOCAL_ARENA_TERM",
        "CFL_COLUMN_NULL",
        { arena_size = arena_size },
        false,
        "COLUMN",
        true)
end

function ColumnFlow:define_column(column_name, main_function, initialization_function, termination_function,
                                   aux_function, column_data, auto_start, label, links_flag)
    -- defaults
    main_function = main_function or "CFL_COLUMN_MAIN"
    initialization_function = initialization_function or "CFL_COLUMN_INIT"
    termination_function = termination_function or "CFL_COLUMN_TERM"
    aux_function = aux_function or "CFL_COLUMN_NULL"
    column_data = column_data or nil
    auto_start = auto_start or false
    label = label or "COLUMN"
    if links_flag == nil then links_flag = true end

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(main_function) ~= "string" then
        error("Main function must be a string")
    end
    if type(initialization_function) ~= "string" then
        error("Initialization function must be a string")
    end
    if type(termination_function) ~= "string" then
        error("Termination function must be a string")
    end
    if type(auto_start) ~= "boolean" then
        error("Auto start must be a boolean")
    end

    local node_name = "_" .. tostring(self.ctb.link_number)
    self.ctb.link_number = self.ctb.link_number + 1
    table.insert(self.ctb.link_number_stack, self.ctb.link_number)
    self.ctb.link_number = 0

    local element_data = {}
    element_data.auto_start = auto_start
    element_data.column_data = column_data

    local temp_name = string.sub(column_name, 1, 4)
    column_name = self.ctb:add_node_element("COL_" .. temp_name, node_name, main_function,
        initialization_function, aux_function, termination_function, element_data, links_flag)

    self.ctb:add_one_shot_function(initialization_function)
    self.ctb:add_boolean_function(aux_function)
    self.ctb:add_one_shot_function(termination_function)

    return column_name
end

function ColumnFlow:define_gate_node(column_name, main_function, initialization_function, termination_function,
                                      aux_function, column_data, auto_start, links_flag)
    -- defaults
    main_function = main_function or "CFL_GATE_NODE_MAIN"
    initialization_function = initialization_function or "CFL_GATE_NODE_INIT"
    termination_function = termination_function or "CFL_GATE_NODE_TERM"
    aux_function = aux_function or "CFL_GATE_NODE_NULL"
    column_data = column_data or nil
    auto_start = auto_start or false
    if links_flag == nil then links_flag = true end

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(main_function) ~= "string" then
        error("Main function must be a string")
    end
    if type(initialization_function) ~= "string" then
        error("Initialization function must be a string")
    end
    if type(termination_function) ~= "string" then
        error("Termination function must be a string")
    end
    if type(aux_function) ~= "string" then
        error("Aux function must be a string")
    end
    if type(column_data) ~= "table" then
        error("Column data must be a table")
    end
    if type(auto_start) ~= "boolean" then
        error("Auto start must be a boolean")
    end

    local element_data = {}
    element_data.auto_start = auto_start
    element_data.column_data = column_data

    local node_name = "_" .. tostring(self.ctb.link_number)
    self.ctb.link_number = self.ctb.link_number + 1
    table.insert(self.ctb.link_number_stack, self.ctb.link_number)
    self.ctb.link_number = 0

    self.ctb:add_main_function(main_function)
    self.ctb:add_one_shot_function(initialization_function)
    self.ctb:add_boolean_function(aux_function)
    self.ctb:add_one_shot_function(termination_function)

    local temp_name
    if links_flag then
        temp_name = string.sub(column_name, 1, 4)
    else
        temp_name = column_name
    end

    return self.ctb:add_node_element("GATE_" .. temp_name, node_name, main_function,
        initialization_function, aux_function, termination_function, column_data, links_flag)
end

function ColumnFlow:define_fork_column(column_name, main_function, initialization_function, termination_function,
                                        aux_function, column_data, auto_start, label)
    -- defaults
    main_function = main_function or "CFL_FORK_MAIN"
    initialization_function = initialization_function or "CFL_FORK_INIT"
    termination_function = termination_function or "CFL_FORK_TERM"
    aux_function = aux_function or "CFL_NULL"
    column_data = column_data or {}
    auto_start = auto_start or false
    label = label or "FORK"

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(main_function) ~= "string" then
        error("Main function must be a string")
    end
    if type(initialization_function) ~= "string" then
        error("Initialization function must be a string")
    end
    if type(termination_function) ~= "string" then
        error("Termination function must be a string")
    end
    if type(aux_function) ~= "string" then
        error("Aux function must be a string")
    end
    if type(column_data) ~= "table" then
        error("Column data must be a table")
    end

    local node_name = "_" .. tostring(self.ctb.link_number)
    self.ctb.link_number = self.ctb.link_number + 1
    table.insert(self.ctb.link_number_stack, self.ctb.link_number)
    self.ctb.link_number = 0

    self.ctb:add_one_shot_function(initialization_function)
    self.ctb:add_boolean_function(aux_function)
    self.ctb:add_one_shot_function(termination_function)

    return self.ctb:add_node_element("FORK_", node_name, main_function,
        initialization_function, aux_function, termination_function, column_data)
end

function ColumnFlow:define_while_column(column_name, main_function, initialization_function, termination_function,
                                         aux_function, user_data, auto_start, label)
    -- defaults
    main_function = main_function or "CFL_WHILE_MAIN"
    initialization_function = initialization_function or "CFL_WHILE_INIT"
    termination_function = termination_function or "CFL_WHILE_TERM"
    aux_function = aux_function or "CFL_NULL"
    user_data = user_data or {}
    auto_start = auto_start or false
    label = label or "WHILE"

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(main_function) ~= "string" then
        error("Main function must be a string")
    end
    if type(initialization_function) ~= "string" then
        error("Initialization function must be a string")
    end
    if type(termination_function) ~= "string" then
        error("Termination function must be a string")
    end
    if type(aux_function) ~= "string" then
        error("Aux function must be a string")
    end

    local node_name = "_" .. tostring(self.ctb.link_number)
    self.ctb.link_number = self.ctb.link_number + 1
    table.insert(self.ctb.link_number_stack, self.ctb.link_number)
    self.ctb.link_number = 0

    local column_data = { user_data = user_data, auto_start = auto_start }

    return self.ctb:add_node_element("WHILE_" .. column_name, node_name, main_function,
        initialization_function, aux_function, termination_function, column_data)
end

function ColumnFlow:define_for_column(column_name, number_of_iterations, main_function, initialization_function,
                                       termination_function, aux_function, user_data, auto_start, label)
    -- defaults
    main_function = main_function or "CFL_FOR_MAIN"
    initialization_function = initialization_function or "CFL_FOR_INIT"
    termination_function = termination_function or "CFL_FOR_TERM"
    aux_function = aux_function or "CFL_NULL"
    user_data = user_data or {}
    auto_start = auto_start or false
    label = label or "FOR"

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(main_function) ~= "string" then
        error("Main function must be a string")
    end
    if type(initialization_function) ~= "string" then
        error("Initialization function must be a string")
    end
    if type(termination_function) ~= "string" then
        error("Termination function must be a string")
    end
    if type(aux_function) ~= "string" then
        error("Aux function must be a string")
    end

    local column_data = {
        number_of_iterations = number_of_iterations,
        user_data = user_data,
        auto_start = auto_start,
    }

    local node_name = "_" .. tostring(self.ctb.link_number)
    self.ctb.link_number = self.ctb.link_number + 1
    table.insert(self.ctb.link_number_stack, self.ctb.link_number)
    self.ctb.link_number = 0

    local temp_name = string.sub(column_name, 1, 4)

    return self.ctb:add_node_element("FOR_" .. temp_name, node_name, main_function,
        initialization_function, aux_function, termination_function, column_data)
end

function ColumnFlow:define_join_link(parent_node_name)
    local node_data = { parent_node_name = parent_node_name }
    return self:define_column_link("CFL_JOIN_MAIN", "CFL_JOIN_INIT",
        "CFL_NULL", "CFL_JOIN_TERM", node_data)
end

function ColumnFlow:define_column_link(main_function_name, initialization_function_name, aux_function_name,
                                        termination_function_name, node_data, label)
    label = label or "LEAF"

    if type(node_data) ~= "table" then
        error("Node data must be a table")
    end

    local node_name = "_" .. tostring(self.ctb.link_number)
    self.ctb.link_number = self.ctb.link_number + 1

    local node_id = self.ctb:add_leaf_element(label, node_name, main_function_name,
        initialization_function_name, aux_function_name, termination_function_name, node_data)

    return node_id
end

function ColumnFlow:end_column(column_name)
    if self.sequence_dict and self.sequence_dict[column_name] then
        error("Sequence is active")
    end

    local column_data = self.ctb.yaml_data[column_name]
    local main_function_name = column_data.label_dict.main_function_name

    if main_function_name == "CFL_FOR_MAIN" or main_function_name == "CFL_WHILE_MAIN" then
        local links = column_data.label_dict.links
        -- count table entries (Lua tables don't have a direct len for hash parts)
        local link_count = 0
        for _ in pairs(links) do link_count = link_count + 1 end
        if link_count > 1 then
            error("Column has multiple links with for or while column")
        end
    end

    -- pop from link_number_stack
    local stack = self.ctb.link_number_stack
    self.ctb.link_number = stack[#stack]
    stack[#stack] = nil

    self.ctb:pop_node_element(column_name)
end

function ColumnFlow:verify_node_id(node_id)
    --[[
        Validate ltree label format without database connection.

        Rules:
        - Only alphanumeric characters and underscores
        - Cannot start with underscore
        - Length between 1-256 characters
        - No dots (dots separate path components in ltree)
    ]]
    if type(node_id) ~= "string" then
        return false
    end

    if #node_id == 0 or #node_id > 256 then
        return false
    end

    -- Must start with alphanumeric, then can contain alphanumeric + underscores
    return node_id:match("^[a-zA-Z0-9][a-zA-Z0-9_]*$") ~= nil
end

return ColumnFlow