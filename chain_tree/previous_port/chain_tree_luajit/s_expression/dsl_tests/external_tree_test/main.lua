-- ============================================================================
-- main_function_dictionary_test.lua
-- Test driver for external_tree / call_tree test
-- Mirrors main_function_dictionary_test.c
-- ============================================================================
local _here = arg[0]:match("(.-)[^/]+$") or "./"
dofile(_here .. "se_path.lua")

local se_runtime  = require("se_runtime")
local se_stack    = require("se_stack")

local user_fns    = require("user_functions")

-- ============================================================================
-- Result helpers (mirrors C result_to_str / result_is_terminate / result_is_complete)
-- ============================================================================
local result_names = {
    [0]  = "CONTINUE",
    [1]  = "HALT",
    [2]  = "TERMINATE",
    [3]  = "RESET",
    [4]  = "DISABLE",
    [5]  = "SKIP_CONTINUE",
    [6]  = "FUNCTION_CONTINUE",
    [7]  = "FUNCTION_HALT",
    [8]  = "FUNCTION_TERMINATE",
    [9]  = "FUNCTION_RESET",
    [10] = "FUNCTION_DISABLE",
    [11] = "FUNCTION_SKIP_CONTINUE",
    [12] = "PIPELINE_CONTINUE",
    [13] = "PIPELINE_HALT",
    [14] = "PIPELINE_TERMINATE",
    [15] = "PIPELINE_RESET",
    [16] = "PIPELINE_DISABLE",
    [17] = "PIPELINE_SKIP_CONTINUE",
}

local function result_to_str(r)
    return result_names[r] or "UNKNOWN"
end

local function result_is_terminate(r)
    return r == se_runtime.SE_TERMINATE
        or r == se_runtime.SE_FUNCTION_TERMINATE
        or r == se_runtime.SE_PIPELINE_TERMINATE
end

local function result_is_complete(r)
    return r == se_runtime.SE_TERMINATE
        or r == se_runtime.SE_FUNCTION_TERMINATE
        or r == se_runtime.SE_PIPELINE_TERMINATE
        or r == se_runtime.SE_DISABLE
        or r == se_runtime.SE_FUNCTION_DISABLE
        or r == se_runtime.SE_PIPELINE_DISABLE
end

-- ============================================================================
-- Load module data
-- ============================================================================
print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           S-EXPRESSION ENGINE DISPATCH TEST                    ║")
print("╚════════════════════════════════════════════════════════════════╝")

print("\n=== Loading module ===\n")

local ok, module_data = pcall(require, "external_tree_module")
if not ok then
    print("❌ FATAL: Could not load external_tree_module: " .. tostring(module_data))
    os.exit(1)
end

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_return_codes"),
    require("se_builtins_dispatch"),
    require("se_builtins_delays"),
    require("se_builtins_spawn"),
    require("se_builtins_stack"),
    require("se_builtins_dict"),
    require("se_builtins_quads"),
    user_fns
)

local mod = se_runtime.new_module(module_data, fns)

local val_ok, missing = se_runtime.validate_module(mod)
if not val_ok then
    print("❌ FATAL: Missing functions:")
    for _, m in ipairs(missing) do
        print(string.format("  [%s] %s", m.kind, m.name))
    end
    os.exit(1)
end

print("✅ Module loaded successfully")
print(string.format("   Trees:   %d", #(module_data.tree_order or {})))
print(string.format("   Oneshot: %d", #(module_data.oneshot_funcs or {})))
print(string.format("   Main:    %d", #(module_data.main_funcs or {})))
print(string.format("   Pred:    %d", #(module_data.pred_funcs or {})))

-- ============================================================================
-- Test dispatch (mirrors C test_dispatch — runs call_tree)
-- ============================================================================
local function test_dispatch()
    print("\n╔════════════════════════════════════════╗")
    print("║    FUNCTION DICTIONARY TEST            ║")
    print("╚════════════════════════════════════════╝")
    print("\nTesting function dictionary test with tick loop...")

    local inst = se_runtime.new_instance(mod, "call_tree")
    if not inst then
        print("  ❌ FAILED: Could not create tree instance")
        return
    end

    inst.stack = se_stack.new_stack(128)

    local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
    local max_ticks     = 2
    local tick_count    = 0
    local result

    print("\n  Running tick loop...")

    repeat
        -- Reset stack each tick
        inst.stack.sp          = 0
        inst.stack.frame_count = 0
        inst.stack.frames      = {}

        result = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)
        tick_count = tick_count + 1
        print(string.format("------------------------> Tick %3d: result=%s",
            tick_count, result_to_str(result)))

        -- Drain event queue (mirrors C event queue drain loop)
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

    print(string.format("\n  Total ticks: %d", tick_count))
    print(string.format("  Final result: %s", result_to_str(result)))

    if result_is_terminate(result) then
        print("\n  ✅ PASSED - Tree terminated normally")
    elseif tick_count >= max_ticks then
        print("\n  ❌ FAILED - Max ticks exceeded without termination")
    elseif result_is_complete(result) then
        print("\n  ✅ PASSED - Tree completed (disabled)")
    else
        print("\n  ❌ FAILED - Unexpected result")
    end
end

test_dispatch()

print("\n✅ All tests completed!\n")