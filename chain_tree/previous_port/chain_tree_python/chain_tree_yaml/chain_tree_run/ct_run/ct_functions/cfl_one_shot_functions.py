from datetime import datetime, timezone
import json
import time

class CFLOneShotFunctions:
    def __init__(self,virtual_one_shot_functions):
        self.virtual_one_shot_functions = virtual_one_shot_functions
        self.one_shot_functions = {}
        
        
    def load_one_shot_functions(self):
       
        function_names = self.one_shot_functions.keys()
        for function_name in function_names:
            self.virtual_one_shot_functions.add_one_shot_function_python(function_name,
                    self.one_shot_functions[function_name]["python_function"],self.one_shot_functions[function_name]["description"])
        
        
    def load_default_one_shot_functions(self):
        
        self.one_shot_functions["CFL_NULL"] = {
            "python_function": cfl_null,
            "description": "null function",
        
        }
        self.one_shot_functions["CFL_LOG_MESSAGE"] = {
            "python_function": cfl_log_message,
            "description": "allows a print out of a message",
        
        }
        self.one_shot_functions["CFL_COLUMN_INIT"] = {
            "python_function": cfl_column_init,
            "description": "Performs column initialization",
            
        }
        self.one_shot_functions["CFL_COLUMN_TERM"] = {
            "python_function": cfl_column_termination,
            "description": "Cleans up for column termination",
            
        }
        self.one_shot_functions["CFL_ENABLE_LINKS"] = {
            "python_function": cfl_enable_links,
            "description": "Enables links for root node",
            
        }
        self.one_shot_functions["CFL_WAIT_TIME_INIT"] = {
            "python_function": cfl_wait_time_init,
            "description": "Waits for a specified time",
        
        }
        self.one_shot_functions["CFL_WAIT_TERM"] = {
            "python_function": cfl_wait_term,
            "description": "Terminates the wait command",
        
        }
        self.one_shot_functions["CFL_WAIT_INIT"] = {
            "python_function": cfl_wait_init,
            "description": "Initializes the wait command",
            
        }
        self.one_shot_functions["CFL_SEND_SYSTEM_EVENT"] = {
            "python_function": cfl_send_system_event,
            "description": "Sends a system event",
        
        }
        self.one_shot_functions["CFL_SEND_NAMED_EVENT"] = {
            "python_function": cfl_send_named_event,
            "description": "Sends a named event",
            
        }
        self.one_shot_functions["CFL_GATE_NODE_INIT"] = {
            "python_function": cfl_gate_node_init,
            "description": "Initializes a gate node",
            
        }
        self.one_shot_functions["CFL_GATE_NODE_TERM"] = {
            "python_function": cfl_gate_node_term,
            "description": "Terminates a gate node",
            
        }
        self.one_shot_functions["CFL_ENABLE_NODES"] = {
            "python_function": cfl_enable_nodes,
            "description": "Enables nodes",
            
        }
        self.one_shot_functions["CFL_DISABLE_NODES"] = {
            "python_function": cfl_disable_nodes,
            "description": "Disables nodes",
            
        }
        self.one_shot_functions["CFL_VERIFY_INIT"] = {
            "python_function": cfl_verify_init,
            "description": "Initializes the verify command",
            
        }
        self.one_shot_functions["CFL_VERIFY_TERM"] = {
            "python_function": cfl_verify_term,
            "description": "Terminates the verify command",
            
        }
        self.one_shot_functions["CFL_PUBLISH_EVENT"] = {
            "python_function": cfl_publish_event,
            "description": "Publishes an event",
    
        }
        self.one_shot_functions["CFL_SUBSCRIBE_EVENTS"] = {
            "python_function": cfl_subscribe_events,
            "description": "Subscribes to events",
            
        }
        self.one_shot_functions["CFL_UNSUBSCRIBE_EVENTS"] = {
            "python_function": cfl_unsubscribe_events,
            "description": "Unsubscribes from events",
            
        }
        self.one_shot_functions["CFL_SEND_IMMEDIATE_EVENT"] = {
            "python_function": cfl_send_immediate_event,
            "description": "sends an immediate event",
            
        }
        self.one_shot_functions["CFL_CHANGE_STATE"] = {
            "python_function": cfl_change_state,
            "description": "Changes the state",
        
        }
        self.one_shot_functions["CFL_STATE_MACHINE_TERM"] = {
            "python_function": cfl_state_machine_term,
            "description": "Ends the state machine",
            
        }
        self.one_shot_functions["CFL_STATE_MACHINE_INIT"] = {
            "python_function": cfl_state_machine_init,
            "description": "Initializes the state machine",
            
        }
        self.one_shot_functions["CFL_FORK_INIT"] = {
            "python_function": cfl_fork_init,
            "description": "Initializes the fork",
            
        }
        self.one_shot_functions["CFL_FORK_TERM"] = {
            "python_function": cfl_fork_term,
            "description": "Terminates the fork",
            
        }
        self.one_shot_functions["CFL_WATCH_DOG_NODE_INIT"] = {
            "python_function": cfl_watch_dog_node_init,
            "description": "Initializes the watch dog node",
        
        }
        self.one_shot_functions["CFL_WATCH_DOG_NODE_TERM"] = {
            "python_function": cfl_watch_dog_node_term,
            "description": "Terminates the watch dog node",
            
        }
        self.one_shot_functions["CFL_SEQUENCE_PASS_INIT"] = {
            "python_function": cfl_sequence_pass_init,
            "description": "Initializes the sequence pass",
        
        }
        self.one_shot_functions["CFL_SEQUENCE_PASS_TERM"] = {
            "python_function": cfl_sequence_pass_term,
            "description": "Terminates the sequence pass",
            
        }
        self.one_shot_functions["CFL_SEQUENCE_FAIL_INIT"] = {
            "python_function": cfl_sequence_fail_init,
            "description": "Initializes the sequence fail",
            
        }
        self.one_shot_functions["CFL_SEQUENCE_FAIL_TERM"] = {
            "python_function": cfl_sequence_fail_term,
            "description": "Terminates the sequence fail",
            
        }
        self.one_shot_functions["CFL_SEQUENCE_START_INIT"] = {
            "python_function": cfl_sequence_start_init,
            "description": "Initializes the sequence start",
            
        }
        self.one_shot_functions["CFL_SEQUENCE_START_TERM"] = {
            "python_function": cfl_sequence_start_term,
            "description": "Terminates the sequence start",
            
        }
        self.one_shot_functions["CFL_MARK_SEQUENCE"] = {
            "python_function": cfl_mark_sequence,
            "description": "Marks the sequence",
            
        }
        
        self.one_shot_functions["CFL_FOR_INIT"] = {
            "python_function": cfl_for_init,
            "description": "Initializes the for",
            
        }
        self.one_shot_functions["CFL_WHILE_INIT"] = {
            "python_function": cfl_while_init,
            "description": "Initializes the while",
            
        }
        self.one_shot_functions["CFL_WHILE_TERM"] = {
            "python_function": cfl_while_term,
            "description": "Terminates the while",
            
        }
        self.one_shot_functions["CFL_ENABLE_WATCH_DOG"] = {
            "python_function": cfl_enable_watch_dog,
            "description": "Enables the watch dog",
            
        }
        self.one_shot_functions["CFL_DISABLE_WATCH_DOG"] = {
            "python_function": cfl_disable_watch_dog,
            "description": "Disables the watch dog",
    
        }
        self.one_shot_functions["CFL_PAT_WATCH_DOG"] = {
            "python_function": cfl_pat_watch_dog,
            "description": "Patches the watch dog",
            
        }
        self.one_shot_functions["CFL_WATCH_DOG_INIT"] = {
            "python_function": cfl_watch_dog_init,
            "description": "Initializes the watch dog",
            
        }
        self.one_shot_functions["CFL_WATCH_DOG_TERM"] = {
            "python_function": cfl_watch_dog_term,
            "description": "Terminates the watch dog",
            
        }
        self.one_shot_functions["CFL_SUPERVISOR_INIT"] = {
            "python_function": cfl_supervisor_init,
            "description": "Initializes the supervisor",
            
        }
        self.one_shot_functions["CFL_SUPERVISOR_TERM"] = {
            "python_function": cfl_supervisor_term,
            "description": "Terminates the supervisor",
            
        }
        self.one_shot_functions["CFL_DEFINE_DF_TOKEN"] = {
            "python_function": cfl_define_df_token,
            "description": "Registers data flow events",
            
        }
        self.one_shot_functions["CFL_SET_DF_TOKEN"] = {
            "python_function": cfl_set_df_token,
            "description": "Sets data flow events",
        
        }
        self.one_shot_functions["CFL_CLEAR_DF_TOKEN"] = {
            "python_function": cfl_clear_df_token,
            "description": "Clears data flow events",
            
        }
        self.one_shot_functions["CFL_DF_MASK_INIT"] = {
            "python_function": cfl_df_mask_init,
            "description": "Initializes the data flow mask",
            
        }
        self.one_shot_functions["CFL_DF_MASK_TERM"] = {
            "python_function": cfl_df_mask_term,
            "description": "Terminates the data flow mask",
            
        }
        self.one_shot_functions["CFL_DF_EXPRESSION_INIT"] = {
            "python_function": cfl_df_expression_init,
            "description": "Initializes the data flow expression",
            
        }
        self.one_shot_functions["CFL_DF_EXPRESSION_TERM"] = {
            "python_function": cfl_df_expression_term,
            "description": "Terminates the data flow expression",
            
        }
       
      
        self.one_shot_functions["CFL_USE_TEMPLATE_INIT"] = {
            "python_function": cfl_use_template_init,
            "description": "Initializes the template",
            
        }
        
        self.one_shot_functions["CFL_USE_TEMPLATE_TERM"] = {
            "python_function": cfl_use_template_term,
            "description": "Terminates the template",
    
        }
        self.one_shot_functions["CFL_EXCEPTION_CATCH_INIT"] = {
            "python_function": cfl_exception_catch_init,
            "description": "Initializes the exception",
            
        }
        self.one_shot_functions["CFL_EXCEPTION_CATCH_TERM"] = {
            "python_function": cfl_exception_catch_term,
            "description": "Terminates the exception",
            
        }
        self.one_shot_functions["CFL_RAISE_EXCEPTION"] = {
            "python_function": cfl_raise_exception,
            "description": "Raises an exception",
            
        }
        self.one_shot_functions["CFL_TURN_HEARTBEAT_ON"] = {
            "python_function": cfl_turn_heartbeat_on,
            "description": "Turns the heartbeat on",

        }
        self.one_shot_functions["CFL_TURN_HEARTBEAT_OFF"] = {
            "python_function": cfl_turn_heartbeat_off,
            "description": "Turns the heartbeat off",
            
        }
        self.one_shot_functions["CFL_HEARTBEAT_EVENT"] = {
            "python_function": cfl_heartbeat_event,
            "description": "Sends the heartbeat event",
        
        }
        self.one_shot_functions["CFL_S_NODE_CONTROL_TERM"] = {
            "python_function": cfl_s_node_control_term,
            "description": "Terminates the s node control",
            
        }
        self.one_shot_functions["CFL_S_NODE_CONTROL_INIT"] = {
            "python_function": cfl_s_node_control_init,
            "description": "Initializes the s node control",
            
        }
        self.one_shot_functions["CFL_VARIABLE_TEMPLATE_INIT"] = {
            "python_function": cfl_variable_template_init,
            "description": "Initializes the variable template",
            
        }
        self.one_shot_functions["CFL_VARIABLE_TEMPLATE_TERM"] = {
            "python_function": cfl_variable_template_term,
            "description": "Terminates the variable template",
            
        }
        self.one_shot_functions["CFL_TERMINATE_STATE_MACHINE"] = {
            "python_function": cfl_terminate_state_machine,
            "description": "Terminates the state machine",
            
        }
        self.one_shot_functions["CFL_RESET_STATE_MACHINE"] = {
            "python_function": cfl_reset_state_machine,
            "description": "Resets the state machine",
            
        }
        self.load_one_shot_functions()

def cfl_null(handle,node_data):
        pass
    
def cfl_log_message(handle, node):
        node_id = node["label_dict"]["ltree_name"]
        node_data = node["node_dict"]
        message = node_data["message"]
        utc_time = datetime.now(timezone.utc)  # Modern way
        timestamp = (utc_time.timestamp())
        readable = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{timestamp}]  ************** node id: [{node_id}] message: {message}")
        
    
def cfl_column_init(handle,node):
    cfl_enable_links(handle,node)

    
def cfl_column_termination(handle, node):
        pass
    
        
    
def cfl_gate_node_init(handle,node):
    chain_tree = handle["chain_tree"]
    cfl_auto_start_links(handle,node)
    
def cfl_gate_node_term(handle,node):
    cfl_column_termination(handle,node)

def cfl_enable_links(handle,node):
    ct_engine = handle["ct_engine"]
    label_dict = node["label_dict"]
    links = label_dict["links"]
    for link in links:
        
        ct_engine.reset_node_id(link)
      


def cfl_auto_start_links(handle,node):
    ct_engine = handle["ct_engine"]
    label_dict = node["label_dict"]
    links = label_dict["links"]
    for link in links:

        link_data = ct_engine.get_node_data(link)
        if  "auto_start" not in link_data["node_dict"]:
            continue
        
        if link_data["node_dict"]["auto_start"] == True:
        
            ct_engine.enable_node_id(link)
        else:
            ct_engine.terminate_node_id(link)

    
def cfl_wait_time_init(handle,node):
    node_data = node["node_dict"]
    node_data["start_time"] = handle["chain_tree"].ct_timer.get_timestamp()
    
def cfl_wait_term(handle,node):
    pass
    
    
def cfl_send_system_event(handle,node): 
     node_data = node["node_dict"]
     handle["chain_tree"].send_system_event(node_data["event_id"],node_data["event_data"])
     
def cfl_send_named_event(handle,node):
     node_data = node["node_dict"]
     handle["chain_tree"].send_system_named_event(node_data["node_id"],node_data["event_id"],node_data["event_data"])
     
def cfl_send_immediate_event(handle,node):
     node_data = node["node_dict"]
     handle["chain_tree"].send_immediate_event(node_data["node_id"],node_data["event_id"],node_data["event_data"])
     
def cfl_wait_init(handle,node):
    node_data = node["node_dict"]
    
    node_data["wait_ctrl"] = {}
    node_data["wait_ctrl"]["current_time_count"] = 0
    node_data["wait_ctrl"]["terminal_count"] = node_data["timeout"]
    node_data["wait_ctrl"]["tm_out_event"] = node_data["time_out_event"]
    
def cfl_enable_nodes(handle,node):

    ct_engine = handle["ct_engine"]
    node_data = node["node_dict"]
    node_ids = node_data["nodes"]
    for node_id in node_ids:
        ct_engine.reset_node_id(node_id)
        
def cfl_disable_nodes(handle,node):
    ct_engine = handle["ct_engine"]
    node_data = node["node_dict"]
    node_ids = node_data["nodes"]
    for node_id in node_ids:
        ct_engine.terminate_node_tree(node_id)
        
def cfl_verify_init(handle,node):
    pass

def cfl_verify_term(handle,node):
    pass
    
    
    
def cfl_publish_event(handle,node):
    
    node_data = node["node_dict"]
    handle["chain_tree"].publish_event(node_data["event_id"],node_data["event_data"])
    
def cfl_subscribe_events(handle,node):
    node_data = node["node_dict"]
    handle["chain_tree"].subscribe_events(node_data["node_id"],node_data["events"])
    
def cfl_unsubscribe_events(handle,node):
    node_data = node["node_dict"]
    handle["chain_tree"].unsubscribe_events(node_data["node_id"],node_data["events"])
    
def cfl_change_state(handle,node):

    chain_tree = handle["chain_tree"]
    sm_node_id = node["node_dict"]["sm_node_id"]
    new_state = node["node_dict"]["new_state"]
    node_id = node["label_dict"]["ltree_name"]
    
    if 'sync_event_id' in node["node_dict"]:
        sync_event_id = node["node_dict"]["sync_event_id"]
        if sync_event_id is not None:
            chain_tree.ct_engine.change_state(node_id,sm_node_id,new_state,sync_event_id)
            chain_tree.send_system_named_event(sm_node_id,sync_event_id,{})
        else:
            chain_tree.ct_engine.change_state(node_id,sm_node_id,new_state)
    else:
        chain_tree.ct_engine.change_state(node_id,sm_node_id,new_state)
 


    
def cfl_state_machine_term(handle,node):
    pass

def cfl_state_machine_init(handle,node):
    
    ct_engine = handle["ct_engine"]
    chain_tree = handle["chain_tree"]

    #ltree_name = node["label_dict"]["ltree_name"]
    label_dict = node["label_dict"]
    sm_name = label_dict["sm_name"]
    sm_initial_state = label_dict["initial_state"]
    sm_state_names = label_dict["state_names"]
    sm_links = label_dict["state_links"]
    node["node_dict"]["current_state"] = sm_initial_state
    node["node_dict"]["new_state"] = sm_initial_state
    
    state_number = chain_tree.find_state_number(sm_initial_state,sm_state_names)
    for link in sm_links:
        ct_engine.terminate_initial_node_id(link)
    ct_engine.enable_selected_node(state_number,sm_links)
   
def cfl_fork_init(handle,node):
    #cfl_column_init(handle,node)
    cfl_enable_links(handle,node)

    
def cfl_fork_term(handle,node):
    pass
   
   
def cfl_watch_dog_node_init(handle,node):
    node["wd_control"]["enabled"] = False
    parent_node_name = node["label_dict"]["parent_node_name"]
    parent_node = handle["chain_tree"].python_dict[parent_node_name]
    parent_node["wd_control"] = {}
    parent_node["wd_control"]["enabled"] = False
    parent_node["wd_control"]["pat_enabled"] = False
    #node["wd_control"]["wd_time_count"] = set by watchdog command line
    node["wd_control"]["wd_time_out"] = 0
    node["wd_control"]["pat_enabled"] = False

def cfl_watch_dog_node_term(handle,node):
    pass

def cfl_sequence_pass_init(handle,node):
    
    chain_tree = handle["chain_tree"]
    chain_tree.sequence_storage.add_sequence_data(node)
    chain_tree.sequence_storage.check_node_exists(node)
    chain_tree.sequence_storage.set_processed(node["label_dict"]["ltree_name"])
    if "sequence_data" not in node:
        node["sequence_data"] = {}
    node["sequence_data"]["current_index"] = 0
    node["sequence_data"]["number_of_links"] = len(node["label_dict"]["links"])
    link = node["label_dict"]["links"][0]
    ct_engine = handle["ct_engine"]
    ct_engine.reset_node_id(link)

def cfl_sequence_pass_term(handle,node):
    
    chain_tree = handle["chain_tree"]
    sequence_element = chain_tree.sequence_storage.get_sequence_element(node["label_dict"]["ltree_name"])
    last_result = sequence_element["results"][-1]
    finalized_results = {}
    if last_result["status"] == True:
        chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],True,len(sequence_element["results"]),finalized_results)
    else:
        chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],False,len(sequence_element["results"]),finalized_results)
    
    column_data = node["node_dict"]["column_data"]
    finalize_function = column_data["finalize_function"]
    #user_data = column_data["user_data"]
    handle["chain_tree"].Vo.run_one_shot_function(finalize_function,handle,node)

def cfl_sequence_fail_init(handle,node):
    cfl_sequence_pass_init(handle,node)

def cfl_sequence_fail_term(handle,node):
    chain_tree = handle["chain_tree"]
    sequence_element = chain_tree.sequence_storage.get_sequence_element(node["label_dict"]["ltree_name"])
    last_result = sequence_element["results"][-1]
    finalized_results = {}
    if last_result["status"] == False:
        chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],False,len(sequence_element["results"]),finalized_results)
    else:
        chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],True,len(sequence_element["results"]),finalized_results)
    
    column_data = node["node_dict"]["column_data"]
    finalize_function = column_data["finalize_function"]
    #user_data = column_data["user_data"]
    handle["chain_tree"].Vo.run_one_shot_function(finalize_function,handle,node)

def cfl_sequence_start_init(handle,node):
    chain_tree = handle["chain_tree"]
    chain_tree.sequence_storage.add_sequence_data(node)
    chain_tree.sequence_storage.check_node_exists(node)
    chain_tree.sequence_storage.reset_node(node["label_dict"]["ltree_name"])
    chain_tree.sequence_storage.set_processed(node["label_dict"]["ltree_name"])
    cfl_enable_links(handle,node)

def cfl_sequence_start_term(handle,node):
    column_data = node["node_dict"]["column_data"]
    finalize_function = column_data["finalize_function"]
    #user_data = column_data["user_data"]
    handle["chain_tree"].Vo.run_one_shot_function(finalize_function,handle,node)



def cfl_mark_sequence(handle,node):
    chain_tree = handle["chain_tree"]
    node_dict = node["node_dict"]
    chain_tree.sequence_storage.append_results(node_dict["parent_node_name"],node["label_dict"]["ltree_name"],
                                               node_dict["result"],node_dict["data"])

    




def cfl_for_init(handle,node):

    node_data = node["node_dict"]
    node_data["current_index"] = 0
    links = node["label_dict"]["links"]
    if len(links) > 1:
        raise Exception("For column with multiple links is not supported")
    link = links[0]
    ct_engine = handle["ct_engine"]
    ct_engine.reset_node_id(link)

def cfl_for_term(handle,node):
    pass
    
    
def cfl_while_init(handle,node):
    
    node_data = node["node_dict"]
    node_data["current_index"] = 0
    links = node["label_dict"]["links"]
    if len(links) > 1:
        raise Exception("While column with multiple links is not supported")
    link = links[0]
    ct_engine = handle["ct_engine"]
    ct_engine.reset_node_id(link)
    
def cfl_while_term(handle,node):
    pass
    
def cfl_enable_watch_dog(handle,node):
    node_data = node["node_dict"]
    wd_node_id = node_data["node_id"]
    wd_node = handle["chain_tree"].python_dict[wd_node_id]
    node_dict = wd_node["node_dict"]
    node_dict["enabled"] = True
    node_dict["state_change"] = True
    
    
def cfl_disable_watch_dog(handle,node):
    node_data = node["node_dict"]
    wd_node_id = node_data["node_id"]
    wd_node = handle["chain_tree"].python_dict[wd_node_id]
    node_dict = wd_node["node_dict"]
    node_dict["enabled"] = False
    
def cfl_pat_watch_dog(handle,node): 
    node_data = node["node_dict"]
    wd_node_id = node_data["node_id"]
    wd_node = handle["chain_tree"].python_dict[wd_node_id]
    node_dict = wd_node["node_dict"]
    node_dict["current_time_count"] = handle["chain_tree"].ct_timer.get_timestamp() + node_dict["wd_time_count"]
    
def cfl_watch_dog_init(handle,node):
    wd_data = node["node_dict"]
    wd_data["enabled"] = False
    wd_data["state_change"] = False
    
    
def cfl_watch_dog_term(handle,node):
    pass

    
    
def cfl_supervisor_init(handle,node):
    ct_engine = handle["ct_engine"]
    chain_tree = handle["chain_tree"]
    
    supervisor_data = node["node_dict"]["column_data"]["supervisor_data"]
    supervisor_data["failure_counter"] = chain_tree.create_supervisor_failure_counter(supervisor_data["max_reset_number"],
                                                                                   supervisor_data["reset_window"])
    
    label_dict = node["label_dict"]
    links = label_dict["links"]
    ltree_name = label_dict["ltree_name"]
    sequence_data = chain_tree.sequence_storage.get_sequence_element(ltree_name)
    sequence_data["processed"] = True
    
    sequence_data["results"] = []
    for link in links:
        sequence_data["results"].append({"element_id":link,"final_status":True,"reset_counts":0})
    sequence_data["overal_status"] = True
    sequence_data["results_length"] = len(links)
    sequence_data["failed_element"] = 0
    sequence_data["finalized_results"] = {}
    
    for link in links:
            ct_engine.reset_node_id(link)
    
def cfl_supervisor_term(handle,node):
   
    chain_tree = handle["chain_tree"]
    supervisor_data = node["node_dict"]["column_data"]["supervisor_data"]
    chain_tree.Vo.run_one_shot_function(supervisor_data["finalize_function"],handle,node)
    
def cfl_define_df_token(handle,node):
    node_dict = node["node_dict"]
    handle["chain_tree"].token_dictionary.define_token(node_dict["token_id"],node_dict["token_description"])
   
def cfl_set_df_token(handle,node):
    
    node_dict = node["node_dict"]
    handle["chain_tree"].token_dictionary.set_token(node_dict["token_id"],node_dict["event_data"])

def cfl_clear_df_token(handle,node):

    node_dict = node["node_dict"]
    handle["chain_tree"].token_dictionary.clear_token(node_dict["token_id"],node_dict["event_data"])

def cfl_disable_links(handle,node):
    ct_engine = handle["ct_engine"]
    label_dict = node["label_dict"]
    links = label_dict["links"]
    for link in links:
        ct_engine.terminate_node_id(link)
        
def cfl_df_mask_init(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    
    data_flow_data = node["node_dict"]["column_data"]["data_flow_data"]
    event_list = data_flow_data["event_list"]
    event_mask = chain_tree.token_dictionary.generate_event_mask(event_list)
    data_flow_data["event_mask"] = event_mask
    data_flow_data["status"] = False
    

def cfl_df_mask_term(handle,node):
    pass

def cfl_df_expression_init(handle,node):
    chain_tree = handle["chain_tree"]
    node_dict = node["node_dict"]
    column_data = node_dict["column_data"]
    column_data["data_flow_data"]["current_trigger_count"] = 0
    s_expression = column_data["data_flow_data"]["event_expression"]
    rt_check = chain_tree.token_dictionary.validate_syntax_with_tokens(s_expression)
    if rt_check == False:
        raise ValueError(f"Invalid s-expression with syntax and tokens check: {s_expression}")
    status = handle["chain_tree"].token_dictionary.evaluate_expression(s_expression)
    column_data["data_flow_data"]["status"] = status
    if status == True:
        cfl_enable_links(handle,node)
    

        


def cfl_df_expression_term(handle,node):
    pass
    

    


def cfl_variable_template_init(handle,node):
    chain_tree = handle["chain_tree"]
    load_function_name = node["node_dict"]["load_function_name"]
    chain_tree.Vo.run_one_shot_function(load_function_name,handle,node)
    cfl_use_template_init(handle,node)
    
def cfl_use_template_init(handle,node):
    
    chain_tree = handle["chain_tree"]
    template_list = node["node_dict"]["template_list"]
    node["label_dict"]["links"] = []
    node["node_dict"]["output_data_dict"] = {}
    node["node_dict"]["input_data_dict"] = {}
    node["node_dict"]["shorted_name_dict"] = {}
    
    for items in template_list:
        template_name = items[0]
        initial_conditions = items[1]
        shorted_name,output_data,input_data = chain_tree.template_functions.install_template(node, template_name,initial_conditions)
        node["node_dict"]["shorted_name_dict"][shorted_name] = template_name
        node["node_dict"]["output_data_dict"][shorted_name] = output_data
        node["node_dict"]["input_data_dict"][shorted_name] = input_data
        link_node_id = node["label_dict"]["links"][-1]
        link_node = chain_tree.python_dict[link_node_id]
        link_node["ct_control"]["enabled"] = True
        link_node["ct_control"]["initialized"] = False



       
def cfl_variable_template_term(handle,node):
    cfl_use_template_term(handle,node)
  

        
def cfl_use_template_term(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    
    finalize_function_name = node["node_dict"]["finalize_function_name"]
    chain_tree.Vo.run_one_shot_function(finalize_function_name,handle,node)
    for link in node["label_dict"]["links"]:
        ct_engine.terminate_node_id(link)
        chain_tree.template_functions.uninstall_instanciated_template(link)

    
 
    
def cfl_exception_catch_init(handle,node):
    chain_tree = handle["chain_tree"]
    chain_tree.exception_catch_storage.add_exception_handler(node)
    cfl_auto_start_links(handle,node)
    
    
def cfl_exception_catch_term(handle,node):
    chain_tree = handle["chain_tree"]
    chain_tree.exception_catch_storage.rm_exception_handler(node)
    cfl_disable_links(handle,node)

def cfl_raise_exception(handle,node):
    
    
    chain_tree = handle["chain_tree"]
    exception_id = node["node_dict"]["exception_id"]
    exception_data = node["node_dict"]["exception_data"]
    chain_tree.exception_catch_storage.raise_exception(node,exception_id,exception_data)
    
    
def cfl_turn_heartbeat_on(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    node_data = node["node_dict"]
    exception_catch_ltree_name = chain_tree.exception_catch_storage.find_nearest_exception_handler(node)
    if exception_catch_ltree_name is None:
        raise KeyError(f"No exception handler found for node {node['label_dict']['ltree_name']}")
    chain_tree.send_system_named_event(exception_catch_ltree_name,
                                        "CFL_HEARTBEAT_ENABLE",
                                        {"parent_node_name":node_data["parent_node_name"],"time_out":node_data["time_out"]})
   
        

    
    
def cfl_turn_heartbeat_off(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    node_data = node["node_dict"]
    exception_catch_ltree_name = chain_tree.exception_catch_storage.find_nearest_exception_handler(node)
    if exception_catch_ltree_name is None:
        raise KeyError(f"No exception handler found for node {node['label_dict']['ltree_name']}")
    chain_tree.send_system_named_event(exception_catch_ltree_name,
                                        "CFL_HEARTBEAT_DISABLE",
                                        {"parent_node_name":node_data["parent_node_name"]})
    
def cfl_heartbeat_event(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    node_data = node["node_dict"]
    exception_catch_ltree_name = chain_tree.exception_catch_storage.find_nearest_exception_handler(node)
    if exception_catch_ltree_name is None:
        raise KeyError(f"No exception handler found for node {node['label_dict']['ltree_name']}")
    chain_tree.send_system_named_event(exception_catch_ltree_name,
                                        "CFL_HEARTBEAT_EVENT",
                                        {"parent_node_name":node_data["parent_node_name"]})
    
    


def cfl_s_node_control_init(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = chain_tree.ct_engine
    
    
    
    links = node["label_dict"]["links"]
    for link in links:
        ct_engine.terminate_node_id(link)
    
    s_data = node["node_dict"]["column_data"]["s_data"]
    s_dict = json.loads(s_data["s_dict"])
    node["node_dict"]["column_data"]["s_data"]["s_dict"] = s_dict

    local_nodes = node["node_dict"]["column_data"]["local_nodes"]
    for node_name in local_nodes.keys():
        local_node = local_nodes[node_name]
        local_node["enabled"] = True
        local_node["initialized"] = False
     
    
    
    s_data = node["node_dict"]["column_data"]["s_data"]

    return_value = chain_tree.s_lisp_engine.run_lisp_instruction(node, s_data["s_dict"],"CFL_INIT_EVENT",{})
    
def cfl_s_node_control_term(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    
    
    
    links = node["label_dict"]["links"]
    for link in links:
        ct_engine.terminate_node_id(link)

    s_data = node["node_dict"]["column_data"]["s_data"]

    # NEW (FIXED) - use run_lisp_instruction instead
    return_value = chain_tree.s_lisp_engine.run_lisp_instruction(node, s_data["s_dict"], "CFL_INIT_EVENT", {})
    ct_engine.terminate_s_nodes(node["node_dict"]["column_data"])
    
    
def cfl_terminate_state_machine(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    state_machine_node_id = node["node_dict"]["sm_node_id"]
    ct_engine.terminate_state_machine_node(state_machine_node_id)
    
def cfl_reset_state_machine(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    state_machine_node_id = node["node_dict"]["sm_node_id"]
    ct_engine.reset_state_machine_node(state_machine_node_id)