#!/usr/bin/env luajit
-- test_se2_dict.lua - S-Engine integration test 2 harness (dict-based runtime)
-- Usage: luajit test_se2_dict.lua [kb_name_or_index]

local script_dir = arg[0]:match("(.*/)")  or "./"
local root_dir   = script_dir .. "../../"
local se_rt_dir  = root_dir .. "s_expression/lua_runtime/"

package.path = root_dir .. "runtime_dict/?.lua;"
             .. script_dir .. "?.lua;"
             .. se_rt_dir .. "?.lua;"
             .. package.path
package.cpath = "/usr/local/lib/lua/5.1/?.so;" .. package.cpath

local ct_runtime  = require("ct_runtime")
local loader      = require("ct_loader")
local builtins    = require("ct_builtins")
local se_bridge   = require("ct_se_bridge")
local se          = require("se_runtime")

local json_path = script_dir .. "s_engine_test_2.json"

local kb_by_index = {
    [0] = "twenty_ninth_test",
    [1] = "thirty_test",
    [2] = "thirty_one_test",
}

local kb_arg = arg[1] or "twenty_ninth_test"
local kb_name = tonumber(kb_arg) and kb_by_index[tonumber(kb_arg)] or kb_arg

if not kb_name then
    print("FAIL: unknown KB index " .. kb_arg)
    os.exit(1)
end

print("=== S-Engine Test 2 Dict Runtime ===")
print("Loading: " .. json_path)

local handle_data = loader.load(json_path)

loader.register_functions(handle_data, builtins, se_bridge)

local ok, missing = loader.validate(handle_data, kb_name)
if not ok then
    print("FAIL: missing functions for " .. kb_name .. ":")
    for _, m in ipairs(missing) do print("  " .. m) end
    os.exit(1)
end

print("Running KB: " .. kb_name)
print(string.rep("-", 60))

local handle = ct_runtime.create({
    delta_time = 0.1,
    max_ticks = 500,
}, handle_data)

ct_runtime.reset(handle)
se_bridge.create_registry(handle)

-- SE-level user functions (called inside s-engine trees)
local se_user_fns = require("se_user_functions")

-- Register module from pre-compiled _module.lua
se_bridge.register_def(handle.se_registry, "chain_flow_dsl_tests",
    function() return require("chain_flow_dsl_tests_module") end,
    se_user_fns)

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
    ffi.C.clock_gettime(1, ts)
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
