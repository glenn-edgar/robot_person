import copy
import json
from .column_flow import ColumnFlow
from .token_splitter.s_general_to_unique_function import SGeneralToUniqueFunction

class SNodeControl(ColumnFlow):
    """Controls S-node expressions and manages node lifecycles."""
    
    def __init__(self, ds, ctb, lisp_sequencer):
        super().__init__(ds, ctb)
        self.ds = ds
        self.ctb = ctb
        self.lisp_sequencer = lisp_sequencer
        self.s_expr_active = False
        self.s_general_to_unique_function = SGeneralToUniqueFunction(self)
        
    def define_s_node_control(self, column_name: str, aux_function_name: str, 
                              s_expression: str, user_data: dict = None, 
                              auto_start: bool = False):
        """
        Define an S-node control with the given expression.
        
        Args:
            column_name: Name of the column
            aux_function_name: Auxiliary function name
            s_expression: S-expression string to parse
            user_data: Optional user data dictionary
            auto_start: Whether to auto-start the node
            
        Returns:
            Node identifier
        """
        if user_data is None:
            user_data = {}
            
        template_node = {
            "fn_type": None,
            "fn_name": None,
            "node_dict": {"user_data": copy.deepcopy(user_data)},
            "enabled": False,
            "initialized": False,
            "parent_node_name": None
        }
        
        self.s_expr_active = True
        
        # Type validation
        if not isinstance(s_expression, str):
            raise TypeError("s_expression must be a string")
        if not isinstance(user_data, dict):
            raise TypeError("user_data must be a dictionary")
        if not isinstance(auto_start, bool):
            raise TypeError("auto_start must be a boolean")
            
            
        print(f"s_expression: {s_expression}")
        try:
            expanded_text = self.lisp_sequencer.expand_macros_only(s_expression)
        
        except ValueError as e: # exception is there because of a macro error
            print(f"Macro expansion error: {e}")
            exit()
        results = self.s_general_to_unique_function.convert(expanded_text)
    
        s_dict = self.lisp_sequencer.check_lisp_instruction_with_macros(results["process_string"])
       
        if not s_dict["valid"]:
            print(f"s_dict: {s_dict}")
            raise ValueError("Invalid s_expression")
        
        base_function_list = results["base_functions"]
        for type_name, fn_name in base_function_list.items():
            fn_type = type_name[0]
            fn_name = type_name[1:]
            if fn_type == "@":
                self.ctb.add_s_one_shot_function(fn_name)
            elif fn_type == "?":
                self.ctb.add_s_boolean_function(fn_name)
            elif fn_type == "!":
                self.ctb.add_s_main_function(fn_name)
            else:
                raise ValueError(f"Invalid function type: {fn_type}")
   
        
        local_nodes = {}
        for unique_function, data in results["unique_function"].items():
            fn_type = data[0]
            base_fn_name = data[1]
        
            local_nodes[unique_function] = copy.deepcopy(template_node)
            local_nodes[unique_function]["fn_type"] = fn_type
            local_nodes[unique_function]["fn_name"] = base_fn_name[1:]
            
                
        s_dict_string = json.dumps(s_dict)
        sdata = {"s_dict": s_dict_string}
        column_data = {
            "user_data": user_data,
            "s_data": sdata,
        
            "local_nodes": local_nodes
        }
        
        return_node = self.define_column(
            column_name, "CFL_S_NODE_CONTROL_MAIN", "CFL_S_NODE_CONTROL_INIT", 
            "CFL_S_NODE_CONTROL_TERM", aux_function_name, column_data, 
            auto_start, label="S_NODE"
        )
        
        self.s_expr_dict[return_node] = True
        
        for node_name in local_nodes.keys():
            local_nodes[node_name]["parent_node_name"] = return_node
           
        return return_node
    
    def end_s_node_control(self, column_name_id: str):
        """End an S-node control and validate """
        if not self.s_expr_active:
            raise ValueError(f"S node control {column_name_id} is not active")
            
        self.s_expr_active = False
        self.s_expr_dict.pop(column_name_id)
    
 
        self.end_column(column_name_id)