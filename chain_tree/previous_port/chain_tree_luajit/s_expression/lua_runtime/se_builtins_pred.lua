-- ============================================================================
-- se_builtins_pred.lua
-- Mirrors s_engine_builtins_pred.h
--
-- All predicate functions: fn(inst, node) -> bool
-- No state mutation; no event_id parameter.
-- ============================================================================

local se_runtime = require("se_runtime")

local invoke_pred  = se_runtime.invoke_pred
local get_ns       = se_runtime.get_ns
local field_get    = se_runtime.field_get
local param_int    = se_runtime.param_int
local param_float  = se_runtime.param_float

local M = {}

-- ----------------------------------------------------------------------------
-- Boolean combinators
-- All children must be predicates.
-- ----------------------------------------------------------------------------

M.se_pred_and = function(inst, node)
    for _, child in ipairs(node.children or {}) do
        if not invoke_pred(inst, child) then return false end
    end
    return true
end

M.se_pred_or = function(inst, node)
    for _, child in ipairs(node.children or {}) do
        if invoke_pred(inst, child) then return true end
    end
    return false
end

M.se_pred_not = function(inst, node)
    local child = (node.children or {})[1]
    assert(child, "se_pred_not: no child")
    return not invoke_pred(inst, child)
end

M.se_pred_nor = function(inst, node)
    return not M.se_pred_or(inst, node)
end

M.se_pred_nand = function(inst, node)
    return not M.se_pred_and(inst, node)
end

M.se_pred_xor = function(inst, node)
    local count = 0
    for _, child in ipairs(node.children or {}) do
        if invoke_pred(inst, child) then count = count + 1 end
    end
    return (count % 2) == 1
end

-- ----------------------------------------------------------------------------
-- Constants
-- ----------------------------------------------------------------------------
M.se_true  = function() return true  end
M.se_false = function() return false end

-- ----------------------------------------------------------------------------
-- se_check_event
-- True if inst.current_event_id matches params[1] (uint or str_hash).
-- ----------------------------------------------------------------------------
M.se_check_event = function(inst, node)
    local p = (node.params or {})[1]
    if not p then return false end
    local check_id = (type(p.value) == "table") and p.value.hash or p.value
    return inst.current_event_id == check_id
end

-- ----------------------------------------------------------------------------
-- Field comparison predicates
-- params[1] = field_ref,  params[2] = comparison value (int)
-- ----------------------------------------------------------------------------

M.se_field_eq = function(inst, node)
    local v = field_get(inst, node, 1)
    return v == param_int(node, 2)
end

M.se_field_ne = function(inst, node)
    local v = field_get(inst, node, 1)
    return v ~= param_int(node, 2)
end

M.se_field_gt = function(inst, node)
    local v = field_get(inst, node, 1) or 0
    return v > param_int(node, 2)
end

M.se_field_ge = function(inst, node)
    local v = field_get(inst, node, 1) or 0
    return v >= param_int(node, 2)
end

M.se_field_lt = function(inst, node)
    local v = field_get(inst, node, 1) or 0
    return v < param_int(node, 2)
end

M.se_field_le = function(inst, node)
    local v = field_get(inst, node, 1) or 0
    return v <= param_int(node, 2)
end

-- ----------------------------------------------------------------------------
-- se_field_in_range
-- params[1] = field_ref,  params[2] = low,  params[3] = high  (inclusive)
-- ----------------------------------------------------------------------------
M.se_field_in_range = function(inst, node)
    local v   = field_get(inst, node, 1) or 0
    local low = param_int(node, 2)
    local hi  = param_int(node, 3)
    return v >= low and v <= hi
end

-- ----------------------------------------------------------------------------
-- se_field_increment_and_test
-- params[1] = counter field_ref
-- params[2] = increment field_ref  (amount to add each call)
-- params[3] = limit field_ref      (exclusive upper bound)
-- Adds increment to counter each call.
-- Returns true (continue) while counter < limit; false when counter >= limit.
-- ----------------------------------------------------------------------------
M.se_field_increment_and_test = function(inst, node)
    local counter   = field_get(inst, node, 1) or 0
    local increment = field_get(inst, node, 2) or 1
    local limit     = field_get(inst, node, 3) or 0
    counter = counter + increment
    se_runtime.field_set(inst, node, 1, counter)
    return counter <= limit
end

-- ----------------------------------------------------------------------------
-- se_state_increment_and_test
-- Increments node_state.user_data by increment each call.
-- Returns true (continue loop) while counter < limit.
-- Returns false (stop loop) when counter >= limit, then resets counter to 0.
-- params[1] = increment_value (uint)
-- params[2] = value_to_test / limit (uint)
-- ----------------------------------------------------------------------------
M.se_state_increment_and_test = function(inst, node)
    local ns        = get_ns(inst, node.node_index)
    local increment = param_int(node, 1)   -- step size
    local limit     = param_int(node, 2)   -- stop when counter >= limit
    ns.user_data = (ns.user_data or 0) + increment
    if ns.user_data > limit then
        ns.user_data = 0
        return false   -- limit exceeded: stop loop
    end
    return true        -- at or below limit: continue loop
end

return M