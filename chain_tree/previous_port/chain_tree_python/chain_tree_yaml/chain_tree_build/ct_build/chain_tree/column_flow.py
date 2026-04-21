from .chain_tree_basic import ChainTreeBasic
import re

class ColumnFlow():
    
    def __init__(self, ds, ctb):
        self.ds = ds
        self.ctb = ctb

        
        
        
    def define_column(self, column_name:str,  main_function ="CFL_COLUMN_MAIN",
                      initialization_function ="CFL_COLUMN_INIT", termination_function ="CFL_COLUMN_TERM", 
                      aux_function ="CFL_COLUMN_NULL",column_data:dict = None,auto_start = False,label:str="COLUMN",links_flag = True):
                      
        
        if not isinstance(column_name, str):
            raise TypeError("Column name must be a string")
        if not isinstance(main_function, str):
            raise TypeError("Main function must be a string")
        if not isinstance(initialization_function, str):
            raise TypeError("Initialization function must be a string")
        if not isinstance(termination_function, str):
            raise TypeError("Termination function must be a string")
        if not isinstance(auto_start, bool):
            raise TypeError("Auto start must be a boolean")
        node_name = f"_{self.ctb.link_number}"
        self.ctb.link_number += 1
        self.ctb.link_number_stack.append(self.ctb.link_number)
        self.ctb.link_number = 0
        element_data = {}
        element_data["auto_start"] = auto_start
        element_data["column_data"] = column_data
        temp_name =column_name[:4]
        column_name =self.ctb.add_node_element("COL_"+temp_name,node_name,main_function,initialization_function,aux_function,termination_function,
                                    element_data,links_flag)
        
        self.ctb.add_one_shot_function(initialization_function)
        self.ctb.add_boolean_function(aux_function)
        self.ctb.add_one_shot_function(termination_function)
        return column_name
        
    def define_gate_node(self, column_name:str,  main_function ="CFL_GATE_NODE_MAIN",
                              initialization_function ="CFL_GATE_NODE_INIT", termination_function ="CFL_GATE_NODE_TERM", 
                              aux_function ="CFL_GATE_NODE_NULL",column_data:dict = None,auto_start = False,links_flag = True):
    
        if not isinstance(column_name, str):
            raise TypeError("Column name must be a string")
        if not isinstance(main_function, str):
            raise TypeError("Main function must be a string")
        if not isinstance(initialization_function, str):
            raise TypeError("Initialization function must be a string")
        if not isinstance(termination_function, str):
            raise TypeError("Termination function must be a string")
        if not isinstance(aux_function, str):
            raise TypeError("Aux function must be a string")
        if not isinstance(column_data, dict):
            raise TypeError("Column data must be a dictionary")
        if column_data is None:
            raise ValueError("Column data must be a dictionary")
        if not isinstance(auto_start, bool):
            raise TypeError("Auto start must be a boolean")
        element_data = {}
        element_data["auto_start"] = auto_start
        element_data["column_data"] = column_data
        node_name = f"_{self.ctb.link_number}"
        self.ctb.link_number += 1
        self.ctb.link_number_stack.append(self.ctb.link_number)
        self.ctb.link_number = 0
        self.ctb.add_main_function(main_function)
        self.ctb.add_one_shot_function(initialization_function)
        self.ctb.add_boolean_function(aux_function)
        self.ctb.add_one_shot_function(termination_function)
        if links_flag:
            temp_name =column_name[:4]
        else:
            temp_name = column_name
        return self.ctb.add_node_element("GATE_"+temp_name, node_name, main_function, initialization_function, 
                                         aux_function, termination_function, column_data,links_flag)
   
           
    def define_fork_column(self, column_name:str,  main_function ="CFL_FORK_MAIN",
                              initialization_function ="CFL_FORK_INIT", termination_function ="CFL_FORK_TERM", 
                              aux_function ="CFL_NULL",column_data:dict = {},auto_start = False,label:str="FORK"):
        
        if not isinstance(column_name, str):
            raise TypeError("Column name must be a string")
        if not isinstance(main_function, str):
            raise TypeError("Main function must be a string")
        if not isinstance(initialization_function, str):
            raise TypeError("Initialization function must be a string")
        if not isinstance(termination_function, str):
            raise TypeError("Termination function must be a string")
        if not isinstance(aux_function, str):
            raise TypeError("Aux function must be a string")
        if not isinstance(column_data, dict):
            raise TypeError("Column data must be a dictionary")
        if column_data is None:
            raise ValueError("Column data must be a dictionary")
        node_name = f"_{self.ctb.link_number}"
        self.ctb.link_number += 1
        self.ctb.link_number_stack.append(self.ctb.link_number)
        self.ctb.link_number = 0  
        self.ctb.add_one_shot_function(initialization_function)
        self.ctb.add_boolean_function(aux_function)
        self.ctb.add_one_shot_function(termination_function)
        return self.ctb.add_node_element("FORK_", node_name, main_function, initialization_function, 
                                         aux_function, termination_function, column_data)
 
 
    def define_while_column(self, column_name:str, main_function ="CFL_WHILE_MAIN",
                     initialization_function ="CFL_WHILE_INIT", termination_function ="CFL_WHILE_TERM", 
                     aux_function ="CFL_NULL",user_data:dict = {},auto_start = False,label:str="WHILE"):
        
        if not isinstance(column_name, str):
            raise TypeError("Column name must be a string")
        if not isinstance(main_function, str):
            raise TypeError("Main function must be a string")
        if not isinstance(initialization_function, str):
            raise TypeError("Initialization function must be a string")
        if not isinstance(termination_function, str):
            raise TypeError("Termination function must be a string")
        if not isinstance(aux_function, str):
            raise TypeError("Aux function must be a string")
        node_name = f"_{self.ctb.link_number}"
        self.ctb.link_number += 1
    
        self.ctb.link_number_stack.append(self.ctb.link_number)
        self.ctb.link_number = 0
        column_data = {"user_data": user_data,"auto_start": auto_start}
        return self.ctb.add_node_element("WHILE_"+column_name, node_name, main_function, initialization_function, aux_function, termination_function, column_data)    
    
    def define_for_column(self, column_name:str,number_of_iterations:int, main_function ="CFL_FOR_MAIN",
                     initialization_function ="CFL_FOR_INIT", termination_function ="CFL_NULL", 
                     aux_function ="CFL_NULL",user_data:dict = {},auto_start = False,label:str="FOR"):
        
        if not isinstance(column_name, str):
            raise TypeError("Column name must be a string")
        if not isinstance(main_function, str):
            raise TypeError("Main function must be a string")
        if not isinstance(initialization_function, str):
            raise TypeError("Initialization function must be a string")
        if not isinstance(termination_function, str):
            raise TypeError("Termination function must be a string")
        if not isinstance(aux_function, str):
            raise TypeError("Aux function must be a string")
        
        column_data = {"number_of_iterations": number_of_iterations, "user_data": user_data,"auto_start": auto_start}
        node_name = f"_{self.ctb.link_number}"
        self.ctb.link_number += 1
        self.ctb.link_number_stack.append(self.ctb.link_number)
        self.ctb.link_number = 0
        temp_name =column_name[:4]
        return self.ctb.add_node_element("FOR_"+temp_name, node_name, main_function, initialization_function, aux_function, termination_function, column_data)
    
    
    def define_join_link(self, parent_node_name:str):
        node_data = {"parent_node_name": parent_node_name}      
        return self.define_column_link(main_function_name="CFL_JOIN_MAIN", initialization_function_name="CFL_NULL", 
                                       aux_function_name="CFL_NULL", termination_function_name="CFL_NULL", node_data=node_data)
  
    
    def define_column_link(self, main_function_name:str, initialization_function_name:str, aux_function_name:str,
                           termination_function_name:str, node_data:dict, label:str = "LEAF"):

      
        if not isinstance(node_data, dict):
            raise TypeError("Node data must be a dictionary")
        node_name = f"_{self.ctb.link_number}"
        self.ctb.link_number += 1
        node_id = self.ctb.add_leaf_element(label, node_name, main_function_name, initialization_function_name, aux_function_name , termination_function_name, node_data )
        return node_id
    
    
 
        
    def end_column(self,column_name:str):
        if column_name in self.sequence_dict:
            raise ValueError("Sequence is active")
        column_data = self.ds.yaml_data[column_name]
        main_function_name = column_data["label_dict"]["main_function_name"]
        if main_function_name in ["CFL_FOR_MAIN", "CFL_WHILE_MAIN"]:
            if len(column_data["label_dict"]["links"]) > 1:
                raise ValueError("Column has multiple links with for or while column")
        self.ctb.link_number = self.ctb.link_number_stack.pop()
        self.ctb.pop_node_element(column_name)
        
        
    def verify_node_id(self,node_id :str):
        
        """
        Validate ltree label format without database connection.
        
        Rules:
        - Only alphanumeric characters and underscores
        - Cannot start with underscore  
        - Length between 1-256 characters
        - No dots (dots separate path components in ltree)
        """
        if not isinstance(node_id, str):
            return False
            
        if not node_id or len(node_id) > 256:
            return False
        
        # Must start with alphanumeric, then can contain alphanumeric + underscores
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_]*$'
        return bool(re.match(pattern, node_id))
    
    
     

 

    

    
 