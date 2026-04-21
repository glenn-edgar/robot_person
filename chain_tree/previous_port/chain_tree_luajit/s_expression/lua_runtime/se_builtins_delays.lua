-- ============================================================================
-- se_builtins_delays.lua
-- Mirrors s_engine_builtins_delays.h
--
-- Timing and event-wait main functions.
-- All main functions: fn(inst, node, event_id, event_data) -> result_code
--
-- Pointer-slot storage (pt_m_call nodes):
--   se_tick_delay   uses get/set_u64 (tick counter in pointer slot)
--   se_time_delay   uses get/set_f64 (target time in pointer slot)
--
-- Per-node extended state:
--   se_wait_event   uses ns.wait_target / ns.wait_remain (separate fields)
--   se_wait_timeout uses get/set_user_f64 (start time in node state)
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
local SE_FUNCTION_HALT     = se_runtime.SE_FUNCTION_HALT
local SE_DISABLE           = se_runtime.SE_DISABLE

local get_ns               = se_runtime.get_ns
local param_int            = se_runtime.param_int
local param_float          = se_runtime.param_float
local child_invoke_pred    = se_runtime.child_invoke_pred
local child_invoke_oneshot = se_runtime.child_invoke_oneshot
local child_reset          = se_runtime.child_reset
local get_u64              = se_runtime.get_u64
local set_u64              = se_runtime.set_u64
local get_f64              = se_runtime.get_f64
local set_f64              = se_runtime.set_f64
local get_user_f64         = se_runtime.get_user_f64
local set_user_f64         = se_runtime.set_user_f64

local M = {}

-- ----------------------------------------------------------------------------
-- SE_TICK_DELAY  (pt_m_call -- uses pointer slot u64)
-- Delays execution by N ticks.
-- params[1] = uint  tick_count
--
-- INIT:  store tick_count+1 in pointer u64 (+1 so the init tick counts)
-- TICK:  decrement; SE_FUNCTION_HALT while > 0, SE_PIPELINE_DISABLE when done
-- TERM:  SE_PIPELINE_CONTINUE (no cleanup needed)
-- ----------------------------------------------------------------------------
M.se_tick_delay = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local ticks = (#(node.params or {}) > 0) and param_int(node, 1) or 0
        set_u64(inst, node, ticks + 1)   -- C: ticks++; s_expr_set_u64(inst, ticks)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    local remaining = get_u64(inst, node)
    if remaining > 0 then
        set_u64(inst, node, remaining - 1)
        return SE_FUNCTION_HALT
    end

    return SE_PIPELINE_DISABLE
end

-- ----------------------------------------------------------------------------
-- SE_TIME_DELAY  (pt_m_call -- uses pointer slot f64)
-- Delays execution by N wall-clock seconds.
-- params[1] = float  seconds
--
-- INIT:  store target_time = now + seconds in pointer f64
--        If seconds <= 0, return PIPELINE_CONTINUE (instant)
-- Non-TICK events: SE_FUNCTION_HALT (only SE_EVENT_TICK advances state)
-- TICK:  SE_FUNCTION_HALT until now >= target_time, then SE_PIPELINE_DISABLE
-- Time source: inst.mod.get_time() -- default os.clock, injectable
-- ----------------------------------------------------------------------------
M.se_time_delay = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local seconds = (#(node.params or {}) > 0) and param_float(node, 1) or 0.0
        if seconds <= 0.0 then
            return SE_PIPELINE_CONTINUE
        end
        set_f64(inst, node, inst.mod.get_time() + seconds)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    -- C: if (event_id != SE_EVENT_TICK) return SE_FUNCTION_HALT
    if event_id ~= SE_EVENT_TICK then
        return SE_FUNCTION_HALT
    end

    if inst.mod.get_time() >= get_f64(inst, node) then
        return SE_PIPELINE_DISABLE
    end

    return SE_FUNCTION_HALT
end

-- ----------------------------------------------------------------------------
-- SE_WAIT_EVENT  (m_call)
-- Wait for a specific event_id to occur N times before proceeding.
-- params[1] = uint  target_event_id
-- params[2] = uint  count
--
-- INIT:  store target and count in per-node state
-- TICK:  SE_PIPELINE_HALT while count > 0
--        decrement when matching event received
--        SE_PIPELINE_DISABLE when count reaches 0
-- TERM:  SE_PIPELINE_CONTINUE
-- ----------------------------------------------------------------------------
M.se_wait_event = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        assert(#(node.params or {}) >= 2,
            "se_wait_event: requires 2 parameters (target_event, count)")
        local ns = get_ns(inst, node.node_index)
        ns.wait_target = param_int(node, 1)  -- uint32
        ns.wait_remain = param_int(node, 2)  -- uint32
        return SE_PIPELINE_CONTINUE
    end

    -- TICK
    local ns = get_ns(inst, node.node_index)
    local remaining = ns.wait_remain or 0

    if remaining == 0 then
        return SE_PIPELINE_DISABLE
    end

    if event_id == ns.wait_target then
        remaining = remaining - 1
        ns.wait_remain = remaining
        if remaining == 0 then
            return SE_PIPELINE_DISABLE
        end
    end

    return SE_PIPELINE_HALT
end

-- ----------------------------------------------------------------------------
-- SE_NOP  (m_call)
-- Returns SE_DISABLE unconditionally. Useful as a dead branch placeholder.
-- ----------------------------------------------------------------------------
M.se_nop = function(inst, node, event_id, event_data)
    return SE_DISABLE
end

-- ----------------------------------------------------------------------------
-- SE_WAIT  (m_call)
-- Waits until a predicate child becomes true.
-- children[0] (0-based) = pred function
--
-- INIT:  validate presence; SE_PIPELINE_CONTINUE
-- TICK:  SE_PIPELINE_DISABLE when pred true, SE_PIPELINE_HALT otherwise
-- TERM:  SE_PIPELINE_CONTINUE
-- ----------------------------------------------------------------------------
M.se_wait = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        assert(#(node.children or {}) >= 1,
            "se_wait: requires 1 predicate child")
        return SE_PIPELINE_CONTINUE
    end

    if child_invoke_pred(inst, node, 0) then
        return SE_PIPELINE_DISABLE
    end

    return SE_PIPELINE_HALT
end

-- ----------------------------------------------------------------------------
-- SE_WAIT_TIMEOUT  (pt_m_call -- uses user_f64 for start time)
-- Waits for a predicate with a timeout watchdog.
-- Lua tree layout:
--   children[0]  (0-based) = pred  (p_call)
--   children[1]  (0-based) = error oneshot  (o_call)
--   params[1]    = float  timeout (seconds)
--   params[2]    = int    reset_flag  (non-zero = PIPELINE_RESET on timeout)
--
-- INIT:     store start_time in user_f64 per-node state
-- Non-TICK: SE_PIPELINE_HALT (events other than TICK are ignored)
-- TICK:
--   pred true          -> SE_PIPELINE_DISABLE
--   elapsed > timeout  -> reset+invoke error child; RESET or TERMINATE
--   else               -> SE_PIPELINE_HALT
-- TERM:     SE_PIPELINE_CONTINUE
-- ----------------------------------------------------------------------------
M.se_wait_timeout = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        assert(#(node.children or {}) >= 2 and #(node.params or {}) >= 2,
            "se_wait_timeout: requires [pred child] [error child] [float timeout] [int reset_flag]")
        set_user_f64(inst, node, inst.mod.get_time())
        return SE_PIPELINE_CONTINUE
    end

    if event_id ~= SE_EVENT_TICK then
        return SE_PIPELINE_HALT
    end

    -- Evaluate predicate
    if child_invoke_pred(inst, node, 0) then
        return SE_PIPELINE_DISABLE
    end

    -- Check timeout
    local timeout    = param_float(node, 1)
    local reset_flag = param_int(node, 2) ~= 0
    local elapsed    = inst.mod.get_time() - get_user_f64(inst, node)

    if elapsed > timeout then
        child_reset(inst, node, 1)
        child_invoke_oneshot(inst, node, 1)
        return reset_flag and SE_PIPELINE_RESET or SE_PIPELINE_TERMINATE
    end

    return SE_PIPELINE_HALT
end

return M