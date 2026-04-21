-- ============================================================================
-- user_fns_function_dictionary.lua
-- LuaJIT translation of function_dictionary_user_functions.c
--
-- C uses s_expr_stack_get_local(inst->stack, N) to read stack locals.
-- In Lua, stack locals are accessed via se_stack.get_local(inst.stack, N)
-- which returns the param table at local slot N (0-based).
-- The C prints uint_val; in Lua params store {type=..., value=...} so we
-- read p.value and format as hex.
-- ============================================================================

local se_stack = require("se_stack")

local M = {}

-- ============================================================================
-- write_register
-- Stack local [0] = address param (uint)
-- Stack local [1] = value  param (uint)
-- ============================================================================
M.write_register = function(inst, node)
    print("write_register called")

    local address_param = se_stack.get_local(inst.stack, 0)
    local addr_val = address_param and address_param.value or 0
    print(string.format("register address: 0x%08X", addr_val))

    local value_param = se_stack.get_local(inst.stack, 1)
    local reg_val = value_param and value_param.value or 0
    print(string.format("register value: 0x%08X", reg_val))
end

return M

