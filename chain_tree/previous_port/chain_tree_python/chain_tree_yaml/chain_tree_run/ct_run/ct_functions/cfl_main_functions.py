from datetime import datetime, timezone
import time



class CFLMainFunctions:
    def __init__(self,virtual_main_functions):
        self.virtual_main_functions = virtual_main_functions
        self.main_functions = {}
        
        
    def load_main_functions(self):
        function_names = self.main_functions.keys()
        for function_name in function_names:
            self.virtual_main_functions.add_main_function_python(function_name,
                    self.main_functions[function_name]["python_function"],self.main_functions[function_name]["description"])
        
    
    def load_default_main_functions(self):
        self.main_functions["CFL_NULL"] = {
            "python_function": cfl_null,
            "description": "information node and should not be called",
            
        }
        self.main_functions["CFL_CONTINUE"] = {
            "python_function": cfl_continue,
            "description": "issue continue return code",
        
        }
        
        self.main_functions["CFL_HALT"] = {
            "python_function": cfl_halt,
            "description": "issue halt return code",
    
        }
        self.main_functions["CFL_RESET"] = {
            "python_function": cfl_reset,
            "description": "issue reset return code",
            
        }
        self.main_functions["CFL_DISABLE"] = {
            "python_function": cfl_disable,
            "description": "issue disable return code",
            
        }
        self.main_functions["CFL_TERMINATE"] = {
            "python_function": cfl_terminate,
            "description": "issue terminate return code",
            
        }
        self.main_functions["CFL_TERMINATE_SYSTEM"] = {
            "python_function": cfl_terminate_system,
            "description": "issue terminate engine return code",
            
        }
        self.main_functions["CFL_COLUMN_MAIN"] = {
            "python_function": cfl_column_main,
            "description": "column main function",
            
        }
        
        self.main_functions["CFL_ROOT_CHECK"] = {
            "python_function": cfl_root_check,
            "description": "determines when to terminate root node",
        
        }
        self.main_functions["CFL_WAIT_TIME"] = {
            "python_function": cfl_wait_time,
            "description": "initializes wait time",
        
        }
        self.main_functions["CFL_WAIT"] ={
            "python_function": cfl_wait,
            "description": "wait for attached aux function to return true",
            
        }
        self.main_functions["CFL_GATE_NODE_MAIN"] = {
            "python_function": cfl_gate_node_main,
            "description": "gate node main function",
            
        }
        self.main_functions["CFL_VERIFY"] = {
            "python_function": cfl_verify,
            "description": "verify function",
    
        }
        self.main_functions["CFL_EVENT_LOGGER"] = {
            "python_function": cfl_event_logger,
            "description": "event logger function",

        }
        self.main_functions["CFL_STATE_MACHINE_MAIN"] = {
            "python_function": cfl_state_machine_main,
            "description": "state machine main function",
            
        }
        self.main_functions["CFL_FORK_MAIN"] = {
            "python_function": cfl_fork_main,
            "description": "fork main function",
            
        }
        
        self.main_functions["CFL_JOIN_MAIN"] = {
            "python_function": cfl_join_main,
            "description": "join main function",
            
        }
        
        self.main_functions["CFL_SEQUENCE_START_MAIN"] = {
            "python_function": cfl_sequence_start_main,
            "description": "sequence start main function",
        
        }
        self.main_functions["CFL_SEQUENCE_PASS_MAIN"] = {
            "python_function": cfl_sequence_pass_main,
            "description": "sequence pass main function",
            
        }
        self.main_functions["CFL_SEQUENCE_FAIL_MAIN"] = {
            "python_function": cfl_sequence_fail_main,
            "description": "sequence fail main function",
        
        }
        self.main_functions["CFL_JOIN_SEQUENCE_ELEMENT"] = {
            "python_function": cfl_join_sequence_element,
            "description": "joins the sequence element",
        
        }
        self.main_functions["CFL_SUPERVISOR_MAIN"] = {
            "python_function": cfl_supervisor_main,
            "description": "supervisor node main function",
            
        }
        self.main_functions["CFL_FOR_MAIN"] = {
            "python_function": cfl_for_main,
            "description": "for main function",
            
        }
        self.main_functions["CFL_WHILE_MAIN"] = {
            "python_function": cfl_while_main,
            "description": "while main function",
            
        }
        self.main_functions["CFL_WATCH_DOG_MAIN"] = {
            "python_function": cfl_watch_dog_main,
            "description": "watch dog main function",
            
        }
        self.main_functions["CFL_DF_EXPRESSION_MAIN"] = {
            "python_function": cfl_df_expression_main,
            "description": "data flow expression main function",
            
        }
        self.main_functions["CFL_DF_MASK_MAIN"] = {
            "python_function": cfl_df_mask_main,
            "description": "data flow mask main function",
            
        }
        self.main_functions["CFL_USE_TEMPLATE_MAIN"] = {
            "python_function": cfl_use_template_main,
            "description": "use template main function",
        
        }
        self.main_functions["CFL_EXCEPTION_CATCH_MAIN"] = {
            "python_function": cfl_exception_catch_main,
            "description": "exception main function",
        
        }
        self.main_functions["CFL_S_NODE_CONTROL_MAIN"] = {
            "python_function": cfl_s_node_control_main,
            "description": "s node control main function",
        }
        
        self.load_main_functions()
        

def cfl_null(auxiliary_function,handle, node,event_id,event_data):
    label_dict = node["label_dict"]
    raise Exception("This is an information node and should not be called")

def cfl_halt(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_HALT"

def cfl_reset(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_RESET"

def cfl_disable(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_DISABLE"
        
def cfl_continue(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_CONTINUE"

def cfl_reset(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_RESET"

def cfl_terminate(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_TERMINATE"

def cfl_terminate_system(auxiliary_function,handle, node,event_id,event_data):
    return "CFL_TERMINATE_SYSTEM"

def cfl_column_main(aux_function,handle, node,event_id,event_data):
    
    
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    #print("cfl_column_main", node["label_dict"]["ltree_name"],event_id,event_data)
    return_code = cfl_root_check(aux_function,handle, node,event_id,event_data)
    #print("cfl_column_main", node["label_dict"]["ltree_name"],return_code)
    return return_code
    
        
def cfl_fork_main(auxiliary_function,handle, node,event_id,event_data):
    return cfl_column_main(auxiliary_function,handle, node,event_id,event_data)
    
        
def cfl_join_main(aux_function,handle, node,event_id,event_data):
    chain_tree = handle["chain_tree"]
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    parent_node_name = node["node_dict"]["parent_node_name"]
    parent_node = chain_tree.python_dict[parent_node_name]
    if parent_node["ct_control"]["enabled"] == True:
        return "CFL_HALT"
    return "CFL_DISABLE"
    
    
        
def cfl_gate_node_main(aux_function,handle, node,event_id,event_data):
    
    
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    return_code = cfl_root_check(aux_function,handle, node,event_id,event_data)
    return return_code

def cfl_root_check(aux_function,handle, node,event_id,event_data):
    
    ct_engine = handle["ct_engine"]
    label_dict = node["label_dict"]
    links = label_dict["links"]
    for link in links:
        
        if ct_engine.node_id_enabled(link) == True:
            
            return "CFL_CONTINUE"
    
    return "CFL_DISABLE"

def cfl_root_join_check(aux_function,handle, node,event_id,event_data):
    
    ct_engine = handle["ct_engine"]
    label_dict = node["label_dict"]
    links = label_dict["links"]
    for link in links:
        
        if ct_engine.node_id_enabled(link) == True:
            
            return "CFL_HALT"
    
    return "CFL_DISABLE"


def cfl_wait_time(aux_function,handle, node,event_id,event_data):
    
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    if event_id != "CFL_TIMER_EVENT":
        return "CFL_HALT"
    node_data = node["node_dict"]
    start_time = node_data["start_time"]
    
    current_time = handle["chain_tree"].ct_timer.get_timestamp()
    
    if current_time - start_time >= node_data["time_delay"]:
        
        return "CFL_DISABLE"
    
    return "CFL_HALT"


def cfl_wait(aux_function,handle, node,event_id,event_data):
    
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    
    wait_ctrl = node["node_dict"]["wait_ctrl"]
    if wait_ctrl["terminal_count"] is None:
        return "CFL_HALT"
    if event_id == wait_ctrl["tm_out_event"]:
        
        wait_ctrl["current_time_count"] = wait_ctrl["current_time_count"] + 1
        if wait_ctrl["current_time_count"] >= wait_ctrl["terminal_count"]:
            error_function = node["node_dict"]["error_function"]
            if error_function is not None:
                handle["chain_tree"].Vo.run_one_shot_function(error_function,handle,node)
            
            if node["node_dict"]["reset_flag"] == True:
                return "CFL_RESET"
            
            return "CFL_TERMINATE"
    return "CFL_HALT"
    
    
def cfl_verify(aux_function,handle, node,event_id,event_data):
    
    result = aux_function(handle, node,event_id,event_data)
     
    if result == False:
        error_function = node["node_dict"]["error_function"]
        if error_function is not None:
            handle["chain_tree"].Vo.run_one_shot_function(error_function,handle,node)
        if node["node_dict"]["reset_flag"] == True:
                return "CFL_RESET"
        
        return "CFL_TERMINATE"
    return "CFL_CONTINUE"


def cfl_event_logger(aux_function,handle, node,event_id,event_data):
    #print("*************************************cfl_event_logger", node["label_dict"]["ltree_name"],event_id,event_data)
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    
    event_list = node["node_dict"]["events"]
    message = node["node_dict"]["message"]
    ltree_name = node["label_dict"]["ltree_name"]
    
    for event in event_list:
        if event == event_id:
            utc_time = datetime.utcnow()
            timestamp = (utc_time.timestamp())
            readable = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[{timestamp}] ++++++++++ node id: {ltree_name} event id: {event_id} message: {message}")
    return "CFL_CONTINUE"

def cfl_state_machine_main(aux_function,handle, node,event_id,event_data):
        
        chain_tree = handle["chain_tree"]
        ct_engine = handle["ct_engine"]
        
        node["node_dict"]["state_change"] = False
        current_state = node["node_dict"]["current_state"]
        new_state = node["node_dict"]["new_state"]
        if current_state != new_state:
            node["node_dict"]["current_state"] = new_state
            state_names = node["label_dict"]["state_names"]
            state_links = node["label_dict"]["state_links"]
            old_state_number = chain_tree.find_state_number(current_state,state_names)
            old_node_id = state_links[old_state_number]
            for link in state_links:
                ct_engine.terminate_node_tree(link)
            new_state_number = chain_tree.find_state_number(new_state,state_names)
            new_node_id = state_links[new_state_number]
        
            ct_engine.enable_node_id(new_node_id)
            node["node_dict"]["state_change"] = True
            
        if aux_function(handle, node,event_id,event_data) == False:
             return "CFL_SKIP_CONTINUE"
        
        return_code = cfl_root_check(aux_function,handle, node,event_id,event_data)
        #print("cfl_column_main", node["label_dict"]["ltree_name"],return_code)
        if return_code == "CFL_TERMINATE":
            return "CFL_TERMINATE"
        return return_code
        


def cfl_terminate_one_for_one(ct_engine,active_mask,links):
    return_value = True
    for i in range(len(active_mask)):
        if active_mask[i] == False:

            ct_engine.reset_node_id(links[i])
            return_value = False
    return return_value

def cfl_terminate_one_for_all(ct_engine,active_mask,links):
    return_value = True
    for i in range(len(active_mask)):
        if active_mask[i] == False:
            return_value = False
    if return_value == False:
        for i in range(len(links)):
            
            ct_engine.reset_node_id(links[i])
    return return_value

def cfl_terminate_rest_for_all(ct_engine,active_mask,links):
    return_value = True
    for i in range(len(active_mask)):
        if return_value == False:
            active_mask[i] = False
        else:
            if ct_engine.node_id_enabled(links[i]) == False:
                return_value = False
    for i in range(len(links)):
        if active_mask[i] == False:
        
            ct_engine.reset_node_id(links[i])
    return return_value
           
           
            
def cfl_supervisor_main(aux_function,handle, node,event_id,event_data):

    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    supervisor_data = node["node_dict"]["column_data"]["supervisor_data"]
    failure_counter = supervisor_data["failure_counter"]
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    

    active_mask = []
    ltree_name = node["label_dict"]["ltree_name"]
    links = node["label_dict"]["links"]
    node_dict = node["node_dict"]
    for index, link in enumerate(links):
        
        if chain_tree.python_dict[link]["ct_control"]["enabled"] == False:
            failure_counter.record_failure()
            active_mask.append(False)
            result = chain_tree.sequence_storage.get_index_result(ltree_name,index)
            result["reset_counts"] = result["reset_counts"] + 1
            chain_tree.sequence_storage.modify_index_results(ltree_name,index,result)

        else:
            active_mask.append(True)
            failure_counter.record_success()
    
    termination_type = supervisor_data["termination_type"]
    if termination_type == "ONE_FOR_ONE":
        cfl_terminate_one_for_one(ct_engine,active_mask,links)
    elif termination_type == "ONE_FOR_ALL":
        cfl_terminate_one_for_all(ct_engine,active_mask,links)
    elif termination_type == "REST_FOR_ALL":
        cfl_terminate_rest_for_all(ct_engine,active_mask,links)
    if supervisor_data["reset_limited_enabled"] == True and failure_counter.is_threshold_exceeded():
        supervisor_data["reset_number_failure"] = True
        return "CFL_DISABLE"
    else:
        supervisor_data["reset_number_failure"] = False
    return "CFL_CONTINUE"

                
                
                
def cfl_sequence_start_main(aux_function,handle, node,event_id,event_data):
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    
    return "CFL_CONTINUE"


def cfl_sequence_fail_main(aux_function,handle, node,event_id,event_data):
    return cfl_common_sequence_main(False,aux_function,handle, node,event_id,event_data)

def cfl_sequence_pass_main(aux_function,handle, node,event_id,event_data):
    return cfl_common_sequence_main(True,aux_function,handle, node,event_id,event_data)

def cfl_common_sequence_main(status,aux_function,handle, node,event_id,event_data):
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    
    if event_id != "CFL_TIMER_EVENT":
        
        return "CFL_CONTINUE"
    ltree_name = node["label_dict"]["ltree_name"]
    kb_list = ltree_name.split('.')
    kb = kb_list[1]
    chain_tree = handle["chain_tree"]
    current_index = node["sequence_data"]["current_index"]
    current_link = node["label_dict"]["links"][current_index]
    current_link_data = chain_tree.python_dict[current_link]
    if current_link_data["ct_control"]["enabled"] == False:
       sequence_element = chain_tree.sequence_storage.sequence_data[kb][node["label_dict"]["ltree_name"]]
       last_result = sequence_element["results"][-1]
    
       
       if last_result["status"] == status:
           #wrap up processing and terminate
           chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],True,current_index)
           return "CFL_TERMINATE"
       else:
           
           if current_index == node["sequence_data"]["number_of_links"]:
               chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],False,current_index)
               return "CFL_TERMINATE"
           else:
               ct_engine = handle["ct_engine"]
               current_index = current_index + 1
               current_link = node["label_dict"]["links"][current_index]
               node["sequence_data"]["current_index"] = current_index
               ct_engine.reset_node_id(current_link)
               return "CFL_CONTINUE"
    return "CFL_CONTINUE"
    


def cfl_join_sequence_element(aux_function,handle, node,event_id,event_data):
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    
    chain_tree = handle["chain_tree"]
    parent_node_name = node["node_dict"]["parent_node_name"]
    parent_node = chain_tree.python_dict[parent_node_name]
    if parent_node["ct_control"]["enabled"] == True:
        return "CFL_HALT"
    
    return "CFL_DISABLE"
    
def cfl_for_main(aux_function,handle, node,event_id,event_data):
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    
    links = node["label_dict"]["links"]
    link = links[0]
    
    link_node = handle["chain_tree"].python_dict[link]
    if link_node["ct_control"]["enabled"] == True:
        return "CFL_CONTINUE"
    current_index = node["node_dict"]["current_index"] +1
    if current_index == node["node_dict"]["number_of_iterations"]:
        return "CFL_TERMINATE"
    
    node["node_dict"]["current_index"] = current_index
    ct_engine = handle["ct_engine"]
    ct_engine.reset_node_id(link)
    return "CFL_CONTINUE"


def cfl_while_main(aux_function,handle, node,event_id,event_data):
    
    links = node["label_dict"]["links"]
    link = links[0]
    
    link_node = handle["chain_tree"].python_dict[link]
    if link_node["ct_control"]["enabled"] == True:
        return "CFL_CONTINUE"
   
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    ct_engine = handle["ct_engine"]
    ct_engine.reset_node_id(link)
    return "CFL_CONTINUE"


def cfl_watch_dog_main(aux_function,handle,node,event_id,event_data):
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    if event_id !="CFL_TIMER_EVENT":
        return "CFL_CONTINUE"

    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    node_dict = node["node_dict"]
    if node_dict["enabled"] == False:
        return "CFL_CONTINUE"
    if node_dict["state_change"] == True:
        node_dict["state_change"] = False

        node_dict["current_time_count"] = chain_tree.ct_timer.get_timestamp() + node_dict["wd_time_count"]
        return "CFL_CONTINUE"
    
    if node_dict["current_time_count"] <= chain_tree.ct_timer.get_timestamp():
        if node_dict["wd_fn"] != None:
            handle["chain_tree"].Vo.run_one_shot_function(node_dict["wd_fn"],handle,node)
        if node_dict["wd_reset"] == True:
            return "CFL_RESET"
        else:
            return "CFL_TERMINATE"
    return "CFL_CONTINUE"


def cfl_df_expression_main(aux_function,handle,node,event_id,event_data):
    
    ct_engine = handle["ct_engine"]
    chain_tree = handle["chain_tree"]
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    data_flow_data = node["node_dict"]["column_data"]["data_flow_data"]
    
    if event_id == data_flow_data["trigger_event"]:
        data_flow_data["current_trigger_count"] = data_flow_data["current_trigger_count"] + 1
        if data_flow_data["current_trigger_count"] >= data_flow_data["trigger_event_count"]:
            data_flow_data["current_trigger_count"] = 0
            new_status = handle["chain_tree"].token_dictionary.evaluate_expression(data_flow_data["event_expression"])
            

            if data_flow_data["status"] == True:
                # chain flow links are active
                if new_status == False:
                    links = node["label_dict"]["links"]
                    for link in links:
                        ct_engine.terminate_node_id(link)
                    data_flow_data["status"] = False
            else:
                # chain flow links are not active
                if new_status == True:
                    links = node["label_dict"]["links"]
                    for link in links:
                        ct_engine.reset_node_id(link)
                    data_flow_data["status"] = True
            
    return "CFL_CONTINUE"
        

def cfl_df_mask_main(aux_function,handle,node,event_id,event_data):
    ct_engine = handle["ct_engine"]
    chain_tree = handle["chain_tree"]
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    data_flow_data = node["node_dict"]["column_data"]["data_flow_data"]
    if event_id == "CFL_TIMER_EVENT":
        node_event_mask = data_flow_data["event_mask"]
        event_event_mask = event_data["event_mask"]
       
        if node_event_mask & event_event_mask == node_event_mask:
            if data_flow_data["status"] == False:
                
                links = node["label_dict"]["links"]
                for link in links:
                    ct_engine.reset_node_id(link)
                data_flow_data["status"] = True
        else:
                if data_flow_data["status"] == True:
                    
                    links = node["label_dict"]["links"]
                    for link in links:
                        ct_engine.terminate_node_id(link)
                    data_flow_data["status"] = False
    return "CFL_CONTINUE"
    
def cfl_use_template_main(aux_function,handle,node,event_id,event_data):

    return_value = "CFL_CONTINUE"
    chain_tree = handle["chain_tree"]
    if aux_function(handle, node,event_id,event_data) == False:
        return_value = "CFL_TEMPLATE_UNLOAD"
    else:
        return_code = cfl_root_check(aux_function,handle, node,event_id,event_data)
        if return_code == "CFL_DISABLE":
            return_value = "CFL_TEMPLATE_UNLOAD"
    if return_code == "CFL_TEMPLATE_UNLOAD":
       for link in node["label_dict"]["links"]:
            chain_tree.template_functions.uninstall_instanciated_template(link)
    return return_value




def cfl_exception_catch_main(aux_function, handle, node, event_id, event_data):
    """Main entry point for CFL exception and event handling."""
    # Define event categories
    HEARTBEAT_EVENTS = {"CFL_HEARTBEAT_EVENT", "CFL_HEARTBEAT_ENABLE", "CFL_HEARTBEAT_DISABLE"}
    EXCEPTION_EVENT = "CFL_EXCEPTION_EVENT"
    TIMER_EVENT = "CFL_TIMER_EVENT"
    
    # Handle heartbeat-specific events
    if event_id in HEARTBEAT_EVENTS:
        return handle_heartbeat_event(handle, node, event_id, event_data)
    
    # Handle exception events
    if event_id == EXCEPTION_EVENT:
        return handle_exception_event(handle, node, event_id, event_data)
    
    # For all other events (including TIMER_EVENT):
    # First handle heartbeat monitoring for timer events
    if event_id == TIMER_EVENT:
        handle_heartbeat_event(handle, node, event_id, event_data)
    
    # Then check root and return its result
    return_code = cfl_root_check(aux_function, handle, node, event_id, event_data)
    return return_code


def handle_heartbeat_event(handle, node, event_id, event_data):
    """Handle heartbeat enable, disable, event, and timer events."""
    chain_tree = handle["chain_tree"]
    node_dict = node["node_dict"]
    
    if event_id == "CFL_HEARTBEAT_ENABLE":
        _enable_heartbeat(node_dict, event_data, chain_tree)
    
    elif event_id == "CFL_HEARTBEAT_DISABLE":
        _disable_heartbeat(node_dict, event_data)
    
    elif event_id == "CFL_HEARTBEAT_EVENT":
        _update_heartbeat(node_dict, event_data, chain_tree)
    
    elif event_id == "CFL_TIMER_EVENT":
        _check_heartbeat_timeouts(handle, node, event_data)
    
    return "CFL_CONTINUE"


def _initialize_heartbeat_storage(node_dict):
    """Initialize heartbeat storage dictionaries if they don't exist."""
    for key in ["heartbeat_status", "heartbeat_time_count", "heartbeat_time_out"]:
        if key not in node_dict:
            node_dict[key] = {}


def _enable_heartbeat(node_dict, event_data, chain_tree):
    """Enable heartbeat monitoring for a parent node."""
    _initialize_heartbeat_storage(node_dict)
    
    parent_node = event_data["parent_node_name"]
    timestamp = chain_tree.ct_timer.get_timestamp()
    
    node_dict["heartbeat_status"][parent_node] = True
    node_dict["heartbeat_time_count"][parent_node] = timestamp
    node_dict["heartbeat_time_out"][parent_node] = event_data["time_out"]


def _disable_heartbeat(node_dict, event_data):
    """Disable heartbeat monitoring for a parent node."""
    parent_node = event_data["parent_node_name"]
    
    node_dict["heartbeat_status"][parent_node] = False
    node_dict["heartbeat_time_count"][parent_node] = 0
    node_dict["heartbeat_time_out"][parent_node] = 0


def _update_heartbeat(node_dict, event_data, chain_tree):
    """Update the heartbeat timestamp for a parent node."""
    parent_node = event_data["parent_node_name"]
    
    if parent_node not in node_dict.get("heartbeat_status", {}):
        raise ValueError(f"Heartbeat status not found for node {parent_node}")
    
    node_dict["heartbeat_time_count"][parent_node] = chain_tree.ct_timer.get_timestamp()


def _check_heartbeat_timeouts(handle, node, event_data):
    """Check all active heartbeats for timeouts."""
    node_dict = node["node_dict"]
    
    if "heartbeat_status" not in node_dict:
        return
    
    chain_tree = handle["chain_tree"]
    current_time = chain_tree.ct_timer.get_timestamp()
    
    for parent_node, is_active in node_dict["heartbeat_status"].items():
        if not is_active:
            continue
        
        elapsed_time = current_time - node_dict["heartbeat_time_count"][parent_node]
        timeout_threshold = node_dict["heartbeat_time_out"][parent_node]
        
        if elapsed_time >= timeout_threshold:
            _handle_timeout(handle, node, parent_node, timeout_threshold, event_data)


def _handle_timeout(handle, node, parent_node, timeout_threshold, event_data):
    """Handle a heartbeat timeout for a specific node."""
    node_dict = node["node_dict"]
    
    # Reset heartbeat state
    node_dict["heartbeat_status"][parent_node] = False
    node_dict["heartbeat_time_count"][parent_node] = 0
    node_dict["failed_node_id"] = parent_node
    
    # Trigger timeout handler
    handle_heartbeat_timeout(parent_node, timeout_threshold, handle, node, 
                            "CFL_HEARTBEAT_TIMEOUT", event_data)
    
    # Clean up
    node_dict["failed_node_id"] = None


def handle_heartbeat_timeout(parent_node, time_out, handle, node, event_id, event_data):
    """Handle heartbeat timeout by logging and running exception handlers."""
    chain_tree = handle["chain_tree"]
    node_dict = node["node_dict"]
    column_data = node_dict["column_data"]
    
    # Prepare timeout context
    timeout_info = {"failed_node_id": parent_node, "time_out": time_out}
    node_dict["event_type"] = "CFL_HEARTBEAT_TIMEOUT"
    node_dict["time_out"] = time_out
    node_dict["failed_node_id"] = parent_node
    
    # Log the timeout
    chain_tree.Vo.run_one_shot_function(column_data["logging_function_name"], handle, node)
    
    # Run default exception handler
    handler_handled = chain_tree.Vb.run_boolean_function(
        column_data["default_exception_handler_name"],
        handle, node, "CFL_HEARTBEAT_TIMEOUT", timeout_info
    )
    
    if handler_handled:
        return "CFL_CONTINUE"
    
    # Raise exception if not handled
    chain_tree.exception_catch_storage.raise_exception(node, "CFL_HEARTBEAT_TIMEOUT", timeout_info)
    return "CFL_DISABLE"


def handle_exception_event(handle, node, event_id, event_data):
    """Handle exception events by logging and attempting recovery."""
    chain_tree = handle["chain_tree"]
    node_dict = node["node_dict"]
    column_data = node_dict["column_data"]
    
    # Extract exception details
    source_node_id = event_data["source_node_id"]
    exception_id = event_data["exception_id"]
    exception_data = event_data["exception_data"]
    
    # Store exception context
    node_dict["exception_data"] = {
        "source_node_id": source_node_id,
        "exception_id": exception_id,
        "exception_data": exception_data
    }
    node_dict["event_type"] = "CFL_EXCEPTION_EVENT"
    
    # Find exception link and log
    exception_link = chain_tree.exception_catch_storage.find_exception_link(node, source_node_id)
    event_data["exception_link"] = exception_link
    chain_tree.Vo.run_one_shot_function(column_data["logging_function_name"], handle, node)
    
    # Try default exception handler
    handler_params = {
        "source_node_id": source_node_id,
        "exception_id": exception_id,
        "exception_data": exception_data
    }
    
    handler_handled = chain_tree.Vb.run_boolean_function(
        column_data["default_exception_handler_name"],
        handle, node, "CFL_EXCEPTION_EVENT", handler_params
    )
    
    if handler_handled:
        return "CFL_CONTINUE"
    
    # Check if this exception type is handled by this catch node
    if exception_id not in column_data["exception_list"] or exception_link not in column_data["recovery_dict"][exception_link]["disable_columns"]:
        chain_tree.exception_catch_storage.raise_exception(node, exception_id, exception_data)
        return "CFL_DISABLE"
    
    # Validate exception link
    if exception_link is None:
        raise ValueError("No source node not in tree")
    
    # Execute recovery actions
    _execute_recovery_actions(chain_tree, column_data, exception_link)
    
    return "CFL_CONTINUE"


def _execute_recovery_actions(chain_tree, column_data, exception_link):
    """Execute the recovery actions for an exception."""
    recovery_config = column_data["recovery_dict"][exception_link]
    
    # Terminate disabled links
    for link in recovery_config["disable_columns"]:
        chain_tree.ct_engine.terminate_node_id(link)
    
    # Reset enabled links
    for link in recovery_config["enable_columns"]:
        chain_tree.ct_engine.reset_node_id(link)

def cfl_s_node_control_main(aux_function,handle,node,event_id,event_data):
    chain_tree = handle["chain_tree"]
    if aux_function(handle, node,event_id,event_data) == False:
        return "CFL_DISABLE"
    s_data = node["node_dict"]["column_data"]["s_data"]

    return_value = chain_tree.s_lisp_engine.run_lisp_instruction(node, s_data["s_dict"], event_id, event_data)
    if return_value == "CFL_FUNCTION_RETURN" or return_value == "CFL_FUNCTION_HALT":

        return "CFL_CONTINUE"
    if return_value == "CFL_FUNCTION_TERMINATE":
        return "CFL_TERMINATE"
    return return_value