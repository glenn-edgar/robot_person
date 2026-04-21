from .column_flow import ColumnFlow

class VerifyCfLinks(ColumnFlow):
    
    def __init__(self, ds, ctb):
        self.ds = ds
        self.ctb = ctb
        ColumnFlow.__init__(self, ds, ctb)
        
        
   
    def asm_verify(self,verify_fn ,fn_data=None, reset_flag = False, error_fn = "CFL_NULL", error_data = None ):
        
        
        
        
        element_data = {}
        element_data["fn_data"] = fn_data
        element_data["reset_flag"] = reset_flag    
        element_data["fn"] = verify_fn
        element_data["error_function"] = error_fn
        if error_fn != None:
            self.ctb.add_one_shot_function(error_fn)
            element_data["error_data"] = error_data
        else:
            element_data["error_function"] = None
            element_data["error_data"] = None
    
        
       
        return self.define_column_link(main_function_name="CFL_VERIFY",
                            aux_function_name=verify_fn,
                            initialization_function_name="CFL_VERIFY_INIT",
                            termination_function_name="CFL_VERIFY_TERM",
                            node_data=element_data)
        
        
        
    def asm_verify_timeout(self,time_out,reset_flag = False,error_fn = "CFL_NULL",error_data = None):
        fn_data = {}
        fn_data["time_out"] = time_out
        fn_data["current_time"] = 0
        
        return self.asm_verify("CFL_VERIFY_TIME_OUT",fn_data, reset_flag, error_fn, error_data )
        
       
   
    