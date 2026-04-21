import time
from datetime import datetime, timezone

import yaml
from pathlib import Path

from typing import List, Union, Dict, Any


from .ct_functions.virtual_main_functions import VirtualMainFunctions
from .ct_functions.virtual_one_shot_functions import VirtualOneShotFunctions
from .ct_functions.virtual_boolean_functions import VirtualBooleanFunctions
from .ct_functions.virtual_s_one_shot_functions import VirtualSOneShotFunctions
from .ct_functions.virtual_s_boolean_functions import VirtualSBooleanFunctions
from .ct_functions.virtual_s_main_functions import VirtualSMainFunctions    
from .ct_functions.cfl_main_functions import CFLMainFunctions
from .ct_functions.cfl_one_shot_functions import CFLOneShotFunctions
from .ct_functions.cfl_boolean_functions import CFLBooleanFunctions
from .ct_functions.cfl_s_one_shot_functions import CFLSOneShotFunctions
from .ct_functions.cfl_s_boolean_functions import CFLSBooleanFunctions
from .ct_functions.cfl_s_main_functions import CFLSMainFunctions
from .ct_events.ct_timer import CT_Timer
from .ct_engine.ct_engine import CT_Engine
from .sequence_data.data_storeage import SequenceDataStorage
from .supervisor_failure_counter import SupervisorFailureCounter
from .data_flow.token_dictionary import TokenDictionary
from .template_functions import TemplateFunctions
from .sequence_data.exception_handler import ExceptionCatchHandler


class ChainTreeRun():
    """
    This class is designed to run a chain tree.
    """
    @classmethod
    def get_root_node_id(cls,system_kb):
        return "kb." + system_kb + ".GATE_root._0"
    
    def __init__(self, wait_seconds,handle_dict = None,LispSequencer=None):
        
        
        if LispSequencer is None:
            raise ValueError("LispSequencer is required")
        self.LispSequencer = LispSequencer
        if handle_dict is None:
            handle_dict = {}
        self.handle_dict = handle_dict
        self.valid_return_codes = ["CFL_CONTINUE","CFL_HALT","CFL_TERMINATE","CFL_RESET","CFL_DISABLE",
                              "CFL_TERMINATE_SYSTEM","CFL_TEMPLATE_UNLOAD", "CFL_SKIP_CONTINUE"]
        self.s_return_control_codes = [
            "CFL_CONTINUE", "CFL_TERMINATE", "CFL_DISABLE", "CFL_TERMINATE_SYSTEM",
         "CFL_FUNCTION_RETURN","CFL_FUNCTION_HALT","CFL_FUNCTION_TERMINATE"
        ]
        self.Vm = VirtualMainFunctions(self,self.valid_return_codes)
        self.Vo = VirtualOneShotFunctions(self,self.valid_return_codes)
        self.Vb = VirtualBooleanFunctions(self,self.valid_return_codes)
        self.Vso = VirtualSOneShotFunctions(self,self.s_return_control_codes)
        self.Vsb = VirtualSBooleanFunctions(self,self.s_return_control_codes)
        self.Vsm = VirtualSMainFunctions(self,self.s_return_control_codes)
        self.cfl_one_shot_functions = CFLOneShotFunctions(self.Vo)
        self.cfl_s_one_shot_functions = CFLSOneShotFunctions(self.Vso)
        self.cfl_boolean_functions = CFLBooleanFunctions(self.Vb)
        self.cfl_s_boolean_functions = CFLSBooleanFunctions(self.Vsb)
        self.cfl_main_functions = CFLMainFunctions(self.Vm)
        self.cfl_s_main_functions = CFLSMainFunctions(self.Vsm)
           
        
        self.wait_seconds = wait_seconds
    
        self.registered_yaml_dicts = {}
        self.registered_python_dicts = {}
        self.registered_kbs_dict = {}
        self.python_dict = {}
       
        self.wait_seconds = wait_seconds
     
        
        self.handle_dict["chain_tree"] = self 
        self.ct_engine = CT_Engine(self.handle_dict)
        self.token_dictionary = TokenDictionary()
        self.template_functions = TemplateFunctions(self,self.ct_engine)
        self.load_system_functions()
    
   

    
    def load_yaml_file(self, yaml_file_name:str) -> dict:
        """
        Load a YAML file and store its structure self.python_dict
        
        Args:
            yaml_name: Key name to store this YAML data under
            yaml_file_name: Path to the YAML file
            
        Returns:
            Dictionary entry created for this YAML file
        """
        yaml_path = Path(yaml_file_name)
        
        if not yaml_path.exists():
            raise FileNotFoundError(f"YAML file not found: {yaml_path}")
        
        # Load the YAML data
        with open(yaml_path, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        self.python_dict = yaml_data
    


    def add_one_shot_function(self,function_name,function,description=""):
        self.Vo.add_one_shot_function_python(function_name,function,description)
        
    def add_boolean_function(self,function_name,function,description=""):
        self.Vb.add_boolean_function_python(function_name,function,description)
    
    def add_main_function(self,function_name,function,description=""):
        self.Vm.add_main_function_python(function_name,function,description)
    
    def add_s_one_shot_function(self,function_name,function,description=""):
        self.Vso.add_s_one_shot_function_python(function_name,function,description)
    
    def add_s_boolean_function(self,function_name,function,description=""):
        self.Vsb.add_s_boolean_function_python(function_name,function,description)
    
    def add_s_main_function(self,function_name,function,description=""):
        self.Vsm.add_s_main_function_python(function_name,function,description)



        
    def load_system_functions(self):
        self.cfl_main_functions.load_default_main_functions()
        self.cfl_one_shot_functions.load_default_one_shot_functions()
        self.cfl_boolean_functions.load_default_boolean_functions()
        self.cfl_s_one_shot_functions.load_default_s_one_shot_functions()
        self.cfl_s_boolean_functions.load_default_s_boolean_functions()
        self.cfl_s_main_functions.load_default_s_main_functions()
             
   
        
 

    def verify_one_shot_functions(self):
        key = "complete_functions.complete_functions.complete_functions.one_shot_functions"
        data = self.python_dict[key]
        self.required_one_shot_functions = data["node_dict"]
        
        self.Vo.detect_one_shot_coverage(self.required_one_shot_functions)
    
        
    
    def verify_boolean_functions(self):
        key = "complete_functions.complete_functions.complete_functions.boolean_functions"
        data = self.python_dict[key]
        self.required_boolean_functions = data["node_dict"]
    
        self.Vb.detect_boolean_coverage(self.required_boolean_functions)
    
    
    def verify_main_functions(self):
        key = "complete_functions.complete_functions.complete_functions.main_functions"
        data = self.python_dict[key]
        self.required_main_functions = data["node_dict"]
        self.Vm.detect_main_coverage(self.required_main_functions)
    
    
    
    def verify_s_one_shot_functions(self):
        key = "complete_functions.complete_functions.complete_functions.s_one_shot_functions"
        data = self.python_dict[key]
        self.required_s_one_shot_functions = data["node_dict"]
        self.Vso.detect_s_one_shot_coverage(self.required_s_one_shot_functions)
    
    def verify_s_boolean_functions(self):
        key = "complete_functions.complete_functions.complete_functions.s_boolean_functions"
        data = self.python_dict[key]
        self.required_s_boolean_functions = data["node_dict"]
        self.Vsb.detect_s_boolean_coverage(self.required_s_boolean_functions)
    
    def verify_s_main_functions(self):
        key = "complete_functions.complete_functions.complete_functions.s_main_functions"
        data = self.python_dict[key]
        self.required_s_main_functions = data["node_dict"]
        self.Vsm.detect_s_main_coverage(self.required_s_main_functions)
         
    
  
    
   
        
    def debug_s_function( handle,message, node=None, event_id=None, event_data=None):
      timestamp = datetime.now().isoformat()
      print(f"[{timestamp}] DEBUG: {message}")
      if node is not None or event_id is not None:
          print(f"  Node: {node}, Event: {event_id}")    
    
    
    def assign_kbs(self,kb_list):
        self.kb_list = kb_list
        
        
            
    def run_multiple_kbs(self,kb_list):
        """
        Run multiple knowledge bases concurrently.
        They share the same timer, event mask, and node dictionary.
        Each KB can stop independently.
        
        Args:
            kb_list: List of KB names to run
            start_nodes: Optional dict mapping KB names to their start nodes
        """
        
        self.kb_list = kb_list
        
        # Shared initialization
        self.node_subscribed_events = {}
        self.subscribed_events = {}
       
        # Verify functions once (shared)
        self.verify_one_shot_functions()
        self.verify_boolean_functions()
        self.verify_main_functions()
        self.verify_s_one_shot_functions()
        self.verify_s_boolean_functions()
        self.verify_s_main_functions()
        
        
        # Setup each KB
        all_start_nodes = []
        self.kb_root_nodes = {}
        self.active_kbs = {}
        
        for kb in self.kb_list:
            start_node = self.get_root_node_id(kb)
            self.kb_root_nodes[kb] = start_node
            all_start_nodes.append(start_node)
            
            self.active_kbs[kb] = {
                'running': True,
                'start_node': start_node,
                'kb_name': kb
            }
            
            # Setup runtime data for this KB's root node
            self.ct_engine.setup_initial_runtime_data_fields(start_node)
            self.ct_engine.reset_start_node(start_node)
        
        # Use the first KB's start node as the primary for the shared timer
    
        self.ct_timer = CT_Timer(self.wait_seconds)
        
        # Initialize shared components
        self.s_lisp_engine = self.LispSequencer(
            handle=self,
            run_function=self.ct_engine.run_s_expression,
            debug_function=self.debug_s_function,
            control_codes=self.s_return_control_codes
        )
        self.ct_engine.initialize_ct_walker()
        self.sequence_storage = SequenceDataStorage(self)
        self.exception_catch_storage = ExceptionCatchHandler(self, self.ct_engine)
        self.token_dictionary.reset_token_dictionary()
        self.template_functions = TemplateFunctions(self, self.ct_engine)
        self.template_functions.reset_instanciated_template_functions()
        
        # Build tree for each KB
        for start_node in all_start_nodes:
            self.sequence_storage.build_tree(start_node)
        for kb in self.kb_list:
            self.exception_catch_storage.exception_tree[kb] = {}
        
        # Main loop - continues while any KB is still running
        self.running = True
        while self.running and self.active_kbs:
            # Shared event mask
            mask = self.token_dictionary.get_current_event_mask()
            self.ct_timer.add_dict_dict("event_mask", mask)
            
            # Single timer tick (shared)
        
            self.ct_timer.timer_tick(all_start_nodes)
            
            # Process all events in the queue
            while self.ct_timer.event_queue_length() > 0:
                event = self.ct_timer.pop_event()
                
                # Determine which KB this event belongs to
                event_node_id = event["node_id"]
                owning_kb = self._find_kb_for_node(event_node_id)
                
                if owning_kb and owning_kb in self.active_kbs:
                    kb_state = self.active_kbs[owning_kb]
                    
                    if kb_state['running']:
                        # Set context for this KB
                        self.root_node_id = kb_state['start_node']
                        self.system_kb = owning_kb
                        
                        return_value = self.ct_engine.execute_event(
                            event["node_id"],
                            event["event_id"],
                            event["event_data"]
                        )
                        
                        if return_value == False:
                            kb_state['running'] = False
                            print(f"KB {owning_kb} stopped running")
                            # Remove this KB from active set
                            del self.active_kbs[owning_kb]
                else:
                    # Event doesn't belong to any known KB - this is an error
                   pass
            
            # Check if all KBs have stopped
            if not self.active_kbs:
                self.running = False
                print("All KBs have stopped")


    def _find_kb_for_node(self, node_id):
        """
        Determine which KB a node belongs to based on the node_id prefix.
        Assumes node_id format like "kb.kb_name.GATE_root._0"
        """
        if not hasattr(self, 'kb_root_nodes'):
            return None
        
        for kb, root_node in self.kb_root_nodes.items():
            # Check if node_id starts with the KB prefix
            if node_id.startswith(f"kb.{kb}."):
                return kb
        
        return None


    def send_event_to_all_kbs(self, event_id, event_data):
        """
        Send the same event to all currently running KBs.
        Uses the shared timer.
        """
        if not hasattr(self, 'active_kbs'):
            raise RuntimeError("No KBs are currently running")
        
        for kb, kb_state in list(self.active_kbs.items()):
            if kb_state['running']:
                root_node = kb_state['start_node']
                self.ct_timer.add_event(root_node, event_id, event_data)


    def send_event_to_specific_kb(self, kb_name, event_id, event_data):
        """
        Send an event to a specific KB.
        """
        if not hasattr(self, 'kb_root_nodes') or kb_name not in self.kb_root_nodes:
            raise ValueError(f"KB {kb_name} not found")
        
        if kb_name in self.active_kbs and self.active_kbs[kb_name]['running']:
            root_node = self.kb_root_nodes[kb_name]
            self.ct_timer.add_event(root_node, event_id, event_data)
        else:
            print(f"KB {kb_name} is not currently running")
                    
    def send_immediate_event(self,node_id,event_id,event_data):       
        
        node = self.python_dict[node_id]
        if node is None:
            raise ValueError(f"Node {node_id} not found")
        ct_control = node["ct_control"]
        if ct_control is None:
            raise ValueError(f"ct_control not found for node {node_id}")
        if ct_control["enabled"] == False:
            return
        if ct_control["initialized"] == False:
            return
        self.ct_timer.add_immediate_event(node_id,event_id,event_data)
            
        #def find_one_shot_function(self,function_name):
        #    function_code = self.virtual_functions.find_one_shot_function(function_name)
    #   return function_code
    
    def send_system_event(self,event_id,event_data):
        self.ct_timer.add_event(self.root_node_id,event_id,event_data)
        
    def send_system_named_event(self,node_id,event_id,event_data):
        node = self.python_dict[node_id]
        if node is None:
            raise ValueError(f"Node {node_id} not found")
    
        ct_control = node["ct_control"]
        if ct_control is None:
            raise ValueError(f"ct_control not found for node {node_id}")
        if ct_control["enabled"] == False:
            return
        if ct_control["initialized"] == False:
            return  
        
        self.ct_timer.add_event(node_id,event_id,event_data)
        
    def subscribe_events(self,node_id,event_list):
        node = self.python_dict[node_id]
        if node is None:
            raise ValueError(f"Node {node_id} not found")
        if "ct_control" in node:
            if node["ct_control"]["enabled"] == False:
                return
            if node["ct_control"]["initialized"] == False:
                return
            
        for event_id in event_list:
            if self.check_for_ancestor_node_subscription(node_id,event_id):
                continue
            if event_id not in self.subscribed_events:
                self.subscribed_events[event_id] = {}
            if node_id not in self.node_subscribed_events:
                
                self.node_subscribed_events[node_id] = {}
            
            self.node_subscribed_events[node_id][event_id] = True
            self.subscribed_events[event_id][node_id] = True
            
            
    def unsubscribe_events(self,node_id,event_list):
        for event_id in event_list:
            if node_id not in self.subscribed_events[event_id]:
                continue
        
            del self.subscribed_events[event_id][node_id]
            
        
    def publish_event(self,event_id,event_data):
        if event_id not in self.subscribed_events:
            return
        for node_id in self.subscribed_events[event_id]:
            self.send_system_named_event(node_id,event_id,event_data)
            
        
    def unsubscribe_all_events_for_a_node(self,node_id):
        
        if node_id not in self.node_subscribed_events:
            return
        event_list = self.node_subscribed_events[node_id].keys()
        self.unsubscribe_events(node_id,event_list)
        self.node_subscribed_events.pop(node_id)
    
    
    def check_for_ancestor_node_subscription(self,node_id,event_id):
        
        node = self.python_dict[node_id]
        if node is None:
            raise ValueError(f"Node {node_id} not found")
    
        while 'label_dict' in node:
            node = self.python_dict[node["label_dict"]["parent_ltree_name"]]
            node_id = node["label_dict"]["ltree_name"]
            
            if node_id in self.node_subscribed_events:
                if event_id in self.node_subscribed_events[node_id]:
                    return True
                    
            node = node["label_dict"]["parent_ltree_name"]
        
        return False
    
    
    
    
    def find_state_number(self,state_name,state_names):
        if state_name not in state_names:
            raise ValueError(f"State {state_name} not found in state names {state_names}")
        return state_names.index(state_name)
    
    
    def create_supervisor_failure_counter(self,max_failures,time_window_seconds):
        return SupervisorFailureCounter(max_failures,time_window_seconds)
    
######################### DATA FLOW FUNCTIONS #########################
    