-- ============================================================================
-- se_builtins_return_codes.lua
-- Mirrors s_engine_builtins_return_codes.h
--
-- Trivial main functions that return a fixed result code on every TICK.
-- All functions: fn(inst, node, event_id, event_data) -> result_code
-- INIT and TERMINATE events are silently ignored.
-- ============================================================================

local se_runtime = require("se_runtime")

local SE_EVENT_INIT      = se_runtime.SE_EVENT_INIT
local SE_EVENT_TERMINATE = se_runtime.SE_EVENT_TERMINATE

local function make_return(code)
    return function(inst, node, event_id, event_data)
        if event_id == SE_EVENT_INIT      then return end
        if event_id == SE_EVENT_TERMINATE then return end
        return code
    end
end

local M = {}

-- Application-level result codes
M.se_return_continue          = make_return(se_runtime.SE_CONTINUE)
M.se_return_halt              = make_return(se_runtime.SE_HALT)
M.se_return_terminate         = make_return(se_runtime.SE_TERMINATE)
M.se_return_reset             = make_return(se_runtime.SE_RESET)
M.se_return_disable           = make_return(se_runtime.SE_DISABLE)
M.se_return_skip_continue     = make_return(se_runtime.SE_SKIP_CONTINUE)

-- Function-level result codes
M.se_return_function_continue      = make_return(se_runtime.SE_FUNCTION_CONTINUE)
M.se_return_function_halt          = make_return(se_runtime.SE_FUNCTION_HALT)
M.se_return_function_terminate     = make_return(se_runtime.SE_FUNCTION_TERMINATE)
M.se_return_function_reset         = make_return(se_runtime.SE_FUNCTION_RESET)
M.se_return_function_disable       = make_return(se_runtime.SE_FUNCTION_DISABLE)
M.se_return_function_skip_continue = make_return(se_runtime.SE_FUNCTION_SKIP_CONTINUE)

-- Pipeline-level result codes
M.se_return_pipeline_continue      = make_return(se_runtime.SE_PIPELINE_CONTINUE)
M.se_return_pipeline_halt          = make_return(se_runtime.SE_PIPELINE_HALT)
M.se_return_pipeline_terminate     = make_return(se_runtime.SE_PIPELINE_TERMINATE)
M.se_return_pipeline_reset         = make_return(se_runtime.SE_PIPELINE_RESET)
M.se_return_pipeline_disable       = make_return(se_runtime.SE_PIPELINE_DISABLE)
M.se_return_pipeline_skip_continue = make_return(se_runtime.SE_PIPELINE_SKIP_CONTINUE)

return M