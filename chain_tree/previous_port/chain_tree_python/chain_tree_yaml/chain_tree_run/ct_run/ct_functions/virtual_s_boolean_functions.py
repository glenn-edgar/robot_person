class VirtualSBooleanFunctions:
    def __init__(self,handle,valid_return_codes):
        self.valid_return_codes = [True,False]
        self.s_boolean_functions = {}
        
        self.handle = handle
        
    def add_s_boolean_function_python(self,function_name,function,description=""):
        if not isinstance(function_name, str):
            raise TypeError("function_name must be a string")
    
        if not isinstance(description, str):
            raise TypeError("description must be a string")
       
        if function_name in self.s_boolean_functions:
            raise ValueError(f"Function {function_name} already exists")
        
        self.s_boolean_functions[function_name] = {
            "python_function": function,
            "description": description
            }
    
        
        
    
        
    def detect_s_boolean_coverage(self,required_s_boolean_functions):   
        for function_name in required_s_boolean_functions:
            if function_name not in self.s_boolean_functions:
                raise ValueError(f"Function {function_name} is not defined")
        return True
    
    
    
    def run_s_boolean_function(self,function_name, handle, node,event_id,event_data,params=[]):
        
        
        if function_name not in self.s_boolean_functions:
            raise ValueError(f"Function {function_name} is not defined")
        
            # will handle later
        return_value =  self.s_boolean_functions[function_name]["python_function"](handle, node,event_id,event_data,params)
        return return_value
    
    