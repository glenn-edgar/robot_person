--[[
    S-Engine Integration Test 2 - se_engine composite node test

    Tests the se_engine composite node which wraps module load, tree load,
    and tick into a single composite. Children are ChainTree nodes
    controlled by the s-engine tree via cfl_enable_child/cfl_disable_children.

    Ported from the old Python DSL twenty_ninth_test.
]]

local ChainTreeMaster = require("chain_tree_master")

-- =========================================================================
-- Helper: insert an s-engine composite node (replaces define_s_expression_node)
-- =========================================================================

local function insert_s_expression_df_a(ct)
    local eng = ct:se_engine("chain_flow_dsl_tests", "s_expression_test_2",
                             "se_tree_a_ptr", {})
        ct:asm_log_message("s expression column s_expression_df_a is active")
        ct:asm_event_logger("----------->  displaying data flow mask events",
                            {"CFL_SECOND_EVENT"})
        ct:asm_halt()
    ct:end_se_engine(eng)
    return eng
end

local function insert_s_expression_df_b(ct)
    local eng = ct:se_engine("chain_flow_dsl_tests", "s_expression_test_2",
                             "se_tree_b_ptr", {})
        ct:asm_log_message("data flow expression column df_b is active")
        ct:asm_event_logger("----------->  displaying data flow mask events",
                            {"CFL_SECOND_EVENT"})
        ct:asm_halt()
    ct:end_se_engine(eng)
    return eng
end

-- =========================================================================
-- Test 1: Data flow mask test with two s-engine composites
-- =========================================================================

local function twenty_ninth_test(ct, kb_name)
    ct:start_test(kb_name)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)

        ct:asm_clear_bitmask({0, 1, 2, 3})

        insert_s_expression_df_a(ct)
        insert_s_expression_df_b(ct)

        ct:asm_log_message("data flow columns are instantiated")
        ct:asm_wait_time(5)
        ct:asm_set_bitmask({0, 1, 2, 3})
        ct:asm_log_message("bitmask 0,1,2,3 is set")
        ct:asm_wait_time(5)
        ct:asm_log_message("bitmask events 0 and 1 are now set")
        ct:asm_set_bitmask({0, 1})
        ct:asm_clear_bitmask({2, 3})
        ct:asm_wait_time(5)
        ct:asm_log_message("bitmask event 1 and 2 are now set")
        ct:asm_set_bitmask({1, 2})
        ct:asm_clear_bitmask({0, 3})
        ct:asm_wait_time(5)
        ct:asm_log_message("test is terminating")

        ct:asm_terminate_system()

    ct:end_column(launch_column)

    ct:end_test()
end

-- =========================================================================
-- Helper: state column child for test 30
-- =========================================================================

local function test_30_insert_state_column(ct, state_name, bb_field)
    local state_column = ct:define_column(state_name)
        ct:asm_log_message(state_name .. " column: ready")
        local eng = ct:se_engine("chain_flow_dsl_tests", "dispatch_test",
                                 bb_field, {})
        ct:end_se_engine(eng)
        ct:asm_wait_time(5)
        ct:asm_log_message(state_name .. " column: terminating")
        ct:asm_reset()
    ct:end_column(state_column)
    return state_column
end

-- =========================================================================
-- Helper: s-engine state machine composite with 4 child columns
-- =========================================================================

local function test_30_define_s_flow_state_machine_b(ct)
    local eng = ct:se_engine("chain_flow_dsl_tests", "s_expression_test_4",
                             "se_sm_ptr", {})
        test_30_insert_state_column(ct, "column_0", "se_disp_0_ptr")
        test_30_insert_state_column(ct, "column_1", "se_disp_1_ptr")
        test_30_insert_state_column(ct, "column_2", "se_disp_2_ptr")
        test_30_insert_state_column(ct, "column_3", "se_disp_3_ptr")
    ct:end_se_engine(eng)
    return eng
end

-- =========================================================================
-- Test 2: State machine controlling child columns (thirty_test)
-- =========================================================================

local function thirty_test(ct, kb_name)
    ct:start_test(kb_name)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)

        local sm_col_b = test_30_define_s_flow_state_machine_b(ct)
        ct:define_join_link(sm_col_b)
        ct:asm_log_message("launch column: is terminating")
        ct:asm_terminate_system()

    ct:end_column(launch_column)

    ct:end_test()
end

-- =========================================================================
-- Test 3: Command dispatch + event dispatch (thirty_one_test)
-- =========================================================================

local function thirty_one_test(ct, kb_name)
    ct:start_test(kb_name)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)

        ct:asm_log_message("launch column: starting")
        ct:asm_log_message("s expression link node test 7 is active")
        local node_id = ct:se_engine_link("chain_flow_dsl_tests",
                                           "s_expression_test_7", "se_link_7_ptr")
        ct:define_join_link(node_id)
        ct:asm_log_message("s expression link node test 7 is not active")

        ct:asm_log_message("s expression link node test 8 is active")
        local node_id_a = ct:se_engine_link("chain_flow_dsl_tests",
                                             "s_expression_test_8", "se_link_8_ptr")
        ct:define_join_link(node_id_a)
        ct:asm_log_message("s expression link node test 8 is not active")

        ct:asm_log_message("launch column: is terminating")
        ct:asm_terminate_system()

    ct:end_column(launch_column)

    ct:end_test()
end


-- =========================================================================
-- Main
-- =========================================================================

local function add_header(yaml_file)
    local ct = ChainTreeMaster.new(yaml_file)

    ct:define_blackboard("se_test_2_state")
        ct:bb_field("se_tree_a_ptr",  "uint64", 0)
        ct:bb_field("se_tree_b_ptr",  "uint64", 0)
        ct:bb_field("se_sm_ptr",      "uint64", 0)
        ct:bb_field("se_disp_0_ptr",  "uint64", 0)
        ct:bb_field("se_disp_1_ptr",  "uint64", 0)
        ct:bb_field("se_disp_2_ptr",  "uint64", 0)
        ct:bb_field("se_disp_3_ptr",  "uint64", 0)
        ct:bb_field("se_link_7_ptr",  "uint64", 0)
        ct:bb_field("se_link_8_ptr",  "uint64", 0)
        ct:bb_field("tick_count",     "int32",  0)
        ct:bb_field("test_result",    "int32",  0)
        ct:bb_field("state",          "int32",  0)
    ct:end_blackboard()

    return ct
end

local test_list = {
    "twenty_ninth_test",
    "thirty_test",
    "thirty_one_test",
}

local test_dict = {
    twenty_ninth_test  = twenty_ninth_test,
    thirty_test        = thirty_test,
    thirty_one_test    = thirty_one_test,
}

if arg then
    if #arg ~= 1 then
        print("Usage: luajit s_engine_test_2.lua <json_file>")
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
