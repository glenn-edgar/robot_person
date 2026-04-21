class VirtualOneShotFunctions:
    def __init__(self,handle,valid_return_codes):
        self.valid_return_codes = valid_return_codes
        self.one_shot_functions = {}
        self.handle = handle
        
    def add_one_shot_function_python(self,function_name,function,description=""):
    
        if not isinstance(function_name, str):
            raise TypeError("function_name must be a string")
    
        if not isinstance(description, str):
            raise TypeError("description must be a string")
    
        if function_name in self.one_shot_functions:
            raise ValueError(f"Function {function_name} already exists")
        
        self.one_shot_functions[function_name] = {
                "python_function": function,  #could be python function or micro instruction text
                "description": description,
                
            }
    
        
        
    def detect_one_shot_coverage(self,required_one_shot_functions):
        
        for function_name in required_one_shot_functions:
            
            if function_name not in self.one_shot_functions:
                raise ValueError(f"Function {function_name} is not defined")
        return True
    
    def run_one_shot_function(self,function_name, handle, node, termination_flag=False):
    
        
        if function_name not in self.one_shot_functions:
            raise ValueError(f"Function {function_name} is not defined")
        self.one_shot_functions[function_name]["python_function"](handle, node)
        
    
        
    
    def find_one_shot_function(self,function_name):
        for function_name, function_code in self.one_shot_functions.items():
            if function_name == function_name:
                return function_code
        raise ValueError(f"Function {function_name} is not defined")
    
    