-- ============================================================================
-- main_function_dictionary_test.lua
-- Test driver for function_dictionary test
-- Mirrors main_function_dictionary_test.c
-- ============================================================================
local _here = arg[0]:match("(.-)[^/]+$") or "./"
dofile(_here .. "se_path.lua")

local se_runtime  = require("se_runtime")
local se_stack    = require("se_stack")

-- Load user functions (translated from function_dictionary_user_functions.c)
local user_fns    = require("user_functions")

-- ============================================================================
-- Load module data
-- ============================================================================
print("=== Loading module ===")

local ok, module_data = pcall(require, "function_dictionary_module")
if not ok then
    print("❌ FATAL: Could not load function_dictionary_module: " .. tostring(module_data))
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
-- Local result-code helpers
-- ============================================================================
local function result_is_complete(r)
    return r ~= se_runtime.SE_PIPELINE_CONTINUE
       and r ~= se_runtime.SE_PIPELINE_DISABLE
end

local function result_is_terminate(r)
    return r == se_runtime.SE_TERMINATE
        or r == se_runtime.SE_FUNCTION_TERMINATE
        or r == se_runtime.SE_PIPELINE_TERMINATE
end

-- ============================================================================
-- Test dispatch
-- ============================================================================
local function test_dispatch()
    print("\n╔════════════════════════════════════════╗")
    print("║    FUNCTION DICTIONARY TEST            ║")
    print("╚════════════════════════════════════════╝")
    print("\nTesting function dictionary test with tick loop...")

    local inst = se_runtime.new_instance(mod, "function_dictionary")
    if not inst then
        print("  ❌ FAILED: Could not create tree instance")
        return
    end

    -- Stack required for write_register (reads locals from stack)
    inst.stack = se_stack.new_stack(128)

    local SE_EVENT_TICK = 0
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
            tick_count, tostring(result)))

    until result_is_complete(result) or tick_count >= max_ticks

    print(string.format("\n  Total ticks: %d", tick_count))
    print(string.format("  Final result: %s", tostring(result)))

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