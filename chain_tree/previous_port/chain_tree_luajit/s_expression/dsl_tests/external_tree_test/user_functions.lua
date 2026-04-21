-- ============================================================================
-- user_functions.lua
-- Mirrors external_tree_user_functions.c
-- ============================================================================

local se_stack = require("se_stack")

local M = {}

-- Oneshot: fn(inst, node)
M.write_register = function(inst, node)
    print("write_register called")
    local stk = inst.stack
    -- Read locals from current stack frame
    -- C: s_expr_stack_get_local(inst->stack, 0) -> params[0].uint_val
    local frame = stk.frames[stk.frame_count]
    local base = frame and frame.base or 0
    local address = stk.data[base + 0] or 0
    local value   = stk.data[base + 1] or 0
    print(string.format("register address: 0x%08X", address))
    print(string.format("register value: 0x%08X", value))
end

return M