from .column_flow import ColumnFlow


class BasicCfLinks(ColumnFlow):
    
    def __init__(self, data_structures, ctb):
        self.ds = data_structures
        self.ctb = ctb
        ColumnFlow.__init__(self, data_structures, ctb)
        

 

    

        
    def asm_one_shot_handler(self,one_shot_fn,one_shot_data):
        self.define_column_link(main_function_name="CFL_DISABLE",
                            initialization_function_name=one_shot_fn,
                            aux_function_name="CFL_NULL",
                            termination_function_name="CFL_NULL",
                            node_data=one_shot_data)

    def asm_bidirectional_one_shot_handler(self,one_shot_fn,termination_fn,one_shot_data):
        self.define_column_link(main_function_name="CFL_CONTINUE",
            
                            initialization_function_name= one_shot_fn,
                            aux_function_name="CFL_NULL",
                            termination_function_name=termination_fn,
                            node_data=one_shot_data)

    def asm_log_message(self,message):
        
        if type(message) is not str:
            raise TypeError("message must be a string")
        message_data = {"message": message}
        self.asm_one_shot_handler("CFL_LOG_MESSAGE",message_data)

  
            
    def asm_reset(self):
        self.define_column_link("CFL_RESET","CFL_NULL","CFL_NULL","CFL_NULL", {})

    def asm_terminate(self):
        self.define_column_link("CFL_TERMINATE","CFL_NULL","CFL_NULL","CFL_NULL", {})

    def asm_halt(self):
        self.define_column_link("CFL_HALT","CFL_NULL","CFL_NULL","CFL_NULL", {})
    
    def asm_disable(self):
        self.define_column_link("CFL_DISABLE","CFL_NULL","CFL_NULL","CFL_NULL", {})

    def asm_terminate_system(self):
        self.define_column_link("CFL_TERMINATE_SYSTEM","CFL_NULL","CFL_NULL","CFL_NULL", {})


    def asm_send_system_event(self,event_id,event_data):
        event_data = {"event_id": event_id, "event_data": event_data}
        self.asm_one_shot_handler("CFL_SEND_SYSTEM_EVENT",event_data)

    def asm_send_named_event(self,node_id :str,event_id :str,event_data :dict):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        if not isinstance(event_id, str):
            raise TypeError("Event id must be a string")
        if not isinstance(event_data, dict):
            raise TypeError("Event data must be a dictionary")
        if self.verify_node_id(node_id):
            raise ValueError("Node id is not valid ltree node id")
        event_data = {"node_id": node_id, "event_id": event_id, "event_data": event_data}
        self.asm_one_shot_handler("CFL_SEND_NAMED_EVENT",event_data)

    def asm_send_immediate_event(self,node_id :str,event_id :str,event_data :dict):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        if not isinstance(event_id, str):
            raise TypeError("Event id must be a string")
        if not isinstance(event_data, dict):
            raise TypeError("Event data must be a dictionary")
        if self.verify_node_id(node_id):
            raise ValueError("Node id is not valid ltree node id")
        event_data = {"node_id": node_id, "event_id": event_id, "event_data": event_data}
        self.asm_one_shot_handler("CFL_SEND_IMMEDIATE_EVENT",event_data)


    def asm_send_parent_event(self, level :int, event_id :str,event_data :dict):
        if level < 0:
            raise ValueError("Level must be greater than 0")

        parent_path =  self.ctb.ltree_stack
        
        if len(parent_path) <= level:
            raise ValueError("Level is too high")
        event_path = parent_path[:level][-1]
        
        self.asm_send_named_event(event_path,event_id,event_data)
    
    
    
    def asm_enable_nodes(self,nodes :list):
        self.asm_one_shot_handler("CFL_ENABLE_NODES",{"nodes": nodes})
        
    def asm_disable_nodes(self,nodes :list):
        self.asm_one_shot_handler("CFL_DISABLE_NODES",{"nodes": nodes})

    def asm_event_logger(self,message :str,events :list):
        if not isinstance(message, str):
            raise TypeError("Message must be a string")
        if not isinstance(events, list):
            raise TypeError("Events must be a list")
        return self.define_column_link("CFL_EVENT_LOGGER","CFL_NULL","CFL_NULL","CFL_NULL", 
                            node_data={"message": message, "events": events})

    def asm_subscribe_events(self,node_id :str,events :list):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        if not isinstance(events, list):
            raise TypeError("Events must be a list")
        if self.verify_node_id(node_id):
            raise ValueError("Node id is not valid ltree node id")

        self.asm_one_shot_handler("CFL_SUBSCRIBE_EVENTS",{"node_id": node_id, "events": events})
       
       
    def asm_unsubscribe_events(self,node_id :str,events :list):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        if not isinstance(events, list):
            raise TypeError("Events must be a list")
        if self.verify_node_id(node_id):
            raise ValueError("Node id is not valid ltree node id")
        self.asm_one_shot_handler("CFL_UNSUBSCRIBE_EVENTS",{"node_id": node_id, "events": events})

    def asm_publish_event(self,event_id :str,event_data :dict):
        if not isinstance(event_id, str):
            raise TypeError("Event id must be a string")
        if not isinstance(event_data, dict):
            raise TypeError("Event data must be a dictionary")
        self.asm_one_shot_handler("CFL_PUBLISH_EVENT",{"event_id": event_id, "event_data": event_data})

    # wd_time_count is the time count in seconds
    def asm_watch_dog_node(self,node_id :str,wd_time_count :int,wd_reset :bool,wd_fn :str,wd_fn_data :dict):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        if not isinstance(wd_time_count, int):
            raise TypeError("Watchdog time out must be an integer")
        if not isinstance(wd_reset, bool):
            raise TypeError("Watchdog reset must be a boolean")
        wd_data = {}
        wd_data["wd_time_count"] = wd_time_count
        wd_data["wd_reset"] = wd_reset
        wd_data["wd_fn"] = wd_fn
        wd_data["wd_fn_data"] = wd_fn_data
        if wd_fn != None:
            self.ctb.add_one_shot_function(wd_fn)
        node_id = self.define_column_link(main_function_name="CFL_WATCH_DOG_MAIN",
                            initialization_function_name="CFL_WATCH_DOG_INIT",
                            aux_function_name="CFL_NULL",
                            termination_function_name="CFL_WATCH_DOG_TERM",
                            node_data=wd_data)
        return node_id
    
    def asm_enable_watch_dog(self,node_id :str):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        node_data = self.ds.yaml_data[node_id]
        if node_data == None:
            raise ValueError("Node id is not valid chain tree node id")
        main_function_name = node_data["label_dict"]["main_function_name"]
        if main_function_name != "CFL_WATCH_DOG_MAIN":
            raise ValueError("Node is not a watch dog node")
        create_node_id = self.asm_one_shot_handler("CFL_ENABLE_WATCH_DOG",{"node_id": node_id})
        return create_node_id
    
    def asm_disable_watch_dog(self,node_id :str):
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        node_data = self.ds.yaml_data[node_id]
        if node_data == None:
            raise ValueError("Node id is not valid ltree node id")
        main_function_name = node_data["label_dict"]["main_function_name"]
        if main_function_name != "CFL_WATCH_DOG_MAIN":
            raise ValueError("Node is not a watch dog node")
        create_node_id = self.asm_one_shot_handler("CFL_DISABLE_WATCH_DOG",{"node_id": node_id})
        return create_node_id
 
    
    def asm_pat_watch_dog(self,node_id :str):  
        if not isinstance(node_id, str):
            raise TypeError("Node id must be a string")
        node_data = self.ds.yaml_data[node_id]
        if node_data == None:
            raise ValueError("Node id is not valid ltree node id")
        create_node_id = self.asm_one_shot_handler("CFL_PAT_WATCH_DOG",{"node_id": node_id})
        return create_node_id
    
    