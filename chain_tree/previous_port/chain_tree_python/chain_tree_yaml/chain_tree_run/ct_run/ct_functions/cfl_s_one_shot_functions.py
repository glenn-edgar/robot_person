from datetime import datetime, timezone
import time
import json

class CFLSOneShotFunctions:
    def __init__(self,virtual_s_one_shot_functions):
        self.virtual_s_one_shot_functions = virtual_s_one_shot_functions
        self.s_one_shot_functions = {}
        
    def load_s_one_shot_functions(self):
        function_names = self.s_one_shot_functions.keys()
        for function_name in function_names:
            self.virtual_s_one_shot_functions.add_s_one_shot_function_python(function_name,
                    self.s_one_shot_functions[function_name]["python_function"],self.s_one_shot_functions[function_name]["description"])
        
    def load_default_s_one_shot_functions(self):
        
        self.s_one_shot_functions["CFL_LOGM"] = {
            "python_function": cfl_logm,
            "description": "log to screen",
        }
        self.s_one_shot_functions["CFL_SET_STATE"] = {
            "python_function": cfl_set_state,
            "description": "set state",
        }
        self.s_one_shot_functions["CFL_SET_INITIAL_STATE"] = {
            "python_function": cfl_set_initial_state,
            "description": "set initial state",
        }
        self.s_one_shot_functions["CFL_BAD_STATE"] = {
            "python_function": cfl_bad_state,
            "description": "bad state",
        }
       
        self.s_one_shot_functions["CFL_FORK"] = {
            "python_function": cfl_fork,
            "description": "fork child",
        }
        self.s_one_shot_functions["CFL_TERMINATE"] = {
            "python_function": cfl_terminate,
            "description": "terminate child",
        }
        self.s_one_shot_functions["CFL_KILL_CHILDREN"] = {
            "python_function": cfl_kill_children,
            "description": "kill children",
        }
        self.s_one_shot_functions["CFL_MARK_INIT_STATE"] = {
            "python_function": cfl_mark_init_state,
            "description": "mark initial state",
        }
        self.s_one_shot_functions["CFL_MARK_STATE"] = {
            "python_function": cfl_mark_state,
            "description": "mark state",
        }
        self.s_one_shot_functions["CFL_SEND_CURRENT_NODE_EVENT"] = {
            "python_function": cfl_send_current_node_event,
            "description": "send current node event",
        }
        self.s_one_shot_functions["CFL_SEND_SYSTEM_EVENT"] = {
            "python_function": cfl_send_system_event,
            "description": "send system event",
        }
        self.load_s_one_shot_functions()
        
        
def cfl_logm(handle,node,event_id,event_data,params=[]):
        node_id = node["parent_node_name"]
        message = params[0]
        utc_time = datetime.now(timezone.utc)  # Modern way
        timestamp = (utc_time.timestamp())
        readable = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{timestamp}]  ************** node id: [{node_id}] message: {message}")
        
        
def cfl_set_state(handle,node,event_id,event_data,params=[]):
        chain_tree = handle
        node_id = node["parent_node_name"]
        node_dict = handle.python_dict[node_id]
        links = node_dict["label_dict"]["links"]
        parent_node = handle.python_dict[node_id]
        state = parent_node["node_dict"]["state_number"]
        state = event_data["state"]
        if state < 0 or state >= len(node_dict["label_dict"]["links"]):
            print(f"state number {state} is out of range")
            raise Exception(f"state number {state} is out of range")
        for link in node_dict["label_dict"]["links"]:
            chain_tree.ct_engine.terminate_node_id(link)
        chain_tree.ct_engine.enable_node_id(node_dict["label_dict"]["links"][state])
        
        
    
def cfl_set_initial_state(handle,node,event_id,event_data,params=[]):
    
    chain_tree = handle
    node_id = node["parent_node_name"]
    node_dict = handle.python_dict[node_id]
    links = node_dict["label_dict"]["links"]
    link_number = len(links)
    for link in links:
        chain_tree.ct_engine.terminate_node_id(link)
        
    if params[0] < link_number:
        link_node_id = links[params[0]]
        chain_tree.ct_engine.enable_node_id(link_node_id)
        node_dict["node_dict"]["state_number"] = params[0]
    else:
        print(f"set initial state number {params[0]} is out of range")
        raise Exception(f"set initial state number {params[0]} is out of range")
    node_dict["node_dict"]["state_number"] = params[0]
    return True
    
def cfl_bad_state(handle,node,event_id,event_data,params=[]):
        parent_node_id = node["parent_node_name"]
        parent_node = handle.python_dict[parent_node_id]
        link_number = len(parent_node["label_dict"]["links"])
        state_number = event_data["state_number"]
        print(f"bad state: {state_number} for link number: {link_number-1}")
        raise Exception(f"bad state: {state_number} for link number: {link_number-1}")
    
    

        
def cfl_fork(handle,node,event_id,event_data,params=[]):
    fork_number = params[0]
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    link_number = len(parent_node["label_dict"]["links"])
    if fork_number < link_number:
        link_node_id = parent_node["label_dict"]["links"][fork_number]
        chain_tree.ct_engine.enable_node_id(link_node_id)
    
    else:
        print(f"fork number {fork_number} is out of range")
        raise Exception(f"fork number {fork_number} is out of range")
    
    
def cfl_terminate(handle,node,event_id,event_data,params=[]):
    fork_number = params[0]
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    link_number = len(parent_node["label_dict"]["links"])
    if fork_number < link_number:
        link_node_id = parent_node["label_dict"]["links"][fork_number]
        chain_tree.ct_engine.terminate_node_id(link_node_id)
    else:
        print(f"terminate number {fork_number} is out of range")
        raise Exception(f"fork number {fork_number} is out of range")


def cfl_kill_children(handle,node,event_id,event_data,params=[]):
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    link_number = len(parent_node["label_dict"]["links"])
    for link in range(link_number):
        link_node_id = parent_node["label_dict"]["links"][link]
        
        chain_tree.ct_engine.terminate_node_id(link_node_id)
        
        
def cfl_mark_init_state(handle,node,event_id,event_data,params=[]):
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    parent_node["node_dict"]["state_number"] = params[0]
    return True
    
def cfl_mark_state(handle,node,event_id,event_data,params=[]):
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    parent_node["node_dict"]["state_number"] = event_data["state"]
    return True

def cfl_send_current_node_event(handle,node,event_id,event_data,params=[]):
    if len(params) != 2:
        raise Exception(f"send current node event requires 2 parameters event_id and event_data")
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    event_id = params[0]
    event_data = json.loads(params[1].replace("---",'"'))
    chain_tree.send_system_named_event(node_id=parent_node_id,event_id=event_id,event_data=event_data)
    return True

def cfl_send_system_event(handle,node,event_id,event_data,params=[]):
    if len(params) != 2:
        raise Exception(f"send system event requires 1 parameter event_id, event_data")
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    
    event_id = params[0]
    event_data = json.loads(params[1].replace("---",'"'))
    chain_tree.ct_engine.send_system_event(event_id=event_id,event_data=event_data)
    return True