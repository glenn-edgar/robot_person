--[[
  orchestrator.lua - ChainTree Pipeline Orchestrator
  
  LuaJIT port of orchestrator.py
  
  Coordinates the 6-stage pipeline for generating C header files from ChainTree JSON:
    Stage 1: Load JSON data         (stage1_handle.lua)
    Stage 2: Build node ordering    (stage2_node_index.lua)
    Stage 3: Build function indices (stage3_function_index.lua)
    Stage 4: Build link tables      (stage4_link_table.lua)
    Stage 5: Encode node data       (stage5_node_data.lua)
    Stage 6: Generate C files       (stage6_codegen.lua)
  
  Usage:
    local Orchestrator = require("orchestrator")
    local orch = Orchestrator.new({
        input_file   = "chaintree_config.json",
        output_dir   = "./generated",
        handle_name  = "my_chaintree",
    })
    orch:run()
--]]

local ChainTreeHandle    = require("stage1_handle")
local NodeIndexBuilder   = require("stage2_node_index")
local FunctionIndexBuilder = require("stage3_function_index")
local LinkTableBuilder   = require("stage4_link_table")
local NodeDataEncoder    = require("stage5_node_data")
local CCodeGenerator     = require("stage6_codegen")

local PipelineOrchestrator = {}
PipelineOrchestrator.__index = PipelineOrchestrator

-- Simple random ID generator (LuaJIT-compatible)
local function generate_unique_id()
    math.randomseed(os.time() + os.clock() * 1000)
    local chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    local parts = {}
    for i = 1, 8 do
        local idx = math.random(1, #chars)
        parts[i] = chars:sub(idx, idx)
    end
    return "ct_" .. table.concat(parts)
end

function PipelineOrchestrator.new(opts)
    local self = setmetatable({}, PipelineOrchestrator)
    self.input_file = opts.input_file
    self.handle_name = opts.handle_name or "chaintree_handle"
    self.output_dir = opts.output_dir or "."
    self.generate_support_header = (opts.generate_support ~= false)
    self.unique_id = generate_unique_id()
    
    -- Stage objects (populated during run)
    self.handle = nil
    self.node_builder = nil
    self.function_builder = nil
    self.link_builder = nil
    self.data_encoder = nil
    self.code_generator = nil
    self.main_function_usage = {}
    return self
end

function PipelineOrchestrator:run()
    print(string.rep("=", 70))
    print("ChainTree Pipeline (LuaJIT)")
    print(string.rep("=", 70))
    print("  Input file:  " .. self.input_file)
    print("  Output dir:  " .. self.output_dir)
    print("  Handle name: " .. self.handle_name)
    print("  Unique ID:   " .. self.unique_id)
    print()
    
    -- Ensure output directory exists
    os.execute("mkdir -p " .. self.output_dir)
    
    self:_run_stage1()
    self:_run_stage2()
    self:_run_stage3()
    self:_run_stage4()
    self:_run_stage5()
    self:_count_main_function_usage()
    self:_run_stage6()
    
    print()
    print(string.rep("=", 70))
    print("Pipeline completed successfully!")
    print(string.rep("=", 70))
end

-- =========================================================================
-- Individual Stage Runners
-- =========================================================================

function PipelineOrchestrator:_run_stage1()
    print("Stage 1: Loading JSON data...")
    self.handle = ChainTreeHandle.new(self.input_file)
    self.handle:print_summary()
end

function PipelineOrchestrator:_run_stage2()
    print("\nStage 2: Building node ordering...")
    self.node_builder = NodeIndexBuilder.new(self.handle)
    self.node_builder:build()
    self.node_builder:print_summary()
end

function PipelineOrchestrator:_run_stage3()
    print("\nStage 3: Building function indices...")
    self.function_builder = FunctionIndexBuilder.new(self.handle)
    self.function_builder:build()
    self.function_builder:print_summary()
end

function PipelineOrchestrator:_run_stage4()
    print("\nStage 4: Building link tables...")
    self.link_builder = LinkTableBuilder.new(self.handle, self.node_builder)
    self.link_builder:build()
    self.link_builder:print_summary()
end

function PipelineOrchestrator:_run_stage5()
    print("\nStage 5: Encoding node data...")
    self.data_encoder = NodeDataEncoder.new(self.handle, self.node_builder, self.function_builder)
    self.data_encoder:build()
    self.data_encoder:print_summary()
end

function PipelineOrchestrator:_count_main_function_usage()
    print("\nCounting main function usage...")
    
    for i = 0, self.function_builder.main_indexer:get_count() - 1 do
        self.main_function_usage[i] = 0
    end
    
    for ltree_name in pairs(self.node_builder.ltree_to_final_index) do
        local functions = self.handle:get_node_functions(ltree_name)
        local main_func = functions.main
        
        if main_func and main_func ~= "CFL_NULL" then
            local ok, func_index = pcall(self.function_builder.main_indexer.get_index,
                                         self.function_builder.main_indexer, main_func)
            if ok then
                self.main_function_usage[func_index] = (self.main_function_usage[func_index] or 0) + 1
            end
        end
    end
    
    local total = 0
    for _, count in pairs(self.main_function_usage) do total = total + count end
    print(string.format("  Total main function references: %d", total))
end

function PipelineOrchestrator:_run_stage6()
    print("\nStage 6: Generating C header and implementation files...")
    
    self.code_generator = CCodeGenerator.new({
        output_dir = self.output_dir,
        handle_name = self.handle_name,
        unique_id = self.unique_id,
        handle = self.handle,
        node_builder = self.node_builder,
        function_builder = self.function_builder,
        link_builder = self.link_builder,
        data_encoder = self.data_encoder,
        main_function_usage = self.main_function_usage,
        generate_support = self.generate_support_header,
    })
    
    self.code_generator:generate_all()
end

return PipelineOrchestrator