--[[
  stage4_link_table.lua - Build flat child-index link table.
  LuaJIT port of stage4_link_table.py
--]]

local LinkTableBuilder = {}
LinkTableBuilder.__index = LinkTableBuilder

function LinkTableBuilder.new(handle, node_builder)
    local self = setmetatable({}, LinkTableBuilder)
    self.handle = handle
    self.node_builder = node_builder
    self.link_table = {}          -- flat array of child indices
    self.node_link_info = {}      -- ltree_name -> { link_start, link_count }
    return self
end

function LinkTableBuilder:build()
    for ltree_name in pairs(self.node_builder.ltree_to_final_index) do
        local children = self.handle:get_node_children(ltree_name)
        
        local operational_children = {}
        for _, child_ltree in ipairs(children) do
            if not self.node_builder.filtered_nodes[child_ltree] and
               self.node_builder.ltree_to_final_index[child_ltree] ~= nil then
                operational_children[#operational_children + 1] = child_ltree
            end
        end
        
        local link_start = #self.link_table
        local link_count = #operational_children
        
        self.node_link_info[ltree_name] = {
            link_start = link_start,
            link_count = link_count,
        }
        
        for _, child_ltree in ipairs(operational_children) do
            local child_index = self.node_builder:get_node_final_index(child_ltree)
            self.link_table[#self.link_table + 1] = child_index
        end
    end
end

function LinkTableBuilder:get_node_link_info(ltree_name)
    return self.node_link_info[ltree_name] or { link_start = 0, link_count = 0 }
end

function LinkTableBuilder:get_link_table_size()
    return #self.link_table
end

function LinkTableBuilder:print_summary()
    print(string.rep("=", 70))
    print("Stage 4: Link Table Builder Summary")
    print(string.rep("=", 70))
    print("Total link entries: " .. #self.link_table)
    
    local max_children = 0
    local nodes_with_children = 0
    for _, info in pairs(self.node_link_info) do
        if info.link_count > max_children then max_children = info.link_count end
        if info.link_count > 0 then nodes_with_children = nodes_with_children + 1 end
    end
    print("Nodes with children: " .. nodes_with_children)
    print("Maximum children per node: " .. max_children)
end

return LinkTableBuilder