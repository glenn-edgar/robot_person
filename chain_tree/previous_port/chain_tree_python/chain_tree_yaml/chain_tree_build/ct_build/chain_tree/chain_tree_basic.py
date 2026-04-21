



class ChainTreeBasic:
    def __init__(self, data_structures,): # has subparts
        self.ds = data_structures
        self.ltree_stack = []
        self.main_function_mapping_dict = {}
        self.one_shot_function_mapping_dict = {}
        self.boolean_function_mapping_dict = {}
        self.s_one_shot_function_mapping_dict = {}
        self.s_boolean_function_mapping_dict = {}
        self.s_main_function_mapping_dict = {}
        self.link_number = 0
        self.link_number_stack = []
        self.define_kb_dict = {}
        self.current_kb_name = None
        
    def initialize_function_mapping(self):
        self.main_function_mapping_dict = {}
        self.one_shot_function_mapping_dict = {}
        self.boolean_function_mapping_dict = {}
        self.s_one_shot_function_mapping_dict = {}
        self.s_boolean_function_mapping_dict = {}
        self.s_main_function_mapping_dict = {}
        self.define_kb_dict = {}
        self.current_kb_name = None
        
    def define_kb(self,kb_name ):
    
        self.current_kb_name = kb_name
        if not isinstance(kb_name, str):
            raise TypeError("kb_name must be a string")
        if kb_name in self.define_kb_dict:
            return
        self.define_kb_dict[kb_name] = True
        if kb_name not in self.main_function_mapping_dict:
            self.main_function_mapping_dict[kb_name] = {}
        if kb_name not in self.one_shot_function_mapping_dict:
            self.one_shot_function_mapping_dict[kb_name] = {}
        if kb_name not in self.boolean_function_mapping_dict:
            self.boolean_function_mapping_dict[kb_name] = {}
        if kb_name not in self.s_one_shot_function_mapping_dict:
            self.s_one_shot_function_mapping_dict[kb_name] = {}
        if kb_name not in self.s_boolean_function_mapping_dict:
            self.s_boolean_function_mapping_dict[kb_name] = {}
        if kb_name not in self.s_main_function_mapping_dict:
            self.s_main_function_mapping_dict[kb_name] = {}
            
    def select_kb(self,kb_name):
        if kb_name in self.define_kb_dict:
            self.current_kb_name = kb_name
        else:
            self.define_kb(kb_name)
            self.current_kb_name = kb_name
            
    def add_main_function(self,function_name):
        
        if self.current_kb_name is None:
            raise ValueError("No database defined")
        self.main_function_mapping_dict[self.current_kb_name][function_name] = True
        
    def add_one_shot_function(self,function_name):
 
        if self.current_kb_name is None:
            raise ValueError("No database defined")
        self.one_shot_function_mapping_dict[self.current_kb_name][function_name] = True
    def add_boolean_function(self,function_name):
        if self.current_kb_name is None:
            raise ValueError("No database defined")
        self.boolean_function_mapping_dict[self.current_kb_name][function_name] = True
    def add_s_one_shot_function(self,function_name):
        if self.current_kb_name is None:
            raise ValueError("No database defined")
        self.s_one_shot_function_mapping_dict[self.current_kb_name][function_name] = True
    def add_s_boolean_function(self,function_name):
        if self.current_kb_name is None:
            raise ValueError("No database defined")
        self.s_boolean_function_mapping_dict[self.current_kb_name][function_name] = True
    def add_s_main_function(self,function_name):
        if self.current_kb_name is None:
            raise ValueError("No database defined")
        self.s_main_function_mapping_dict[self.current_kb_name][function_name] = True
        
        
        
        
    def check_for_balance_ltree(self):
        if len(self.ltree_stack) != 0:
            
            raise ValueError("Ltrees have not been closed: {self.ltree_stack}")
     

            
    def start_assembly(self):
        self.ltree_stack = []
    
    
    def _add_node_link(self, ltree_name :str):
        if len(self.ltree_stack) == 0:
            return
        if not isinstance(ltree_name, str):
            raise TypeError("ltree_name must be a string")
        ref_node = self.ltree_stack[-1]
        ref_data = self.ds.yaml_data[ref_node]
       
        ref_data["label_dict"]["links"].append(ltree_name)
        self.ds.yaml_data[ref_node] = ref_data
      
        
        
    def add_node_element(self, label_name :str, node_name :str, main_function_name :str, initialization_function_name :str,
                         aux_function_name :str ,termination_function_name :str, node_data :dict,links_flag = True):
        
        if not isinstance(label_name, str):
            raise TypeError("label_name must be a string")
        if not isinstance(node_name, str):
            raise TypeError("node_name must be a string")
        if not isinstance(main_function_name, str):
            raise TypeError("main_function_name must be a string")
        if not isinstance(aux_function_name, str):
            raise TypeError("aux_function_name must be a string")
        
        if not isinstance(initialization_function_name, str):
            raise TypeError("initialization_function_name must be a string")
        
        if not isinstance(node_data, dict):
            raise TypeError("node_data must be a dictionary")
        label_data = {}
        label_data["main_function_name"] = main_function_name
        label_data["initialization_function_name"] = initialization_function_name
        label_data["aux_function_name"] = aux_function_name
        label_data["termination_function_name"] = termination_function_name
        label_data["links"] = []
        ltree_name = self.ds.define_composite_node(label_name, node_name, label_data, node_data)
        
        self.add_main_function(main_function_name)

        self.add_boolean_function(aux_function_name)
        self.add_one_shot_function(termination_function_name)
        self.add_one_shot_function(initialization_function_name)
        if links_flag:
            self._add_node_link(ltree_name)
    
        self.ltree_stack.append(ltree_name)
        return ltree_name
        
    
    def pop_node_element(self,ref_ltree_name:str):
        ltree_name = self.ltree_stack.pop()
        
        if ltree_name != ref_ltree_name:
        
            raise ValueError(f"Ltree name mismatch: {ltree_name} != {ref_ltree_name}")
        temp_data = self.ds.yaml_data[ltree_name]
    
        self.ds.pop_path(temp_data["label"], temp_data["node_name"])
        
        
    def add_leaf_element(self, label_name :str, node_name :str, main_function_name :str,initialization_function_name :str,
                         aux_function_name :str, termination_function_name :str, node_data :dict):
        if not isinstance(label_name, str):
            raise TypeError("label_name must be a string")
        if not isinstance(node_name, str):
            raise TypeError("node_name must be a string")
        if not isinstance(aux_function_name, str):
            raise TypeError("aux_function_name must be a string")
        if not isinstance(termination_function_name, str):
            raise TypeError("termination_function_name must be a string")
        
        if not isinstance(initialization_function_name, str):
            raise TypeError("initialization_function_name must be a string")
        

        label_data = {}
        label_data["main_function_name"] = main_function_name
        label_data["initialization_function_name"] = initialization_function_name
        label_data["aux_function_name"] = aux_function_name
        label_data["termination_function_name"] = termination_function_name
        label_data["links"] = []
    
        ltree_name = self.ds.define_simple_node(label_name, node_name, label_data, node_data)
        self.add_main_function(main_function_name)
                
        self.add_boolean_function(aux_function_name)
        self.add_one_shot_function(termination_function_name)
        self.add_one_shot_function(initialization_function_name)
        self._add_node_link(ltree_name)
        return ltree_name
        
        
        
        
    