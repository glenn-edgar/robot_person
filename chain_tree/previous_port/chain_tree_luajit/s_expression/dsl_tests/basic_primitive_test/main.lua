-- ============================================================================
-- test_trigger_on_change.lua
-- LuaJIT translation of test_trigger_on_change.c
--
-- Tests the se_trigger_on_change builtin against the basic_primitive_test
-- module.  14 test cases covering single-bit, AND-predicate, OR-predicate,
-- NOT-predicate edges and repeated toggling.
--
-- Shared state mirrors C globals:
--   g_bitmap         -- the bitmap that predicates read  (inst.user_ctx.bitmap)
--   g_trigger_events -- bitmask of which oneshot actions fired this tick
--
-- User functions (basic_primitive_test_register_all equivalent) are defined
-- in this file.  Predicates read inst.user_ctx.bitmap; oneshots OR a bit
-- into inst.user_ctx.trigger_events.
--
-- Usage:
--   luajit test_trigger_on_change.lua [module_name] [tree_name_or_hash]
-- ============================================================================

-- Locate the lua_runtime directory relative to this file.
local _here = arg[0]:match("(.-)[^/]+$") or "./"
dofile(_here .. "se_path.lua")

local bit = require("bit")
local band, bor, bnot = bit.band, bit.bor, bit.bnot

local ffi = require("ffi")

-- ============================================================================
-- FFI: wall-clock time
-- ============================================================================

ffi.cdef[[
    struct timespec { long tv_sec; long tv_nsec; };
    int clock_gettime(int clk_id, struct timespec* tp);
]]

local function get_wall_time()
    local ts = ffi.new("struct timespec")
    ffi.C.clock_gettime(0, ts)
    return tonumber(ts.tv_sec) + tonumber(ts.tv_nsec) * 1e-9
end

-- ============================================================================
-- CONFIGURATION
-- ============================================================================

local MODULE_NAME       = (arg and arg[1]) or "basic_primitive_test_module"
local TREE_NAME_OR_HASH = (arg and arg[2]) or nil

-- ============================================================================
-- RUNTIME
-- ============================================================================

local se_runtime = require("se_runtime")
se_runtime.default_get_time = get_wall_time

-- Event bit constants come from the user functions module (imported below)

-- ============================================================================
-- SHARED STATE  (mirrors C globals g_bitmap / g_trigger_events)
--
-- Stored in a table so it can be passed to inst.user_ctx and mutated in place.
-- Predicates read ctx.bitmap; oneshots OR bits into ctx.trigger_events.
-- This mirrors the C pattern of passing &g_bitmap via tree->user_ctx.
-- ============================================================================

local ctx = {
    bitmap         = 0,
    trigger_events = 0,
}

local function reset_trigger_events()  ctx.trigger_events = 0 end
local function get_trigger_events()    return ctx.trigger_events end

-- ============================================================================
-- USER FUNCTIONS
-- Loaded from basic_primitive_test_user_functions.lua which mirrors
-- basic_primitive_test_register_all() in C.
-- Event bit constants are imported from the same module.
-- ============================================================================

local user_module = require("user_functions")

-- ============================================================================
-- MODULE LOAD
-- ============================================================================

local function load_module(module_name)
    local ok, module_data = pcall(require, module_name)
    if not ok then return nil, tostring(module_data) end

    local mod = se_runtime.new_module(module_data)
    mod.get_time = get_wall_time

    -- Standard builtins
    se_runtime.register_fns(mod, require("se_builtins_flow_control"))
    se_runtime.register_fns(mod, require("se_builtins_dispatch"))
    se_runtime.register_fns(mod, require("se_builtins_pred"))
    se_runtime.register_fns(mod, require("se_builtins_oneshot"))
    se_runtime.register_fns(mod, require("se_builtins_return_codes"))
    se_runtime.register_fns(mod, require("se_builtins_delays"))
    se_runtime.register_fns(mod, require("se_builtins_verify"))
    se_runtime.register_fns(mod, require("se_builtins_stack"))
    se_runtime.register_fns(mod, require("se_builtins_spawn"))
    se_runtime.register_fns(mod, require("se_builtins_quads"))
    se_runtime.register_fns(mod, require("se_builtins_dict"))

    -- Application-specific user functions  (mirrors basic_primitive_test_register_all)
    user_module.register(mod)

    local valid, missing = se_runtime.validate_module(mod)
    if not valid then
        local names = {}
        for _, m in ipairs(missing) do
            names[#names+1] = string.format("[%s] %s", m.kind, m.name)
        end
        return nil, "missing functions:\n  " .. table.concat(names, "\n  ")
    end

    return mod
end

local function resolve_tree_name(mod, hint)
    if hint then
        if mod.module_data.trees and mod.module_data.trees[hint] then return hint end
        local hash = tonumber(hint)
        if hash and mod.trees_by_hash[hash] then return mod.trees_by_hash[hash] end
        if hint:sub(1,2) ~= "0x" then
            hash = tonumber("0x" .. hint)
            if hash and mod.trees_by_hash[hash] then return mod.trees_by_hash[hash] end
        end
        return nil, "tree not found for hint: " .. hint
    end
    if mod.module_data.test_tree_name then return mod.module_data.test_tree_name end
    local order = mod.module_data.tree_order
    if order and order[1] then return order[1] end
    return nil, "no trees in module"
end

-- ============================================================================
-- TICK HELPER
-- No event-queue drain needed here: trigger_on_change fires oneshots
-- synchronously during the tick, not via the event queue.
-- ============================================================================

local function do_tick(inst)
    return se_runtime.tick_once(inst, se_runtime.SE_EVENT_TICK, nil)
end

-- ============================================================================
-- TEST_TRIGGER_ON_CHANGE
-- Direct line-for-line translation of C test_trigger_on_change().
-- ============================================================================

local function test_trigger_on_change(mod, tree_name)
    print("\n=== Test Trigger On Change ===")

    local inst = se_runtime.new_instance(mod, tree_name)

    -- Wire shared state into the instance  (mirrors tree->user_ctx = &g_bitmap)
    inst.user_ctx = ctx

    ctx.bitmap         = 0
    ctx.trigger_events = 0

    local test_pass = true

    local function check(label, cond, msg)
        if not cond then
            print(string.format("  ❌ %s", msg))
            test_pass = false
        end
    end

    local function check_not(label, cond, msg)
        if cond then
            print(string.format("  ❌ %s", msg))
            test_pass = false
        end
    end

    -- -------------------------------------------------------------------------
    -- Initial tick — all triggers start at their initial state, no transitions
    -- -------------------------------------------------------------------------
    print(string.format("\n--- Initial tick (bitmap=0x%08X) ---", ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))

    -- -------------------------------------------------------------------------
    -- Test 1: Set bit 0 -> BIT0_RISE
    -- -------------------------------------------------------------------------
    local prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 0))
    print(string.format("\n--- Set bit 0 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t1", band(get_trigger_events(), user_module.EVENT_BIT0_RISE) ~= 0, "Expected BIT0_RISE")

    -- -------------------------------------------------------------------------
    -- Test 2: Clear bit 0 -> BIT0_FALL
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 0)))
    print(string.format("\n--- Clear bit 0 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t2", band(get_trigger_events(), user_module.EVENT_BIT0_FALL) ~= 0, "Expected BIT0_FALL")

    -- -------------------------------------------------------------------------
    -- Test 3: Set bit 1 only -> AND not yet true, no BITS12_RISE
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 1))
    print(string.format("\n--- Set bit 1 only (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check_not("t3", band(get_trigger_events(), user_module.EVENT_BITS12_RISE) ~= 0,
        "Unexpected BITS12_RISE (only bit1 set)")

    -- -------------------------------------------------------------------------
    -- Test 4: Set bit 2 -> AND now true, BITS12_RISE
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 2))
    print(string.format("\n--- Set bit 2 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t4", band(get_trigger_events(), user_module.EVENT_BITS12_RISE) ~= 0, "Expected BITS12_RISE")

    -- -------------------------------------------------------------------------
    -- Test 5: Clear bit 1 -> AND false, BITS12_FALL
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 1)))
    print(string.format("\n--- Clear bit 1 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t5", band(get_trigger_events(), user_module.EVENT_BITS12_FALL) ~= 0, "Expected BITS12_FALL")

    -- -------------------------------------------------------------------------
    -- Test 6: Set bit 3 -> OR true, BITS34_RISE
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 3))
    print(string.format("\n--- Set bit 3 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t6", band(get_trigger_events(), user_module.EVENT_BITS34_RISE) ~= 0, "Expected BITS34_RISE")

    -- -------------------------------------------------------------------------
    -- Test 7: Set bit 4 also -> OR still true, no new edge
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 4))
    print(string.format("\n--- Set bit 4 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check_not("t7",
        band(get_trigger_events(), bor(user_module.EVENT_BITS34_RISE, user_module.EVENT_BITS34_FALL)) ~= 0,
        "Unexpected BITS34 event (OR still true)")

    -- -------------------------------------------------------------------------
    -- Test 8: Clear bit 3 -> OR still true via bit 4, no edge
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 3)))
    print(string.format("\n--- Clear bit 3 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check_not("t8",
        band(get_trigger_events(), bor(user_module.EVENT_BITS34_RISE, user_module.EVENT_BITS34_FALL)) ~= 0,
        "Unexpected BITS34 event (OR still true via bit4)")

    -- -------------------------------------------------------------------------
    -- Test 9: Clear bit 4 -> OR now false, BITS34_FALL
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 4)))
    print(string.format("\n--- Clear bit 4 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t9", band(get_trigger_events(), user_module.EVENT_BITS34_FALL) ~= 0, "Expected BITS34_FALL")

    -- -------------------------------------------------------------------------
    -- Test 10: Set bit 5 -> NOT becomes false, BIT5_SET
    -- (initial_state=1 so NOT bit5 starts true when bit5=0)
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 5))
    print(string.format("\n--- Set bit 5 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t10", band(get_trigger_events(), user_module.EVENT_BIT5_SET) ~= 0,
        "Expected BIT5_SET (NOT became false)")

    -- -------------------------------------------------------------------------
    -- Test 11: Clear bit 5 -> NOT becomes true, BIT5_CLEAR
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 5)))
    print(string.format("\n--- Clear bit 5 (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t11", band(get_trigger_events(), user_module.EVENT_BIT5_CLEAR) ~= 0,
        "Expected BIT5_CLEAR (NOT became true)")

    -- -------------------------------------------------------------------------
    -- Test 12: Set bit 0 AGAIN -> BIT0_RISE repeated
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 0))
    print(string.format("\n--- Set bit 0 AGAIN (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t12", band(get_trigger_events(), user_module.EVENT_BIT0_RISE) ~= 0,
        "Expected BIT0_RISE on repeated trigger")

    -- -------------------------------------------------------------------------
    -- Test 13: Clear bit 0 AGAIN -> BIT0_FALL repeated
    -- -------------------------------------------------------------------------
    prev = ctx.bitmap
    ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 0)))
    print(string.format("\n--- Clear bit 0 AGAIN (bitmap=0x%08X -> 0x%08X) ---", prev, ctx.bitmap))
    reset_trigger_events()
    do_tick(inst)
    print(string.format("  events fired: 0x%02X", get_trigger_events()))
    check("t13", band(get_trigger_events(), user_module.EVENT_BIT0_FALL) ~= 0,
        "Expected BIT0_FALL on repeated trigger")

    -- -------------------------------------------------------------------------
    -- Test 14: Rapid toggle — 3 full rise/fall cycles on bit 0
    -- -------------------------------------------------------------------------
    print("\n--- Rapid toggle bit 0 (3 cycles) ---")
    for cycle = 1, 3 do
        -- Rise
        ctx.bitmap = bor(ctx.bitmap, bit.lshift(1, 0))
        reset_trigger_events()
        do_tick(inst)
        check("t14-rise", band(get_trigger_events(), user_module.EVENT_BIT0_RISE) ~= 0,
            string.format("Cycle %d: Expected BIT0_RISE", cycle))

        -- Fall
        ctx.bitmap = band(ctx.bitmap, bnot(bit.lshift(1, 0)))
        reset_trigger_events()
        do_tick(inst)
        check("t14-fall", band(get_trigger_events(), user_module.EVENT_BIT0_FALL) ~= 0,
            string.format("Cycle %d: Expected BIT0_FALL", cycle))
    end
    print("  Completed 3 toggle cycles")

    -- -------------------------------------------------------------------------
    -- Summary
    -- -------------------------------------------------------------------------
    if test_pass then
        print("\n  ✅ PASSED: All edge triggers working correctly")
    else
        print("\n  ❌ FAILED: Some edge triggers failed")
    end
end

-- ============================================================================
-- MAIN
-- ============================================================================

print()
print("╔════════════════════════════════════════════════════════════════╗")
print("║        S-EXPRESSION ENGINE TRIGGER ON CHANGE TEST             ║")
print("╚════════════════════════════════════════════════════════════════╝")
print()

-- ---- Test 1: require() load — analogous to s_engine_load_from_rom ----------

print("=== Loading module from require() ===\n")

local mod, err = load_module(MODULE_NAME)
if not mod then
    print(string.format("❌ FATAL: Failed to load module '%s': %s", MODULE_NAME, err))
    os.exit(1)
end
print("✅ Module loaded successfully")

local tree_name, tree_err = resolve_tree_name(mod, TREE_NAME_OR_HASH)
if not tree_name then
    print(string.format("❌ FATAL: %s", tree_err))
    os.exit(1)
end

test_trigger_on_change(mod, tree_name)



print("\n✅ All tests completed!\n")