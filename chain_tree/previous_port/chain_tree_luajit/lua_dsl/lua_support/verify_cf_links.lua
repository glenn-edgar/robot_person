local ColumnFlow = require("lua_support.column_flow")
local bit = require("bit")

local VerifyCfLinks = setmetatable({}, { __index = ColumnFlow })
VerifyCfLinks.__index = VerifyCfLinks

function VerifyCfLinks.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, VerifyCfLinks)
end

function VerifyCfLinks:asm_verify(verify_fn, fn_data, reset_flag, error_fn, error_data)
    if reset_flag == nil then reset_flag = false end
    error_fn = error_fn or "CFL_NULL"

    local element_data = {}
    element_data.fn_data = fn_data
    element_data.reset_flag = reset_flag
    element_data.error_function = error_fn

    if error_fn ~= nil then
        self.ctb:add_one_shot_function(error_fn)
        element_data.error_data = error_data
    else
        element_data.error_function = nil
        element_data.error_data = nil
    end

    return self:define_column_link(
        "CFL_VERIFY",
        "CFL_VERIFY_INIT",
        verify_fn,
        "CFL_VERIFY_TERM",
        element_data
    )
end

function VerifyCfLinks:asm_verify_timeout(time_out, reset_flag, error_fn, error_data)
    if reset_flag == nil then reset_flag = false end
    error_fn = error_fn or "CFL_NULL"

    local fn_data = {
        time_out = time_out,
        current_time = 0,
    }

    return self:asm_verify("CFL_VERIFY_TIME_OUT", fn_data, reset_flag, error_fn, error_data)
end

function VerifyCfLinks:asm_verify_bitmask(required_bitmask_list, excluded_bitmask_list,
                                           reset_flag, error_fn, error_data)
    if reset_flag == nil then reset_flag = false end
    error_fn = error_fn or "CFL_NULL"

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

    local fn_data = {
        required_bitmask = required_mask,
        excluded_bitmask = excluded_mask,
    }

    self.ctb:add_one_shot_function(error_fn)
    return self:asm_verify("CFL_VERIFY_BITMASK", fn_data, reset_flag, error_fn, error_data)
end

function VerifyCfLinks:asm_verify_tests_active(test_ids, reset_flag, error_fn, error_data)
    if type(test_ids) ~= "table" then
        error("Test ids must be a table")
    end
    if reset_flag == nil then reset_flag = false end
    error_fn = error_fn or "CFL_NULL"

    local element_data = {
        test_ids = test_ids,
        reset_flag = reset_flag,
        error_function = error_fn,
        error_data = error_data,
    }

    self.ctb:add_one_shot_function(error_fn)
    return self:asm_verify("CFL_VERIFY_TESTS_ACTIVE", element_data, reset_flag, error_fn, error_data)
end

return VerifyCfLinks