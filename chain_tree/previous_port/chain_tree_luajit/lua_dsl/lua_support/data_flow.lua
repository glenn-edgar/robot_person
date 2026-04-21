local ColumnFlow = require("lua_support.column_flow")
local bit = require("bit")

local DataFlow = setmetatable({}, { __index = ColumnFlow })
DataFlow.__index = DataFlow

function DataFlow.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, DataFlow)
end

--- Helper: resolve a list of event names (strings) or explicit bit positions (numbers)
--- into a combined bitmask value.
--- @param event_list table  Array of strings or numbers
--- @return number  Combined bitmask
local function resolve_bitmask(ctb, event_list)
    
    local mask = 0
    for i = 1, #event_list do
        local event = event_list[i]
        
        local bit_pos
        if type(event) == "string" then
            bit_pos = ctb:register_bitmask(event)
        
        elseif type(event) == "number" then
            bit_pos = event
        
        else
            error("Event must be string or number, got " .. type(event))
        end
        mask = bit.bor(mask, bit.lshift(1, bit_pos))
        
    end
    
    return mask
end

--- Define a column that triggers on a bitmask of events.
--- event lists can contain strings (event names) or numbers (explicit bit positions).
---
--- @param column_name string
--- @param aux_function string|nil  Defaults to "CFL_NULL"
--- @param user_data table|nil
--- @param required_bitmask table|nil  Array of string|number
--- @param excluded_bitmask table|nil  Array of string|number
--- @param auto_start boolean|nil  Defaults to false
--- @return string  Node identifier
function DataFlow:define_data_flow_event_mask(column_name, aux_function, user_data,
                                               required_bitmask, excluded_bitmask, auto_start)
    aux_function = aux_function or "CFL_NULL"
    user_data = user_data or {}
    required_bitmask = required_bitmask or {}
    excluded_bitmask = excluded_bitmask or {}
    if auto_start == nil then auto_start = false end

    user_data.required_bitmask = resolve_bitmask(self.ctb, required_bitmask)
   
    user_data.excluded_bitmask = resolve_bitmask(self.ctb, excluded_bitmask)


    self.ctb:add_boolean_function(aux_function)

    return self:define_column(
        column_name,
        "CFL_DF_MASK_MAIN",
        "CFL_DF_MASK_INIT",
        "CFL_DF_MASK_TERM",
        aux_function,
        user_data,
        auto_start,
        "CFL_DF_MASK"
    )
end

--- Generate assembly to set bits in the event mask.
--- event_list can contain strings (event names) or numbers (explicit bit positions).
---
--- @param event_list table  Array of string|number
function DataFlow:asm_set_bitmask(event_list)
    if type(event_list) ~= "table" then
        error("event_list must be a table")
    end
    local mask = resolve_bitmask(self.ctb, event_list)
    self:asm_one_shot_handler("CFL_SET_BITMASK", { bit_mask = mask })
end

--- Generate assembly to clear bits in the event mask.
--- event_list can contain strings (event names) or numbers (explicit bit positions).
---
--- @param event_list table  Array of string|number
function DataFlow:asm_clear_bitmask(event_list)
    if type(event_list) ~= "table" then
        error("event_list must be a table")
    end
    local mask = resolve_bitmask(self.ctb, event_list)
    self:asm_one_shot_handler("CFL_CLEAR_BITMASK", { bit_mask = mask })
end

return DataFlow