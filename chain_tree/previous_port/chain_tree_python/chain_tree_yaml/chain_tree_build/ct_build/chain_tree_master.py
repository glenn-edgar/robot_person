import time
import json
from pathlib import Path
from datetime import datetime, timezone

from .chain_tree.chain_tree_basic import ChainTreeBasic
from .chain_tree.basic_cf_links import BasicCfLinks
from .chain_tree.wait_cf_links import WaitCfLinks
from .chain_tree.verify_cf_links import VerifyCfLinks
from .chain_tree.state_machine import StateMachine

from .chain_tree.column_flow import ColumnFlow
from .chain_tree.sequence_til import SequenceTil
from .chain_tree.data_flow import DataFlow
from .chain_tree.templates import Templates
from .chain_tree.s_node_control import SNodeControl



class ChainTreeMaster(BasicCfLinks, WaitCfLinks, VerifyCfLinks, StateMachine, SequenceTil, DataFlow, Templates, SNodeControl):
    
    @classmethod
    def start_build(cls,yaml_file,DataStructures,LispSequencer,template_dirs=[]):
        ds = DataStructures(yaml_file=Path(yaml_file))
        ct = cls(ds,LispSequencer,template_dirs=template_dirs)
        return ct
    
    def __init__(self, data_structures,LispSequencer=None,template_dirs=[],enable_mako=True,macro_files=[]):
        if LispSequencer is None:
            raise ValueError("Lisp sequencer is required")
        self.ds = data_structures
        self.lisp_sequencer = LispSequencer
        self.macro_files = macro_files
        self.ctb = ChainTreeBasic(self.ds)
        BasicCfLinks.__init__(self, self.ds,self.ctb)
        WaitCfLinks.__init__(self, self.ds,self.ctb)
        VerifyCfLinks.__init__(self, self.ds,self.ctb)
        StateMachine.__init__(self, self.ds,self.ctb)

        ColumnFlow.__init__(self, self.ds,self.ctb)
        SequenceTil.__init__(self, self.ds,self.ctb)
        DataFlow.__init__(self, self.ds,self.ctb)
        Templates.__init__(self, self.ds,self.ctb)
        
        
        self.ctb.link_number = 0
        self.ctb.initialize_function_mapping()
        self.ctb.link_number_stack = []
        self.s_return_control_codes = [
            "CFL_CONTINUE", "CFL_TERMINATE", "CFL_DISABLE", "CFL_TERMINATE_SYSTEM",
         "CFL_FUNCTION_RETURN","CFL_FUNCTION_HALT","CFL_FUNCTION_TERMINATE"
        ]
        
        self.lisp_sequencer = LispSequencer( handle = self,
                 run_function = self.run_function,
                 debug_function = self.debug_function,
                 control_codes= self.s_return_control_codes,
                 template_dirs=template_dirs)
        SNodeControl.__init__(self, self.ds,self.ctb,self.lisp_sequencer)
        
    def compress_event_data(self, event_data):
        return json.dumps(event_data).replace('"', '---')
    
    
    def get_macro_files(self):
        return self.macro_files
    
    def set_macro_files(self, macro_files):
        self.macro_files = macro_files
        
    # not needed in generation
    def run_function(self, handle, func_type, func_name, node, event_id, event_data,params=[]):
        raise ValueError(f"Function {func_name} should not occur in the operation because the lisp sequencer is only doing token checking")
        
    
    
    def check_and_generate_yaml(self):
    
        self.finalize_template_kb()
        self.check_valid_chain_tree_configuration()
        self.dump_function_mapping()
        self.dump_complete_function_map()
        self.generate_yaml()
        
        
        
        
    def  generate_yaml(self):
        self.ds.generate_yaml()

    def select_kb(self,kb_name):
        if kb_name in self.ctb.define_kb_dict:
            self.ds.select_kb(kb_name)
            self.ctb.select_kb(kb_name)
            
        else:
        
            self.ds.add_kb(kb_name)
            self.ds.select_kb(kb_name)
            self.ctb.define_kb(kb_name)
            self.ctb.select_kb(kb_name)
            
    def debug_function(self, handle, message, node=None, event_id=None):
        """Debug logging with timestamp."""
        timestamp = datetime.now().isoformat()
        print(f"[{timestamp}] DEBUG: {message}")
        if node is not None or event_id is not None:
            print(f"  Node: {node}, Event: {event_id}")
            
        
    def define_root_node(self,version:str):
       self.ctb.link_number = 0
       self.ctb.link_number_stack = []
       self.root_node = self.define_gate_node("root_node", column_data={"version":version},auto_start = True,links_flag = True)
       self.sequence_dict = {}
       self.s_expr_dict = {}
                 
 
    
                 
    def start_test(self,test_name:str,
                  template_function_list=None):  
        
    
        
        self.select_kb(test_name)
        self.define_root_node(version="1.0.0")            
        self.init_template_kb()
        if template_function_list is not None:
            for template_function in template_function_list:
                template_function(self)
    
     
        
    def end_test(self):
        self.finalize_template_kb()
        self.finalize_and_check()
    
        
        
    def pop_root_node(self):
        self.ctb.pop_node_element(self.root_node)
        
    def add_state_machine_node(self):
       node_data = self.sm_name_dict 
       self.sm_node = self.ctb.add_node_element("sm_node","sm_node","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
       self.pop_state_machine_node()                

    def pop_state_machine_node(self):
        self.ctb.pop_node_element(self.sm_node)

    def check_valid_chain_tree_configuration(self):
        self.check_for_balance_sm()
        #self.check_for_balance_ltree()
        
        
    def finalize_and_check(self):
        self.check_for_balance_sm()
        if len(self.sequence_dict) > 0:
            raise ValueError(f"Unfinished sequence ends {self.sequence_dict.keys()}")
        if len(self.s_expr_dict) > 0:
            raise ValueError(f"Unfinished s_expression ends {self.s_expr_dict.keys()}")
        self.end_column(self.root_node)
        self.ds.leave_kb()
    
            

    
     
    def get_all_virtual_functions(self):
        main_functions = self.ctb.ds.yaml_data["complete_functions.complete_functions.complete_functions.main_functions"]["node_dict"].keys()
        one_shot_functions = self.ctb.ds.yaml_data["complete_functions.complete_functions.complete_functions.one_shot_functions"]["node_dict"].keys()
        boolean_functions = self.ctb.ds.yaml_data["complete_functions.complete_functions.complete_functions.boolean_functions"]["node_dict"].keys()
        s_one_shot_functions = self.ctb.ds.yaml_data["complete_functions.complete_functions.complete_functions.s_one_shot_functions"]["node_dict"].keys()
        s_boolean_functions = self.ctb.ds.yaml_data["complete_functions.complete_functions.complete_functions.s_boolean_functions"]["node_dict"].keys()
        s_main_functions = self.ctb.ds.yaml_data["complete_functions.complete_functions.complete_functions.s_main_functions"]["node_dict"].keys()
        return {"main_functions":main_functions, "one_shot_functions":one_shot_functions, "boolean_functions":boolean_functions, 
                "s_one_shot_functions":s_one_shot_functions, "s_boolean_functions":s_boolean_functions, "s_main_functions":s_main_functions}
    
    
    def display_chain_tree_function_mapping(self):
        all_virtual_functions = self.get_all_virtual_functions()
        print("complete function mapping:")
        print("main_functions:")
      
        print("display one_shot_functions:")
        print("one_shot_functions:")
        for function in all_virtual_functions["one_shot_functions"]:
            print("--------------------------------",function)
        
        print("boolean_functions:")
        for function in all_virtual_functions["boolean_functions"]:
            print("--------------------------------",function)
        print("s_one_shot_functions:")
        for function in all_virtual_functions["s_one_shot_functions"]:
            print("--------------------------------",function)
        
        print("s_boolean_functions:")
        for function in all_virtual_functions["s_boolean_functions"]:
            print("--------------------------------",function)
        print("s_main_functions:")
        for function in all_virtual_functions["s_main_functions"]:
            print("--------------------------------",function)
        
        
      

        
    def dump_function_mapping(self):
    
        for kb in self.ctb.define_kb_dict:
        
            top_node = self.ctb.add_node_element("kb."+kb,"virtual_functions_"+str(0),"CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",{})
            function_node = self.ctb.add_node_element("virtual_functions","virtual_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",{})
            node_data =  self.ctb.main_function_mapping_dict[kb]
            self.ctb.add_leaf_element("virtual_functions","main_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
            node_data = self.ctb.one_shot_function_mapping_dict[kb]
            self.ctb.add_leaf_element("virtual_functions","one_shot_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
            node_data = self.ctb.boolean_function_mapping_dict[kb]
            self.ctb.add_leaf_element("virtual_functions","boolean_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
            node_data = self.ctb.s_one_shot_function_mapping_dict[kb]
            self.ctb.add_leaf_element("virtual_functions","s_one_shot_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
            node_data = self.ctb.s_boolean_function_mapping_dict[kb]
            self.ctb.add_leaf_element("virtual_functions","s_boolean_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
            node_data = self.ctb.s_main_function_mapping_dict[kb]
            self.ctb.add_leaf_element("virtual_functions","s_main_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",node_data)
            self.ctb.pop_node_element(function_node)
            self.ctb.pop_node_element(top_node)
            
    def dump_complete_function_map(self):
        top_node = self.ctb.add_node_element("complete_functions","complete_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",{})
        one_shot_map = {}
        boolean_map = {}
        main_map = {}
        s_one_shot_map = {}
        s_boolean_map = {}
        s_main_map = {}
        for kb in self.ctb.define_kb_dict:
          test_one_shot_map = self.ctb.one_shot_function_mapping_dict[kb].keys()
          for function in test_one_shot_map:
            if function not in one_shot_map:
              one_shot_map[function] = True
            
               
          test_boolean_map = self.ctb.boolean_function_mapping_dict[kb].keys()
          for function in test_boolean_map:
            if function not in boolean_map:
              boolean_map[function] = True
          test_main_map = self.ctb.main_function_mapping_dict[kb].keys()
          for function in test_main_map:
            if function not in main_map:
              main_map[function] = True
          test_s_one_shot_map = self.ctb.s_one_shot_function_mapping_dict[kb].keys()
          for function in test_s_one_shot_map:
            if function not in s_one_shot_map:
              s_one_shot_map[function] = True
          test_s_boolean_map = self.ctb.s_boolean_function_mapping_dict[kb].keys()
          for function in test_s_boolean_map:
            if function not in s_boolean_map:
              s_boolean_map[function] = True
          test_s_main_map = self.ctb.s_main_function_mapping_dict[kb].keys()
          for function in test_s_main_map:
            if function not in s_main_map:
              s_main_map[function] = True
        self.ctb.add_leaf_element("complete_functions","one_shot_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",one_shot_map)
        self.ctb.add_leaf_element("complete_functions","boolean_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",boolean_map)
        self.ctb.add_leaf_element("complete_functions","main_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",main_map)
        self.ctb.add_leaf_element("complete_functions","s_one_shot_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",s_one_shot_map)
        self.ctb.add_leaf_element("complete_functions","s_boolean_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",s_boolean_map)
        self.ctb.add_leaf_element("complete_functions","s_main_functions","CFL_NULL","CFL_NULL","CFL_NULL","CFL_NULL",s_main_map)
        self.ctb.pop_node_element(top_node)
        
        
        
    def list_kbs(self):
        return self.ctb.define_kb_dict.keys()
        
    def list_templates(self,kb_name:str=None):
       if kb_name is None:
           raise ValueError("Valid kb name is required")
       else:
           node_name = "kb."+kb_name+".TEMPLATE.MASTER"
           return self.ctb.ds.yaml_data[node_name]["node_dict"]
       
    def list_all_templates(self):
        return_value = {}
        for kb in self.ctb.define_kb_dict:
            return_value[kb] = self.list_templates(kb_name=kb)
        return return_value