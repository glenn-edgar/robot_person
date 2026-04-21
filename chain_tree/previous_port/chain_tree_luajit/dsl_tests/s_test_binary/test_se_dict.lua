#!/usr/bin/env luajit
-- test_se_dict.lua — test harness for S-Engine integration (dict-based runtime)
-- Runs tests from s_engine_test.json
--
-- Usage: luajit test_se_dict.lua [kb_name_or_index]

-- Resolve paths
local script_dir = arg[0]:match("(.*/)")  or "./"
local root_dir   = script_dir .. "../../"
local se_rt_dir  = root_dir .. "s_expression/lua_runtime/"
local se_tests   = root_dir .. "s_expression/dsl_tests/"

-- Set up LUA_PATH
package.path = root_dir .. "runtime_dict/?.lua;"
             .. script_dir .. "?.lua;"
             .. se_rt_dir .. "?.lua;"
             .. se_tests .. "state_machine/?.lua;"
             .. package.path
package.cpath = "/usr/local/lib/lua/5.1/?.so;" .. package.cpath

local ct_runtime  = require("ct_runtime")
local loader      = require("ct_loader")
local builtins    = require("ct_builtins")
local se_bridge   = require("ct_se_bridge")

-- JSON file path
local json_path = script_dir .. "s_engine_test.json"

-- KB index-to-name mapping
local kb_by_index = {
    [0] = "se_basic_load_test",
    [1] = "se_multi_tree_test",
    [2] = "se_custom_bb_test",
}

-- Select test KB
local kb_arg = arg[1] or "se_basic_load_test"
local kb_name = tonumber(kb_arg) and kb_by_index[tonumber(kb_arg)] or kb_arg

if not kb_name then
    print("FAIL: unknown KB index " .. kb_arg)
    os.exit(1)
end

print("=== S-Engine Dict Runtime Test ===")
print("Loading: " .. json_path)

-- Load JSON IR
local handle_data = loader.load(json_path)

-- User functions (booleans called during SE module load)
local user_fns = { main = {}, one_shot = {}, boolean = {} }

-- USER_REGISTER_S_FUNCTIONS: called during module load, returns false (use default)
user_fns.boolean.USER_REGISTER_S_FUNCTIONS = function(handle, node, event_id, event_data)
    return false
end

-- SE_CUSTOM_BB_LOAD: returns true to skip default BB loading
user_fns.boolean.SE_CUSTOM_BB_LOAD = function(handle, node, event_id, event_data)
    print("SE_CUSTOM_BB_LOAD: custom blackboard loading")
    return true
end

-- Register all functions (builtins + bridge + user)
loader.register_functions(handle_data, builtins, se_bridge, user_fns)

-- Validate
local ok, missing = loader.validate(handle_data, kb_name)
if not ok then
    print("FAIL: missing functions for " .. kb_name .. ":")
    for _, m in ipairs(missing) do print("  " .. m) end
    os.exit(1)
end

print("Running KB: " .. kb_name)
print(string.rep("-", 60))

-- Create runtime handle
local handle = ct_runtime.create({
    delta_time = 0.001,  -- fast for testing
    max_ticks = 50000,
}, handle_data)

ct_runtime.reset(handle)

-- Create SE registry and pre-register modules
se_bridge.create_registry(handle)

-- Register state_machine_test module
se_bridge.register_def(handle.se_registry, "state_machine_test",
    function() return require("state_machine_test_module") end)

-- Register dummy modules for tests 2 and 3
-- Helper: create a minimal SE module with a single-node tree that disables immediately
local function make_dummy_module(tree_names)
    local trees = {}
    local tree_order = {}
    for _, name in ipairs(tree_names) do
        trees[name] = {
            nodes = {{ call_type = "m_call", func_name = "se_return_disable",
                       children = {}, params = {} }},
            node_count = 1,
        }
        tree_order[#tree_order + 1] = name
    end
    return {
        trees = trees,
        tree_order = tree_order,
        main_funcs = { "se_return_disable" },
        oneshot_funcs = {},
        pred_funcs = {},
        string_table = {},
    }
end

se_bridge.register_def(handle.se_registry, "se_multi_module",
    function() return make_dummy_module({"tree_alpha", "tree_beta"}) end)

se_bridge.register_def(handle.se_registry, "se_custom_module",
    function() return make_dummy_module({"se_custom_tree"}) end)

-- Add test and run
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
