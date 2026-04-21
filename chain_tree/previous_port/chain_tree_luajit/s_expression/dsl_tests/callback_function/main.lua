-- ============================================================================
-- main_callback_function.lua
-- Lua test driver for callback_function test
-- Mirrors test_dispatch.c (callback_function)
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
-- LOAD MODULE
-- ============================================================================

local ok, md = pcall(require, "callback_function_module")
if not ok then
    print("❌ FATAL: Could not load callback_function_module: " .. tostring(md))
    os.exit(1)
end

print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           S-EXPRESSION ENGINE DISPATCH TEST                    ║")
print("╚════════════════════════════════════════════════════════════════╝")
print("")
print("=== Loading module ===")
print("")

-- ============================================================================
-- USER FUNCTIONS
-- Add callback_function-specific user functions here as:
--   { se_my_function = function(inst, node, event_id, event_data) ... end }
-- ============================================================================

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_return_codes"),
    require("se_builtins_dispatch"),
    require("se_builtins_delays"),
    require("se_builtins_spawn")
    -- add user function tables here
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
-- TEST DISPATCH  (mirrors test_dispatch() in C)
-- max_ticks=2, stack enabled, most per-tick printing suppressed
-- ============================================================================

local function test_dispatch(mod, md, tree_hash, tree_label)
    print("")
    print("╔════════════════════════════════════════╗")
    print("║    CALLBACK FUNCTION TEST              ║")
    print("╚════════════════════════════════════════╝")
    print("")
    print("Testing function dictionary test with tick loop...")

    -- Resolve tree by hash, fallback to first tree
    local tree_name = mod.trees_by_hash and mod.trees_by_hash[tree_hash]
    if not tree_name then
        tree_name = md.tree_order and md.tree_order[1]
    end
    if not tree_name then
        print("  ❌ FAILED: Could not resolve tree")
        return
    end

    local inst = se_runtime.new_instance(mod, tree_name)
    if not inst then
        print("  ❌ FAILED: Could not create tree instance")
        return
    end

    -- Create stack (mirrors s_expr_tree_create_stack(tree, 128))
    inst.stack = { top = 0 }

    local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
    local max_ticks     = 2       -- matches C: max_ticks = 2
    local tick_count    = 0
    local result        = se_runtime.SE_PIPELINE_CONTINUE

    print("")
    print("  Running tick loop...")

    repeat
        result    = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)
        tick_count = tick_count + 1
        -- C suppresses per-tick print; only event count printed
        local event_count = se_runtime.event_count(inst)
        print(string.format("------------------------>      Event count: %d", event_count))

        while event_count > 0 do
            local e_tick_type, e_event_id, e_event_data = se_runtime.event_pop(inst)
            -- C suppresses event print

            local saved_tick_type = inst.tick_type
            inst.tick_type        = e_tick_type

            local event_result = se_runtime.tick_once(inst, e_event_id, e_event_data)

            inst.tick_type = saved_tick_type
            -- C suppresses event result print

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

local CALLBACK_FUNCTION_HASH = md.trees[md.tree_order[1]] and
                                md.trees[md.tree_order[1]].name_hash or 0

test_dispatch(mod, md, CALLBACK_FUNCTION_HASH, md.tree_order[1])

print("")
print("✅ All tests completed!")
print("")