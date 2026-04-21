-- ============================================================================
-- main_json_test.lua
-- LuaJIT test driver for json_test
-- Mirrors json_test C driver with user functions from user_dict_extract_debug.c
-- ============================================================================

local _here = arg[0]:match("(.-)[^/]+$") or "./"
dofile(_here .. "se_path.lua")

local se_runtime  = require("se_runtime")
local field_get   = se_runtime.field_get
local param_str   = se_runtime.param_str

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
-- EXPECTED VALUES  (mirrors #define block in C)
-- ============================================================================

local E = {
    INT_1=12345, INT_2=-9876, INT_3=42,
    UINT_1=100, UINT_2=50000, UINT_3=255,
    FLOAT_1=3.14159, FLOAT_2=-273.15, FLOAT_3=2.71828,
    BOOL_1=1, BOOL_2=0, BOOL_3=1,
    ARR_INT_0=10, ARR_INT_1=20, ARR_INT_2=30, ARR_INT_3=40,
    ARR_FLOAT_0=1.5, ARR_FLOAT_1=2.5, ARR_FLOAT_2=3.5,
    ARR_N0_ID=100, ARR_N0_VAL=10.1,
    ARR_N1_ID=200, ARR_N1_VAL=20.2,
    ARR_N2_ID=300, ARR_N2_VAL=30.3,
    PTR_INT_POS=12345, PTR_INT_NEG=-9876,
    PTR_FLOAT_PI=3.14159, PTR_FLOAT_NEG=-273.15,
    PTR_N0_ID=100, PTR_N0_VAL=10.1,
    PTR_N1_ID=200, PTR_N1_VAL=20.2,
}
local TOL = 0.01

-- ============================================================================
-- CHECK HELPERS
-- ============================================================================

local function check_int(name, got, expected, errors)
    got = math.floor(tonumber(got) or 0)
    if got == expected then
        print(string.format("║  ✅ %-28s = %-10d", name, got))
    else
        print(string.format("║  ❌ %s: got %d, expected %d", name, got, expected))
        errors[1] = errors[1] + 1
    end
end

local function check_uint(name, got, expected, errors)
    got = math.floor(tonumber(got) or 0)
    if got == expected then
        print(string.format("║  ✅ %-28s = %-10u", name, got))
    else
        print(string.format("║  ❌ %s: got %u, expected %u", name, got, expected))
        errors[1] = errors[1] + 1
    end
end

local function check_float(name, got, expected, errors)
    got = tonumber(got) or 0
    if math.abs(got - expected) < TOL then
        print(string.format("║  ✅ %-28s = %-10.5f", name, got))
    else
        print(string.format("║  ❌ %s: got %.5f, expected %.5f", name, got, expected))
        errors[1] = errors[1] + 1
    end
end

-- Hash: Lua cannot call s_expr_hash() so verify non-zero and display value.
local function check_hash(name, got, label, errors)
    got = math.floor(tonumber(got) or 0)
    if got ~= 0 then
        print(string.format("║  ✅ %-28s = 0x%08X  (hash of '%s')", name, got, label))
    else
        print(string.format("║  ❌ %s: got 0 (expected hash of '%s')", name, label))
        errors[1] = errors[1] + 1
    end
end

local function fv(inst, node, idx)  -- float value helper
    return tonumber(field_get(inst, node, idx)) or 0
end
local function iv(inst, node, idx)  -- int value helper
    return math.floor(fv(inst, node, idx))
end

-- ============================================================================
-- USER FUNCTIONS  (mirrors C user_dict_extract_debug.c)
-- C params[] is 0-based; Lua param_* helpers are 1-based.
-- C params[N] -> Lua param index N+1 -> field_get(inst, node, N+1)
-- ============================================================================

-- user_print_extract_results  (Pass 1 & 2)
-- params[0]=STR title, [1]=pass, [2-4]=int, [5-7]=uint, [8-10]=float,
--          [11-13]=bool, [14-16]=hash
local function user_print_extract_results(inst, node)
    local title = param_str(node, 1) or "Unknown"
    local pass  = iv(inst, node, 2)
    print("")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print(string.format("║  %s (Pass %d)", title, pass))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  INTEGERS:                                                       ║")
    print(string.format("║    int_val_1 (positive)      = %-10d  (expected: %d)",  iv(inst,node,3),  E.INT_1))
    print(string.format("║    int_val_2 (negative)      = %-10d  (expected: %d)",  iv(inst,node,4),  E.INT_2))
    print(string.format("║    int_val_3 (nested.deep)   = %-10d  (expected: %d)",  iv(inst,node,5),  E.INT_3))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  UNSIGNED INTEGERS:                                              ║")
    print(string.format("║    uint_val_1 (small)        = %-10u  (expected: %u)",  iv(inst,node,6),  E.UINT_1))
    print(string.format("║    uint_val_2 (medium)       = %-10u  (expected: %u)",  iv(inst,node,7),  E.UINT_2))
    print(string.format("║    uint_val_3 (nested.deep)  = %-10u  (expected: %u)",  iv(inst,node,8),  E.UINT_3))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  FLOATS:                                                         ║")
    print(string.format("║    float_val_1 (pi)          = %-10.5f  (expected: %.5f)", fv(inst,node,9),  E.FLOAT_1))
    print(string.format("║    float_val_2 (negative)    = %-10.2f  (expected: %.2f)", fv(inst,node,10), E.FLOAT_2))
    print(string.format("║    float_val_3 (nested.deep) = %-10.5f  (expected: %.5f)", fv(inst,node,11), E.FLOAT_3))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  BOOLEANS:                                                       ║")
    print(string.format("║    bool_val_1 (true_val)     = %-10u  (expected: %u)", iv(inst,node,12), E.BOOL_1))
    print(string.format("║    bool_val_2 (false_val)    = %-10u  (expected: %u)", iv(inst,node,13), E.BOOL_2))
    print(string.format("║    bool_val_3 (nested.deep)  = %-10u  (expected: %u)", iv(inst,node,14), E.BOOL_3))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  HASHES:                                                         ║")
    print(string.format("║    hash_val_1 (idle)         = 0x%08X  (expected: hash('idle'))",      iv(inst,node,15)))
    print(string.format("║    hash_val_2 (running)      = 0x%08X  (expected: hash('running'))",   iv(inst,node,16)))
    print(string.format("║    hash_val_3 (deep_hash)    = 0x%08X  (expected: hash('deep_hash'))", iv(inst,node,17)))
    print("╚══════════════════════════════════════════════════════════════════╝")
end

-- user_print_array_results  (Pass 3)
-- params[0]=STR title, [1]=pass, [2-5]=arr_int, [6-8]=arr_float,
--          [9-10]=n0 id/val, [11-12]=n1 id/val, [13-14]=n2 id/val
local function user_print_array_results(inst, node)
    local title = param_str(node, 1) or "Unknown"
    local pass  = iv(inst, node, 2)
    print("")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print(string.format("║  %s (Pass %d)", title, pass))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  INT ARRAY {10, 20, 30, 40}:                                     ║")
    print(string.format("║    [0] = %-10d  (expected: %d)", iv(inst,node,3),  E.ARR_INT_0))
    print(string.format("║    [1] = %-10d  (expected: %d)", iv(inst,node,4),  E.ARR_INT_1))
    print(string.format("║    [2] = %-10d  (expected: %d)", iv(inst,node,5),  E.ARR_INT_2))
    print(string.format("║    [3] = %-10d  (expected: %d)", iv(inst,node,6),  E.ARR_INT_3))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  FLOAT ARRAY {1.5, 2.5, 3.5}:                                   ║")
    print(string.format("║    [0] = %-10.5f  (expected: %.5f)", fv(inst,node,7),  E.ARR_FLOAT_0))
    print(string.format("║    [1] = %-10.5f  (expected: %.5f)", fv(inst,node,8),  E.ARR_FLOAT_1))
    print(string.format("║    [2] = %-10.5f  (expected: %.5f)", fv(inst,node,9),  E.ARR_FLOAT_2))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  NESTED ARRAY [{id:100,val:10.1}, {id:200,val:20.2}, ...]:       ║")
    print(string.format("║    items[0].id    = %-10u  (expected: %u)",   iv(inst,node,10), E.ARR_N0_ID))
    print(string.format("║    items[0].value = %-10.1f  (expected: %.1f)", fv(inst,node,11), E.ARR_N0_VAL))
    print(string.format("║    items[1].id    = %-10u  (expected: %u)",   iv(inst,node,12), E.ARR_N1_ID))
    print(string.format("║    items[1].value = %-10.1f  (expected: %.1f)", fv(inst,node,13), E.ARR_N1_VAL))
    print(string.format("║    items[2].id    = %-10u  (expected: %u)",   iv(inst,node,14), E.ARR_N2_ID))
    print(string.format("║    items[2].value = %-10.1f  (expected: %.1f)", fv(inst,node,15), E.ARR_N2_VAL))
    print("╚══════════════════════════════════════════════════════════════════╝")
end

-- user_print_pointer_results  (Pass 4)
-- params[0]=STR title, [1]=pass, [2-3]=int from sub_integers,
--          [4-5]=float from sub_floats, [6-7]=n0 id/val, [8-9]=n1 id/val
local function user_print_pointer_results(inst, node)
    local title = param_str(node, 1) or "Unknown"
    local pass  = iv(inst, node, 2)
    print("")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print(string.format("║  %s (Pass %d)", title, pass))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  FROM sub_integers POINTER:                                      ║")
    print(string.format("║    positive  = %-10d  (expected: %d)",   iv(inst,node,3), E.PTR_INT_POS))
    print(string.format("║    negative  = %-10d  (expected: %d)",   iv(inst,node,4), E.PTR_INT_NEG))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  FROM sub_floats POINTER:                                        ║")
    print(string.format("║    pi        = %-10.5f  (expected: %.5f)", fv(inst,node,5), E.PTR_FLOAT_PI))
    print(string.format("║    negative  = %-10.2f  (expected: %.2f)", fv(inst,node,6), E.PTR_FLOAT_NEG))
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  FROM sub_nested POINTERS (items[0], items[1]):                  ║")
    print(string.format("║    items[0].id    = %-10u  (expected: %u)",   iv(inst,node,7), E.PTR_N0_ID))
    print(string.format("║    items[0].value = %-10.1f  (expected: %.1f)", fv(inst,node,8), E.PTR_N0_VAL))
    print(string.format("║    items[1].id    = %-10u  (expected: %u)",   iv(inst,node,9), E.PTR_N1_ID))
    print(string.format("║    items[1].value = %-10.1f  (expected: %.1f)", fv(inst,node,10), E.PTR_N1_VAL))
    print("╚══════════════════════════════════════════════════════════════════╝")
end

-- user_verify_results  (no params — reads blackboard directly by field name)
local function user_verify_results(inst, node)
    local bb = inst.blackboard
    if not bb then return end
    local errors = {0}

    print("")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  VERIFICATION RESULTS                                            ║")
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  Pass 1 & 2: Scalar Extractions                                 ║")
    print("╠──────────────────────────────────────────────────────────────────╣")

    check_int  ("int_val_1",   bb.int_val_1,   E.INT_1,   errors)
    check_int  ("int_val_2",   bb.int_val_2,   E.INT_2,   errors)
    check_int  ("int_val_3",   bb.int_val_3,   E.INT_3,   errors)
    check_uint ("uint_val_1",  bb.uint_val_1,  E.UINT_1,  errors)
    check_uint ("uint_val_2",  bb.uint_val_2,  E.UINT_2,  errors)
    check_uint ("uint_val_3",  bb.uint_val_3,  E.UINT_3,  errors)
    check_float("float_val_1", bb.float_val_1, E.FLOAT_1, errors)
    check_float("float_val_2", bb.float_val_2, E.FLOAT_2, errors)
    check_float("float_val_3", bb.float_val_3, E.FLOAT_3, errors)
    check_uint ("bool_val_1",  bb.bool_val_1,  E.BOOL_1,  errors)
    check_uint ("bool_val_2",  bb.bool_val_2,  E.BOOL_2,  errors)
    check_uint ("bool_val_3",  bb.bool_val_3,  E.BOOL_3,  errors)
    check_hash ("hash_val_1",  bb.hash_val_1,  "idle",      errors)
    check_hash ("hash_val_2",  bb.hash_val_2,  "running",   errors)
    check_hash ("hash_val_3",  bb.hash_val_3,  "deep_hash", errors)

    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  Pass 3: Array Access                                            ║")
    print("╠──────────────────────────────────────────────────────────────────╣")

    check_int  ("arr_int_0",       bb.arr_int_0,       E.ARR_INT_0,   errors)
    check_int  ("arr_int_1",       bb.arr_int_1,       E.ARR_INT_1,   errors)
    check_int  ("arr_int_2",       bb.arr_int_2,       E.ARR_INT_2,   errors)
    check_int  ("arr_int_3",       bb.arr_int_3,       E.ARR_INT_3,   errors)
    check_float("arr_float_0",     bb.arr_float_0,     E.ARR_FLOAT_0, errors)
    check_float("arr_float_1",     bb.arr_float_1,     E.ARR_FLOAT_1, errors)
    check_float("arr_float_2",     bb.arr_float_2,     E.ARR_FLOAT_2, errors)
    check_uint ("arr_nested_0_id", bb.arr_nested_0_id, E.ARR_N0_ID,   errors)
    check_float("arr_nested_0_val",bb.arr_nested_0_val,E.ARR_N0_VAL,  errors)
    check_uint ("arr_nested_1_id", bb.arr_nested_1_id, E.ARR_N1_ID,   errors)
    check_float("arr_nested_1_val",bb.arr_nested_1_val,E.ARR_N1_VAL,  errors)
    check_uint ("arr_nested_2_id", bb.arr_nested_2_id, E.ARR_N2_ID,   errors)
    check_float("arr_nested_2_val",bb.arr_nested_2_val,E.ARR_N2_VAL,  errors)

    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  Pass 4: Pointer Extraction                                      ║")
    print("╠──────────────────────────────────────────────────────────────────╣")

    check_int  ("ptr_int_pos",  bb.ptr_int_pos,  E.PTR_INT_POS,   errors)
    check_int  ("ptr_int_neg",  bb.ptr_int_neg,  E.PTR_INT_NEG,   errors)
    check_float("ptr_float_pi", bb.ptr_float_pi, E.PTR_FLOAT_PI,  errors)
    check_float("ptr_float_neg",bb.ptr_float_neg,E.PTR_FLOAT_NEG, errors)
    check_uint ("ptr_n0_id",    bb.ptr_n0_id,    E.PTR_N0_ID,     errors)
    check_float("ptr_n0_val",   bb.ptr_n0_val,   E.PTR_N0_VAL,    errors)
    check_uint ("ptr_n1_id",    bb.ptr_n1_id,    E.PTR_N1_ID,     errors)
    check_float("ptr_n1_val",   bb.ptr_n1_val,   E.PTR_N1_VAL,    errors)

    local total  = 15 + 13 + 8
    local passed = total - errors[1]
    print("╠══════════════════════════════════════════════════════════════════╣")
    if errors[1] == 0 then
        print(string.format("║  ✅ ALL %d TESTS PASSED                                         ║", total))
    else
        print(string.format("║  ❌ %d/%d PASSED, %d FAILED                                     ║",
            passed, total, errors[1]))
    end
    print("╚══════════════════════════════════════════════════════════════════╝")
    print("")
end

-- ============================================================================
-- LOAD MODULE
-- ============================================================================

local ok, md = pcall(require, "json_test_module")
if not ok then
    print("❌ FATAL: Could not load json_test_module: " .. tostring(md))
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
    require("se_builtins_dict"),
    {
        user_print_extract_results  = user_print_extract_results,
        user_print_array_results    = user_print_array_results,
        user_print_pointer_results  = user_print_pointer_results,
        user_verify_results         = user_verify_results,
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
-- TEST DISPATCH
-- ============================================================================

local function test_dispatch(mod, md)
    print("")
    print("╔════════════════════════════════════════╗")
    print("║    JSON TEST                           ║")
    print("╚════════════════════════════════════════╝")
    print("")
    print("Testing json test with tick loop...")

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
