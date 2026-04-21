--[[
    ChainTreeMaster - Unified DSL combining all ChainTree mixin modules.

    Python uses multiple inheritance (MRO) to compose this class.
    LuaJIT achieves the same by copying methods from each module into
    a single metatable, with ColumnFlow as the base.

    Output: Structured JSON (schema v1.0) consumed by any backend
    code generator (Python, LuaJIT, Zig, Go).

    Directory: lua_support/

    Translated from Python to LuaJIT.
]]
local ok, DebugYamlDumper = pcall(require, "lua_support.debug_yaml_dumper")
if not ok then
    print("Warning: debug_yaml_dumper failed to load: " .. tostring(DebugYamlDumper))
    error("debug_yaml_dumper failed to load")
    DebugYamlDumper = nil
end
local ChainTreeYaml      = require("lua_support.chain_tree_yaml")
local ColumnFlow          = require("lua_support.column_flow")
local BasicCfLinks        = require("lua_support.basic_cf_links")
local WaitCfLinks         = require("lua_support.wait_cf_links")
local VerifyCfLinks       = require("lua_support.verify_cf_links")
local StateMachine        = require("lua_support.state_machine")
local SequenceTil         = require("lua_support.sequence_till")
local DataFlow            = require("lua_support.data_flow")
local ExceptionHandler    = require("lua_support.exception_handler")
local Streaming           = require("lua_support.streaming")
local ControlledNodes     = require("lua_support.controlled_nodes")
local SExpressionNodes    = require("lua_support.s_expression_nodes")
local SEngine             = require("lua_support.s_engine")

-- ---------------------------------------------------------------------------
-- Mixin helper: copy all methods from a source table into dest,
-- skipping keys that are already defined (first writer wins)
-- and skipping metamethods / constructor.
-- ---------------------------------------------------------------------------
local function mixin(dest, src)
    for k, v in pairs(src) do
        if type(v) == "function" and k ~= "new" and k:sub(1, 2) ~= "__" then
            if dest[k] == nil then
                dest[k] = v
            end
        end
    end
end

-- ---------------------------------------------------------------------------
-- Build the ChainTreeMaster class
-- ---------------------------------------------------------------------------
local ChainTreeMaster = {}
ChainTreeMaster.__index = ChainTreeMaster

-- Mix in methods from all modules (order matters — first writer wins,
-- matching Python MRO left-to-right priority)
mixin(ChainTreeMaster, BasicCfLinks)
mixin(ChainTreeMaster, WaitCfLinks)
mixin(ChainTreeMaster, VerifyCfLinks)
mixin(ChainTreeMaster, StateMachine)
mixin(ChainTreeMaster, SequenceTil)
mixin(ChainTreeMaster, DataFlow)
mixin(ChainTreeMaster, ExceptionHandler)
mixin(ChainTreeMaster, Streaming)
mixin(ChainTreeMaster, ControlledNodes)
mixin(ChainTreeMaster, SExpressionNodes)
mixin(ChainTreeMaster, SEngine)
mixin(ChainTreeMaster, ColumnFlow)

-- ---------------------------------------------------------------------------
-- Constructor
-- ---------------------------------------------------------------------------
function ChainTreeMaster.new(output_file)
    local self = setmetatable({}, ChainTreeMaster)

    -- ChainTreeYaml now outputs JSON (the name is kept for backward compat)
    self.ctb = ChainTreeYaml.new(output_file)

    -- Initialize instance state from mixins
    self.sm_stack = {}
    self.sm_name_dict = {}
    self.sequence_dict = {}
    self.sequence_active = false
    self.s_expr_dict = {}

    -- ExceptionHandler state
    self.main_flag = false
    self.recovery_flag = false
    self.finalize_flag = false
    self.exception_catch_stack = {}
    self.exception_catch_flags = {}
    self.exception_catch_links = {}

    -- Convenience alias
    self.register_event = function(_, event_id)
        return self.ctb:register_event(event_id)
    end

    -- Register core system events
    local core_events = {
        "CFL_INIT_EVENT",
        "CFL_TERMINATE_EVENT",
        "CFL_START_TESTS",
        "CFL_TERMINATE_TESTS",
        "CFL_TIMER_EVENT",
        "CFL_SECOND_EVENT",
        "CFL_MINUTE_EVENT",
        "CFL_HOUR_EVENT",
        "CFL_DAY_EVENT",
        "CFL_WEEK_EVENT",
        "CFL_MONTH_EVENT",
        "CFL_YEAR_EVENT",
        "CFL_RAISE_EXCEPTION_EVENT",
        "CFL_TURN_HEARTBEAT_ON_EVENT",
        "CFL_TURN_HEARTBEAT_OFF_EVENT",
        "CFL_HEARTBEAT_EVENT",
        "CFL_SET_EXCEPTION_STEP_EVENT",
        "CFL_START_TESTS",
        "CFL_TERMINATE_TESTS",
        "CFL_CHANGE_STATE_EVENT",
        "CFL_RESET_STATE_MACHINE_EVENT",
        "CFL_TERMINATE_STATE_MACHINE_EVENT",
    }
    for _, evt in ipairs(core_events) do
        self.ctb:register_event(evt)
    end

    return self
end

-- ---------------------------------------------------------------------------
-- Top-level API
-- ---------------------------------------------------------------------------

function ChainTreeMaster:check_and_generate()
    self:check_valid_chain_tree_configuration()
    self:dump_kb_functions()
    self:dump_complete_functions()
    self:generate_json()
end

--- Primary output method - generates structured JSON
function ChainTreeMaster:generate_json()
    self.ctb:generate_json()
end
--- Debug output - generates human-readable YAML to file
function ChainTreeMaster:generate_debug_yaml(filepath)
    if not DebugYamlDumper then
        print("Warning: debug_yaml_dumper not available, skipping debug YAML output")
        return
    end
    filepath = filepath or self.ctb.output_file:gsub("%.json$", "_debug.yaml")
    DebugYamlDumper.dump_to_file(self.ctb.yaml_data, filepath)
end

function ChainTreeMaster:dump_debug_yaml()
    if not DebugYamlDumper then
        print("Warning: debug_yaml_dumper not available")
        return
    end
    DebugYamlDumper.dump(self.ctb.yaml_data)
end

--- Variant of check_and_generate that also emits debug YAML
function ChainTreeMaster:check_and_generate_with_debug(debug_filepath)
    self:check_valid_chain_tree_configuration()
    self:dump_kb_functions()
    self:dump_complete_functions()
    self:generate_json()
    self:generate_debug_yaml(debug_filepath)
end
--- Backward compatibility aliases
ChainTreeMaster.generate_yaml = ChainTreeMaster.generate_json
ChainTreeMaster.check_and_generate_yaml = ChainTreeMaster.check_and_generate

function ChainTreeMaster:select_kb(kb_name)
    self.ctb:select_kb(kb_name)
end

function ChainTreeMaster:debug_function(handle, message, node, event_id)
    local timestamp = os.date("!%Y-%m-%dT%H:%M:%S")
    print(string.format("[%s] DEBUG: %s", timestamp, message))
    if node ~= nil or event_id ~= nil then
        print(string.format("  Node: %s, Event: %s", tostring(node), tostring(event_id)))
    end
end

function ChainTreeMaster:define_root_node(version)
    self.ctb.link_number = 0
    self.ctb.link_number_stack = {}
    self.root_node = self:define_gate_node("root_node",
        nil, nil, nil, nil,        -- defaults for main/init/term/aux
        { version = version },     -- column_data
        true,                      -- auto_start
        true                       -- links_flag
    )
    self.sequence_dict = {}
    self.s_expr_dict = {}
    self:initialize_state_machine_stack()
end

function ChainTreeMaster:start_test(test_name, kb_memory_factor)
    kb_memory_factor = kb_memory_factor or 10
    self:select_kb(test_name)
    self.ctb.kb_metadata[test_name] = { node_memory_factor = kb_memory_factor }
    self:define_root_node("1.0.0")
end

function ChainTreeMaster:end_test()
    self:finalize_and_check()
end

function ChainTreeMaster:pop_root_node()
    self.ctb:pop_node_element(self.root_node)
end

function ChainTreeMaster:add_state_machine_node()
    local node_data = self.sm_name_dict
    self.sm_node = self.ctb:add_node_element(
        "sm_node", "sm_node",
        "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
        node_data
    )
    self:pop_state_machine_node()
end

function ChainTreeMaster:pop_state_machine_node()
    self.ctb:pop_node_element(self.sm_node)
end

function ChainTreeMaster:check_valid_chain_tree_configuration()
    self:check_for_balance_sm()
end

function ChainTreeMaster:finalize_and_check()
    self:check_for_balance_sm()

    if next(self.sequence_dict) then
        error("Unfinished sequence ends")
    end
    if next(self.s_expr_dict) then
        error("Unfinished s_expression ends")
    end

    self:end_column(self.root_node)
    self.ctb:leave_kb()
end

function ChainTreeMaster:get_all_virtual_functions()
    local base_path = "kb.complete_functions_kb.complete_functions.complete_functions.complete_functions"

    local main_fns = self.ctb.yaml_data[base_path .. ".main_functions"].node_dict
    local one_shot_fns = self.ctb.yaml_data[base_path .. ".one_shot_functions"].node_dict
    local boolean_fns = self.ctb.yaml_data[base_path .. ".boolean_functions"].node_dict

    -- Collect keys
    local function keys(t)
        local out = {}
        for k, _ in pairs(t) do out[#out + 1] = k end
        return out
    end

    return {
        main_functions = keys(main_fns),
        one_shot_functions = keys(one_shot_fns),
        boolean_functions = keys(boolean_fns),
    }
end

function ChainTreeMaster:display_chain_tree_function_mapping()
    local all = self:get_all_virtual_functions()

    print("complete function mapping:")
    print("main_functions:")
    for _, fn in ipairs(all.main_functions) do
        print("--------------------------------", fn)
    end
    print("display one_shot_functions:")
    print("one_shot_functions:")
    for _, fn in ipairs(all.one_shot_functions) do
        print("--------------------------------", fn)
    end
    print("boolean_functions:")
    for _, fn in ipairs(all.boolean_functions) do
        print("--------------------------------", fn)
    end
end

function ChainTreeMaster:dump_kb_functions()
    -- Collect kb names to avoid modifying table during iteration
    local kb_names = {}
    for kb_name, _ in pairs(self.ctb.kb_log_dict) do
        kb_names[#kb_names + 1] = kb_name
    end

    for _, kb_name in ipairs(kb_names) do
        -- Skip temporary KBs
        if not kb_name:match("_functions$") then
            local temp_kb_name = kb_name .. "_functions"
            self.ctb:add_kb(temp_kb_name)
            self.ctb:select_kb(temp_kb_name)

            -- Create top-level node for this KB's function mappings
            local top_node = self.ctb:add_node_element(
                "kb", kb_name,
                "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL", {}
            )

            -- Create virtual_functions container node
            local function_node = self.ctb:add_node_element(
                "virtual_functions", "virtual_functions",
                "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL", {}
            )

            -- Add leaf nodes for each function type
            self.ctb:add_leaf_element(
                "virtual_functions", "main_functions",
                "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
                self.ctb.main_functions[kb_name]
            )

            self.ctb:add_leaf_element(
                "virtual_functions", "one_shot_functions",
                "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
                self.ctb.one_shot_functions[kb_name]
            )

            self.ctb:add_leaf_element(
                "virtual_functions", "boolean_functions",
                "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
                self.ctb.boolean_functions[kb_name]
            )

            self.ctb:add_leaf_element(
                "virtual_functions", "main_functions",
                "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
                self.ctb.main_functions[kb_name]
            )

            -- Close the nodes
            self.ctb:pop_node_element(function_node)
            self.ctb:pop_node_element(top_node)

            -- Leave this temporary KB
            self.ctb:leave_kb()

            -- Remove from kb_log_dict since this is just a temporary KB
            if self.ctb.kb_log_dict[temp_kb_name] then
                self.ctb.kb_log_dict[temp_kb_name] = nil
            end
        end
    end
end

function ChainTreeMaster:dump_complete_functions()
    self.ctb:add_kb("complete_functions_kb")
    self.ctb:select_kb("complete_functions_kb")

    -- Create top-level node
    local top_node = self.ctb:add_node_element(
        "complete_functions", "complete_functions",
        "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL", {}
    )

    -- Initialize maps for collecting unique functions
    local one_shot_map = {}
    local boolean_map = {}
    local main_map = {}

    -- Collect kb names to avoid modifying table during iteration
    local kb_names = {}
    for kb_name, _ in pairs(self.ctb.kb_log_dict) do
        kb_names[#kb_names + 1] = kb_name
    end

    -- Collect all unique functions from all KBs
    for _, kb_name in ipairs(kb_names) do
        -- one_shot functions
        if self.ctb.one_shot_functions[kb_name] then
            for fn, _ in pairs(self.ctb.one_shot_functions[kb_name]) do
                if not one_shot_map[fn] then
                    one_shot_map[fn] = true
                end
            end
        end

        -- boolean functions
        if self.ctb.boolean_functions[kb_name] then
            for fn, _ in pairs(self.ctb.boolean_functions[kb_name]) do
                if not boolean_map[fn] then
                    boolean_map[fn] = true
                end
            end
        end

        -- main functions
        if self.ctb.main_functions[kb_name] then
            for fn, _ in pairs(self.ctb.main_functions[kb_name]) do
                if not main_map[fn] then
                    main_map[fn] = true
                end
            end
        end
    end

    -- Add leaf elements for each function type
    self.ctb:add_leaf_element(
        "complete_functions", "one_shot_functions",
        "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
        one_shot_map
    )

    self.ctb:add_leaf_element(
        "complete_functions", "boolean_functions",
        "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
        boolean_map
    )

    self.ctb:add_leaf_element(
        "complete_functions", "main_functions",
        "CFL_NULL", "CFL_NULL", "CFL_NULL", "CFL_NULL",
        main_map
    )

    -- Close the top node
    self.ctb:pop_node_element(top_node)

    -- Leave the temporary KB
    self.ctb:leave_kb()
end

function ChainTreeMaster:list_kbs()
    local result = {}
    for kb_name, _ in pairs(self.ctb.kb_log_dict) do
        if not kb_name:match("_functions$") and not kb_name:match("^complete_functions_kb") then
            result[#result + 1] = kb_name
        end
    end
    return result
end

-- ---------------------------------------------------------------------------
-- Blackboard DSL (delegates to ChainTreeYaml)
-- ---------------------------------------------------------------------------

function ChainTreeMaster:define_blackboard(name)
    self.ctb:define_blackboard(name)
end

function ChainTreeMaster:bb_field(field_name, field_type, default_value)
    self.ctb:bb_field(field_name, field_type, default_value)
end

function ChainTreeMaster:end_blackboard()
    self.ctb:end_blackboard()
end

function ChainTreeMaster:define_const_record(name)
    self.ctb:define_const_record(name)
end

function ChainTreeMaster:const_field(field_name, field_type, value)
    self.ctb:const_field(field_name, field_type, value)
end

function ChainTreeMaster:end_const_record()
    self.ctb:end_const_record()
end

return ChainTreeMaster