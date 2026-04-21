-- ============================================================================
-- cfl_common.lua
-- ChainTree LuaJIT Runtime — shared helpers
-- Mirrors cfl_common_functions.c / fnv1a.c
-- ============================================================================

local M = {}

local bit = require("bit")
local band, bxor = bit.band, bit.bxor
local defs = require("cfl_definitions")

-- ============================================================================
-- FNV-1a 32-bit hash (for blackboard field compat)
-- ============================================================================
function M.fnv1a_32(str)
    local hash = 2166136261
    for i = 1, #str do
        hash = bxor(hash, str:byte(i))
        -- Multiply by 16777619 using 32-bit arithmetic
        hash = hash * 16777619
        hash = band(hash, 0xFFFFFFFF)
    end
    return hash
end

-- ============================================================================
-- Node child helpers
-- ============================================================================

-- Get children of a node from the flash_handle link table.
-- Returns a 1-based array of child node indices (0-based node IDs).
function M.get_children_from_links(flash_handle, node_id)
    local node = flash_handle.nodes[node_id]
    if not node then return {} end

    local link_start = node.link_start
    local link_count = band(node.link_count, defs.CFL_LINK_COUNT_MASK)
    if link_count == 0 then return {} end

    local children = {}
    local lt = flash_handle.link_table
    for i = 0, link_count - 1 do
        children[#children + 1] = lt[link_start + i]
    end
    return children
end

-- Enable all children of a node
function M.enable_children(handle, node_id)
    local children = M.get_children_from_links(handle.flash_handle, node_id)
    for _, child_id in ipairs(children) do
        handle.flags[child_id] = bit.bor(
            band(handle.flags[child_id], bit.bnot(defs.CT_FLAG_USER_MASK)),
            defs.CT_FLAG_USER3
        )
    end
end

-- Disable all children flags
function M.disable_children(handle, node_id)
    local children = M.get_children_from_links(handle.flash_handle, node_id)
    for _, child_id in ipairs(children) do
        handle.flags[child_id] = band(handle.flags[child_id], bit.bnot(defs.CT_FLAG_USER_MASK))
    end
end

-- Check if any child is enabled
function M.any_child_enabled(handle, node_id)
    local children = M.get_children_from_links(handle.flash_handle, node_id)
    for _, child_id in ipairs(children) do
        if band(handle.flags[child_id], defs.CT_FLAG_USER3) ~= 0 then
            return true
        end
    end
    return false
end

-- Enable a specific child by its link index (0-based)
function M.enable_child(handle, node_id, child_link_index)
    local node = handle.flash_handle.nodes[node_id]
    local lt = handle.flash_handle.link_table
    local child_id = lt[node.link_start + child_link_index]
    handle.flags[child_id] = bit.bor(
        band(handle.flags[child_id], bit.bnot(defs.CT_FLAG_USER_MASK)),
        defs.CT_FLAG_USER3
    )
end

-- ============================================================================
-- Per-node mutable state (replaces C arena allocator)
-- ============================================================================

function M.get_node_state(handle, node_id)
    return handle.node_state[node_id]
end

function M.set_node_state(handle, node_id, data)
    handle.node_state[node_id] = data
end

function M.alloc_node_state(handle, node_id, initial)
    if not handle.node_state[node_id] then
        handle.node_state[node_id] = initial or {}
    end
    return handle.node_state[node_id]
end

-- ============================================================================
-- Bitmask helpers
-- ============================================================================

function M.get_bitmask(handle)
    return handle.bitmask or 0
end

function M.set_bitmask(handle, mask)
    handle.shaddow_bitmask = mask
end

function M.change_bitmask(handle, mask)
    handle.shaddow_bitmask = mask
end

-- ============================================================================
-- Node data access (from JSON IR node_dict)
-- ============================================================================

function M.get_node_data(handle, node_id)
    local fh = handle.flash_handle
    if fh.node_data and fh.node_data[node_id] then
        return fh.node_data[node_id]
    end
    return nil
end

-- Deep-get a dotted path from node_data, e.g. "fn_data.time_out"
function M.get_node_data_field(handle, node_id, path)
    local data = M.get_node_data(handle, node_id)
    if not data then return nil end

    for key in path:gmatch("[^%.]+") do
        if type(data) ~= "table" then return nil end
        data = data[key]
    end
    return data
end

-- ============================================================================
-- Walk parent chain to find nearest exception catch node
-- Returns node_id or nil
-- ============================================================================
function M.find_parent_exception_node(handle, node_id)
    local nodes = handle.flash_handle.nodes
    local names = handle.flash_handle.main_function_names
    local cur = node_id
    while true do
        local node = nodes[cur]
        if not node then return nil end
        local pid = node.parent_index
        if not pid or pid == defs.CFL_NO_PARENT then return nil end
        local pnode = nodes[pid]
        if not pnode then return nil end
        local fn_name = names[pnode.main_function_index]
        if fn_name == "CFL_EXCEPTION_CATCH_MAIN" or fn_name == "CFL_EXCEPTION_CATCH_ALL_MAIN" then
            return pid
        end
        cur = pid
    end
end

return M
