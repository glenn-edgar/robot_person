--[[
    S-Engine Integration Test - ChainTree DSL test for s-engine module
    load/unload and tree load/unload via blackboard pointer slots.

    S-engine module se_test_module is compiled separately in s_engine/.
]]

local ChainTreeMaster = require("chain_tree_master")

-- =========================================================================
-- Test 1: Module load + single tree load
--   - Defines blackboard with uint64 slot for tree instance pointer
--   - Loads s-engine module (with user registration boolean)
--   - Loads one tree, stores instance in blackboard
--   - Runs a timer column, then terminates
-- =========================================================================

local function se_basic_load_test(ct, kb_name)
    ct:start_test(kb_name)

    -- Top-level column: module lifecycle wraps everything
    local module_column = ct:define_column("se_module_scope", nil, nil, nil, nil, nil, true)

        -- Load the s-engine module
        -- "USER_REGISTER_S_FUNCTIONS" is the user boolean function called
        -- to register user s-engine function tables.
        -- CFL_NULL would skip user registration.
        ct:se_module_load("state_machine_test", "USER_REGISTER_S_FUNCTIONS")

        -- Load a tree from the module, store instance ptr in blackboard
        ct:se_tree_load("state_machine_test", "state_machine_test", "se_tree_ptr")

        -- Tick the s-engine tree — runs until the tree terminates or disables
        ct:se_tick("se_tree_ptr")

        -- After tree completes, terminate the system
        local run_column = ct:define_column("se_run", nil, nil, nil, nil, nil, true)
            ct:asm_log_message("s-engine tree complete, shutting down")
            ct:asm_terminate_system()
        ct:end_column(run_column)

    ct:end_column(module_column)

    ct:end_test()
end

-- =========================================================================
-- Test 2: Module load + multiple tree loads
--   - Two trees from the same module, each in its own blackboard slot
--   - Tests that registry lookup works for multiple tree creates
-- =========================================================================

local function se_multi_tree_test(ct, kb_name)
    ct:start_test(kb_name)

    local module_column = ct:define_column("se_multi_scope", nil, nil, nil, nil, nil, true)

        -- Load module (no user functions for this test)
        ct:se_module_load("se_multi_module")

        -- Load two trees into separate blackboard slots
        ct:se_tree_load("se_multi_module", "tree_alpha", "se_tree_a_ptr")
        ct:se_tree_load("se_multi_module", "tree_beta",  "se_tree_b_ptr")

        local run_column = ct:define_column("se_multi_run", nil, nil, nil, nil, nil, true)
            ct:asm_log_message("two s-engine trees loaded")
            ct:asm_wait_time(2.0)
            ct:asm_log_message("s-engine multi-tree test complete")
            ct:asm_terminate_system()
        ct:end_column(run_column)

    ct:end_column(module_column)

    ct:end_test()
end

-- =========================================================================
-- Test 3: Module load with custom blackboard loader
--   - Uses the custom_bb_load_fn on se_tree_load
--   - Boolean returns true → skips default blackboard loading
-- =========================================================================

local function se_custom_bb_test(ct, kb_name)
    ct:start_test(kb_name)

    local module_column = ct:define_column("se_custom_scope", nil, nil, nil, nil, nil, true)

        ct:se_module_load("se_custom_module", "USER_REGISTER_S_FUNCTIONS")

        -- Tree load with custom blackboard loader
        -- "SE_CUSTOM_BB_LOAD" returns true → skip default bb loading
        ct:se_tree_load("se_custom_module", "se_custom_tree", "se_tree_ptr", "SE_CUSTOM_BB_LOAD")

        local run_column = ct:define_column("se_custom_run", nil, nil, nil, nil, nil, true)
            ct:asm_log_message("custom blackboard loaded")
            ct:asm_wait_time(1.0)
            ct:asm_log_message("s-engine custom bb test complete")
            ct:asm_terminate_system()
        ct:end_column(run_column)

    ct:end_column(module_column)

    ct:end_test()
end

-- =========================================================================
-- Main
-- =========================================================================

local function add_header(yaml_file)
    local ct = ChainTreeMaster.new(yaml_file)

    -- One blackboard per configuration — all fields needed across tests
    ct:define_blackboard("se_test_state")
        ct:bb_field("se_tree_ptr",    "uint64", 0)
        ct:bb_field("se_tree_a_ptr",  "uint64", 0)
        ct:bb_field("se_tree_b_ptr",  "uint64", 0)
        ct:bb_field("tick_count",     "int32",  0)
        ct:bb_field("test_result",    "int32",  0)
        ct:bb_field("state",          "int32",  0)
        ct:bb_field("custom_loaded",  "int32",  0)
    ct:end_blackboard()

    return ct
end

local test_list = {
    "se_basic_load_test",
    "se_multi_tree_test",
    "se_custom_bb_test",
}

local test_dict = {
    se_basic_load_test  = se_basic_load_test,
    se_multi_tree_test  = se_multi_tree_test,
    se_custom_bb_test   = se_custom_bb_test,
}

if arg then
    if #arg ~= 1 then
        print("Usage: luajit s_engine_test.lua <json_file>")
        os.exit(1)
    end

    local json_file = arg[1]
    print(json_file)

    local ct = add_header(json_file)
    for _, test_name in ipairs(test_list) do
        test_dict[test_name](ct, test_name)
    end

    ct:check_and_generate_yaml()
    ct:generate_debug_yaml()
    ct:display_chain_tree_function_mapping()

    local kbs = ct:list_kbs()
    print(table.concat(kbs, ", "))
    print("total nodes", ct.ctb:get_total_node_count())
end
