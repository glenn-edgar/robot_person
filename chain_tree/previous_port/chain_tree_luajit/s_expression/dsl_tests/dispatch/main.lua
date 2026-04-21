-- ============================================================================
-- main_advanced_primitive.lua
-- Lua test driver for advanced_primitive_test
-- Mirrors test_dispatch.c + advanced_primitive_test_user_functions.c
-- ============================================================================

local _here = arg[0]:match("(.-)[^/]+$") or "./"
dofile(_here .. "se_path.lua")

local se_runtime = require("se_runtime")

-- ============================================================================
-- RESULT HELPERS
-- ============================================================================

local function result_to_str(r)
    if     r == 0  then return "CONTINUE"
    elseif r == 1  then return "HALT"
    elseif r == 2  then return "TERMINATE"
    elseif r == 3  then return "RESET"
    elseif r == 4  then return "DISABLE"
    elseif r == 5  then return "SKIP_CONTINUE"
    elseif r == se_runtime.SE_FUNCTION_CONTINUE      then return "FUNCTION_CONTINUE"
    elseif r == se_runtime.SE_FUNCTION_HALT          then return "FUNCTION_HALT"
    elseif r == se_runtime.SE_FUNCTION_TERMINATE     then return "FUNCTION_TERMINATE"
    elseif r == 9                                    then return "FUNCTION_RESET"
    elseif r == se_runtime.SE_FUNCTION_DISABLE       then return "FUNCTION_DISABLE"
    elseif r == 11                                   then return "FUNCTION_SKIP_CONTINUE"
    elseif r == se_runtime.SE_PIPELINE_CONTINUE      then return "PIPELINE_CONTINUE"
    elseif r == se_runtime.SE_PIPELINE_HALT          then return "PIPELINE_HALT"
    elseif r == se_runtime.SE_PIPELINE_TERMINATE     then return "PIPELINE_TERMINATE"
    elseif r == se_runtime.SE_PIPELINE_RESET         then return "PIPELINE_RESET"
    elseif r == se_runtime.SE_PIPELINE_DISABLE       then return "PIPELINE_DISABLE"
    elseif r == se_runtime.SE_PIPELINE_SKIP_CONTINUE then return "PIPELINE_SKIP_CONTINUE"
    else return "UNKNOWN(" .. tostring(r) .. ")"
    end
end

local function result_is_terminate(r)
    return r == 2
        or r == se_runtime.SE_FUNCTION_TERMINATE
        or r == se_runtime.SE_PIPELINE_TERMINATE
end

local function result_is_complete(r)
    return r == 2
        or r == 4
        or r == se_runtime.SE_FUNCTION_TERMINATE
        or r == se_runtime.SE_FUNCTION_DISABLE
        or r == se_runtime.SE_PIPELINE_TERMINATE
        or r == se_runtime.SE_PIPELINE_DISABLE
end

-- ============================================================================
-- USER FUNCTIONS
-- Mirrors advanced_primitive_test_user_functions.c
-- ============================================================================

-- display_event_info (oneshot: fn(inst, node))
--
-- C signature:
--   void display_event_info(inst, params, param_count,
--                           event_type, event_id, event_data)
-- Skips silently on SE_EVENT_TICK.
-- event_data in C is a uint16_t byte offset into the blackboard struct
-- used to read a float. In Lua, event_data is the blackboard field name
-- string (set by se_queue_event), read via inst.blackboard[tostring(event_data)].
-- Event context is in inst.current_event_id / inst.current_event_data,
-- set by tick_once before every invocation.
local function display_event_info(inst, node)
    local event_id   = inst.current_event_id
    local event_data = inst.current_event_data

    if event_id == se_runtime.SE_EVENT_TICK then
        return  -- silent on normal ticks
    end

    print("******************[display_event_info] Displaying event info")
    print(string.format(
        "******************[display_event_info] Event type: TICK, Event ID: %d",
        event_id))
    print(string.format(
        "******************[display_event_info] Event data: %s",
        tostring(event_data)))
    local value = event_data and inst.blackboard[tostring(event_data)]
    print(string.format(
        "******************[display_event_info] Value: %s",
        tostring(value)))
end

-- ============================================================================
-- LOAD MODULE
-- ============================================================================

local ok, md = pcall(require, "dispatch_test_module")
if not ok then
    print("❌ FATAL: Could not load dispatch_test_module: " .. tostring(md))
    os.exit(1)
end

print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           S-EXPRESSION ENGINE DISPATCH TEST                    ║")
print("╚════════════════════════════════════════════════════════════════╝")
print("")
print("=== Loading module ===")
print("")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_return_codes"),
    require("se_builtins_dispatch"),
    require("se_builtins_delays"),
    require("se_builtins_spawn"),
    {
        -- Register under both names; runtime uppercases for lookup
        se_display_event_info = display_event_info,
        display_event_info    = display_event_info,
    }
)

local mod = se_runtime.new_module(md, fns)
local ok2, missing = se_runtime.validate_module(mod)
if not ok2 then
    print("❌ FATAL: Module validation failed - unregistered functions:")
    for _, m in ipairs(missing) do
        print(string.format("  [%s] %s", m.kind, m.name))
    end
    os.exit(1)
end

print("✅ Module loaded successfully")
print("   Trees:   " .. #(md.tree_order or {}))
print("   Oneshot: " .. #(md.oneshot_funcs or {}))
print("   Main:    " .. #(md.main_funcs or {}))
print("   Pred:    " .. #(md.pred_funcs or {}))

-- ============================================================================
-- TEST DISPATCH  (mirrors test_dispatch() in test_dispatch.c)
-- ============================================================================

local function test_dispatch(mod, md, tree_hash, tree_label)
    print("")
    print("╔════════════════════════════════════════╗")
    print("║    DISPATCH TEST                       ║")
    print("╚════════════════════════════════════════╝")
    print("")
    print("Testing dispatch with tick loop...")
    print("  Tree: " .. tostring(tree_label))

    -- Resolve tree name from hash; fall back to first tree
    local tree_name = mod.trees_by_hash and mod.trees_by_hash[tree_hash]
    if not tree_name then
        tree_name = md.tree_order and md.tree_order[1]
    end
    if not tree_name then
        print("  ❌ FAILED: Could not resolve tree hash 0x"
              .. string.format("%08X", tree_hash))
        return
    end

    local inst = se_runtime.new_instance(mod, tree_name)
    if not inst then
        print("  ❌ FAILED: Could not create tree instance")
        return
    end

    local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
    local max_ticks     = 500
    local tick_count    = 0
    local result        = se_runtime.SE_PIPELINE_CONTINUE

    print("  Running tick loop...")

    repeat
        result     = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)
        tick_count = tick_count + 1
        print(string.format("------------------------>    Tick %3d: result=%s",
              tick_count, result_to_str(result)))

        -- Drain event queue (mirrors C event loop)
        local event_count = se_runtime.event_count(inst)
        print(string.format("------------------------>      Event count: %d", event_count))

        while event_count > 0 do
            local e_tick_type, e_event_id, e_event_data = se_runtime.event_pop(inst)
            print(string.format(
                "-------------------------------->      Event: tick_type=%s, event_id=%d, event_data=%s",
                tostring(e_tick_type), e_event_id, tostring(e_event_data)))

            local saved_tick_type = inst.tick_type
            inst.tick_type        = e_tick_type

            local event_result = se_runtime.tick_once(inst, e_event_id, e_event_data)

            inst.tick_type = saved_tick_type

            print(string.format(
                "-------------------------------->      Event result: %s",
                result_to_str(event_result)))

            if result_is_complete(event_result) then
                result = event_result
                break
            end

            event_count = se_runtime.event_count(inst)
        end

    until result_is_complete(result) or tick_count >= max_ticks

    print("")
    print("  Total ticks: " .. tick_count)
    print("  Final result: " .. result_to_str(result))

    if result_is_terminate(result) then
        print("")
        print("  ✅ PASSED - Tree terminated normally")
    elseif tick_count >= max_ticks then
        print("")
        print("  ❌ FAILED - Max ticks exceeded without termination")
    elseif result_is_complete(result) then
        print("")
        print("  ✅ PASSED - Tree completed (disabled)")
    else
        print("")
        print("  ❌ FAILED - Unexpected result")
    end
end

-- ============================================================================
-- MAIN
-- ============================================================================

local DISPATCH_TEST_HASH = md.trees[md.tree_order[1]] and
                           md.trees[md.tree_order[1]].name_hash or 0

test_dispatch(mod, md, DISPATCH_TEST_HASH, md.tree_order[1])

print("")
print("✅ All tests completed!")
print("")

