--[[
    ChainTree Incremental Build - Test harness for the ChainTree DSL.
    Translated from Python to LuaJIT.

    Only first_test is active; remaining tests are commented out.
]]

local ChainTreeMaster = require("chain_tree_master")

-- =========================================================================
-- Active Test
-- =========================================================================

local function first_test(ct, kb_name)
    ct:start_test(kb_name)

    local activate_valve_column = ct:define_column("activate_valve", nil, nil, nil, nil, nil, true)
    ct:asm_one_shot_handler("ACTIVATE_VALVE", { state = "open" })
    ct:asm_log_message("Valve activated")
    ct:asm_terminate()
    ct:end_column(activate_valve_column)

    local terminate_engine_column = ct:define_column("terminate_engine", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("waiting time 12 seconds to terminate engine")
    ct:asm_wait_time(12.0)
    ct:asm_log_message("terminating engine")
    ct:asm_terminate_system()
    ct:end_column(terminate_engine_column)

    local wait_for_event_column = ct:define_column("wait_for_event", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("waiting for event")
    local wait_for_event_node = ct:asm_wait_for_event("WAIT_FOR_EVENT", 1, true, 5,
        "WAIT_FOR_EVENT_ERROR", "CFL_SECOND_EVENT", { error_message = "WAIT_FOR_EVENT_ERROR" })
    ct:asm_log_message("event received")
    ct:asm_reset()
    ct:end_column(wait_for_event_column)

    local reset_node_column = ct:define_column("reset_node", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("waiting 2 seconds to reset node")
    ct:asm_wait_time(2.0)
    ct:asm_log_message("sending system event")
    -- sending an event to a column link or leaf node
    ct:asm_send_named_event(wait_for_event_column, "WAIT_FOR_EVENT", {})
    ct:asm_log_message("resetting node")
    ct:asm_reset()
    ct:end_column(reset_node_column)

    local verify_column = ct:define_column("verify", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("verifying")
    ct:asm_verify("CFL_BOOL_FALSE", {}, false, "VERIFY_ERROR", { failure_data = "failure_data  - verify column" })
    ct:asm_log_message("waiting for verify to fail")
    ct:asm_halt()
    ct:end_column(verify_column)

    local verify_timeout_column = ct:define_column("verify_timeout", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("verifying timeout")
    ct:asm_verify_timeout(5.0, false, "VERIFY_ERROR", { failure_data = "failure_data - verify timeout column" })
    ct:asm_log_message("waiting for verify timeout to fail which will result in a terminate column")
    ct:asm_halt()
    ct:end_column(verify_timeout_column)

    ct:end_test()
end

local function second_test(ct,kb_name)
    ct:start_test(kb_name)
    
    local activate_valve_column = ct:define_column("activate_valve", nil, nil, nil, nil, nil, true)
    ct:asm_one_shot_handler("ACTIVATE_VALVE", { state = "open" })
    ct:asm_log_message("Valve activated")
    ct:asm_terminate()
    ct:end_column(activate_valve_column)
    
    local terminate_engine_column = ct:define_column("terminate_engine", nil, nil, nil, nil, nil, false)
    ct:asm_log_message("waiting time 20 seconds to terminate engine")
    ct:asm_wait_time(20.0)
    ct:asm_log_message("terminating engine")
    ct:asm_terminate_system()
    ct:end_column(terminate_engine_column)
    
    local wait_for_event_column = ct:define_column("wait_for_event", nil, nil, nil, nil, nil, false)
    ct:asm_log_message("waiting for event")
    ct:asm_wait_for_event("WAIT_FOR_EVENT", 1, true, 5,
        "WAIT_FOR_EVENT_ERROR", "CFL_SECOND_EVENT", { error_message = "WAIT_FOR_EVENT_ERROR" })
    ct:asm_log_message("event received")
    ct:asm_reset()
    ct:end_column(wait_for_event_column)

    
    local reset_node_column = ct:define_column("reset_node", nil, nil, nil, nil, nil, false)
    ct:asm_log_message("waiting 2 seconds to reset node")
    ct:asm_wait_time(2.0)
    ct:asm_log_message("sending system event")
    ct:asm_send_named_event(wait_for_event_column, "WAIT_FOR_EVENT", {})
    ct:asm_log_message("resetting node")
    ct:asm_reset()
    ct:end_column(reset_node_column)

    local enable_column = ct:define_column("start_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("waiting 5 seconds to start rest of columns")
    ct:asm_wait_time(5.0)
    ct:asm_log_message("starting rest of columns")
    ct:asm_enable_nodes({ activate_valve_column, terminate_engine_column, wait_for_event_column, reset_node_column })
    ct:asm_log_message("waiting 8 seconds to disable column")
    ct:asm_wait_time(8.0)
    ct:asm_disable_nodes({ terminate_engine_column })
    ct:asm_log_message("waiting 20 seconds to end test")
    ct:asm_wait_time(20.0)
    ct:asm_log_message("ending test")
    ct:asm_terminate_system()
    ct:end_column(enable_column)
    
    ct:end_test()
end


local function fourth_test(ct,kb_name)
    ct:start_test(kb_name)
    
    local top_column = ct:define_column("top_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("top column")
    
    local middle_column = ct:define_column("middle_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("middle column")
    ct:asm_event_logger("displaying middle column events", { "PUBLISH_EVENT" })
    ct:asm_halt()
    ct:end_column(middle_column)
    
    
    
    ct:asm_send_named_event(top_column, "PUBLISH_EVENT", { event_data = "event_data" })
    ct:asm_log_message("waiting 2 seconds")
    ct:asm_wait_time(2.0)
    ct:asm_log_message("resetting top column")
    ct:asm_reset()
    ct:end_column(top_column)
    
    
    local time_out_column = ct:define_column("time_out_column", nil, nil, nil, nil, nil, true)
    ct:asm_wait_time(20.0)
    ct:asm_terminate_system()
    ct:end_column(time_out_column)
    
    
    
    ct:end_test()
end


--[[
  test_fifth.lua - State machine test definition
  LuaJIT port of Python fifth_test
--]]

local function fifth_test(ct, kb_name) -- state machine
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column")
    ct:asm_log_message("launching state machine 1")
    local sm_name_1 = "state_machine_1"
    local state_machine_1 = ct:define_state_machine("state_machine_1", sm_name_1,
        {"state1", "state2", "state3"}, "state2", true)

    local state1_1 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:change_state(state_machine_1, "state2")
    ct:asm_halt()
    ct:end_column(state1_1)

    local state2_1 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:change_state(state_machine_1, "state3")
    ct:asm_halt()
    ct:end_column(state2_1)

    local state3_1 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:change_state(state_machine_1, "state1")
    ct:asm_halt()
    ct:end_column(state3_1)

    ct:end_state_machine(state_machine_1, "state_machine_1")
    ct:asm_wait_time(10)
    ct:asm_log_message("terminating state machine 1")
    ct:terminate_state_machine(state_machine_1)
    local sm_name_2 = "state_machine_2"
    local state_machine_2 = ct:define_state_machine("state_machine_2", sm_name_2,
        {"state1", "state2", "state3"}, "state3", true, "CFL_SM_EVENT_SYNC")

    local state1_2 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_event_logger("displaying state 1 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3", "TEST_EVENT_4"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    
    ct:change_state(state_machine_2, "state2", "SYNC_EVENT")
    ct:asm_log_message("state2 changed")
    ct:asm_halt()
    ct:end_column(state1_2)

    local state2_2 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_event_logger("displaying state 2 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3", "TEST_EVENT_4"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state3")
    ct:asm_halt()
    ct:end_column(state2_2)

    local state3_2 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_event_logger("displaying state 3 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3", "TEST_EVENT_4"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state1", "SYNC_EVENT")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_4", {})
    ct:asm_log_message("sending event 4 to state machine 1")
    ct:asm_halt()
    ct:end_column(state3_2)

    ct:end_state_machine(state_machine_2, "state_machine_2")

    ct:asm_wait_time(20)
    ct:asm_log_message("terminating state machine 2")
    ct:terminate_state_machine(state_machine_2)

    ct:asm_log_message("launch column is terminating")

    ct:end_column(launch_column)

    ct:end_test()
end

--[[
  test_definitions.lua - ChainTree test definitions (tests 6-9)
  LuaJIT port of Python test construction code

  Signature reference:
    define_column(column_name, main_function, init_function, term_function, aux_function, column_data, auto_start, label, links_flag)
    define_fork_column(column_name, main_function, init_function, term_function, aux_function, column_data, auto_start, label)
    define_join_link(parent_node_name)
    end_column(column_name)
    define_sequence_start_node(column_name, main_function, init_function, term_function, aux_function, initialize_function, finalize_function, user_data, auto_start)
    define_sequence_til_pass_node(column_name, main_function, init_function, term_function, aux_function, finalize_function, user_data, auto_start)
    define_sequence_til_fail_node(column_name, main_function, init_function, term_function, aux_function, finalize_function, user_data, auto_start)
    mark_sequence_false_link(parent_node_name, data)
    mark_sequence_true_link(parent_node_name, data)
    end_sequence_node(column_name)
--]]

local function insert_fork_column(ct)

    local fork_column = ct:define_fork_column("fork_column")
    local fork_child_1 = ct:define_column("fork_child_1")
    ct:asm_log_message("fork child 1 starting")
    ct:asm_event_logger("displaying fork child 1 events", {"TEST_EVENT"})
    ct:asm_halt()
    ct:end_column(fork_child_1)


    local fork_child_2 = ct:define_column("fork_child_2")
    ct:asm_log_message("fork child 2 starting")
    ct:asm_event_logger("displaying fork child 2 events", {"TEST_EVENT"})
    ct:asm_halt()
    ct:end_column(fork_child_2)

    local fork_child_3 = ct:define_column("fork_child_3")
    ct:asm_log_message("fork child 3 starting")
    ct:asm_event_logger("displaying fork child 3 events", {"TEST_EVENT"})
    ct:asm_wait_time(2)
    ct:asm_log_message("child 3 executed a time delay of 2 seconds")
    ct:asm_wait_time(15)
    ct:asm_halt()
    ct:end_column(fork_child_3)
    ct:end_column(fork_column)
end


local function sixth_test(ct, kb_name)

    ct:start_test(kb_name)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column")

    ct:asm_wait_time(1.5)
    ct:asm_log_message("launching fork column")

    insert_fork_column(ct)

    ct:asm_log_message("fork column launched")
    ct:asm_event_logger("displaying fork column events", {"TEST_EVENT"})

    ct:asm_wait_time(5)
    ct:asm_log_message("resetting launch column")
    ct:asm_reset()
    ct:end_column(launch_column)


    local event_generator_column = ct:define_column("event_generator_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("sending event to launch column")
    ct:asm_send_named_event(launch_column, "TEST_EVENT", {event_data="event_data"})
    ct:asm_wait_time(1)
    ct:asm_reset()
    ct:end_column(event_generator_column)

    local end_column = ct:define_column("end_column", nil, nil, nil, nil, nil, true)

    ct:asm_wait_time(20)
    ct:asm_log_message("ending test")
    ct:asm_terminate_system()
    ct:end_column(end_column)

    ct:end_test()
end

local function insert_fork_join_column(ct)
    local fork_join_column = ct:define_fork_column("fork_column")
    local fork_child_1 = ct:define_column("fork_child_1")
    ct:asm_log_message("fork child 1 starting")
    ct:asm_event_logger("displaying fork child 1 events", {"TEST_EVENT"})
    ct:asm_wait_time(2)
    ct:asm_log_message("fork 1 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_1)


    local fork_child_2 = ct:define_column("fork_child_2")
    ct:asm_log_message("fork child 2 starting")
    ct:asm_event_logger("displaying fork child 2 events", {"TEST_EVENT"})
    ct:asm_wait_time(3)
    ct:asm_log_message("fork 2 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_2)

    local fork_child_3 = ct:define_column("fork_child_3")
    ct:asm_log_message("fork child 3 starting")
    ct:asm_event_logger("displaying fork child 3 events", {"TEST_EVENT"})
    ct:asm_wait_time(4)
    ct:asm_log_message("fork 3 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_3)

    ct:end_column(fork_join_column)
    ct:define_join_link(fork_join_column)
end


local function seventh_test(ct, kb_name) -- fork column
    ct:start_test(kb_name)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column")

    ct:asm_wait_time(1.5)
    ct:asm_log_message("launching fork column")

    insert_fork_join_column(ct)
    ct:asm_log_message("fork column joined")
    ct:asm_event_logger("displaying fork column events", {"TEST_EVENT"})
    ct:asm_log_message("waiting 5 seconds to reset launch column")
    ct:asm_wait_time(5)
    ct:asm_log_message("resetting launch column")
    ct:asm_reset()
    ct:end_column(launch_column)


    local event_generator_column = ct:define_column("event_generator_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("sending event to launch column")
    ct:asm_send_named_event(launch_column, "TEST_EVENT", {event_data="event_data"})
    ct:asm_wait_time(1)
    ct:asm_reset()
    ct:end_column(event_generator_column)

    local end_column = ct:define_column("end_column", nil, nil, nil, nil, nil, true)
    ct:asm_wait_time(20)
    ct:asm_log_message("ending test")
    ct:asm_terminate_system()
    ct:end_column(end_column)

    ct:end_test()
end


local function insert_fork_join_column_a(ct)

    local sequence_til_pass_node = ct:define_sequence_til_pass_node(
        "sequence_til_pass_node", nil, nil, nil, nil,
        "DISPLAY_SEQUENCE_TILL_RESULT", {message="sequence till pass"})

    local fork_child_1 = ct:define_column("fork_child_1")
    ct:asm_log_message("fork child 1 starting")
    ct:asm_event_logger("displaying fork child 1 events", {"TEST_EVENT"})
    ct:asm_wait_time(2)
    ct:mark_sequence_false_link(sequence_til_pass_node, {message="first sequence failed"})
    ct:asm_log_message("fork 1 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_1)


    local fork_child_2 = ct:define_column("fork_child_2")
    ct:asm_log_message("fork child 2 starting")
    ct:asm_event_logger("displaying fork child 2 events", {"TEST_EVENT"})
    ct:asm_wait_time(3)
    ct:mark_sequence_false_link(sequence_til_pass_node, {message="second sequence failed"})
    ct:asm_log_message("fork 2 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_2)

    local fork_child_3 = ct:define_column("fork_child_3")
    ct:asm_log_message("fork child 3 starting")
    ct:asm_event_logger("displaying fork child 3 events", {"TEST_EVENT"})
    ct:asm_wait_time(5)
    ct:mark_sequence_false_link(sequence_til_pass_node, {message="third sequence failed"})
    ct:asm_log_message("fork 3 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_3)

    ct:end_sequence_node(sequence_til_pass_node)
end


local function eighth_test(ct, kb_name) -- sequence til
    ct:start_test(kb_name)

    local main_node = ct:define_sequence_start_node(
        "main_node", nil, nil, nil, nil,
        "INITIALIZE_SEQUENCE", "DISPLAY_SEQUENCE_RESULT", nil, true)
    ct:asm_log_message("main node")
    insert_fork_join_column_a(ct)
    ct:asm_log_message("main node is terminating")
    ct:asm_terminate()
    ct:end_column(main_node)

    ct:end_test()
end

local function insert_sequence_til_fail_column(ct)

    local sequence_til_fail_node = ct:define_sequence_til_fail_node(
        "sequence_til_fail_node", nil, nil, nil, nil,
        "DISPLAY_SEQUENCE_TILL_RESULT", {message="sequence till fail"})

    local fork_child_1 = ct:define_column("fork_child_1")
    ct:asm_log_message("fork child 1 starting")
    ct:asm_event_logger("displaying fork child 1 events", {"TEST_EVENT"})
    ct:asm_wait_time(2)
    ct:mark_sequence_true_link(sequence_til_fail_node, {message="first sequence passed"})
    ct:asm_log_message("fork 1 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_1)


    local fork_child_2 = ct:define_column("fork_child_2")
    ct:asm_log_message("fork child 2 starting")
    ct:asm_event_logger("displaying fork child 2 events", {"TEST_EVENT"})
    ct:asm_wait_time(3)
    ct:mark_sequence_true_link(sequence_til_fail_node, {message="second sequence passed"})
    ct:asm_log_message("fork 2 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_2)

    local fork_child_3 = ct:define_column("fork_child_3")
    ct:asm_log_message("fork child 3 starting")
    ct:asm_event_logger("displaying fork child 3 events", {"TEST_EVENT"})
    ct:asm_wait_time(5)
    ct:mark_sequence_true_link(sequence_til_fail_node, {message="third sequence passed"})
    ct:asm_log_message("fork 3 is terminating")
    ct:asm_terminate()
    ct:end_column(fork_child_3)

 
    ct:end_sequence_node(sequence_til_fail_node)
end

local function ninth_test(ct, kb_name) -- sequence til
    ct:start_test(kb_name)

    local main_node = ct:define_sequence_start_node(
        "main_node", nil, nil, nil, nil,
        nil, "DISPLAY_SEQUENCE_RESULT", nil, true)
    ct:asm_log_message("main node")
    insert_sequence_til_fail_column(ct)
    ct:asm_log_message("main node is terminating")
    ct:asm_terminate()
    ct:end_column(main_node)

    ct:end_test()
end


--[[
  test_supervisor.lua - ChainTree supervisor test definitions (test 10)
  LuaJIT port of Python test construction code
--]]

local function test_one_for_one_test(ct, top_column_name)
    local top_column = ct:define_column(top_column_name, nil, nil, nil, nil, nil, true)

    local supervisor_node = ct:define_supervisor_one_for_one_node(
        "supervisor_node", "CFL_NULL", {}, nil, false, nil, nil, true)

    local branch_1 = ct:define_column("branch_1", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 1 starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("branch 1 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 1 failed"})
    ct:asm_terminate()
    ct:end_column(branch_1)

    local branch_2 = ct:define_column("branch_2", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 2 starting")
    ct:asm_wait_time(3)
    ct:asm_log_message("branch 2 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 2 failed"})
    ct:asm_terminate()
    ct:end_column(branch_2)

    ct:end_column(supervisor_node)
    ct:asm_log_message("waiting 20 seconds to terminate top column")
    ct:asm_wait_time(20)
    ct:asm_log_message("top column is terminating")
    ct:asm_terminate()
    ct:end_column(top_column)
    return top_column
end

local function test_one_for_all_test(ct, top_column_name)
    local top_column = ct:define_column(top_column_name, nil, nil, nil, nil, nil, true)

    local supervisor_node = ct:define_supervisor_one_for_all_node(
        "supervisor_node", "CFL_NULL", {}, nil, false, nil, nil, true)

    local branch_1 = ct:define_column("branch_1", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 1 starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("branch 1 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 1 failed"})
    ct:asm_terminate()
    ct:end_column(branch_1)

    local branch_2 = ct:define_column("branch_2", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 2 starting")
    ct:asm_wait_time(3)
    ct:asm_log_message("branch 2 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 2 failed"})
    ct:asm_terminate()
    ct:end_column(branch_2)

    local branch_3 = ct:define_column("branch_3", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 3 starting")
    ct:asm_wait_time(20)
    ct:asm_log_message("branch 3 is resetting")
    ct:asm_reset()
    ct:end_column(branch_3)


    ct:end_column(supervisor_node)

    ct:asm_log_message("waiting 20 seconds to terminate top column")
    ct:asm_wait_time(20)
    ct:asm_log_message("top column is terminating")
    ct:asm_terminate()
    ct:end_column(top_column)
    return top_column
end


local function test_rest_for_all_test(ct, top_column_name)

    local top_column = ct:define_column(top_column_name, nil, nil, nil, nil, nil, true)

    local supervisor_node = ct:define_supervisor_rest_for_all_node(
        "supervisor_node", "CFL_NULL", {}, nil, false, nil, nil, true)

    local branch_1 = ct:define_column("branch_1", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 1 starting")
    ct:asm_wait_time(21)
    ct:asm_log_message("branch 1 is resetting")
    ct:asm_reset()
    ct:end_column(branch_1)

    local branch_2 = ct:define_column("branch_2", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 2 starting")
    ct:asm_wait_time(3)
    ct:asm_log_message("branch 2 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 2 failed"})
    ct:asm_terminate()
    ct:end_column(branch_2)



    local branch_3 = ct:define_column("branch_3", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 3 starting")
    ct:asm_wait_time(120)
    ct:asm_log_message("branch 3 is resetting")
    ct:asm_reset()
    ct:end_column(branch_3)


    ct:end_column(supervisor_node)
    ct:asm_log_message("waiting 20 seconds to terminate top column")
    ct:asm_wait_time(20)
    ct:asm_log_message("top column is terminating")
    ct:asm_terminate()
    ct:end_column(top_column)
    return top_column
end

local function test_failure_window_test(ct, top_column_name)
    local top_column = ct:define_column(top_column_name, nil, nil, nil, nil, nil, true)
    local uplink_node_id = 34 -- dummy will be filled in actual use
    local supervisor_node = ct:define_supervisor_one_for_all_node(
        "supervisor_node", "CFL_NULL", {uplink_node_id=uplink_node_id},
        nil, true, 3, 100, true,
        "DISPLAY_FAILURE_WINDOW_RESULT", {})

    local branch_1 = ct:define_column("branch_1", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 1 starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("branch 1 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 1 failed"})
    ct:asm_terminate()
    ct:end_column(branch_1)

    local branch_2 = ct:define_column("branch_2", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 2 starting")
    ct:asm_wait_time(120)
    ct:asm_log_message("branch 2 is terminating")
    ct:define_mark_supervisor_node_failure({message="branch 2 failed"})
    ct:asm_terminate()
    ct:end_column(branch_2)

    local branch_3 = ct:define_column("branch_3", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 3 starting")
    ct:asm_wait_time(120)
    ct:asm_log_message("branch 3 is resetting")
    ct:asm_reset()
    ct:end_column(branch_3)


    ct:end_column(supervisor_node)
    ct:define_join_link(supervisor_node)
    ct:asm_log_message("top column is terminating")
    ct:asm_terminate()
    ct:end_column(top_column)
    return top_column
end

local function tenth_test(ct, kb_name) -- supervisor node
    ct:start_test(kb_name)
    local test_start = ct:define_column("test_coordinator_node", nil, nil, nil, nil, nil, true)

    ct:asm_log_message("starting test one for one")
    local test_one_for_one = test_one_for_one_test(ct, "one_for_one_column")
    ct:define_join_link(test_one_for_one)


    ct:asm_log_message("starting test one for all")
    local test_one_for_all = test_one_for_all_test(ct, "one_for_all_column")
    ct:define_join_link(test_one_for_all)

    ct:asm_log_message("starting test rest for all")
    local test_reset_for_all = test_rest_for_all_test(ct, "rest_for_all_column")
    ct:define_join_link(test_reset_for_all)

    ct:asm_log_message("testing failure window test")
    local test_failure_window = test_failure_window_test(ct, "failure_window_column")
    ct:define_join_link(test_failure_window)

    ct:asm_log_message("test coordinator node is terminating")
    ct:asm_terminate()
    ct:end_column(test_start)

    ct:end_test()
end

--[[
  test_for_while.lua - ChainTree for/while test definitions (tests 11-12)
--]]

local function eleventh_test(ct, kb_name) -- for column
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    local for_column = ct:define_for_column("for_column", 3, nil, nil, nil, nil, nil, true)
    local branch_1 = ct:define_column("branch_1", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 1 starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("branch 1 is terminating")
    ct:asm_terminate()
    ct:end_column(branch_1)

    ct:end_column(for_column)

    ct:define_join_link(for_column)
    ct:asm_log_message("for column is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    ct:end_test()
end


local function twelfth_test(ct, kb_name) -- while column
    ct:start_test(kb_name)

    local while_column = ct:define_while_column("while_column", nil, nil, nil, "WHILE_TEST", {count=5}, true)
    local branch_1 = ct:define_column("branch_1", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("branch 1 starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("branch 1 is terminating")
    ct:asm_terminate()
    ct:end_column(branch_1)
    ct:end_column(while_column)

    ct:end_test()
end

--[[
  test_watchdog.lua - ChainTree watchdog test definition (test 13)
--]]

local function thirteenth_test(ct, kb_name) -- watch dog
    ct:start_test(kb_name)

    local watch_dog_column = ct:define_column("watch_dog_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("starting watch dog column")
    local wd_node_id = ct:asm_watch_dog_node(30, true, "WATCH_DOG_TIME_OUT",
        {message="************ watch dog time out  reset action"})
    ct:asm_log_message("watch dog node enabled")
    ct:asm_enable_watch_dog(wd_node_id)
    ct:asm_wait_time(2)
    ct:asm_log_message("patting watch dog")
    ct:asm_pat_watch_dog(wd_node_id)
    ct:asm_wait_time(2)
    ct:asm_log_message("disabling watch dog")
    ct:asm_disable_watch_dog(wd_node_id)
    ct:asm_wait_time(4)
    ct:asm_log_message("enabling watch dog")
    ct:asm_enable_watch_dog(wd_node_id)
    ct:asm_wait_time(10)
    ct:asm_log_message("this should not be reached")
    ct:asm_terminate()
    ct:end_column(watch_dog_column)

    local end_column = ct:define_column("end_column", nil, nil, nil, nil, nil, true)
    ct:asm_wait_time(33)
    ct:asm_log_message("ending test")
    ct:asm_terminate_system()
    ct:end_column(end_column)

    ct:end_test()
end

--[[
  test_data_flow.lua - ChainTree data flow bitmask test definition (test 14)
--]]

local function insert_event_mask_df_a(ct)

    local data_flow_mask_column = ct:define_data_flow_event_mask(
        "df_mask", "CFL_NULL", {},{"a", "c"}, {"d", "e", "f"})

    ct:asm_log_message("data flow expression column df_a is active")
    ct:asm_event_logger("----------->  displaying data flow mask events", {"CFL_SECOND_EVENT"})
    ct:asm_halt()
    ct:end_column(data_flow_mask_column)
    return data_flow_mask_column
end

local function insert_event_mask_df_b(ct)
    
    local data_flow_mask_column = ct:define_data_flow_event_mask(
        "df_mask", "CFL_NULL",{}, {"b", "c"}, {"d", "e", "f"})

    ct:asm_log_message("data flow expression column df_b is active")
    ct:asm_event_logger("----------->  displaying data flow mask events", {"CFL_SECOND_EVENT"})
    ct:asm_halt()
    ct:end_column(data_flow_mask_column)
    return data_flow_mask_column
end


local function fourteenth_test(ct, kb_name) -- data flow

    ct:start_test(kb_name)

    ct:asm_clear_bitmask({"a", "b", "c", "d", "e", "f"})
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    insert_event_mask_df_a(ct)
    insert_event_mask_df_b(ct)

    ct:asm_log_message("data flow columns are instantiated")
    ct:asm_wait_time(5)
    ct:asm_set_bitmask({"a", "c"})
    ct:asm_log_message("bitmask event a and c are set")
    ct:asm_wait_time(5)
    ct:asm_log_message("bitmask event b is now set")
    ct:asm_set_bitmask({"b"})
    ct:asm_log_message("bitmask event a is now cleared")
    ct:asm_clear_bitmask({"a"})
    ct:asm_wait_time(5)
    ct:asm_log_message("bitmask event b and c are now cleared")
    ct:asm_clear_bitmask({"b", "c"})

    ct:asm_wait_time(5)
    ct:asm_log_message("test is terminating")

    ct:asm_terminate()
    ct:end_column(launch_column)

    ct:end_test()
end


--[[
  test_exception.lua - ChainTree exception handler test definitions (test 17)
--]]

local function insert_good_main_column(ct, name)
    local main_column = ct:define_main_exception_column(name, nil, nil, nil, nil, nil, true)
    ct:asm_log_message("main column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("main column is terminating")
    ct:asm_terminate()
    ct:end_main_exception_column(main_column)
    return main_column
end

local function insert_bad_main_column(ct, name)
    local main_column = ct:define_main_exception_column(name, nil, nil, nil, nil, nil, true)
    ct:asm_log_message("main column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 1")
    ct:asm_set_exception_step(1)
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 2")
    ct:asm_set_exception_step(2)
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 3")
    ct:asm_set_exception_step(3)
    ct:asm_wait_time(2)
    ct:asm_log_message("main column is terminating")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_main_exception_column(main_column)
    return main_column
end

local function insert_good_recovery_column(ct, name)
    local recover_column = ct:define_recovery_column(name, 5, "USER_SKIP_CONDITION",
        {skip_condition_data="good_recovery_condition"})

    local step_5_column = ct:define_column("step_5_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 5 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 5 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_5_column)
    local step_4_column = ct:define_column("step_4_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 4 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 4 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_4_column)
    local step_3_column = ct:define_column("step_3_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 3 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 3 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_3_column)
    local step_2_column = ct:define_column("step_2_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 2 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 2 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_2_column)
    local step_1_column = ct:define_column("step_1_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 1 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 1 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_1_column)
    local step_0_column = ct:define_column("step_0_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 0 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 0 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_0_column)

    ct:asm_log_message("recovery column is terminating")
    ct:asm_terminate()
    ct:end_recovery_column(recover_column)
    return recover_column
end

local function insert_bad_recovery_column(ct, name)

    local recover_column = ct:define_recovery_column(name, 5, "USER_SKIP_CONDITION",
        {skip_condition_data="has_raised_exception"})

    local step_5_column = ct:define_column("step_5_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 5 column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("step 5 column is raising exception")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_column(step_5_column)
    local step_4_column = ct:define_column("step_4_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 4 column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("step 4 column is raising exception")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_column(step_4_column)
    local step_3_column = ct:define_column("step_3_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 3 column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("step 3 column is raising exception")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_column(step_3_column)
    local step_2_column = ct:define_column("step_2_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 2 column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("step 2 column is raising exception")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_column(step_2_column)
    local step_1_column = ct:define_column("step_1_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 1 column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("step 1 column is raising exception")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_column(step_1_column)
    local step_0_column = ct:define_column("step_0_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 0 column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("step 0 column is raising exception")
    ct:asm_raise_exception(1, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_column(step_0_column)
    ct:asm_log_message("recovery column is terminating")
    ct:asm_terminate()
    ct:end_recovery_column(recover_column)
    return recover_column
end


local function insert_good_finalize_column(ct, name)
    local finalize_column = ct:define_finalize_column(name)
    ct:asm_log_message("finalize column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("finalize column is terminating")
    ct:asm_terminate()
    ct:end_finalize_column(finalize_column)
    return finalize_column
end

local function insert_bad_finalize_column(ct, name)
    local finalize_column = ct:define_finalize_column(name)
    ct:asm_log_message("finalize column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("finalize column is generating exception")
    ct:asm_raise_exception(3, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_finalize_column(finalize_column)
    return finalize_column
end


local function insert_exception_catch_column(ct, name)

    local exception_catch_column = ct:define_exception_catch(
        name, "EXCEPTION_FILTER",
        {exception_filter_data="exception_filter_data"},
        "EXCEPTION_LOGGING",
        {logging_function_data="logging_function_data"},
        true)

    return exception_catch_column
end

local function end_exception_catch_column(ct, name)
    ct:exception_catch_end(name)
end

local function seventeenth_test(ct, kb_name) -- exception handler
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column is starting")
    local catch_all_exception_column = ct:catch_all_exception(
        "catch_all_exception_column", "CATCH_ALL_EXCEPTION",
        {aux_data="aux_data"}, true)
    ct:asm_log_message("exception combo 1 is starting")
    local exception_catch_column_1 = insert_exception_catch_column(ct, "combo_1")
    insert_good_main_column(ct, "combo_1_main")
    insert_good_recovery_column(ct, "combo_1_recovery")
    insert_good_finalize_column(ct, "combo_1_finalize")
    end_exception_catch_column(ct, exception_catch_column_1)
    ct:define_join_link(exception_catch_column_1)
    ct:asm_wait_time(1)
    ct:asm_log_message("exception combo 2 is starting")
    local exception_catch_column_2 = insert_exception_catch_column(ct, "combo_2")
    insert_bad_main_column(ct, "combo_2_main")
    insert_good_recovery_column(ct, "combo_2_recovery")
    insert_good_finalize_column(ct, "combo_2_finalize")
    end_exception_catch_column(ct, exception_catch_column_2)
    ct:define_join_link(exception_catch_column_2)
    ct:asm_wait_time(1)
    ct:asm_log_message("exception combo 3 is starting")
    local exception_catch_column_3 = insert_exception_catch_column(ct, "combo_3")
    insert_bad_main_column(ct, "combo_3_main")
    insert_bad_recovery_column(ct, "combo_3_recovery")
    insert_good_finalize_column(ct, "combo_3_finalize")
    end_exception_catch_column(ct, exception_catch_column_3)
    ct:define_join_link(exception_catch_column_3)
    ct:asm_wait_time(1)
    ct:asm_log_message("exception combo 4 is starting")
    local exception_catch_column_4 = insert_exception_catch_column(ct, "combo_4")
    insert_good_main_column(ct, "combo_4_main")
    insert_good_recovery_column(ct, "combo_4_recovery")
    insert_bad_finalize_column(ct, "combo_4_finalize")
    end_exception_catch_column(ct, exception_catch_column_4)
    ct:define_join_link(exception_catch_column_4)

    ct:end_catch_all_exception(catch_all_exception_column)
    ct:define_join_link(catch_all_exception_column)
    ct:asm_log_message("launch column is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    ct:end_test()
end

--[[
  test_exception_heartbeat.lua - ChainTree exception handler heartbeat test (test 18)
--]]

local function insert_good_main_column_heartbeat(ct, name)
    local main_column = ct:define_main_exception_column(name, nil, nil, nil, nil, nil, true)
    ct:asm_log_message("main column is starting")
    ct:asm_turn_heartbeat_on(50)
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 1")
    ct:asm_set_exception_step(1)
    ct:asm_heartbeat_event()
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 2")
    ct:asm_set_exception_step(2)
    ct:asm_heartbeat_event()
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 3")
    ct:asm_set_exception_step(3)
    ct:asm_wait_time(2)
    ct:asm_turn_heartbeat_off()
    ct:asm_log_message("main column is terminating")

    ct:asm_terminate()
    ct:end_main_exception_column(main_column)
    return main_column
end


local function insert_bad_main_column_heartbeat(ct, name)
    local main_column = ct:define_main_exception_column(name, nil, nil, nil, nil, nil, true)
    ct:asm_log_message("main column is starting")
    ct:asm_turn_heartbeat_on(50)
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 1")
    ct:asm_set_exception_step(1)
    ct:asm_heartbeat_event()
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 2")
    ct:asm_set_exception_step(2)
    --ct:asm_heartbeat_event()
    ct:asm_wait_time(2)
    ct:asm_log_message("setting step 3")
    ct:asm_set_exception_step(3)
    ct:asm_wait_time(2)
    ct:asm_turn_heartbeat_off()
    ct:asm_log_message("main column is terminating")

    ct:asm_terminate()
    ct:end_main_exception_column(main_column)
    return main_column
end


local function insert_good_recovery_column_heartbeat(ct, name)
    local recover_column = ct:define_recovery_column(name, 5, "USER_SKIP_CONDITION",
        {skip_condition_data="good_recovery_condition"})

    local step_5_column = ct:define_column("step_5_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 5 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 5 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_5_column)
    local step_4_column = ct:define_column("step_4_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 4 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 4 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_4_column)
    local step_3_column = ct:define_column("step_3_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 3 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 3 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_3_column)
    local step_2_column = ct:define_column("step_2_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 2 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 2 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_2_column)
    local step_1_column = ct:define_column("step_1_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 1 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 1 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_1_column)
    local step_0_column = ct:define_column("step_0_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 0 column is starting")
    ct:asm_wait_time(5)
    ct:asm_log_message("step 0 column is terminating")
    ct:asm_terminate()
    ct:end_column(step_0_column)

    ct:asm_log_message("recovery column is terminating")
    ct:asm_terminate()
    ct:end_recovery_column(recover_column)
    return recover_column
end


local function insert_good_finalize_column_heartbeat(ct, name)
    local finalize_column = ct:define_finalize_column(name)
    ct:asm_log_message("finalize column is starting")
    ct:asm_wait_time(2)
    ct:asm_log_message("finalize column is terminating")
    ct:asm_terminate()
    ct:end_finalize_column(finalize_column)
    return finalize_column
end

local function insert_bad_finalize_column_heartbeat(ct, name)
    local finalize_column = ct:define_finalize_column(name)
    ct:asm_log_message("finalize column is starting")
    ct:asm_turn_heartbeat_on(10)
    ct:asm_wait_time(2)
    ct:asm_log_message("finalize column is generating exception")
    ct:asm_raise_exception(3, {exception_data="exception_data"})
    ct:asm_terminate()
    ct:end_finalize_column(finalize_column)
    return finalize_column
end


local function insert_exception_catch_column_heartbeat(ct, name)

    local exception_catch_column = ct:define_exception_catch(
        name, "EXCEPTION_FILTER",
        {exception_filter_data="exception_filter_data"},
        "EXCEPTION_LOGGING",
        {logging_function_data="logging_function_data"},
        true)

    return exception_catch_column
end

local function end_exception_catch_column_heartbeat(ct, name)
    ct:exception_catch_end(name)
end


local function eighteenth_test(ct, kb_name) -- exception handler heartbeat
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column is starting")
    local catch_all_exception_column = ct:catch_all_exception(
        "catch_all_exception_column", "CATCH_ALL_EXCEPTION",
        {aux_data="aux_data"}, true)
    ct:asm_log_message("exception combo 1 is starting")
    local exception_catch_column_1 = insert_exception_catch_column_heartbeat(ct, "combo_1")
    insert_good_main_column_heartbeat(ct, "combo_1_main_heartbeat")
    insert_good_recovery_column_heartbeat(ct, "combo_1_recovery_heartbeat")
    insert_good_finalize_column_heartbeat(ct, "combo_1_finalize_heartbeat")
    end_exception_catch_column_heartbeat(ct, exception_catch_column_1)
    ct:define_join_link(exception_catch_column_1)
    ct:asm_wait_time(1)
    ct:asm_log_message("exception combo 2 is starting")
    local exception_catch_column_2 = insert_exception_catch_column_heartbeat(ct, "combo_2")
    insert_bad_main_column_heartbeat(ct, "combo_2_main_heartbeat")
    insert_good_recovery_column_heartbeat(ct, "combo_2_recovery_heartbeat")
    insert_good_finalize_column_heartbeat(ct, "combo_2_finalize_heartbeat")
    end_exception_catch_column_heartbeat(ct, exception_catch_column_2)
    ct:define_join_link(exception_catch_column_2)
    ct:asm_wait_time(1)

    ct:asm_log_message("exception combo 4 is starting")
    local exception_catch_column_4 = insert_exception_catch_column_heartbeat(ct, "combo_4")
    insert_good_main_column_heartbeat(ct, "combo_4_main_heartbeat")
    insert_good_recovery_column_heartbeat(ct, "combo_4_recovery_heartbeat")
    insert_bad_finalize_column_heartbeat(ct, "combo_4_finalize_heartbeat")
    end_exception_catch_column_heartbeat(ct, exception_catch_column_4)
    ct:define_join_link(exception_catch_column_4)

    ct:end_column(catch_all_exception_column)
    ct:define_join_link(catch_all_exception_column)
    ct:asm_log_message("launch column is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    ct:end_test()
end

--[[
  test_state_machine_advanced.lua - ChainTree advanced state machine tests (test 19)
--]]

local function inner_state_sequential_machine(ct)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("sequential machine sm test is starting")
    ct:asm_log_message("launching state machine 1")


    local container_column_1 = ct:define_column("container_column_1", nil, nil, nil, nil, nil, true)

    local sm_name_1 = "sequential_state_machine_1"
    local state_machine_1 = ct:define_state_machine("state_machine_1", sm_name_1,
        {"state1", "state2", "state3"}, "state2", true)

    local state1_1 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:change_state(state_machine_1, "state2")
    ct:asm_halt()
    ct:end_column(state1_1)

    local state2_1 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:change_state(state_machine_1, "state3")
    ct:asm_halt()
    ct:end_column(state2_1)

    local state3_1 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:change_state(state_machine_1, "state1")
    ct:asm_halt()
    ct:end_column(state3_1)

    ct:end_state_machine(state_machine_1, "sequential_state_machine_1")
    ct:asm_wait_time(10)
    ct:asm_log_message("terminating state machine 1")
    ct:terminate_state_machine(state_machine_1)
    ct:end_column(container_column_1)
    ct:define_join_link(container_column_1)

    local sm_name_2 = "parallel_state_machine_2"

    local container_column_2 = ct:define_column("container_column_2", nil, nil, nil, nil, nil, true)

    local state_machine_2 = ct:define_state_machine("state_machine_2", sm_name_2,
        {"state1", "state2", "state3"}, "state3", true, "CFL_SM_EVENT_SYNC")

    local state1_2 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_event_logger("displaying state 1 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state2", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state1_2)

    local state2_2 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_event_logger("displaying state 2 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state3")
    ct:asm_halt()
    ct:end_column(state2_2)

    local state3_2 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_event_logger("displaying state 3 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state1", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state3_2)

    ct:end_state_machine(state_machine_2, "parallel_state_machine_2")
    ct:end_column(container_column_2)
    ct:asm_wait_time(20)
    ct:asm_log_message("sequential machine sm test is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    return launch_column
end


local function inner_state_parallel_machine(ct)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("parallel machine sm test is starting")
    ct:asm_log_message("launching state machine 1")


    local container_column_1 = ct:define_column("container_column_1", nil, nil, nil, nil, nil, true)

    local sm_name_1 = "state_machine_1"
    local state_machine_1 = ct:define_state_machine("state_machine_1", sm_name_1,
        {"state1", "state2", "state3"}, "state2", true)

    local state1_1 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:change_state(state_machine_1, "state2")
    ct:asm_halt()
    ct:end_column(state1_1)

    local state2_1 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:change_state(state_machine_1, "state3")
    ct:asm_halt()
    ct:end_column(state2_1)

    local state3_1 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:change_state(state_machine_1, "state1")
    ct:asm_halt()
    ct:end_column(state3_1)

    ct:end_state_machine(state_machine_1, "state_machine_1")
    ct:asm_wait_time(10)
    ct:asm_log_message("terminating state machine 1")
    ct:terminate_state_machine(state_machine_1)

    ct:end_column(container_column_1)
    ct:define_join_link(container_column_1)

    local sm_name_2 = "state_machine_2"

    local container_column_2 = ct:define_column("container_column_2", nil, nil, nil, nil, nil, true)

    local state_machine_2 = ct:define_state_machine("state_machine_2", sm_name_2,
        {"state1", "state2", "state3"}, "state3", true, "CFL_SM_EVENT_SYNC")

    local state1_2 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_event_logger("displaying state 1 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state2", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state1_2)

    local state2_2 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_event_logger("displaying state 2 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state3")
    ct:asm_halt()
    ct:end_column(state2_2)

    local state3_2 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_event_logger("displaying state 3 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state1", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state3_2)

    ct:end_state_machine(state_machine_2, "state_machine_2")
    ct:end_column(container_column_2)
    ct:asm_wait_time(20)
    ct:asm_log_message("parallel machine sm test is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    return launch_column
end


local function inner_nested_sm(ct)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("sequential machine sm test is starting")
    ct:asm_log_message("launching state machine 1")


    local sm_name_2 = "inner_nested_state_machine_2"

    local container_column_2 = ct:define_column("container_column_2", nil, nil, nil, nil, nil, true)

    local state_machine_2 = ct:define_state_machine("state_machine_2", sm_name_2,
        {"state1", "state2", "state3"}, "state3", true, "CFL_SM_EVENT_SYNC")

    local state1_2 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_event_logger("displaying state 1 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state2", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state1_2)

    local state2_2 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_event_logger("displaying state 2 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state3")
    ct:asm_halt()
    ct:end_column(state2_2)

    local state3_2 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_event_logger("displaying state 3 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(state_machine_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state1", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state3_2)

    ct:end_state_machine(state_machine_2, sm_name_2)

    ct:end_column(container_column_2)

    ct:end_column(launch_column)
    return launch_column, state_machine_2
end


local function nested_machine(ct)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("parallel machine sm test is starting")
    ct:asm_log_message("launching state machine 1")


    local container_column_1 = ct:define_column("container_column_1", nil, nil, nil, nil, nil, true)

    local sm_name_1 = "nested_state_machine_1"
    local state_machine_1 = ct:define_state_machine("state_machine_1", sm_name_1,
        {"state1", "state2", "state3"}, "state2", true)

    local state1_1 = ct:define_state("state1", nil)
    ct:asm_log_message("outer state1")
    ct:asm_log_message("nested state machine 1 is starting")
    local inner_launch_column, inner_nested_sm_node = inner_nested_sm(ct)
    ct:asm_wait_time(20)
    ct:asm_log_message("resetting inner nested state machine")
    ct:reset_state_machine(inner_nested_sm_node)
    ct:asm_log_message("changing state to state2")
    ct:change_state(state_machine_1, "state2")
    ct:asm_halt()
    ct:end_column(state1_1)

    local state2_1 = ct:define_state("state2", nil)
    ct:asm_log_message("outer state2")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:change_state(state_machine_1, "state3")
    ct:asm_halt()
    ct:end_column(state2_1)

    local state3_1 = ct:define_state("state3", nil)
    ct:asm_log_message("outer state3")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:change_state(state_machine_1, "state1")
    ct:asm_halt()
    ct:end_column(state3_1)

    ct:end_state_machine(state_machine_1, sm_name_1)
    ct:asm_wait_time(100)
    ct:asm_log_message("terminating state machine 1")
    ct:terminate_state_machine(state_machine_1)

    ct:end_column(container_column_1)
    ct:define_join_link(container_column_1)
    ct:end_column(launch_column)
    return launch_column
end


local function insert_sm_event_filtering(ct)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("sequential machine sm test is starting")
    ct:asm_log_message("launching state machine 1")


    local sm_name_2 = "sm_event_filtering_state_machine_2"

    local container_column_2 = ct:define_column("container_column_2", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launching event filtering state machine")
    ct:asm_node_element("SM_EVENT_FILTERING_MAIN", "SM_EVENT_FILTERING_INIT")
    local state_machine_2 = ct:define_state_machine("state_machine_2", sm_name_2,
        {"state1", "state2", "state3"}, "state3", true, "CFL_SM_EVENT_SYNC")

    local state1_2 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_event_logger("displaying state 1 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state2", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state1_2)

    local state2_2 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_event_logger("displaying state 2 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state3")
    ct:asm_halt()
    ct:end_column(state2_2)

    local state3_2 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_event_logger("displaying state 3 events", {"TEST_EVENT_1", "TEST_EVENT_2", "TEST_EVENT_3"})
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_1", {})
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_2", {})
    ct:asm_send_named_event(container_column_2, "TEST_EVENT_3", {})
    ct:change_state(state_machine_2, "state1", "SYNC_EVENT")
    ct:asm_halt()
    ct:end_column(state3_2)

    ct:end_state_machine(state_machine_2, sm_name_2)

    ct:end_column(container_column_2)
    ct:asm_wait_time(20)
    ct:asm_log_message("event filtering state machine is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    return launch_column, state_machine_2
end


local function ninteenth_test(ct, kb_name) -- state machine
    ct:start_test(kb_name)
    local define_container_column = ct:define_column("container_column", nil, nil, nil, nil, nil, true)
    local inner_sequential_column = inner_state_sequential_machine(ct)
    ct:define_join_link(inner_sequential_column)
    local inner_parallel_column = inner_state_parallel_machine(ct)
    ct:define_join_link(inner_parallel_column)
    local inner_nested_column = nested_machine(ct)
    ct:define_join_link(inner_nested_column)
    local event_filter_column = insert_sm_event_filtering(ct)
    ct:end_column(define_container_column)
    ct:end_test()
end

--[[
  test_bitmask_arena.lua - ChainTree bitmask, test control, and local arena tests (tests 20-22)
--]]

local function twentieth_test(ct, kb_name) -- bitmask wait/verify
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_clear_bitmask({"a", "b", "c", "d", "e", "f"})
    local bitmask_column = ct:define_column("bitmask_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("waiting for bitmask")
    ct:asm_wait_for_bitmask({"a", "b", "c"}, {"d", "e", "f"}, false, 10, "WHILE_BITMASK_FAILURE", "CF_SECOND_EVENT", {})
    ct:asm_log_message("bitmask received")
    ct:asm_verify_bitmask({"a", "b", "c"}, {"d", "e", "f"}, false, "VERIFY_BITMASK_FAILURE", {})
    ct:asm_log_message("bitmask verified")
    ct:asm_halt()
    ct:end_column(bitmask_column)
    ct:asm_log_message("setting bitmask")
    ct:asm_set_bitmask({"a", "b", "c"})
    ct:asm_log_message("bitmask set")
    ct:asm_wait_time(5)
    ct:asm_log_message("clearing bitmask")
    ct:asm_clear_bitmask({"a", "b", "c"})
    ct:define_join_link(bitmask_column)
    ct:asm_log_message("verify test has failed")
    ct:asm_terminate()
    ct:end_column(launch_column)
    ct:end_test()
end

local function twenty_first_test(ct, kb_name) -- test start/stop control
    ct:start_test(kb_name, 40)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column_started")
    ct:asm_wait_time(1)
    ct:asm_start_stop_tests({}, {3})
    ct:asm_log_message("test 0 started")
    ct:asm_wait_time(10)
    ct:asm_start_stop_tests({3}, {1})
    ct:asm_log_message("test 1 started")
    ct:asm_wait_for_tests_complete({1}, false, 30, "WAIT_FOR_TEST_COMPLETE_ERROR", "CF_SECOND_EVENT", {})
    ct:asm_log_message("test 1 completed")
    ct:asm_start_stop_tests({1}, {2})
    ct:asm_verify_tests_active({2}, false, "VERIFY_TESTS_ACTIVE_ERROR", {})
    ct:asm_halt()
    ct:end_column(launch_column)
    ct:end_test()
end

local function twenty_second_test(ct, kb_name) -- local arena + state machine
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column")
    ct:asm_log_message("launching state machine 1")
    ct:asm_log_message("launching local arena")
    local column_arena = ct:define_local_arena("column_arena", 500)
    local sm_name_1 = "state_machine_1"
    local state_machine_1 = ct:define_state_machine("state_machine_1", sm_name_1,
        {"state1", "state2", "state3"}, "state2", true)

    local state1_1 = ct:define_state("state1", nil)
    ct:asm_log_message("state1")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state2")
    ct:change_state(state_machine_1, "state2")
    ct:asm_halt()
    ct:end_column(state1_1)

    local state2_1 = ct:define_state("state2", nil)
    ct:asm_log_message("state2")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state3")
    ct:change_state(state_machine_1, "state3")
    ct:asm_halt()
    ct:end_column(state2_1)

    local state3_1 = ct:define_state("state3", nil)
    ct:asm_log_message("state3")
    ct:asm_wait_time(2)
    ct:asm_log_message("changing state to state1")
    ct:change_state(state_machine_1, "state1")
    ct:asm_halt()
    ct:end_column(state3_1)

    ct:end_state_machine(state_machine_1, "state_machine_1")

    ct:asm_log_message("waiting 10 seconds to terminate state machine 1")

    ct:end_column(column_arena)
    ct:asm_wait_time(10)
    ct:asm_log_message("launch column is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)

    ct:end_test()
end

-- =========================================================================
-- Streaming Tests (23-26) - translated from Python
-- =========================================================================

local function twenty_third_test(ct, kb_name)
    ct:start_test(kb_name)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column")

    local event_id = ct.ctb:register_event("GENERATE_AVRO_PACKET")
    local event_id_const = ct.ctb:register_event("GENERATE_CONST_AVRO_PACKET")
    local node_index = ct.ctb:get_node_index(launch_column)
    
    ct:asm_one_shot_handler("GENERATE_AVRO_PACKET", { event_id = event_id, node_index = node_index })
    ct:asm_node_element("AVRO_VERIFY_PACKET", "AVRO_VERIFY_PACKET_INIT", nil, nil, { event_id = event_id })
    ct:asm_one_shot_handler("GENERATE_CONST_AVRO_PACKET", { event_id = event_id_const, node_index = node_index })
    ct:asm_node_element("AVRO_VERIFY_CONST_PACKET", "AVRO_VERIFY_CONST_PACKET_INIT", nil, nil, { event_id = event_id_const })
    ct:asm_halt()
    ct:end_column(launch_column)
    ct:end_test()
end

-- Helper: packet generator column
local function insert_packet_generator(ct, port_0, event_column)
    local packet_generator_column = ct:define_column("packet_generator_column", nil, nil, nil, nil, nil, true)
    ct:asm_wait_time(0.2)
    ct:asm_log_message("sending packet")
    ct:asm_streaming_emit_packet("PACKET_GENERATOR", { device_id = 1 }, event_column, port_0)
    ct:asm_reset()
    ct:end_column(packet_generator_column)
    return packet_generator_column
end

-- Helper: packet sink column
local function insert_packet_sink(ct, port_0, port_1)
    local packet_sink_column = ct:define_column("packet_sink_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("receiving packet")
    ct:asm_streaming_sink_packet("PACKET_SINK_A",
        { sink_message = "raw packet received" },
        port_0)
    ct:asm_streaming_sink_packet("PACKET_SINK_B",
        { sink_message = "filtered packet received" },
        port_1)
    ct:asm_halt()
    ct:end_column(packet_sink_column)
    return packet_sink_column
end

local function twenty_fourth_test(ct, kb_name)
    local port_0 = ct:make_port("stream_test_1", "accelerometer_reading", 0, "PACKET_GENERATOR_EVENT_1")
    local port_1 = ct:make_port("stream_test_1", "accelerometer_reading_filtered", 1, "PACKET_GENERATOR_EVENT_2")

    ct:start_test(kb_name, 50)
    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column")
    ct:asm_log_message("launching streaming column")

    local packet_generator_column = insert_packet_generator(ct, port_0, launch_column)

    ct:asm_streaming_transform_packet("PACKET_TRANSFORM", { average = 5 },
        port_0, port_1, launch_column)

    ct:asm_streaming_tap_packet("PACKET_TAP",
        { log_message = "packet received" },
        port_0)

    ct:asm_streaming_filter_packet("PACKET_FILTER", { x = 0.5 }, port_0)

    local packet_sink_column = insert_packet_sink(ct, port_0, port_1)

    ct:asm_wait_time(100)
    ct:asm_log_message("launch column is terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    ct:end_test()
end

-- Helper: delayed packet generator
local function insert_packet_generator_delayed(ct, port, event_column, device_id, delay)
    local column_name = "packet_generator_" .. tostring(device_id) .. "_column"
    local generator_column = ct:define_column(column_name, nil, nil, nil, nil, nil, true)
    ct:asm_wait_time(delay)
    ct:asm_log_message("emitter " .. tostring(device_id) .. ": sending packet")
    ct:asm_streaming_emit_packet("PACKET_GENERATOR", { device_id = device_id },
        event_column, port)
    ct:asm_reset()
    ct:end_column(generator_column)
    return generator_column
end

-- Helper: collector sink column
local function insert_collector_sink(ct, event_name)
    local sink_column = ct:define_column("collector_sink_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("collector sink: ready")
    ct:asm_streaming_sink_collected_packets("PACKET_COLLECTOR_SINK",
        { sink_message = "collected packet received" },
        event_name)
    ct:asm_halt()
    ct:end_column(sink_column)
    return sink_column
end

local function twenty_fifth_test(ct, kb_name)
    local port_emitter_1 = ct:make_port("stream_test_1", "accelerometer_reading", 0, "EMITTER_1_EVENT")
    local port_emitter_2 = ct:make_port("stream_test_1", "accelerometer_reading", 0, "EMITTER_2_EVENT")
    local port_emitter_3 = ct:make_port("stream_test_1", "accelerometer_reading", 0, "EMITTER_3_EVENT")

    ct:start_test(kb_name, 50)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column: collector test starting")

    -- Create 3 packet generators, each with 1.0 second delay
    insert_packet_generator_delayed(ct, port_emitter_1, launch_column, 1, 1.0)
    insert_packet_generator_delayed(ct, port_emitter_2, launch_column, 2, 1.0)
    insert_packet_generator_delayed(ct, port_emitter_3, launch_column, 3, 1.0)
    ct:asm_log_message("packet generators created")

    -- Collector node - collects from all 3 emitters, outputs when all received
    ct:asm_streaming_collect_packets("PACKET_COLLECTOR",
        { expected_count = 3 },
        { port_emitter_1, port_emitter_2, port_emitter_3 },
        "COLLECTOR_OUTPUT_EVENT",
        launch_column)
    ct:asm_log_message("collector node created")

    -- Sink for collector output
    insert_collector_sink(ct, "COLLECTOR_OUTPUT_EVENT")

    ct:asm_wait_time(100)
    ct:asm_log_message("launch column: terminating")
    ct:asm_terminate()
    ct:end_column(launch_column)
    ct:end_test()
end
-- Helper: packet generator for verify test
local function insert_packet_generator_for_verify(ct, port, event_column, device_id, delay)
    local column_name = "packet_generator_" .. tostring(device_id) .. "_column"
    local generator_column = ct:define_column(column_name, nil, nil, nil, nil, nil, true)
    ct:asm_wait_time(delay)
    ct:asm_log_message("emitter " .. tostring(device_id) .. ": sending packet")
    ct:asm_streaming_emit_packet("PACKET_GENERATOR", { device_id = device_id },
        event_column, port)
    ct:asm_reset()
    ct:end_column(generator_column)
    return generator_column
end

-- Helper: verified sink column
local function insert_verified_sink(ct, inport)
    local sink_column = ct:define_column("verified_sink_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("verified sink: ready")
    ct:asm_streaming_sink_packet("PACKET_VERIFIED_SINK",
        { sink_message = "verified packet received" },
        inport)
    ct:asm_halt()
    ct:end_column(sink_column)
    return sink_column
end

local function twenty_sixth_test(ct, kb_name)
    
    --    Test demonstrating asm_streaming_verify_packet with reset_flag=true.
    --    Packets with x > 0.5 will fail verification and cause column reset.
    --    Packets with x <= 0.5 will pass and reach the sink.
    
    local port_0 = ct:make_port("stream_test_1", "accelerometer_reading", 0, "SENSOR_EVENT")

    ct:start_test(kb_name, 50)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column: verify packet test starting")
    local inner_column = ct:define_column("inner_column", nil, nil, nil, nil, nil, true)
    -- Create packet generator - emits every 0.5 seconds
    insert_packet_generator_for_verify(ct, port_0, launch_column, 1, 0.5)
    ct:asm_log_message("packet generator created")

    -- Verify packets - x must be in range [0.0, 0.5]
    -- If verification fails, column resets (reset_flag=true)
    
    ct:asm_streaming_verify_packet("PACKET_VERIFY_X_RANGE",
        { min_x = 0.0, max_x = 0.5 },
        port_0,
        true)  -- reset_flag
    
    ct:asm_log_message("verify packet created")

    -- Tap to see packets that passed verification
    ct:asm_streaming_tap_packet("PACKET_TAP",
        { log_message = "packet passed verification" },
        port_0)

    -- Sink for verified packets
    insert_verified_sink(ct, port_0)
    ct:end_column(inner_column)
    ct:asm_wait_time(30)
    ct:asm_log_message("launch column: terminating")
    ct:asm_terminate_system()
    ct:end_column(launch_column)
    ct:end_test()
end

--[[
    Tests 27 and 28 - Drone control using controlled nodes (client/server pattern).

    Test 27: Basic drone control - four flight mode servers with a client
             sequencing through fly_straight, fly_arc, fly_up, fly_down.

    Test 28: Same as 27 but fly_straight server raises an exception,
             and the client uses catch_all_exception to handle it.

    Translated from Python to LuaJIT.
]]



-- =========================================================================
-- Shared column helpers
-- =========================================================================

local function insert_fly_up_column(ct)
    local fly_up_column = ct.drone_control:fly_up_server("fly_up", "fly_up_monitor", {})
    ct:asm_log_message("fly up column: ready")
    ct:asm_wait_time(2)
    ct:asm_one_shot_handler("UPDATE_FLY_UP_FINAL", { final_data = {} })
    ct:asm_log_message("fly up column: terminating")
    ct:asm_terminate()
    ct:end_column(fly_up_column)
    return fly_up_column
end

local function insert_fly_down_column(ct)
    local fly_down_column = ct.drone_control:fly_down_server("fly_down", "fly_down_monitor", {})
    ct:asm_log_message("fly down column: ready")
    ct:asm_wait_time(2)
    ct:asm_one_shot_handler("UPDATE_FLY_DOWN_FINAL", { final_data = {} })
    ct:asm_log_message("fly down column: terminating")
    ct:asm_terminate()
    ct:end_column(fly_down_column)
    return fly_down_column
end

local function insert_fly_arc_column(ct)
    local fly_arc_column = ct.drone_control:fly_arc_server("fly_arc", "fly_arc_monitor", {})
    ct:asm_log_message("fly arc column: ready")
    ct:asm_wait_time(2)
    ct:asm_one_shot_handler("UPDATE_FLY_ARC_FINAL", { final_data = {} })
    ct:asm_log_message("fly arc column: terminating")
    ct:asm_terminate()
    ct:end_column(fly_arc_column)
    return fly_arc_column
end

local function insert_fly_straight_column(ct)
    local fly_straight_column = ct.drone_control:fly_straight_server("fly_straight", "fly_straight_monitor", {})
    ct:asm_log_message("fly straight column: ready")
    ct:asm_wait_time(2)
    ct:asm_one_shot_handler("UPDATE_FLY_STRAIGHT_FINAL", {})
    ct:asm_log_message("fly straight column: terminating")
    ct:asm_terminate()
    ct:end_column(fly_straight_column)
    return fly_straight_column
end

-- =========================================================================
-- Test 28 variant: fly_straight server that raises an exception
-- =========================================================================

local function insert_fly_exception_straight_column(ct)
    local fly_straight_column = ct.drone_control:fly_straight_server("fly_straight", "fly_straight_monitor", {})
    ct:asm_log_message("fly straight column: ready")
    ct:asm_wait_time(2)
    ct:asm_raise_exception(1, { ["low battery"] = 12.0 })
    ct:asm_one_shot_handler("UPDATE_FLY_STRAIGHT_FINAL", {})
    ct:asm_log_message("fly straight column: terminating")
    ct:asm_terminate()
    ct:end_column(fly_straight_column)
    return fly_straight_column
end

-- =========================================================================
-- Client control columns
-- =========================================================================

local function insert_client_control_column(ct)
    local client_column = ct:define_column("client_control", nil, nil, nil, nil, nil, true)

    -- Fly straight: 100m at 50m altitude, 10m/s, heading 90 degrees
    ct.drone_control:fly_straight_client(
        100.0, 50.0, 10.0, 90.0,
        "ON_FLY_STRAIGHT_COMPLETE",
        { waypoint = "wp1" }
    )

    ct:asm_log_message("fly straight command sent")
    ct:asm_wait_time(2)

    -- Fly arc: 50m at 60m altitude, 8m/s, heading 180 degrees
    ct.drone_control:fly_arc_client(
        50.0, 60.0, 8.0, 180.0,
        "ON_FLY_ARC_COMPLETE",
        { waypoint = "wp2" }
    )

    ct:asm_log_message("fly arc command sent")
    ct:asm_wait_time(2)

    -- Fly up: climb to 100m at 5m/s
    ct.drone_control:fly_up_client(
        100.0, 5.0,
        "ON_FLY_UP_COMPLETE",
        { target = "cruise_altitude" }
    )

    ct:asm_log_message("fly up command sent")
    ct:asm_wait_time(2)

    -- Fly down: descend to 20m at 3m/s
    ct.drone_control:fly_down_client(
        20.0, 3.0,
        "ON_FLY_DOWN_COMPLETE",
        { target = "landing_approach" }
    )

    ct:asm_log_message("fly down command sent")
    ct:asm_log_message("client control column: complete")
    ct:asm_terminate()
    ct:end_column(client_column)
    return client_column
end

local function insert_exception_client_control_column(ct)
    local client_column = ct:catch_all_exception(
        "client_control",
        "DRONE_CONTROL_EXCEPTION_CATCH",
        { aux_data = {} }
    )

    -- Fly straight: 100m at 50m altitude, 10m/s, heading 90 degrees
    ct.drone_control:fly_straight_client(
        100.0, 50.0, 10.0, 90.0,
        "ON_FLY_STRAIGHT_COMPLETE",
        { waypoint = "wp1" }
    )

    ct:asm_log_message("fly straight command sent")
    ct:asm_wait_time(2)

    -- Fly arc: 50m at 60m altitude, 8m/s, heading 180 degrees
    ct.drone_control:fly_arc_client(
        50.0, 60.0, 8.0, 180.0,
        "ON_FLY_ARC_COMPLETE",
        { waypoint = "wp2" }
    )

    ct:asm_log_message("fly arc command sent")
    ct:asm_wait_time(2)

    -- Fly up: climb to 100m at 5m/s
    ct.drone_control:fly_up_client(
        100.0, 5.0,
        "ON_FLY_UP_COMPLETE",
        { target = "cruise_altitude" }
    )

    ct:asm_log_message("fly up command sent")
    ct:asm_wait_time(2)

    -- Fly down: descend to 20m at 3m/s
    ct.drone_control:fly_down_client(
        20.0, 3.0,
        "ON_FLY_DOWN_COMPLETE",
        { target = "landing_approach" }
    )

    ct:asm_log_message("fly down command sent")
    ct:asm_log_message("client control column: complete")
    ct:asm_terminate()
    ct:end_column(client_column)
    return client_column
end
--[[
    DroneControl - DSL extension for drone flight control server/client nodes.

    Wraps the ControlledNodes API with typed ports for each flight mode:
      - fly_straight: request handler 0, response handler 1
      - fly_arc:      request handler 2, response handler 3
      - fly_up:       request handler 4, response handler 5
      - fly_down:     request handler 6, response handler 7

    Each mode has a server (controlled node) and client (initiator) pair.
    Ports are built once in the constructor and reused across calls.

    In Python, DroneControl inherits from ControlledNodes and calls
    self.make_port / self.controlled_node / self.client_controlled_node directly.
    In LuaJIT, those methods live on ct via the mixin system, so we delegate.

    Translated from Python to LuaJIT.
]]

local DroneControl = {}
DroneControl.__index = DroneControl

-- FIXED: was `local function DroneControl.new` — invalid syntax
function DroneControl.new(ct, h_file)
    local self = setmetatable({}, DroneControl)
    self.ct = ct
    self.h_file = h_file

    -- Strip .h extension: make_control_port appends ".h:" internally
    local base = h_file:gsub("%.h$", "")

    self.command_container = {}

    self.command_container["fly_straight"] = {
        request_port  = ct:make_control_port(base, "fly_straight_request",  0, "fly_straight_request"),
        response_port = ct:make_control_port(base, "fly_straight_response", 1, "fly_straight_response"),
        api_name      = "drone_control_fly_straight",
    }
    self.command_container["fly_arc"] = {
        request_port  = ct:make_control_port(base, "fly_arc_request",  2, "fly_arc_request"),
        response_port = ct:make_control_port(base, "fly_arc_response", 3, "fly_arc_response"),
        api_name      = "drone_control_fly_arc",
    }
    self.command_container["fly_up"] = {
        request_port  = ct:make_control_port(base, "fly_up_request",  4, "fly_up_request"),
        response_port = ct:make_control_port(base, "fly_up_response", 5, "fly_up_response"),
        api_name      = "drone_control_fly_up",
    }
    self.command_container["fly_down"] = {
        request_port  = ct:make_control_port(base, "fly_down_request",  6, "fly_down_request"),
        response_port = ct:make_control_port(base, "fly_down_response", 7, "fly_down_response"),
        api_name      = "drone_control_fly_down",
    }

    return self
end
-- =========================================================================
-- Servers (controlled nodes)
-- =========================================================================

-- FIXED: was `local function DroneControl:...` on all methods below
function DroneControl:fly_straight_server(column_name, monitor_fn, monitor_data)
    monitor_data = monitor_data or {}
    local c = self.command_container["fly_straight"]
    return self.ct:controlled_node(c.api_name, column_name, monitor_fn, monitor_data,
                                    c.request_port, c.response_port)
end

function DroneControl:fly_arc_server(column_name, monitor_fn, monitor_data)
    monitor_data = monitor_data or {}
    local c = self.command_container["fly_arc"]
    return self.ct:controlled_node(c.api_name, column_name, monitor_fn, monitor_data,
                                    c.request_port, c.response_port)
end

function DroneControl:fly_up_server(column_name, monitor_fn, monitor_data)
    monitor_data = monitor_data or {}
    local c = self.command_container["fly_up"]
    return self.ct:controlled_node(c.api_name, column_name, monitor_fn, monitor_data,
                                    c.request_port, c.response_port)
end

function DroneControl:fly_down_server(column_name, monitor_fn, monitor_data)
    monitor_data = monitor_data or {}
    local c = self.command_container["fly_down"]
    return self.ct:controlled_node(c.api_name, column_name, monitor_fn, monitor_data,
                                    c.request_port, c.response_port)
end

-- =========================================================================
-- Clients (initiator nodes)
-- =========================================================================

function DroneControl:fly_straight_client(distance, final_altitude, final_speed, heading,
                                           finalize_fn, finalize_data)
    finalize_data = finalize_data or {}
    local c = self.command_container["fly_straight"]
    local monitor_data = {
        distance       = distance,
        final_altitude = final_altitude,
        final_speed    = final_speed,
        heading        = heading,
        finalize_data  = finalize_data,
    }
    return self.ct:client_controlled_node(c.api_name, finalize_fn, monitor_data,
                                           c.request_port, c.response_port)
end

function DroneControl:fly_arc_client(distance, final_altitude, final_speed, heading,
                                      finalize_fn, finalize_data)
    finalize_data = finalize_data or {}
    local c = self.command_container["fly_arc"]
    local monitor_data = {
        distance       = distance,
        final_altitude = final_altitude,
        final_speed    = final_speed,
        heading        = heading,
        finalize_data  = finalize_data,
    }
    return self.ct:client_controlled_node(c.api_name, finalize_fn, monitor_data,
                                           c.request_port, c.response_port)
end

function DroneControl:fly_up_client(final_altitude, final_speed, finalize_fn, finalize_data)
    finalize_data = finalize_data or {}
    local c = self.command_container["fly_up"]
    local monitor_data = {
        final_altitude = final_altitude,
        final_speed    = final_speed,
        finalize_data  = finalize_data,
    }
    return self.ct:client_controlled_node(c.api_name, finalize_fn, monitor_data,
                                           c.request_port, c.response_port)
end

function DroneControl:fly_down_client(final_altitude, final_speed, finalize_fn, finalize_data)
    finalize_data = finalize_data or {}
    local c = self.command_container["fly_down"]
    local monitor_data = {
        final_altitude = final_altitude,
        final_speed    = final_speed,
        finalize_data  = finalize_data,
    }
    return self.ct:client_controlled_node(c.api_name, finalize_fn, monitor_data,
                                           c.request_port, c.response_port)
end

-- =========================================================================
-- Test 27
-- =========================================================================

local function twenty_seventh_test(ct, kb_name)
    ct.drone_control = DroneControl.new(ct, "drone_control")

    ct:start_test(kb_name, 50)

    local controlled_node_container = ct:controlled_node_container("controlled_node_container")
    insert_fly_straight_column(ct)
    insert_fly_arc_column(ct)
    insert_fly_up_column(ct)
    insert_fly_down_column(ct)
    ct:end_column(controlled_node_container)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column: starting client control")
    local client_control_column = insert_client_control_column(ct)
    ct:define_join_link(client_control_column)

    ct:asm_log_message("launch column: complete")
    ct:asm_terminate_system()
    ct:end_column(launch_column)

    ct:end_test()
end

-- =========================================================================
-- Test 28
-- =========================================================================

local function twenty_eighth_test(ct, kb_name)
    ct.drone_control = DroneControl.new(ct, "drone_control")

    ct:start_test(kb_name, 50)

    local controlled_node_container = ct:controlled_node_container("controlled_node_container")
    insert_fly_exception_straight_column(ct)
    insert_fly_arc_column(ct)
    insert_fly_up_column(ct)
    insert_fly_down_column(ct)
    ct:end_column(controlled_node_container)

    local launch_column = ct:define_column("launch_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("launch column: starting client control")
    local client_control_column = insert_exception_client_control_column(ct)
    ct:define_join_link(client_control_column)

    ct:asm_log_message("launch column: complete")
    ct:asm_terminate_system()
    ct:end_column(launch_column)

    ct:end_test()
end
-- =========================================================================
-- Test 29: Blackboard verification
--   Calls one-shot functions that verify:
--     - Mutable blackboard fields (int32, float, uint16, nested struct)
--     - Constant record lookup and field access
--     - 64-bit pointer storage in blackboard
-- =========================================================================

local function twenty_ninth_test(ct, kb_name)
    -- Define the shared mutable blackboard
    ct:define_blackboard("system_state")
        ct:bb_field("mode",          "int32",  0)
        ct:bb_field("temperature",   "float",  20.0)
        ct:bb_field("error_count",   "uint16", 0)
        ct:bb_field("nav.heading",   "int32",  0)
        ct:bb_field("nav.altitude",  "float",  0.0)
        ct:bb_field("nav.speed",     "float",  0.0)
        ct:bb_field("debug_ptr",     "uint64", 0)
    ct:end_blackboard()

    -- Define a read-only calibration constant record
    ct:define_const_record("calibration")
        ct:const_field("gain",      "float",  1.5)
        ct:const_field("offset",    "float",  -0.25)
        ct:const_field("max_value", "int32",  1000)
        ct:const_field("scale_x",   "float",  2.0)
        ct:const_field("scale_y",   "float",  3.0)
    ct:end_const_record()

    ct:start_test(kb_name)

    local bb_test_column = ct:define_column("bb_test_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("blackboard test: initializing fields")
    ct:asm_one_shot_handler("BB_INIT_FIELDS", {})
    ct:asm_log_message("blackboard test: verifying int32 and float fields")
    ct:asm_one_shot_handler("BB_VERIFY_BASIC_FIELDS", {})
    ct:asm_log_message("blackboard test: verifying nested struct fields")
    ct:asm_one_shot_handler("BB_VERIFY_NESTED_FIELDS", {})
    ct:asm_log_message("blackboard test: verifying constant record")
    ct:asm_one_shot_handler("BB_VERIFY_CONST_RECORD", {})
    ct:asm_log_message("blackboard test: verifying 64-bit pointer field")
    ct:asm_one_shot_handler("BB_VERIFY_PTR64_FIELD", {})
    ct:asm_log_message("blackboard test: all verifications passed")
    ct:asm_terminate_system()
    ct:end_column(bb_test_column)

    ct:end_test()
end

-- =========================================================================
-- Header / entry point
-- =========================================================================

local function add_header(yaml_file)
    return ChainTreeMaster.new(yaml_file)
end

-- =========================================================================
-- Main
-- =========================================================================

local test_list = {
    "first_test",
    "second_test",
    "fourth_test",
    "fifth_test",
    "sixth_test",
    "seventh_test",
    "eighth_test",
    "ninth_test",
    "tenth_test",
    "eleventh_test",
    "twelfth_test",
    "thirteenth_test",
    "fourteenth_test",
    "seventeenth_test",
    "eighteenth_test",
    "ninteenth_test",
    "twentieth_test",
    "twenty_first_test",
    "twenty_second_test",
    "twenty_third_test",
    "twenty_fourth_test",
    "twenty_fifth_test",
    "twenty_sixth_test",
    "twenty_seventh_test",
    "twenty_eighth_test",
    "twenty_ninth_test",
    -- "thirty_test",
    -- "thirty_one_test",
    -- "thirty_two_test",
}

local test_dict = {
    first_test = first_test,
    second_test = second_test,
    fourth_test = fourth_test,
    fifth_test = fifth_test,
    sixth_test = sixth_test,
    seventh_test = seventh_test,
    eighth_test = eighth_test,
    ninth_test = ninth_test,
    tenth_test = tenth_test,
    eleventh_test = eleventh_test,
    twelfth_test = twelfth_test,
    thirteenth_test = thirteenth_test,
    fourteenth_test = fourteenth_test,
    seventeenth_test = seventeenth_test,
    eighteenth_test = eighteenth_test,
    ninteenth_test = ninteenth_test,
    twentieth_test = twentieth_test,
    twenty_first_test = twenty_first_test,
    twenty_second_test = twenty_second_test,
    twenty_third_test = twenty_third_test,
    twenty_fourth_test = twenty_fourth_test,
    twenty_fifth_test = twenty_fifth_test,
    twenty_sixth_test = twenty_sixth_test,
    twenty_seventh_test = twenty_seventh_test,
    twenty_eighth_test = twenty_eighth_test,
    twenty_ninth_test = twenty_ninth_test,
    -- thirty_test = thirty_test,
    -- thirty_one_test = thirty_one_test,
    -- thirty_two_test = thirty_two_test,
}

-- Main execution
if arg then
    if #arg ~= 1 then
        print("Usage: luajit chain_tree_incremental_build.lua <yaml_file>")
        os.exit(1)
    end

    local yaml_file = arg[1]
    print(yaml_file)

    local single_test = "first_test"
    local single_test_flag = false

    if single_test_flag then
        local ct = add_header(yaml_file)
        test_dict[single_test](ct, single_test)
        ct:check_and_generate_yaml()
        ct:generate_debug_yaml()
        ct:display_chain_tree_function_mapping()
        os.exit(0)
    end
    print("Adding tests")
    local ct = add_header(yaml_file)
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