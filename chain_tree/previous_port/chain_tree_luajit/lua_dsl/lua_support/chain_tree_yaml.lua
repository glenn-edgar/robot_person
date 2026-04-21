--[[
    ChainTreeYaml - Unified ChainTree generator with ltree-based hierarchical structure.
    Combines node management, function mapping, and structured JSON output.

    Output format: Structured JSON (schema v1.0) consumed by any backend
    code generator (Python, LuaJIT, Zig, Go).

    Translated from Python to LuaJIT.

    Dependencies: none (pure Lua JSON encoder embedded below)
]]

-- ---------------------------------------------------------------------------
-- Embedded JSON encoder (pure Lua, no C dependencies)
-- Only encode is needed — the pipeline never reads JSON back into Lua.
-- ---------------------------------------------------------------------------
local json_encode  -- forward declaration

local function json_encode_string(s)
    -- Escape special characters per JSON spec
    s = s:gsub('\\', '\\\\')
    s = s:gsub('"', '\\"')
    s = s:gsub('\n', '\\n')
    s = s:gsub('\r', '\\r')
    s = s:gsub('\t', '\\t')
    s = s:gsub('%c', function(c)
        return string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. s .. '"'
end

local function is_array(t)
    if type(t) ~= "table" then return false end
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    if count == 0 then return false end  -- empty table -> encode as {}
    -- Check that keys are 1..N with no gaps
    for i = 1, count do
        if t[i] == nil then return false end
    end
    return count == #t
end

local function sorted_keys(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    return keys
end

json_encode = function(val)
    if val == nil then
        return "null"
    end
    if type(val) == "table" and tostring(val) == "null" then
        return "null"
    end

    local vtype = type(val)

    if vtype == "boolean" then
        return val and "true" or "false"

    elseif vtype == "number" then
        -- Integer check: no fractional part and within safe range
        if val == math.floor(val) and math.abs(val) < 2^53 then
            return string.format("%d", val)
        else
            return string.format("%.17g", val)
        end

    elseif vtype == "string" then
        return json_encode_string(val)

    elseif vtype == "table" then
        -- Empty table -> {}
        if next(val) == nil then
            return "{}"
        end

        if is_array(val) then
            local parts = {}
            for i = 1, #val do
                parts[i] = json_encode(val[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for _, k in ipairs(sorted_keys(val)) do
                parts[#parts + 1] = json_encode_string(tostring(k)) .. ":" .. json_encode(val[k])
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end

    else
        -- Fallback for userdata, function, etc.
        return '"<' .. vtype .. '>"'
    end
end

local ChainTreeYaml = {}
ChainTreeYaml.__index = ChainTreeYaml

-- Schema version - backends check this for compatibility
ChainTreeYaml.SCHEMA_VERSION = "1.0"

-- ---------------------------------------------------------------------------
-- Utility helpers
-- ---------------------------------------------------------------------------

--- Shallow copy a table (one level deep).
local function shallow_copy(t)
    if t == nil then return nil end
    local out = {}
    for k, v in pairs(t) do out[k] = v end
    return out
end

--- Count the number of keys in a table.
local function table_len(t)
    local n = 0
    for _ in pairs(t) do n = n + 1 end
    return n
end

--- Check if a file or directory exists.
local function path_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

--- Get the parent directory of a file path.
local function parent_dir(filepath)
    return filepath:match("^(.+)/[^/]+$") or filepath:match("^(.+)\\[^\\]+$") or "."
end

--- Replace .yaml/.yml extension with .json, or append .json
local function to_json_path(filepath)
    local base = filepath:match("^(.+)%.ya?ml$")
    if base then
        return base .. ".json"
    end
    -- Already .json or no extension
    if filepath:match("%.json$") then
        return filepath
    end
    return filepath .. ".json"
end

--- Sorted keys of a table (for deterministic output)
local function sorted_keys(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys)
    return keys
end

-- ---------------------------------------------------------------------------
-- Constructor
-- ---------------------------------------------------------------------------

function ChainTreeYaml.new(output_file)
    local self = setmetatable({}, ChainTreeYaml)

    -- Accept .yaml or .json path; store the JSON path
    self.output_file = to_json_path(output_file)
    -- Keep original for backward compat
    self.yaml_file = self.output_file

    -- Check parent directory exists
    local parent = parent_dir(output_file)
    if not path_exists(parent) then
        error("Parent directory for output file does not exist: " .. parent)
    end

    -- Core ltree structure
    self.separator = "."
    self.path_list = {}        -- List[str]
    self.ltree_stack = {}      -- List[str]
    self.yaml_data = {}        -- Flat structure with ltree keys
    self.node_count = 0
    self.ltree_to_index = {}   -- Map ltree name -> array index
    self.index_to_ltree = {}   -- Map array index -> ltree name

    -- Event string table for embedded systems
    self.event_string_table = {}   -- Map event_id -> index
    self.event_index_counter = 0

    -- Bitmask table for embedded systems (max 32 bits)
    self.bitmask_bit_counter = 0
    self.bitmask_table = {}        -- str -> int (event name to bit)
    self.used_bits = {}            -- set of all occupied bit numbers (bit -> true)
    self.next_auto_bit = 0

    -- Knowledge base management
    self.kb_dict = {}              -- str -> List[str]
    self.kb_log_dict = {}          -- str -> List[str]
    self.kb_metadata = {}          -- str -> Dict
    self.current_kb_name = nil

    -- Node alias tables per KB
    self.node_alias_tables = {}    -- str -> { alias -> index }

    -- Function mappings per knowledge base
    self.main_functions = {}
    self.one_shot_functions = {}
    self.boolean_functions = {}
    self.s_main_functions = {}
    self.s_one_shot_functions = {}
    self.s_boolean_functions = {}

    -- Blackboard definitions
    self.blackboard = nil          -- { name, fields: [{name, type, default}] }
    self.const_records = {}        -- list of { name, fields: [{name, type, value}] }

    return self
end

-- =========================================================================
-- Knowledge Base Management
-- =========================================================================

function ChainTreeYaml:add_kb(kb_name)
    if type(kb_name) ~= "string" then
        error("kb_name must be a string")
    end
    if self.kb_dict[kb_name] then
        error("Knowledge base " .. kb_name .. " already exists")
    end

    local path_list = { "kb", kb_name }
    self.kb_dict[kb_name] = path_list
    self.kb_log_dict[kb_name] = { path_list[1], path_list[2] } -- copy

    -- Initialize function mappings for this kb
    self:_init_kb_function_mappings(kb_name)
end

function ChainTreeYaml:select_kb(kb_name)
    if type(kb_name) ~= "string" then
        error("kb_name must be a string")
    end
    if kb_name == self.current_kb_name then
        return
    end

    -- Auto-create kb if it doesn't exist
    if not self.kb_dict[kb_name] then
        self:add_kb(kb_name)
    end

    -- Copy the path list
    local src = self.kb_dict[kb_name]
    self.path_list = {}
    for i = 1, #src do self.path_list[i] = src[i] end

    self.current_kb_name = kb_name
end

function ChainTreeYaml:leave_kb()
    if self.current_kb_name == nil then
        error("No knowledge base is currently selected")
    end

    if #self.path_list ~= 2 then
        error("Path list is not at the root level: " .. table.concat(self.path_list, ", "))
    end

    -- Ensure kb_metadata exists for this KB (defensive)
    if not self.kb_metadata[self.current_kb_name] then
        self.kb_metadata[self.current_kb_name] = {
            start_index = 0,
            node_count = 0,
            node_aliases = {},
        }
    end

    local kb_meta = self.kb_metadata[self.current_kb_name]

    -- Calculate node count for this KB
    local start_idx = kb_meta.start_index or 0
    kb_meta.node_count = self.node_count - start_idx

    -- Attach alias table to kb_metadata
    kb_meta.node_aliases = shallow_copy(
        self.node_alias_tables[self.current_kb_name] or {}
    )

    self:pop_path(self.path_list[1], self.path_list[2])
    self.kb_dict[self.current_kb_name] = nil
    self.current_kb_name = nil
end

function ChainTreeYaml:get_current_kb()
    return self.current_kb_name
end

function ChainTreeYaml:_init_kb_function_mappings(kb_name)
    self.main_functions[kb_name] = {}
    self.one_shot_functions[kb_name] = {}
    self.boolean_functions[kb_name] = {}
    self.s_main_functions[kb_name] = {}
    self.s_one_shot_functions[kb_name] = {}
    self.s_boolean_functions[kb_name] = {}

    -- Initialize alias table for this KB (only if not already set)
    if not self.node_alias_tables[kb_name] then
        self.node_alias_tables[kb_name] = {}
    end

    -- Initialize KB metadata with start index (only if not already set)
    if not self.kb_metadata[kb_name] then
        self.kb_metadata[kb_name] = {
            start_index = self.node_count,
            node_count = 0,
            node_aliases = {},
        }
    end
end

-- =========================================================================
-- Function Registration
-- =========================================================================

function ChainTreeYaml:_check_kb_selected()
    if self.current_kb_name == nil then
        error("No knowledge base is currently selected")
    end
end

function ChainTreeYaml:add_main_function(function_name)
    self:_check_kb_selected()
    self.main_functions[self.current_kb_name][function_name] = true
end

function ChainTreeYaml:add_one_shot_function(function_name)
    self:_check_kb_selected()
    self.one_shot_functions[self.current_kb_name][function_name] = true
end

function ChainTreeYaml:add_boolean_function(function_name)
    self:_check_kb_selected()
    self.boolean_functions[self.current_kb_name][function_name] = true
end

function ChainTreeYaml:add_s_main_function(function_name)
    self:_check_kb_selected()
    self.s_main_functions[self.current_kb_name][function_name] = true
end

function ChainTreeYaml:add_s_one_shot_function(function_name)
    self:_check_kb_selected()
    self.s_one_shot_functions[self.current_kb_name][function_name] = true
end

function ChainTreeYaml:add_s_boolean_function(function_name)
    self:_check_kb_selected()
    self.s_boolean_functions[self.current_kb_name][function_name] = true
end

-- =========================================================================
-- Node Alias Table Management
-- =========================================================================

function ChainTreeYaml:register_node_alias(alias_name, ltree_name)
    self:_check_kb_selected()

    if type(alias_name) ~= "string" then
        error("alias_name must be a string")
    end

    if ltree_name == nil then
        if #self.ltree_stack == 0 then
            error("No current node and no ltree_name provided")
        end
        ltree_name = self.ltree_stack[#self.ltree_stack]
    end

    if self.ltree_to_index[ltree_name] == nil then
        error("Node not found: " .. ltree_name)
    end

    local node_index = self.ltree_to_index[ltree_name]

    -- Ensure the KB has an alias table
    if not self.node_alias_tables[self.current_kb_name] then
        self.node_alias_tables[self.current_kb_name] = {}
    end

    -- Check if alias already exists in THIS KB's table
    if self.node_alias_tables[self.current_kb_name][alias_name] ~= nil then
        error("Alias " .. alias_name .. " already exists in KB " .. self.current_kb_name)
    end

    -- Store the node index
    self.node_alias_tables[self.current_kb_name][alias_name] = node_index

    return node_index
end

function ChainTreeYaml:get_node_by_alias(alias_name, kb_name)
    local kb = kb_name or self.current_kb_name
    if kb == nil then
        error("No knowledge base specified")
    end

    local alias_tbl = self.node_alias_tables[kb] or {}
    if alias_tbl[alias_name] == nil then
        error("Alias not found: " .. alias_name)
    end

    return alias_tbl[alias_name]
end

function ChainTreeYaml:get_ltree_by_alias(alias_name, kb_name)
    local node_index = self:get_node_by_alias(alias_name, kb_name)
    return self.index_to_ltree[node_index]
end

function ChainTreeYaml:get_node_alias_table(kb_name)
    local kb = kb_name or self.current_kb_name
    if kb == nil then
        error("No knowledge base specified")
    end
    return shallow_copy(self.node_alias_tables[kb] or {})
end

function ChainTreeYaml:get_kb_metadata(kb_name)
    if not self.kb_metadata[kb_name] then
        error("KB not found: " .. kb_name)
    end
    return shallow_copy(self.kb_metadata[kb_name])
end

-- =========================================================================
-- Path Management
-- =========================================================================

function ChainTreeYaml:get_current_path()
    local copy = {}
    for i = 1, #self.path_list do copy[i] = self.path_list[i] end
    return copy
end

function ChainTreeYaml:set_path_list(path_list)
    if type(path_list) ~= "table" then
        error("Path list must be a table")
    end
    self.path_list = {}
    for i = 1, #path_list do self.path_list[i] = path_list[i] end
end

function ChainTreeYaml:get_current_ltree_prefix()
    if #self.path_list == 0 then return "" end
    return table.concat(self.path_list, self.separator)
end

function ChainTreeYaml:pop_path(label_name, node_name)
    if #self.path_list < 2 then
        error("Path list is too short to pop")
    end

    local local_node = table.remove(self.path_list)
    local local_label = table.remove(self.path_list)

    if local_node ~= node_name or local_label ~= label_name then
        error(string.format(
            "Path mismatch: expected (%s, %s), got (%s, %s)",
            label_name, node_name, local_label, local_node
        ))
    end
end

function ChainTreeYaml:_create_ltree_name(label_name, node_name)
    -- Build all_parts = path_list + {label_name, node_name}
    local all_parts = {}
    for i = 1, #self.path_list do
        all_parts[#all_parts + 1] = self.path_list[i]
    end
    all_parts[#all_parts + 1] = label_name
    all_parts[#all_parts + 1] = node_name

    local ltree_name = table.concat(all_parts, self.separator)
    local parent_ltree_name = table.concat(self.path_list, self.separator)

    return ltree_name, parent_ltree_name
end

-- =========================================================================
-- Node Creation - Core Methods
-- =========================================================================

function ChainTreeYaml:define_composite_node(label_name, node_name, label_dict, node_dict)
    label_dict = label_dict or {}
    node_dict = node_dict or {}

    local ltree_name, parent_ltree_name = self:_create_ltree_name(label_name, node_name)
    label_dict.parent_ltree_name = parent_ltree_name
    label_dict.ltree_name = ltree_name
    label_dict.array_index = self.node_count

    self.yaml_data[ltree_name] = {
        label = label_name,
        node_name = node_name,
        label_dict = label_dict,
        node_dict = node_dict,
    }

    -- Update path list to include this composite node
    self.path_list[#self.path_list + 1] = label_name
    self.path_list[#self.path_list + 1] = node_name

    -- Store mapping from ltree_name to array index (and reverse)
    self.ltree_to_index[ltree_name] = self.node_count
    self.index_to_ltree[self.node_count] = ltree_name
    self.node_count = self.node_count + 1

    return self.node_count
end

function ChainTreeYaml:define_simple_node(label_name, node_name, label_dict, node_dict)
    label_dict = label_dict or {}
    node_dict = node_dict or {}

    local ltree_name, parent_ltree_name = self:_create_ltree_name(label_name, node_name)
    label_dict.parent_ltree_name = parent_ltree_name
    label_dict.ltree_name = ltree_name
    label_dict.array_index = self.node_count

    self.yaml_data[ltree_name] = {
        label = label_name,
        node_name = node_name,
        label_dict = label_dict,
        node_dict = node_dict,
    }

    -- Store mapping from ltree_name to array index (and reverse)
    self.ltree_to_index[ltree_name] = self.node_count
    self.index_to_ltree[self.node_count] = ltree_name
    self.node_count = self.node_count + 1

    return self.node_count
end

-- =========================================================================
-- Node Creation - ChainTree-Specific Methods
-- =========================================================================

function ChainTreeYaml:_add_node_link(ltree_name)
    if #self.ltree_stack == 0 then
        return
    end

    if type(ltree_name) ~= "string" then
        error("ltree_name must be a string")
    end

    local parent_ltree = self.ltree_stack[#self.ltree_stack]
    local parent_data = self.yaml_data[parent_ltree]
    local links = parent_data.label_dict.links
    links[#links + 1] = ltree_name
end

function ChainTreeYaml:add_node_element(label_name, node_name, main_function_name,
        initialization_function_name, aux_function_name, termination_function_name,
        node_data, links_flag)

    if links_flag == nil then links_flag = true end

    -- Type validation
    if type(label_name) ~= "string" then error("label_name must be a string") end
    if type(node_name) ~= "string" then error("node_name must be a string") end
    if type(main_function_name) ~= "string" then error("main_function_name must be a string") end
    if type(initialization_function_name) ~= "string" then error("initialization_function_name must be a string") end
    if type(aux_function_name) ~= "string" then error("aux_function_name must be a string") end
    if type(termination_function_name) ~= "string" then error("termination_function_name must be a string") end
    if type(node_data) ~= "table" then error("node_data must be a table") end

    -- Build label data
    local label_data = {
        main_function_name = main_function_name,
        initialization_function_name = initialization_function_name,
        aux_function_name = aux_function_name,
        termination_function_name = termination_function_name,
        links = {},
    }

    -- Create the composite node
    self:define_composite_node(label_name, node_name, label_data, node_data)
    local ltree_name = self:get_current_ltree_prefix()

    -- Register functions
    self:add_main_function(main_function_name)
    self:add_boolean_function(aux_function_name)
    self:add_one_shot_function(termination_function_name)
    self:add_one_shot_function(initialization_function_name)

    -- Add link from parent if requested
    if links_flag then
        self:_add_node_link(ltree_name)
    end

    -- Push onto stack for children
    self.ltree_stack[#self.ltree_stack + 1] = ltree_name

    return ltree_name
end

function ChainTreeYaml:pop_node_element(ref_ltree_name)
    if #self.ltree_stack == 0 then
        error("Ltree stack is empty")
    end

    local ltree_name = table.remove(self.ltree_stack)

    if ltree_name ~= ref_ltree_name then
        error(string.format(
            "Ltree name mismatch: expected %s, got %s",
            ref_ltree_name, ltree_name
        ))
    end

    local node_data = self.yaml_data[ltree_name]
    self:pop_path(node_data.label, node_data.node_name)
end

function ChainTreeYaml:add_leaf_element(label_name, node_name, main_function_name,
        initialization_function_name, aux_function_name, termination_function_name,
        node_data)

    -- Type validation
    if type(label_name) ~= "string" then error("label_name must be a string") end
    if type(node_name) ~= "string" then error("node_name must be a string") end
    if type(main_function_name) ~= "string" then error("main_function_name must be a string") end
    if type(initialization_function_name) ~= "string" then error("initialization_function_name must be a string") end
    if type(aux_function_name) ~= "string" then error("aux_function_name must be a string") end
    if type(termination_function_name) ~= "string" then error("termination_function_name must be a string") end
    if type(node_data) ~= "table" then error("node_data must be a table") end

    -- Build label data
    local label_data = {
        main_function_name = main_function_name,
        initialization_function_name = initialization_function_name,
        aux_function_name = aux_function_name,
        termination_function_name = termination_function_name,
        links = {},
    }

    -- Create the simple node
    self:define_simple_node(label_name, node_name, label_data, node_data)
    local ltree_name = self:_create_ltree_name(label_name, node_name)

    -- Register functions
    self:add_main_function(main_function_name)
    self:add_boolean_function(aux_function_name)
    self:add_one_shot_function(termination_function_name)
    self:add_one_shot_function(initialization_function_name)

    -- Add link from parent
    self:_add_node_link(ltree_name)

    return ltree_name
end

-- =========================================================================
-- Event String Table Management (for embedded C)
-- =========================================================================

function ChainTreeYaml:register_event(event_id)
    if type(event_id) ~= "string" then
        error("event_id must be a string")
    end

    -- Check if already registered
    if self.event_string_table[event_id] then
        return self.event_string_table[event_id]
    end

    -- Register new event
    local index = self.event_index_counter
    self.event_string_table[event_id] = index
    self.event_index_counter = self.event_index_counter + 1

    return index
end

function ChainTreeYaml:get_event_index(event_id)
    if self.event_string_table[event_id] == nil then
        error("Event ID not registered: " .. event_id)
    end
    return self.event_string_table[event_id]
end

function ChainTreeYaml:get_all_events()
    return shallow_copy(self.event_string_table)
end

function ChainTreeYaml:get_event_string_table_size()
    return self.event_index_counter
end

-- =========================================================================
-- Bitmask Table Management (for embedded C, max 32 bits)
-- =========================================================================

function ChainTreeYaml:register_bitmask(event)
    if type(event) == "string" then
        local name = event
        if self.bitmask_table[name] then
            return self.bitmask_table[name]
        end

        -- Find next free bit (skip used ones)
        local bit_pos = self.next_auto_bit
        while self.used_bits[bit_pos] do
            bit_pos = bit_pos + 1
            if bit_pos > 31 then
                error("No free bits left (0-31).")
            end
        end

        -- Register
        self.bitmask_table[name] = bit_pos
        self.used_bits[bit_pos] = true
        self.next_auto_bit = bit_pos + 1

        return bit_pos

    elseif type(event) == "number" then
        local bit_pos = event
        if bit_pos < 0 or bit_pos > 31 then
            error(string.format("Bit position must be 0-31, got %d", bit_pos))
        end

        if self.used_bits[bit_pos] then
            -- Find who owns it
            local owner = "explicit reservation"
            for n, b in pairs(self.bitmask_table) do
                if b == bit_pos then owner = n; break end
            end
            error(string.format("Bit %d already in use by '%s'", bit_pos, owner))
        end

        -- Reserve it
        self.bitmask_table["EXPLICIT_" .. bit_pos] = bit_pos
        self.used_bits[bit_pos] = true

        -- Update auto-next if needed
        if bit_pos >= self.next_auto_bit then
            self.next_auto_bit = bit_pos + 1
        end

        return bit_pos
    else
        error("event must be a string (event name) or a number (bit position)")
    end
end

function ChainTreeYaml:get_bitmask_bit(event)
    if type(event) == "string" then
        if self.bitmask_table[event] == nil then
            error("Bitmask event not registered: " .. event)
        end
        return self.bitmask_table[event]

    elseif type(event) == "number" then
        local bit_pos = event
        local found = false
        for _, b in pairs(self.bitmask_table) do
            if b == bit_pos then found = true; break end
        end
        if not found then
            error(string.format(
                "Bit position %d has not been allocated (no event registered with this bit)", bit_pos
            ))
        end
        return bit_pos
    else
        error("event must be a string (event name) or a number (bit position)")
    end
end

function ChainTreeYaml:get_all_bitmasks()
    return shallow_copy(self.bitmask_table)
end

function ChainTreeYaml:get_bitmask_count()
    return self.bitmask_bit_counter
end

function ChainTreeYaml:get_bitmask_value(event_name)
    local bit_number = self:get_bitmask_bit(event_name)
    return bit.lshift(1, bit_number)  -- LuaJIT bit library
end

-- =========================================================================
-- Array Index Mapping (for embedded C)
-- =========================================================================

function ChainTreeYaml:get_node_index(ltree_name)
    if self.ltree_to_index[ltree_name] == nil then
        error("Ltree name not found: " .. ltree_name)
    end
    return self.ltree_to_index[ltree_name]
end

function ChainTreeYaml:get_all_node_indices()
    return shallow_copy(self.ltree_to_index)
end

function ChainTreeYaml:get_total_node_count()
    return self.node_count
end

-- =========================================================================
-- Assembly and Validation
-- =========================================================================

function ChainTreeYaml:start_assembly()
    self.ltree_stack = {}
end

function ChainTreeYaml:check_for_balance_ltree()
    if #self.ltree_stack > 0 then
        error("Ltrees have not been closed: " .. table.concat(self.ltree_stack, ", "))
    end
end

-- =========================================================================
-- JSON Generation (was YAML - now produces structured JSON)
-- =========================================================================

--- Build the structured JSON envelope separating nodes from metadata.
--- This is the IR consumed by all backend code generators.
function ChainTreeYaml:_build_envelope()
    -- Separate nodes from metadata in yaml_data
    -- Nodes are keyed by ltree paths starting with "kb."
    -- Metadata is stored separately
    local nodes = {}
    for key, value in pairs(self.yaml_data) do
        if type(key) == "string" and type(value) == "table" then
            -- Node entries have ltree paths as keys
            if key:sub(1, 3) == "kb." then
                nodes[key] = value
            end
        end
    end

    -- Build blackboard section for JSON IR
    local bb_section = nil
    if self.blackboard or #self.const_records > 0 then
        bb_section = {}
        if self.blackboard then
            bb_section.record = self.blackboard
        end
        if #self.const_records > 0 then
            bb_section.const_records = self.const_records
        end
    end

    -- Function registry: union of every function name the DSL has been
    -- told about (per-KB sets in self.{main,one_shot,boolean}_functions).
    -- This is the canonical list the runtime loader builds its
    -- name -> index tables from. Without it, functions referenced from
    -- node_dict fields (verify error_function, watchdog wd_fn, ...) get
    -- index 0 (CFL_NULL) and silently no-op.
    local function _union_set(per_kb_map)
        local seen = {}
        for _, names in pairs(per_kb_map or {}) do
            for name, _ in pairs(names) do seen[name] = true end
        end
        local arr = {}
        for name, _ in pairs(seen) do arr[#arr + 1] = name end
        table.sort(arr)
        return arr
    end

    local function_registry = {
        main      = _union_set(self.main_functions),
        one_shot  = _union_set(self.one_shot_functions),
        boolean   = _union_set(self.boolean_functions),
    }

    local envelope = {
        schema_version     = self.SCHEMA_VERSION,
        total_nodes        = self.node_count,
        kb_log_dict        = self.kb_log_dict,
        kb_metadata        = self.kb_metadata,
        ltree_to_index     = self.ltree_to_index,
        event_string_table = self.event_string_table,
        bitmask_table      = self.bitmask_table,
        blackboard         = bb_section,
        function_registry  = function_registry,
        nodes              = nodes,
    }

    return envelope
end

--- Generate the output file (JSON format).
--- Backward-compatible: can be called as generate_yaml() or generate_json().
function ChainTreeYaml:generate_json()
    -- Add event string table node if any events were registered
    if next(self.event_string_table) then
        self:_create_event_string_table_node()
    end

    -- Add bitmask table node if any bitmasks were registered
    if next(self.bitmask_table) then
        self:_create_bitmask_table_node()
    end

    -- Validate all KBs are closed
    if next(self.kb_dict) then
        local open_kbs = {}
        for k, _ in pairs(self.kb_dict) do open_kbs[#open_kbs + 1] = k end
        error("Knowledge bases still open: " .. table.concat(open_kbs, ", "))
    end

    -- Build the structured envelope
    local envelope = self:_build_envelope()

    -- Write JSON file
    local json_str = json_encode(envelope)

    local f = io.open(self.output_file, "w")
    if not f then
        error("Cannot open file for writing: " .. self.output_file)
    end
    f:write(json_str)
    f:write("\n")
    f:close()

    print(string.format("  Written: %s (%d bytes, %d nodes, schema v%s)",
        self.output_file, #json_str, self.node_count, self.SCHEMA_VERSION))

    return envelope
end

--- Backward compatibility alias
ChainTreeYaml.generate_yaml = ChainTreeYaml.generate_json

function ChainTreeYaml:_create_event_string_table_node()
    local temp_kb_name = "event_string_table_kb"
    self:add_kb(temp_kb_name)
    self:select_kb(temp_kb_name)

    self:add_leaf_element(
        "event_strings",
        "event_string_table",
        "CFL_NULL",
        "CFL_NULL",
        "CFL_NULL",
        "CFL_NULL",
        shallow_copy(self.event_string_table)
    )

    self:leave_kb()

    -- Remove from kb_log_dict since this is just for the event table
    if self.kb_log_dict[temp_kb_name] then
        self.kb_log_dict[temp_kb_name] = nil
    end
end

function ChainTreeYaml:_create_bitmask_table_node()
    local temp_kb_name = "bitmask_table_kb"
    self:add_kb(temp_kb_name)
    self:select_kb(temp_kb_name)

    self:add_leaf_element(
        "bitmask",
        "bitmask_table",
        "CFL_NULL",
        "CFL_NULL",
        "CFL_NULL",
        "CFL_NULL",
        shallow_copy(self.bitmask_table)
    )

    self:leave_kb()

    if self.kb_log_dict[temp_kb_name] then
        self.kb_log_dict[temp_kb_name] = nil
    end
end

-- =========================================================================
-- Function Mapping Access
-- =========================================================================

function ChainTreeYaml:get_function_mappings(kb_name)
    local kb = kb_name or self.current_kb_name
    if kb == nil then
        error("No knowledge base specified")
    end

    return {
        main_functions = self.main_functions[kb] or {},
        one_shot_functions = self.one_shot_functions[kb] or {},
        boolean_functions = self.boolean_functions[kb] or {},
        s_main_functions = self.s_main_functions[kb] or {},
        s_one_shot_functions = self.s_one_shot_functions[kb] or {},
        s_boolean_functions = self.s_boolean_functions[kb] or {},
    }
end

-- =========================================================================
-- Blackboard DSL
-- =========================================================================

--- Define the mutable shared blackboard record.
--- Only one blackboard per ChainTree configuration.
--- @param name string Record name (used for hash identification)
function ChainTreeYaml:define_blackboard(name)
    if self.blackboard then
        error("Blackboard already defined: " .. self.blackboard.name)
    end
    self.blackboard = { name = name, fields = {} }
end

--- Add a field to the current blackboard definition.
--- @param field_name string Field name (supports dotted names for nested access)
--- @param field_type string Type: "int32", "uint32", "uint16", "float", "uint64"
--- @param default_value number|nil Default value (0 if nil)
function ChainTreeYaml:bb_field(field_name, field_type, default_value)
    if not self.blackboard then
        error("No blackboard defined — call define_blackboard() first")
    end
    self.blackboard.fields[#self.blackboard.fields + 1] = {
        name = field_name,
        type = field_type,
        default = default_value or 0,
    }
end

--- Finish the blackboard definition.
function ChainTreeYaml:end_blackboard()
    if not self.blackboard then
        error("No blackboard to end")
    end
    -- Validation: at least one field
    if #self.blackboard.fields == 0 then
        error("Blackboard '" .. self.blackboard.name .. "' has no fields")
    end
end

--- Define a read-only constant record.
--- @param name string Record name (used for hash identification)
function ChainTreeYaml:define_const_record(name)
    self._current_const_record = { name = name, fields = {} }
end

--- Add a field to the current constant record.
--- @param field_name string Field name
--- @param field_type string Type: "int32", "uint32", "uint16", "float", "uint64"
--- @param value number The constant value
function ChainTreeYaml:const_field(field_name, field_type, value)
    if not self._current_const_record then
        error("No const record defined — call define_const_record() first")
    end
    self._current_const_record.fields[#self._current_const_record.fields + 1] = {
        name = field_name,
        type = field_type,
        value = value,
    }
end

--- Finish the current constant record definition.
function ChainTreeYaml:end_const_record()
    if not self._current_const_record then
        error("No const record to end")
    end
    if #self._current_const_record.fields == 0 then
        error("Const record '" .. self._current_const_record.name .. "' has no fields")
    end
    self.const_records[#self.const_records + 1] = self._current_const_record
    self._current_const_record = nil
end

return ChainTreeYaml