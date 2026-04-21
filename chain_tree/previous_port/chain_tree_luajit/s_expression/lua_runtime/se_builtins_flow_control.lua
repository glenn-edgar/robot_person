-- ============================================================================
-- se_builtins_flow_control.lua
-- Mirrors s_engine_builtins_flow_control.h
--
-- All main functions: fn(inst, node, event_id, event_data) -> result_code
-- ============================================================================

local se_runtime = require("se_runtime")

local SE_EVENT_INIT             = se_runtime.SE_EVENT_INIT
local SE_EVENT_TERMINATE        = se_runtime.SE_EVENT_TERMINATE
local SE_SKIP_CONTINUE          = 5   -- application-level
local SE_PIPELINE_CONTINUE      = se_runtime.SE_PIPELINE_CONTINUE
local SE_PIPELINE_HALT          = se_runtime.SE_PIPELINE_HALT
local SE_PIPELINE_DISABLE       = se_runtime.SE_PIPELINE_DISABLE
local SE_PIPELINE_TERMINATE     = se_runtime.SE_PIPELINE_TERMINATE
local SE_PIPELINE_RESET         = se_runtime.SE_PIPELINE_RESET
local SE_PIPELINE_SKIP_CONTINUE = se_runtime.SE_PIPELINE_SKIP_CONTINUE
local SE_FUNCTION_CONTINUE      = se_runtime.SE_FUNCTION_CONTINUE
local SE_FUNCTION_HALT          = se_runtime.SE_FUNCTION_HALT
local SE_FUNCTION_SKIP_CONTINUE = 11  -- function-level skip
local SE_FUNCTION_DISABLE       = se_runtime.SE_FUNCTION_DISABLE

local child_count            = se_runtime.child_count
local child_invoke           = se_runtime.child_invoke
local child_invoke_pred      = se_runtime.child_invoke_pred
local child_reset            = se_runtime.child_reset
local child_reset_recursive  = se_runtime.child_reset_recursive
local child_terminate        = se_runtime.child_terminate
local children_terminate_all = se_runtime.children_terminate_all
local children_reset_all     = se_runtime.children_reset_all
local invoke_pred            = se_runtime.invoke_pred
local invoke_any             = se_runtime.invoke_any
local get_ns                 = se_runtime.get_ns
local param_int              = se_runtime.param_int
local bit                    = require("bit")

-- Node state flag constants
local FLAG_ACTIVE      = 0x01
local FLAG_INITIALIZED = 0x02

-- Fork state constants (must match C: FORK_STATE_INIT=0, RUNNING=1, COMPLETE=2)
local FORK_STATE_INIT     = 0
local FORK_STATE_RUNNING  = 1
local FORK_STATE_COMPLETE = 2

-- While state constants
local SE_WHILE_EVAL_PRED = 0
local SE_WHILE_RUN_BODY  = 1

-- Sentinel for "no active child"
local NO_CHILD = 0xFFFF

local M = {}

-- ----------------------------------------------------------------------------
-- SE_SEQUENCE
-- Executes children one at a time in order; advances when current completes.
-- ns.state = current child index (0-based).
-- ----------------------------------------------------------------------------
M.se_sequence = function(inst, node, event_id, event_data)
    local ns       = get_ns(inst, node.node_index)
    local children = node.children or {}
    local n        = #children

    if event_id == SE_EVENT_INIT then
        ns.state = 0
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        local s = ns.state
        if s < n then
            local cns = get_ns(inst, children[s + 1].node_index)
            if bit.band(cns.flags, FLAG_INITIALIZED) ~= 0 then
                child_terminate(inst, node, s)
            end
        end
        ns.state = 0
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: while loop, can advance multiple children per tick
    while ns.state < n do
        local s     = ns.state
        local child = children[s + 1]
        local ct    = child.call_type

        -- Oneshot: invoke and advance immediately
        if ct == "o_call" or ct == "io_call" then
            child_invoke(inst, node, s, event_id, event_data)
            ns.state = s + 1
            goto seq_continue
        end

        -- Pred: invoke and advance immediately
        if ct == "p_call" or ct == "p_call_composite" then
            child_invoke(inst, node, s, event_id, event_data)
            ns.state = s + 1
            goto seq_continue
        end

        -- Main: invoke and dispatch result
        do
            local r = child_invoke(inst, node, s, event_id, event_data)

            -- Application codes (0-5): propagate immediately
            if r <= SE_SKIP_CONTINUE then
                return r
            end

            -- Function codes (6-11): propagate; FUNCTION_HALT -> PIPELINE_HALT
            if r >= SE_FUNCTION_CONTINUE and r <= SE_FUNCTION_SKIP_CONTINUE then
                if r == SE_FUNCTION_HALT then return SE_PIPELINE_HALT end
                return r
            end

            -- Pipeline codes (12-17)
            if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
                return SE_PIPELINE_CONTINUE   -- child still running, pause

            elseif r == SE_PIPELINE_DISABLE
                or r == SE_PIPELINE_TERMINATE
                or r == SE_PIPELINE_RESET then
                -- child complete: terminate and advance
                child_terminate(inst, node, s)
                ns.state = s + 1

            elseif r == SE_PIPELINE_SKIP_CONTINUE then
                return SE_PIPELINE_CONTINUE   -- pause this tick

            else
                return SE_PIPELINE_CONTINUE   -- unknown: pause
            end
        end

        ::seq_continue::
    end

    -- All children complete
    return SE_PIPELINE_DISABLE
end

-- ----------------------------------------------------------------------------
-- SE_SEQUENCE_ONCE
-- Fires ALL children exactly once in a single tick, then terminates them all
-- and returns PIPELINE_DISABLE.
-- ----------------------------------------------------------------------------
M.se_sequence_once = function(inst, node, event_id, event_data)
    local ns       = get_ns(inst, node.node_index)
    local children = node.children or {}
    local n        = #children

    if event_id == SE_EVENT_INIT then
        ns.state = 0
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        for i = 1, n do
            local cns = get_ns(inst, children[i].node_index)
            if bit.band(cns.flags, FLAG_INITIALIZED) ~= 0 then
                child_terminate(inst, node, i - 1)
            end
        end
        ns.state = 0
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: fire all children once, break on non-normal result
    for i = 1, n do
        local child = children[i]
        local idx   = i - 1
        local ct    = child.call_type

        -- Oneshot and pred: invoke and continue (no result check)
        if ct == "o_call" or ct == "io_call"
        or ct == "p_call" or ct == "p_call_composite" then
            child_invoke(inst, node, idx, event_id, event_data)
            goto continue_so
        end

        -- Main: invoke and break if result is not CONTINUE or DISABLE
        do
            local r = child_invoke(inst, node, idx, event_id, event_data)
            if r ~= SE_PIPELINE_CONTINUE and r ~= SE_PIPELINE_DISABLE then
                break
            end
        end

        ::continue_so::
    end

    -- Terminate all initialized children
    for i = 1, n do
        local cns = get_ns(inst, children[i].node_index)
        if bit.band(cns.flags, FLAG_INITIALIZED) ~= 0 then
            child_terminate(inst, node, i - 1)
        end
    end

    return SE_PIPELINE_DISABLE
end

-- ----------------------------------------------------------------------------
-- SE_FUNCTION_INTERFACE
-- Top-level parallel dispatcher; FUNCTION_DISABLE when all children complete.
-- ns.state: FORK_STATE_RUNNING or FORK_STATE_COMPLETE
-- ----------------------------------------------------------------------------
M.se_function_interface = function(inst, node, event_id, event_data)
    local ns       = get_ns(inst, node.node_index)
    local children = node.children or {}
    local n        = #children

    if event_id == SE_EVENT_INIT then
        ns.state = FORK_STATE_RUNNING
        for i = 1, n do
            local ct = children[i].call_type
            if ct == "m_call" or ct == "pt_m_call"
            or ct == "o_call" or ct == "io_call"
            or ct == "p_call" or ct == "p_call_composite" then
                child_reset(inst, node, i - 1)
            end
        end
        return SE_FUNCTION_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        ns.state = FORK_STATE_COMPLETE
        return SE_FUNCTION_CONTINUE
    end

    -- TICK
    if ns.state ~= FORK_STATE_RUNNING then
        return SE_FUNCTION_DISABLE
    end

    local active_count = 0
    local skip         = false

    for i = 1, n do
        if skip then break end
        local child = children[i]
        local idx   = i - 1
        if not child.node_index then goto continue_fi end
        local cns   = get_ns(inst, child.node_index)

        -- Skip inactive children
        if bit.band(cns.flags, FLAG_ACTIVE) == 0 then
            goto continue_fi
        end

        do
            local r = child_invoke(inst, node, idx, event_id, event_data)

            -- Non-pipeline codes: propagate immediately
            if r < SE_PIPELINE_CONTINUE then
                return r
            end

            if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
                active_count = active_count + 1

            elseif r == SE_PIPELINE_DISABLE or r == SE_PIPELINE_TERMINATE then
                child_terminate(inst, node, idx)

            elseif r == SE_PIPELINE_RESET then
                child_terminate(inst, node, idx)
                child_reset(inst, node, idx)
                active_count = active_count + 1

            elseif r == SE_PIPELINE_SKIP_CONTINUE then
                active_count = active_count + 1
                skip = true

            else
                active_count = active_count + 1
            end
        end

        ::continue_fi::
    end

    if active_count == 0 then
        ns.state = FORK_STATE_COMPLETE
        return SE_FUNCTION_DISABLE
    end
    return SE_FUNCTION_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_FORK
-- Parallel execution of all children; PIPELINE_DISABLE when all MAIN complete.
-- ns.state: FORK_STATE_RUNNING or FORK_STATE_COMPLETE
-- ----------------------------------------------------------------------------
M.se_fork = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)

    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        ns.state = FORK_STATE_COMPLETE
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        ns.state = FORK_STATE_RUNNING
        local children = node.children or {}
        for i = 1, #children do
            local ct = children[i].call_type
            if ct == "m_call" or ct == "pt_m_call"
            or ct == "o_call" or ct == "io_call"
            or ct == "p_call" or ct == "p_call_composite" then
                child_reset(inst, node, i - 1)
            end
        end
        return SE_PIPELINE_CONTINUE
    end

    -- TICK
    if ns.state ~= FORK_STATE_RUNNING then
        return SE_PIPELINE_DISABLE
    end

    local children = node.children or {}
    local n        = #children
    local skip     = false

    for i = 1, n do
        if skip then break end
        local child = children[i]
        local idx   = i - 1
        if not child.node_index then goto continue_fork end
        local ct    = child.call_type
        local cns   = get_ns(inst, child.node_index)

        -- Oneshot: fire once if not yet initialized
        if ct == "o_call" or ct == "io_call" then
            if bit.band(cns.flags, FLAG_INITIALIZED) == 0 then
                child_invoke(inst, node, idx, event_id, event_data)
            end
            goto continue_fork
        end

        -- Pred: evaluate once if not yet initialized
        if ct == "p_call" or ct == "p_call_composite" then
            if bit.band(cns.flags, FLAG_INITIALIZED) == 0 then
                child_invoke(inst, node, idx, event_id, event_data)
            end
            goto continue_fork
        end

        -- Main: only invoke if active
        if bit.band(cns.flags, FLAG_ACTIVE) == 0 then
            goto continue_fork
        end

        do
            local r = child_invoke(inst, node, idx, event_id, event_data)

            if r == SE_FUNCTION_HALT then r = SE_PIPELINE_HALT end

            if r < SE_PIPELINE_CONTINUE then
                return r
            end

            if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
                -- child still running

            elseif r == SE_PIPELINE_DISABLE or r == SE_PIPELINE_TERMINATE then
                child_terminate(inst, node, idx)

            elseif r == SE_PIPELINE_RESET then
                child_terminate(inst, node, idx)
                child_reset_recursive(inst, node, idx)

            elseif r == SE_PIPELINE_SKIP_CONTINUE then
                skip = true
            end
        end

        ::continue_fork::
    end

    -- check_completion: count active MAIN children
    local active_main = 0
    for i = 1, n do
        local child = children[i]
        local ct    = child.call_type
        if (ct == "m_call" or ct == "pt_m_call")
        and bit.band(get_ns(inst, child.node_index).flags, FLAG_ACTIVE) ~= 0 then
            active_main = active_main + 1
        end
    end

    if active_main == 0 then
        ns.state = FORK_STATE_COMPLETE
        return SE_PIPELINE_DISABLE
    end
    return SE_PIPELINE_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_FORK_JOIN
-- Parallel; returns FUNCTION_HALT while any MAIN child is active,
-- PIPELINE_DISABLE when all MAIN children complete.
-- ----------------------------------------------------------------------------
M.se_fork_join = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        return SE_PIPELINE_CONTINUE
    end

    local children = node.children or {}
    local n        = #children
    local skip     = false

    for i = 1, n do
        if skip then break end
        local child = children[i]
        local idx   = i - 1
        if not child.node_index then goto continue_fj end
        local ct    = child.call_type
        local cns   = get_ns(inst, child.node_index)

        -- Oneshot: fire once if not yet initialized
        if ct == "o_call" or ct == "io_call" then
            if bit.band(cns.flags, FLAG_INITIALIZED) == 0 then
                child_invoke(inst, node, idx, event_id, event_data)
            end
            goto continue_fj
        end

        -- Pred: evaluate once if not yet initialized
        if ct == "p_call" or ct == "p_call_composite" then
            if bit.band(cns.flags, FLAG_INITIALIZED) == 0 then
                child_invoke(inst, node, idx, event_id, event_data)
            end
            goto continue_fj
        end

        -- Main: only invoke if active
        if bit.band(cns.flags, FLAG_ACTIVE) == 0 then
            goto continue_fj
        end

        do
            local r = child_invoke(inst, node, idx, event_id, event_data)

            if r == SE_FUNCTION_HALT then r = SE_PIPELINE_HALT end

            if r < SE_PIPELINE_CONTINUE then
                return r
            end

            if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
                -- child still running

            elseif r == SE_PIPELINE_DISABLE or r == SE_PIPELINE_TERMINATE then
                child_terminate(inst, node, idx)

            elseif r == SE_PIPELINE_RESET then
                child_terminate(inst, node, idx)
                child_reset_recursive(inst, node, idx)

            elseif r == SE_PIPELINE_SKIP_CONTINUE then
                skip = true
            end
        end

        ::continue_fj::
    end

    -- check_completion: count active MAIN children
    local active_main = 0
    for i = 1, n do
        local child = children[i]
        local ct    = child.call_type
        if (ct == "m_call" or ct == "pt_m_call")
        and bit.band(get_ns(inst, child.node_index).flags, FLAG_ACTIVE) ~= 0 then
            active_main = active_main + 1
        end
    end

    if active_main == 0 then
        return SE_PIPELINE_DISABLE
    end
    return SE_FUNCTION_HALT
end

-- ----------------------------------------------------------------------------
-- SE_CHAIN_FLOW
-- Ticks all active children each tick with full result-code dispatch.
-- ----------------------------------------------------------------------------
M.se_chain_flow = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then return SE_PIPELINE_CONTINUE end
    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    end

    local children = node.children or {}
    local n = #children
    local active_count = 0
    local skip = false

    for i = 1, n do
        if skip then break end
        local child = children[i]
        local idx   = i - 1

        -- Skip inactive children
        if bit.band(get_ns(inst, child.node_index).flags, FLAG_ACTIVE) == 0 then
            goto continue_loop
        end

        local ct = child.call_type

        -- Oneshot: fire and terminate
        if ct == "o_call" or ct == "io_call" then
            child_invoke(inst, node, idx, event_id, event_data)
            child_terminate(inst, node, idx)
            goto continue_loop
        end

        -- Pred: evaluate and terminate
        if ct == "p_call" or ct == "p_call_composite" then
            child_invoke(inst, node, idx, event_id, event_data)
            child_terminate(inst, node, idx)
            goto continue_loop
        end

        -- Main: invoke and dispatch on result
        do
            local r = child_invoke(inst, node, idx, event_id, event_data)

            if r == SE_FUNCTION_HALT then
                return SE_PIPELINE_HALT
            end

            if r < SE_PIPELINE_CONTINUE then
                return r
            end

            if r == SE_PIPELINE_CONTINUE then
                active_count = active_count + 1

            elseif r == SE_PIPELINE_HALT then
                return SE_PIPELINE_CONTINUE

            elseif r == SE_PIPELINE_DISABLE then
                child_terminate(inst, node, idx)

            elseif r == SE_PIPELINE_TERMINATE then
                children_terminate_all(inst, node)
                return SE_PIPELINE_TERMINATE

            elseif r == SE_PIPELINE_RESET then
                children_terminate_all(inst, node)
                children_reset_all(inst, node)
                return SE_PIPELINE_CONTINUE

            elseif r == SE_PIPELINE_SKIP_CONTINUE then
                active_count = active_count + 1
                skip = true

            else
                active_count = active_count + 1
            end
        end

        ::continue_loop::
    end

    if active_count == 0 then
        return SE_PIPELINE_DISABLE
    end
    return SE_PIPELINE_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_WHILE
-- children[0] = predicate, children[1] = body
-- ns.state: 0=EVAL_PRED, 1=RUN_BODY
-- Returns FUNCTION_HALT while body is running, PIPELINE_HALT when body
-- completes (loops back to pred), PIPELINE_DISABLE when pred is false.
-- ----------------------------------------------------------------------------
M.se_while = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)

    if event_id == SE_EVENT_TERMINATE then
        local children = node.children or {}
        if children[2] then
            local cns = get_ns(inst, children[2].node_index)
            if bit.band(cns.flags, FLAG_INITIALIZED) ~= 0 then
                child_terminate(inst, node, 1)
            end
        end
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        ns.state = SE_WHILE_EVAL_PRED
        return SE_PIPELINE_CONTINUE
    end

    -- TICK
    if ns.state == SE_WHILE_EVAL_PRED then
        if not child_invoke_pred(inst, node, 0) then
            return SE_PIPELINE_DISABLE
        end
        -- Pred true: reset body and fall through to RUN_BODY this tick
        child_reset_recursive(inst, node, 1)
        ns.state = SE_WHILE_RUN_BODY
    end

    -- RUN_BODY
    local r = child_invoke(inst, node, 1, event_id, event_data)

    -- Non-pipeline codes: propagate immediately
    if r < SE_PIPELINE_CONTINUE then
        return r
    end

    if r == SE_PIPELINE_CONTINUE
    or r == SE_PIPELINE_HALT
    or r == SE_PIPELINE_SKIP_CONTINUE then
        -- Body still running
        return SE_FUNCTION_HALT

    elseif r == SE_PIPELINE_DISABLE
        or r == SE_PIPELINE_TERMINATE
        or r == SE_PIPELINE_RESET then
        -- Body complete: terminate, reset, loop back to pred check next tick
        child_terminate(inst, node, 1)
        child_reset_recursive(inst, node, 1)
        ns.state = SE_WHILE_EVAL_PRED
        return SE_PIPELINE_HALT

    else
        return SE_PIPELINE_DISABLE
    end
end

-- ----------------------------------------------------------------------------
-- SE_IF_THEN_ELSE
-- children[0] = predicate (re-evaluated every tick)
-- children[1] = then-branch
-- children[2] = else-branch (optional)
-- ----------------------------------------------------------------------------
M.se_if_then_else = function(inst, node, event_id, event_data)
    local children = node.children or {}
    local n        = #children
    assert(n >= 2, "se_if_then_else: need at least predicate and then branch")
    local has_else = (n >= 3)

    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        return SE_PIPELINE_CONTINUE
    end

    -- Evaluate predicate (child 0) every tick
    local condition = child_invoke_pred(inst, node, 0)

    local r
    if condition then
        r = child_invoke(inst, node, 1, event_id, event_data)
    elseif has_else then
        r = child_invoke(inst, node, 2, event_id, event_data)
    else
        return SE_PIPELINE_CONTINUE
    end

    -- Non-pipeline codes: propagate immediately
    if r < SE_PIPELINE_CONTINUE then
        return r
    end

    if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
        return r

    elseif r == SE_PIPELINE_RESET then
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        if has_else then
            child_terminate(inst, node, 2)
            child_reset(inst, node, 2)
        end
        return SE_PIPELINE_RESET

    elseif r == SE_PIPELINE_DISABLE or r == SE_PIPELINE_TERMINATE then
        child_terminate(inst, node, 1)
        child_reset(inst, node, 1)
        if has_else then
            child_terminate(inst, node, 2)
            child_reset(inst, node, 2)
        end
        return SE_PIPELINE_CONTINUE

    elseif r == SE_PIPELINE_SKIP_CONTINUE then
        return SE_PIPELINE_CONTINUE

    else
        return SE_PIPELINE_CONTINUE
    end
end

-- ----------------------------------------------------------------------------
-- SE_COND
-- Multi-branch conditional: pairs of (pred, action) at even/odd child indices.
-- children layout: [pred0, action0, pred1, action1, ...]
-- Predicates re-evaluated every tick; active branch tracked in ns.user_data.
-- ns.user_data: NO_CHILD = no active branch, else 0-based action child index.
-- ----------------------------------------------------------------------------
M.se_cond = function(inst, node, event_id, event_data)
    local ns       = get_ns(inst, node.node_index)
    local children = node.children or {}
    local n        = #children

    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        ns.user_data = NO_CHILD
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        ns.user_data = NO_CHILD
        return SE_PIPELINE_CONTINUE
    end

    -- Find first matching pred (even 0-based indices: 0,2,4,...)
    -- Actions at odd 0-based indices: 1,3,5,...
    local matched_action = NO_CHILD
    local i = 1  -- 1-based Lua index
    while i <= n do
        local child = children[i]
        local ct    = child.call_type
        if ct == "p_call" or ct == "p_call_composite" then
            local pred_result = child_invoke_pred(inst, node, i - 1)  -- 0-based
            if pred_result and matched_action == NO_CHILD then
                -- Action is next child; i is 1-based pred, action is 0-based (i)
                matched_action = i  -- 0-based index of action child
                break
            end
            i = i + 2  -- skip past action
        else
            i = i + 1
        end
    end

    if matched_action == NO_CHILD then
        return SE_PIPELINE_CONTINUE
    end

    local active = ns.user_data

    -- Branch switch: terminate old, reset new
    if matched_action ~= active then
        if active ~= NO_CHILD then
            child_terminate(inst, node, active)
            child_reset_recursive(inst, node, active)
        end
        child_terminate(inst, node, matched_action)
        child_reset_recursive(inst, node, matched_action)
        ns.user_data = matched_action
    end

    local r = child_invoke(inst, node, matched_action, event_id, event_data)

    -- Non-pipeline codes: propagate
    if r < SE_PIPELINE_CONTINUE then
        return r
    end

    if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
        return SE_PIPELINE_CONTINUE

    elseif r == SE_PIPELINE_RESET then
        child_terminate(inst, node, matched_action)
        child_reset_recursive(inst, node, matched_action)
        return SE_PIPELINE_CONTINUE

    elseif r == SE_PIPELINE_DISABLE
        or r == SE_PIPELINE_TERMINATE
        or r == SE_PIPELINE_SKIP_CONTINUE then
        return r

    else
        return SE_PIPELINE_CONTINUE
    end
end

-- ----------------------------------------------------------------------------
-- SE_TRIGGER_ON_CHANGE
-- Edge-triggered action dispatch. Detects rising/falling edges of a predicate
-- and fires corresponding action subtrees.
--
-- params[1] = uint (initial state: 0 or 1)
-- children[0] = predicate
-- children[1] = rising action
-- children[2] = falling action (optional)
--
-- ns.state: previous predicate value (0 or 1)
-- ----------------------------------------------------------------------------

-- Helper: invoke action and handle pipeline result codes for trigger
local function trigger_invoke_and_handle(inst, node, action_idx, event_id, event_data)
    local r = child_invoke(inst, node, action_idx, event_id, event_data)

    -- Non-pipeline codes: propagate
    if r < SE_PIPELINE_CONTINUE then
        return r
    end

    if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
        return SE_PIPELINE_CONTINUE

    elseif r == SE_PIPELINE_DISABLE
        or r == SE_PIPELINE_TERMINATE
        or r == SE_PIPELINE_RESET then
        child_terminate(inst, node, action_idx)
        child_reset(inst, node, action_idx)
        return SE_PIPELINE_CONTINUE

    elseif r == SE_PIPELINE_SKIP_CONTINUE then
        return SE_PIPELINE_CONTINUE

    else
        return SE_PIPELINE_CONTINUE
    end
end

M.se_trigger_on_change = function(inst, node, event_id, event_data)
    local ns       = get_ns(inst, node.node_index)
    local children = node.children or {}
    local n        = #children

    assert(n >= 2, "se_trigger_on_change: need at least predicate and rising action")

    local PRED_CHILD    = 0   -- 0-based for child_invoke
    local RISING_CHILD  = 1
    local FALLING_CHILD = 2
    local has_falling   = (n >= 3)

    -- TERMINATE
    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    end

    -- INIT: read initial state from params[1]
    if event_id == SE_EVENT_INIT then
        local initial = param_int(node, 1)
        ns.state = (initial ~= 0) and 1 or 0
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: evaluate predicate, detect edges
    local current = child_invoke_pred(inst, node, PRED_CHILD)
    local prev    = ns.state
    local current_val = current and 1 or 0

    local rising  = (prev == 0 and current_val == 1)
    local falling = (prev ~= 0 and current_val == 0)

    ns.state = current_val

    if rising then
        -- Terminate falling action if it was running
        if has_falling then
            child_terminate(inst, node, FALLING_CHILD)
            child_reset(inst, node, FALLING_CHILD)
        end

        -- Restart rising action
        child_terminate(inst, node, RISING_CHILD)
        child_reset(inst, node, RISING_CHILD)

        return trigger_invoke_and_handle(inst, node, RISING_CHILD, event_id, event_data)

    elseif falling and has_falling then
        -- Terminate rising action
        child_terminate(inst, node, RISING_CHILD)
        child_reset(inst, node, RISING_CHILD)

        -- Restart falling action
        child_terminate(inst, node, FALLING_CHILD)
        child_reset(inst, node, FALLING_CHILD)

        return trigger_invoke_and_handle(inst, node, FALLING_CHILD, event_id, event_data)
    end

    return SE_PIPELINE_CONTINUE
end

return M