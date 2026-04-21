from .column_flow import ColumnFlow



class WaitCfLinks(ColumnFlow):
    
    def __init__(self, data_structures, ctb):
        self.ds = data_structures
        self.ctb = ctb
        ColumnFlow.__init__(self, data_structures, ctb)
        

  
    def asm_wait(self,  wait_fn ,wait_fn_data, reset_flag = False, timeout=None,time_out_event="CF_TIMER_EVENT",
                 error_fn =None,error_data = None):
        element_data = {}
        element_data["wait_fn_data"] = wait_fn_data
        element_data["reset_flag"] = reset_flag
        element_data["timeout"] = timeout
        element_data["time_out_event"] = time_out_event 
        element_data["error_function"] = error_fn
        if error_data == None:
            error_data = {}
        element_data["error_data"] = error_data
        
        if error_fn is not None:
            self.ctb.add_one_shot_function(error_fn)
        
        
        return self.define_column_link(main_function_name="CFL_WAIT",
                            aux_function_name=wait_fn,
                            initialization_function_name="CFL_WAIT_INIT",
                            termination_function_name="CFL_WAIT_TERM",
                            node_data=element_data)
       
        
    
   

    def asm_wait_for_event(self,event_id,event_count = 1,reset_flag = False,timeout=None,
                           error_fn = "CFL_NULL",time_out_event ="CF_TIMER_EVENT",error_data = None):
        element_data = {}
        element_data["event_id"] = event_id
        element_data["event_count"] = event_count
        return self.asm_wait("CFL_WAIT_FOR_EVENT",element_data,reset_flag,timeout,time_out_event,error_fn,error_data)
    
 
    
    def asm_wait_time(self,time_delay):
        element_data = {}
        element_data["time_delay"] = time_delay #time delay in seconds
    
        return self.define_column_link(main_function_name="CFL_WAIT_TIME",
                
                            aux_function_name="CFL_NULL",
                            initialization_function_name="CFL_WAIT_TIME_INIT",
                            termination_function_name="CFL_NULL",
                            node_data=element_data)
 