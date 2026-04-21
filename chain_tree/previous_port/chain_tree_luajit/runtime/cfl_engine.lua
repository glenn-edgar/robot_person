-- ============================================================================
-- cfl_engine.lua
-- ChainTree LuaJIT Runtime — engine core: KB activation, node execution
-- Mirrors cfl_engine.c
--
-- The engine sets up walker callbacks, manages node flags, and dispatches
-- the main/init/aux/term functions for each visited node.
-- ============================================================================

local M = {}

local bit = require("bit")
local band, bor, bnot = bit.band, bit.bor, bit.bnot

local defs   = require("cfl_definitions")
local walker = require("cfl_tree_walker")
local common = require("cfl_common")

-- Local aliases for hot constants
local CT_FLAG_USER1     = defs.CT_FLAG_USER1
local CT_FLAG_USER2     = defs.CT_FLAG_USER2
local CT_FLAG_USER3     = defs.CT_FLAG_USER3
local CT_FLAG_USER_MASK = defs.CT_FLAG_USER_MASK

local CFL_CONTINUE         = defs.CFL_CONTINUE
local CFL_HALT             = defs.CFL_HALT
local CFL_TERMINATE        = defs.CFL_TERMINATE
local CFL_RESET            = defs.CFL_RESET
local CFL_DISABLE          = defs.CFL_DISABLE
local CFL_SKIP_CONTINUE    = defs.CFL_SKIP_CONTINUE
local CFL_TERMINATE_SYSTEM = defs.CFL_TERMINATE_SYSTEM

local CT_CONTINUE      = defs.CT_CONTINUE
local CT_SKIP_CHILDREN = defs.CT_SKIP_CHILDREN
local CT_STOP_SIBLINGS = defs.CT_STOP_SIBLINGS
local CT_STOP_ALL      = defs.CT_STOP_ALL

local CFL_INIT_EVENT      = defs.CFL_INIT_EVENT
local CFL_TERMINATE_EVENT = defs.CFL_TERMINATE_EVENT
local CFL_EVENT_TYPE_NULL = defs.CFL_EVENT_TYPE_NULL
local CFL_LINK_COUNT_MASK = defs.CFL_LINK_COUNT_MASK
local CFL_NO_PARENT       = defs.CFL_NO_PARENT

-- ============================================================================
-- get_children callback for walker
-- ============================================================================
local function get_forward_enabled_links(handle, node_id)
    return common.get_children_from_links(handle.flash_handle, node_id)
end

-- ============================================================================
-- Disable a single node (run teardown if initialized)
-- ============================================================================
local function disable_node(handle, node_id)
    local flags = handle.flags
    local nf = flags[node_id]

    -- Only run teardown if enabled AND initialized
    if band(nf, CT_FLAG_USER3 + CT_FLAG_USER2) ~= (CT_FLAG_USER3 + CT_FLAG_USER2) then
        flags[node_id] = band(nf, bnot(CT_FLAG_USER_MASK))
        return
    end

    local node = handle.flash_handle.nodes[node_id]

    -- Aux/boolean terminate first
    if node.aux_function_index ~= 0 then
        local aux_fn = handle.flash_handle.boolean_functions[node.aux_function_index]
        if aux_fn then
            aux_fn(handle, node_id, CFL_EVENT_TYPE_NULL, CFL_TERMINATE_EVENT, nil)
        end
    end

    -- Term one-shot second
    if node.term_function_index ~= 0 then
        local term_fn = handle.flash_handle.one_shot_functions[node.term_function_index]
        if term_fn then
            term_fn(handle, node_id)
        end
    end

    flags[node_id] = band(nf, bnot(CT_FLAG_USER_MASK))
end

-- ============================================================================
-- Terminate a subtree (mark, then disable in reverse)
-- ============================================================================
function M.terminate_node_tree(handle, node_id)
    local flags = handle.flags

    -- Early out if never initialized
    if band(flags[node_id], CT_FLAG_USER2) == 0 then
        return
    end

    local node = handle.flash_handle.nodes[node_id]
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)

    -- Leaf node — disable directly
    if link_count == 0 then
        disable_node(handle, node_id)
        return
    end

    -- Save walker context
    local ctx = walker.save_context(handle.walker)

    -- Mark phase: walk subtree setting USER1 on enabled nodes
    walker.update_functions(handle.walker,
        function(h, nid, level, fl)
            if band(fl[nid], CT_FLAG_USER3) ~= 0 then
                handle.backup_flags[nid] = bor(handle.backup_flags[nid] or 0, CT_FLAG_USER1)
            end
            return CT_CONTINUE
        end,
        get_forward_enabled_links
    )

    -- Initialize backup_flags
    if not handle.backup_flags then handle.backup_flags = {} end
    for i = 0, handle.flash_handle.node_count - 1 do
        handle.backup_flags[i] = 0
    end

    walker.walk(handle.walker, handle, node_id,
        handle.walker.max_level, handle.flash_handle.node_count)

    -- Restore walker
    walker.restore_context(handle.walker, ctx)

    -- Terminate marked nodes in reverse order within KB range
    local start_idx = handle.kb_start_index or 0
    local end_idx   = start_idx + (handle.kb_node_count or handle.flash_handle.node_count) - 1
    if end_idx >= handle.flash_handle.node_count then
        end_idx = handle.flash_handle.node_count - 1
    end

    for i = end_idx, node_id, -1 do
        if handle.backup_flags[i] and band(handle.backup_flags[i], CT_FLAG_USER1) ~= 0 then
            handle.backup_flags[i] = band(handle.backup_flags[i], bnot(CT_FLAG_USER1))
            disable_node(handle, i)
        end
    end
end

-- ============================================================================
-- Terminate all nodes in a KB
-- ============================================================================
function M.terminate_all_nodes_in_kb(handle, start_node, node_count)
    for i = start_node + node_count - 1, start_node, -1 do
        disable_node(handle, i)
    end
end

-- ============================================================================
-- execute_node callback for walker
-- ============================================================================
local function execute_node(handle, node_id, level, flags)
    local node = handle.flash_handle.nodes[node_id]

    if band(flags[node_id], CT_FLAG_USER3) == 0 then
        return CT_SKIP_CHILDREN
    end

    handle.cfl_node_execution_count = handle.cfl_node_execution_count + 1

    -- Initialize if not yet done
    if band(flags[node_id], CT_FLAG_USER2) == 0 then
        if node.init_function_index ~= 0 then
            local init_fn = handle.flash_handle.one_shot_functions[node.init_function_index]
            if init_fn then init_fn(handle, node_id) end
        end
        if node.aux_function_index ~= 0 then
            local aux_fn = handle.flash_handle.boolean_functions[node.aux_function_index]
            if aux_fn then
                aux_fn(handle, node_id, CFL_EVENT_TYPE_NULL, CFL_INIT_EVENT, nil)
            end
        end
        flags[node_id] = bor(flags[node_id], CT_FLAG_USER2)

        -- Auto-start: enable all children if bit 15 set in link_count
        if band(node.link_count, defs.CFL_AUTO_START_BIT) ~= 0 then
            local link_start = node.link_start
            local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
            local lt = handle.flash_handle.link_table
            for i = 0, link_count - 1 do
                local child_id = lt[link_start + i]
                M.enable_node(handle, child_id)
            end
        end
    end

    -- Execute main function
    local main_fn = handle.flash_handle.main_functions[node.main_function_index]
    assert(main_fn, "cfl_engine: no main function at index " ..
        node.main_function_index .. " for node " .. node_id)

    local event = handle.event_data_ptr
    local rc = main_fn(handle, node.aux_function_index, node_id,
                       event.event_type, event.event_id, event.data)

    handle.cfl_engine_flag = true

    if rc == CFL_CONTINUE then
        return CT_CONTINUE

    elseif rc == CFL_HALT then
        return CT_STOP_SIBLINGS

    elseif rc == CFL_RESET then
        M.terminate_node_tree(handle, node.parent_index)
        -- Re-enable parent
        M.enable_node(handle, node.parent_index)
        return CT_CONTINUE

    elseif rc == CFL_DISABLE then
        M.terminate_node_tree(handle, node_id)
        return CT_SKIP_CHILDREN

    elseif rc == CFL_SKIP_CONTINUE then
        return CT_SKIP_CHILDREN

    elseif rc == CFL_TERMINATE then
        if node.parent_index ~= CFL_NO_PARENT then
            M.terminate_node_tree(handle, node.parent_index)
            return CT_SKIP_CHILDREN
        end
        disable_node(handle, node_id)
        return CT_STOP_ALL

    elseif rc == CFL_TERMINATE_SYSTEM then
        handle.cfl_engine_flag = false
        M.terminate_node_tree(handle, handle.node_start_index)
        return CT_STOP_ALL

    else
        error("cfl_engine: invalid return code: " .. tostring(rc))
    end
end

-- ============================================================================
-- Public API
-- ============================================================================

function M.create(handle)
    handle.walker = walker.create(handle.flash_handle.node_count)
    -- Share handle.flags with walker so visited bits and user flags coexist
    -- (mirrors C version where CT_Tree_Walker and engine use the same array)
    handle.walker.flags = handle.flags
    handle.walker.apply_func   = execute_node
    handle.walker.get_children = get_forward_enabled_links
    handle.backup_flags = {}
end

function M.init(handle)
    -- Disable all user flags
    local flags = handle.flags
    for i = 0, handle.flash_handle.node_count - 1 do
        flags[i] = band(flags[i], bnot(CT_FLAG_USER_MASK))
    end
end

function M.init_test(handle, start_node, node_count)
    local flags = handle.flags
    for i = start_node, start_node + node_count - 1 do
        flags[i] = band(flags[i], bnot(CT_FLAG_USER_MASK))
    end
    -- Enable start node
    M.enable_node(handle, start_node)
end

function M.execute_event(handle)
    local event = handle.event_data_ptr
    local node_id = event.node_id

    if not M.node_is_enabled(handle, node_id) then
        return false
    end

    handle.cfl_engine_flag = true
    handle.cfl_node_execution_count = 0
    handle.node_start_index = node_id

    walker.walk(handle.walker, handle, node_id,
        handle.walker.max_level, handle.flash_handle.node_count)

    if handle.cfl_node_execution_count == 0 or not handle.cfl_engine_flag then
        handle.cfl_engine_flag = false
    end

    return handle.cfl_engine_flag
end

function M.node_is_enabled(handle, node_id)
    return band(handle.flags[node_id] or 0, CT_FLAG_USER3) ~= 0
end

function M.node_is_initialized(handle, node_id)
    local f = handle.flags[node_id] or 0
    return band(f, CT_FLAG_USER2) ~= 0 and band(f, CT_FLAG_USER3) ~= 0
end

function M.enable_node(handle, node_id)
    local flags = handle.flags
    flags[node_id] = bor(band(flags[node_id], bnot(CT_FLAG_USER_MASK)), CT_FLAG_USER3)
end

function M.disable_node_flag(handle, node_id)
    handle.flags[node_id] = band(handle.flags[node_id], bnot(CT_FLAG_USER_MASK))
end

return M
