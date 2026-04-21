import uuid
import copy
from .ct_engine.ct_tree_walker import CT_Tree_Walker



class TemplateFunctions:
    def __init__(self,chain_tree,ct_engine):
        self.chain_tree = chain_tree
        self.ct_engine = ct_engine
        self.instanciated_template_dict = {}
        self.shorted_name_dict = {}
        self.initial_conditions_dict = {}
        self.output_data_dict = {}
        self.shorted_name_length = 5
                
    def reset_instanciated_template_functions(self):
        self.instanciated_template_dict = {}
        self.shorted_name_dict = {}
        
    def install_template(self,node,template_name,initial_conditions):
        ltree_name = node["label_dict"]["ltree_name"]
        node_list = ltree_name.split(".")
        template_kb_name = node_list[0]+"."+node_list[1]+".TEMPLATE.MASTER"
        template_master_dict = self.chain_tree.python_dict[template_kb_name]["node_dict"]
        if template_name not in template_master_dict:
            raise Exception(f"Template {template_name} not found")
        template_root_node_id = template_master_dict[template_name]
        
        
        

        ltree_name = node["label_dict"]["ltree_name"]
        link_number = len(node["label_dict"]["links"])
        
    
        instanciated_template_name = str(uuid.uuid4())
        shorted_name = self.generate_shorted_name(instanciated_template_name)
        
        full_shorted_name = template_root_node_id.replace("TEMPLATE.MASTER.RAW",shorted_name)
        node["label_dict"]["links"].append(full_shorted_name)
        
        self.load_instanciated_template(template_root_node_id,shorted_name,ltree_name)
    
        self.output_data_dict[shorted_name] = []
        self.initial_conditions_dict[shorted_name] = initial_conditions
    
        return shorted_name,self.output_data_dict[shorted_name],self.initial_conditions_dict[shorted_name]
        
        
    def generate_shorted_name(self,instanciated_template_name):
        shortened_name = instanciated_template_name[:self.shorted_name_length]
        while self.shorted_name_dict.get(shortened_name) is not None:
            temp = str(uuid.uuid4())
            shortened_name_full = temp[:self.shorted_name_length]
            shortened_name = shortened_name_full[:self.shorted_name_length]
        self.shorted_name_dict[shortened_name] = True
        return shortened_name
    
    def load_instanciated_template(self,template_root_node_id,shorted_name,parent_ltree_name):
        
        ct_walker = CT_Tree_Walker(self.chain_tree.python_dict,self.load_instanciated_template_function,self.get_node_forward_links)
        user_handle = []
        ct_walker.walk(start_node=template_root_node_id,method='bfs',user_handle=user_handle)
        old_number_of_nodes = len(user_handle)
        
        for index, node in enumerate(user_handle):
            new_node = copy.deepcopy(node)
            
            
            label_dict = new_node["label_dict"]
            label_dict["ltree_name"] = label_dict["ltree_name"].replace("TEMPLATE.MASTER.RAW",shorted_name)
            if index == 0:
                label_dict["parent_ltree_name"] = parent_ltree_name
            else:
                label_dict["parent_ltree_name"] = label_dict["parent_ltree_name"].replace("TEMPLATE.MASTER.RAW",shorted_name)
            new_links = []
            if "links" in label_dict:
                for link in label_dict["links"]:
                    link = link.replace("TEMPLATE.MASTER.RAW",shorted_name)
                    new_links.append(link)
                label_dict["links"] = new_links
            new_node["label_dict"] = label_dict
    
            self.chain_tree.python_dict[label_dict["ltree_name"]] = new_node
            #print("node",label_dict["ltree_name"])
        new_root_node_id = template_root_node_id.replace("TEMPLATE.MASTER.RAW",shorted_name)
        self.ct_engine.setup_initial_runtime_data_fields(new_root_node_id)
        self.chain_tree.sequence_storage.build_tree(new_root_node_id)
        '''
        user_handle = []
        # this is test code to verify dictionary and links are correct
        ct_walker = CT_Tree_Walker(self.chain_tree.python_dict,self.display_instanciated_template_function,self.get_node_forward_links)
        ct_walker.walk(start_node = new_root_node_id,method='bfs',user_handle=user_handle)
        new_number_of_nodes = len(user_handle)
        print("old_number_of_nodes",old_number_of_nodes)
        print("new_number_of_nodes",new_number_of_nodes)
        '''
        
    def load_instanciated_template_function(self,node,level,user_handle):
        
        user_handle.append(node)
        return True
    
    def display_instanciated_template_function(self,node,level,user_handle):
        print("--------------------------------------",node,level)
        user_handle.append(node)
        return True
    
    def get_node_forward_links(self,node):
        if "label_dict" not in node:
            raise Exception("label_dict not found")
        if "links" not in node["label_dict"]:
            return []
        return node["label_dict"]["links"]
    
    def uninstall_instanciated_template(self,instanciated_template_start_node_id):
        user_handle = []
        ct_walker = CT_Tree_Walker(self.chain_tree.python_dict,self.load_instanciated_template_function,self.get_node_forward_links)
        ct_walker.walk(start_node = instanciated_template_start_node_id,method='bfs',user_handle=user_handle)
        
        for node in user_handle:
            kb = node["label_dict"]["ltree_name"].split(".")[1]
            if kb in self.chain_tree.sequence_storage.sequence_data:
                self.chain_tree.sequence_storage.rm_sequence_data(node)
            if kb in self.chain_tree.exception_catch_storage.exception_tree:
                self.chain_tree.exception_catch_storage.rm_exception_handler(node)
            del self.chain_tree.python_dict[node["label_dict"]["ltree_name"]]
        name_list = instanciated_template_start_node_id.split(".")
        shorted_name = name_list[2]
        del self.initial_conditions_dict[shorted_name]
        del self.output_data_dict[shorted_name]
        del self.shorted_name_dict[shorted_name]
      
      
    def get_template_input_data(self,node):
        ltree_name = node["label_dict"]["ltree_name"]
        shorted_list = ltree_name.split(".")
        shorted_name = shorted_list[2]
        return self.initial_conditions_dict[shorted_name]
    
    def set_template_output_data(self,node,output_data):
    
        ltree_name = node["label_dict"]["ltree_name"]
        shorted_list = ltree_name.split(".")
        shorted_name = shorted_list[2]
    
        self.output_data_dict[shorted_name].append(output_data)
    
    
    def get_template_output_data(self,node):
        ltree_name = node["label_dict"]["ltree_name"]
        shorted_list = ltree_name.split(".")
        shorted_name = shorted_list[2]
        return self.output_data_dict[shorted_name]
