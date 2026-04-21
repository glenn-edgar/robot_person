

class VirtualMainFunctions:
    def __init__(self,handle,valid_return_codes):
       
        
        self.valid_return_codes = valid_return_codes
        
        self.handle = handle
        self.main_functions = {}
        
    def add_main_function_python(self,function_name,function,description=""):
        if not isinstance(function_name, str):
            raise TypeError("function_name must be a string")
    
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        
        if function_name in self.main_functions:
            raise ValueError(f"Function {function_name} already exists")
    
        self.main_functions[function_name] = {
                "python_function": function,  #could be python function or micro instruction text
                "description": description,
                
            }
    
        
    def detect_main_coverage(self,required_main_functions):
    
        for function_name in required_main_functions:
            if function_name not in self.main_functions:
                raise ValueError(f"Function {function_name} is not defined")
        return True
    
    def run_main_function(self,function_name,auxiliary_function_name, handle, node_data,event_id,event_data):
        
        if function_name not in self.main_functions:
            raise ValueError(f"Function {function_name} is not defined")
            
        if auxiliary_function_name not in self.handle.Vb.boolean_functions:
            raise ValueError(f"Function {auxiliary_function_name} is not defined")
        
    
        auxiliary_function = self.handle.Vb.boolean_functions[auxiliary_function_name]["python_function"]    # will handle later
        return_value =  self.main_functions[function_name]["python_function"](auxiliary_function,handle, node_data,event_id,event_data)
      
        if return_value not in self.valid_return_codes:
                print("function_name: ", function_name)
                print("return_value: ", return_value)
                print("valid_return_codes: ", self.valid_return_codes)
                raise ValueError(f"Function {function_name} returned an invalid return code: {return_value}")
        return return_value
        
    
    
        
        