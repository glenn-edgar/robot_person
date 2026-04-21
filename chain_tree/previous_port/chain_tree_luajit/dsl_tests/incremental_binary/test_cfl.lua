#!/usr/bin/env luajit
-- test_cfl.lua — test harness for CFL runtime (C-compatible)
-- Runs tests from incremental_build.json
--
-- Usage: luajit test_cfl.lua [kb_name_or_index]
-- Default: first_test
-- Special: "all" runs all KBs sequentially

-- Resolve paths
local script_dir = arg[0]:match("(.*/)")  or "./"
local root_dir   = script_dir .. "../../"

-- Set up LUA_PATH for CFL runtime modules + local user functions + FFI schemas
package.path  = root_dir .. "runtime/?.lua;" .. script_dir .. "?.lua;" ..
                script_dir .. "?_ffi.lua;" .. package.path
-- Ensure LuaJIT-compatible cjson (5.1) is found before 5.4
package.cpath = "/usr/local/lib/lua/5.1/?.so;" .. package.cpath

local cfl_runtime = require("cfl_runtime")
local loader      = require("cfl_json_loader")
local builtins    = require("cfl_builtins")
local sm          = require("cfl_state_machine")
local user_fns    = require("user_functions_cfl")

-- JSON file path
local json_path = script_dir .. "incremental_build.json"

-- KB index-to-name mapping (matches C test harness ordering from DSL test_list)
local kb_by_index = {
    [0]  = "first_test",
    [1]  = "second_test",
    [2]  = "fourth_test",
    [3]  = "fifth_test",
    [4]  = "sixth_test",
    [5]  = "seventh_test",
    [6]  = "eighth_test",
    [7]  = "ninth_test",
    [8]  = "tenth_test",
    [9]  = "eleventh_test",
    [10] = "twelfth_test",
    [11] = "thirteenth_test",
    [12] = "fourteenth_test",
    [13] = "seventeenth_test",
    [14] = "eighteenth_test",
    [15] = "ninteenth_test",
    [16] = "twentieth_test",
    [17] = "twenty_first_test",
    [18] = "twenty_second_test",
    [19] = "twenty_third_test",
    [20] = "twenty_fourth_test",
    [21] = "twenty_fifth_test",
    [22] = "twenty_sixth_test",
    [23] = "twenty_seventh_test",
    [24] = "twenty_eighth_test",
    [25] = "twenty_ninth_test",
}

-- Reverse map: name -> index
local kb_name_to_index = {}
for idx, name in pairs(kb_by_index) do
    kb_name_to_index[name] = idx
end

-- Load JSON IR (once)
local flash_handle = loader.load(json_path)

-- Register all functions: builtins + state machine + user functions
loader.register_functions(flash_handle, builtins, sm, user_fns)

-- Validate all functions are registered
local ok, missing = loader.validate(flash_handle)
if not ok then
    print("WARNING: missing functions:")
    for _, m in ipairs(missing) do
        print("  " .. m.kind .. ": " .. m.name)
    end
end

-- Helper: find KB index (0-based) by name
local function find_kb_index(flash, name)
    for i, kb in ipairs(flash.kb_table) do
        if kb.name == name then
            return i - 1  -- 0-based
        end
    end
    return nil
end

-- Wallclock timer
local ffi = require("ffi")
pcall(ffi.cdef, "typedef struct { long tv_sec; long tv_nsec; } cfl_timespec_t;")
pcall(ffi.cdef, "int clock_gettime(int clk_id, cfl_timespec_t *tp);")
local function walltime()
    local ts = ffi.new("cfl_timespec_t")
    ffi.C.clock_gettime(1, ts)  -- CLOCK_MONOTONIC
    return tonumber(ts.tv_sec) + tonumber(ts.tv_nsec) * 1e-9
end

-- Run a single KB test
local function run_test(kb_name)
    local kb_idx = find_kb_index(flash_handle, kb_name)
    if not kb_idx then
        print("FAIL: KB '" .. kb_name .. "' not found in JSON IR")
        return false
    end

    print("Running KB: " .. kb_name .. " (index " .. kb_idx .. ")")
    print(string.rep("-", 60))

    local handle = cfl_runtime.create({
        delta_time = 0.1,
        max_ticks  = 5000,
    }, flash_handle)

    cfl_runtime.reset(handle)

    local added = cfl_runtime.add_test(handle, kb_idx)
    if not added then
        print("FAIL: could not add test " .. kb_name)
        return false
    end

    local wall_start = walltime()
    local result = cfl_runtime.run(handle)
    local wall_elapsed = walltime() - wall_start

    local sim_time = handle.timer and handle.timer.timestamp or 0
    local status = result and "PASS" or "FAIL"

    print(string.rep("-", 60))
    print(string.format("=== Result: %s ===", status))
    print(string.format("Sim ticks: %d  Sim time: %.1fs  Wall time: %.3fs",
        handle.tick_count or 0, sim_time, wall_elapsed))
    print("")

    return result
end

-- ============================================================================
-- Main
-- ============================================================================
print("=== CFL Runtime (C-Compatible) Test Harness ===")
print("Loading: " .. json_path)
print("")

local kb_arg = arg[1] or "first_test"

if kb_arg == "all" then
    -- Run all tests sequentially
    local pass_count, fail_count, skip_count = 0, 0, 0
    for i = 0, 25 do
        local name = kb_by_index[i]
        if name then
            local ok = run_test(name)
            if ok then pass_count = pass_count + 1
            else fail_count = fail_count + 1 end
        end
    end
    print(string.rep("=", 60))
    print(string.format("TOTAL: %d passed, %d failed", pass_count, fail_count))
else
    -- Single test
    local kb_name = tonumber(kb_arg) and kb_by_index[tonumber(kb_arg)] or kb_arg
    if not kb_name then
        print("FAIL: unknown KB '" .. kb_arg .. "'")
        print("Valid: 0-25 or KB name or 'all'")
        os.exit(1)
    end
    local ok = run_test(kb_name)
    if not ok then os.exit(1) end
end
