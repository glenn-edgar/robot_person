local ColumnFlow = require("lua_support.column_flow")
local bit = require("bit")

local WaitCfLinks = setmetatable({}, { __index = ColumnFlow })
WaitCfLinks.__index = WaitCfLinks

function WaitCfLinks.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, WaitCfLinks)
end

function WaitCfLinks:asm_wait(wait_fn, wait_fn_data, reset_flag, timeout, time_out_event,
                               error_fn, error_data)
    if reset_flag == nil then reset_flag = false end
    timeout = timeout or 0
    time_out_event = time_out_event or "CF_TIMER_EVENT"

    if error_data == nil then
        error_data = {}
    end

    local element_data = {
        wait_fn_data = wait_fn_data,
        reset_flag = reset_flag,
        timeout = timeout,
        time_out_event = self.ctb:register_event(time_out_event),
        error_function = error_fn,
        error_data = error_data,
    }

    if error_fn ~= nil then
        self.ctb:add_one_shot_function(error_fn)
    end

    return self:define_column_link(
        "CFL_WAIT",
        "CFL_WAIT_INIT",
        wait_fn,
        "CFL_WAIT_TERM",
        element_data
    )
end

function WaitCfLinks:asm_wait_for_event(event_id, event_count, reset_flag, timeout,
                                         error_fn, time_out_event, error_data)
    event_count = event_count or 1
    if reset_flag == nil then reset_flag = false end
    timeout = timeout or 0
    error_fn = error_fn or "CFL_NULL"
    time_out_event = time_out_event or "CF_TIMER_EVENT"
    error_data = error_data or {}

    local element_data = {
        event_id = self.ctb:register_event(event_id),
        event_count = event_count,
    }

    return self:asm_wait("CFL_WAIT_FOR_EVENT", element_data, reset_flag, timeout,
        time_out_event, error_fn, error_data)
end

function WaitCfLinks:asm_wait_time(time_delay)
    local element_data = {
        time_delay = time_delay,  -- time delay in seconds
    }

    return self:define_column_link(
        "CFL_WAIT_TIME",
        "CFL_WAIT_TIME_INIT",
        "CFL_NULL",
        "CFL_NULL",
        element_data
    )
end

function WaitCfLinks:asm_wait_for_bitmask(required_bitmask_list, excluded_bitmask_list,
                                            reset_flag, timeout, error_fn, time_out_event, error_data)
    if reset_flag == nil then reset_flag = false end
    error_fn = error_fn or "CFL_NULL"
    time_out_event = time_out_event or "CF_TIMER_EVENT"

    if type(required_bitmask_list) ~= "table" then
        error("Event list must be a table")
    end

    local required_mask = 0
    for i = 1, #required_bitmask_list do
        local bit_pos = self.ctb:register_bitmask(required_bitmask_list[i])
        required_mask = bit.bor(required_mask, bit.lshift(1, bit_pos))
    end

    local excluded_mask = 0
    for i = 1, #excluded_bitmask_list do
        local bit_pos = self.ctb:register_bitmask(excluded_bitmask_list[i])
        excluded_mask = bit.bor(excluded_mask, bit.lshift(1, bit_pos))
    end

    local bitmask_data = {
        required_bitmask = required_mask,
        excluded_bitmask = excluded_mask,
    }

    return self:asm_wait("CFL_WAIT_FOR_BITMASK", bitmask_data, reset_flag, timeout,
        time_out_event, error_fn, error_data)
end

function WaitCfLinks:asm_wait_for_tests_complete(test_ids, reset_flag, timeout,
                                                   error_fn, time_out_event, error_data)
    if type(test_ids) ~= "table" then
        error("Test ids must be a table")
    end
    if reset_flag == nil then reset_flag = false end
    timeout = timeout or 0
    error_fn = error_fn or "CFL_NULL"
    time_out_event = time_out_event or "CF_TIMER_EVENT"

    local element_data = {
        test_ids = test_ids,
        reset_flag = reset_flag,
        error_function = error_fn,
        error_data = error_data,
    }

    return self:asm_wait("CFL_WAIT_FOR_TESTS_COMPLETE", element_data, reset_flag, timeout,
        time_out_event, error_fn, error_data)
end

return WaitCfLinks