-- ============================================================================
-- main_state_machine_test.lua
-- Lua test driver for state_machine_test
-- Mirrors test_dispatch.c (state_machine_test)
--   + state_machine_test_user_functions.c
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
-- Mirrors state_machine_test_user_functions.c
-- All are oneshots: fn(inst, node) — event context via inst.current_event_id
-- ============================================================================

-- cfl_disable_children
-- C: prints "cfl_disable_children", ignores INIT/TERMINATE (no-ops there).
-- Lua: same — reads event_id from inst.current_event_id, prints on tick only.
local function cfl_disable_children(inst, node)
    local event_id = inst.current_event_id
    if event_id == se_runtime.SE_EVENT_INIT then
        return
    end
    if event_id == se_runtime.SE_EVENT_TERMINATE then
        return
    end
    print("cfl_disable_children")
end

-- cfl_enable_child
-- C: reads params[0] as int/uint child index, prints it.
--    Skips silently on INIT and TERMINATE.
-- Lua: params[1] (1-based) holds the child index integer.
local function cfl_enable_child(inst, node)
    local event_id = inst.current_event_id
    if event_id == se_runtime.SE_EVENT_INIT then
        return
    end
    if event_id == se_runtime.SE_EVENT_TERMINATE then
        return
    end

    local p = (node.params or {})[1]
    assert(p, "cfl_enable_child: need at least one parameter")
    local child_index = (type(p.value) == "table") and p.value.i or p.value
    assert(type(child_index) == "number",
        "cfl_enable_child: first parameter must be an integer")

    print(string.format("cfl_enable_child: enabling child %d", child_index))
end

-- ============================================================================
-- LOAD MODULE
-- ============================================================================

local ok, md = pcall(require, "state_machine_test_module")
if not ok then
    print("❌ FATAL: Could not load state_machine_test_module: " .. tostring(md))
    os.exit(1)
end

print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           S-EXPRESSION ENGINE STATE MACHINE TEST               ║")
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
        cfl_disable_children = cfl_disable_children,
        cfl_enable_child     = cfl_enable_child,
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
-- STATE MACHINE TEST  (mirrors test_state_machine() in C)
-- ============================================================================

local function test_state_machine(mod, md)
    print("")
    print("=== STATE MACHINE TEST ===")
    print("")

    local tree_name = md.tree_order and md.tree_order[1]
    if not tree_name then
        print("FAILED: No trees in module")
        return
    end

    local inst = se_runtime.new_instance(mod, tree_name)
    if not inst then
        print("FAILED: Could not create tree instance")
        return
    end

    local SE_EVENT_TICK = se_runtime.SE_EVENT_TICK
    local max_ticks     = 500

    for i = 1, max_ticks do
        local result = se_runtime.tick_once(inst, SE_EVENT_TICK, nil)
        print(string.format("Tick %3d: %s", i, result_to_str(result)))

        if result == se_runtime.SE_FUNCTION_TERMINATE then
            print(string.format(
                "✅ PASSED: Expected SE_FUNCTION_TERMINATE, got %s",
                result_to_str(result)))
            return
        end

        -- Drain event queue
        local event_count = se_runtime.event_count(inst)
        while event_count > 0 do
            local e_tick_type, e_event_id, e_event_data = se_runtime.event_pop(inst)
            local saved = inst.tick_type
            inst.tick_type = e_tick_type
            local event_result = se_runtime.tick_once(inst, e_event_id, e_event_data)
            inst.tick_type = saved
            if result_is_complete(event_result) then
                print(string.format(
                    "✅ PASSED: Tree completed via event with %s",
                    result_to_str(event_result)))
                return
            end
            event_count = se_runtime.event_count(inst)
        end
    end

    print("❌ FAILED: Max ticks (" .. max_ticks .. ") exceeded without termination")
end

-- ============================================================================
-- RUN ALL TESTS
-- ============================================================================

print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           STATE MACHINE TEST SUITE                             ║")
print("╚════════════════════════════════════════════════════════════════╝")

test_state_machine(mod, md)

print("")
print("╔════════════════════════════════════════════════════════════════╗")
print("║           ALL STATE MACHINE TESTS COMPLETE                     ║")
print("╚════════════════════════════════════════════════════════════════╝")
print("")
print("✅ All tests completed!")
print("")
