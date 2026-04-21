from calendar import c
from chain_tree_build.yaml_generator.data_structures import DataStructures
from chain_tree_build.ct_build.chain_tree_master import ChainTreeMaster
from s_functions.lisp_sequencer import LispSequencer

from pathlib import Path

def first_test(ct,kb_name):
    
    ct.start_test(test_name=kb_name)
    
    activate_valve_column = ct.define_column(column_name="activate_valve", column_data=None,auto_start=True)
    ct.asm_one_shot_handler(one_shot_fn="ACTIVATE_VALVE",one_shot_data={"state":"open"})
    ct.asm_log_message("Valve activated")
    ct.asm_terminate()
    ct.end_column(column_name=activate_valve_column)
    
    terminate_engine_column = ct.define_column(column_name="terminate_engine", column_data=None, auto_start=True)
    ct.asm_log_message("waiting time 12 seconds to terminate engine")
    ct.asm_wait_time(time_delay=12)
    ct.asm_log_message("terminating engine")
    ct.asm_terminate_system()
    ct.end_column(column_name=terminate_engine_column)
    
    wait_for_event_column = ct.define_column(column_name="wait_for_event", column_data=None, auto_start=True)
    ct.asm_log_message("waiting for event")
    wait_for_event_node = ct.asm_wait_for_event(event_id="WAIT_FOR_EVENT",event_count = 1,reset_flag = True,timeout= 5,
                           error_fn = "WAIT_FOR_EVENT_ERROR",time_out_event ="CFL_SECOND_EVENT",error_data = {"error_message":"WAIT_FOR_EVENT_ERROR"})
    ct.asm_log_message("event received")
    ct.asm_reset()
    ct.end_column(column_name=wait_for_event_column)

    
    reset_node_column = ct.define_column(column_name="reset_node", column_data=None, auto_start=True)
    ct.asm_log_message("waiting 2 seconds to reset node")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("sending system event")
    #ct.asm_send_system_event("WAIT_FOR_EVENT",event_data={})
    #sending an event to a column link or leaf node

    ct.asm_send_named_event(node_id=wait_for_event_column,event_id="WAIT_FOR_EVENT",event_data={})
    ct.asm_log_message("resetting node")
    ct.asm_reset()
    ct.end_column(column_name=reset_node_column)

    verify_column = ct.define_column(column_name="verify", column_data=None, auto_start=True)
    ct.asm_log_message("verifying")
    ct.asm_verify(verify_fn="CFL_BOOL_FALSE",fn_data={},reset_flag=False,
                  error_fn="VERIFY_ERROR",error_data={"failure_data":"failure_data"})
    ct.asm_log_message("waiting for verify to fail")
    ct.asm_halt()
    ct.end_column(column_name=verify_column)
    
    verify_timeout_column = ct.define_column(column_name="verify_timeout", column_data=None, auto_start=True)
    ct.asm_log_message("verifying timeout")
    ct.asm_verify_timeout(time_out=5,reset_flag=False,error_fn="VERIFY_ERROR",error_data={"failure_data":"failure_data"})
    ct.asm_log_message("waiting for verify timeout to fail which will result in a terminate column")
    ct.asm_halt()
    ct.end_column(column_name=verify_timeout_column)

    ct.end_test()
 
def second_test(ct,kb_name):
    ct.start_test(test_name=kb_name)
    
    activate_valve_column = ct.define_column(column_name="activate_valve", column_data=None,auto_start=True)
    ct.asm_one_shot_handler(one_shot_fn="ACTIVATE_VALVE",one_shot_data={"state":"open"})
    ct.asm_log_message("Valve activated")
    ct.asm_terminate()
    ct.end_column(column_name=activate_valve_column)
    
    terminate_engine_column = ct.define_column(column_name="terminate_engine", column_data=None, auto_start=True)
    ct.asm_log_message("waiting time 20 seconds to terminate engine")
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("terminating engine")
    ct.asm_terminate_system()
    ct.end_column(column_name=terminate_engine_column)
    
    wait_for_event_column = ct.define_column(column_name="wait_for_event", column_data=None, auto_start=True)
    ct.asm_log_message("waiting for event")
    wait_for_event_node = ct.asm_wait_for_event(event_id="WAIT_FOR_EVENT",event_count = 1,reset_flag = True,timeout= 5,
                           error_fn = "WAIT_FOR_EVENT_ERROR",time_out_event ="CFL_SECOND_EVENT",error_data = {"error_message":"WAIT_FOR_EVENT_ERROR"})
    ct.asm_log_message("event received")
    ct.asm_reset()
    ct.end_column(column_name=wait_for_event_column)

    
    reset_node_column = ct.define_column(column_name="reset_node", column_data=None, auto_start=True)
    ct.asm_log_message("waiting 2 seconds to reset node")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("sending system event")
    #ct.asm_send_system_event("WAIT_FOR_EVENT",event_data={})
    #sending an event to a column link or leaf node

    ct.asm_send_named_event(node_id=wait_for_event_node,event_id="WAIT_FOR_EVENT",event_data={})
    ct.asm_log_message("resetting node")
    ct.asm_reset()
    ct.end_column(column_name=reset_node_column)

    enable_column = ct.define_column(column_name="start_column", column_data=None, auto_start=True)
    ct.asm_log_message("waiting 2 seconds to start rest of columns")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("starting rest of columns")
    ct.asm_enable_nodes([activate_valve_column,terminate_engine_column,wait_for_event_column,reset_node_column])
    ct.asm_log_message("waiting 8 seconds to disable column")
    ct.asm_wait_time(time_delay=8)
    ct.asm_disable_nodes([terminate_engine_column])
    ct.asm_log_message("waiting 20 seconds to end test")
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("ending test")
    ct.asm_terminate_system()
    ct.end_column(column_name=enable_column)
    
    ct.end_test()
    

def third_test(ct,kb_name):
    ct.start_test(test_name=kb_name)
    

    top_column = ct.define_column(column_name="top_column", column_data=None,auto_start=True)
    fork_column = ct.define_column(column_name="fork_column",auto_start=True)
    
    subscribe_event = ct.define_column(column_name="subscribe_event", column_data=None,auto_start=True)
    ct.asm_event_logger("displaying subscribed events",["PUBLISH_EVENT"])
    ct.asm_log_message("waiting 5 seconds")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("subscribing to event")
    ct.asm_subscribe_events(node_id=fork_column,events=["PUBLISH_EVENT"])
    ct.asm_subscribe_events(node_id=subscribe_event,events=["PUBLISH_EVENT"])
    ct.asm_log_message("waiting 5 seconds")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("unsubscribing from event")
    ct.asm_unsubscribe_events(node_id=fork_column,events=["PUBLISH_EVENT"])
    
    ct.asm_log_message("waiting 5 seconds")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("ending test")
    ct.asm_terminate()
    ct.end_column(column_name=subscribe_event)
    
    publish_event = ct.define_column(column_name="publish_event", column_data=None,auto_start=True)
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("publishing event")
    ct.asm_publish_event(event_id="PUBLISH_EVENT",event_data={"event_data":"event_data"})
    ct.asm_reset()
    ct.end_column(column_name=publish_event)
    
    
    ct.end_column(column_name=fork_column)
    time_out_column = ct.define_column(column_name="time_out_column", column_data=None,auto_start=True)
    ct.asm_log_message("system time out column")
    ct.asm_wait_time(time_delay=20)
    ct.asm_terminate_system()
    ct.end_column(column_name=time_out_column)
    ct.end_column(column_name=top_column)
    
    ct.end_test()
    
def fourth_test(ct,kb_name):
    ct.start_test(test_name=kb_name)
    
    top_column = ct.define_column(column_name="top_column", column_data=None,auto_start=True)
    ct.asm_log_message("top column")
    
    middle_column = ct.define_column(column_name="middle_column", column_data=None,auto_start=True)
    ct.asm_log_message("middle column")
    ct.asm_event_logger("displaying middle column events",["PUBLISH_EVENT"])
    #ct.asm_wait_time(time_delay=1)
    #ct.asm_log_message("terminating middle column")
    #ct.asm_terminate()
    ct.asm_halt()
    ct.end_column(column_name=middle_column)
    
    
    
    ct.asm_send_named_event(node_id=top_column,event_id="PUBLISH_EVENT",event_data={"event_data":"event_data"})
    ct.asm_log_message("waiting 2 seconds")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("resetting top column")
    ct.asm_reset()
    ct.end_column(column_name=top_column)
    
    
    time_out_column = ct.define_column(column_name="time_out_column", column_data=None,auto_start=True)
    ct.asm_wait_time(time_delay=20)
    ct.asm_terminate_system()
    ct.end_column(column_name=time_out_column)
    
    
    
    ct.end_test()
    
    
def fifth_test(ct,kb_name): # state machine
    ct.start_test(test_name=kb_name)
    launch_column = ct.define_column(column_name="launch_column", column_data=None,auto_start=True)
    ct.asm_log_message("launch column")
    ct.asm_log_message("launching state machine 1")
    sm_name_1 = "state_machine_1"
    state_machine_1 = ct.define_state_machine(column_name="state_machine_1",sm_name=sm_name_1,state_names=["state1","state2","state3"],
                                            initial_state="state1",auto_start=True)
    
    state1_1 = ct.define_state(state_name="state1",column_data=None)
    ct.asm_log_message("state1")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to state2")
    ct.change_state(sm_node_id=state_machine_1,new_state="state2")
    ct.asm_halt()
    ct.end_column(column_name=state1_1)
    
    state2_1 = ct.define_state(state_name="state2",column_data=None)
    ct.asm_log_message("state2")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to state3")
    ct.change_state(state_machine_1,new_state="state3")
    ct.asm_halt()
    ct.end_column(column_name=state2_1)

    state3_1 = ct.define_state(state_name="state3",column_data=None)
    ct.asm_log_message("state3")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to state1")
    ct.change_state(state_machine_1,new_state="state1")
    ct.asm_halt()
    ct.end_column(column_name = state3_1)
    
    ct.end_state_machine(state_node=state_machine_1,sm_name="state_machine_1")
    ct.asm_wait_time(time_delay=10)
    ct.asm_log_message("terminating state machine 1")
    ct.terminate_state_machine(state_machine_1)
    sm_name_2 = "state_machine_2"
    state_machine_2 = ct.define_state_machine(column_name="state_machine_2",sm_name=sm_name_2,state_names=["state1","state2","state3"],
                                            initial_state="state1",auto_start=True,aux_function_name="CFL_SM_EVENT_SYNC")
    
    state1_2 = ct.define_state(state_name="state1",column_data=None)
    ct.asm_log_message("state1")
    ct.asm_event_logger("displaying state 1 events",["TEST_EVENT_1","TEST_EVENT_2","TEST_EVENT_3"])
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to state2")
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_1",event_data={})
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_2",event_data={})
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_3",event_data={})
    ct.change_state(sm_node_id=state_machine_2,new_state="state2",sync_event_id="SYNC_EVENT")
    ct.asm_halt()
    ct.end_column(column_name=state1_2)
    
    state2_2 = ct.define_state(state_name="state2",column_data=None)
    ct.asm_log_message("state2")
    ct.asm_event_logger("displaying state 2 events",["TEST_EVENT_1","TEST_EVENT_2","TEST_EVENT_3"])
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to state3")
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_1",event_data={})
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_2",event_data={})
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_3",event_data={})
    ct.change_state(state_machine_2,new_state="state3")
    ct.asm_halt()
    ct.end_column(column_name=state2_2)

    state3_2 = ct.define_state(state_name="state3",column_data=None)
    ct.asm_log_message("state3")
    ct.asm_event_logger("displaying state 3 events",["TEST_EVENT_1","TEST_EVENT_2","TEST_EVENT_3"])
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to state1")
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_1",event_data={})
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_2",event_data={})
    ct.asm_send_named_event(node_id=state_machine_2,event_id="TEST_EVENT_3",event_data={})
    ct.change_state(state_machine_2,new_state="state1",sync_event_id="SYNC_EVENT")
    ct.asm_halt()
    ct.end_column(column_name = state3_2)
    
    ct.end_state_machine(state_node=state_machine_2,sm_name="state_machine_2")
    ct.asm_log_message("terminating state machine 2")
    ct.asm_wait_time(time_delay=20)
    ct.terminate_state_machine(state_machine_2)
    
    ct.asm_log_message("launch column is terminating")
    
    ct.end_column(column_name=launch_column)
    
    ct.end_test()
    

    
def insert_fork_column(ct):
    
    fork_column = ct.define_fork_column(column_name="fork_column")
    fork_child_1 = ct.define_column("fork_child_1")
    ct.asm_log_message("fork child 1 starting")
    ct.asm_event_logger("displaying fork child 1 events",["TEST_EVENT"])
    ct.asm_halt()
    ct.end_column(column_name=fork_child_1)
    
    
    fork_child_2 = ct.define_column("fork_child_2")
    ct.asm_log_message("fork child 2 starting")
    ct.asm_event_logger("displaying fork child 2 events",["TEST_EVENT"])
    ct.asm_halt()
    ct.end_column(column_name=fork_child_2)
    
    fork_child_3 = ct.define_column("fork_child_3")
    ct.asm_log_message("fork child 3 starting")
    ct.asm_event_logger("displaying fork child 3 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("child 3 executed a time delay of 2 seconds")
    ct.asm_wait_time(time_delay=15)
    ct.asm_halt()
    ct.end_column(column_name=fork_child_3)
    ct.end_column(column_name=fork_column)
    
    
    
    
    
def sixth_test(ct,kb_name):

    ct.start_test(test_name=kb_name)
    
    
    
    launch_column = ct.define_column(column_name="launch_column", column_data=None,auto_start=True)
    ct.asm_log_message("launch column")

    ct.asm_wait_time(time_delay=1.5)
    ct.asm_log_message("launching fork column")
   
    insert_fork_column(ct)

    ct.asm_log_message("fork column launched")
    ct.asm_event_logger("displaying fork column events",["TEST_EVENT"])

    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("resetting launch column")
    ct.asm_reset()
    ct.end_column(column_name=launch_column)
    
    
    
    
    event_generator_column = ct.define_column(column_name="event_generator_column", column_data=None,auto_start=True)
    ct.asm_log_message("sending event to launch column")
    ct.asm_send_named_event(node_id=launch_column,event_id="TEST_EVENT",event_data={"event_data":"event_data"})
    ct.asm_wait_time(time_delay=1)
    ct.asm_reset()
    ct.end_column(column_name=event_generator_column)
    
    end_column =ct.define_column(column_name="end_column", column_data=None,auto_start=True)
    
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("ending test")
    ct.asm_terminate_system()
    ct.end_column(column_name=end_column)
    
    ct.end_test()
    
def insert_fork_join_column(ct):
    fork_join_column = ct.define_fork_column(column_name="fork_column")
    fork_child_1 = ct.define_column("fork_child_1")
    ct.asm_log_message("fork child 1 starting")
    ct.asm_event_logger("displaying fork child 1 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("fork 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_1)
    
    
    fork_child_2 = ct.define_column("fork_child_2")
    ct.asm_log_message("fork child 2 starting")
    ct.asm_event_logger("displaying fork child 2 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("fork 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_2)
    
    fork_child_3 = ct.define_column("fork_child_3")
    ct.asm_log_message("fork child 3 starting")
    ct.asm_event_logger("displaying fork child 3 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("fork 3 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_3)
    
    ct.end_column(column_name=fork_join_column)
    ct.define_join_link(parent_node_name=fork_join_column)
    
    
def seventh_test(ct,kb_name): # fork column
    ct.start_test(test_name=kb_name)
    
    
    
    launch_column = ct.define_column(column_name="launch_column", column_data=None,auto_start=True)
    ct.asm_log_message("launch column")

    ct.asm_wait_time(time_delay=1.5)
    ct.asm_log_message("launching fork column")
   
    insert_fork_join_column(ct)
    ct.asm_log_message("fork column joined")
    ct.asm_event_logger("displaying fork column events",["TEST_EVENT"])
   
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("resetting launch column")
    ct.asm_reset()
    ct.end_column(column_name=launch_column)
    
    
    
    
    event_generator_column = ct.define_column(column_name="event_generator_column", column_data=None,auto_start=True)
    ct.asm_log_message("sending event to launch column")
    ct.asm_send_named_event(node_id=launch_column,event_id="TEST_EVENT",event_data={"event_data":"event_data"})
    ct.asm_wait_time(time_delay=1)
    ct.asm_reset()
    ct.end_column(column_name=event_generator_column)
    
    end_column =ct.define_column(column_name="end_column", column_data=None,auto_start=True)
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("ending test")
    ct.asm_terminate_system()
    ct.end_column(column_name=end_column)
    
    
    
    ct.end_test()
    
     
def insert_fork_join_column_a(ct):
    
    sequence_til_pass_node = ct.define_sequence_til_pass_node (column_name="sequence_til_pass_node")

    fork_child_1 = ct.define_column("fork_child_1")
    ct.asm_log_message("fork child 1 starting")
    ct.asm_event_logger("displaying fork child 1 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=2)
    ct.mark_sequence_false_link(parent_node_name=sequence_til_pass_node,data={"message":"first sequence failed"})
    ct.asm_log_message("fork 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_1)
    
    
    fork_child_2 = ct.define_column("fork_child_2")
    ct.asm_log_message("fork child 2 starting")
    ct.asm_event_logger("displaying fork child 2 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=3)
    ct.mark_sequence_false_link(parent_node_name=sequence_til_pass_node,data={"message":"second sequence failed"})
    ct.asm_log_message("fork 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_2)
    
    fork_child_3 = ct.define_column("fork_child_3")
    ct.asm_log_message("fork child 3 starting")
    ct.asm_event_logger("displaying fork child 3 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=5)
    ct.mark_sequence_false_link(parent_node_name=sequence_til_pass_node,data={"message":"third sequence failed"})
    ct.asm_log_message("fork 3 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_3)

    ct.mark_sequence_false_link(parent_node_name=sequence_til_pass_node,data={"message":"fourth sequence failed"})
    ct.asm_terminate()
    ct.end_sequence_node(column_name=sequence_til_pass_node)
    
        
def eighth_test(ct,kb_name): # sequence til
    ct.start_test(test_name=kb_name)
    
    main_node = ct.define_sequence_start_node(column_name="main_node",finalize_function="DISPLAY_SEQUENCE_RESULT",auto_start=True)
    ct.asm_log_message("main node")
    insert_fork_join_column_a(ct)
    ct.asm_log_message("main node is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=main_node)
    
    ct.end_test()
    
def insert_sequence_til_fail_column(ct):
    
    sequence_til_fail_node = ct.define_sequence_til_fail_node (column_name="sequence_til_fail_node")

    fork_child_1 = ct.define_column("fork_child_1")
    ct.asm_log_message("fork child 1 starting")
    ct.asm_event_logger("displaying fork child 1 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=2)
    ct.mark_sequence_true_link(parent_node_name=sequence_til_fail_node,data={"message":"first sequence passed"})
    ct.asm_log_message("fork 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_1)
    
    
    fork_child_2 = ct.define_column("fork_child_2")
    ct.asm_log_message("fork child 2 starting")
    ct.asm_event_logger("displaying fork child 2 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=3)
    ct.mark_sequence_true_link(parent_node_name=sequence_til_fail_node,data={"message":"second sequence passed"})
    ct.asm_log_message("fork 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_2)
    
    fork_child_3 = ct.define_column("fork_child_3")
    ct.asm_log_message("fork child 3 starting")
    ct.asm_event_logger("displaying fork child 3 events",["TEST_EVENT"])
    ct.asm_wait_time(time_delay=5)
    ct.mark_sequence_true_link(parent_node_name=sequence_til_fail_node,data={"message":"third sequence passed"})
    ct.asm_log_message("fork 3 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=fork_child_3)

    ct.mark_sequence_true_link(parent_node_name=sequence_til_fail_node,data={"message":"fourth sequence passed"})
    ct.asm_terminate()
    ct.end_sequence_node(column_name=sequence_til_fail_node)
    
    
def ninth_test(ct,kb_name): # sequence til
    ct.start_test(test_name=kb_name)
    
    main_node = ct.define_sequence_start_node(column_name="main_node",finalize_function="DISPLAY_SEQUENCE_RESULT",auto_start=True)
    ct.asm_log_message("main node")
    insert_sequence_til_fail_column(ct)
    ct.asm_log_message("main node is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=main_node)
    
    ct.end_test()
    

def test_one_for_one_test(ct,top_column_name):
    top_column = ct.define_column(column_name=top_column_name,auto_start=True)
    
    supervisor_node = ct.define_supervisor_one_for_one_node(column_name="supervisor_node",aux_function ="CFL_NULL",
                                           user_data = {},reset_limited_enabled=False,auto_start = True)
    
    branch_1 = ct.define_column(column_name="branch_1",auto_start=True)
    ct.asm_log_message("branch 1 starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("branch 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_1)

    branch_2 = ct.define_column(column_name="branch_2",auto_start=True)
    ct.asm_log_message("branch 2 starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("branch 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_2)
    
    ct.end_column(column_name=supervisor_node)
    
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("top column is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=top_column)
    return top_column
    
def test_one_for_all_test(ct,top_column_name):
    top_column = ct.define_column(column_name=top_column_name,auto_start=True)

    supervisor_node = ct.define_supervisor_one_for_all_node(column_name="supervisor_node",aux_function ="CFL_NULL",
                                           user_data = {},reset_limited_enabled=False,auto_start = True)
    
    branch_1 = ct.define_column(column_name="branch_1",auto_start=True)
    ct.asm_log_message("branch 1 starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("branch 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_1)

    branch_2 = ct.define_column(column_name="branch_2",auto_start=True)
    ct.asm_log_message("branch 2 starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("branch 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_2)
    
    branch_3 = ct.define_column(column_name="branch_3",auto_start=True)
    ct.asm_log_message("branch 3 starting")
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("branch 3 is resetting")
    ct.asm_reset()
    ct.end_column(column_name=branch_3)
    
    
    ct.end_column(column_name=supervisor_node)
    
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("top column is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=top_column)
    return top_column  

    
def test_rest_for_all_test(ct,top_column_name):
        
    top_column = ct.define_column(column_name=top_column_name,auto_start=True)
    
    supervisor_node = ct.define_supervisor_rest_for_all_node(column_name="supervisor_node",aux_function ="CFL_NULL",
                                           user_data = {},reset_limited_enabled=False,auto_start = True)
    
    branch_1 = ct.define_column(column_name="branch_1",auto_start=True)
    ct.asm_log_message("branch 1 starting")
    ct.asm_wait_time(time_delay=21)
    ct.asm_log_message("branch 1 is resetting")
    ct.asm_reset()
    ct.end_column(column_name=branch_1)

    branch_2 = ct.define_column(column_name="branch_2",auto_start=True)
    ct.asm_log_message("branch 2 starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("branch 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_2)
    
    
    
    branch_3 = ct.define_column(column_name="branch_3",auto_start=True)
    ct.asm_log_message("branch 3 starting")
    ct.asm_wait_time(time_delay=120)
    ct.asm_log_message("branch 3 is resetting")
    ct.asm_reset()
    ct.end_column(column_name=branch_3)
    
    
    ct.end_column(column_name=supervisor_node)
    
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("top column is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=top_column)
    return top_column   
 
def test_failure_window_test(ct,top_column_name):
    top_column = ct.define_column(column_name=top_column_name,auto_start=True)
    # should get a failure in around 3 seconds for the window test
    supervisor_node = ct.define_supervisor_one_for_all_node(column_name="supervisor_node",aux_function ="CFL_NULL",
                                           user_data = {},reset_limited_enabled=True,
                                           max_reset_number=3,reset_window=100,finalize_function="DISPLAY_FAILURE_WINDOW_RESULT",finalize_function_data={},
                                           auto_start = True)
    
    branch_1 = ct.define_column(column_name="branch_1",auto_start=True)
    ct.asm_log_message("branch 1 starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("branch 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_1)

    branch_2 = ct.define_column(column_name="branch_2",auto_start=True)
    ct.asm_log_message("branch 2 starting")
    ct.asm_wait_time(time_delay=120)
    ct.asm_log_message("branch 2 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_2)
    
    branch_3 = ct.define_column(column_name="branch_3",auto_start=True)
    ct.asm_log_message("branch 3 starting")
    ct.asm_wait_time(time_delay=120)
    ct.asm_log_message("branch 3 is resetting")
    ct.asm_reset()
    ct.end_column(column_name=branch_3)
    
    
    ct.end_column(column_name=supervisor_node)
    
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("top column is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=top_column)
    return top_column  
 
def tenth_test(ct,kb_name): # supervisor node
    ct.start_test(test_name=kb_name)
    test_start = ct.define_column(column_name="test_coordinator_node",column_data=None,auto_start=True)
    
    ct.asm_log_message("starting test one for one")
    test_one_for_one = test_one_for_one_test(ct,"one_for_one_column")
    ct.define_join_link(test_one_for_one)
    
    
    ct.asm_log_message("starting test one for all")
    test_one_for_all = test_one_for_all_test(ct,"one_for_all_column")
    ct.define_join_link(test_one_for_all)
    
    ct.asm_log_message("starting test rest for all")
    test_reset_for_all = test_rest_for_all_test(ct,"rest_for_all_column")
    ct.define_join_link(test_reset_for_all)
    
    ct.asm_log_message("testing failure window test")
    test_failure_window = test_failure_window_test(ct,"failure_window_column")
    ct.define_join_link(test_failure_window)
    
    ct.asm_log_message("test coordinator node is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=test_start)
    
    ct.end_test()
    
    
def eleventh_test(ct,kb_name): # supervisor node
    ct.start_test(test_name=kb_name)
    
    for_column = ct.define_for_column(column_name="for_column",number_of_iterations=3,auto_start=True)
    branch_1 = ct.define_column(column_name="branch_1",auto_start=True)
    ct.asm_log_message("branch 1 starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("branch 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_1)
    ct.end_column(column_name=for_column)
    
    ct.end_test()
    
    
def twelfth_test(ct,kb_name): # while column
    ct.start_test(test_name=kb_name)
    
    while_column = ct.define_while_column(column_name="while_column",aux_function="WHILE_TEST",user_data={"count":5},auto_start=True)
    branch_1 = ct.define_column(column_name="branch_1",auto_start=True)
    ct.asm_log_message("branch 1 starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("branch 1 is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=branch_1)
    ct.end_column(column_name=while_column)
    
    ct.end_test() 
    
def thirteenth_test(ct,kb_name): # watch dog
    ct.start_test(test_name=kb_name)
    
    watch_dog_column = ct.define_column(column_name="watch_dog_column",auto_start=True)
    ct.asm_log_message("starting watch dog column")
    wd_node_id = ct.asm_watch_dog_node(node_id=watch_dog_column,wd_time_count=3,wd_reset=True,wd_fn="WATCH_DOG_TIME_OUT",
                          wd_fn_data={"message":"************ watch dog time out  reset action"})
    ct.asm_log_message("watch dog node enabled")
    ct.asm_enable_watch_dog(node_id=wd_node_id)
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("patting watch dog")
    ct.asm_pat_watch_dog(node_id=wd_node_id)
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("disabling watch dog")
    ct.asm_disable_watch_dog(node_id=wd_node_id)
    ct.asm_wait_time(time_delay=4)
    ct.asm_log_message("enabling watch dog")
    ct.asm_enable_watch_dog(node_id=wd_node_id)
    ct.asm_wait_time(time_delay=10)
    ct.asm_log_message("this should not be reached")
    ct.asm_terminate()
    ct.end_column(column_name=watch_dog_column)
    
    end_column = ct.define_column(column_name="end_column",auto_start=True)
    ct.asm_wait_time(time_delay=33)
    ct.asm_log_message("ending test")
    ct.asm_terminate_system()
    ct.end_column(column_name=end_column)
    
    ct.end_test() 
 
 
def insert_register_event_column(ct):
    register_event_column = ct.define_column(column_name="register_event_column",auto_start=True)
    ct.asm_log_message("registering data flow event")
    
    ct.asm_define_df_token("a","a token")
    ct.asm_define_df_token("b","b token")
    ct.asm_define_df_token("c","c token")
    ct.asm_clear_df_token("a","a token is off")
    ct.asm_clear_df_token("b","b token is off")
    ct.asm_clear_df_token("c","c token is off")
    ct.asm_terminate()
    ct.end_column(column_name=register_event_column)
    return register_event_column

def insert_event_generator_column(ct):
    event_generator_column = ct.define_column(column_name="event_generator_column",auto_start=True)
    ct.asm_log_message("generating event")
    ct.asm_log_message("all events are on")
    ct.asm_set_df_token("a","a token is on")
    ct.asm_set_df_token("b","b token is on" )
    ct.asm_set_df_token("c","c token is on")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("clear a event")
    ct.asm_clear_df_token("a","a token is off")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("set a event and clear c event")
    ct.asm_set_df_token("a","a token is on")
    ct.asm_clear_df_token("c","c token is off")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("clear b event and set c event")
    ct.asm_clear_df_token("b","b token is off")
    ct.asm_set_df_token("c","c token is on")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("reseting event generator column")
    ct.asm_log_message("reset")
    ct.asm_reset()
    ct.end_column(column_name=event_generator_column)
    return event_generator_column

def insert_event_mask_df(ct):
    
    
    data_flow_mask_column = ct.define_data_flow_event_mask("df_mask",aux_function="DF_EXPRESSION",event_list=["a","c"])
                                                           
    ct.asm_log_message("data flow expression column is generated")
    ct.asm_event_logger("----------->  displaying data flow mask events",["CFL_SECOND_EVENT"])
    ct.asm_halt()
    ct.end_column(column_name=data_flow_mask_column)
    return data_flow_mask_column



def insert_data_flow_expression_column(ct):
    s_expression = ['or',['and', 'a', ['or','b','c']]]
    
    data_flow_expression_column = ct.define_data_flow_event_expression("df_expression",aux_function="DF_EXPRESSION",s_expression=s_expression,
                                                                       trigger_event="CFL_TIMER_EVENT",trigger_event_count=4) 
    ct.asm_log_message("data flow expression column is generated")
    ct.asm_event_logger("+++++++++++++++> displaying data flow expression events",["CFL_SECOND_EVENT"])
    ct.asm_halt()
    ct.end_column(column_name=data_flow_expression_column)
    return data_flow_expression_column



def fourteenth_test(ct,kb_name): # data flow
    ct.start_test(test_name=kb_name)


    ##### register data flow events
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    register_event_column = insert_register_event_column(ct)
    ct.define_join_link(register_event_column)
   
    #### periodic data flow event set and clear
    event_generator = insert_event_generator_column(ct)

    #### data flow event expression
    data_flow_expression_column = insert_data_flow_expression_column(ct)
    #### data flow event mask
    data_flow_mask_column = insert_event_mask_df(ct)
    

    
    ct.asm_wait_time(time_delay=30)
    ct.asm_log_message("launch column is terminating")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.end_test() 
   
   
def define_template_a(ct):
    ct.start_template("a")
    column_a = ct.define_column(column_name="a",auto_start=True)
    ct.asm_log_message("a template a is running")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("a template a is terminating at 5 seconds")
    ct.asm_terminate()
    ct.end_column(column_name=column_a)
    ct.end_template()
   
def define_template_b(ct):
    ct.start_template("b")
    column_a = ct.define_column(column_name="a",auto_start=True)
    ct.asm_log_message("b template b is running")
    ct.asm_wait_time(time_delay=10)
    ct.asm_log_message("b template b is terminating at 10 seconds")
    ct.asm_terminate()
    ct.end_column(column_name=column_a)
    ct.end_template()


def define_template_c(ct):
   ct.start_template("c")
   column_a = ct.define_column(column_name="a",auto_start=True)
   ct.asm_log_message("c template c is running ")
   ct.asm_wait_time(time_delay=15)
   ct.asm_log_message("c template c is terminating at 15 seconds")
   ct.asm_terminate()
   ct.end_column(column_name=column_a)
   ct.end_template()
   
def define_template_d(ct):
   ct.start_template("d")
   column_a = ct.define_column(column_name="a",auto_start=True)
   ct.asm_log_message("d template d is running")
   ct.asm_wait_time(time_delay=20)
   ct.asm_log_message("d template d is terminating at 20 seconds")
   ct.asm_terminate()
   ct.end_column(column_name=column_a)
   ct.end_template()
 
def define_template_e(ct):
    ct.start_template("e")
    column_a = ct.define_column(column_name="a",auto_start=True)
    ct.asm_log_message("e template e is running")
    ct.asm_one_shot_handler(one_shot_fn="GET_TEMPLATE_INPUT_DATA",one_shot_data={})
    ct.asm_one_shot_handler(one_shot_fn="SET_TEMPLATE_OUTPUT_DATA",one_shot_data={"data":"e template e is running"})
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("e template e is terminating at 5 seconds")
    ct.asm_terminate()
    ct.end_column(column_name=column_a)
    ct.end_template()
   
def define_template_f(ct):
    ct.start_template("f")
    column_a = ct.define_column(column_name="a",auto_start=True)
    ct.asm_log_message("f template f is running")
    ct.asm_one_shot_handler(one_shot_fn="GET_TEMPLATE_INPUT_DATA",one_shot_data={})
    ct.asm_one_shot_handler(one_shot_fn="SET_TEMPLATE_OUTPUT_DATA",one_shot_data={"data":"f template f is running"})
    ct.asm_wait_time(time_delay=10)
    ct.asm_log_message("f template f is terminating at 10 seconds")
    ct.asm_terminate()
    ct.end_column(column_name=column_a)
    ct.end_template()


def define_template_g(ct):
   ct.start_template("g")
   column_a = ct.define_column(column_name="a",auto_start=True)
   ct.asm_log_message("g template g is running ")
   ct.asm_one_shot_handler(one_shot_fn="GET_TEMPLATE_INPUT_DATA",one_shot_data={})
   ct.asm_one_shot_handler(one_shot_fn="SET_TEMPLATE_OUTPUT_DATA",one_shot_data={"data":"g template g is running"})
   ct.asm_wait_time(time_delay=15)
   ct.asm_log_message("g template g is terminating at 15 seconds")
   ct.asm_terminate()
   ct.end_column(column_name=column_a)
   ct.end_template()
   
def define_template_h(ct):
   ct.start_template("h")
   column_a = ct.define_column(column_name="a",auto_start=True)
   ct.asm_log_message("h template h is running")
   ct.asm_one_shot_handler(one_shot_fn="GET_TEMPLATE_INPUT_DATA",one_shot_data={})
   ct.asm_one_shot_handler(one_shot_fn="SET_TEMPLATE_OUTPUT_DATA",one_shot_data={"data":"h template h is running"})
   ct.asm_wait_time(time_delay=20)
   ct.asm_log_message("h template h is terminating at 20 seconds")
   ct.asm_terminate()
   ct.end_column(column_name=column_a)
   ct.end_template() 
 
def fifteenth_test(ct,kb_name): # templates
    
    
    
    ct.start_test(test_name="fifteenth_test",
                  template_function_list=[define_template_a,define_template_b,define_template_c,define_template_d])
    
    
   
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    ct.asm_log_message("using templates")
    template_test_1 = ct.asm_use_templates([["a",{}],["b",{}],["c",{}],["d",{}]],finalize_function_name="FINALIZE_TEMPLATE_RESULTS",
                                           finalize_function_data={"data":"finalize_function_data 1"})
    ct.define_join_link(template_test_1)
    ct.asm_log_message("template test 1 has completed")
    ct.asm_wait_time(time_delay=2)
    
    
    
    
    ct.asm_log_message("using templates again")
    template_test_2 = ct.asm_use_templates([["a",{}],["b",{}],["c",{}],["d",{}]],finalize_function_name="FINALIZE_TEMPLATE_RESULTS",
                                           finalize_function_data={"data":"finalize_function_data 2"})
    ct.define_join_link(template_test_2)
    ct.asm_log_message("template test 2 has completed")
    
    ct.asm_log_message("using variable templates")
    variable_template_test_3 = ct.asm_use_variable_templates(load_function_name="LOAD_TEMPLATE_DATA",
                                                             load_function_data={"template_list": [["a",{}],["b",{}],["c",{}],["d",{}]]},
                                                             finalize_function_name="FINALIZE_TEMPLATE_RESULTS",
                                                             finalize_function_data={"data":"finalize_function_data 3"})
    ct.define_join_link(variable_template_test_3)
    ct.asm_log_message("variable template test 1 has completed")
    ct.asm_wait_time(time_delay=2)
    
    
    
    
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("launch column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
   
    
    ct.end_test()

    
    
def sixteenth_test(ct,kb_name): # templates
        
    ct.start_test(test_name=kb_name)

    define_template_e(ct)
    define_template_f(ct)
    define_template_g(ct)
    define_template_h(ct)
    

   
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    ct.asm_log_message("using templates")
    template_test_1 = ct.asm_use_templates([["e",{"id":1}],["f",{"id":2}],["g",{"id":3}],["h",{"id":4}]],
                                           finalize_function_name="FINALIZE_TEMPLATE_RESULTS",
                                           finalize_function_data={"data":"finalize_function_data 1"})
    ct.define_join_link(template_test_1)
    ct.asm_log_message("template test 1 has completed")
    ct.asm_wait_time(time_delay=2)
    
    
    
    
    ct.asm_log_message("using templates again")
    template_test_2 = ct.asm_use_templates([["e",{"id":10}],["f",{"id":20}],["g",{"id":30}],["h",{"id":40}]],
                                           finalize_function_name="FINALIZE_TEMPLATE_RESULTS",
                                           finalize_function_data={"data":"finalize_function_data 2"})
    ct.define_join_link(template_test_2)
    ct.asm_log_message("template test 2 has completed")
    
    #ct.asm_wait_time(time_delay=30)
    
    
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("launch column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.end_test() 


def test_unhandled_exception(ct):
    no_exception_column = ct.define_column(column_name="no_exception_column",auto_start=True)
    ct.asm_log_message("no exception column is starting")
    ct.asm_wait_time(time_delay=5)
    ct.asm_raise_exception(exception_id="TEST_EXECEPTION",exception_data={"exception_data":"exception_data"})
    ct.asm_wait_time(time_delay=4)
    ct.asm_log_message("should not be reached")
    ct.asm_terminate()
    ct.end_column(column_name=no_exception_column)


def seventeenth_test(ct,kb_name): # exception handler
    ct.start_test(test_name=kb_name)
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    ct.asm_log_message("using exception handler")
    
    exception_handler_column = ct.exception_catch(column_name="exception_handler_column",
                            aux_function_name="CFL_NULL",
                            aux_function_data={},
                            logging_function_name="MY_EXCEPTION_LOGGING",
                            logging_function_data={"logging_function_data":"logging_function_data"},
                            exception_id_list=["TEST_EXECEPTION"],
                            default_exception_handler_name="MY_EXCEPTION_DISPATCHER",
                            default_exception_handler_data={"default_exception_handler_function_data":"default_exception_handler_function_data"})
    
    
    middle_column = ct.define_column(column_name="middle_column",auto_start=True)
    ct.asm_log_message("middle column is starting")
    
    exception_raise_column = ct.define_column(column_name="exception_raise_column",auto_start=True)
    ct.asm_log_message("exception handler column is starting")
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("raising exception")
    ct.asm_raise_exception(exception_id="TEST_EXECEPTION",exception_data={"exception_data":"exception_data"})
    ct.asm_wait_time(time_delay=4)
    ct.asm_log_message("should not be reached")
    ct.asm_terminate()
    ct.end_column(column_name=exception_raise_column)
    ct.asm_wait_time(time_delay=10)
    ct.asm_log_message("middle column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=middle_column)
    
    error_recovery_column = ct.define_column(column_name="error_recovery_column",auto_start=False)
    ct.asm_log_message("error recovery column is starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("error recovery column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=error_recovery_column)
    
    ct.end_column(column_name= exception_handler_column)
      
    ct.add_exception_recovery_link(except_node_id=exception_handler_column,
                                   link_id=middle_column,
                                   disable_columns=[middle_column],enable_columns=[error_recovery_column])
    ct.add_exception_recovery_link(except_node_id=exception_handler_column,
                                   link_id=error_recovery_column,
                                   disable_columns=[],enable_columns=[])
    
    ct.finalize_exception_recovery_links(exception_handler_column)
    
    unhandled_test = False
    if unhandled_test:
        test_unhandled_exception(ct)
    
    ct.define_join_link(exception_handler_column)
    ct.asm_log_message("launch column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.end_test() 
    
def eighteenth_test(ct,kb_name): # exception handler
    ct.start_test(test_name=kb_name )
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    ct.asm_log_message("using top exception handler")
    top_exception_handler_column = ct.exception_catch(column_name="top_exception_handler_column",
                            aux_function_name="CFL_NULL",
                            aux_function_data={},
                            logging_function_name="MY_EXCEPTION_LOGGING",
                            logging_function_data={"logging_function_data":"logging_function_data"},
                            exception_id_list=["TEST_EXECEPTION"],
                            default_exception_handler_name="MY_TOP_EXCEPTION_DISPATCHER",
                            default_exception_handler_data=
                               {"default_exception_handler_function_data":"default_exception_handler_function_data"},auto_start=True)
    
    exception_handler_column = ct.exception_catch(column_name="exception_handler_column",
                            aux_function_name="CFL_NULL",
                            aux_function_data={},
                            logging_function_name="MY_EXCEPTION_LOGGING",
                            logging_function_data={"logging_function_data":"logging_function_data"},
                            exception_id_list=["TEST_EXECEPTION"],
                            default_exception_handler_name="MY_EXCEPTION_DISPATCHER",
                            default_exception_handler_data=
                               {"default_exception_handler_function_data":"default_exception_handler_function_data"},auto_start=True)
    
    
    middle_column = ct.define_column(column_name="middle_column",auto_start=True)
    ct.asm_log_message("middle column is starting")
    
    heartbeat_column = ct.define_column(column_name="heartbeat_raise_column",auto_start=True)
    ct.asm_log_message("heartbeat column is starting")
    ct.asm_log_message("turning heartbeat on")
    ct.asm_turn_heartbeat_on(parent_node_name=heartbeat_column,time_out=4)
    ct.asm_heartbeat_event(parent_node_name=heartbeat_column)
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("should not be reached")
    ct.asm_log_message("turning heartbeat off")
    ct.asm_turn_heartbeat_off(parent_node_name=heartbeat_column)
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("turning heartbeat on")
    ct.asm_turn_heartbeat_on(parent_node_name=heartbeat_column,time_out=2)
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("should not be reached")
    ct.asm_terminate()
    ct.end_column(column_name=heartbeat_column)
    
    ct.define_join_link(exception_handler_column)
    ct.asm_log_message("middle column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=middle_column)
    
    error_recovery_column = ct.define_column(column_name="error_recovery_column",auto_start=False)
    ct.asm_log_message("error recovery column is starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("error recovery column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=error_recovery_column)
    
    ct.end_column(column_name= exception_handler_column)
    ct.define_join_link(exception_handler_column)
    ct.end_column(column_name= top_exception_handler_column)
    ct.define_join_link(top_exception_handler_column)
      
    ct.add_exception_recovery_link(except_node_id=exception_handler_column,
                                   link_id=middle_column,
                                   disable_columns=[middle_column],enable_columns=[error_recovery_column])
    ct.add_exception_recovery_link(except_node_id=exception_handler_column,
                                   link_id=error_recovery_column,
                                   disable_columns=[],enable_columns=[])
    
    ct.finalize_exception_recovery_links(exception_handler_column)
    
   
    
   
    
    ct.define_join_link(exception_handler_column)
    ct.asm_log_message("launch column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    ct.finalize_and_check()
    
test_1 = "(pipeline (@CFL_LOGM test_message1) (@CFL_LOGM test_message2) 'CFL_FUNCTION_TERMINATE))" 
test_2 = "(pipeline (@CFL_LOGM wait_for_three_seconds ) (!CFL_WAIT 3) (@CFL_LOGM wait_for_two_seconds) (!CFL_WAIT 2) \
    (@CFL_LOGM terminate_sequence) 'CFL_FUNCTION_TERMINATE))"
test_3 = "(pipeline (!CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ) (!CFL_WAIT 3) (@CFL_LOGM wait_for_two_seconds) (!CFL_WAIT 2) \
    (@CFL_LOGM terminate_sequence) (@CFL_LOGM wait_five_seconds_for_timeout) 'CFL_FUNCTION_HALT))"
    




def nineteenth_test(ct,kb_name): # s node control
    ct.start_test(test_name=kb_name)
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    ct.asm_log_message("using s node control")

    
    s_node_control_column = ct.define_s_node_control(column_name="s_node_control_column",
                            aux_function_name="CFL_NULL",
                            s_expression=test_3,
                            user_data={"user_data":"user_data"})
    
    ct.end_s_node_control(s_node_control_column)
    
    ct.define_join_link(s_node_control_column)
    ct.asm_log_message("s node control column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.finalize_and_check()
   
   
link_test_1 = "(pipeline (@CFL_KILL_CHILDREN) (@CFL_FORK 0)  (@CFL_FORK 1) (!CFL_JOIN 0) (@CFL_FORK 2 ) (!CFL_JOIN 2)\
    (!CFL_JOIN 0) 'CFL_FUNCTION_TERMINATE))" 
link_test_2 = "(pipeline (@CFL_KILL_CHILDREN) (@CFL_FORK 0) (!CFL_JOIN 0) (@CFL_FORK 1) (!CFL_JOIN 1)\
                        (@CFL_FORK 2) (!CFL_JOIN 2) 'CFL_FUNCTION_TERMINATE))" 
link_test_3 = "(pipeline (@CFL_KILL_CHILDREN) (@CFL_FORK 0) (@CFL_FORK 1) (!CFL_JOIN 0) (!CFL_WAIT 4) (@CFL_TERMINATE 1) \
             (@CFL_FORK 2) (!CFL_JOIN 2) 'CFL_FUNCTION_TERMINATE))"

 
def twentieth_test(ct,kb_name): # s node control
    ct.start_test(test_name=kb_name)
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
   
    
    s_node_control_column = ct.define_s_node_control(column_name="s_node_control_column",
                            aux_function_name="CFL_NULL",
                            s_expression=link_test_3,
                            user_data={"user_data":"user_data"})
    
    test_column_one = ct.define_column(column_name="test_column_one",auto_start=False)
    ct.asm_log_message("test column one is starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("test column one is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_one)
    
    test_column_two = ct.define_column(column_name="test_column_two",auto_start=False)
    ct.asm_log_message("test column two is starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("test column two is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_two)
    
    test_column_three = ct.define_column(column_name="test_column_three",auto_start=False)
    ct.asm_log_message("test column three is starting")
    ct.asm_wait_time(time_delay=5)
    ct.asm_log_message("test column three is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_three)
    
   
    
    ct.end_s_node_control(s_node_control_column)
    
    ct.define_join_link(s_node_control_column)
  
    
    
    ct.asm_log_message("s node control column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.finalize_and_check()


link_test_4 = """
  (dispatch event_id
  ("CFL_INIT_EVENT" (pipeline (@CFL_SET_INITIAL_STATE 0)  !CFL_RESET_CODES 'CFL_FUNCTION_RETURN))
  ("CFL_TERM_EVENT" (pipeline (@CFL_KILL_CHILDREN) 'CFL_FUNCTION_RETURN))
 
  ("CFL_CHANGE_STATE" (pipeline (@CFL_SET_STATE 0)  !CFL_RESET_CODES 'CFL_FUNCTION_HALT))

  
  
  (default 'CFL_FUNCTION_RETURN)
  )
 

"""



def twenty_first_test(ct,kb_name): # s node control
    ct.start_test(test_name=kb_name)
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    test_timeout_column = ct.define_column(column_name="test_timeout_column",auto_start=True)
    ct.asm_log_message("test timeout column is starting")
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("test timeout column is terminating ")
    ct.asm_terminate_system()
    ct.end_column(column_name=test_timeout_column)
    
    ct.asm_log_message("using s node control")

    
    s_node_control_column = ct.define_s_node_control(column_name="s_node_control_column",
                            aux_function_name="CFL_NULL",
                            s_expression=link_test_4,
                            user_data={"user_data":"user_data"})
    
    test_column_one = ct.define_column(column_name="test_column_one",auto_start=True)
    ct.asm_log_message("test column one is starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to 1")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":1})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column one is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_one)
    
    test_column_two = ct.define_column(column_name="test_column_two",auto_start=True)
    ct.asm_log_message("test column two is starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("changing state to 2")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":2})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column two is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_two)
    
    test_column_three = ct.define_column(column_name="test_column_three",auto_start=True)
    ct.asm_log_message("test column three is starting")
    ct.asm_wait_time(time_delay=4)
    ct.asm_log_message("changing state to 0")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":0})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column three is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_three)
    
   
    
    ct.end_s_node_control(s_node_control_column)
    
    ct.define_join_link(s_node_control_column)
  
    
    
    ct.asm_log_message("s node control column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.finalize_and_check()
    
    
    
    
link_test_5 = """
  (dispatch event_id
  ("CFL_INIT_EVENT" (pipeline (@CFL_KILL_CHILDREN) (@CFL_FORK 0) (@CFL_FORK 1) !CFL_RESET_CODES 'CFL_FUNCTION_RETURN))
  ("CFL_TERM_EVENT" (pipeline (@CFL_KILL_CHILDREN) !CFL_RESET_CODES 'CFL_FUNCTION_RETURN))
 
  ("CFL_CHANGE_STATE" (cond  ((?CFL_IS_STATE 0) (pipeline (@CFL_KILL_CHILDREN)(@CFL_FORK 0)(@CFL_FORK 1) !CFL_RESET_CODES 'CFL_FUNCTION_RETURN) )
                             ((?CFL_IS_STATE 1) (pipeline (@CFL_KILL_CHILDREN)(@CFL_FORK 2)(@CFL_FORK 3) !CFL_RESET_CODES 'CFL_FUNCTION_RETURN) )
                             (else (pipeline (@CFL_LOGM "Invalid state") !CFL_RESET_CODES 'CFL_FUNCTION_TERMINATE))))

  
  (default 'CFL_FUNCTION_RETURN)
  )
"""

link_test_6 = """
  (dispatch event_id
  ("CFL_INIT_EVENT" (pipeline (@CFL_KILL_CHILDREN) (@CFL_MARK_INIT_STATE 0) !CFL_RESET_CODES 'CFL_FUNCTION_RETURN))
  ("CFL_TERM_EVENT" (pipeline (@CFL_KILL_CHILDREN) !CFL_RESET_CODES 'CFL_FUNCTION_RETURN))
 
  ("CFL_CHANGE_STATE" (pipeline @CFL_KILL_CHILDREN @CFL_MARK_STATE  !CFL_RESET_CODES 'CFL_FUNCTION_RETURN))
  
  
  
  (default (cond ((?CFL_IS_STATE 0) (pipeline (@CFL_FORK 0) (@CFL_FORK 1) 'CFL_FUNCTION_RETURN) )
                    ((?CFL_IS_STATE 1) (pipeline (@CFL_FORK 2) (@CFL_FORK 3) 'CFL_FUNCTION_RETURN) )
                    (else (pipeline (@CFL_LOGM "Invalid state") !CFL_RESET_CODES 'CFL_FUNCTION_TERMINATE))))
  )
"""
    
def twenty_second_test(ct,kb_name): # s node control
    ct.start_test(test_name=kb_name)
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    test_timeout_column = ct.define_column(column_name="test_timeout_column",auto_start=True)
    ct.asm_log_message("test timeout column is starting")
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("test timeout column is terminating ")
    ct.asm_terminate_system()
    ct.end_column(column_name=test_timeout_column)
    
    ct.asm_log_message("using s node control")

    
    s_node_control_column = ct.define_s_node_control(column_name="s_node_control_column",
                            aux_function_name="CFL_NULL",
                            s_expression=link_test_6,
                            user_data={"user_data":"user_data"})
    
    test_column_one = ct.define_column(column_name="test_column_one",auto_start=True)
    ct.asm_log_message("test column one is starting")
    ct.asm_wait_time(time_delay=2)

    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column one is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_one)
    
    test_column_two = ct.define_column(column_name="test_column_one",auto_start=True)
    ct.asm_log_message("test column two is starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to 1")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":1})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column two is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_two)
    
    test_column_three = ct.define_column(column_name="test_column_two",auto_start=True)
    ct.asm_log_message("test column three is starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("test column three is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_three)
    
    test_column_four = ct.define_column(column_name="test_column_three",auto_start=True)
    ct.asm_log_message("test column four is starting")
    ct.asm_wait_time(time_delay=4)
    ct.asm_log_message("changing state to 0")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":0})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column four is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_four)
    
   
    
    ct.end_s_node_control(s_node_control_column)
    
    ct.define_join_link(s_node_control_column)
  
    
    
    ct.asm_log_message("s node control column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.end_test()
    
macro_test_1 = "(pipeline (@CFL_KILL_CHILDREN) (fork_join 0) (fork_join 1)  (fork_join 2)   'CFL_FUNCTION_TERMINATE))"    
def twenty_third_test(ct,kb_name): # s node control
    macro_test_2 = ("(pipeline (@CFL_KILL_CHILDREN) (fork_join 0) (fork_join 1) " +
                ct.lisp_sequencer.send_current_node_event("CFL_CHANGE_STATE", {"state": 1}) +" (fork_join 2) 'CFL_FUNCTION_TERMINATE)")
    
    
    ct.start_test(test_name=kb_name)
    
    launch_column = ct.define_column(column_name="launch_column",auto_start=True)
    ct.asm_log_message("launch column is starting")
    
    test_timeout_column = ct.define_column(column_name="test_timeout_column",auto_start=True)
    ct.asm_log_message("test timeout column is starting")
    ct.asm_wait_time(time_delay=20)
    ct.asm_log_message("test timeout column is terminating ")
    ct.asm_terminate_system()
    ct.end_column(column_name=test_timeout_column)
    
    ct.asm_log_message("using s node control")

    
    s_node_control_column = ct.define_s_node_control(column_name="s_node_control_column",
                            aux_function_name="CFL_NULL",
                            s_expression=macro_test_2,
                            user_data={"user_data":"user_data"})
    
    test_column_one = ct.define_column(column_name="test_column_one",auto_start=True)
    ct.asm_log_message("test column one is starting")
    ct.asm_wait_time(time_delay=2)

    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column one is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_one)
    
    test_column_two = ct.define_column(column_name="test_column_one",auto_start=True)
    ct.asm_log_message("test column two is starting")
    ct.asm_wait_time(time_delay=2)
    ct.asm_log_message("changing state to 1")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":1})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column two is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_two)
    
    test_column_three = ct.define_column(column_name="test_column_two",auto_start=True)
    ct.asm_log_message("test column three is starting")
    ct.asm_wait_time(time_delay=3)
    ct.asm_log_message("test column three is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_three)
    
    test_column_four = ct.define_column(column_name="test_column_three",auto_start=True)
    ct.asm_log_message("test column four is starting")
    ct.asm_wait_time(time_delay=4)
    ct.asm_log_message("changing state to 0")
    ct.asm_send_named_event(node_id=s_node_control_column,event_id="CFL_CHANGE_STATE",event_data={"state":0})
    ct.asm_wait_time(time_delay=1)
    ct.asm_log_message("test column four is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=test_column_four)
    
   
    
    ct.end_s_node_control(s_node_control_column)
    
    ct.define_join_link(s_node_control_column)
  
    
    
    ct.asm_log_message("s node control column is terminating ")
    ct.asm_terminate()
    ct.end_column(column_name=launch_column)
    
    ct.end_test()
    
    
def add_header(yaml_file):
    
    ct = ChainTreeMaster.start_build(yaml_file,DataStructures,LispSequencer,template_dirs=["chain_tree_templates"])
    ct.lisp_sequencer.load_template_defs('basic_templates.mako')
    ct.lisp_sequencer.define_macro("fork_join", ["x"], """(@CFL_FORK $x)(!CFL_JOIN $x)""")
    return ct
    

    
    #ct.display_chain_tree_function_mapping()
    


if __name__ == "__main__":
    test_list = ["first_test","second_test","third_test","fourth_test","fifth_test","sixth_test","seventh_test","eighth_test",
                 "ninth_test","tenth_test","eleventh_test","twelfth_test","thirteenth_test","fourteenth_test",
                 "fifteenth_test","sixteenth_test","seventeenth_test","eighteenth_test","nineteenth_test","twentieth_test","twenty_first_test",
                 "twenty_second_test","twenty_third_test"]
    test_dict = { "first_test": first_test, "second_test": second_test, "third_test": third_test, 
                 "fourth_test": fourth_test, "fifth_test": fifth_test, "sixth_test": sixth_test, "seventh_test": seventh_test, "eighth_test": eighth_test, "ninth_test": ninth_test, 
                 "tenth_test": tenth_test, "eleventh_test": eleventh_test, "twelfth_test": twelfth_test, "thirteenth_test": thirteenth_test,
                 "fourteenth_test": fourteenth_test, "fifteenth_test": fifteenth_test, "sixteenth_test": sixteenth_test,
                 "seventeenth_test": seventeenth_test,"eighteenth_test": eighteenth_test,
                 "nineteenth_test": nineteenth_test, "twentieth_test": twentieth_test,"twenty_first_test": twenty_first_test,
                 "twenty_second_test": twenty_second_test,"twenty_third_test": twenty_third_test}



    single_test = "fifteenth_test"
    single_test_flag = False
    if single_test_flag == True:
        ct = add_header("basic_tests.yaml")
        test_dict[single_test](ct,single_test)
        ct.check_and_generate_yaml()
        ct.display_chain_tree_function_mapping()
        exit()
        
    #test_list = ["seventeenth_test","eighteenth_test"]    
   
    ct = add_header("basic_tests.yaml")
    for test in test_list:
    
        test_dict[test](ct,test)
    
    ct.check_and_generate_yaml()
    ct.display_chain_tree_function_mapping()
    print(ct.list_kbs())
    print(ct.list_all_templates())
    exit()
    
