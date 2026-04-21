--[[
  stage3_function_index.lua - Build function index tables.
  LuaJIT port of stage3_function_index.py
--]]

local ValidatedFunctionIndexer = require("validated_function_index")

local FunctionIndexBuilder = {}
FunctionIndexBuilder.__index = FunctionIndexBuilder

function FunctionIndexBuilder.new(handle)
    local self = setmetatable({}, FunctionIndexBuilder)
    self.handle = handle
    self.main_indexer = ValidatedFunctionIndexer.new("main_function")
    self.one_shot_indexer = ValidatedFunctionIndexer.new("one_shot_function")
    self.boolean_indexer = ValidatedFunctionIndexer.new("boolean_function")
    self.main_name_map = {}
    self.one_shot_name_map = {}
    self.boolean_name_map = {}
    return self
end

local function make_typed_name(func_name, suffix)
    return func_name:lower() .. "_" .. suffix
end

local function sorted_set_keys(set_tbl)
    local keys = {}
    for k in pairs(set_tbl) do keys[#keys + 1] = k end
    table.sort(keys)
    return keys
end

function FunctionIndexBuilder:build()
    local all_functions = self.handle:get_all_functions()
    
    -- Main functions
    self.main_indexer:add_function("CFL_NULL")
    self.main_indexer:set_function_valid("CFL_NULL", true,
        "unsigned cfl_null_main_fn(void *handle, unsigned bool_function_index, unsigned node_index, unsigned event_type, unsigned event_id, void *event_data)",
        "builtin")
    self.main_name_map["CFL_NULL"] = make_typed_name("CFL_NULL", "main")
    
    for _, fn in ipairs(sorted_set_keys(all_functions.main)) do
        if fn ~= "CFL_NULL" then
            self.main_name_map[fn] = make_typed_name(fn, "main")
            self.main_indexer:add_function(fn)
        end
    end
    
    -- One-shot functions
    self.one_shot_indexer:add_function("CFL_NULL")
    self.one_shot_indexer:set_function_valid("CFL_NULL", true,
        "void cfl_null_one_shot_fn(void *handle, unsigned node_index)",
        "builtin")
    self.one_shot_name_map["CFL_NULL"] = make_typed_name("CFL_NULL", "one_shot")
    
    for _, fn in ipairs(sorted_set_keys(all_functions.one_shot)) do
        if fn ~= "CFL_NULL" then
            self.one_shot_name_map[fn] = make_typed_name(fn, "one_shot")
            self.one_shot_indexer:add_function(fn)
        end
    end
    
    -- Boolean functions
    self.boolean_indexer:add_function("CFL_NULL")
    self.boolean_indexer:set_function_valid("CFL_NULL", true,
        "bool cfl_null_boolean_fn(void *handle, unsigned node_index, unsigned event_type, unsigned event_id, void *event_data)",
        "builtin")
    self.boolean_name_map["CFL_NULL"] = make_typed_name("CFL_NULL", "boolean")
    
    for _, fn in ipairs(sorted_set_keys(all_functions.boolean)) do
        if fn ~= "CFL_NULL" then
            self.boolean_name_map[fn] = make_typed_name(fn, "boolean")
            self.boolean_indexer:add_function(fn)
        end
    end
end

function FunctionIndexBuilder:get_typed_main_name(original_name)
    return self.main_name_map[original_name] or make_typed_name(original_name, "main")
end

function FunctionIndexBuilder:get_typed_one_shot_name(original_name)
    return self.one_shot_name_map[original_name] or make_typed_name(original_name, "one_shot")
end

function FunctionIndexBuilder:get_typed_boolean_name(original_name)
    return self.boolean_name_map[original_name] or make_typed_name(original_name, "boolean")
end

function FunctionIndexBuilder:print_summary()
    print(string.rep("=", 70))
    print("Stage 3: Function Index Builder Summary")
    print(string.rep("=", 70))
    print("Main functions: " .. self.main_indexer:get_count())
    print("One-shot functions: " .. self.one_shot_indexer:get_count())
    print("Boolean functions: " .. self.boolean_indexer:get_count())
end

return FunctionIndexBuilder