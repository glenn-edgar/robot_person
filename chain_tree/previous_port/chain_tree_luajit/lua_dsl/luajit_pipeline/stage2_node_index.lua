--[[
  stage2_node_index.lua - Build node ordering and index mappings.
  LuaJIT port of stage2_node_index.py
--]]

local NodeIndexBuilder = {}
NodeIndexBuilder.__index = NodeIndexBuilder

local METADATA_NODE_LABELS = {
    virtual_functions = true,
    complete_functions = true,
    main_functions = true,
    one_shot_functions = true,
    boolean_functions = true,
}

function NodeIndexBuilder.new(handle)
    local self = setmetatable({}, NodeIndexBuilder)
    self.handle = handle
    self.kb_node_order = {}       -- kb_name -> { ltree_names }
    self.kb_start_index = {}      -- kb_name -> int
    self.kb_end_index = {}        -- kb_name -> int
    self.ltree_to_final_index = {} -- ltree_name -> original index
    self.final_index_to_ltree = {} -- original_index -> ltree_name
    self.filtered_nodes = {}      -- set: ltree_name -> true
    self.max_index = 0
    return self
end

function NodeIndexBuilder:get_node_depth(ltree_name)
    local parts = {}
    for part in ltree_name:gmatch("[^%.]+") do parts[#parts + 1] = part end
    if #parts < 2 then return 0 end
    
    local kb_name = parts[2]
    local root_ltree = self.handle:get_kb_root_node(kb_name)
    if not root_ltree then return math.max(0, #parts - 3) end
    
    local root_parts = 0
    for _ in root_ltree:gmatch("[^%.]+") do root_parts = root_parts + 1 end
    
    local depth = math.floor((#parts - root_parts) / 2)
    return math.max(0, depth)
end

function NodeIndexBuilder:_is_metadata_node(ltree_name)
    local node_data = self.handle:get_node_data(ltree_name)
    if not node_data then return false end
    
    local label = node_data.label or ""
    if METADATA_NODE_LABELS[label] then return true end
    
    local parent_ltree = self.handle:get_node_parent(ltree_name)
    if parent_ltree and self.filtered_nodes[parent_ltree] then return true end
    
    return false
end

function NodeIndexBuilder:build()
    local total_filtered = 0
    
    for _, kb_name in ipairs(self.handle:get_kb_names()) do
        local all_nodes = self.handle:traverse_kb_breadth_first(kb_name)
        local operational_nodes = {}
        local kb_indices = {}
        
        for _, ltree_name in ipairs(all_nodes) do
            if self:_is_metadata_node(ltree_name) then
                self.filtered_nodes[ltree_name] = true
                total_filtered = total_filtered + 1
            else
                operational_nodes[#operational_nodes + 1] = ltree_name
                local original_index = self.handle:get_node_index(ltree_name)
                if original_index ~= nil then
                    kb_indices[#kb_indices + 1] = original_index
                    self.ltree_to_final_index[ltree_name] = original_index
                    self.final_index_to_ltree[original_index] = ltree_name
                    if original_index > self.max_index then
                        self.max_index = original_index
                    end
                end
            end
        end
        
        self.kb_node_order[kb_name] = operational_nodes
        
        if #kb_indices > 0 then
            local min_idx, max_idx = kb_indices[1], kb_indices[1]
            for _, idx in ipairs(kb_indices) do
                if idx < min_idx then min_idx = idx end
                if idx > max_idx then max_idx = idx end
            end
            self.kb_start_index[kb_name] = min_idx
            self.kb_end_index[kb_name] = max_idx + 1
        end
    end
    
    if total_filtered > 0 then
        print(string.format("  Filtered out %d function definition metadata nodes", total_filtered))
    end
end

function NodeIndexBuilder:get_node_final_index(ltree_name)
    return self.ltree_to_final_index[ltree_name]
end

function NodeIndexBuilder:get_node_by_index(index)
    return self.final_index_to_ltree[index]
end

function NodeIndexBuilder:get_kb_range(kb_name)
    local s = self.kb_start_index[kb_name] or 0
    local e = self.kb_end_index[kb_name] or 0
    return s, e
end

function NodeIndexBuilder:get_total_nodes()
    local count = 0
    for _ in pairs(self.ltree_to_final_index) do count = count + 1 end
    return count
end

function NodeIndexBuilder:get_array_size()
    return self.max_index + 1
end

function NodeIndexBuilder:print_summary()
    print(string.rep("=", 70))
    print("Stage 2: Node Index Builder Summary")
    print(string.rep("=", 70))
    print(string.format("Total operational nodes: %d", self:get_total_nodes()))
    print(string.format("Array size needed: %d (indices 0..%d)", self:get_array_size(), self.max_index))
    
    for kb_name, nodes in pairs(self.kb_node_order) do
        local s, e = self:get_kb_range(kb_name)
        print(string.format("  %s: original indices [%d..%d] (%d nodes)", kb_name, s, e - 1, #nodes))
    end
end

return NodeIndexBuilder