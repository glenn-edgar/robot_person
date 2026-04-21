from .column_flow import ColumnFlow

class StateMachine(ColumnFlow):
    def __init__(self, ds, ctb):
        ColumnFlow.__init__(self, ds, ctb)
        self.ds = ds
        self.ctb = ctb
        self.sm_stack = []
        self.sm_name_dict = {}
     
    def add_sm_name_dict(self,sm_name:str):
        if sm_name in self.sm_name_dict:
            raise ValueError(f"State machine {sm_name} already exists")
        self.sm_name_dict[sm_name] = True
    
    def check_for_balance_sm(self):
        if len(self.sm_stack) != 0:
            
            raise ValueError(f"State machines have not been closed: {self.sm_stack.keys()}")
    
        
    def define_state_machine(self,column_name:str,sm_name:str,state_names:list[str],initial_state:str,auto_start:bool,
                             aux_function_name:str="CFL_STATE_MACHINE_NULL"):
        
        self.add_sm_name_dict(sm_name)
        
        state_node = self.define_column(column_name,  main_function ="CFL_STATE_MACHINE_MAIN",
                      initialization_function ="CFL_STATE_MACHINE_INIT", termination_function ="CFL_STATE_MACHINE_TERM", 
                      aux_function =aux_function_name,column_data= {},
                      auto_start=auto_start,label="SM_"+sm_name[:4])
                      
        self.__initialize_state_links(state_node,sm_name,state_names,initial_state)
        self.sm_stack.append(sm_name)
        return state_node
        
        
    def define_state(self,state_name:str,column_data:dict=None):
        if not isinstance(state_name, str):
            raise TypeError("State name must be a string")

        if column_data is None:
            column_data = {}
        if not isinstance(column_data, dict):
            raise TypeError("Column data must be a dictionary")
        state_node = self.define_column(state_name, column_data=column_data,label= "STATE_"+state_name[:4])
        self._add_state_link(state_name,state_node)
        return state_node
    
    
    def terminate_state_machine(self,sm_node_id:str):
        if not isinstance(sm_node_id, str):
            raise TypeError("State machine node id must be a string")
        
        node_date = { "sm_node_id": sm_node_id}
        self.asm_one_shot_handler(one_shot_fn="CFL_TERMINATE_STATE_MACHINE",one_shot_data=node_date)
        
    def reset_state_machine(self,sm_node_id:str):
        if not isinstance(sm_node_id, str):
            raise TypeError("State machine node id must be a string")
        node_date = { "sm_node_id": sm_node_id}
        self.asm_one_shot_handler(one_shot_fn="CFL_RESET_STATE_MACHINE",one_shot_data=node_date)
    
    def change_state(self,sm_node_id:str,new_state:str,sync_event_id:str=None):
        if not isinstance(sm_node_id, str):
            raise TypeError("State machine node id must be a string")
        if not isinstance(new_state, str):
            raise TypeError("New state must be a string")
        if len(self.sm_stack) == 0:
            raise ValueError("State machine not defined")
        node_date = { "sm_node_id": sm_node_id, "new_state": new_state, "sync_event_id": sync_event_id}
        self.asm_one_shot_handler(one_shot_fn="CFL_CHANGE_STATE",one_shot_data=node_date)
        
   
        
    def end_state_machine(self,state_node:str,sm_name:str):
        if len(self.sm_stack) == 0:
            raise ValueError("State machine not defined")
        poped_sm = self.sm_stack.pop()
        
        if poped_sm != sm_name:
            raise ValueError("State machine mismatch")
        ref_data = self.ds.yaml_data[state_node]
        if "state_links" not in ref_data["label_dict"]:
            raise ValueError("state machine not found")
        if len(ref_data["label_dict"]["state_names"]) != len(ref_data["label_dict"]["defined_states"]):
            raise ValueError("State states are not defined")
        for state_name in ref_data["label_dict"]["state_names"]:
            if state_name not in ref_data["label_dict"]["defined_states"]:
                raise ValueError(f"State link not found for {state_name}")
        self.end_column(state_node)    
        
    def __initialize_state_links(self, state_node :str, sm_name :str, state_names :list[str],initial_state:str):
        if not isinstance(state_node, str):
            raise TypeError("State node must be a string")
        if not isinstance(sm_name, str):
            raise TypeError("State machine name must be a string")
        if not isinstance(state_names, list):
            raise TypeError("State names must be a list")
        ### sm data is placed in label dictionary
        ref_data = self.ds.yaml_data[state_node]
        
        if initial_state not in state_names:
            raise ValueError(f"Initial state {initial_state} not found in state names {state_names}")
        ref_data["node_dict"]["current_state"] = initial_state
        ref_data["label_dict"]["initial_state"] = initial_state
        ref_data["label_dict"]["sm_name"] = sm_name
        ref_data["label_dict"]["state_links"] = []
        ref_data["label_dict"]["state_names"] = state_names
        ref_data["label_dict"]["defined_states"] = []
        
        self.ds.yaml_data[state_node] = ref_data
        
        
        
        
    def _add_state_link(self, state,ltree_name :str):
        if len(self.sm_stack) == 0:
            raise ValueError("State machine not defined")
        if not isinstance(ltree_name, str):
            raise TypeError("ltree_name must be a string")
        ref_node = self.ctb.ltree_stack[-2]
        ref_data = self.ds.yaml_data[ref_node]
        if "state_links" not in ref_data["label_dict"]:
            raise ValueError("state machine not found")
        
        if state not in ref_data["label_dict"]["state_names"]:
            raise ValueError("State not defined")
        if state in ref_data["label_dict"]["defined_states"]:
            raise ValueError("State already defined")
        ref_data["label_dict"]["defined_states"].append(state)
        ref_data["label_dict"]["state_links"].append(ltree_name)
        self.ds.yaml_data[ref_node] = ref_data