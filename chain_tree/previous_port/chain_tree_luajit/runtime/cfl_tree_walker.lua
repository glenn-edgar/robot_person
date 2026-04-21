-- ============================================================================
-- cfl_tree_walker.lua
-- ChainTree LuaJIT Runtime — iterative DFS tree walker
-- Mirrors CT_Tree_Walker.c
--
-- API:
--   local walker = cfl_tree_walker.create(node_count)
--   walker.apply_func  = function(handle, node_id, level, flags) -> CT_ReturnCode
--   walker.get_children = function(handle, node_id) -> {child_id, ...}
--   cfl_tree_walker.walk(walker, handle, root_id, max_level, max_node_id)
--   cfl_tree_walker.save_context(walker) -> context
--   cfl_tree_walker.restore_context(walker, context)
-- ============================================================================

local M = {}

local bit = require("bit")
local band, bor, bnot = bit.band, bit.bor, bit.bnot

local defs = require("cfl_definitions")
local CT_FLAG_VISITED   = defs.CT_FLAG_VISITED
local CT_FLAG_USER_MASK = defs.CT_FLAG_USER_MASK
local CT_CONTINUE       = defs.CT_CONTINUE
local CT_SKIP_CHILDREN  = defs.CT_SKIP_CHILDREN
local CT_STOP_BRANCH    = defs.CT_STOP_BRANCH
local CT_STOP_SIBLINGS  = defs.CT_STOP_SIBLINGS
local CT_STOP_LEVEL     = defs.CT_STOP_LEVEL
local CT_STOP_ALL       = defs.CT_STOP_ALL

-- ============================================================================
-- Create walker
-- ============================================================================
function M.create(node_count)
    local flags = {}
    for i = 0, node_count - 1 do flags[i] = 0 end

    return {
        flags         = flags,
        max_nodes     = node_count,
        max_level     = 0xFFFF,
        max_node_id   = node_count - 1,
        stop_all      = false,
        apply_func    = nil,   -- set by engine
        get_children  = nil,   -- set by engine
    }
end

-- ============================================================================
-- Clear engine flags (visited), keep user flags
-- ============================================================================
local function clear_engine_flags(walker)
    local flags = walker.flags
    for i = 0, walker.max_nodes - 1 do
        flags[i] = band(flags[i], CT_FLAG_USER_MASK)
    end
end

-- ============================================================================
-- Iterative DFS walk — port of walk_iterative()
-- ============================================================================
function M.walk(walker, handle, root_id, max_level, max_node_id)
    max_level   = max_level   or walker.max_level
    max_node_id = max_node_id or walker.max_node_id

    walker.max_level   = max_level
    walker.max_node_id = max_node_id
    walker.stop_all    = false

    clear_engine_flags(walker)

    local flags        = walker.flags
    local apply_func   = walker.apply_func
    local get_children = walker.get_children

    -- Explicit stack: {node_id, level, child_index}
    local stack = {}
    local sp = 0
    sp = sp + 1
    stack[sp] = { node_id = root_id, level = 0, child_index = 0 }

    while sp > 0 do
        if walker.stop_all then return CT_STOP_ALL end

        local entry   = stack[sp]
        local node_id = entry.node_id
        local level   = entry.level
        local ci      = entry.child_index

        -- Check visited
        local nf = flags[node_id]
        if band(nf, CT_FLAG_VISITED) ~= 0 then
            if ci == 0 then
                sp = sp - 1
                goto continue_loop
            end
        else
            -- First visit — mark visited
            flags[node_id] = bor(nf, CT_FLAG_VISITED)

            if level > max_level then
                sp = sp - 1
                goto continue_loop
            end

            -- Apply function
            local ret = apply_func(handle, node_id, level, flags)

            if ret == CT_STOP_ALL then
                walker.stop_all = true
                return CT_STOP_ALL
            elseif ret == CT_STOP_BRANCH then
                sp = sp - 1
                goto continue_loop
            elseif ret == CT_STOP_SIBLINGS then
                sp = sp - 1
                if sp > 0 then sp = sp - 1 end
                goto continue_loop
            elseif ret == CT_STOP_LEVEL then
                walker.max_level = level
                sp = sp - 1
                goto continue_loop
            elseif ret == CT_SKIP_CHILDREN then
                sp = sp - 1
                goto continue_loop
            end
            -- CT_CONTINUE: fall through to children
        end

        -- Get children
        local children = get_children(handle, node_id)
        local next_ci = ci + 1  -- 1-based index into children

        if next_ci <= #children and level < max_level then
            entry.child_index = next_ci
            local child_id = children[next_ci]

            if child_id <= max_node_id and band(flags[child_id], CT_FLAG_VISITED) == 0 then
                sp = sp + 1
                stack[sp] = { node_id = child_id, level = level + 1, child_index = 0 }
            end
        else
            sp = sp - 1
        end

        ::continue_loop::
    end

    return CT_CONTINUE
end

-- ============================================================================
-- Context save/restore for nested walks (e.g., terminate_node_tree)
-- ============================================================================
function M.save_context(walker)
    -- Shallow copy flags
    local backup = {}
    for i = 0, walker.max_nodes - 1 do
        backup[i] = walker.flags[i]
    end
    return {
        saved_flags      = backup,
        saved_stop_all   = walker.stop_all,
        saved_max_level  = walker.max_level,
        saved_max_node_id = walker.max_node_id,
        saved_apply_func = walker.apply_func,
    }
end

function M.restore_context(walker, ctx)
    for i = 0, walker.max_nodes - 1 do
        walker.flags[i] = ctx.saved_flags[i]
    end
    walker.stop_all   = ctx.saved_stop_all
    walker.max_level  = ctx.saved_max_level
    walker.max_node_id = ctx.saved_max_node_id
    walker.apply_func = ctx.saved_apply_func
end

-- ============================================================================
-- Flag queries
-- ============================================================================
function M.reset(walker)
    clear_engine_flags(walker)
    walker.stop_all = false
end

function M.is_visited(walker, node_id)
    return band(walker.flags[node_id], CT_FLAG_VISITED) ~= 0
end

function M.update_functions(walker, apply_func, get_children)
    if apply_func   then walker.apply_func   = apply_func   end
    if get_children  then walker.get_children = get_children end
end

return M
