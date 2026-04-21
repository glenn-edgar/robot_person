#!/usr/bin/env luajit
-- test_dict.lua — test harness for dict-based ChainTree runtime
-- Runs tests from incremental_build.json
--
-- Usage: luajit test_dict.lua [kb_name]
-- Default: first_test

-- Resolve paths
local script_dir = arg[0]:match("(.*/)")  or "./"
local root_dir   = script_dir .. "../../"

-- Set up LUA_PATH for runtime_dict modules + local user functions + FFI schemas
package.path  = root_dir .. "runtime_dict/?.lua;" .. script_dir .. "?.lua;" ..
                script_dir .. "?_ffi.lua;" .. package.path
-- Ensure LuaJIT-compatible cjson (5.1) is found before 5.4
package.cpath = "/usr/local/lib/lua/5.1/?.so;" .. package.cpath

local ct_runtime = require("ct_runtime")
local loader     = require("ct_loader")
local builtins   = require("ct_builtins")
local user_fns   = require("user_functions_dict")

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

-- Select test KB: accept index (number) or name (string)
local kb_arg = arg[1] or "first_test"
local kb_name = tonumber(kb_arg) and kb_by_index[tonumber(kb_arg)] or kb_arg

if not kb_name then
    print("FAIL: unknown KB index " .. kb_arg)
    print("Valid indices: 0-" .. 25)
    os.exit(1)
end

print("=== Dict-Based ChainTree Runtime ===")
print("Loading: " .. json_path)

-- Load JSON IR
local handle_data = loader.load(json_path)

-- Register all functions
loader.register_functions(handle_data, builtins, user_fns)

-- Validate only the selected KB's functions
local ok, missing = loader.validate(handle_data, kb_name)
if not ok then
    print("FAIL: missing functions for " .. kb_name .. ":")
    for _, m in ipairs(missing) do
        print("  " .. m)
    end
    os.exit(1)
end

print("Running KB: " .. kb_name)
print(string.rep("-", 60))

-- Create and run (max_ticks high enough for long tests)
local handle = ct_runtime.create({
    delta_time = 0.1,
    max_ticks = 5000,
}, handle_data)

ct_runtime.reset(handle)

local added = ct_runtime.add_test(handle, kb_name)
if not added then
    print("FAIL: could not add test " .. kb_name)
    os.exit(1)
end

local ffi = require("ffi")
pcall(ffi.cdef, "typedef struct { long tv_sec; long tv_nsec; } ct_log_timespec_t;")
pcall(ffi.cdef, "int clock_gettime(int clk_id, ct_log_timespec_t *tp);")
local function walltime()
    local ts = ffi.new("ct_log_timespec_t")
    ffi.C.clock_gettime(1, ts)  -- CLOCK_MONOTONIC
    return tonumber(ts.tv_sec) + tonumber(ts.tv_nsec) * 1e-9
end

local wall_start = walltime()
local result = ct_runtime.run(handle)
local wall_elapsed = walltime() - wall_start

local status = result and "PASS" or "FAIL"

print(string.rep("-", 60))
print(string.format("=== Result: %s ===", status))
print(string.format("Sim ticks: %d  Sim time: %.1fs  Wall time: %.3fs",
    handle.tick_count, handle.timestamp, wall_elapsed))
