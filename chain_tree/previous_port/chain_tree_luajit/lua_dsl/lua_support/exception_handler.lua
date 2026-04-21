--[[
    ExceptionHandler - DSL for exception catch/recovery/finalize columns.

    This class expects to be mixed into an object that also has ColumnFlow
    and BasicCfLinks methods (define_column, end_column, asm_one_shot_handler,
    define_column_link, etc.).

    Translated from Python to LuaJIT.
]]

local ExceptionHandler = {}
ExceptionHandler.__index = ExceptionHandler

function ExceptionHandler.new(ctb)
    local self = setmetatable({}, ExceptionHandler)
    self.ctb = ctb
    self.main_flag = false
    self.recovery_flag = false
    self.finalize_flag = false
    self.exception_catch_stack = {}
    self.exception_catch_flags = {}
    self.exception_catch_links = {}
    return self
end

function ExceptionHandler:define_exception_catch(column_name, aux_function_name, aux_function_data,
                                                  logging_function_name, logging_function_data, auto_start)
    logging_function_data = logging_function_data or {}
    if auto_start == nil then auto_start = true end

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(aux_function_name) ~= "string" then
        error("Exception function name must be a string")
    end
    if type(aux_function_data) ~= "table" then
        error("Aux function data must be a table")
    end
    if type(logging_function_name) ~= "string" then
        error("Logging function name must be a string")
    end
    if type(logging_function_data) ~= "table" then
        error("Logging function data must be a table")
    end

    self.ctb:add_one_shot_function(logging_function_name)

    local column_data = {
        logging_function = logging_function_name,
        logging_function_data = logging_function_data,
        aux_function_data = aux_function_data,
    }

    -- Push sentinel values for links and flags
    self.exception_catch_links[#self.exception_catch_links + 1] = { -1, -1, -1 }
    self.exception_catch_flags[#self.exception_catch_flags + 1] = { false, false, false }

    local return_column_name = self:define_column(
        column_name,
        "CFL_EXCEPTION_CATCH_MAIN",   -- main_function
        "CFL_EXCEPTION_CATCH_INIT",   -- initialization_function
        "CFL_EXCEPTION_CATCH_TERM",   -- termination_function
        aux_function_name,             -- aux_function
        column_data,
        auto_start,
        "EXCEP_CATCH"                  -- label
    )

    self.exception_catch_stack[#self.exception_catch_stack + 1] = return_column_name
    return return_column_name
end

function ExceptionHandler:define_main_exception_column(name, main_function, initialization_function,
                                                        termination_function, aux_function, column_data, auto_start)
    main_function = main_function or "CFL_COLUMN_MAIN"
    initialization_function = initialization_function or "CFL_COLUMN_INIT"
    termination_function = termination_function or "CFL_COLUMN_TERM"
    aux_function = aux_function or "CFL_COLUMN_NULL"
    column_data = column_data or {}
    if auto_start == nil then auto_start = true end

    if type(name) ~= "string" then
        error("Name must be a string")
    end
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
    if type(column_data) ~= "table" then
        error("Column data must be a table")
    end
    if type(auto_start) ~= "boolean" then
        error("Auto start must be a boolean")
    end

    self.exception_catch_flags[#self.exception_catch_flags][1] = true

    local col_name = self:define_column(
        name,
        main_function,
        initialization_function,
        termination_function,
        aux_function,
        column_data,
        auto_start,
        "EXCEP_MAIN"
    )

    self.exception_catch_links[#self.exception_catch_links][1] = self.ctb:get_node_index(col_name)
    return col_name
end

function ExceptionHandler:end_main_exception_column(name)
    local name_link = self.ctb:get_node_index(name)
    if name_link ~= self.exception_catch_links[#self.exception_catch_links][1] then
        error("Main exception column mismatch")
    end
    self:end_column(name)
end

function ExceptionHandler:define_recovery_column(name, max_steps, skip_condition_function, skip_condition_data)
    skip_condition_data = skip_condition_data or {}

    if type(name) ~= "string" then
        error("Name must be a string")
    end
    if type(max_steps) ~= "number" then
        error("Max steps must be a number")
    end
    if type(skip_condition_function) ~= "string" then
        error("Skip condition function must be a string")
    end
    if type(skip_condition_data) ~= "table" then
        error("Skip condition data must be a table")
    end
    if max_steps <= 0 then
        error("Max steps must be greater than 0")
    end

    local column_data = {
        max_steps = max_steps,
        skip_condition_data = skip_condition_data,
    }

    local col_name = self:define_column(
        name,
        "CFL_RECOVERY_MAIN",
        "CFL_RECOVERY_INIT",
        "CFL_RECOVERY_TERM",
        skip_condition_function,
        column_data,
        nil,              -- auto_start (default)
        "RECOVERY_LINK"   -- label
    )

    self.exception_catch_links[#self.exception_catch_links][2] = self.ctb:get_node_index(col_name)
    self.exception_catch_flags[#self.exception_catch_flags][2] = true
    return col_name
end

function ExceptionHandler:end_recovery_column(name)
    local name_link = self.ctb:get_node_index(name)
    if name_link ~= self.exception_catch_links[#self.exception_catch_links][2] then
        error("Recovery column mismatch")
    end

    local ref_data = self.ctb.yaml_data[name]
    local links = ref_data.label_dict.links
    local links_number = #links
    local max_steps = ref_data.node_dict.column_data.max_steps

    if links_number < max_steps + 2 then
        error("Recovery column has not the correct number of links")
    end

    self:end_column(name)
end

function ExceptionHandler:define_finalize_column(name, main_function, initialization_function,
                                                  termination_function, aux_function, column_data, auto_start)
    main_function = main_function or "CFL_COLUMN_MAIN"
    initialization_function = initialization_function or "CFL_COLUMN_INIT"
    termination_function = termination_function or "CFL_COLUMN_TERM"
    aux_function = aux_function or "CFL_COLUMN_NULL"
    column_data = column_data or {}
    if auto_start == nil then auto_start = true end

    if type(name) ~= "string" then
        error("Column name must be a string")
    end
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
    if type(column_data) ~= "table" then
        error("Column data must be a table")
    end
    if type(auto_start) ~= "boolean" then
        error("Auto start must be a boolean")
    end

    local col_name = self:define_column(
        name,
        main_function,
        initialization_function,
        termination_function,
        aux_function,
        column_data,
        auto_start,
        "EXCEP_MAIN"
    )

    self.exception_catch_links[#self.exception_catch_links][3] = self.ctb:get_node_index(col_name)
    self.exception_catch_flags[#self.exception_catch_flags][3] = true
    return col_name
end

function ExceptionHandler:end_finalize_column(name)
    local name_link = self.ctb:get_node_index(name)
    if name_link ~= self.exception_catch_links[#self.exception_catch_links][3] then
        error("Finalize column mismatch")
    end
    self:end_column(name)
end

function ExceptionHandler:exception_catch_end(exception_catch_name)
    if type(exception_catch_name) ~= "string" then
        error("Exception catch name must be a string")
    end
    if #self.exception_catch_stack == 0 then
        error("Exception catch stack is empty")
    end

    local popped = table.remove(self.exception_catch_stack)

    if popped ~= exception_catch_name then
        error("Exception catch mismatch")
    end

    local check_flag = table.remove(self.exception_catch_flags)

    if not check_flag[1] then
        error("Main Link not started")
    end
    if not check_flag[2] then
        error("Recovery Link not started")
    end
    if not check_flag[3] then
        error("Finalize Link not started")
    end

    local link_data = table.remove(self.exception_catch_links)

    local ref_data = self.ctb.yaml_data[exception_catch_name]
    ref_data.node_dict.column_data.exception_catch_links = {
        link_data[1], link_data[2], link_data[3]
    }

    self:end_column(exception_catch_name)
end

function ExceptionHandler:catch_all_exception(column_name, aux_function, aux_data, auto_start)
    aux_data = aux_data or {}
    if auto_start == nil then auto_start = true end

    if type(column_name) ~= "string" then
        error("Column name must be a string")
    end
    if type(aux_function) ~= "string" then
        error("Aux function must be a string")
    end
    if type(aux_data) ~= "table" then
        error("Aux data must be a table")
    end
    if type(auto_start) ~= "boolean" then
        error("Auto start must be a boolean")
    end

    return self:define_column(
        column_name,
        "CFL_EXCEPTION_CATCH_ALL_MAIN",
        "CFL_CATCH_ALL_EXCEPTION_INIT",
        "CFL_CATCH_ALL_EXCEPTION_TERM",
        aux_function,
        aux_data,
        auto_start,
        "CATCH_ALL_EXCEPTION"
    )
end

function ExceptionHandler:end_catch_all_exception(name)
    if type(name) ~= "string" then
        error("Name must be a string")
    end
    self:end_column(name)
end

function ExceptionHandler:asm_turn_heartbeat_on(time_out)
    return self:asm_one_shot_handler("CFL_TURN_HEARTBEAT_ON", { time_out = time_out })
end

function ExceptionHandler:asm_turn_heartbeat_off()
    return self:asm_one_shot_handler("CFL_TURN_HEARTBEAT_OFF", {})
end

function ExceptionHandler:asm_heartbeat_event()
    return self:asm_one_shot_handler("CFL_HEARTBEAT_EVENT", {})
end

function ExceptionHandler:asm_raise_exception(exception_id, exception_data)
    exception_data = exception_data or {}

    if type(exception_id) ~= "number" then
        error("Exception id must be a number")
    end
    if type(exception_data) ~= "table" then
        error("Exception data must be a table")
    end

    return self:define_column_link(
        "CFL_HALT",
        "CFL_RAISE_EXCEPTION",
        "CFL_NULL",
        "CFL_NULL",
        { exception_id = exception_id, exception_data = exception_data }
    )
end

function ExceptionHandler:asm_set_exception_step(step)
    if type(step) ~= "number" then
        error("Step must be a number")
    end
    if step < 0 then
        error("Step must be greater than 0")
    end
    return self:asm_one_shot_handler("CFL_SET_EXCEPTION_STEP", { step = step })
end

return ExceptionHandler