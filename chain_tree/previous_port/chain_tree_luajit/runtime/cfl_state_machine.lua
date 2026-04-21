-- ============================================================================
-- cfl_state_machine.lua
-- ChainTree LuaJIT Runtime — state machine built-in functions
-- Mirrors cfl_sm_functions.c
-- ============================================================================

local M = {}

local bit  = require("bit")
local band = bit.band

local defs   = require("cfl_definitions")
local common = require("cfl_common")

local CFL_CONTINUE         = defs.CFL_CONTINUE
local CFL_HALT             = defs.CFL_HALT
local CFL_DISABLE          = defs.CFL_DISABLE
local CFL_SKIP_CONTINUE    = defs.CFL_SKIP_CONTINUE
local CFL_TERMINATE_SYSTEM = defs.CFL_TERMINATE_SYSTEM
local CFL_TIMER_EVENT      = defs.CFL_TIMER_EVENT
local CFL_CHANGE_STATE_EVENT           = defs.CFL_CHANGE_STATE_EVENT
local CFL_RESET_STATE_MACHINE_EVENT    = defs.CFL_RESET_STATE_MACHINE_EVENT
local CFL_TERMINATE_STATE_MACHINE_EVENT = defs.CFL_TERMINATE_STATE_MACHINE_EVENT
local CFL_LINK_COUNT_MASK = defs.CFL_LINK_COUNT_MASK
local CT_FLAG_USER3        = defs.CT_FLAG_USER3

local engine -- lazy
local function get_engine()
    if not engine then engine = require("cfl_engine") end
    return engine
end

-- ============================================================================
-- State machine main function
--
-- Per-node state:
--   ns.current_state  (0-based child index)
--   ns.state_count    (number of children = states)
-- ============================================================================

M.CFL_STATE_MACHINE_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    -- Handle state machine control events
    if event_id == CFL_CHANGE_STATE_EVENT then
        -- event_data is {sm_node_id, new_state, sync_flag, sync_event_id}
        if event_data and event_data.sm_node_id == node_idx then
            local ns = common.get_node_state(handle, node_idx)
            if ns then
                local node = handle.flash_handle.nodes[node_idx]
                local lt = handle.flash_handle.link_table
                local link_start = node.link_start
                local old_child = lt[link_start + ns.current_state]

                -- Terminate old state
                get_engine().terminate_node_tree(handle, old_child)

                -- Activate new state
                ns.current_state = event_data.new_state
                local new_child = lt[link_start + ns.current_state]
                get_engine().enable_node(handle, new_child)
            end
        end
        return CFL_CONTINUE
    end

    if event_id ~= CFL_TIMER_EVENT then
        return CFL_CONTINUE
    end

    -- Normal tick: check if active state child is still enabled
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end

    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_start = node.link_start
    local active_child = lt[link_start + ns.current_state]

    if band(handle.flags[active_child], CT_FLAG_USER3) ~= 0 then
        return CFL_CONTINUE
    end

    return CFL_DISABLE
end

-- ============================================================================
-- State machine control helpers
-- ============================================================================

function M.change_state(handle, node_idx, sm_node_id, new_state, sync_event_id)
    local eq = require("cfl_event_queue")
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
        sm_node_id, defs.CFL_EVENT_TYPE_NULL,
        CFL_CHANGE_STATE_EVENT,
        { sm_node_id = sm_node_id, new_state = new_state,
          sync_event_id = sync_event_id })
end

function M.terminate_state_machine(handle, node_idx, sm_node_id)
    get_engine().terminate_node_tree(handle, sm_node_id)
end

function M.reset_state_machine(handle, node_idx, sm_node_id)
    get_engine().terminate_node_tree(handle, sm_node_id)
    get_engine().enable_node(handle, sm_node_id)
end

return M
