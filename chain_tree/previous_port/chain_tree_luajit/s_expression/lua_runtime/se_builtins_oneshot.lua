-- ============================================================================
-- se_builtins_oneshot.lua
-- Mirrors s_engine_builtins_oneshot.h
--
-- All oneshot functions: fn(inst, node)
-- No return value; no event_id parameter.
-- These fire exactly once per node activation (o_call) or
-- exactly once ever (io_call / SURVIVES_RESET) per the engine rules.
-- ============================================================================

local se_runtime = require("se_runtime")

local field_get       = se_runtime.field_get
local field_set       = se_runtime.field_set
local param_int       = se_runtime.param_int
local param_float     = se_runtime.param_float
local param_str       = se_runtime.param_str
local param_field_name= se_runtime.param_field_name
local SE_EVENT_TICK   = se_runtime.SE_EVENT_TICK

local M = {}

-- ----------------------------------------------------------------------------
-- Logging
-- ----------------------------------------------------------------------------

-- se_log: print a literal string param
-- params[1] = str_idx or str_ptr
M.se_log = function(inst, node)
    local msg = param_str(node, 1) or "(nil)"
    print("[SE_LOG] " .. tostring(msg))
end

-- se_log_int: print format string + field as integer
-- params[1] = str_ptr (format string),  params[2] = field_ref
M.se_log_int = function(inst, node)
    local fmt = param_str(node, 1) or "%d"
    local v   = field_get(inst, node, 2)
    print(string.format("[SE_LOG_INT] " .. fmt, tonumber(v) or 0))
end

-- se_log_float: print format string + field as float
-- params[1] = str_ptr (format string),  params[2] = field_ref
M.se_log_float = function(inst, node)
    local fmt = param_str(node, 1) or "%f"
    local v   = field_get(inst, node, 2)
    print(string.format("[SE_LOG_FLOAT] " .. fmt, tonumber(v) or 0))
end

-- se_log_field: print field name and value
-- params[1] = field_ref
M.se_log_field = function(inst, node)
    local name = param_field_name(node, 1)
    local v    = inst.blackboard[name]
    print("[SE_LOG_FIELD] " .. tostring(name) .. " = " .. tostring(v))
end

-- ----------------------------------------------------------------------------
-- Field write operations
-- ----------------------------------------------------------------------------

-- se_set_field: write integer or hash constant to field
-- params[1] = field_ref,  params[2] = int/uint/str_hash value
M.se_set_field = function(inst, node)
    local p = (node.params or {})[2]
    assert(p, "se_set_field: missing param 2")
    local val
    if type(p.value) == "table" and p.value.hash then
        val = p.value.hash       -- str_hash: store the numeric hash
    else
        val = param_int(node, 2)
    end
    field_set(inst, node, 1, val)
end

-- se_set_field_float: write float constant to field
-- params[1] = field_ref,  params[2] = float value
M.se_set_field_float = function(inst, node)
    field_set(inst, node, 1, param_float(node, 2))
end

-- se_inc_field: increment field by 1
-- params[1] = field_ref
M.se_inc_field = function(inst, node)
    local v = field_get(inst, node, 1) or 0
    field_set(inst, node, 1, v + 1)
end

-- se_dec_field: decrement field by 1
-- params[1] = field_ref
M.se_dec_field = function(inst, node)
    local v = field_get(inst, node, 1) or 0
    field_set(inst, node, 1, v - 1)
end

-- se_set_hash: write a hash value to a field
-- params[1] = field_ref,  params[2] = str_hash
M.se_set_hash = function(inst, node)
    local p = (node.params or {})[2]
    assert(p, "se_set_hash: missing param 2")
    local hash = (type(p.value) == "table") and p.value.hash or p.value
    field_set(inst, node, 1, hash)
end

-- se_set_hash_field: alias for se_set_hash (DSL uses this name)
-- params[1] = field_ref,  params[2] = str_hash
M.se_set_hash_field = function(inst, node)
    local p = (node.params or {})[2]
    assert(p, "se_set_hash_field: missing param 2")
    local hash = (type(p.value) == "table") and p.value.hash or p.value
    field_set(inst, node, 1, hash)
end

-- se_set_external_field: write a value from own blackboard into a child tree's
-- blackboard, using a byte offset to resolve the target field name.
-- Mirrors the C version which does raw pointer arithmetic on the child's
-- blackboard struct.
--
-- params[1] = field_ref (source value field in own blackboard)
-- params[2] = field_ref (child tree instance in own blackboard)
-- params[3] = uint      (byte offset of target field in child's record)
M.se_set_external_field = function(inst, node)
    local params = node.params or {}
    assert(#params >= 3, "se_set_external_field: need 3 params")

    -- Read the value to write from own blackboard
    local value = inst.blackboard[params[1].value]

    -- Read the child tree instance from own blackboard
    local child = inst.blackboard[params[2].value]
    assert(child and type(child) == "table" and child.blackboard,
        "se_set_external_field: child tree instance not found in field: "
        .. tostring(params[2].value))

    -- Byte offset in the child's record
    local offset = params[3].value

    -- Resolve byte offset to field name using the child's record definition
    local record_name = child.tree.record_name
    local record = child.mod.module_data.records[record_name]
    assert(record, "se_set_external_field: child has no record: "
        .. tostring(record_name))

    for _, field in ipairs(record.fields) do
        if field.offset == offset then
            child.blackboard[field.name] = value
            return
        end
    end

    error(string.format(
        "se_set_external_field: no field at offset %d in record '%s'",
        offset, record_name))
end

-- ----------------------------------------------------------------------------
-- Event queue
-- ----------------------------------------------------------------------------

-- se_queue_event: push an event onto the instance event queue
-- params[1] = tick_type (uint), params[2] = event_id (uint),
-- params[3] = field_ref (blackboard field name passed as event_data)
M.se_queue_event = function(inst, node)
    local tt        = param_int(node, 1)
    local eid       = param_int(node, 2)
    local field_name = param_field_name(node, 3)  -- may be nil if not present
    se_runtime.event_push(inst, tt, eid, field_name)
end

-- ----------------------------------------------------------------------------
-- Stack
-- ----------------------------------------------------------------------------

-- se_push_stack: push params[1] value onto inst.stack
-- Handles int/uint, field_ref, and str_hash param types.
M.se_push_stack = function(inst, node)
    if inst.stack then
        local p = (node.params or {})[1]
        assert(p, "se_push_stack: missing param 1")
        local val
        if p.type == "field_ref" then
            val = inst.blackboard[p.value] or 0
        elseif type(p.value) == "table" and p.value.hash then
            val = p.value.hash
        else
            val = param_int(node, 1)
        end
        require("se_stack").push_int(inst.stack, val)
    end
end

-- ----------------------------------------------------------------------------
-- Function dictionary loading
-- NOTE: se_load_function_dict is implemented in se_builtins_dict.lua
-- NOTE: se_load_function is implemented in se_builtins_spawn.lua (io_call oneshot)
-- ----------------------------------------------------------------------------

return M