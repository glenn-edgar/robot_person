from calendar import c
from .filtered_tree_builder import FilteredTreeBuilder

class ExceptionCatchHandler:
    def __init__(self,chain_tree,ct_engine):
        self.chain_tree = chain_tree
        self.ct_engine = ct_engine
        self.exception_tree = {}
    
   
    def rm_exception_handler(self,node):
        kb= node["label_dict"]["ltree_name"].split('.')[1]
        ltree_name = node["label_dict"]["ltree_name"]
        if kb in self.exception_tree and ltree_name in self.exception_tree[kb]:
            del self.exception_tree[kb][ltree_name]
            
   
    def add_exception_handler(self,node):
        kb= node["label_dict"]["ltree_name"].split('.')[1]
        ltree_name = node["label_dict"]["ltree_name"]
        if kb not in self.exception_tree:
            self.exception_tree[kb] = {}
        if ltree_name not in self.exception_tree[kb]:
            self.exception_tree[kb][ltree_name] = self.node_constructor(node)
        
    def check_node_exists(self,node):
        ltree_name = node["label_dict"]["ltree_name"]
        kb_list = ltree_name.split('.')
        kb = kb_list[1]
        if ltree_name not in self.exception_tree[kb]:
            raise ValueError(f"Node {ltree_name} not found in exception tree")
        return True
    
    def filter_func(self,node):
        
        label_dict = node["label_dict"]
    
        
        if label_dict["main_function_name"] in ["CFL_EXCEPTION_CATCH_MAIN"]:
            
            return True
        else:
            return False
        
    def links_func(self,node):
        if "label_dict" not in node:
            raise ValueError(f"label_dict not found for node {node['node_id']}")
        if "links" not in node["label_dict"]:
            return []
        links = node["label_dict"]["links"]
        return links
        
    def node_constructor(self,node):
    
        return_node = {}
        return_node["node_id"] = node["label_dict"]["ltree_name"]
        return_node["processed"] = False
        return_node["exception_data"] = {}
        return return_node

    def raise_exception(self,node,exception_id,exception_data):
        exception_catch_ltree_name = self.find_nearest_exception_handler(node)
        if exception_catch_ltree_name is None:
            raise KeyError(f"No exception handler found for node {node['label_dict']['ltree_name']} \
                            exception_id {exception_id}, exception_data {exception_data}")
    
        self.chain_tree.send_immediate_event(exception_catch_ltree_name,
                                             "CFL_EXCEPTION_EVENT",
                                             {"source_node_id": node["label_dict"]["ltree_name"], 
                                              "exception_id": exception_id, "exception_data": exception_data}) 
        
        
        
    def find_nearest_exception_handler(self,node):
        """
        Finds the nearest exception handler that is an ancestor of the given node.
        
        Args:
            node: The starting 
        
        Returns:
            The nearest ancestor node that has an exception handler, or None if not found
        """
         # Start with the parent (a node can't handle its own exception)
        
        if "label_dict" not in node:
            return None
        ltree_name = node["label_dict"]["ltree_name"]
        kb_list = ltree_name.split('.')
        kb = kb_list[1]
        # nust look for parent as current needs to propagate the exception
        current = node["label_dict"]["parent_ltree_name"]
        while current is not None:
            if current in self.exception_tree[kb]:
                return current
            if current not in self.chain_tree.python_dict:
                current = None
                return current
            if "label_dict" not in self.chain_tree.python_dict[current]:
                current = None
                break
            else:
                current = self.chain_tree.python_dict[current]["label_dict"]["parent_ltree_name"]
                
                
        return None 
    
    
    def error_recovery_links(self,node,link_indexes):
        if "label_dict" not in node:
            raise ValueError("label_dict not found")
        links = node["label_dict"]["links"]
        for link_index in link_indexes:
            if link_index >= len(links):
                raise ValueError("link_index out of range")
            recovery_link = links[link_index]
            self.ct_engine.reset_node_id(recovery_link)
            
        
    
    def find_exception_link(self,node,exception_link_id):
        for link in node["label_dict"]["links"]:
            if self.string_match(link,exception_link_id):
                return link
        return None
    
    def string_match(self,str1, str2):
        """
        Determines if the smaller string matches the start of the larger string.
        
        Args:
            str1: First string
            str2: Second string
        
        Returns:
            bool: True if the smaller string is a prefix of the larger string, False otherwise
        """
        # Determine which string is smaller
        smaller = str1 if len(str1) <= len(str2) else str2
        larger = str2 if len(str1) <= len(str2) else str1
        
        # Check if larger string starts with smaller string
        return larger.startswith(smaller)
    
    '''
    def find_exception_link(self,node,exception_link_id):
        for link in node["label_dict"]["links"]:
            if self.string_match(link,exception_link_id):
                return link
        return None
    '''