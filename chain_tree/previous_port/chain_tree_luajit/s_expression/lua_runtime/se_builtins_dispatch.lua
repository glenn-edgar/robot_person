-- ============================================================================
-- se_builtins_dispatch.lua
-- Mirrors s_engine_builtins_dispatch.c
--
-- Event-driven and field-driven dispatch builtins.
-- All main functions: fn(inst, node, event_id, event_data) -> result_code
--
-- In the Lua tree model:
--   event_dispatch:  params[i] = case value, children[i] = action subtree
--   state_machine:   params[1] = field_ref, params[i+1] = case value,
--                    children[i] = action subtree
--   field_dispatch:  same layout as state_machine
--
-- Default case uses value -1.
-- No-match without default is an error (Erlang-style crash).
-- ============================================================================

local se_runtime = require("se_runtime")

local SE_EVENT_INIT             = se_runtime.SE_EVENT_INIT
local SE_EVENT_TERMINATE        = se_runtime.SE_EVENT_TERMINATE
local SE_PIPELINE_CONTINUE      = se_runtime.SE_PIPELINE_CONTINUE
local SE_PIPELINE_HALT          = se_runtime.SE_PIPELINE_HALT
local SE_PIPELINE_DISABLE       = se_runtime.SE_PIPELINE_DISABLE
local SE_PIPELINE_TERMINATE     = se_runtime.SE_PIPELINE_TERMINATE
local SE_PIPELINE_RESET         = se_runtime.SE_PIPELINE_RESET
local SE_PIPELINE_SKIP_CONTINUE = se_runtime.SE_PIPELINE_SKIP_CONTINUE
local SE_FUNCTION_HALT          = se_runtime.SE_FUNCTION_HALT

local get_ns                = se_runtime.get_ns
local param_int             = se_runtime.param_int
local param_field_name      = se_runtime.param_field_name
local field_get             = se_runtime.field_get
local child_count           = se_runtime.child_count
local child_invoke          = se_runtime.child_invoke
local child_terminate       = se_runtime.child_terminate
local child_reset_recursive = se_runtime.child_reset_recursive

local SENTINEL = 0xFFFF

local M = {}

-- ============================================================================
-- Helper: invoke child and handle PIPELINE result codes
-- Mirrors C invoke_and_handle_result().
--
-- Non-PIPELINE codes (0-11): propagate to caller unchanged.
-- PIPELINE_CONTINUE/HALT: return as-is (action still running).
-- PIPELINE_DISABLE/TERMINATE/RESET: terminate+reset child, return CONTINUE.
-- PIPELINE_SKIP_CONTINUE: return CONTINUE.
-- ============================================================================
local function invoke_and_handle_result(inst, node, child_idx, event_id, event_data)
    local r = child_invoke(inst, node, child_idx, event_id, event_data)

    -- Non-PIPELINE codes propagate directly
    if r < SE_PIPELINE_CONTINUE then
        return r
    end

    if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
        return r
    end

    if r == SE_PIPELINE_DISABLE
    or r == SE_PIPELINE_TERMINATE
    or r == SE_PIPELINE_RESET then
        child_terminate(inst, node, child_idx)
        child_reset_recursive(inst, node, child_idx)
        return SE_PIPELINE_CONTINUE
    end

    if r == SE_PIPELINE_SKIP_CONTINUE then
        return SE_PIPELINE_CONTINUE
    end

    return SE_PIPELINE_CONTINUE
end

-- ============================================================================
-- SE_EVENT_DISPATCH  (m_call)
-- Dispatch based on event_id. Stateless.
--
-- Lua tree layout:
--   params[1] = int (case event_id 0)
--   params[2] = int (case event_id 1)
--   ...
--   children[1] = action for case 0
--   children[2] = action for case 1
--   ...
--
-- Default case value = -1.
-- No match + no default = error (Erlang-style).
-- ============================================================================
M.se_event_dispatch = function(inst, node, event_id, event_data)
    -- INIT/TERMINATE: nothing to do
    if event_id == SE_EVENT_INIT or event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    local params   = node.params or {}
    local children = node.children or {}
    local default_child_idx = nil

    -- Search for matching case
    for i = 1, #params do
        local case_val = params[i].value
        if type(case_val) == "number" then
            local child_idx = i - 1  -- 0-based for child_invoke

            if case_val == event_id then
                return invoke_and_handle_result(inst, node, child_idx, event_id, event_data)
            end

            if case_val == -1 then
                default_child_idx = child_idx
            end
        end
    end

    -- No exact match — try default
    if default_child_idx then
        return invoke_and_handle_result(inst, node, default_child_idx, event_id, event_data)
    end

    error("se_event_dispatch: no matching event handler for event_id=" .. tostring(event_id))
end

-- ============================================================================
-- SE_STATE_MACHINE  (m_call)
-- Dispatch based on integer field value. Stateful — tracks active branch,
-- handles branch transitions with terminate/reset.
--
-- Lua tree layout:
--   params[1] = field_ref (field to read)
--   params[2] = int (case value 0)
--   params[3] = int (case value 1)
--   ...
--   children[1] = action for case 0
--   children[2] = action for case 1
--   ...
--
-- Default case value = -1.
-- No match + no default = error (Erlang-style).
--
-- node_state.user_data tracks the previous child index (0-based).
-- SENTINEL (0xFFFF) = no previous branch.
-- ============================================================================
M.se_state_machine = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)
    local prev_child_idx = ns.user_data

    -- -----------------------------------------------------------------
    -- TERMINATE: clean up active branch
    -- -----------------------------------------------------------------
    if event_id == SE_EVENT_TERMINATE then
        if prev_child_idx ~= SENTINEL and prev_child_idx ~= nil then
            child_terminate(inst, node, prev_child_idx)
        end
        ns.user_data = SENTINEL
        return SE_PIPELINE_CONTINUE
    end

    -- -----------------------------------------------------------------
    -- INIT: set sentinel
    -- -----------------------------------------------------------------
    if event_id == SE_EVENT_INIT then
        ns.user_data = SENTINEL
        return SE_PIPELINE_CONTINUE
    end

    -- -----------------------------------------------------------------
    -- TICK: dispatch based on field value
    -- -----------------------------------------------------------------
    local params   = node.params or {}
    local children = node.children or {}

    -- Read field value
    local val = field_get(inst, node, 1)
    if val == nil then val = 0 end
    val = math.floor(tonumber(val) or 0)

    -- Search case values (params[2..N] map to children[1..N-1])
    local action_child_idx = nil
    local default_child_idx = nil

    for i = 2, #params do
        local case_val = params[i].value
        if type(case_val) == "number" then
            local child_idx = i - 2  -- 0-based: params[2]→child 0, params[3]→child 1

            if math.floor(case_val) == val then
                action_child_idx = child_idx
                break
            end

            if case_val == -1 then
                default_child_idx = child_idx
            end
        end
    end

    -- Use default if no exact match
    if action_child_idx == nil then
        action_child_idx = default_child_idx
    end

    -- No match and no default — Erlang-style crash
    if action_child_idx == nil then
        error("se_state_machine: no matching case for value=" .. tostring(val))
    end

    -- Handle branch change: terminate old, reset new
    if action_child_idx ~= prev_child_idx then
        if prev_child_idx ~= nil and prev_child_idx ~= SENTINEL then
            child_terminate(inst, node, prev_child_idx)
            child_reset_recursive(inst, node, prev_child_idx)
        end
        child_reset_recursive(inst, node, action_child_idx)
        ns.user_data = action_child_idx
    end

    -- Invoke current action
    local r = child_invoke(inst, node, action_child_idx, event_id, event_data)

    -- SE_FUNCTION_HALT → SE_PIPELINE_HALT
    if r == SE_FUNCTION_HALT then
        return SE_PIPELINE_HALT
    end

    -- Non-PIPELINE codes propagate
    if r < SE_PIPELINE_CONTINUE then
        return r
    end

    if r == SE_PIPELINE_CONTINUE or r == SE_PIPELINE_HALT then
        return r
    end

    if r == SE_PIPELINE_DISABLE
    or r == SE_PIPELINE_TERMINATE
    or r == SE_PIPELINE_RESET then
        child_terminate(inst, node, action_child_idx)
        child_reset_recursive(inst, node, action_child_idx)
        return SE_PIPELINE_CONTINUE
    end

    if r == SE_PIPELINE_SKIP_CONTINUE then
        return SE_PIPELINE_CONTINUE
    end

    return SE_PIPELINE_CONTINUE
end

-- ============================================================================
-- SE_FIELD_DISPATCH  (m_call)
-- Dispatch based on integer field value. Stateful — tracks active branch.
-- Same layout as state_machine but different result handling for PIPELINE_RESET.
--
-- Lua tree layout:
--   params[1] = field_ref (field to read)
--   params[2] = int (case value 0)
--   params[3] = int (case value 1)
--   ...
--   children[1] = action for case 0
--   children[2] = action for case 1
--   ...
--
-- Default case value = -1.
-- No match + no default = error (Erlang-style).
-- ============================================================================
M.se_field_dispatch = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)
    local prev_child_idx = ns.user_data

    -- -----------------------------------------------------------------
    -- TERMINATE: clean up active branch
    -- -----------------------------------------------------------------
    if event_id == SE_EVENT_TERMINATE then
        if prev_child_idx ~= SENTINEL and prev_child_idx ~= nil then
            child_terminate(inst, node, prev_child_idx)
        end
        ns.user_data = SENTINEL
        return SE_PIPELINE_CONTINUE
    end

    -- -----------------------------------------------------------------
    -- INIT: set sentinel
    -- -----------------------------------------------------------------
    if event_id == SE_EVENT_INIT then
        ns.user_data = SENTINEL
        return SE_PIPELINE_CONTINUE
    end

    -- -----------------------------------------------------------------
    -- TICK: dispatch based on field value
    -- -----------------------------------------------------------------
    local params   = node.params or {}
    local children = node.children or {}

    -- Read field value
    local val = field_get(inst, node, 1)
    if val == nil then val = 0 end
    val = math.floor(tonumber(val) or 0)

    -- Search case values (params[2..N] map to children[1..N-1])
    local action_child_idx = nil
    local default_child_idx = nil

    for i = 2, #params do
        local case_val = params[i].value
        if type(case_val) == "number" then
            local child_idx = i - 2  -- 0-based: params[2]→child 0, params[3]→child 1

            if math.floor(case_val) == val then
                action_child_idx = child_idx
                break
            end

            if case_val == -1 then
                default_child_idx = child_idx
            end
        end
    end

    -- Use default if no exact match
    if action_child_idx == nil then
        action_child_idx = default_child_idx
    end

    -- No match and no default — Erlang-style crash
    if action_child_idx == nil then
        error("se_field_dispatch: no matching case for value=" .. tostring(val))
    end

    -- Handle branch change: terminate old, reset new
    if action_child_idx ~= prev_child_idx then
        if prev_child_idx ~= nil and prev_child_idx ~= SENTINEL then
            child_terminate(inst, node, prev_child_idx)
            child_reset_recursive(inst, node, prev_child_idx)
        end
        child_reset_recursive(inst, node, action_child_idx)
        ns.user_data = action_child_idx
    end

    -- Invoke current action
    local result = child_invoke(inst, node, action_child_idx, event_id, event_data)

    -- DISABLE/TERMINATE/RESET: terminate+reset action, clear state sentinel
    if result == SE_PIPELINE_RESET
    or result == SE_PIPELINE_DISABLE
    or result == SE_PIPELINE_TERMINATE then
        child_terminate(inst, node, action_child_idx)
        child_reset_recursive(inst, node, action_child_idx)
        ns.user_data = 0xFFFF  -- reset state sentinel (no previous branch)
        return SE_PIPELINE_CONTINUE
    end

    return result
end

return M