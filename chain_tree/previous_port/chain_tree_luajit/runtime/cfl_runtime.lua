-- ============================================================================
-- cfl_runtime.lua
-- ChainTree LuaJIT Runtime — top-level lifecycle: create, reset, run, destroy
-- Mirrors cfl_runtime.c
--
-- API:
--   local cfl = require("cfl_runtime")
--   local handle = cfl.create(params, flash_handle)
--   cfl.reset(handle)
--   cfl.add_test(handle, kb_index)   -- 0-based KB index
--   local ok = cfl.run(handle)
-- ============================================================================

local M = {}

local bit  = require("bit")
local band = bit.band

local defs       = require("cfl_definitions")
local eq_mod     = require("cfl_event_queue")
local timer_mod  = require("cfl_timer")
local engine     = require("cfl_engine")
local blackboard = require("cfl_blackboard")

-- ============================================================================
-- create(params, flash_handle) -> handle
--
-- params = {
--   delta_time           = 0.1,        -- seconds per tick
--   eq_high              = 8,          -- high-priority queue size
--   eq_low               = 64,         -- low-priority queue size
--   max_ticks            = nil,        -- optional: stop after N ticks (nil = run until done)
-- }
-- ============================================================================
function M.create(params, flash_handle)
    params = params or {}

    local handle = {
        flash_handle = flash_handle,

        -- Event queue
        event_queue = eq_mod.create(params.eq_high or 8, params.eq_low or 64),

        -- Timer
        timer = timer_mod.create(params.delta_time or 0.1),
        delta_time = params.delta_time or 0.1,

        -- Node flags (0-based, one byte per node as integer)
        flags = {},

        -- Backup flags (for nested walker contexts)
        backup_flags = {},

        -- Per-node mutable state (replaces C arena allocator)
        node_state = {},

        -- Execution state
        cfl_engine_flag = true,
        cfl_node_execution_count = 0,
        node_start_index = 0,
        kb_start_index = 0,
        kb_node_count = 0,
        kb_max_level = 0,
        current_kb_idx = 0,

        -- Bitmask
        bitmask = 0,
        shaddow_bitmask = 0,

        -- Test/KB management
        active_tests = {},   -- kb_idx -> true
        active_test_count = 0,

        -- Blackboard (filled by blackboard.init)
        blackboard = {},
        bb_defaults = {},
        const_records = {},

        -- Event data pointer (set before each event execution)
        event_data_ptr = nil,

        -- Test run control
        tests_running = true,

        -- User context
        user_handle = nil,

        -- Runtime params
        max_ticks = params.max_ticks,
    }

    -- Initialize flags
    for i = 0, flash_handle.node_count - 1 do
        handle.flags[i] = 0
        handle.backup_flags[i] = 0
        handle.node_state[i] = {}
    end

    -- Initialize engine (creates walker)
    engine.create(handle)

    -- Initialize blackboard
    blackboard.init(handle)

    return handle
end

-- ============================================================================
-- reset(handle)
-- ============================================================================
function M.reset(handle)
    -- Clear event queue
    eq_mod.clear(handle.event_queue)

    -- Reset bitmasks
    handle.bitmask = 0
    handle.shaddow_bitmask = 0

    -- Reset blackboard
    blackboard.reset(handle)

    -- Clear all flags and node state
    for i = 0, handle.flash_handle.node_count - 1 do
        handle.flags[i] = 0
        handle.node_state[i] = {}
    end

    -- Re-initialize all active tests
    for kb_idx, _ in pairs(handle.active_tests) do
        local kb = handle.flash_handle.kb_table[kb_idx + 1]  -- kb_table is 1-based
        engine.init_test(handle, kb.start_index, kb.node_count)
    end
end

-- ============================================================================
-- add_test(handle, kb_index) — 0-based KB index
-- ============================================================================
function M.add_test(handle, kb_index)
    if handle.active_tests[kb_index] then return false end

    local kb = handle.flash_handle.kb_table[kb_index + 1]  -- kb_table is 1-based
    assert(kb, "cfl_runtime.add_test: invalid kb_index " .. tostring(kb_index))

    engine.init_test(handle, kb.start_index, kb.node_count)
    handle.active_tests[kb_index] = true
    handle.active_test_count = handle.active_test_count + 1

    return true
end

-- ============================================================================
-- delete_test(handle, kb_index)
-- ============================================================================
function M.delete_test(handle, kb_index)
    if not handle.active_tests[kb_index] then return false end

    local kb = handle.flash_handle.kb_table[kb_index + 1]
    engine.terminate_all_nodes_in_kb(handle, kb.start_index, kb.node_count)

    handle.active_tests[kb_index] = nil
    handle.active_test_count = handle.active_test_count - 1

    return true
end

-- ============================================================================
-- run(handle) -> bool
-- Main event loop. Returns true on normal completion.
-- ============================================================================
function M.run(handle)
    local tick_count = 0

    while true do
        -- Check if any tests are active
        local any_active = false
        for _ in pairs(handle.active_tests) do
            any_active = true
            break
        end
        if not any_active then break end

        -- Pause: keep ticking the timer but skip event processing
        if not handle.tests_running then
            timer_mod.tick(handle.timer)
            tick_count = tick_count + 1
            handle.tick_count = tick_count
            if handle.max_ticks and tick_count >= handle.max_ticks then
                break
            end
            goto continue_loop
        end

        -- Timer tick
        local tick_result = timer_mod.tick(handle.timer)
        tick_count = tick_count + 1
        handle.tick_count = tick_count

        -- Process each active KB
        local had_active = false
        for kb_idx, _ in pairs(handle.active_tests) do
            had_active = true
            local kb = handle.flash_handle.kb_table[kb_idx + 1]

            handle.current_kb_idx = kb_idx
            handle.kb_start_index = kb.start_index
            handle.kb_node_count  = kb.node_count
            handle.kb_max_level   = kb.max_depth + 1

            -- Generate timer events
            generate_timer_events(handle, kb_idx, tick_result)
            handle.bitmask = handle.shaddow_bitmask

            -- Drain event queue
            while eq_mod.total_count(handle.event_queue) > 0 do
                local event = eq_mod.pop(handle.event_queue)

                if event.event_id == defs.CFL_TERMINATE_SYSTEM_EVENT then
                    -- Clear active tests so the host's outer
                    -- run_loop sees no work and exits cleanly.
                    -- (Without this, M.run returns but
                    -- handle.active_tests is still populated, and the
                    -- caller's any_active() check loops forever.)
                    for kb_idx, _ in pairs(handle.active_tests) do
                        local kb2 = handle.flash_handle.kb_table[kb_idx + 1]
                        if kb2 then
                            engine.terminate_all_nodes_in_kb(handle,
                                kb2.start_index, kb2.node_count)
                        end
                    end
                    handle.active_tests = {}
                    handle.active_test_count = 0
                    return true
                end

                handle.event_data_ptr = event

                if not engine.execute_event(handle) then
                    M.delete_test(handle, handle.current_kb_idx)
                    break
                end
            end

            -- Check if start node still enabled
            if handle.active_tests[kb_idx] and
               not engine.node_is_enabled(handle, kb.start_index) then
                M.delete_test(handle, kb_idx)
            end
        end

        if not had_active then break end

        -- Optional tick limit
        if handle.max_ticks and tick_count >= handle.max_ticks then
            break
        end

        ::continue_loop::
    end

    return true
end

-- ============================================================================
-- Timer event generation (mirrors cfl_generate_timer_events)
-- ============================================================================
function generate_timer_events(handle, kb_idx, tick_result)
    local kb = handle.flash_handle.kb_table[kb_idx + 1]
    local start = kb.start_index

    if not engine.node_is_enabled(handle, start) then return end

    -- Always send timer event
    eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
        start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_TIMER_EVENT, tick_result)

    local mask = tick_result.changed_mask
    if band(mask, defs.CFL_CHANGED_SECOND) ~= 0 then
        eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_SECOND_EVENT, tick_result)
    end
    if band(mask, defs.CFL_CHANGED_MINUTE) ~= 0 then
        eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_MINUTE_EVENT, tick_result)
    end
    if band(mask, defs.CFL_CHANGED_HOUR) ~= 0 then
        eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_HOUR_EVENT, tick_result)
    end
    if band(mask, defs.CFL_CHANGED_DAY) ~= 0 then
        eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_DAY_EVENT, tick_result)
    end
    if band(mask, defs.CFL_CHANGED_DOW) ~= 0 then
        eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_WEEK_EVENT, tick_result)
    end
    if band(mask, defs.CFL_CHANGED_DOY) ~= 0 then
        eq_mod.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
            start, defs.CFL_EVENT_TYPE_PTR, defs.CFL_YEAR_EVENT, tick_result)
    end
end

-- ============================================================================
-- Accessors
-- ============================================================================
function M.set_user_handle(handle, user_handle)
    handle.user_handle = user_handle
end

function M.get_user_handle(handle)
    return handle.user_handle
end

function M.test_is_active(handle, kb_index)
    return handle.active_tests[kb_index] == true
end

return M
