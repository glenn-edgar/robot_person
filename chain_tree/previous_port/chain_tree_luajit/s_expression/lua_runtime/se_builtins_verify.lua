-- ============================================================================
-- se_builtins_verify.lua
-- Mirrors s_engine_builtins_verify.h
--
-- Runtime watchdog / assertion functions.
-- All main functions: fn(inst, node, event_id, event_data) -> result_code
--
-- Lua tree param layout (non-callables in params[], callables in children[]):
--
--   se_verify_and_check_elapsed_time:
--     params[1]    = float  timeout
--     params[2]    = int    reset_flag
--     children[0]  = error oneshot  (0-based)
--
--   se_verify_and_check_elapsed_events:
--     params[1]    = uint   target_event_id
--     params[2]    = uint   max_count
--     params[3]    = int    reset_flag
--     children[0]  = error oneshot  (0-based)
--
--   se_verify:
--     params[1]    = int    reset_flag
--     children[0]  = pred  (0-based)
--     children[1]  = error oneshot  (0-based)
-- ============================================================================

local se_runtime = require("se_runtime")

local SE_EVENT_INIT        = se_runtime.SE_EVENT_INIT
local SE_EVENT_TERMINATE   = se_runtime.SE_EVENT_TERMINATE
local SE_EVENT_TICK        = se_runtime.SE_EVENT_TICK
local SE_PIPELINE_CONTINUE = se_runtime.SE_PIPELINE_CONTINUE
local SE_PIPELINE_DISABLE  = se_runtime.SE_PIPELINE_DISABLE
local SE_PIPELINE_HALT     = se_runtime.SE_PIPELINE_HALT
local SE_PIPELINE_RESET    = se_runtime.SE_PIPELINE_RESET
local SE_PIPELINE_TERMINATE= se_runtime.SE_PIPELINE_TERMINATE

local get_ns               = se_runtime.get_ns
local param_int            = se_runtime.param_int
local param_float          = se_runtime.param_float
local child_invoke_pred    = se_runtime.child_invoke_pred
local child_invoke_oneshot = se_runtime.child_invoke_oneshot
local child_reset          = se_runtime.child_reset
local get_user_f64         = se_runtime.get_user_f64
local set_user_f64         = se_runtime.set_user_f64
local get_user_u64         = se_runtime.get_user_u64
local set_user_u64         = se_runtime.set_user_u64

local M = {}

-- ----------------------------------------------------------------------------
-- SE_VERIFY_AND_CHECK_ELAPSED_TIME  (pt_m_call -- uses user_f64)
-- Monitors elapsed wall-clock time; invokes error handler on timeout.
-- params[1]   = float  timeout (seconds)
-- params[2]   = int    reset_flag
-- children[0] = error oneshot (0-based)
--
-- INIT:     store start_time in user_f64
-- Non-TICK: SE_PIPELINE_CONTINUE (passthrough; only TICK checks elapsed time)
-- TICK:     SE_PIPELINE_CONTINUE while within timeout
--           on timeout: reset+invoke error, return RESET or TERMINATE
-- TERM:     SE_PIPELINE_CONTINUE
-- ----------------------------------------------------------------------------
M.se_verify_and_check_elapsed_time = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        assert(#(node.params or {}) >= 2,
            "se_verify_and_check_elapsed_time: requires [float timeout] [int reset_flag]")
        set_user_f64(inst, node, inst.mod.get_time())
        return SE_PIPELINE_CONTINUE
    end

    -- C: if (event_id != SE_EVENT_TICK) return SE_PIPELINE_CONTINUE
    if event_id ~= SE_EVENT_TICK then
        return SE_PIPELINE_CONTINUE
    end

    local timeout    = param_float(node, 1)
    local reset_flag = param_int(node, 2) ~= 0
    local elapsed    = inst.mod.get_time() - get_user_f64(inst, node)

    if elapsed > timeout then
        -- Reset and invoke error oneshot at logical child 2 → children[0] in Lua
        child_reset(inst, node, 0)
        child_invoke_oneshot(inst, node, 0)
        return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
    end

    return SE_PIPELINE_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_VERIFY_AND_CHECK_ELAPSED_EVENTS  (pt_m_call -- uses user_u64)
-- Monitors a specific event; invokes error handler when count exceeded.
-- params[1]   = uint  target_event_id
-- params[2]   = uint  max_count
-- params[3]   = int   reset_flag
-- children[0] = error oneshot (0-based)
--
-- INIT:  store 0 counter in user_u64
-- TICK:  SE_PIPELINE_CONTINUE when event doesn't match
--        increment counter when matching event received
--        on exceed: reset+invoke error, return RESET or TERMINATE
-- TERM:  SE_PIPELINE_CONTINUE
-- ----------------------------------------------------------------------------
M.se_verify_and_check_elapsed_events = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        assert(#(node.params or {}) >= 3,
            "se_verify_and_check_elapsed_events: requires [uint event_id] [uint max_count] [int reset_flag]")
        set_user_u64(inst, node, 0)
        return SE_PIPELINE_CONTINUE
    end

    local target_event = param_int(node, 1)
    local max_count    = param_int(node, 2)
    local reset_flag   = param_int(node, 3) ~= 0

    -- Only count events matching target_event_id
    if event_id ~= target_event then
        return SE_PIPELINE_CONTINUE
    end

    local current = get_user_u64(inst, node) + 1
    set_user_u64(inst, node, current)

    if current > max_count then
        child_reset(inst, node, 0)
        child_invoke_oneshot(inst, node, 0)
        return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
    end

    return SE_PIPELINE_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_VERIFY  (m_call)
-- Evaluates a predicate every TICK; invokes error handler on failure.
-- params[1]   = int   reset_flag
-- children[0] = pred  (0-based)
-- children[1] = error oneshot  (0-based)
--
-- INIT:     SE_PIPELINE_CONTINUE
-- Non-TICK: SE_PIPELINE_CONTINUE (passthrough)
-- TICK:     pred true  -> SE_PIPELINE_CONTINUE
--           pred false -> reset+invoke error, return RESET or TERMINATE
-- TERM:     SE_PIPELINE_CONTINUE
-- ----------------------------------------------------------------------------
M.se_verify = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        assert(#(node.children or {}) >= 2 and #(node.params or {}) >= 1,
            "se_verify: requires [int reset_flag] [pred child] [error child]")
        return SE_PIPELINE_CONTINUE
    end

    -- C: if (event_id != SE_EVENT_TICK) return SE_PIPELINE_CONTINUE
    if event_id ~= SE_EVENT_TICK then
        return SE_PIPELINE_CONTINUE
    end

    local reset_flag = param_int(node, 1) ~= 0

    if child_invoke_pred(inst, node, 0) then
        return SE_PIPELINE_CONTINUE
    end

    -- Predicate failed
    child_reset(inst, node, 1)
    child_invoke_oneshot(inst, node, 1)
    return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
end

return M