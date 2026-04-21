#!/usr/bin/env luajit
--[[
  main.lua - CLI entry point for ChainTree Pipeline (LuaJIT)
  
  Usage:
    luajit main.lua <input_file> <output_dir> [handle_name] [--no-support]
  
  Arguments:
    input_file   : Path to ChainTree JSON configuration
    output_dir   : Directory for generated .h/.c files
    handle_name  : Name for the handle type (default: chaintree_handle)
    --no-support : Skip generating chaintree_support.h/.c
--]]

-- Add script directory to package path so requires work
local script_dir = arg[0]:match("^(.*)/") or "."
package.path = script_dir .. "/?.lua;" .. package.path

local PipelineOrchestrator = require("orchestrator")

-- Parse arguments
if #arg < 2 then
    print("Usage: luajit main.lua <input_file> <output_dir> [handle_name] [--no-support]")
    print("")
    print("  input_file   : Path to ChainTree JSON configuration")
    print("  output_dir   : Directory for generated .h/.c files")
    print("  handle_name  : Name for the handle type (default: chaintree_handle)")
    print("  --no-support : Skip generating chaintree_support.h/.c")
    os.exit(1)
end

local input_file = arg[1]
local output_dir = arg[2]
local handle_name = "chaintree_handle"
local generate_support = true

for i = 3, #arg do
    if arg[i] == "--no-support" then
        generate_support = false
    else
        handle_name = arg[i]
    end
end

-- Verify input file exists
local f = io.open(input_file, "r")
if not f then
    print("Error: " .. input_file .. " not found.")
    os.exit(1)
end
f:close()

-- Run pipeline
local orch = PipelineOrchestrator.new({
    input_file = input_file,
    output_dir = output_dir,
    handle_name = handle_name,
    generate_support = generate_support,
})

orch:run()