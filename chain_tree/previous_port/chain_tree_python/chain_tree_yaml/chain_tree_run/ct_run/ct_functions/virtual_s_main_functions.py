class VirtualSMainFunctions:
    def __init__(self,handle,valid_return_codes):
       
        
        self.valid_return_codes = valid_return_codes
       
    
        self.handle = handle
        self.s_main_functions = {}
        
    def add_s_main_function_python(self,function_name,function,description=""):
        if not isinstance(function_name, str):
            raise TypeError("function_name must be a string")
    
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        
        if function_name in self.s_main_functions:
            raise ValueError(f"Function {function_name} already exists")
    
        self.s_main_functions[function_name] = {
                "python_function": function,  #could be python function or micro instruction text
                "description": description,
                
            }
    
        
    def detect_s_main_coverage(self,required_s_main_functions):
    
        for function_name in required_s_main_functions:
            if function_name not in self.s_main_functions:
                raise ValueError(f"Function {function_name} is not defined")
        return True
    
    def run_s_main_function(self,function_name, handle, node_data,event_id,event_data,params):
        
        if function_name not in self.s_main_functions:
            raise ValueError(f"Function {function_name} is not defined")
            
    

        return_value =  self.s_main_functions[function_name]["python_function"](handle, node_data,event_id,event_data,params)
        if return_value not in self.valid_return_codes:
                raise ValueError(f"Function {function_name} returned an invalid return code: {return_value}")
        return return_value
        
    
    
        
        