-- ============================================================================
-- test_complex_sequence.lua
-- LuaJIT translation of test_dispatch.c (complex_sequence variant)
--
-- Differences from the generic test_dispatch.lua:
--   - Module: complex_sequence_module
--   - Tree:   looked up by COMPLEX_SEQUENCE_TEST_HASH (from module_data)
--   - Delay:  0.1 s between ticks  (mirrors delay_seconds(0.1) in C)
--   - No user functions — module uses builtins only
--
-- Usage:
--   luajit test_complex_sequence.lua
-- ============================================================================

local _here = arg[0]:match("(.-)[^/]+$") or "./"
dofile(_here .. "se_path.lua")

local ffi = require("ffi")

-- ============================================================================
-- FFI: sleep + wall clock
-- ============================================================================

ffi.cdef[[
    struct timespec { long tv_sec; long tv_nsec; };
    int nanosleep(const struct timespec* req, struct timespec* rem);
    int clock_gettime(int clk_id, struct timespec* tp);
]]

local function delay_seconds(sec)
    if sec <= 0 then return end
    local ts = ffi.new("struct timespec")
    ts.tv_sec  = math.floor(sec)
    ts.tv_nsec = math.floor((sec % 1) * 1e9)
    ffi.C.nanosleep(ts, nil)
end

local function get_wall_time()
    local ts = ffi.new("struct timespec")
    ffi.C.clock_gettime(0, ts)
    return tonumber(ts.tv_sec) + tonumber(ts.tv_nsec) * 1e-9
end

-- ============================================================================
-- Runtime
-- ============================================================================

local se_runtime = require("se_runtime")
se_runtime.default_get_time = get_wall_time

local function register_builtins(mod)
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
    -- No user functions: complex_sequence uses builtins only
end

-- ============================================================================
-- Result helpers  (application-defined — mirrors C exactly)
-- ============================================================================

local R = se_runtime

local RESULT_NAMES = {
    [R.SE_CONTINUE]               = "CONTINUE",
    [R.SE_HALT]                   = "HALT",
    [R.SE_TERMINATE]              = "TERMINATE",
    [R.SE_RESET]                  = "RESET",
    [R.SE_DISABLE]                = "DISABLE",
    [R.SE_SKIP_CONTINUE]          = "SKIP_CONTINUE",
    [R.SE_FUNCTION_CONTINUE]      = "FUNCTION_CONTINUE",
    [R.SE_FUNCTION_HALT]          = "FUNCTION_HALT",
    [R.SE_FUNCTION_TERMINATE]     = "FUNCTION_TERMINATE",
    [R.SE_FUNCTION_RESET]         = "FUNCTION_RESET",
    [R.SE_FUNCTION_DISABLE]       = "FUNCTION_DISABLE",
    [R.SE_FUNCTION_SKIP_CONTINUE] = "FUNCTION_SKIP_CONTINUE",
    [R.SE_PIPELINE_CONTINUE]      = "PIPELINE_CONTINUE",
    [R.SE_PIPELINE_HALT]          = "PIPELINE_HALT",
    [R.SE_PIPELINE_TERMINATE]     = "PIPELINE_TERMINATE",
    [R.SE_PIPELINE_RESET]         = "PIPELINE_RESET",
    [R.SE_PIPELINE_DISABLE]       = "PIPELINE_DISABLE",
    [R.SE_PIPELINE_SKIP_CONTINUE] = "PIPELINE_SKIP_CONTINUE",
}

local function result_to_str(r)
    return RESULT_NAMES[r] or string.format("UNKNOWN(%d)", r)
end

local function result_is_terminate(r)
    return r == R.SE_TERMINATE
        or r == R.SE_FUNCTION_TERMINATE
        or r == R.SE_PIPELINE_TERMINATE
end

local function result_is_complete(r)
    return r == R.SE_TERMINATE        or r == R.SE_FUNCTION_TERMINATE
        or r == R.SE_PIPELINE_TERMINATE
        or r == R.SE_DISABLE          or r == R.SE_FUNCTION_DISABLE
        or r == R.SE_PIPELINE_DISABLE
end

-- ============================================================================
-- load_module
-- ============================================================================

local function load_module(module_name)
    local ok, md = pcall(require, module_name)
    if not ok then return nil, tostring(md) end

    local mod = se_runtime.new_module(md)
    mod.get_time = get_wall_time
    register_builtins(mod)

    local valid, missing = se_runtime.validate_module(mod)
    if not valid then
        local t = {}
        for _, m in ipairs(missing) do
            t[#t+1] = string.format("[%s] %s", m.kind, m.name)
        end
        return nil, "missing functions:\n  " .. table.concat(t, "\n  ")
    end
    return mod
end

-- ============================================================================
-- test_dispatch
-- Mirrors C test_dispatch() exactly, including the 0.1 s inter-tick delay
-- and the manual event-queue drain loop.
-- Tree is located by the name_hash stored in module_data
-- (mirrors s_engine_create_tree_by_hash(engine, COMPLEX_SEQUENCE_TEST_HASH, 0)).
-- ============================================================================

local MAX_TICKS      = 500
local TICK_DELAY_SEC = 0.1

local function test_dispatch(mod)
    print("\n╔════════════════════════════════════════╗")
    print("║    LOOP TEST                           ║")
    print("╚════════════════════════════════════════╝")
    print("\nTesting dispatch with tick loop...")

    -- Locate tree by module name_hash  (COMPLEX_SEQUENCE_TEST_HASH in C)
    local md         = mod.module_data
    local test_hash  = md.name_hash   -- the module's own hash is the test tree hash
    local tree_name  = mod.trees_by_hash[test_hash]

    -- Fallback: if name_hash doesn't match a tree hash, use the first tree
    if not tree_name then
        for _, tname in ipairs(md.tree_order or {}) do
            local tree = md.trees[tname]
            if tree and tree.name_hash == test_hash then
                tree_name = tname
                break
            end
        end
    end
    if not tree_name then
        tree_name = md.tree_order and md.tree_order[1]
    end

    if not tree_name then
        print("  ❌ FAILED: Could not locate tree")
        return
    end

    print(string.format("  Tree: %s", tree_name))

    local inst       = se_runtime.new_instance(mod, tree_name)
    local tick_count = 0
    local result

    print("\n  Running tick loop...")

    repeat
        -- Primary tick
        result = se_runtime.tick_once(inst, R.SE_EVENT_TICK, nil)
        tick_count = tick_count + 1
        delay_seconds(TICK_DELAY_SEC)
        print(string.format(
            "------------------------>    Tick %3d: result=%s",
            tick_count, result_to_str(result)))

        -- Event queue drain
        local event_count = se_runtime.event_count(inst)
        while event_count > 0 do
            local tick_type, event_id, event_data = se_runtime.event_pop(inst)
            local saved        = inst.tick_type
            inst.tick_type     = tick_type
            local event_result = se_runtime.tick_once(inst, event_id, event_data)
            inst.tick_type     = saved
            if result_is_complete(event_result) then
                result = event_result
                break
            end
            event_count = se_runtime.event_count(inst)
        end

    until result_is_complete(result) or tick_count >= MAX_TICKS

    print(string.format("\n  Total ticks: %d", tick_count))
    print(string.format("  Final result: %s", result_to_str(result)))

    if result_is_terminate(result) then
        print("\n  ✅ PASSED - Tree terminated normally")
    elseif tick_count >= MAX_TICKS then
        print("\n  ❌ FAILED - Max ticks exceeded without termination")
    elseif result_is_complete(result) then
        print("\n  ✅ PASSED - Tree completed (disabled)")
    else
        print("\n  ❌ FAILED - Unexpected result")
    end
end

-- ============================================================================
-- MAIN
-- ============================================================================

print()
print("╔════════════════════════════════════════════════════════════════╗")
print("║           S-EXPRESSION ENGINE DISPATCH TEST                    ║")
print("╚════════════════════════════════════════════════════════════════╝")
print()

-- ---- Test 1: require() load — analogous to s_engine_load_from_rom ----------

print("=== Loading module from ROM ===\n")

local mod, err = load_module("complex_sequence_module")
if not mod then
    print(string.format("❌ FATAL: Failed to load module: %s", err))
    os.exit(1)
end
print("✅ Module loaded successfully")
local md = mod.module_data
print(string.format("   Trees:    %d", md.tree_order and #md.tree_order or 0))
print(string.format("   Oneshot:  %d", md.oneshot_funcs and #md.oneshot_funcs or 0))
print(string.format("   Main:     %d", md.main_funcs    and #md.main_funcs    or 0))
print(string.format("   Pred:     %d", md.pred_funcs    and #md.pred_funcs    or 0))

test_dispatch(mod)



print("\n✅ All tests completed!\n")

