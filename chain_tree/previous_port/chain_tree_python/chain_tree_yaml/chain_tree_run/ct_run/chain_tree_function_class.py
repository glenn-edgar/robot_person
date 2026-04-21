

class ChainTreeFunctionClass:
    def __init__(self):
        self.boolean_functions = {}
        self.one_shot_functions = {}
        self.main_functions = {}
        self.s_one_shot_functions = {}
        self.s_boolean_functions = {}
        self.s_main_functions = {}
        
    def add_boolean_function(self,function_name,function,description=""):
        self.boolean_functions[function_name] = {
            "function": function,
            "description": description
        }
        
    def add_one_shot_function(self,function_name,function,description=""):
        self.one_shot_functions[function_name] = {
            "function": function,
            "description": description
        }
        
    def add_main_function(self,function_name,function,description=""):
        self.main_functions[function_name] = {
            "function": function,
            "description": description
        }
        
    def add_s_one_shot_function(self,function_name,function,description=""):
        self.s_one_shot_functions[function_name] = {
            "function": function,
            "description": description
        }
        
    def add_s_boolean_function(self,function_name,function,description=""):
        self.s_boolean_functions[function_name] = {
            "function": function,
            "description": description
        }
        
    def add_s_main_function(self,function_name,function,description=""):
        self.s_main_functions[function_name] = {
            "function": function,
            "description": description
        }
    
    def load_functions(self,chain_tree,update_function=False):
        self.transfer_boolean_functions(chain_tree,update_function)
        self.transfer_one_shot_functions(chain_tree,update_function)
        self.transfer_main_functions(chain_tree,update_function)
        self.transfer_s_one_shot_functions(chain_tree,update_function)
        self.transfer_s_boolean_functions(chain_tree,update_function)
        self.transfer_s_main_functions(chain_tree,update_function)
        
    def transfer_boolean_functions(self,chain_tree,update_function = False):
        for function_name in self.boolean_functions:
            if update_function == True or function_name not in chain_tree.Vb.boolean_functions:
                chain_tree.Vb.add_boolean_function_python(function_name,
                      self.boolean_functions[function_name]["function"],
                      self.boolean_functions[function_name]["description"])
    
    def transfer_one_shot_functions(self,chain_tree,update_function = False):
        for function_name in self.one_shot_functions:
            if update_function == True or function_name not in chain_tree.Vo.one_shot_functions:
                chain_tree.Vo.add_one_shot_function_python(function_name,
                  self.one_shot_functions[function_name]["function"],
                  self.one_shot_functions[function_name]["description"])    
            
    def transfer_main_functions(self,chain_tree,update_function = False):
        for function_name in self.main_functions:
            if update_function == True or function_name not in chain_tree.Vm.main_functions:
                chain_tree.Vm.add_main_function_python(function_name,
                      self.main_functions[function_name]["function"],
                      self.main_functions[function_name]["description"])
            
    def transfer_s_boolean_functions(self,chain_tree,update_function = False):
        for function_name in self.s_boolean_functions:
            if update_function == True or function_name not in chain_tree.Vsb.s_boolean_functions:
                chain_tree.Vsb.add_s_boolean_function_python(function_name,
                      self.s_boolean_functions[function_name]["function"],
                      self.s_boolean_functions[function_name]["description"])
            
    def transfer_s_main_functions(self,chain_tree,update_function = False):
        for function_name in self.s_main_functions:
            if update_function == True or function_name not in chain_tree.Vsm.s_main_functions:
                chain_tree.Vsm.add_s_main_function_python(function_name,
                      self.s_main_functions[function_name]["function"],
                      self.s_main_functions[function_name]["description"])
                
    def transfer_s_one_shot_functions(self,chain_tree,update_function = False):
        for function_name in self.s_one_shot_functions:
            if update_function == True or function_name not in chain_tree.Vso.s_one_shot_functions:
                chain_tree.Vso.add_s_one_shot_function_python(function_name,
                      self.s_one_shot_functions[function_name]["function"],
                      self.s_one_shot_functions[function_name]["description"])