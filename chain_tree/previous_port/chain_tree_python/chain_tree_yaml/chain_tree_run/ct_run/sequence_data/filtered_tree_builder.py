class FilteredTreeBuilder:
    """
    Builds a filtered tree from a graph structure.
    """
    
    def __init__(self, graph, filter_func, links_func, node_constructor):
        """
        Initialize the tree builder.
        
        Args:
            graph: Dictionary containing nodes
            filter_func: A function that takes a node and returns True/False
            links_func: A function that takes a node and returns a list of linked node keys
            node_constructor: A function that takes a node and returns a new node for the tree
        """
        self.graph = graph
        self.filter_func = filter_func
        self.links_func = links_func
        self.node_constructor = node_constructor
    
    def construct_tree(self, start_node):
        """
        Construct a tree of nodes starting from start_node, only including nodes that pass filter_func.
        Skips nodes that don't pass the filter but continues searching their children.
        
        Args:
            start_node: The starting node key
        
        Returns:
            Dictionary where keys are node keys and values are constructed nodes with 'links' field
        """
        if start_node not in self.graph:
            return {}
        
        result = {}
        self._build_tree(start_node, set(), result)
        return result
    
    def _build_tree(self, node_key, visited, result):
        """Recursively build tree, tracking visited nodes to avoid cycles"""
        if node_key in visited or node_key not in self.graph:
            return []
        
        node = self.graph[node_key]
        new_visited = visited | {node_key}
        
        # Get links using the provided function
        node_links = self.links_func(node)
        
        # Collect all valid child keys
        valid_child_keys = []
        for link in node_links:
            child_keys = self._build_tree(link, new_visited, result)
            valid_child_keys.extend(child_keys)
        
        # If this node passes the filter, include it
        if self.filter_func(node):
        
            tree_node = self.node_constructor(node)
            tree_node['links'] = valid_child_keys
            result[node_key] = tree_node
            return [node_key]
        
        # If this node doesn't pass but has valid children, return those keys
        return valid_child_keys
    
    def topological_sort(self, tree):
        """
        Perform a topological sort on the tree.
        Returns a list of node keys in topological order (dependencies first).
        
        Args:
            tree: Dictionary returned by construct_tree
        
        Returns:
            List of node keys in topological order
        """
        # Calculate in-degree for each node
        in_degree = {key: 0 for key in tree}
        
        for key, node in tree.items():
            for link in node['links']:
                if link in in_degree:
                    in_degree[link] += 1
        
        # Queue of nodes with no incoming edges
        queue = [key for key, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # Sort queue for consistent ordering (optional)
            queue.sort()
            current = queue.pop(0)
            result.append(current)
            
            # Reduce in-degree for all children
            if current in tree:
                for link in tree[current]['links']:
                    if link in in_degree:
                        in_degree[link] -= 1
                        if in_degree[link] == 0:
                            queue.append(link)
        
        # Check if all nodes were processed (no cycles)
        if len(result) != len(tree):
            raise ValueError("Graph contains a cycle, cannot perform topological sort")
        
        return result
    
    def filtered_topological_sort(self, tree, sort_filter_func):
        """
        Perform a topological sort on the tree with additional filtering.
        Nodes that don't pass the filter are excluded from the result, and their
        links are adjusted so that their children become direct descendants of
        their parents.
        
        Args:
            tree: Dictionary returned by construct_tree
            sort_filter_func: A function that takes a node_key and returns True/False
        
        Returns:
            List of node keys in topological order, excluding filtered nodes
        """
        # First, create a filtered tree with adjusted links
        filtered_tree = {}
        
        for key, node in tree.items():
            if sort_filter_func(key):
                # This node passes the filter
                new_node = node.copy()
                # Adjust links to skip filtered nodes
                new_links = self._get_filtered_descendants(key, tree, sort_filter_func, set())
                new_node['links'] = new_links
                filtered_tree[key] = new_node
        
        # Now perform topological sort on the filtered tree
        if not filtered_tree:
            return []
        
        # Calculate in-degree for each node
        in_degree = {key: 0 for key in filtered_tree}
        
        for key, node in filtered_tree.items():
            for link in node['links']:
                if link in in_degree:
                    in_degree[link] += 1
        
        # Queue of nodes with no incoming edges
        queue = [key for key, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # Sort queue for consistent ordering (optional)
            queue.sort()
            current = queue.pop(0)
            result.append(current)
            
            # Reduce in-degree for all children
            if current in filtered_tree:
                for link in filtered_tree[current]['links']:
                    if link in in_degree:
                        in_degree[link] -= 1
                        if in_degree[link] == 0:
                            queue.append(link)
        
        # Check if all nodes were processed (no cycles)
        if len(result) != len(filtered_tree):
            raise ValueError("Graph contains a cycle, cannot perform topological sort")
        
        return result
    
    def _get_filtered_descendants(self, node_key, tree, sort_filter_func, visited):
        """
        Get all descendants of a node that pass the filter, skipping intermediate filtered nodes.
        
        Args:
            node_key: Current node key
            tree: The tree dictionary
            sort_filter_func: Filter function for nodes
            visited: Set of visited nodes to avoid cycles
        
        Returns:
            List of descendant node keys that pass the filter
        """
        if node_key not in tree or node_key in visited:
            return []
        
        new_visited = visited | {node_key}
        descendants = []
        
        for link in tree[node_key]['links']:
            if sort_filter_func(link):
                # This child passes the filter, include it
                descendants.append(link)
            else:
                # This child doesn't pass, get its descendants
                descendants.extend(self._get_filtered_descendants(link, tree, sort_filter_func, new_visited))
        
        return descendants
    
    def compare_topological_sorts(self, sort_a, sort_b):
        """
        Compare two topological sorts and determine the differences.
        
        Args:
            sort_a: First topological sort (list of node keys)
            sort_b: Second topological sort (list of node keys)
        
        Returns:
            Dictionary with:
                - 'missing_in_b': Elements in A but not in B
                - 'additional_in_b': Elements in B but not in A
                - 'common': Elements in both A and B
        """
        set_a = set(sort_a)
        set_b = set(sort_b)
        
        missing_in_b = list(set_a - set_b)
        additional_in_b = list(set_b - set_a)
        common = list(set_a & set_b)
        
        # Sort for consistent output
        missing_in_b.sort()
        additional_in_b.sort()
        common.sort()
        
        return {
            'missing_in_b': missing_in_b,
            'additional_in_b': additional_in_b,
            'common': common
        }

    def reset_from_node(self, tree, start_node, reset_function):
        """
        Starting from a given node, traverse the tree and apply a reset function to each node.
        Traverses in depth-first order following the links.
        
        Args:
            tree: Dictionary returned by construct_tree
            start_node: The node key to start the reset from
            reset_function: A function that takes a node and performs a reset operation on it
        
        Returns:
            List of node keys that were reset, in the order they were processed
        """
        if start_node not in tree:
            return []
        
        visited = set()
        reset_order = []
        
        def _reset_recursive(node_key):
            """Recursively reset nodes"""
            if node_key in visited or node_key not in tree:
                return
            
            visited.add(node_key)
            node = tree[node_key]
            
            # Apply the reset function to the current node
            reset_function(node)
            reset_order.append(node_key)
            
            # Recursively reset all linked nodes
            for link in node.get('links', []):
                _reset_recursive(link)
        
        _reset_recursive(start_node)
        return reset_order

    def collect_to_json(self, tree, start_node, filter_func):
        """
        Starting from a given node, collect all nodes that pass the filter function
        and generate a JSON structure representing the filtered subtree.
        
        Args:
            tree: Dictionary returned by construct_tree
            start_node: The node key to start collection from
            filter_func: A function that takes a node and returns True/False
        
        Returns:
            Dictionary representing the JSON structure of the filtered subtree,
            or None if start_node doesn't exist or doesn't pass the filter
        """
        if start_node not in tree:
            return None
        
        start_node_obj = tree[start_node]
        
        # Check if the start node passes the filter
        if not filter_func(start_node_obj):
            return None
        
        visited = set()
        
        def _collect_recursive(node_key):
            """Recursively collect nodes that pass the filter"""
            if node_key in visited or node_key not in tree:
                return None
            
            visited.add(node_key)
            node = tree[node_key]
            
            # Check if this node passes the filter
            if not filter_func(node):
                return None
            
            # Create the JSON structure for this node
            json_node = {
                'key': node_key,
                'data': {k: v for k, v in node.items() if k != 'links'},
                'children': []
            }
            
            # Recursively process all linked nodes
            for link in node.get('links', []):
                child_json = _collect_recursive(link)
                if child_json is not None:
                    json_node['children'].append(child_json)
            
            return json_node
        
        return _collect_recursive(start_node)

    def collect_to_list(self, tree, start_node, filter_func):
        """
        Starting from a given node, collect all nodes that pass the filter function
        and generate a list of nodes in depth-first order.
        
        Args:
            tree: Dictionary returned by construct_tree
            start_node: The node key to start collection from
            filter_func: A function that takes a node and returns True/False
        
        Returns:
            List of dictionaries, where each dictionary contains 'key' and node data,
            for all nodes that pass the filter. Returns empty list if start_node 
            doesn't exist.
        """
        if start_node not in tree:
            return []
        
        visited = set()
        result = []
        
        def _collect_recursive(node_key):
            """Recursively collect nodes that pass the filter"""
            if node_key in visited or node_key not in tree:
                return
            
            visited.add(node_key)
            node = tree[node_key]
            
            # Check if this node passes the filter
            if filter_func(node):
                # Add the node to the result list
                node_data = {'key': node_key}
                node_data.update({k: v for k, v in node.items() if k != 'links'})
                result.append(node_data)
            
            # Recursively process all linked nodes (regardless of filter)
            for link in node.get('links', []):
                _collect_recursive(link)
        
        _collect_recursive(start_node)
        return result
    
    
if __name__ == "__main__":
    # Example usage:
    graph = {
        'A': {'value': 10, 'type': 'important', 'links': ['B', 'C']},
        'B': {'value': 5, 'type': 'skip', 'links': ['D', 'G']},
        'C': {'value': 15, 'type': 'important', 'links': ['D', 'E']},
        'D': {'value': 3, 'type': 'skip', 'links': ['H']},
        'E': {'value': 20, 'type': 'important', 'links': ['F']},
        'F': {'value': 8, 'type': 'important', 'links': []},
        'G': {'value': 2, 'type': 'skip', 'links': ['I']},
        'H': {'value': 12, 'type': 'important', 'links': []},
        'I': {'value': 25, 'type': 'important', 'links': []}
    }
    # Create a builder instance
    builder = FilteredTreeBuilder(
        graph=graph,
        filter_func=lambda node: node['value'] > 7,
        links_func=lambda node: node.get('links', []),
        node_constructor=lambda node: {'value': node['value'], 'type': node['type']}
    )

    # Build the tree
    tree = builder.construct_tree('A')

    import json
    print("Full tree structure:")
    print(json.dumps(tree, indent=2))

    print("\n--- Standard Topological Sort ---")
    sorted_all = builder.topological_sort(tree)
    print("All nodes:", sorted_all)

    print("\n--- Filtered Topological Sort (only 'important' type) ---")
    sorted_important = builder.filtered_topological_sort(
        tree,
        lambda key: tree[key]['type'] == 'important'
    )
    print("Important nodes:", sorted_important)

    print("\n--- Comparison ---")
    comparison = builder.compare_topological_sorts(sorted_all, sorted_important)
    print(f"Missing in filtered sort: {comparison['missing_in_b']}")
    print(f"Additional in filtered sort: {comparison['additional_in_b']}")
    print(f"Common in both: {comparison['common']}")

    print("\n--- Another Comparison Example ---")
    # Create another filtered sort with different criteria
    sorted_high_value = builder.filtered_topological_sort(
        tree,
        lambda key: tree[key]['value'] > 15
    )
    print("High value nodes (>15):", sorted_high_value)

    comparison2 = builder.compare_topological_sorts(sorted_important, sorted_high_value)
    print(f"In 'important' but not 'high value': {comparison2['missing_in_b']}")
    print(f"In 'high value' but not 'important': {comparison2['additional_in_b']}")
    print(f"In both: {comparison2['common']}")