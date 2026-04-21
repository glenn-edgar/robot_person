--[[
  stage5_node_data.lua - Encode node data into compact JSON record format.
  LuaJIT port of stage5_node_data.py
  
  Uses LuaJIT FFI for float-to-uint32 reinterpretation.
--]]

local ffi = require("ffi")

-- Float <-> uint32 reinterpretation via FFI
local float_buf = ffi.new("float[1]")
local uint32_ptr = ffi.cast("uint32_t*", float_buf)

local function float_to_uint32(f)
    float_buf[0] = f
    return tonumber(uint32_ptr[0])
end

local function uint32_to_float(u)
    uint32_ptr[0] = u
    return tonumber(float_buf[0])
end

-- int32 <-> uint32
local int32_buf = ffi.new("int32_t[1]")
local uint32_buf = ffi.new("uint32_t[1]")

local function int32_to_uint32(i)
    int32_buf[0] = i
    return tonumber(ffi.cast("uint32_t*", int32_buf)[0])
end

local function uint32_to_int32(u)
    uint32_buf[0] = u
    return tonumber(ffi.cast("int32_t*", uint32_buf)[0])
end

-- =========================================================================
-- JsonRecordEncoder
-- =========================================================================

local JsonRecordEncoder = {}
JsonRecordEncoder.__index = JsonRecordEncoder

function JsonRecordEncoder.new()
    local self = setmetatable({}, JsonRecordEncoder)
    self:init()
    return self
end

function JsonRecordEncoder:init()
    self.string_table = {}    -- str -> offset
    self.string_data = {}     -- ordered list of strings
    self.next_offset = 0
    self.records = {}         -- array of { type_tag, value }
    self.record_controls = {} -- array of { start_position, num_records }
end

function JsonRecordEncoder:add_string(s)
    if self.string_table[s] ~= nil then
        return self.string_table[s]
    end
    local offset = self.next_offset
    self.string_table[s] = offset
    self.string_data[#self.string_data + 1] = s
    self.next_offset = self.next_offset + #s + 1  -- +1 for null terminator
    return offset
end

local function is_array(t)
    if type(t) ~= "table" then return false end
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    if count == 0 then return true end  -- empty -> array
    for i = 1, count do
        if t[i] == nil then return false end
    end
    return count == #t
end

function JsonRecordEncoder:encode_value(value)
    if value == nil then
        self.records[#self.records + 1] = { 3, 0 }  -- NULL
    elseif type(value) == "boolean" then
        self.records[#self.records + 1] = { 4, value and 1 or 0 }  -- BOOL
    elseif type(value) == "string" then
        local offset = self:add_string(value)
        self.records[#self.records + 1] = { 0, offset }  -- STRING
    elseif type(value) == "number" then
        if value == math.floor(value) and math.abs(value) < 2147483648 then
            -- Integer
            local clamped = math.max(-2147483648, math.min(2147483647, value))
            self.records[#self.records + 1] = { 1, int32_to_uint32(clamped) }  -- INT32
        else
            -- Float
            self.records[#self.records + 1] = { 2, float_to_uint32(value) }  -- FLOAT32
        end
    elseif type(value) == "table" then
        if is_array(value) then
            self.records[#self.records + 1] = { 5, #value }  -- ARRAY
            for _, item in ipairs(value) do
                self:encode_value(item)
            end
        else
            -- Count keys
            local key_count = 0
            for _ in pairs(value) do key_count = key_count + 1 end
            self.records[#self.records + 1] = { 6, key_count * 2 }  -- OBJECT
            for key, val in pairs(value) do
                local key_offset = self:add_string(tostring(key))
                self.records[#self.records + 1] = { 0, key_offset }
                self:encode_value(val)
            end
        end
    end
end

function JsonRecordEncoder:load_dict(obj)
    local start_position = #self.records
    self:encode_value(obj)
    local num_records = #self.records - start_position
    self.record_controls[#self.record_controls + 1] = {
        start_position = start_position,
        num_records = num_records,
    }
    return #self.record_controls - 1  -- 0-based index
end

-- =========================================================================
-- NodeDataEncoder
-- =========================================================================

local NodeDataEncoder = {}
NodeDataEncoder.__index = NodeDataEncoder

local FUNCTION_FIELDS = {
    error_function = "one_shot",
    boolean_function = "boolean",
    finalize_function = "one_shot",
    initialize_function = "one_shot",
    wd_fn = "one_shot",
    logging_function = "one_shot",
    user_aux_function = "boolean",
}

local NODE_REF_PATTERNS = {
    sm_node_id = true, target_node_id = true, parent_node_id = true,
    parent_node_name = true, next_node_id = true, prev_node_id = true,
}

function NodeDataEncoder.new(handle, node_builder, function_builder)
    local self = setmetatable({}, NodeDataEncoder)
    self.handle = handle
    self.node_builder = node_builder
    self.function_builder = function_builder
    self.encoder = JsonRecordEncoder.new()
    self.node_data_ids = {}  -- ltree_name -> data_id
    return self
end

local function has_meaningful_data(data)
    if data == nil then return false end
    if type(data) == "table" then
        local has_any = false
        for _, v in pairs(data) do
            if has_meaningful_data(v) then has_any = true; break end
        end
        return has_any
    end
    return true  -- string, number, bool
end

function NodeDataEncoder:_resolve_function_field(func_name, func_type)
    local indexer
    if func_type == "one_shot" then indexer = self.function_builder.one_shot_indexer
    elseif func_type == "main" then indexer = self.function_builder.main_indexer
    elseif func_type == "boolean" then indexer = self.function_builder.boolean_indexer
    else return nil end
    
    local ok, idx = pcall(indexer.get_index, indexer, func_name)
    if not ok then
        indexer:add_function(func_name)
        idx = indexer:get_index(func_name)
    end
    return idx
end

function NodeDataEncoder:_process_function_fields(data_dict)
    local result = {}
    for key, value in pairs(data_dict) do
        if FUNCTION_FIELDS[key] and type(value) == "string" then
            local func_type = FUNCTION_FIELDS[key]
            local func_id = self:_resolve_function_field(value, func_type)
            if func_id then
                result[key .. "_id"] = func_id
            else
                result[key] = value
            end
        elseif type(value) == "table" and not is_array(value) then
            result[key] = self:_process_function_fields(value)
        elseif type(value) == "table" and is_array(value) then
            local arr = {}
            for i, item in ipairs(value) do
                if type(item) == "table" and not is_array(item) then
                    arr[i] = self:_process_function_fields(item)
                else
                    arr[i] = item
                end
            end
            result[key] = arr
        else
            result[key] = value
        end
    end
    return result
end

local function ends_with(str, suffix)
    return str:sub(-#suffix) == suffix
end

function NodeDataEncoder:_process_node_reference_fields(data_dict)
    local result = {}
    for key, value in pairs(data_dict) do
        local copy_val = value
        
        if NODE_REF_PATTERNS[key] or
           ends_with(key, "_node_id") or
           ends_with(key, "_node_ref") or
           ends_with(key, "_node_name") then
            if type(value) == "string" and value:sub(1, 3) == "kb." then
                local node_index = self.node_builder.ltree_to_final_index[value]
                if node_index then
                    copy_val = node_index
                else
                    copy_val = 0xFFFF
                end
            end
        elseif type(value) == "table" and not is_array(value) then
            copy_val = self:_process_node_reference_fields(value)
        elseif type(value) == "table" and is_array(value) then
            local arr = {}
            for i, item in ipairs(value) do
                if type(item) == "table" and not is_array(item) then
                    arr[i] = self:_process_node_reference_fields(item)
                else
                    arr[i] = item
                end
            end
            copy_val = arr
        end
        
        result[key] = copy_val
    end
    return result
end

function NodeDataEncoder:build()
    local nodes_with_data = 0
    local nodes_skipped = 0
    
    for ltree_name in pairs(self.node_builder.ltree_to_final_index) do
        if self.node_builder.filtered_nodes[ltree_name] then
            goto continue
        end
        
        local node_data = self.handle:get_node_data(ltree_name)
        if not node_data then
            self.node_data_ids[ltree_name] = 0xFFFF
            nodes_skipped = nodes_skipped + 1
            goto continue
        end
        
        local encode_data = {}
        
        -- Custom data
        if node_data.data and has_meaningful_data(node_data.data) then
            encode_data.data = node_data.data
        end
        
        -- node_dict (exclude auto_start, resolve functions and node refs)
        if node_data.node_dict and type(node_data.node_dict) == "table" then
            local filtered = {}
            for k, v in pairs(node_data.node_dict) do
                if k ~= "auto_start" then filtered[k] = v end
            end
            if next(filtered) then
                filtered = self:_process_function_fields(filtered)
            end
            if next(filtered) then
                filtered = self:_process_node_reference_fields(filtered)
            end
            if has_meaningful_data(filtered) then
                encode_data.node_dict = filtered
            end
        end
        
        -- Other operational fields
        for _, key in ipairs({ "timeout", "priority", "config", "parameters" }) do
            if node_data[key] and has_meaningful_data(node_data[key]) then
                local fd = node_data[key]
                if type(fd) == "table" and not is_array(fd) then
                    fd = self:_process_node_reference_fields(fd)
                end
                encode_data[key] = fd
            end
        end
        
        if next(encode_data) then
            local data_id = self.encoder:load_dict(encode_data)
            self.node_data_ids[ltree_name] = data_id
            nodes_with_data = nodes_with_data + 1
        else
            self.node_data_ids[ltree_name] = 0xFFFF
            nodes_skipped = nodes_skipped + 1
        end
        
        ::continue::
    end
    
    print(string.format("\n  Summary: %d nodes with data, %d nodes skipped", nodes_with_data, nodes_skipped))
end

-- =========================================================================
-- C Code Generation
-- =========================================================================

local TYPE_NAMES = {
    [0] = "JSON_TYPE_STRING", [1] = "JSON_TYPE_INT32", [2] = "JSON_TYPE_FLOAT32",
    [3] = "JSON_TYPE_NULL", [4] = "JSON_TYPE_BOOL", [5] = "JSON_TYPE_ARRAY",
    [6] = "JSON_TYPE_OBJECT",
}

function NodeDataEncoder:generate_c_arrays(lines, unique_id)
    local enc = self.encoder
    
    -- Records array
    if #enc.records > 0 then
        lines[#lines + 1] = "/* JSON records array */"
        lines[#lines + 1] = string.format("const json_record_t %s_node_data_records[%d] = {", unique_id, #enc.records)
        
        for i, rec in ipairs(enc.records) do
            local tt, val = rec[1], rec[2]
            local line
            if tt == 0 then
                line = string.format("    { .object_type = %s, .value = { .string_offset = %d } }", TYPE_NAMES[tt], val)
            elseif tt == 1 then
                line = string.format("    { .object_type = %s, .value = { .i32_value = %d } }", TYPE_NAMES[tt], uint32_to_int32(val))
            elseif tt == 2 then
                line = string.format("    { .object_type = %s, .value = { .f32_value = %sf } }", TYPE_NAMES[tt], tostring(uint32_to_float(val)))
            elseif tt == 3 then
                line = string.format("    { .object_type = %s, .value = { .i32_value = 0 } }", TYPE_NAMES[tt])
            elseif tt == 4 then
                line = string.format("    { .object_type = %s, .value = { .bool_value = %d } }", TYPE_NAMES[tt], val)
            else -- 5, 6
                line = string.format("    { .object_type = %s, .value = { .container_count = %d } }", TYPE_NAMES[tt], val)
            end
            if i < #enc.records then line = line .. "," end
            lines[#lines + 1] = line
        end
        lines[#lines + 1] = "};"
        lines[#lines + 1] = ""
    end
    
    -- String table
    if #enc.string_data > 0 then
        local bytes = {}
        for _, s in ipairs(enc.string_data) do
            for ci = 1, #s do bytes[#bytes + 1] = string.byte(s, ci) end
            bytes[#bytes + 1] = 0
        end
        
        lines[#lines + 1] = "/* String data buffer */"
        lines[#lines + 1] = string.format("const char %s_node_data_strings[%d] = {", unique_id, #bytes)
        
        for i = 1, #bytes, 16 do
            local chunk = {}
            for j = i, math.min(i + 15, #bytes) do
                chunk[#chunk + 1] = string.format("0x%02x", bytes[j])
            end
            local line = "    " .. table.concat(chunk, ", ")
            if i + 16 <= #bytes then line = line .. "," end
            lines[#lines + 1] = line
        end
        lines[#lines + 1] = "};"
        lines[#lines + 1] = ""
    end
    
    -- Controls array
    if #enc.record_controls > 0 then
        lines[#lines + 1] = "/* Record control array */"
        lines[#lines + 1] = string.format("const record_control_t %s_node_data_controls[%d] = {", unique_id, #enc.record_controls)
        
        for i, ctrl in ipairs(enc.record_controls) do
            local line = string.format("    { .start_position = %d, .num_records = %d }", ctrl.start_position, ctrl.num_records)
            if i < #enc.record_controls then line = line .. "," end
            lines[#lines + 1] = line
        end
        lines[#lines + 1] = "};"
        lines[#lines + 1] = ""
    end
end

-- =========================================================================
-- Accessors
-- =========================================================================

function NodeDataEncoder:get_node_data_id(ltree_name)
    return self.node_data_ids[ltree_name] or 0xFFFF
end

function NodeDataEncoder:get_records_count()
    return #self.encoder.records
end

function NodeDataEncoder:get_strings_size()
    return self.encoder.next_offset
end

function NodeDataEncoder:get_controls_count()
    return #self.encoder.record_controls
end

function NodeDataEncoder:print_summary()
    local nodes_with_data = 0
    for _, id in pairs(self.node_data_ids) do
        if id ~= 0xFFFF then nodes_with_data = nodes_with_data + 1 end
    end
    print(string.rep("=", 70))
    print("Stage 5: Node Data Encoder Summary")
    print(string.rep("=", 70))
    print("Nodes with data: " .. nodes_with_data)
    print("Total JSON records: " .. #self.encoder.records)
    print("Unique strings: " .. #self.encoder.string_data)
    print("String table size: " .. self.encoder.next_offset .. " bytes")
end

return NodeDataEncoder