local ColumnFlow = require("lua_support.column_flow")

local SequenceTil = setmetatable({}, { __index = ColumnFlow })
SequenceTil.__index = SequenceTil

function SequenceTil.new(ctb)
    local self = ColumnFlow.new(ctb)
    self.sequence_dict = {}
    self.sequence_active = false
    return setmetatable(self, SequenceTil)
end

function SequenceTil:define_sequence_start_node(column_name, main_function, initialization_function,
                                                 termination_function, aux_function, initialize_function,
                                                 finalize_function, user_data, auto_start)
    main_function = main_function or "CFL_SEQUENCE_START_MAIN"
    initialization_function = initialization_function or "CFL_SEQUENCE_START_INIT"
    termination_function = termination_function or "CFL_SEQUENCE_START_TERM"
    aux_function = aux_function or "CFL_NULL"
    initialize_function = initialize_function or "CFL_NULL"
    finalize_function = finalize_function or "CFL_NULL"
    user_data = user_data or {}
    if auto_start == nil then auto_start = false end

    if type(initialize_function) ~= "string" then
        error("initialize_function must be a string")
    end
    if type(finalize_function) ~= "string" then
        error("finalize_function must be a string")
    end

    self.ctb:add_one_shot_function(initialize_function)
    self.ctb:add_one_shot_function(finalize_function)

    local column_data = {
        initialize_function = initialize_function,
        finalize_function = finalize_function,
        user_data = user_data,
    }

    self.sequence_active = true

    return self:define_column(column_name, main_function, initialization_function,
        termination_function, aux_function, column_data, auto_start, "SEQ_ST")
end

function SequenceTil:define_sequence_til_pass_node(column_name, main_function, initialization_function,
                                                    termination_function, aux_function, finalize_function,
                                                    user_data, auto_start)
    main_function = main_function or "CFL_SEQUENCE_PASS_MAIN"
    initialization_function = initialization_function or "CFL_SEQUENCE_PASS_INIT"
    termination_function = termination_function or "CFL_SEQUENCE_PASS_TERM"
    aux_function = aux_function or "CFL_NULL"
    finalize_function = finalize_function or "CFL_NULL"
    user_data = user_data or {}
    if auto_start == nil then auto_start = false end

    if type(finalize_function) ~= "string" then
        error("finalize_function must be a string")
    end

    self.ctb:add_one_shot_function(finalize_function)

    local column_data = {
        finalize_function = finalize_function,
        user_data = user_data,
    }

    local return_node = self:define_column(column_name, main_function, initialization_function,
        termination_function, aux_function, column_data, auto_start, "SEQ_PASS")

    self.sequence_dict[return_node] = true
    return return_node
end

function SequenceTil:define_sequence_til_fail_node(column_name, main_function, initialization_function,
                                                    termination_function, aux_function, finalize_function,
                                                    user_data, auto_start)
    main_function = main_function or "CFL_SEQUENCE_FAIL_MAIN"
    initialization_function = initialization_function or "CFL_SEQUENCE_FAIL_INIT"
    termination_function = termination_function or "CFL_SEQUENCE_FAIL_TERM"
    aux_function = aux_function or "CFL_NULL"
    finalize_function = finalize_function or "CFL_NULL"
    user_data = user_data or {}
    if auto_start == nil then auto_start = false end

    if type(finalize_function) ~= "string" then
        error("finalize_function must be a string")
    end

    self.ctb:add_one_shot_function(finalize_function)

    local column_data = {
        finalize_function = finalize_function,
        user_data = user_data,
    }

    local return_node = self:define_column(column_name, main_function, initialization_function,
        termination_function, aux_function, column_data, auto_start, "SEQ_FAIL")

    self.sequence_dict[return_node] = true
    return return_node
end

function SequenceTil:define_supervisor_node(column_name, main_function, initialization_function,
                                             termination_function, aux_function, user_data,
                                             restart_enabled, termination_type, reset_limited_enabled,
                                             max_reset_number, reset_window, auto_start,
                                             finalize_function, finalize_function_data, label)
    main_function = main_function or "CFL_SUPERVISOR_MAIN"
    initialization_function = initialization_function or "CFL_SUPERVISOR_INIT"
    termination_function = termination_function or "CFL_SUPERVISOR_TERM"
    aux_function = aux_function or "CFL_NULL"
    if restart_enabled == nil then restart_enabled = true end
    termination_type = termination_type or 0
    if reset_limited_enabled == nil then reset_limited_enabled = false end
    max_reset_number = max_reset_number or 1
    reset_window = reset_window or 10
    if auto_start == nil then auto_start = false end
    finalize_function = finalize_function or "CFL_NULL"
    finalize_function_data = finalize_function_data or {}
    label = label or "SUP"

    if type(column_name) ~= "string" then error("Column name must be a string") end
    if type(main_function) ~= "string" then error("Main function must be a string") end
    if type(initialization_function) ~= "string" then error("Initialization function must be a string") end
    if type(termination_function) ~= "string" then error("Termination function must be a string") end
    if type(aux_function) ~= "string" then error("Aux function must be a string") end
    if type(termination_type) ~= "number" then error("Termination type must be a number") end
    if type(reset_limited_enabled) ~= "boolean" then error("Reset limited enabled must be a boolean") end
    if type(max_reset_number) ~= "number" then error("Max reset number must be a number") end
    if type(reset_window) ~= "number" then error("Reset window must be a number") end
    if type(restart_enabled) ~= "boolean" then error("Restart enabled must be a boolean") end

    local supervisor_data = {
        termination_type = termination_type,
        restart_enabled = restart_enabled,
        reset_limited_enabled = reset_limited_enabled,
        max_reset_number = max_reset_number,
        reset_window = reset_window,
        finalize_function = finalize_function,
        finalize_function_data = finalize_function_data,
    }

    local column_data = {
        user_data = user_data,
        supervisor_data = supervisor_data,
    }

    self.ctb:add_one_shot_function(finalize_function)

    return self:define_column(column_name, main_function, initialization_function,
        termination_function, aux_function, column_data, auto_start, label)
end

function SequenceTil:define_supervisor_one_for_one_node(column_name, aux_function, user_data,
                                                         restart_enabled, reset_limited_enabled,
                                                         max_reset_number, reset_window, auto_start,
                                                         finalize_function, finalize_function_data)
    aux_function = aux_function or "CFL_NULL"
    user_data = user_data or {}
    if restart_enabled == nil then restart_enabled = true end
    if reset_limited_enabled == nil then reset_limited_enabled = false end
    max_reset_number = max_reset_number or 1
    reset_window = reset_window or 10
    if auto_start == nil then auto_start = false end
    finalize_function = finalize_function or "CFL_NULL"
    finalize_function_data = finalize_function_data or {}

    return self:define_supervisor_node(column_name, nil, nil, nil, aux_function, user_data,
        restart_enabled, 0, reset_limited_enabled, max_reset_number, reset_window,
        auto_start, finalize_function, finalize_function_data, "SUP_1_1")
end

function SequenceTil:define_supervisor_one_for_all_node(column_name, aux_function, user_data,
                                                         restart_enabled, reset_limited_enabled,
                                                         max_reset_number, reset_window, auto_start,
                                                         finalize_function, finalize_function_data)
    aux_function = aux_function or "CFL_NULL"
    user_data = user_data or {}
    if restart_enabled == nil then restart_enabled = true end
    if reset_limited_enabled == nil then reset_limited_enabled = false end
    max_reset_number = max_reset_number or 1
    reset_window = reset_window or 10
    if auto_start == nil then auto_start = false end
    finalize_function = finalize_function or "CFL_NULL"
    finalize_function_data = finalize_function_data or {}

    return self:define_supervisor_node(column_name, nil, nil, nil, aux_function, user_data,
        restart_enabled, 1, reset_limited_enabled, max_reset_number, reset_window,
        auto_start, finalize_function, finalize_function_data, "SUP_1_ALL")
end

function SequenceTil:define_supervisor_rest_for_all_node(column_name, aux_function, user_data,
                                                          restart_enabled, reset_limited_enabled,
                                                          max_reset_number, reset_window, auto_start,
                                                          finalize_function, finalize_function_data)
    aux_function = aux_function or "CFL_NULL"
    user_data = user_data or {}
    if restart_enabled == nil then restart_enabled = true end
    if reset_limited_enabled == nil then reset_limited_enabled = false end
    max_reset_number = max_reset_number or 1
    reset_window = reset_window or 10
    if auto_start == nil then auto_start = false end
    finalize_function = finalize_function or "CFL_NULL"
    finalize_function_data = finalize_function_data or {}

    return self:define_supervisor_node(column_name, nil, nil, nil, aux_function, user_data,
        restart_enabled, 2, reset_limited_enabled, max_reset_number, reset_window,
        auto_start, finalize_function, finalize_function_data, "SUP_REST_ALL")
end

function SequenceTil:define_mark_supervisor_node_failure(data)
    if type(data) ~= "table" then
        error("Data must be a table")
    end
    return self:define_column_link("CFL_DISABLE", "CFL_MARK_SUPERVISOR_NODE_FAILURE_INIT",
        "CFL_NULL", "CFL_NULL", data)
end

function SequenceTil:end_sequence_node(column_name)
    if not self.sequence_dict[column_name] then
        error("Sequence is not active")
    end
    self.sequence_dict[column_name] = nil
    self:end_column(column_name)
    self:join_sequence_element(column_name)
end

function SequenceTil:mark_sequence_true_link(parent_node_name, data)
    data = data or {}
    local node_data = { parent_node_name = parent_node_name, result = 1, data = data }
    self:define_column_link("CFL_DISABLE", "CFL_MARK_SEQUENCE",
        "CFL_NULL", "CFL_NULL", node_data)
end

function SequenceTil:mark_sequence_false_link(parent_node_name, data)
    data = data or {}
    local node_data = { parent_node_name = parent_node_name, result = 0, data = data }
    self:define_column_link("CFL_DISABLE", "CFL_MARK_SEQUENCE",
        "CFL_NULL", "CFL_NULL", node_data)
end

function SequenceTil:join_sequence_element(parent_node_name)
    return self:define_column_link(
        "CFL_JOIN_SEQUENCE_ELEMENT",
        "CFL_JOIN_SEQUENCE_ELEMENT_INIT",
        "CFL_NULL",
        "CFL_JOIN_SEQUENCE_ELEMENT_TERM",
        { parent_node_name = parent_node_name }
    )
end

return SequenceTil