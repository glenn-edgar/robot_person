from collections import deque
import threading
import uuid

class CT_Tree_Walker:
    """
    A reentrant class for traversing tree/graph structures stored in dictionaries.
    Supports DFS (recursive and iterative) and BFS traversal methods.
    Each traversal gets a unique handle to maintain separate state.
    
    The apply_func can return:
    - True or any truthy value: Continue traversing normally
    - False: Stop traversing this branch (subtree termination)
    - "SKIP_CHILDREN": Skip children of current node but continue with siblings
    - "STOP_LEVEL": Stop processing at current level (level termination)
    - "STOP_SIBLINGS": Stop processing siblings at current level, return to parent
    - "STOP_ALL": Stop entire traversal immediately
    """
    
    # Constants for return values
    STOP_LEVEL = "STOP_LEVEL"
    STOP_ALL = "STOP_ALL"
    STOP_SIBLINGS = "STOP_SIBLINGS"
    SKIP_CHILDREN = "SKIP_CHILDREN"
    
    def __init__(self, nodes_dict, apply_func, get_links_func):
        """
        Initialize the tree walker.
        
        Args:
            nodes_dict: Dictionary containing all nodes
            apply_func: Function to apply to each node (takes node and level as arguments, 
                       returns bool/string):
                       - True: Continue traversing
                       - False: Stop traversing this branch
                       - "SKIP_CHILDREN": Skip children but continue with siblings
                       - "STOP_LEVEL": Stop processing at current level
                       - "STOP_SIBLINGS": Stop processing siblings, return to parent
                       - "STOP_ALL": Stop entire traversal
            get_links_func: Function to get links from a node (takes node as argument, 
                           returns list of node ids)
        """
        self.nodes_dict = nodes_dict
        self.apply_func = apply_func
        self.get_links_func = get_links_func
        self.traversal_states = {}  # Dictionary to store state per handle
        self.lock = threading.Lock()  # Thread safety for state management
    
    def create_handle(self):
        """
        Create a unique handle for a new traversal session.
        
        Returns:
            A unique handle (string) for this traversal
        """
        handle = str(uuid.uuid4())
        with self.lock:
            self.traversal_states[handle] = {
                'visited': set(),
                'in_progress': False,
                'completed': False,
                'stop_all': False,
                'max_level': None
            }
        return handle
    
    def get_state(self, handle):
        """
        Get the state for a specific handle.
        
        Args:
            handle: The traversal handle
            
        Returns:
            State dictionary or None if handle doesn't exist
        """
        with self.lock:
            return self.traversal_states.get(handle)
    
    def cleanup_handle(self, handle):
        """
        Remove the state associated with a handle.
        
        Args:
            handle: The traversal handle to clean up
        """
        with self.lock:
            if handle in self.traversal_states:
                del self.traversal_states[handle]
    
    def cleanup_all_handles(self):
        """Remove all traversal states."""
        with self.lock:
            self.traversal_states.clear()
    
    def _apply_with_level(self, node, level, handle, user_handle=None):
        """
        Apply the function and handle different return values.
        
        Returns:
            Tuple (should_continue, action) where action can be None, "SKIP_CHILDREN", "STOP_LEVEL", "STOP_SIBLINGS", or "STOP_ALL"
        """
        state = self.get_state(handle)
        
        # Check if we should stop all processing
        if state and state.get('stop_all'):
            return False, self.STOP_ALL
        
        # Check if we've reached max level
        if state and state.get('max_level') is not None and level > state['max_level']:
            return False, self.STOP_LEVEL
        
        # Apply the function (pass level if function accepts it)
        try:
            # Try calling with level parameter
            result = self.apply_func(node, level, user_handle)
        except TypeError:
            # Fall back to calling without level for backward compatibility
            result = self.apply_func(node, user_handle)
        
        # Handle different return values
        if result == self.STOP_ALL:
            if state:
                state['stop_all'] = True
            return False, self.STOP_ALL
        elif result == self.STOP_SIBLINGS:
            return False, self.STOP_SIBLINGS
        elif result == self.STOP_LEVEL:
            if state:
                state['max_level'] = level
            return False, self.STOP_LEVEL
        elif result == self.SKIP_CHILDREN:
            return False, self.SKIP_CHILDREN
        elif result is False:
            return False, None
        else:
            return True, None
    
    def traverse_recursive(self, start_node, handle, visited=None, level=0, user_handle=None):
        """
        Traverse nodes using recursive depth-first search.
        
        Args:
            start_node: The starting node identifier
            handle: The traversal handle
            visited: Set of already visited nodes (used internally for cycle detection)
            level: Current depth level in the tree
            user_handle: Optional user-defined handle passed to apply_func
            
        Returns:
            String indicating action ("STOP_SIBLINGS", "STOP_ALL") or None
        """
        state = self.get_state(handle)
        if state is None:
            raise ValueError(f"Invalid handle: {handle}")
        
        # Check if we should stop all processing
        if state.get('stop_all'):
            return self.STOP_ALL
        
        if visited is None:
            visited = state['visited']
        
        # Check if we've already visited this node (cycle detection)
        if start_node in visited:
            return None
        
        # Mark node as visited
        visited.add(start_node)
        
        # Get the actual node from the dictionary
        if start_node not in self.nodes_dict:
            return None
        
        node = self.nodes_dict[start_node]
        
        # Apply the function to the current node
        should_continue, action = self._apply_with_level(node, level, handle, user_handle)
        
        if action == self.STOP_ALL:
            return self.STOP_ALL
        elif action == self.STOP_SIBLINGS:
            # Return signal to parent to stop processing siblings
            return self.STOP_SIBLINGS
        elif action == self.STOP_LEVEL:
            # Don't process children due to level limit
            return None
        elif action == self.SKIP_CHILDREN:
            # Skip children but continue with siblings normally
            return None
        elif not should_continue:
            # False: Stop this branch entirely
            return None
        
        # Get links from the current node
        links = self.get_links_func(node)
        
        # If no links, stop this branch
        if not links:
            return None
        
        # Recursively follow each link
        for i, link in enumerate(links):
            if state.get('stop_all'):
                break
            
            result = self.traverse_recursive(link, handle, visited, level + 1, user_handle)
            
            # Handle STOP_SIBLINGS from child
            if result == self.STOP_SIBLINGS:
                # Stop processing remaining siblings at this level
                break
            elif result == self.STOP_ALL:
                return self.STOP_ALL
        
        return None
    
    def traverse_iterative(self, start_node, handle, user_handle=None):
        """
        Traverse nodes using iterative depth-first search with a stack.
        
        Args:
            start_node: The starting node identifier
            handle: The traversal handle
            user_handle: Optional user-defined handle passed to apply_func
        """
        state = self.get_state(handle)
        if state is None:
            raise ValueError(f"Invalid handle: {handle}")
        
        visited = state['visited']
        # Stack stores (node_id, level, parent_id) tuples
        # parent_id helps track when to stop processing siblings
        stack = [(start_node, 0, None)]
        stop_siblings_for_parent = set()  # Track which parents should stop processing children
        
        while stack and not state.get('stop_all'):
            current, level, parent_id = stack.pop()
            
            # Check if this node's siblings should be skipped
            if parent_id in stop_siblings_for_parent:
                continue
            
            if current in visited:
                continue
                
            visited.add(current)
            
            if current not in self.nodes_dict:
                continue
                
            node = self.nodes_dict[current]
            
            # Apply function and check if we should continue
            should_continue, action = self._apply_with_level(node, level, handle, user_handle)
            
            if action == self.STOP_ALL:
                break
            elif action == self.STOP_SIBLINGS:
                # Mark parent to stop processing more children
                if parent_id is not None:
                    stop_siblings_for_parent.add(parent_id)
                # Don't add children
            elif action == self.STOP_LEVEL:
                # Don't add children (level termination)
                pass
            elif action == self.SKIP_CHILDREN:
                # Skip adding children but continue normally
                pass
            elif not should_continue:
                # False means stop this branch (skip children)
                pass
            else:
                # Only add children if we should continue normally
                links = self.get_links_func(node)
                if links:
                    # Add unvisited links to stack with incremented level
                    for link in reversed(links):  # Reversed to maintain order
                        if link not in visited:
                            stack.append((link, level + 1, current))
    
    def traverse_bfs(self, start_node, handle, user_handle=None):
        """
        Traverse nodes using breadth-first search with a queue.
        
        Args:
            start_node: The starting node identifier
            handle: The traversal handle
            user_handle: Optional user-defined handle passed to apply_func
        """
        state = self.get_state(handle)
        if state is None:
            raise ValueError(f"Invalid handle: {handle}")
        
        visited = state['visited']
        # Queue stores (node_id, level, parent_id) tuples
        queue = deque([(start_node, 0, None)])
        current_level = -1
        stop_at_next_level = False
        stop_siblings_for_parent = set()  # Track which parents should not process more children
        
        while queue and not state.get('stop_all'):
            current, level, parent_id = queue.popleft()
            
            # Check if we've moved to a new level and should stop
            if level > current_level:
                if stop_at_next_level:
                    break
                current_level = level
                # Clear stop_siblings tracking for previous level
                if level > 0:
                    stop_siblings_for_parent.clear()
            
            # Skip if this parent's children should stop
            if parent_id in stop_siblings_for_parent:
                continue
            
            if current in visited:
                continue
                
            visited.add(current)
            
            if current not in self.nodes_dict:
                continue
                
            node = self.nodes_dict[current]
            
            # Apply function and check if we should continue
            should_continue, action = self._apply_with_level(node, level, handle, user_handle)
            
            if action == self.STOP_ALL:
                break
            elif action == self.STOP_SIBLINGS:
                # Mark parent to stop processing more children
                if parent_id is not None:
                    stop_siblings_for_parent.add(parent_id)
                continue
            elif action == self.STOP_LEVEL:
                # In BFS, finish current level but don't go deeper
                stop_at_next_level = True
                continue
            elif action == self.SKIP_CHILDREN or not should_continue:
                # Skip adding children to queue
                continue
            
            if not stop_at_next_level:
                links = self.get_links_func(node)
                if links:
                    for link in links:
                        if link not in visited:
                            queue.append((link, level + 1, current))
    
    def walk(self, start_node, method='recursive', user_handle=None, handle=None, max_level=None):
        """
        Main method to traverse the tree/graph using the specified method.
        
        Args:
            start_node: The starting node identifier
            method: Traversal method ('recursive', 'iterative', 'bfs')
            user_handle: Optional user-defined handle passed to apply_func
            handle: Traversal handle (if None, creates a new one)
            max_level: Maximum depth level to traverse (optional)
        
        Returns:
            Tuple of (handle, self) for method chaining
        """
        if handle is None:
            handle = self.create_handle()
        
        state = self.get_state(handle)
        if state is None:
            raise ValueError(f"Invalid handle: {handle}")
        
        # Set max level if provided
        if max_level is not None:
            state['max_level'] = max_level
        
        # Check if a traversal is already in progress for this handle
        with self.lock:
            if state['in_progress']:
                raise RuntimeError(f"Traversal already in progress for handle: {handle}")
            state['in_progress'] = True
        
        try:
            if method == 'recursive':
                self.traverse_recursive(start_node, handle, user_handle=user_handle)
            elif method == 'iterative':
                self.traverse_iterative(start_node, handle, user_handle)
            elif method == 'bfs':
                self.traverse_bfs(start_node, handle, user_handle)
            else:
                raise ValueError(f"Unknown traversal method: {method}")
        finally:
            with self.lock:
                state['in_progress'] = False
                state['completed'] = True
        
        return handle, self
    
    def get_visited_nodes(self, handle):
        """
        Return the set of visited node identifiers for a specific handle.
        
        Args:
            handle: The traversal handle
            
        Returns:
            Set of visited nodes or None if handle doesn't exist
        """
        state = self.get_state(handle)
        if state:
            return state['visited'].copy()
        return None
    
    def is_in_progress(self, handle):
        """
        Check if a traversal is currently in progress for a handle.
        
        Args:
            handle: The traversal handle
            
        Returns:
            Boolean indicating if traversal is in progress
        """
        state = self.get_state(handle)
        return state['in_progress'] if state else False
    
    def is_completed(self, handle):
        """
        Check if a traversal has been completed for a handle.
        
        Args:
            handle: The traversal handle
            
        Returns:
            Boolean indicating if traversal is completed
        """
        state = self.get_state(handle)
        return state['completed'] if state else False
    
    def update_functions(self, apply_func=None, get_links_func=None):
        """
        Update the apply or get_links functions.
        
        Args:
            apply_func: New function to apply to nodes (optional)
            get_links_func: New function to get links (optional)
        """
        if apply_func is not None:
            self.apply_func = apply_func
        if get_links_func is not None:
            self.get_links_func = get_links_func


# Example usage:
if __name__ == "__main__":
    import threading
    
    # Example nodes dictionary with deeper structure
    nodes = {
        'A': {'value': 1, 'links': ['B', 'C']},           # Level 0
        'B': {'value': 2, 'links': ['D', 'E']},          # Level 1
        'C': {'value': 3, 'links': ['F']},               # Level 1
        'D': {'value': 4, 'links': ['G', 'H']},          # Level 2
        'E': {'value': 5, 'links': ['I']},               # Level 2
        'F': {'value': 6, 'links': ['J']},               # Level 2
        'G': {'value': 7, 'links': []},                  # Level 3
        'H': {'value': 8, 'links': []},                  # Level 3
        'I': {'value': 9, 'links': []},                  # Level 3
        'J': {'value': 10, 'links': ['K']},              # Level 3
        'K': {'value': 11, 'links': []},                 # Level 4
    }
    
    def get_node_links(node):
        return node.get('links', [])
    
    # Example 1: Stop at a specific level
    print("Example 1: Stop at specific level")
    print("="*50)
    
    def process_with_level_stop(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        
        # Stop at level 2
        if level >= 2:
            print(f"    -> Stopping at level {level}")
            return CT_Tree_Walker.STOP_LEVEL
        
        return True
    
    walker = CT_Tree_Walker(nodes, process_with_level_stop, get_node_links)
    handle1, _ = walker.walk('A', method='bfs')
    print(f"Visited nodes: {walker.get_visited_nodes(handle1)}\n")
    
    # Example 2: Stop entire traversal when condition is met
    print("Example 2: Stop entire traversal")
    print("="*50)
    
    def process_with_stop_all(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        
        # Stop everything when we find value 5
        if value == 5:
            print(f"    -> STOP ALL at value {value}")
            return CT_Tree_Walker.STOP_ALL
        
        return True
    
    walker.update_functions(apply_func=process_with_stop_all)
    handle2, _ = walker.walk('A', method='bfs')
    print(f"Visited nodes: {walker.get_visited_nodes(handle2)}\n")
    
    # Example 3: Mixed termination strategies
    print("Example 3: Mixed termination strategies")
    print("="*50)
    
    def process_with_mixed(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        
        # Different strategies based on conditions
        if value == 6:
            print(f"    -> Stopping branch at value {value}")
            return False  # Stop this branch
        elif level >= 3:
            print(f"    -> Stopping at level {level}")
            return CT_Tree_Walker.STOP_LEVEL
        
        return True
    
    walker.update_functions(apply_func=process_with_mixed)
    handle3, _ = walker.walk('A', method='recursive')
    print(f"Visited nodes: {walker.get_visited_nodes(handle3)}\n")
    
    # Example 4: Using max_level parameter
    print("Example 4: Using max_level parameter")
    print("="*50)
    
    def simple_process(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        return True
    
    walker.update_functions(apply_func=simple_process)
    handle4, _ = walker.walk('A', method='bfs', max_level=2)
    print(f"Visited nodes (max_level=2): {walker.get_visited_nodes(handle4)}\n")
    
    # Example 5: Backward compatibility (function without level parameter)
    print("Example 5: Backward compatibility")
    print("="*50)
    
    def old_style_function(node, user_handle=None):
        # This function doesn't accept level parameter
        value = node['value']
        print(f"  Processing node {value}")
        return value < 7  # Stop if value >= 7
    
    walker.update_functions(apply_func=old_style_function)
    handle5, _ = walker.walk('A', method='iterative')
    print(f"Visited nodes: {walker.get_visited_nodes(handle5)}\n")
    
    # Example 6: Level-aware data collection
    print("Example 6: Level-aware data collection")
    print("="*50)
    
    level_data = {0: [], 1: [], 2: [], 3: []}
        
    def collect_by_level(node, level, user_handle=None):
        value = node['value']
        if level in level_data:
            level_data[level].append(value)
        print(f"  Level {level}: Collected value {value}")
        return True
    
    walker.update_functions(apply_func=collect_by_level)
    handle6, _ = walker.walk('A', method='bfs')
    
    for level, values in level_data.items():
        print(f"Level {level}: {values}")
    
    # Example 7: NEW - Testing STOP_SIBLINGS
    print("\nExample 7: Testing STOP_SIBLINGS")
    print("="*50)
    
    def process_with_stop_siblings(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        
        # Stop processing siblings when we find value 4 (D)
        if value == 4:
            print(f"    -> STOP SIBLINGS at value {value}")
            return CT_Tree_Walker.STOP_SIBLINGS
        
        return True
    
    walker.update_functions(apply_func=process_with_stop_siblings)
    
    print("\n  Testing with DFS (recursive):")
    handle7a, _ = walker.walk('A', method='recursive')
    print(f"  Visited nodes: {walker.get_visited_nodes(handle7a)}")
    print("  Note: D was processed, but its siblings (E) and D's children (G, H) were skipped")
    
    print("\n  Testing with BFS:")
    handle7b, _ = walker.walk('A', method='bfs')
    print(f"  Visited nodes: {walker.get_visited_nodes(handle7b)}")
    print("  Note: In BFS, D's sibling E at the same level was skipped")
    
    # Example 8: Complex scenario with STOP_SIBLINGS
    print("\nExample 8: STOP_SIBLINGS at different levels")
    print("="*50)
    
    def complex_stop_siblings(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        
        # Stop siblings at E (value 5) - should skip I but continue with F
        if value == 5:
            print(f"    -> STOP SIBLINGS at value {value} (level {level})")
            return CT_Tree_Walker.STOP_SIBLINGS
        
        return True
    
    walker.update_functions(apply_func=complex_stop_siblings)
    handle8, _ = walker.walk('A', method='recursive')
    print(f"Visited nodes: {walker.get_visited_nodes(handle8)}")
    print("Note: E returned STOP_SIBLINGS, so I (E's child) wasn't processed,")
    print("      but traversal continued with C branch (F, J, K)")
    
    # Example 9: NEW - Testing SKIP_CHILDREN
    print("\nExample 9: Testing SKIP_CHILDREN")
    print("="*50)
    
    def process_with_skip_children(node, level, user_handle=None):
        value = node['value']
        print(f"  Level {level}: Processing node {value}")
        
        # Skip children of nodes with value 2 or 3 (B and C)
        if value in [2, 3]:
            print(f"    -> SKIP CHILDREN for value {value}")
            return CT_Tree_Walker.SKIP_CHILDREN
        
        return True
    
    walker.update_functions(apply_func=process_with_skip_children)
    handle9, _ = walker.walk('A', method='recursive')
    print(f"Visited nodes: {walker.get_visited_nodes(handle9)}")
    print("Note: B and C were processed, but their children were skipped")
    print("      This is clearer than using False for this specific intent")
    
    # Example 10: Comparing False vs SKIP_CHILDREN
    print("\nExample 10: Comparing False vs SKIP_CHILDREN with different methods")
    print("="*50)
    
    print("  Testing SKIP_CHILDREN with BFS:")
    def using_skip_children_bfs(node, level, user_handle=None):
        value = node['value']
        print(f"    Processing node {value} at level {level}")
        if value == 2:  # B
            print(f"      -> SKIP_CHILDREN at node {value}")
            return CT_Tree_Walker.SKIP_CHILDREN
        return True
    
    walker.update_functions(apply_func=using_skip_children_bfs)
    handle10a, _ = walker.walk('A', method='bfs')
    print(f"  BFS Visited: {sorted(walker.get_visited_nodes(handle10a))}")
    print(f"  (Should visit A, B, C, F, J, K - skipping B's children D, E)")
    
    print("\n  Testing SKIP_CHILDREN with Iterative DFS:")
    walker.cleanup_all_handles()  # Clear previous state
    walker.update_functions(apply_func=using_skip_children_bfs)
    handle10b, _ = walker.walk('A', method='iterative')
    print(f"  Iterative Visited: {sorted(walker.get_visited_nodes(handle10b))}")
    print(f"  (Should visit A, B, C, F, J, K - skipping B's children D, E)")
    
    print("\n  Testing SKIP_CHILDREN with Recursive DFS:")
    walker.cleanup_all_handles()  # Clear previous state
    walker.update_functions(apply_func=using_skip_children_bfs)
    handle10c, _ = walker.walk('A', method='recursive')
    print(f"  Recursive Visited: {sorted(walker.get_visited_nodes(handle10c))}")
    print(f"  (Should visit A, B, C, F, J, K - skipping B's children D, E)")
    
    # Cleanup
    walker.cleanup_all_handles()