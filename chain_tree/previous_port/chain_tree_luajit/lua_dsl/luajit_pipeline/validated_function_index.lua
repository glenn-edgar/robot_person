--[[
  validated_function_index.lua - Function name-to-index mapping with validity tracking.
  
  LuaJIT port of validated_function_index.py
--]]

local ValidatedFunctionIndexer = {}
ValidatedFunctionIndexer.__index = ValidatedFunctionIndexer

function ValidatedFunctionIndexer.new(name)
    local self = setmetatable({}, ValidatedFunctionIndexer)
    self.name = name or "functions"
    self.function_to_index = {}   -- name -> index (0-based)
    self.index_to_function = {}   -- array of names (1-based Lua, but index values are 0-based)
    self.function_valid = {}      -- name -> bool
    self.function_prototypes = {} -- name -> string
    self.function_source_files = {} -- name -> string
    return self
end

function ValidatedFunctionIndexer:add_function(function_name)
    if self.function_to_index[function_name] ~= nil then
        return self.function_to_index[function_name]
    end
    
    local index = #self.index_to_function  -- 0-based index
    self.function_to_index[function_name] = index
    self.index_to_function[#self.index_to_function + 1] = function_name
    self.function_valid[function_name] = false
    self.function_prototypes[function_name] = ""
    self.function_source_files[function_name] = ""
    return index
end

function ValidatedFunctionIndexer:set_function_valid(function_name, valid, prototype, source_file)
    if valid == nil then valid = true end
    if self.function_to_index[function_name] == nil then
        error("Function not indexed: " .. function_name)
    end
    self.function_valid[function_name] = valid
    if prototype and prototype ~= "" then
        self.function_prototypes[function_name] = prototype
    end
    if source_file and source_file ~= "" then
        self.function_source_files[function_name] = source_file
    end
end

function ValidatedFunctionIndexer:register_implementation(function_name, prototype, source_file)
    local index = self:add_function(function_name)
    self:set_function_valid(function_name, true, prototype, source_file)
    return index
end

function ValidatedFunctionIndexer:is_valid(function_name)
    if self.function_to_index[function_name] == nil then
        error("Function not indexed: " .. function_name)
    end
    return self.function_valid[function_name]
end

function ValidatedFunctionIndexer:get_invalid_functions()
    local result = {}
    for name, valid in pairs(self.function_valid) do
        if not valid then result[#result + 1] = name end
    end
    return result
end

function ValidatedFunctionIndexer:get_valid_functions()
    local result = {}
    for name, valid in pairs(self.function_valid) do
        if valid then result[#result + 1] = name end
    end
    return result
end

function ValidatedFunctionIndexer:all_functions_valid()
    for _, valid in pairs(self.function_valid) do
        if not valid then return false end
    end
    return true
end

function ValidatedFunctionIndexer:get_index(function_name)
    if self.function_to_index[function_name] == nil then
        error("Function not indexed: " .. function_name)
    end
    return self.function_to_index[function_name]
end

function ValidatedFunctionIndexer:get_function(index)
    -- index is 0-based, Lua array is 1-based
    local name = self.index_to_function[index + 1]
    if not name then
        error("Function index out of range: " .. index)
    end
    return name
end

function ValidatedFunctionIndexer:get_all_functions()
    local copy = {}
    for i = 1, #self.index_to_function do
        copy[i] = self.index_to_function[i]
    end
    return copy
end

function ValidatedFunctionIndexer:get_count()
    return #self.index_to_function
end

-- =========================================================================
-- C Code Generation Helpers
-- =========================================================================

function ValidatedFunctionIndexer:generate_c_enum(enum_name)
    local lines = {}
    lines[#lines + 1] = "typedef enum {"
    for i, func_name in ipairs(self.index_to_function) do
        local idx = i - 1  -- 0-based
        lines[#lines + 1] = string.format("    %s_%s = %d,", enum_name, func_name:upper(), idx)
    end
    lines[#lines + 1] = string.format("    %s_COUNT = %d", enum_name, #self.index_to_function)
    lines[#lines + 1] = string.format("} %s_t;", enum_name)
    return table.concat(lines, "\n")
end

function ValidatedFunctionIndexer:generate_c_string_array(array_name)
    local lines = {}
    lines[#lines + 1] = string.format("const char *%s[%d] = {", array_name, #self.index_to_function)
    for _, func_name in ipairs(self.index_to_function) do
        lines[#lines + 1] = string.format('    "%s",', func_name)
    end
    lines[#lines + 1] = "};"
    return table.concat(lines, "\n")
end

function ValidatedFunctionIndexer:print_summary()
    local valid_count = 0
    local total = 0
    for _, v in pairs(self.function_valid) do
        total = total + 1
        if v then valid_count = valid_count + 1 end
    end
    print(string.format("  %s:", self.name))
    print(string.format("    Total functions: %d", total))
    print(string.format("    Valid functions: %d", valid_count))
    print(string.format("    Invalid functions: %d", total - valid_count))
end

return ValidatedFunctionIndexer