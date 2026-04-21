class CFLSBooleanFunctions:
    def __init__(self,virtual_s_boolean_functions):
        self.virtual_s_boolean_functions = virtual_s_boolean_functions
        self.s_boolean_functions = {}

        
    def load_s_boolean_functions(self):
        function_names = self.s_boolean_functions.keys()
        for function_name in function_names:
            self.virtual_s_boolean_functions.add_s_boolean_function_python(function_name,
                    self.s_boolean_functions[function_name]["python_function"],self.s_boolean_functions[function_name]["description"])
        
    def load_default_s_boolean_functions(self):
        self.s_boolean_functions["CFL_IS_STATE"] = {
            "python_function": cfl_is_state,
            "description": "is state boolean function",
        }
        self.load_s_boolean_functions()

        
def cfl_is_state(handle,node,event_id,event_data,params=[]):
    if event_id not in ["CFL_INIT_EVENT","CFL_TERM_EVENT"]:
        
        target_state = params[0]
        parent_node = handle.python_dict[node["parent_node_name"]]
        current_state = parent_node["node_dict"]["state_number"]
        if current_state == target_state:
            return True
        else:
            return False
    else:
        return False