-- ============================================================================
-- cfl_blackboard.lua
-- ChainTree LuaJIT Runtime — shared mutable blackboard + constant records
-- Mirrors cfl_blackboard.c
--
-- In LuaJIT the blackboard is a string-keyed table (no byte offsets needed).
-- Constant records are plain read-only tables.
-- ============================================================================

local M = {}

-- ============================================================================
-- Initialize blackboard from JSON IR descriptor
-- ============================================================================
function M.init(handle)
    local bb_desc = handle.flash_handle.bb_table
    if not bb_desc then
        handle.blackboard = {}
        handle.bb_defaults = {}
        handle.const_records = {}
        return true
    end

    -- Mutable blackboard
    local bb = {}
    local defaults = {}
    if bb_desc.fields then
        for _, field in ipairs(bb_desc.fields) do
            local val = field.default
            if val == nil then val = 0 end
            bb[field.name] = val
            defaults[field.name] = val
        end
    end
    handle.blackboard = bb
    handle.bb_defaults = defaults

    -- Constant records
    local const_recs = {}
    if bb_desc.const_records then
        for _, rec in ipairs(bb_desc.const_records) do
            local data = {}
            if rec.fields then
                for _, f in ipairs(rec.fields) do
                    data[f.name] = f.value or f.default or 0
                end
            end
            const_recs[rec.name] = data
        end
    end
    handle.const_records = const_recs

    return true
end

-- ============================================================================
-- Reset blackboard to defaults
-- ============================================================================
function M.reset(handle)
    if handle.bb_defaults then
        for name, val in pairs(handle.bb_defaults) do
            handle.blackboard[name] = val
        end
    end
end

-- ============================================================================
-- Field access — by name
-- ============================================================================
function M.get(handle, field_name)
    return handle.blackboard[field_name]
end

function M.set(handle, field_name, value)
    handle.blackboard[field_name] = value
end

-- ============================================================================
-- Constant record access
-- ============================================================================
function M.const_find(handle, record_name)
    return handle.const_records and handle.const_records[record_name]
end

function M.const_field(record, field_name)
    if record then return record[field_name] end
    return nil
end

return M
