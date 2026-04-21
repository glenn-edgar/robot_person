

from chain_tree_run.ct_run.execution_sequencer import ExecutionSequencer


class MyUserFunctions:
    
    def __init__(self,execution_sequencer:ExecutionSequencer):
        
        self.es = execution_sequencer
        self.es.add_one_shot_function("LOAD_TEMPLATE_DATA",load_template_data,description="Loads the template data")
        self.es.add_one_shot_function("WAIT_FOR_EVENT_ERROR",wait_for_event_error,description="Waits for an event error")
        self.es.add_one_shot_function("ACTIVATE_VALVE",activate_valve,description="Activates a valve")
        self.es.add_one_shot_function("VERIFY_ERROR",verify_error,description="Verifies an error")
        self.es.add_one_shot_function("DISPLAY_SEQUENCE_RESULT",display_sequence_result,description="Displays the sequence result")
        self.es.add_boolean_function("WHILE_TEST",while_test,description="While test")
        self.es.add_one_shot_function("WATCH_DOG_TIME_OUT",watch_dog_time_out,description="Watch dog time out")
        self.es.add_one_shot_function("DISPLAY_FAILURE_WINDOW_RESULT",display_failure_window_result,
                                       description="Displays the failure window result")
        self.es.add_boolean_function("DF_EXPRESSION",df_expression,description="Data flow expression")
        self.es.add_boolean_function("DF_MASK",df_mask,description="Data flow mask")
        self.es.add_one_shot_function("SET_TEMPLATE_OUTPUT_DATA",set_template_output_data,description="Sets the template output data")
    
        self.es.add_one_shot_function("FINALIZE_TEMPLATE_RESULTS",finalize_template_results,description="Finalizes the template results")
    
        self.es.add_one_shot_function("MY_EXCEPTION_LOGGING",my_exception_logging,description="Exception logging")
    
        self.es.add_boolean_function("MY_EXCEPTION_DISPATCHER",my_exception_dispatcher,description="My exception dispatcher")
        self.es.add_boolean_function("MY_TOP_EXCEPTION_DISPATCHER",my_top_exception_dispatcher,description="My top exception dispatcher")
        self.es.add_one_shot_function("GET_TEMPLATE_INPUT_DATA",get_template_input_data,description="Gets the template input data")
        
        


def load_template_data(handle,node):
    print("LOAD_TEMPLATE_DATA")
    print("node",node["node_dict"])
    node["node_dict"]["template_list"] = node["node_dict"]["load_function_data"]["template_list"]
    
def my_exception_logging(handle,node):
    event_id = node["node_dict"]["event_type"]
    if event_id == "CFL_EXCEPTION_EVENT":
        print("\n\n************** LOGGING EXCEPTION **************")
        
        
        chain_tree = handle["chain_tree"]
        node_data = node["node_dict"]
        column_data = node_data["column_data"]
        print("logging function data",column_data["logging_function_data"])
        exception_data = node_data["exception_data"]
        print("exception_data",exception_data)

        exception_link = chain_tree.exception_catch_storage.find_exception_link(node,exception_data["source_node_id"])
        if exception_link is None:
            raise ValueError("No exception link found")
        print("exception_link",exception_link)
        
        exeption_id = exception_data["exception_id"]
        if exeption_id not in column_data["exception_list"]:
            print("exception_id not in exception_list")
        else:
            print("exception_id in exception_list")
        if exception_link in column_data["recovery_dict"]:
    
            print("exception_link in recovery_dict")
            disable_columns = column_data["recovery_dict"][exception_link]["disable_columns"]
            enable_columns = column_data["recovery_dict"][exception_link]["enable_columns"]
            for column in disable_columns:
                print("exception termination link",column)
            for column in enable_columns:
                print("exception recovery link",column)
        else:
            print("exception_link not in recovery_dict")
        print("************** LOGGING EXCEPTION **************\n\n")
        return
    if event_id == "CFL_HEARTBEAT_TIMEOUT":
        print("**************** LOGGING HEARTBEAT TIMEOUT ****************")
        node_data = node["node_dict"]
        failed_node_id = node_data["failed_node_id"]
        print("failed_node_id",failed_node_id)
        time_out = node_data["time_out"]
        print("time_out",time_out)
        return
    print("Unrecognized event",event_id)

def my_top_exception_dispatcher(handle,node,event_id,event_data):
    if event_id == "CFL_INIT_EVENT":
        return False
    if event_id == "CFL_TERM_EVENT":
        return False
    if event_id == "CFL_EXCEPTION_EVENT":
        print(f"TOP EXCEPTION DISPATCHER: {event_id}")
        exception_id = event_data["exception_id"]
        exception_data = event_data["exception_data"]
        exception_source_node_id = event_data["source_node_id"]
        print("exception_source_node_id",exception_source_node_id)
        print("exception_id",exception_id)
        print("exception_data",exception_data)
        print("exception has been handled")
        return True
    if event_id == "CFL_HEARTBEAT_TIMEOUT":
        print(f"TOP EXCEPTION DISPATCHER For Heartbeat Timeout: {event_id}")
        print("heartbeat timeout has been handled")
        return True
    print("Unhandled event",event_id)
    return False
def my_exception_dispatcher(handle,node,event_id,event_data):
    if event_id == "CFL_INIT_EVENT":
        return False
    if event_id == "CFL_TERM_EVENT":
        return False
    if event_id == "CFL_EXCEPTION_EVENT":
        print(f"SPECIAL EXCEPTION DISPATCHER: {event_id}")
        exception_id = event_data["exception_id"]
        exception_data = event_data["exception_data"]
        exception_source_node_id = event_data["source_node_id"]
        print("exception_source_node_id",exception_source_node_id)
        print("exception_id",exception_id)
        print("exception_data",exception_data)
        
        return False  
    if event_id == "CFL_HEARTBEAT_TIMEOUT":
        print(f"EXCEPTION DISPATCHER For Heartbeat Timeout: {event_id}")
        
        return False
    print("Unhandled event",event_id)
    return False

def set_template_output_data(handle,node):

    input_data = handle["chain_tree"].template_functions.get_template_input_data(node)

    output_data = {"node":node["label_dict"]["ltree_name"],"output_data":"output_data"}
    handle["chain_tree"].template_functions.set_template_output_data(node,output_data)
    

def finalize_template_results(handle,node):
    print("FINALIZE_TEMPLATE_RESULTS")
    finalize_function_data = node["node_dict"]["finalize_function_data"]
    print("finalize_function_data",finalize_function_data)
    
    for shorted_name in node["node_dict"]["output_data_dict"]:
        print("shorted_name",shorted_name)
        input_data = node["node_dict"]["input_data_dict"][shorted_name]
        print("input_data",input_data)
        output_data = node["node_dict"]["output_data_dict"][shorted_name]
        print("output_data",output_data)

 
def df_expression(handle,node,event_id,event_data):
    if event_id == "CFL_INIT_EVENT":
        return True
    if event_id == "CFL_TERM_EVENT":
        return True
    return True

def df_mask(handle,node,event_id,event_data):
    raise Exception("DF_MASK is not implemented")

def display_failure_window_result(handle,node):
    chain_tree = handle["chain_tree"]
    supervisor_data = node["node_dict"]["column_data"]["supervisor_data"]
    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@  reset_number_failure",supervisor_data["reset_number_failure"])
    if supervisor_data["reset_number_failure"] == True:
        failure_counts = {}
        for index,link in enumerate(chain_tree.python_dict[node["label_dict"]["ltree_name"]]["label_dict"]["links"]):
            
            failure_counts[link] = chain_tree.sequence_storage.get_index_result(node["label_dict"]["ltree_name"],index)["reset_counts"]
        chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],False,0,failure_counts)
    else:
        chain_tree.sequence_storage.set_overall_status(node["label_dict"]["ltree_name"],True,0,{})
    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@  overall_status",chain_tree.sequence_storage.get_overall_status(node["label_dict"]["ltree_name"]))
    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@  finalized_results",chain_tree.sequence_storage.get_finalized_results(node["label_dict"]["ltree_name"]))
def activate_valve(handle, node):
    print("Activating valve")

def wait_for_event_error(handle,node):
    node_data = node["node_dict"]
    error_message = node_data["error_data"]["error_message"]
    print(f"Error message: {error_message}")
    
def verify_error(handle,node):
    node_data = node["node_dict"]
    error_message = node_data["error_data"]["failure_data"]
    print(f"****************Error message: {error_message}")

def display_sequence_result(handle,node):
    chain_tree = handle["chain_tree"]
    ct_engine = handle["ct_engine"]
    node_id = node["label_dict"]["ltree_name"]
    print("node_id",node_id)

    json_data = chain_tree.sequence_storage.collect_to_json(node_id,lambda node: True)
    print("json_data",json_data)
    collected_list = chain_tree.sequence_storage.collect_to_list(node_id,lambda node: True)
    print("collected_list")
    for item in collected_list:
        print(item)

def while_test(handle,node,event_id,event_data):
    if event_id == "CFL_INIT_EVENT":
        node["node_dict"]["user_data"]["current_index"] = 0
        return True
    current_index = node["node_dict"]["user_data"]["current_index"] + 1
    if current_index >= node["node_dict"]["user_data"]["count"]:
        return False
    node["node_dict"]["user_data"]["current_index"] = current_index
    return True

def watch_dog_time_out(handle,node):
    node_data = node["node_dict"]
    wd_fn_data = node_data["wd_fn_data"]
    print(f"Watch dog time out: {wd_fn_data['message']}")
    return True

def get_template_input_data(handle,node):
    print("GET_TEMPLATE_INPUT_DATA")
    input_data =  handle["chain_tree"].template_functions.get_template_input_data(node)
    print("input_data",input_data)
    
if __name__ == "__main__":
    my_user_functions = MyUserFunctions()