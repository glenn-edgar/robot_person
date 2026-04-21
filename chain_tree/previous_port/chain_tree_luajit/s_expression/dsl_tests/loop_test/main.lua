-- ============================================================================
-- main_loop_test.lua
-- LuaJIT test driver for loop_test
-- Mirrors loop_test C driver (test_dispatch / main)
-- No user functions.
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

local ok, md = pcall(require, "loop_test_module")
if not ok then
    print("❌ FATAL: Could not load loop_test_module: " .. tostring(md))
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
    require("se_builtins_spawn")
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
-- ============================================================================

local function test_dispatch(mod, md)
    print("")
    print("╔════════════════════════════════════════╗")
    print("║    LOOP TEST                           ║")
    print("╚════════════════════════════════════════╝")
    print("")
    print("Testing dispatch with tick loop...")

    local tree_name = md.tree_order and md.tree_order[1]
    if not tree_name then
        print("  ❌ FAILED: No trees in module")
        return
    end

    local inst = se_runtime.new_instance(mod, tree_name)
    if not inst then
        print("  ❌ FAILED: Could not create tree instance for: " .. tostring(tree_name))
        return
    end

    local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
    local tick_count    = 0
    local max_ticks     = 500
    local result

    print("")
    print("  Running tick loop...")
    print("")

    repeat
        result     = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)
        tick_count = tick_count + 1
        print(string.format("------------------------> Tick %3d: result=%s",
            tick_count, result_to_str(result)))

        local event_count = se_runtime.event_count(inst)
        while event_count > 0 do
            local tick_type, event_id, event_data = se_runtime.event_pop(inst)

            local saved_tick_type = inst.tick_type
            inst.tick_type = tick_type

            local event_result = se_runtime.tick_once(inst, event_id, event_data)

            inst.tick_type = saved_tick_type

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
-- RUN
-- ============================================================================

test_dispatch(mod, md)

print("")
print("✅ All tests completed!")
print("")
