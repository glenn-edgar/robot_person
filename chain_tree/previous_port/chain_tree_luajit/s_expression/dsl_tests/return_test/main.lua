-- ============================================================================
-- main_return_tests.lua
-- LuaJIT test driver for return_tests
-- Mirrors return_tests C driver
-- Tests each tree with a single tick and checks the expected result code.
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

-- ============================================================================
-- LOAD MODULE
-- ============================================================================

local ok, md = pcall(require, "return_tests_module")
if not ok then
    print("❌ FATAL: Could not load return_tests_module: " .. tostring(md))
    os.exit(1)
end

print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           S-EXPRESSION ENGINE TEST SUITE                       ║")
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
-- SINGLE-TICK TEST  (mirrors test_return_code() in C)
-- Creates a fresh instance, ticks once, checks result.
-- ============================================================================

local tests_passed = 0
local tests_failed = 0

local function test_return_code(mod, tree_name, expected)
    io.write("Testing " .. tree_name .. "... ")

    local inst = se_runtime.new_instance(mod, tree_name)
    if not inst then
        print("  ❌ FAILED: Could not create instance for tree: " .. tree_name)
        tests_failed = tests_failed + 1
        return
    end

    local result = se_runtime.tick_once(inst, se_runtime.SE_EVENT_TICK, nil)

    if result == expected then
        print(string.format("  ✅ PASS: %s (%d)", result_to_str(result), result))
        tests_passed = tests_passed + 1
    else
        print(string.format("  ❌ FAIL: got %s (%d), expected %s (%d)",
            result_to_str(result),   result,
            result_to_str(expected), expected))
        tests_failed = tests_failed + 1
    end
end

-- ============================================================================
-- RUN ALL RETURN VALUE TESTS  (mirrors run_return_value_tests() in C)
-- Tree names map 1:1 from C hash macro names to snake_case.
-- ============================================================================

local function run_return_value_tests(mod)
    print("")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║                    RETURN VALUE TESTS                          ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print("")

    tests_passed = 0
    tests_failed = 0

    -- Application Result Codes (0-5)
    print("--- Application Result Codes (0-5) ---")
    print("")
    test_return_code(mod, "return_continue_test",      0)
    test_return_code(mod, "return_halt_test",           1)
    test_return_code(mod, "return_terminate_test",      2)
    test_return_code(mod, "return_reset_test",          3)
    test_return_code(mod, "return_disable_test",        4)
    test_return_code(mod, "return_skip_continue_test",  5)

    -- Function Result Codes (6-11)
    print("")
    print("--- Function Result Codes (6-11) ---")
    print("")
    test_return_code(mod, "return_function_continue_test",      se_runtime.SE_FUNCTION_CONTINUE)
    test_return_code(mod, "return_function_halt_test",           se_runtime.SE_FUNCTION_HALT)
    test_return_code(mod, "return_function_terminate_test",      se_runtime.SE_FUNCTION_TERMINATE)
    test_return_code(mod, "return_function_reset_test",          9)
    test_return_code(mod, "return_function_disable_test",        se_runtime.SE_FUNCTION_DISABLE)
    test_return_code(mod, "return_function_skip_continue_test",  11)

    -- Pipeline Result Codes (12-17)
    print("")
    print("--- Pipeline Result Codes (12-17) ---")
    print("")
    test_return_code(mod, "return_pipeline_continue_test",      se_runtime.SE_PIPELINE_CONTINUE)
    test_return_code(mod, "return_pipeline_halt_test",           se_runtime.SE_PIPELINE_HALT)
    test_return_code(mod, "return_pipeline_terminate_test",      se_runtime.SE_PIPELINE_TERMINATE)
    test_return_code(mod, "return_pipeline_reset_test",          se_runtime.SE_PIPELINE_RESET)
    test_return_code(mod, "return_pipeline_disable_test",        se_runtime.SE_PIPELINE_DISABLE)
    test_return_code(mod, "return_pipeline_skip_continue_test",  se_runtime.SE_PIPELINE_SKIP_CONTINUE)

    -- Summary
    print("")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║                        TEST SUMMARY                            ║")
    print("╠════════════════════════════════════════════════════════════════╣")
    print(string.format("║  Passed: %2d                                                    ║", tests_passed))
    print(string.format("║  Failed: %2d                                                    ║", tests_failed))
    print(string.format("║  Total:  %2d                                                    ║", tests_passed + tests_failed))
    print("╚════════════════════════════════════════════════════════════════╝")

    if tests_failed == 0 then
        print("\n✅ ALL TESTS PASSED\n")
    else
        print("\n❌ SOME TESTS FAILED\n")
    end
end

-- ============================================================================
-- RUN
-- ============================================================================

run_return_value_tests(mod)

