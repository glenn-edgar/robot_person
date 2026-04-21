from datetime import datetime, timezone
import time



class CFLSMainFunctions:
    def __init__(self,virtual_s_main_functions):
        self.virtual_s_main_functions = virtual_s_main_functions
        self.s_main_functions = {}
    
        

    def load_s_main_functions(self):
        function_names = self.s_main_functions.keys()
        for function_name in function_names:
            self.virtual_s_main_functions.add_s_main_function_python(function_name,
                    self.s_main_functions[function_name]["python_function"],self.s_main_functions[function_name]["description"])
        
    
    def load_default_s_main_functions(self):
        self.s_main_functions["CFL_WAIT"] = {
            "python_function": cfl_wait_time_s,
            "description": "wait for a specified time",
        }
        self.s_main_functions["CFL_TIME_OUT"] = {
            "python_function": cfl_time_out_s,
            "description": "time out function",
        }
        self.s_main_functions["CFL_JOIN"] = {
            "python_function": cfl_join_s,
            "description": "join function",
        }
        self.s_main_functions["CFL_RESET_CODES"] = {
            "python_function": cfl_reset_codes,
            "description": "reset codes function",
        }
        self.load_s_main_functions()
        
        
def cfl_wait_time_s(handle, node,event_id,event_data,params):
    #("***************************************cfl_wait_time", node["label_dict"]["ltree_name"],event_id,event_data)
    if event_id == "CFL_INIT_EVENT":
        node["time_delay"] = params[0]
        node["start_time"] = handle.ct_timer.get_timestamp()
        
        return "CFL_FUNCTION_HALT"
    
    if event_id == "CFL_TERM_EVENT":
        return "CFL_CONTINUE"
    
    
    start_time = node["start_time"]
    
    current_time = handle.ct_timer.get_timestamp()
    
    if current_time - start_time >= node["time_delay"]:
        
        return "CFL_CONTINUE"
    
    return "CFL_FUNCTION_RETURN"

def cfl_time_out_s(handle, node,event_id,event_data,params):
    #("***************************************cfl_wait_time", node["label_dict"]["ltree_name"],event_id,event_data)
    if event_id == "CFL_INIT_EVENT":

        node["time_delay"] = params[0]
        node["start_time"] = handle.ct_timer.get_timestamp()
        return "CFL_CONTINUE"
    
    if event_id == "CFL_TERM_EVENT":
        return "CFL_CONTINUE"
    
        
    start_time = node["start_time"]
    
    current_time = handle.ct_timer.get_timestamp()
    
    if current_time - start_time >= node["time_delay"]:
        
        return "CFL_FUNCTION_TERMINATE"
    
    return "CFL_CONTINUE"


def cfl_join_s(handle, node,event_id,event_data,params):

    #("***************************************cfl_wait_time", node["label_dict"]["ltree_name"],event_id,event_data)
    if event_id == "CFL_INIT_EVENT":
        return "CFL_FUNCTION_HALT"
    if event_id == "CFL_TERM_EVENT":
        return "CFL_FUNCTION_HALT"
    
    selected_link_number = params[0]
    parent_node_id = node["parent_node_name"]
    chain_tree = handle
    parent_node = chain_tree.python_dict[parent_node_id]
    link_number = len(parent_node["label_dict"]["links"])
    if selected_link_number < link_number:
        link_node_id = parent_node["label_dict"]["links"][selected_link_number]
        
        if chain_tree.ct_engine.node_id_enabled(link_node_id) == True:
            return "CFL_FUNCTION_HALT"
        else:

            return "CFL_DISABLE"
    else:
        print(f"link number {link_number} is out of range")
        raise Exception(f"link number {link_number} is out of range")

def cfl_reset_codes(handle, node,event_id,event_data,params):
    raise NotImplementedError("cfl_reset_codes is a dummy function and should not be called")