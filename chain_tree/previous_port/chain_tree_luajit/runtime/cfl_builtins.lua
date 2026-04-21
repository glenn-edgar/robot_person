-- ============================================================================
-- cfl_builtins.lua
-- ChainTree LuaJIT Runtime — all built-in main, boolean, and one-shot functions
-- Mirrors cfl_main_functions.c, cfl_boolean_functions.c, cfl_one_shot_functions.c
--
-- Function keys match JSON IR names exactly (no _MAIN/_BOOLEAN/_ONE_SHOT suffixes).
--
-- Signatures:
--   main:    fn(handle, bool_fn_idx, node_idx, event_type, event_id, event_data) -> return_code
--   boolean: fn(handle, node_idx, event_type, event_id, event_data) -> bool
--   oneshot: fn(handle, node_idx) -> nil
-- ============================================================================

local M = {}

local bit  = require("bit")
local band, bor = bit.band, bit.bor

local defs      = require("cfl_definitions")
local common    = require("cfl_common")
local streaming = require("cfl_streaming")
local engine -- loaded lazily to avoid circular require

local CFL_CONTINUE         = defs.CFL_CONTINUE
local CFL_HALT             = defs.CFL_HALT
local CFL_TERMINATE        = defs.CFL_TERMINATE
local CFL_RESET            = defs.CFL_RESET
local CFL_DISABLE          = defs.CFL_DISABLE
local CFL_SKIP_CONTINUE    = defs.CFL_SKIP_CONTINUE
local CFL_TERMINATE_SYSTEM = defs.CFL_TERMINATE_SYSTEM

local CFL_TIMER_EVENT      = defs.CFL_TIMER_EVENT
local CFL_INIT_EVENT       = defs.CFL_INIT_EVENT
local CFL_TERMINATE_EVENT  = defs.CFL_TERMINATE_EVENT
local CFL_LINK_COUNT_MASK  = defs.CFL_LINK_COUNT_MASK
local CT_FLAG_USER3        = defs.CT_FLAG_USER3
local CFL_RAISE_EXCEPTION_EVENT = defs.CFL_RAISE_EXCEPTION_EVENT
local CFL_EVENT_TYPE_NULL  = defs.CFL_EVENT_TYPE_NULL

local function get_engine()
    if not engine then engine = require("cfl_engine") end
    return engine
end

-- Helper: resolve a oneshot function name to its index
local function resolve_oneshot_idx(handle, name)
    if not name or name == "" or name == "CFL_NULL" then return 0 end
    local idx = handle.flash_handle._oneshot_fn_idx[name]
    return idx or 0
end

-- ============================================================================
-- MAIN FUNCTIONS
-- ============================================================================

-- No-op: always continue (main), always false (boolean), no-op (oneshot)
M.CFL_NULL = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return CFL_CONTINUE
end

-- Always disable
M.CFL_DISABLE = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return CFL_DISABLE
end

-- Always halt
M.CFL_HALT = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return CFL_HALT
end

-- Always reset
M.CFL_RESET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return CFL_RESET
end

-- Always terminate
M.CFL_TERMINATE = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return CFL_TERMINATE
end

-- Terminate system
M.CFL_TERMINATE_SYSTEM = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return CFL_TERMINATE_SYSTEM
end

-- Column main: check boolean, check children enabled
M.CFL_COLUMN_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    if event_id ~= CFL_TIMER_EVENT then
        return CFL_CONTINUE
    end

    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table

    for i = 0, link_count - 1 do
        local child_id = lt[link_start + i]
        if band(handle.flags[child_id], CT_FLAG_USER3) ~= 0 then
            return CFL_CONTINUE
        end
    end

    return CFL_DISABLE
end

-- Aliases for column-like mains
M.CFL_LOCAL_ARENA_MAIN    = M.CFL_COLUMN_MAIN
M.CFL_GATE_NODE_MAIN      = M.CFL_COLUMN_MAIN
M.CFL_FORK_MAIN           = M.CFL_COLUMN_MAIN
M.CFL_SEQUENCE_START_MAIN = M.CFL_COLUMN_MAIN

-- Verify: check boolean, if false call error handler
M.CFL_VERIFY = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_CONTINUE
    end

    local ns = common.get_node_state(handle, node_idx)
    if ns and ns.error_function and ns.error_function ~= 0 then
        local err_fn = handle.flash_handle.one_shot_functions[ns.error_function]
        if err_fn then err_fn(handle, node_idx) end
        if ns.reset_flag then return CFL_RESET end
    end

    return CFL_TERMINATE
end

-- Wait: halt until boolean or event count reached
M.CFL_WAIT = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns or ns.timeout == 0 then
        return CFL_HALT
    end

    if ns.time_out_event == event_id then
        ns.event_count = (ns.event_count or 0) + 1
        if ns.event_count >= ns.timeout then
            if ns.error_function then
                local err_fn = handle.flash_handle.one_shot_functions[ns.error_function]
                if err_fn then err_fn(handle, node_idx) end
            end
            if ns.reset_flag then return CFL_RESET end
            return CFL_TERMINATE
        end
    end

    return CFL_HALT
end

-- Wait time: halt until timestamp exceeded
M.CFL_WAIT_TIME = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end
    if event_id ~= CFL_TIMER_EVENT then
        return CFL_HALT
    end

    local ns = common.get_node_state(handle, node_idx)
    if ns and ns.wait_time_out and ns.wait_time_out >= handle.timer.timestamp then
        return CFL_HALT
    end
    return CFL_DISABLE
end

-- Event logger
M.CFL_EVENT_LOGGER = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.event_ids then return CFL_DISABLE end

    for _, eid in ipairs(ns.event_ids) do
        if eid == event_id then
            print(string.format("++++ timestamp %f, node %d, event %d, msg: %s",
                handle.timer.timestamp, node_idx, event_id, ns.message or ""))
        end
    end
    return CFL_CONTINUE
end

-- Join: halt until target node disabled
M.CFL_JOIN_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end

    if ns.target_node and get_engine().node_is_enabled(handle, ns.target_node) then
        return CFL_HALT
    end
    return CFL_DISABLE
end

M.CFL_JOIN_SEQUENCE_ELEMENT = M.CFL_JOIN_MAIN

-- Sequence pass (sequence_till pattern)
M.CFL_SEQUENCE_PASS_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    if bool_fn_idx ~= 0 then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        if bool_fn(handle, node_idx, event_type, event_id, event_data) then
            return CFL_DISABLE
        end
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end
    if event_id ~= CFL_TIMER_EVENT then return CFL_CONTINUE end

    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table
    local active_link = lt[link_start + ns.current_sequence_index]

    if get_engine().node_is_enabled(handle, active_link) then
        return CFL_CONTINUE
    end

    ns.final_status = ns.sequence_results and ns.sequence_results[ns.current_sequence_index]
    if ns.current_sequence_index + 1 >= link_count then
        if ns.finalize_fn then
            local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
            if fin then fin(handle, node_idx) end
        end
        return CFL_DISABLE
    end

    -- Pass: if child failed, advance to next
    if ns.final_status == false then
        get_engine().terminate_node_tree(handle, active_link)
        ns.current_sequence_index = ns.current_sequence_index + 1
        get_engine().enable_node(handle, lt[link_start + ns.current_sequence_index])
        return CFL_CONTINUE
    end

    if ns.finalize_fn then
        local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
        if fin then fin(handle, node_idx) end
    end
    return CFL_DISABLE
end

-- Sequence fail
M.CFL_SEQUENCE_FAIL_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    if bool_fn_idx ~= 0 then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        if bool_fn(handle, node_idx, event_type, event_id, event_data) then
            return CFL_DISABLE
        end
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end
    if event_id ~= CFL_TIMER_EVENT then return CFL_CONTINUE end

    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table
    local active_link = lt[link_start + ns.current_sequence_index]

    if get_engine().node_is_enabled(handle, active_link) then
        return CFL_CONTINUE
    end

    ns.final_status = ns.sequence_results and ns.sequence_results[ns.current_sequence_index]
    if ns.current_sequence_index + 1 >= link_count then
        if ns.finalize_fn then
            local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
            if fin then fin(handle, node_idx) end
        end
        return CFL_DISABLE
    end

    -- Fail: if child passed, advance to next
    if ns.final_status == true then
        get_engine().terminate_node_tree(handle, active_link)
        ns.current_sequence_index = ns.current_sequence_index + 1
        get_engine().enable_node(handle, lt[link_start + ns.current_sequence_index])
        return CFL_CONTINUE
    end

    if ns.finalize_fn then
        local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
        if fin then fin(handle, node_idx) end
    end
    return CFL_DISABLE
end

-- For loop
M.CFL_FOR_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local child_id = lt[node.link_start]

    if get_engine().node_is_enabled(handle, child_id) then
        return CFL_CONTINUE
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end
    ns.current_iteration = (ns.current_iteration or 0) + 1
    if ns.current_iteration >= ns.number_of_iterations then
        return CFL_DISABLE
    end
    get_engine().enable_node(handle, child_id)
    return CFL_CONTINUE
end

-- While loop
M.CFL_WHILE_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local child_id = lt[node.link_start]

    if get_engine().node_is_enabled(handle, child_id) then
        return CFL_CONTINUE
    end

    local ns = common.get_node_state(handle, node_idx)
    if ns then ns.current_iteration = (ns.current_iteration or 0) + 1 end

    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if not bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end
    get_engine().enable_node(handle, child_id)
    return CFL_CONTINUE
end

-- Watchdog
M.CFL_WATCH_DOG_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.wd_enabled then return CFL_CONTINUE end
    if event_id ~= CFL_TIMER_EVENT then return CFL_CONTINUE end

    ns.current_count = (ns.current_count or 0) + 1
    if ns.current_count >= ns.wd_time_count then
        if ns.wd_fn_id then
            local wd_fn = handle.flash_handle.one_shot_functions[ns.wd_fn_id]
            if wd_fn then wd_fn(handle, node_idx) end
        end
        if ns.wd_reset then return CFL_RESET end
        return CFL_TERMINATE
    end
    return CFL_CONTINUE
end

-- Data flow bitmask
M.CFL_DF_MASK_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end

    if event_id == CFL_TIMER_EVENT then
        local required_met = band(ns.required_bitmask or 0, handle.bitmask or 0) == (ns.required_bitmask or 0)
        local excluded_clear = band(ns.excluded_bitmask or 0, handle.bitmask or 0) == 0
        local conditions_met = required_met and excluded_clear

        if not ns.node_state then
            if conditions_met then
                common.enable_children(handle, node_idx)
                ns.node_state = true
            end
        else
            if not conditions_met then
                local children = common.get_children_from_links(handle.flash_handle, node_idx)
                for _, cid in ipairs(children) do
                    get_engine().terminate_node_tree(handle, cid)
                end
                ns.node_state = false
            end
        end
    end

    if not ns.node_state then return CFL_SKIP_CONTINUE end
    return CFL_CONTINUE
end

-- Supervisor main: monitors children, tracks failures, handles reset/restart
M.CFL_SUPERVISOR_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    if event_id ~= CFL_TIMER_EVENT then
        return CFL_CONTINUE
    end

    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end

    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table

    -- Check if any child is still enabled
    local any_enabled = false
    for i = 0, link_count - 1 do
        local child_id = lt[link_start + i]
        if band(handle.flags[child_id], CT_FLAG_USER3) ~= 0 then
            any_enabled = true
            break
        end
    end

    if any_enabled then
        return CFL_CONTINUE
    end

    -- All children disabled — check restart policy
    ns.reset_count = (ns.reset_count or 0) + 1
    if ns.finalize_fn then
        local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
        if fin then fin(handle, node_idx) end
    end

    if ns.restart_enabled then
        if ns.reset_limited_enabled and ns.reset_count >= ns.max_reset_number then
            return CFL_DISABLE
        end
        -- Restart children
        common.enable_children(handle, node_idx)
        return CFL_CONTINUE
    end

    return CFL_DISABLE
end

-- Recovery main: step through children sequentially, skip if condition met
M.CFL_RECOVERY_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    if event_id ~= CFL_TIMER_EVENT then
        return CFL_CONTINUE
    end

    local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
    if bool_fn(handle, node_idx, event_type, event_id, event_data) then
        return CFL_DISABLE
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end

    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table

    if link_count == 0 then return CFL_DISABLE end

    local active_link = lt[link_start + ns.current_step]
    if get_engine().node_is_enabled(handle, active_link) then
        return CFL_CONTINUE
    end

    -- Current step finished — advance
    ns.current_step = ns.current_step + 1
    if ns.current_step >= link_count or ns.current_step >= (ns.max_steps or link_count) then
        return CFL_DISABLE
    end

    get_engine().enable_node(handle, lt[link_start + ns.current_step])
    return CFL_CONTINUE
end

-- Exception catch-all: column that handles exception events
M.CFL_EXCEPTION_CATCH_ALL_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        if bool_fn(handle, node_idx, event_type, event_id, event_data) then
            -- Exception caught — continue running children
            local ns = common.get_node_state(handle, node_idx)
            if ns and ns.logging_fn then
                local log_fn = handle.flash_handle.one_shot_functions[ns.logging_fn]
                if log_fn then
                    if ns then ns.original_node_id = event_data end
                    log_fn(handle, node_idx)
                end
            end
            return CFL_CONTINUE
        end
    end

    if event_id ~= CFL_TIMER_EVENT then
        return CFL_CONTINUE
    end

    -- Normal tick: check if children still enabled
    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table

    for i = 0, link_count - 1 do
        local child_id = lt[link_start + i]
        if band(handle.flags[child_id], CT_FLAG_USER3) ~= 0 then
            return CFL_CONTINUE
        end
    end

    return CFL_DISABLE
end

-- Exception catch (filtered): 3-stage pipeline with heartbeat monitoring
-- Stages: MAIN_LINK -> RECOVERY_LINK -> FINALIZE_LINK
M.CFL_EXCEPTION_CATCH_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_TERMINATE_SYSTEM end

    local CFL_EXCEPTION_MAIN_LINK     = defs.CFL_EXCEPTION_MAIN_LINK
    local CFL_EXCEPTION_RECOVERY_LINK = defs.CFL_EXCEPTION_RECOVERY_LINK
    local CFL_EXCEPTION_FINALIZE_LINK = defs.CFL_EXCEPTION_FINALIZE_LINK

    -- Forward exception event to parent exception handler
    local function forward_exception(original_node_id)
        if ns.parent_exception_node then
            local eq = require("cfl_event_queue")
            eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
                ns.parent_exception_node, CFL_EVENT_TYPE_NULL,
                CFL_RAISE_EXCEPTION_EVENT, original_node_id)
        end
    end

    -- Transition from current stage to RECOVERY
    local function transition_to_recovery()
        if ns.catch_links and ns.catch_links[CFL_EXCEPTION_MAIN_LINK] then
            get_engine().terminate_node_tree(handle, ns.catch_links[CFL_EXCEPTION_MAIN_LINK])
        end
        ns.exception_stage = CFL_EXCEPTION_RECOVERY_LINK
        if ns.catch_links and ns.catch_links[CFL_EXCEPTION_RECOVERY_LINK] then
            get_engine().enable_node(handle, ns.catch_links[CFL_EXCEPTION_RECOVERY_LINK])
        end
    end

    -- ---- Handle exception raise ----
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        local original_node_id = event_data
        ns.original_node_id = original_node_id
        ns.exception_type = defs.CFL_EXCEPTION_RAISED

        -- Log the exception
        if ns.logging_fn and ns.logging_fn ~= 0 then
            local log_fn = handle.flash_handle.one_shot_functions[ns.logging_fn]
            if log_fn then log_fn(handle, node_idx) end
        end

        -- Check boolean filter: true = not handled, forward to parent
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        if bool_fn(handle, node_idx, event_type, event_id, event_data) then
            forward_exception(original_node_id)
            return CFL_DISABLE
        end

        -- Handled: transition based on current stage
        if ns.exception_stage == CFL_EXCEPTION_MAIN_LINK then
            transition_to_recovery()
            return CFL_CONTINUE
        end

        -- Already in RECOVERY or FINALIZE — can't handle, forward up
        forward_exception(original_node_id)
        return CFL_DISABLE
    end

    -- ---- Handle step count event ----
    if event_id == defs.CFL_SET_EXCEPTION_STEP_EVENT then
        ns.step_count = event_data or 0
        return CFL_CONTINUE
    end

    -- ---- Handle heartbeat control events ----
    if event_id == defs.CFL_TURN_HEARTBEAT_ON_EVENT then
        ns.heartbeat_enabled  = true
        ns.heartbeat_time_out = event_data or 0
        ns.heartbeat_count    = 0
        return CFL_CONTINUE
    end

    if event_id == defs.CFL_TURN_HEARTBEAT_OFF_EVENT then
        ns.heartbeat_enabled = false
        return CFL_CONTINUE
    end

    if event_id == defs.CFL_HEARTBEAT_EVENT then
        ns.heartbeat_count = 0
        return CFL_CONTINUE
    end

    -- ---- Timer tick: heartbeat timeout check ----
    if event_id == CFL_TIMER_EVENT then
        if ns.heartbeat_enabled then
            ns.heartbeat_count = ns.heartbeat_count + 1
            if ns.heartbeat_count >= ns.heartbeat_time_out then
                ns.heartbeat_enabled = false
                ns.original_node_id = node_idx
                ns.exception_type = defs.CFL_EXCEPTION_HEARTBEAT_TIMEOUT

                if ns.logging_fn and ns.logging_fn ~= 0 then
                    local log_fn = handle.flash_handle.one_shot_functions[ns.logging_fn]
                    if log_fn then log_fn(handle, node_idx) end
                end

                if ns.exception_stage == CFL_EXCEPTION_MAIN_LINK then
                    transition_to_recovery()
                    return CFL_CONTINUE
                end

                -- Already past MAIN — forward to parent and disable
                forward_exception(node_idx)
                return CFL_DISABLE
            end
        end
    end

    -- ---- Normal tick: check if active stage child is still enabled ----
    if not ns.catch_links then return CFL_DISABLE end
    local active_child = ns.catch_links[ns.exception_stage]
    if active_child and band(handle.flags[active_child], CT_FLAG_USER3) ~= 0 then
        return CFL_CONTINUE
    end

    -- Active stage child finished — advance to next stage
    if ns.exception_stage == CFL_EXCEPTION_MAIN_LINK then
        -- MAIN completed normally: skip RECOVERY, go to FINALIZE
        ns.exception_stage = CFL_EXCEPTION_FINALIZE_LINK
        if ns.catch_links[CFL_EXCEPTION_FINALIZE_LINK] then
            get_engine().enable_node(handle, ns.catch_links[CFL_EXCEPTION_FINALIZE_LINK])
        end
        return CFL_CONTINUE
    elseif ns.exception_stage == CFL_EXCEPTION_RECOVERY_LINK then
        -- RECOVERY completed: go to FINALIZE
        ns.exception_stage = CFL_EXCEPTION_FINALIZE_LINK
        if ns.catch_links[CFL_EXCEPTION_FINALIZE_LINK] then
            get_engine().enable_node(handle, ns.catch_links[CFL_EXCEPTION_FINALIZE_LINK])
        end
        return CFL_CONTINUE
    elseif ns.exception_stage == CFL_EXCEPTION_FINALIZE_LINK then
        -- FINALIZE completed: done
        return CFL_DISABLE
    end

    return CFL_CONTINUE
end

-- Controlled node container: structural owner, delegates to CFL_COLUMN_MAIN (no-op in C too)
M.CFL_CONTROLLED_NODE_CONTAINER_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    return M.CFL_COLUMN_MAIN(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
end

-- Controlled node (server): dormant until request event, runs children, sends response on term
M.CFL_CONTROLLED_NODE_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_CONTINUE end

    -- Match request event
    if ns.request_port and event_id == ns.request_port.event_id
       and event_type == defs.CFL_EVENT_TYPE_STREAMING_DATA then
        -- Store request data
        ns.request_data = event_data

        -- Call boolean function (user processes request data)
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        bool_fn(handle, node_idx, event_type, event_id, event_data)

        -- Enable all children (the processing pipeline)
        common.enable_children(handle, node_idx)
        return CFL_HALT
    end

    -- Handle exception: forward to client node
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        if ns.client_node_index then
            local eq = require("cfl_event_queue")
            eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
                ns.client_node_index, CFL_EVENT_TYPE_NULL,
                CFL_RAISE_EXCEPTION_EVENT, event_data)
        end
        return CFL_DISABLE
    end

    -- Normal tick: check if children still active
    local node = handle.flash_handle.nodes[node_idx]
    local link_start = node.link_start
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    local lt = handle.flash_handle.link_table

    for i = 0, link_count - 1 do
        local child_id = lt[link_start + i]
        if band(handle.flags[child_id], CT_FLAG_USER3) ~= 0 then
            return CFL_CONTINUE
        end
    end

    return CFL_DISABLE
end

-- Client controlled node: activates server, waits for response
M.CFL_CLIENT_CONTROLLED_NODE_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_CONTINUE end

    -- First tick: activate server node directly (mirrors C cfl_client_controlled_node_main)
    if not ns.node_is_active then
        local server_id = ns.server_node_id
        if not server_id then return CFL_HALT end

        -- Enable server node with initialized flag set
        -- (so engine won't re-run init one-shot — we handle it here)
        local bor = bit.bor
        handle.flags[server_id] = bor(
            band(handle.flags[server_id], bit.bnot(defs.CT_FLAG_USER_MASK)),
            defs.CT_FLAG_USER3, defs.CT_FLAG_USER2)

        -- Ensure all ancestors of server are enabled (container may have
        -- disabled itself when all children completed on a previous call)
        local nodes = handle.flash_handle.nodes
        local pid = nodes[server_id] and nodes[server_id].parent_index
        while pid and pid ~= defs.CFL_NO_PARENT do
            if band(handle.flags[pid], defs.CT_FLAG_USER3) == 0 then
                handle.flags[pid] = bor(
                    band(handle.flags[pid], bit.bnot(defs.CT_FLAG_USER_MASK)),
                    defs.CT_FLAG_USER3, defs.CT_FLAG_USER2)
            end
            pid = nodes[pid] and nodes[pid].parent_index
        end

        -- Initialize server: call init one-shot + boolean init
        local server_node = handle.flash_handle.nodes[server_id]
        if server_node then
            local init_fn = handle.flash_handle.one_shot_functions[server_node.init_function_index]
            if init_fn then init_fn(handle, server_id) end

            if server_node.aux_function_index ~= 0 then
                local aux_fn = handle.flash_handle.boolean_functions[server_node.aux_function_index]
                if aux_fn then
                    aux_fn(handle, server_id, CFL_EVENT_TYPE_NULL, CFL_INIT_EVENT, nil)
                end
            end
        end

        -- Store client node on server state for response routing
        local server_ns = common.get_node_state(handle, server_id)
        if server_ns then
            server_ns.client_node_index = node_idx
        end

        -- Send request event to server (high priority, processed immediately)
        if ns.request_port then
            local eq = require("cfl_event_queue")
            eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
                server_id, defs.CFL_EVENT_TYPE_STREAMING_DATA,
                ns.request_port.event_id, ns.request_packet)
        end

        ns.node_is_active = true
        return CFL_HALT
    end

    -- Wait for response event
    if ns.response_port and event_id == ns.response_port.event_id then
        -- Accept both FFI cdata and Lua table responses
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        if not bool_fn(handle, node_idx, event_type, event_id, event_data) then
            return CFL_TERMINATE
        end
        return CFL_DISABLE
    end

    -- Handle exception forwarded from server
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        -- Forward to parent exception handler
        local parent_exc = common.find_parent_exception_node(handle, node_idx)
        if parent_exc then
            local eq = require("cfl_event_queue")
            eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
                parent_exc, CFL_EVENT_TYPE_NULL,
                CFL_RAISE_EXCEPTION_EVENT, event_data)
        end
        return CFL_DISABLE
    end

    return CFL_HALT
end

-- Streaming sink: match inport -> call boolean (user processes packet)
M.CFL_STREAMING_SINK_PACKET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.inport then return CFL_CONTINUE end

    if streaming.event_matches(event_type, event_id, event_data, ns.inport) then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        bool_fn(handle, node_idx, event_type, event_id, event_data)
    end

    return CFL_CONTINUE
end

-- Streaming tap: match inport -> call boolean (observation, non-blocking)
M.CFL_STREAMING_TAP_PACKET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.inport then return CFL_CONTINUE end

    if streaming.event_matches(event_type, event_id, event_data, ns.inport) then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        bool_fn(handle, node_idx, event_type, event_id, event_data)
    end

    return CFL_CONTINUE
end

-- Streaming filter: match inport -> call boolean -> false = CFL_HALT
M.CFL_STREAMING_FILTER_PACKET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.inport then return CFL_CONTINUE end

    if streaming.event_matches(event_type, event_id, event_data, ns.inport) then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        if not bool_fn(handle, node_idx, event_type, event_id, event_data) then
            return CFL_HALT
        end
    end

    return CFL_CONTINUE
end

-- Streaming transform: match inport -> call boolean (user transforms + emits on outport)
M.CFL_STREAMING_TRANSFORM_PACKET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.inport then return CFL_CONTINUE end

    if streaming.event_matches(event_type, event_id, event_data, ns.inport) then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        bool_fn(handle, node_idx, event_type, event_id, event_data)
    end

    return CFL_CONTINUE
end

-- Streaming collect: accumulate packets from multiple inports, emit when full
M.CFL_STREAMING_COLLECT_PACKETS = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.inports then return CFL_CONTINUE end

    -- Don't accept while container is pending consumption
    if ns.container_pending then return CFL_CONTINUE end

    for i, inport in ipairs(ns.inports) do
        if streaming.event_matches(event_type, event_id, event_data, inport) then
            local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
            -- Boolean receives port index as event_type (matches C convention)
            local accept = bool_fn(handle, node_idx, i, event_id, event_data)

            if accept and ns.container_count < ns.container_capacity then
                ns.container_count = ns.container_count + 1
                ns.container_packets[ns.container_count] = event_data
                ns.container_port_indices[ns.container_count] = i

                if ns.container_count >= ns.container_capacity then
                    ns.container_pending = true
                    -- Emit collected packets event
                    local container = {
                        packets      = ns.container_packets,
                        port_indices = ns.container_port_indices,
                        count        = ns.container_count,
                        capacity     = ns.container_capacity,
                    }
                    streaming.send_collected_event(handle,
                        ns.output_event_column_id,
                        ns.output_event_id, container)
                end
            end
            break
        end
    end

    return CFL_CONTINUE
end

-- Streaming sink collected: match collected event -> call boolean -> reset container
M.CFL_STREAMING_SINK_COLLECTED_PACKETS = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_CONTINUE end

    if streaming.collected_event_matches(event_type, event_id, ns.event_id) then
        local bool_fn = handle.flash_handle.boolean_functions[bool_fn_idx]
        bool_fn(handle, node_idx, event_type, event_id, event_data)

        -- Reset the source container after user processes it
        if type(event_data) == "table" then
            -- Find the collect node and reset its container
            -- event_data is the container table passed by collect node
            if event_data.packets then
                for k = 1, (event_data.capacity or 0) do
                    event_data.packets[k] = nil
                    if event_data.port_indices then
                        event_data.port_indices[k] = nil
                    end
                end
            end
            -- Signal back that container is consumed
            -- The collect node checks container_pending on next event
        end
    end

    return CFL_CONTINUE
end


-- ============================================================================
-- BOOLEAN FUNCTIONS
-- ============================================================================

-- Always false
M.CFL_BOOL_FALSE = function(handle, node_idx, event_type, event_id, event_data)
    return false
end

M.CFL_COLUMN_NULL        = M.CFL_BOOL_FALSE
M.CFL_GATE_NODE_NULL     = M.CFL_BOOL_FALSE
M.CFL_STATE_MACHINE_NULL = M.CFL_BOOL_FALSE

-- Verify timeout boolean
M.CFL_VERIFY_TIME_OUT = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    if event_id == CFL_INIT_EVENT then
        local nd = common.get_node_data_field(handle, node_idx, "fn_data.time_out")
        ns.timestamp_timeout = handle.timer.timestamp + (tonumber(nd) or 0)
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if event_id == CFL_TIMER_EVENT then
        if handle.timer.timestamp >= (ns.timestamp_timeout or 0) then
            return false
        end
    end
    return true
end

-- Wait for event boolean
M.CFL_WAIT_FOR_EVENT = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    if event_id == CFL_INIT_EVENT then
        ns.wait_event_id = common.get_node_data_field(handle, node_idx, "wait_fn_data.event_id")
        ns.wait_event_count = common.get_node_data_field(handle, node_idx, "wait_fn_data.event_count") or 1
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end

    if event_id == ns.wait_event_id then
        ns.wait_event_count = ns.wait_event_count - 1
        if ns.wait_event_count <= 0 then return true end
    end
    return false
end

-- State machine event sync boolean
M.CFL_SM_EVENT_SYNC = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end

    local ns = common.get_node_state(handle, node_idx)
    if not ns or not ns.sync_event_id_valid then return false end

    if event_id == ns.sync_event_id then
        ns.sync_event_id_valid = false
    end
    return true
end

-- Verify bitmask boolean
M.CFL_VERIFY_BITMASK = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    if event_id == CFL_INIT_EVENT then
        ns.required_bitmask = common.get_node_data_field(handle, node_idx, "fn_data.required_bitmask") or 0
        ns.excluded_bitmask = common.get_node_data_field(handle, node_idx, "fn_data.excluded_bitmask") or 0
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if event_id ~= CFL_TIMER_EVENT then return true end

    local req = band(ns.required_bitmask, handle.bitmask or 0) == ns.required_bitmask
    local exc = band(ns.excluded_bitmask, handle.bitmask or 0) == 0
    return req and exc
end

-- Wait for bitmask boolean
M.CFL_WAIT_FOR_BITMASK = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    if event_id == CFL_INIT_EVENT then
        ns.required_bitmask = common.get_node_data_field(handle, node_idx, "wait_fn_data.required_bitmask") or 0
        ns.excluded_bitmask = common.get_node_data_field(handle, node_idx, "wait_fn_data.excluded_bitmask") or 0
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if event_id ~= CFL_TIMER_EVENT then return false end

    local req = band(ns.required_bitmask, handle.bitmask or 0) == ns.required_bitmask
    local exc = band(ns.excluded_bitmask, handle.bitmask or 0) == 0
    return req and exc
end

-- Verify tests active boolean
M.CFL_VERIFY_TESTS_ACTIVE = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end
    -- Returns true while tests are still running (any KB active)
    return handle.active_test_count and handle.active_test_count > 0
end

-- Wait for tests complete boolean
M.CFL_WAIT_FOR_TESTS_COMPLETE = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end
    return handle.active_test_count and handle.active_test_count <= 0
end

-- Streaming verify packet: match inport -> delegate to user boolean
M.CFL_STREAMING_VERIFY_PACKET = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    -- On init: set up verify packet state (inport + user function)
    if event_id == CFL_INIT_EVENT then
        if not ns._verify_packet then
            local inport = streaming.decode_port(handle, node_idx, "fn_data.inport")
            local user_fn_name = common.get_node_data_field(handle, node_idx, "fn_data.user_aux_function")
            local user_fn_idx = 0
            if user_fn_name and user_fn_name ~= "" and user_fn_name ~= "CFL_NULL" then
                user_fn_idx = handle.flash_handle._bool_fn_idx[user_fn_name] or 0
            end
            ns._verify_packet = {
                inport = inport,
                user_fn_idx = user_fn_idx,
            }
        end
        -- Forward init to user function
        local vp = ns._verify_packet
        if vp.user_fn_idx ~= 0 then
            local user_fn = handle.flash_handle.boolean_functions[vp.user_fn_idx]
            return user_fn(handle, node_idx, event_type, event_id, event_data)
        end
        return false
    end

    local vp = ns._verify_packet
    if not vp then return false end

    if event_id == CFL_TERMINATE_EVENT then
        if vp.user_fn_idx ~= 0 then
            local user_fn = handle.flash_handle.boolean_functions[vp.user_fn_idx]
            return user_fn(handle, node_idx, event_type, event_id, event_data)
        end
        return false
    end

    -- Non-streaming events pass through (return true = keep running)
    if event_type ~= defs.CFL_EVENT_TYPE_STREAMING_DATA then
        return true
    end

    -- Check if event matches inport
    if not streaming.event_matches(event_type, event_id, event_data, vp.inport) then
        return true
    end

    -- Delegate to user verification function
    if vp.user_fn_idx ~= 0 then
        local user_fn = handle.flash_handle.boolean_functions[vp.user_fn_idx]
        return user_fn(handle, node_idx, event_type, event_id, event_data)
    end

    return false
end


-- ============================================================================
-- ONE-SHOT FUNCTIONS — Init/Term for all node types
-- ============================================================================

-- Null one-shot: no-op
M.CFL_NULL = M.CFL_NULL  -- already defined as main, also works as oneshot key (won't collide — CFL_NULL used for main)

-- Generic no-op one-shot (used for simple init/term)
local function noop_oneshot(handle, node_idx) end

-- ---------- Column ----------
M.CFL_COLUMN_INIT = function(handle, node_idx)
    common.alloc_node_state(handle, node_idx)
    -- Enable all children (mirrors C cfl_column_init_one_shot_fn)
    common.enable_children(handle, node_idx)
end

M.CFL_COLUMN_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Gate node ----------
M.CFL_GATE_NODE_INIT = M.CFL_COLUMN_INIT
M.CFL_GATE_NODE_TERM = M.CFL_COLUMN_TERM

-- ---------- Fork ----------
M.CFL_FORK_INIT = M.CFL_COLUMN_INIT
M.CFL_FORK_TERM = M.CFL_COLUMN_TERM

-- ---------- Local arena (no-op in LuaJIT) ----------
M.CFL_LOCAL_ARENA_INIT = M.CFL_COLUMN_INIT
M.CFL_LOCAL_ARENA_TERM = M.CFL_COLUMN_TERM

-- ---------- Verify ----------
M.CFL_VERIFY_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local err_name = common.get_node_data_field(handle, node_idx, "error_function")
    ns.error_function = resolve_oneshot_idx(handle, err_name)
    ns.reset_flag = common.get_node_data_field(handle, node_idx, "reset_flag") or false
end

M.CFL_VERIFY_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Wait ----------
M.CFL_WAIT_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.timeout = common.get_node_data_field(handle, node_idx, "timeout") or 0
    ns.time_out_event = common.get_node_data_field(handle, node_idx, "time_out_event") or CFL_TIMER_EVENT
    local err_name = common.get_node_data_field(handle, node_idx, "error_function")
    ns.error_function = resolve_oneshot_idx(handle, err_name)
    ns.reset_flag = common.get_node_data_field(handle, node_idx, "reset_flag") or false
    ns.event_count = 0
end

M.CFL_WAIT_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Wait time ----------
M.CFL_WAIT_TIME_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local delay = common.get_node_data_field(handle, node_idx, "time_delay") or 0
    ns.wait_time_out = handle.timer.timestamp + delay
end

-- ---------- For loop ----------
M.CFL_FOR_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.number_of_iterations = common.get_node_data_field(handle, node_idx, "number_of_iterations") or 1
    ns.current_iteration = 0
    -- Enable first child
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    if link_count > 0 then
        get_engine().enable_node(handle, lt[node.link_start])
    end
end

M.CFL_FOR_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- While loop ----------
M.CFL_WHILE_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.current_iteration = 0
    -- Enable first child
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    if link_count > 0 then
        get_engine().enable_node(handle, lt[node.link_start])
    end
end

M.CFL_WHILE_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Watchdog ----------
M.CFL_WATCH_DOG_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.wd_time_count = common.get_node_data_field(handle, node_idx, "wd_time_count") or 100
    local wd_fn_name = common.get_node_data_field(handle, node_idx, "wd_fn")
    ns.wd_fn_id = resolve_oneshot_idx(handle, wd_fn_name)
    ns.wd_reset = common.get_node_data_field(handle, node_idx, "wd_reset") or false
    ns.wd_enabled = true
    ns.current_count = 0
end

M.CFL_WATCH_DOG_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- State machine ----------
M.CFL_STATE_MACHINE_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local initial = common.get_node_data_field(handle, node_idx, "column_data.initial_state_number") or 0
    ns.current_state = initial

    -- Enable initial state child
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    ns.state_count = link_count

    if link_count > 0 and initial < link_count then
        local child_id = lt[node.link_start + initial]
        get_engine().enable_node(handle, child_id)
    end
end

M.CFL_STATE_MACHINE_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Join ----------
M.CFL_JOIN_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local target_ltree = common.get_node_data_field(handle, node_idx, "parent_node_name")
    if target_ltree then
        ns.target_node = handle.flash_handle.ltree_to_index[target_ltree]
    end
end

M.CFL_JOIN_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

M.CFL_JOIN_SEQUENCE_ELEMENT_INIT = M.CFL_JOIN_INIT
M.CFL_JOIN_SEQUENCE_ELEMENT_TERM = M.CFL_JOIN_TERM

-- ---------- Sequence pass/fail/start ----------
M.CFL_SEQUENCE_PASS_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.current_sequence_index = 0
    ns.sequence_type = "pass"
    ns.final_status = nil
    ns.sequence_results = {}
    local fin_name = common.get_node_data_field(handle, node_idx, "column_data.finalize_function")
    ns.finalize_fn = resolve_oneshot_idx(handle, fin_name)
    -- Enable first child
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    if link_count > 0 then
        get_engine().enable_node(handle, lt[node.link_start])
    end
end

M.CFL_SEQUENCE_PASS_TERM = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    if ns and ns.finalize_fn and ns.finalize_fn ~= 0 then
        local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
        if fin then fin(handle, node_idx) end
    end
    handle.node_state[node_idx] = nil
end

M.CFL_SEQUENCE_FAIL_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.current_sequence_index = 0
    ns.sequence_type = "fail"
    ns.final_status = nil
    ns.sequence_results = {}
    local fin_name = common.get_node_data_field(handle, node_idx, "column_data.finalize_function")
    ns.finalize_fn = resolve_oneshot_idx(handle, fin_name)
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    if link_count > 0 then
        get_engine().enable_node(handle, lt[node.link_start])
    end
end

M.CFL_SEQUENCE_FAIL_TERM = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    if ns and ns.finalize_fn and ns.finalize_fn ~= 0 then
        local fin = handle.flash_handle.one_shot_functions[ns.finalize_fn]
        if fin then fin(handle, node_idx) end
    end
    handle.node_state[node_idx] = nil
end

M.CFL_SEQUENCE_START_INIT = M.CFL_COLUMN_INIT
M.CFL_SEQUENCE_START_TERM = M.CFL_COLUMN_TERM

-- ---------- DF mask ----------
M.CFL_DF_MASK_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.required_bitmask = common.get_node_data_field(handle, node_idx, "column_data.required_bitmask") or 0
    ns.excluded_bitmask = common.get_node_data_field(handle, node_idx, "column_data.excluded_bitmask") or 0
    ns.node_state = false
end

M.CFL_DF_MASK_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Event logger ----------
M.CFL_EVENT_LOGGER_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.event_ids = common.get_node_data_field(handle, node_idx, "events") or {}
    ns.message = common.get_node_data_field(handle, node_idx, "message") or ""
end

M.CFL_EVENT_LOGGER_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Supervisor ----------
M.CFL_SUPERVISOR_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.restart_enabled = common.get_node_data_field(handle, node_idx, "column_data.supervisor_data.restart_enabled") or false
    ns.reset_limited_enabled = common.get_node_data_field(handle, node_idx, "column_data.supervisor_data.reset_limited_enabled") or false
    ns.max_reset_number = common.get_node_data_field(handle, node_idx, "column_data.supervisor_data.max_reset_number") or 3
    ns.reset_window = common.get_node_data_field(handle, node_idx, "column_data.supervisor_data.reset_window") or 100
    ns.termination_type = common.get_node_data_field(handle, node_idx, "column_data.supervisor_data.termination_type") or 0
    ns.reset_count = 0
    local fin_name = common.get_node_data_field(handle, node_idx, "column_data.supervisor_data.finalize_function")
    ns.finalize_fn = resolve_oneshot_idx(handle, fin_name)
    -- Enable all supervised children
    common.enable_children(handle, node_idx)
end

M.CFL_SUPERVISOR_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Recovery ----------
M.CFL_RECOVERY_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.current_step = 0
    ns.max_steps = common.get_node_data_field(handle, node_idx, "column_data.max_steps") or 99
    -- Enable first child
    local node = handle.flash_handle.nodes[node_idx]
    local lt = handle.flash_handle.link_table
    local link_count = band(node.link_count, CFL_LINK_COUNT_MASK)
    if link_count > 0 then
        get_engine().enable_node(handle, lt[node.link_start])
    end
end

M.CFL_RECOVERY_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Exception catch-all ----------
M.CFL_CATCH_ALL_EXCEPTION_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.aux_data = common.get_node_data_field(handle, node_idx, "column_data.aux_data")
    local log_name = common.get_node_data_field(handle, node_idx, "column_data.logging_function")
    ns.logging_fn = resolve_oneshot_idx(handle, log_name)
    -- Enable all children
    common.enable_children(handle, node_idx)
end

M.CFL_CATCH_ALL_EXCEPTION_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Exception catch (filtered) ----------
M.CFL_EXCEPTION_CATCH_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local log_name = common.get_node_data_field(handle, node_idx, "column_data.logging_function")
    ns.logging_fn = resolve_oneshot_idx(handle, log_name)

    -- Heartbeat state
    ns.heartbeat_enabled  = false
    ns.heartbeat_time_out = 0
    ns.heartbeat_count    = 0

    -- 3-stage pipeline: MAIN -> RECOVERY -> FINALIZE
    ns.exception_stage = defs.CFL_EXCEPTION_MAIN_LINK
    ns.step_count      = 0

    -- Find parent exception node for forwarding
    ns.parent_exception_node = common.find_parent_exception_node(handle, node_idx)

    -- Resolve exception_catch_links (original indices -> final indices)
    -- catch_links[1]=MAIN, [2]=RECOVERY, [3]=FINALIZE
    local raw_links = common.get_node_data_field(handle, node_idx, "column_data.exception_catch_links")
    if raw_links then
        ns.catch_links = {}
        local o2f = handle.flash_handle.original_to_final
        for _, orig_idx in ipairs(raw_links) do
            local final_idx = o2f and o2f[orig_idx]
            if final_idx then
                ns.catch_links[#ns.catch_links + 1] = final_idx
            end
        end
    end

    -- Enable MAIN link child
    if ns.catch_links and ns.catch_links[defs.CFL_EXCEPTION_MAIN_LINK] then
        get_engine().enable_node(handle, ns.catch_links[defs.CFL_EXCEPTION_MAIN_LINK])
    end
end

M.CFL_EXCEPTION_CATCH_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Controlled node container ----------
M.CFL_CONTROLLED_NODE_CONTAINER_INIT = M.CFL_COLUMN_INIT
M.CFL_CONTROLLED_NODE_CONTAINER_TERM = M.CFL_COLUMN_TERM

-- ---------- Controlled node (server) ----------
M.CFL_CONTROLLED_NODE_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    -- Decode request/response ports from column_data
    ns.request_port  = streaming.decode_port(handle, node_idx, "column_data.request_port")
    ns.response_port = streaming.decode_port(handle, node_idx, "column_data.response_port")
    ns.client_node_index = nil
end

M.CFL_CONTROLLED_NODE_TERM = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    if ns and ns.response_port and ns.client_node_index then
        -- Send response back to client (high priority so it's processed next)
        local response = ns.response_packet or { success = true }
        local eq = require("cfl_event_queue")
        eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
            ns.client_node_index, defs.CFL_EVENT_TYPE_STREAMING_DATA,
            ns.response_port.event_id, response)
    end
    handle.node_state[node_idx] = nil
end

-- ---------- Client controlled node ----------
M.CFL_CLIENT_CONTROLLED_NODE_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.request_port  = streaming.decode_port(handle, node_idx, "request_port")
    ns.response_port = streaming.decode_port(handle, node_idx, "response_port")
    ns.node_is_active = false

    -- Resolve server node index (original -> final)
    local server_orig = common.get_node_data_field(handle, node_idx, "server_node_index")
    if server_orig then
        local o2f = handle.flash_handle.original_to_final
        ns.server_node_id = o2f and o2f[server_orig]
    end

    -- Store aux_data and api_name for user code access
    local nd = common.get_node_data(handle, node_idx)
    ns.aux_data = nd and nd.aux_data
    ns.api_name = nd and nd.api_name

    -- Create request packet as Lua table (user boolean fills details on INIT)
    ns.request_packet = { aux_data = ns.aux_data }
end

M.CFL_CLIENT_CONTROLLED_NODE_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Streaming inport nodes (sink, tap, filter) ----------
local function streaming_inport_init(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.inport = streaming.decode_port(handle, node_idx, "inport")
end

local function streaming_inport_term(handle, node_idx)
    handle.node_state[node_idx] = nil
end

M.CFL_STREAMING_SINK_PACKET_INIT   = streaming_inport_init
M.CFL_STREAMING_SINK_PACKET_TERM   = streaming_inport_term
M.CFL_STREAMING_TAP_PACKET_INIT    = streaming_inport_init
M.CFL_STREAMING_TAP_PACKET_TERM    = streaming_inport_term
M.CFL_STREAMING_FILTER_PACKET_INIT = streaming_inport_init
M.CFL_STREAMING_FILTER_PACKET_TERM = streaming_inport_term

-- ---------- Streaming transform (inport + outport) ----------
M.CFL_STREAMING_TRANSFORM_PACKET_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.inport  = streaming.decode_port(handle, node_idx, "inport")
    ns.outport = streaming.decode_port(handle, node_idx, "outport")
    ns.output_event_column_id = common.get_node_data_field(handle, node_idx, "output_event_column_id")
end

M.CFL_STREAMING_TRANSFORM_PACKET_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Streaming collect (multiple inports + container) ----------
M.CFL_STREAMING_COLLECT_PACKETS_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)

    -- Decode array of inports
    local raw_inports = common.get_node_data_field(handle, node_idx, "inports") or {}
    ns.inports = {}
    for i, ip in ipairs(raw_inports) do
        ns.inports[i] = {
            schema_hash = ip.schema_hash or 0,
            handler_id  = ip.handler_id or 0,
            event_id    = ip.event_id or 0,
        }
    end

    -- Output event config
    ns.output_event_id        = common.get_node_data_field(handle, node_idx, "output_event_id") or 0
    ns.output_event_column_id = common.get_node_data_field(handle, node_idx, "output_event_column_id") or 0

    -- Container
    local expected = common.get_node_data_field(handle, node_idx, "aux_data.expected_count") or #raw_inports
    ns.container_capacity     = expected
    ns.container_count        = 0
    ns.container_pending      = false
    ns.container_packets      = {}
    ns.container_port_indices = {}
end

M.CFL_STREAMING_COLLECT_PACKETS_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end

-- ---------- Streaming sink collected packets ----------
M.CFL_STREAMING_SINK_COLLECTED_PACKETS_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    ns.event_id = common.get_node_data_field(handle, node_idx, "event_id") or 0
end

M.CFL_STREAMING_SINK_COLLECTED_PACKETS_TERM = function(handle, node_idx)
    handle.node_state[node_idx] = nil
end


-- ============================================================================
-- ONE-SHOT FUNCTIONS — Action one-shots
-- ============================================================================

-- Change state (queue state machine event)
M.CFL_CHANGE_STATE = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local sm = require("cfl_state_machine")

    -- DSL writes numeric sm node id in nd.node_id; legacy paths used
    -- nd.sm_node_name / nd.parent_node_name (ltree string) and we
    -- resolve via ltree_to_index as a fallback.
    local sm_node_id = nd.node_id
    if not sm_node_id then
        local sm_ltree = nd.sm_node_name or nd.parent_node_name
        if sm_ltree then
            sm_node_id = handle.flash_handle.ltree_to_index[sm_ltree]
        end
    end
    if not sm_node_id then return end

    -- new_state may be a string (DSL) or integer index; state machine
    -- main expects integer index into child link table.
    local new_state = nd.new_state
    if type(new_state) == "string" then
        local sm_node = handle.flash_handle.nodes[sm_node_id]
        local sm_data = sm_node and common.get_node_data(handle, sm_node_id)
        local state_names = sm_data and
            (sm_data.column_data and sm_data.column_data.state_names
             or sm_data.state_names)
        if state_names then
            for i, name in ipairs(state_names) do
                if name == new_state then
                    new_state = i - 1   -- 0-based
                    break
                end
            end
        end
        if type(new_state) == "string" then return end
    end
    new_state = new_state or 0

    sm.change_state(handle, node_idx, sm_node_id, new_state, nd.sync_event_id)
end

-- Reset state machine
M.CFL_RESET_STATE_MACHINE = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local sm = require("cfl_state_machine")

    local sm_ltree = nd.sm_node_name or nd.parent_node_name
    local sm_node_id
    if sm_ltree then
        sm_node_id = handle.flash_handle.ltree_to_index[sm_ltree]
    end
    if sm_node_id then
        sm.reset_state_machine(handle, node_idx, sm_node_id)
    end
end

-- Terminate state machine
M.CFL_TERMINATE_STATE_MACHINE = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local sm = require("cfl_state_machine")

    local sm_ltree = nd.sm_node_name or nd.parent_node_name
    local sm_node_id
    if sm_ltree then
        sm_node_id = handle.flash_handle.ltree_to_index[sm_ltree]
    end
    if sm_node_id then
        sm.terminate_state_machine(handle, node_idx, sm_node_id)
    end
end

-- Bitmask operations
M.CFL_SET_BITMASK = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local mask = nd.bitmask_value or 0
    handle.shaddow_bitmask = bor(handle.bitmask or 0, mask)
end

M.CFL_CLEAR_BITMASK = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local mask = nd.bitmask_value or 0
    handle.shaddow_bitmask = band(handle.bitmask or 0, bit.bnot(mask))
end

-- Log message (stderr so it lands in host process log)
M.CFL_LOG_MESSAGE = function(handle, node_idx)
    local msg = common.get_node_data_field(handle, node_idx, "message")
    local tick = handle.tick_count or 0
    io.stderr:write(string.format(
        "[chain_tree] tick=%d node=%d: %s\n", tick, node_idx, tostring(msg)))
    io.stderr:flush()
end

-- Send named event
M.CFL_SEND_NAMED_EVENT = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local eq = require("cfl_event_queue")
    local event_name = nd.event_name
    local event_id = event_name and handle.flash_handle.event_strings[event_name]
    if event_id then
        local target = nd.target_node_id or handle.node_start_index or 0
        eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            target, CFL_EVENT_TYPE_NULL, event_id, nil)
    end
end

-- Raise exception
M.CFL_RAISE_EXCEPTION = function(handle, node_idx)
    local eq = require("cfl_event_queue")
    local nd = common.get_node_data(handle, node_idx)
    local target = handle.node_start_index or 0
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_HIGH,
        target, CFL_EVENT_TYPE_NULL, CFL_RAISE_EXCEPTION_EVENT, node_idx)
end

-- Set exception step
M.CFL_SET_EXCEPTION_STEP = function(handle, node_idx)
    -- Store step info in node state for recovery main to use
    local ns = common.alloc_node_state(handle, node_idx)
    ns.exception_step = common.get_node_data_field(handle, node_idx, "exception_step") or 0
end

-- Enable/disable nodes
M.CFL_ENABLE_NODES = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd or not nd.node_list then return end
    local o2f = handle.flash_handle.original_to_final
    for _, orig_idx in ipairs(nd.node_list) do
        local final_idx = o2f and o2f[orig_idx]
        if final_idx then
            get_engine().enable_node(handle, final_idx)
        end
    end
end

M.CFL_DISABLE_NODES = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd or not nd.node_list then return end
    local o2f = handle.flash_handle.original_to_final
    for _, orig_idx in ipairs(nd.node_list) do
        local final_idx = o2f and o2f[orig_idx]
        if final_idx then
            get_engine().terminate_node_tree(handle, final_idx)
        end
    end
end

-- Heartbeat operations — send events to parent exception catch node
M.CFL_HEARTBEAT_EVENT = function(handle, node_idx)
    local target = common.find_parent_exception_node(handle, node_idx)
    if not target then return end
    local eq = require("cfl_event_queue")
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
        target, CFL_EVENT_TYPE_NULL, defs.CFL_HEARTBEAT_EVENT, nil)
end

M.CFL_TURN_HEARTBEAT_ON = function(handle, node_idx)
    local target = common.find_parent_exception_node(handle, node_idx)
    if not target then return end
    local nd = common.get_node_data(handle, node_idx)
    local time_out = nd and nd.time_out or 0
    local eq = require("cfl_event_queue")
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
        target, CFL_EVENT_TYPE_NULL, defs.CFL_TURN_HEARTBEAT_ON_EVENT, time_out)
end

M.CFL_TURN_HEARTBEAT_OFF = function(handle, node_idx)
    local target = common.find_parent_exception_node(handle, node_idx)
    if not target then return end
    local eq = require("cfl_event_queue")
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
        target, CFL_EVENT_TYPE_NULL, defs.CFL_TURN_HEARTBEAT_OFF_EVENT, nil)
end

-- Watchdog control
M.CFL_PAT_WATCH_DOG = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local wd_ltree = nd.wd_node_name
    local wd_node_id
    if wd_ltree then
        wd_node_id = handle.flash_handle.ltree_to_index[wd_ltree]
    end
    if wd_node_id then
        local ns = common.get_node_state(handle, wd_node_id)
        if ns then ns.current_count = 0 end
    end
end

M.CFL_ENABLE_WATCH_DOG = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local wd_ltree = nd.wd_node_name
    local wd_node_id
    if wd_ltree then
        wd_node_id = handle.flash_handle.ltree_to_index[wd_ltree]
    end
    if wd_node_id then
        local ns = common.get_node_state(handle, wd_node_id)
        if ns then ns.wd_enabled = true; ns.current_count = 0 end
    end
end

M.CFL_DISABLE_WATCH_DOG = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local wd_ltree = nd.wd_node_name
    local wd_node_id
    if wd_ltree then
        wd_node_id = handle.flash_handle.ltree_to_index[wd_ltree]
    end
    if wd_node_id then
        local ns = common.get_node_state(handle, wd_node_id)
        if ns then ns.wd_enabled = false end
    end
end

-- Sequence mark
M.CFL_MARK_SEQUENCE = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local parent_node = handle.flash_handle.nodes[node_idx].parent_index
    if parent_node and parent_node ~= defs.CFL_NO_PARENT then
        local ns = common.get_node_state(handle, parent_node)
        if ns and ns.sequence_results then
            ns.sequence_results[ns.current_sequence_index] = nd.mark_value
        end
    end
end

-- Supervisor failure init mark
M.CFL_MARK_SUPERVISOR_NODE_FAILURE_INIT = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local parent_node = handle.flash_handle.nodes[node_idx].parent_index
    if parent_node and parent_node ~= defs.CFL_NO_PARENT then
        local ns = common.get_node_state(handle, parent_node)
        if ns then
            ns.failed_link_index = nd.link_index or 0
        end
    end
end

-- Start/stop tests
M.CFL_START_STOP_TESTS = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    if nd.action == "start" then
        handle.tests_running = true
    else
        handle.tests_running = false
    end
end

return M
