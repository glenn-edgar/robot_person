--[[
  stage1_handle.lua - Load and organize ChainTree JSON data.
  
  LuaJIT port of stage1_handle.py
  Loads structured JSON (schema v1.0) or legacy flat format.
--]]

local json = require("json_util")

local ChainTreeHandle = {}
ChainTreeHandle.__index = ChainTreeHandle

function ChainTreeHandle.new(input_file)
    local self = setmetatable({}, ChainTreeHandle)
    self.input_file = input_file
    
    -- Load JSON
    local f = io.open(input_file, "r")
    if not f then error("Cannot open file: " .. input_file) end
    local content = f:read("*a")
    f:close()
    
    self.raw_data = json.decode(content)
    
    -- Detect format
    self.schema_version = self.raw_data.schema_version
    
    if self.schema_version then
        self:_load_structured()
    else
        self:_load_legacy()
    end
    
    -- Organized storage
    self.kb_nodes = {}           -- kb_name -> { ltree_name -> node_data }
    self.kb_root_nodes = {}      -- kb_name -> root ltree_name
    self.special_table_nodes = {} -- set: ltree_name -> true
    
    -- Function collections (sets: name -> true)
    self.all_main_functions = {}
    self.all_one_shot_functions = {}
    self.all_boolean_functions = {}
    
    self:_parse_nodes()
    return self
end

function ChainTreeHandle:_load_structured()
    self.kb_log_dict = self.raw_data.kb_log_dict or {}
    self.ltree_to_index = self.raw_data.ltree_to_index or {}
    self.total_nodes = self.raw_data.total_nodes or 0
    self.kb_metadata = self.raw_data.kb_metadata or {}
    self.event_string_table = self.raw_data.event_string_table or {}
    self.bitmask_table = self.raw_data.bitmask_table or {}
    self.blackboard = self.raw_data.blackboard or nil
    self._node_source = self.raw_data.nodes or {}
end

function ChainTreeHandle:_load_legacy()
    self.kb_log_dict = self.raw_data.kb_log_dict or {}
    self.ltree_to_index = self.raw_data.ltree_to_index or {}
    self.total_nodes = self.raw_data.total_nodes or 0
    self.kb_metadata = self.raw_data.kb_metadata or {}
    self.event_string_table = {}
    self.bitmask_table = {}
    self._node_source = nil  -- signal to use raw_data
end

function ChainTreeHandle:_parse_nodes()
    local metadata_keys = {
        kb_log_dict = true, ltree_to_index = true,
        total_nodes = true, kb_metadata = true,
        schema_version = true, event_string_table = true,
        bitmask_table = true, nodes = true,
    }
    
    -- Determine node source
    local entries
    if self._node_source then
        entries = self._node_source
    else
        entries = self.raw_data
    end
    
    for ltree_name, node_data in pairs(entries) do
        if type(node_data) ~= "table" or metadata_keys[ltree_name] then
            goto continue
        end
        
        -- Parse ltree path
        local parts = {}
        for part in ltree_name:gmatch("[^%.]+") do
            parts[#parts + 1] = part
        end
        
        if #parts < 2 or parts[1] ~= "kb" then
            goto continue
        end
        
        local kb_name = parts[2]
        
        -- Handle special tables (legacy format only)
        if self._node_source == nil then
            if kb_name == "event_string_table_kb" then
                if node_data.node_dict then
                    for k, v in pairs(node_data.node_dict) do
                        self.event_string_table[k] = v
                    end
                end
                self.special_table_nodes[ltree_name] = true
                goto continue
            end
            if kb_name == "bitmask_table_kb" then
                if node_data.node_dict then
                    for k, v in pairs(node_data.node_dict) do
                        self.bitmask_table[k] = v
                    end
                end
                self.special_table_nodes[ltree_name] = true
                goto continue
            end
        end
        
        -- Regular node
        if not self.kb_nodes[kb_name] then
            self.kb_nodes[kb_name] = {}
        end
        self.kb_nodes[kb_name][ltree_name] = node_data
        
        -- Track root node (shortest path)
        if not self.kb_root_nodes[kb_name] or
           #ltree_name < #self.kb_root_nodes[kb_name] then
            self.kb_root_nodes[kb_name] = ltree_name
        end
        
        -- Collect function names
        local label_dict = node_data.label_dict
        if label_dict then
            local main_fn = label_dict.main_function_name
            if main_fn and main_fn ~= "CFL_NULL" then
                self.all_main_functions[main_fn] = true
            end
            
            local init_fn = label_dict.initialization_function_name
            if init_fn and init_fn ~= "CFL_NULL" then
                self.all_one_shot_functions[init_fn] = true
            end
            
            local term_fn = label_dict.termination_function_name
            if term_fn and term_fn ~= "CFL_NULL" then
                self.all_one_shot_functions[term_fn] = true
            end
            
            local aux_fn = label_dict.aux_function_name
            if aux_fn and aux_fn ~= "CFL_NULL" then
                self.all_boolean_functions[aux_fn] = true
            end
        end
        
        ::continue::
    end
end

-- =========================================================================
-- Query Methods - Knowledge Bases
-- =========================================================================

function ChainTreeHandle:get_kb_metadata_value(kb_name, key, default)
    local meta = self.kb_metadata[kb_name]
    if not meta then return default end
    local val = meta[key]
    if val == nil then return default end
    return val
end

function ChainTreeHandle:get_kb_node_aliases(kb_name)
    local meta = self.kb_metadata[kb_name]
    if not meta then return {} end
    return meta.node_aliases or {}
end

function ChainTreeHandle:get_kb_names()
    local names = {}
    for name in pairs(self.kb_nodes) do names[#names + 1] = name end
    return names
end

function ChainTreeHandle:get_kb_node_count(kb_name)
    local nodes = self.kb_nodes[kb_name]
    if not nodes then return 0 end
    local count = 0
    for _ in pairs(nodes) do count = count + 1 end
    return count
end

function ChainTreeHandle:get_kb_root_node(kb_name)
    return self.kb_root_nodes[kb_name]
end

-- =========================================================================
-- Query Methods - Nodes
-- =========================================================================

function ChainTreeHandle:get_node_data(ltree_name)
    for _, kb_nodes in pairs(self.kb_nodes) do
        if kb_nodes[ltree_name] then
            return kb_nodes[ltree_name]
        end
    end
    return nil
end

function ChainTreeHandle:get_node_index(ltree_name)
    return self.ltree_to_index[ltree_name]
end

function ChainTreeHandle:get_node_parent(ltree_name)
    local node_data = self:get_node_data(ltree_name)
    if node_data and node_data.label_dict then
        return node_data.label_dict.parent_ltree_name
    end
    return nil
end

function ChainTreeHandle:get_node_children(ltree_name)
    local node_data = self:get_node_data(ltree_name)
    if node_data and node_data.label_dict then
        return node_data.label_dict.links or {}
    end
    return {}
end

function ChainTreeHandle:get_node_label(ltree_name)
    local node_data = self:get_node_data(ltree_name)
    if node_data then return node_data.label end
    return nil
end

function ChainTreeHandle:get_node_name(ltree_name)
    local node_data = self:get_node_data(ltree_name)
    if node_data then return node_data.node_name end
    return nil
end

-- =========================================================================
-- Query Methods - Functions
-- =========================================================================

function ChainTreeHandle:get_node_functions(ltree_name)
    local node_data = self:get_node_data(ltree_name)
    if not node_data or not node_data.label_dict then return {} end
    local ld = node_data.label_dict
    return {
        main = ld.main_function_name or "CFL_NULL",
        init = ld.initialization_function_name or "CFL_NULL",
        aux = ld.aux_function_name or "CFL_NULL",
        term = ld.termination_function_name or "CFL_NULL",
    }
end

function ChainTreeHandle:get_all_functions()
    -- Return copies of the sets
    local function copy_set(s)
        local c = {}; for k in pairs(s) do c[k] = true end; return c
    end
    return {
        main = copy_set(self.all_main_functions),
        one_shot = copy_set(self.all_one_shot_functions),
        boolean = copy_set(self.all_boolean_functions),
    }
end

-- =========================================================================
-- Query Methods - Event/Bitmask Tables
-- =========================================================================

function ChainTreeHandle:get_event_string_table()
    local copy = {}
    for k, v in pairs(self.event_string_table) do copy[k] = v end
    return copy
end

function ChainTreeHandle:get_bitmask_table()
    local copy = {}
    for k, v in pairs(self.bitmask_table) do copy[k] = v end
    return copy
end

-- =========================================================================
-- Traversal
-- =========================================================================

function ChainTreeHandle:traverse_kb_breadth_first(kb_name)
    local root = self:get_kb_root_node(kb_name)
    if not root then return {} end
    
    local result = {}
    local queue = { root }
    local visited = {}
    local qi = 1
    
    while qi <= #queue do
        local current = queue[qi]
        qi = qi + 1
        
        if not visited[current] then
            visited[current] = true
            result[#result + 1] = current
            
            local children = self:get_node_children(current)
            for _, child in ipairs(children) do
                if not visited[child] then
                    queue[#queue + 1] = child
                end
            end
        end
    end
    
    return result
end

-- =========================================================================
-- Summary
-- =========================================================================

function ChainTreeHandle:print_summary()
    local fmt = self.schema_version and "JSON" or "Legacy"
    local ver = self.schema_version and (" v" .. self.schema_version) or ""
    
    print(string.rep("=", 70))
    print(string.format("Stage 1: ChainTree Handle Summary (%s%s)", fmt, ver))
    print(string.rep("=", 70))
    print("Input File: " .. self.input_file)
    print("Total Nodes: " .. self.total_nodes)
    
    local kb_count = 0
    for _ in pairs(self.kb_nodes) do kb_count = kb_count + 1 end
    print("Knowledge Bases: " .. kb_count)
    
    for kb_name in pairs(self.kb_nodes) do
        local nc = self:get_kb_node_count(kb_name)
        local root = self:get_kb_root_node(kb_name) or "?"
        print(string.format("  - %s: %d nodes, root=%s", kb_name, nc, root))
    end
    
    local main_count, os_count, bool_count = 0, 0, 0
    for _ in pairs(self.all_main_functions) do main_count = main_count + 1 end
    for _ in pairs(self.all_one_shot_functions) do os_count = os_count + 1 end
    for _ in pairs(self.all_boolean_functions) do bool_count = bool_count + 1 end
    print("\nFunctions:")
    print("  Main functions: " .. main_count)
    print("  One-shot functions: " .. os_count)
    print("  Boolean functions: " .. bool_count)
    print(string.rep("=", 70))
end

return ChainTreeHandle