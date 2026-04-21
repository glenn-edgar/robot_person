from operator import not_
from .column_flow import ColumnFlow

class SequenceTil(ColumnFlow):
    def __init__(self, ds, ctb):
        ColumnFlow.__init__(self, ds, ctb)
        self.ds = ds
        self.ctb = ctb
        
        
    def define_sequence_start_node(self,column_name:str,main_function ="CFL_SEQUENCE_START_MAIN",
                                   initialization_function ="CFL_SEQUENCE_START_INIT",
                                   termination_function ="CFL_SEQUENCE_START_TERM",
                                   aux_function ="CFL_NULL",finalize_function="CFL_NULL",
                                   user_data:dict = {},auto_start = False):
        if not isinstance(finalize_function, str):
            raise TypeError("finalize_function must be a string")
        self.ctb.add_one_shot_function(finalize_function)
        column_data = {}
        column_data["finalize_function"] = finalize_function
        column_data["user_data"] = user_data
        self.sequence_active = True
        return_node = self.define_column(column_name,main_function,initialization_function,termination_function,
                                         aux_function,column_data,auto_start,label="SEQ_ST")
        
        return return_node
    
    def define_sequence_til_pass_node (self,column_name:str,main_function ="CFL_SEQUENCE_PASS_MAIN",
                                   initialization_function ="CFL_SEQUENCE_PASS_INIT",
                                   termination_function ="CFL_SEQUENCE_PASS_TERM",
                                   aux_function ="CFL_NULL",finalize_function="CFL_NULL",user_data:dict = {},auto_start = False):
        
        if not isinstance(finalize_function, str):
            raise TypeError("finalize_function must be a string")
        self.ctb.add_one_shot_function(finalize_function)
        column_data = {}
        column_data["finalize_function"] = finalize_function
        column_data["user_data"] = user_data
        
        return_node = self.define_column(column_name,main_function,initialization_function,termination_function,aux_function,
                                         column_data,auto_start,"SEQ_PASS")
        self.sequence_dict[return_node] = True
        return return_node
    
    def define_sequence_til_fail_node (self,column_name:str,main_function =f"CFL_SEQUENCE_FAIL_MAIN",
                                   initialization_function ="CFL_SEQUENCE_FAIL_INIT",
                                   termination_function ="CFL_SEQUENCE_FAIL_TERM",
                                   aux_function ="CFL_NULL",finalize_function="CFL_NULL",user_data:dict = {},auto_start = False):
        if not isinstance(finalize_function, str):
            raise TypeError("finalize_function must be a string")
        self.ctb.add_one_shot_function(finalize_function)
        column_data = {}
        column_data["finalize_function"] = finalize_function
        column_data["user_data"] = user_data
        return_node = self.define_column(column_name,main_function,initialization_function,termination_function,
                                        aux_function,column_data,auto_start,label="SEQ_FAIL")
        self.sequence_dict[return_node] = True
        return return_node
    
    
    def define_supervisor_node(self, column_name:str,  main_function ="CFL_SUPERVISOR_MAIN",
                              initialization_function ="CFL_SUPERVISOR_INIT", termination_function ="CFL_SUPERVISOR_TERM", 
                              aux_function ="CFL_NULL",user_data:dict = None,termination_type:str="ONE_FOR_ONE",
                              reset_limited_enabled:bool=False,max_reset_number:int=1,reset_window:int=10,auto_start = False,
                              finalize_function:str="CFL_NULL",finalize_function_data:dict={},label:str="SUP"):
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
        if not isinstance(termination_type, str):
            raise TypeError("Termination type must be a string")
        if not isinstance(reset_limited_enabled, bool):
            raise TypeError("Reset limited enabled must be a boolean")
        if not isinstance(max_reset_number, int):
            raise TypeError("Max reset number must be an integer")
        if not isinstance(reset_window, int):
            raise TypeError("Reset window must be an integer")
        supervisor_data = {
                        "termination_type": termination_type, 
                       "reset_limited_enabled": reset_limited_enabled, "max_reset_number": max_reset_number, "reset_window": reset_window,
                       "finalize_function": finalize_function, "finalize_function_data": finalize_function_data}
        column_data = {"user_data": user_data,"supervisor_data": supervisor_data}
        self.ctb.add_one_shot_function(finalize_function)
        return self.define_column(column_name,main_function,initialization_function,termination_function,
                                  aux_function,column_data,auto_start,label)
                                        
    
    def define_supervisor_one_for_one_node(self, column_name:str,  aux_function ="CFL_NULL",
                                           user_data:dict = {},reset_limited_enabled:bool=False,
                                           max_reset_number:int=1,reset_window:int=10,auto_start = False,
                                           finalize_function:str="CFL_NULL",finalize_function_data:dict={}):
        
        return self.define_supervisor_node(column_name = column_name, aux_function= aux_function, user_data =user_data,
                                           termination_type="ONE_FOR_ONE", 
                                           reset_limited_enabled=reset_limited_enabled,
                                           max_reset_number=max_reset_number, reset_window=reset_window, auto_start=auto_start,
                                           finalize_function=finalize_function,
                                           finalize_function_data=finalize_function_data,label="SUP_1_1")
    
    def define_supervisor_one_for_all_node(self, column_name:str,    aux_function ="CFL_NULL", user_data:dict = {}
                                           ,reset_limited_enabled:bool=False,max_reset_number:int=1,
                                           reset_window:int=10, auto_start = False,
                                           finalize_function:str="CFL_NULL",
                                           finalize_function_data:dict={}): 
        
         return self.define_supervisor_node(column_name = column_name, aux_function= aux_function, user_data =user_data,
                                            termination_type="ONE_FOR_ALL", 
                                           reset_limited_enabled=reset_limited_enabled,
                                           max_reset_number=max_reset_number, reset_window=reset_window, auto_start=auto_start,
                                           finalize_function=finalize_function,
                                           finalize_function_data=finalize_function_data,label="SUP_1_ALL")
 
    def define_supervisor_rest_for_all_node(self, column_name:str,  aux_function ="CFL_NULL", user_data:dict = {},
                                            reset_limited_enabled:bool=False,max_reset_number:int=1,reset_window:int=10,auto_start = False,
                                            finalize_function:str="CFL_NULL",finalize_function_data:dict={}):
                                                
        return self.define_supervisor_node(column_name = column_name, aux_function= aux_function, user_data =user_data,
                                           termination_type="REST_FOR_ALL", 
                                           reset_limited_enabled=reset_limited_enabled,
                                           max_reset_number=max_reset_number, reset_window=reset_window, auto_start=auto_start,
                                           finalize_function=finalize_function,
                                           finalize_function_data=finalize_function_data,label="SUP_REST_ALL")
    
    def end_sequence_node(self,column_name:str):
        if column_name not in self.sequence_dict:
            raise ValueError("Sequence is not active")
        del self.sequence_dict[column_name] 
        self.end_column(column_name)
        self.join_sequence_element(column_name)
    
    def mark_sequence_true_link(self,parent_node_name:str,data:dict = {}):
        result = True
        node_data = {"parent_node_name":parent_node_name,"result":"true","data":data}
        self.asm_one_shot_handler("CFL_MARK_SEQUENCE",node_data)

    
    def mark_sequence_false_link(self,parent_node_name:str,data:dict = {}):
        result = False
        node_data = {"parent_node_name":parent_node_name,"result":"false","data":data}
        self.asm_one_shot_handler("CFL_MARK_SEQUENCE",node_data)
        
    def join_sequence_element(self,parent_node_name:str):
        return self.define_column_link(main_function_name="CFL_JOIN_SEQUENCE_ELEMENT",
                                       aux_function_name="CFL_NULL",
                                       initialization_function_name="CFL_NULL",
                                       termination_function_name="CFL_NULL",
                                       node_data={"parent_node_name":parent_node_name})

    
    # aux_function_name is used to override default behavior
    def exception_catch(self,column_name:str,
                        aux_function_name:str,
                        aux_function_data:dict,
                        exception_id_list:list[str],
                        logging_function_name:str,
                        logging_function_data:dict={},
                        default_exception_handler_name:str="CFL_NULL",
                        default_exception_handler_data:dict={},auto_start:bool=True):
        
        
        if not isinstance(column_name, str):
            raise TypeError("Column name must be a string")
        if not isinstance(aux_function_name, str):
            raise TypeError("Exception function name must be a string")
        if not isinstance(aux_function_data, dict):
            raise TypeError("Aux function data must be a dictionary")
        if not isinstance(exception_id_list, list):
            raise TypeError("Exception id list must be a list")
        if not isinstance(logging_function_name, str):
            raise TypeError("Logging function name must be a string")
        if not isinstance(logging_function_data, dict):
            raise TypeError("Logging function data must be a dictionary")
        if not isinstance(default_exception_handler_name, str):
            raise TypeError("Default exception handler name must be a string")
        if not isinstance(default_exception_handler_data, dict):
            raise TypeError("Default exception handler data must be a dictionary")
    
        
        self.ctb.add_one_shot_function(logging_function_name)
        self.ctb.add_boolean_function(default_exception_handler_name)
        column_data = {"exception_list": exception_id_list,
                       "logging_function_name": logging_function_name,
                       "logging_function_data": logging_function_data,
                       "aux_function_name": aux_function_name,
                       "aux_function_data": aux_function_data,
                       "default_exception_handler_name": default_exception_handler_name,
                       "default_exception_handler_data": default_exception_handler_data,
                       "recovery_dict": {}}
        
        return self.define_column(column_name,
                                  aux_function=aux_function_name,
                                  main_function="CFL_EXCEPTION_CATCH_MAIN",
                                  initialization_function="CFL_EXCEPTION_CATCH_INIT",
                                  termination_function="CFL_EXCEPTION_CATCH_TERM",
                                  column_data=column_data,label= "EXCEP_HDL",auto_start=auto_start)
    
    def asm_raise_exception(self,exception_id:str,exception_data:dict = {}):
        if not isinstance(exception_id, str):
            raise TypeError("Exception id must be a string")
        if not isinstance(exception_data, dict):
            raise TypeError("Exception data must be a dictionary")
    
        return self.asm_one_shot_handler("CFL_RAISE_EXCEPTION",{"exception_id": exception_id, "exception_data": exception_data})
    
    
    def add_exception_recovery_link(self, except_node_id:str,link_id:str, disable_columns:list,enable_columns:list):
        except_node = self.ds.yaml_data[except_node_id]
        
 
        if except_node is None:
            raise ValueError("Exception node not found")
        if "label_dict" not in except_node:
            raise ValueError("Label dict not found in exception node")
        if "links" not in except_node["label_dict"]:
            raise ValueError("Links not found in exception node")
        if link_id not in except_node["label_dict"]["links"]:
            raise ValueError("Link id not found in exception node")
        for column in disable_columns:
            if column not in except_node["label_dict"]["links"]:
                raise ValueError("Column not found in exception node links")
        for column in enable_columns:
            if column not in except_node["label_dict"]["links"]:
                raise ValueError("Column not found in exception node links")
        
        node_dict = except_node["node_dict"]["column_data"]
        except_recover_dict = node_dict["recovery_dict"]
        if except_recover_dict is None:
            raise ValueError("Except recover dict not found in exception node")
        if link_id in except_recover_dict:
            raise ValueError("Link id already exists in exception node")
        except_recover_dict[link_id] = {"disable_columns": disable_columns, "enable_columns": enable_columns}
        
        
    def finalize_exception_recovery_links(self,except_node_id:str):
        except_node = self.ds.yaml_data[except_node_id]
        if except_node is None:
            raise ValueError("Exception node not found")
        
        if "node_dict" not in except_node:
            raise ValueError("Node dict not found in exception node")
        
        except_recover_dict = except_node["node_dict"]["column_data"]["recovery_dict"]
        if except_recover_dict is None:
            raise ValueError("Except recover dict not found in exception node")
        
        for link_id in except_node["label_dict"]["links"]:
            if link_id not in except_recover_dict:
                raise ValueError("Link id not found in exception recover dict")
            
        for link_id in except_recover_dict:
            if link_id not in except_node["label_dict"]["links"]:
                raise ValueError("Link id not found in exception node links")
        
    def asm_turn_heartbeat_on(self,parent_node_name:str,time_out:int):
        return self.asm_one_shot_handler("CFL_TURN_HEARTBEAT_ON",{"parent_node_name":parent_node_name,"time_out":time_out})
    
    def asm_turn_heartbeat_off(self,parent_node_name:str):
        return self.asm_one_shot_handler("CFL_TURN_HEARTBEAT_OFF",{"parent_node_name":parent_node_name})
    
    def asm_heartbeat_event(self,parent_node_name:str):
        return self.asm_one_shot_handler("CFL_HEARTBEAT_EVENT",{"parent_node_name":parent_node_name})
    
