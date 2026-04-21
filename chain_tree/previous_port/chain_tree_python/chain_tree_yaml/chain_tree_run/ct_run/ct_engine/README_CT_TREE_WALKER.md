# CT_Tree_Walker

A powerful, reentrant Python class for traversing tree and graph structures stored in dictionaries. Supports multiple traversal methods (DFS recursive/iterative and BFS) with fine-grained control over traversal behavior through return codes.

## Features

- **Multiple Traversal Methods**: Depth-First Search (recursive and iterative) and Breadth-First Search
- **Reentrant Design**: Thread-safe with support for multiple concurrent traversals using unique handles
- **Fine-Grained Control**: Six different return codes for precise traversal control
- **Cycle Detection**: Automatically handles cycles in graph structures
- **Level Tracking**: Built-in depth/level tracking for all traversal methods
- **Dynamic Function Updates**: Modify processing functions during runtime

## Installation

Simply copy the `CT_Tree_Walker` class into your project. The only dependencies are Python standard library modules:
- `collections.deque`
- `threading`
- `uuid`

## Quick Start

```python
from ct_tree_walker import CT_Tree_Walker

# Define your tree/graph as a dictionary
nodes = {
    'A': {'value': 1, 'children': ['B', 'C']},
    'B': {'value': 2, 'children': ['D', 'E']},
    'C': {'value': 3, 'children': ['F']},
    'D': {'value': 4, 'children': []},
    'E': {'value': 5, 'children': []},
    'F': {'value': 6, 'children': []}
}

# Define how to get links from a node
def get_links(node):
    return node.get('children', [])

# Define what to do with each node
def process_node(node, level, user_handle=None):
    print(f"Level {level}: Processing node with value {node['value']}")
    return True  # Continue traversal

# Create walker and traverse
walker = CT_Tree_Walker(nodes, process_node, get_links)
handle, _ = walker.walk('A', method='bfs')

# Check visited nodes
visited = walker.get_visited_nodes(handle)
print(f"Visited nodes: {visited}")
```

## Return Codes

The `apply_func` can return different values to control traversal behavior:

| Return Code | Description | Effect on Children | Effect on Siblings | Continue Elsewhere |
|-------------|-------------|-------------------|-------------------|-------------------|
| `True` | Continue normally | Process | Process | Yes |
| `False` | Stop this branch | Skip | Process | Yes |
| `SKIP_CHILDREN` | Skip children only | Skip | Process | Yes |
| `STOP_SIBLINGS` | Stop processing siblings | Skip | Skip | Yes (parent level) |
| `STOP_LEVEL` | Stop at current depth | Skip (deeper levels) | Process (same level) | Yes |
| `STOP_ALL` | Stop entire traversal | Skip | Skip | No |

### Return Code Examples

```python
def process_with_conditions(node, level, user_handle=None):
    value = node['value']
    
    # Stop entire traversal if target found
    if value == target_value:
        return CT_Tree_Walker.STOP_ALL
    
    # Skip children of large nodes
    if node['size'] > threshold:
        return CT_Tree_Walker.SKIP_CHILDREN
    
    # Stop processing siblings if quota met
    if quota_reached():
        return CT_Tree_Walker.STOP_SIBLINGS
    
    # Don't go deeper than level 3
    if level >= 3:
        return CT_Tree_Walker.STOP_LEVEL
    
    # Skip this branch if not relevant
    if not is_relevant(node):
        return False
    
    # Otherwise continue normally
    return True
```

## API Reference

### Constructor

```python
CT_Tree_Walker(nodes_dict, apply_func, get_links_func)
```

**Parameters:**
- `nodes_dict`: Dictionary containing all nodes (keys are node IDs, values are node objects)
- `apply_func`: Function to apply to each node
  - Signature: `func(node, level, user_handle=None)`
  - Returns: Boolean or string return code
- `get_links_func`: Function to get child links from a node
  - Signature: `func(node)`
  - Returns: List of node IDs

### Main Methods

#### `walk(start_node, method='recursive', user_handle=None, handle=None, max_level=None)`

Traverse the tree/graph using the specified method.

**Parameters:**
- `start_node`: Starting node ID
- `method`: Traversal method ('recursive', 'iterative', 'bfs')
- `user_handle`: Optional user-defined data passed to apply_func
- `handle`: Reuse existing handle (if None, creates new one)
- `max_level`: Maximum depth to traverse

**Returns:** Tuple of (handle, self)

#### `create_handle()`

Create a unique handle for a new traversal session.

**Returns:** String handle ID

#### `get_visited_nodes(handle)`

Get the set of visited node IDs for a specific traversal.

**Parameters:**
- `handle`: The traversal handle

**Returns:** Set of visited node IDs

#### `cleanup_handle(handle)`

Remove the state associated with a handle to free memory.

**Parameters:**
- `handle`: The traversal handle to clean up

#### `cleanup_all_handles()`

Remove all traversal states.

#### `update_functions(apply_func=None, get_links_func=None)`

Update the processing or link extraction functions.

**Parameters:**
- `apply_func`: New node processing function (optional)
- `get_links_func`: New link extraction function (optional)

#### `is_in_progress(handle)`

Check if a traversal is currently running.

**Parameters:**
- `handle`: The traversal handle

**Returns:** Boolean

#### `is_completed(handle)`

Check if a traversal has completed.

**Parameters:**
- `handle`: The traversal handle

**Returns:** Boolean

## Advanced Usage

### Reentrant Traversals

Multiple traversals can run concurrently using different handles:

```python
walker = CT_Tree_Walker(nodes, process_func, get_links_func)

# Start multiple traversals
handle1, _ = walker.walk('A', method='bfs')
handle2, _ = walker.walk('B', method='recursive')
handle3, _ = walker.walk('C', method='iterative')

# Each maintains separate state
visited1 = walker.get_visited_nodes(handle1)
visited2 = walker.get_visited_nodes(handle2)
visited3 = walker.get_visited_nodes(handle3)
```

### Level-Aware Processing

Process nodes differently based on their depth:

```python
def level_aware_process(node, level, user_handle=None):
    if level == 0:
        # Root node processing
        return True
    elif level == 1:
        # First-level processing
        if should_skip_children(node):
            return CT_Tree_Walker.SKIP_CHILDREN
        return True
    elif level >= 3:
        # Don't go deeper than level 3
        return CT_Tree_Walker.STOP_LEVEL
    return True
```

### Using User Handles

Pass custom data through the traversal:

```python
class TraversalContext:
    def __init__(self):
        self.collected_values = []
        self.max_value = 0

def collect_values(node, level, user_handle):
    ctx = user_handle
    value = node['value']
    ctx.collected_values.append(value)
    ctx.max_value = max(ctx.max_value, value)
    return True

context = TraversalContext()
walker = CT_Tree_Walker(nodes, collect_values, get_links)
handle, _ = walker.walk('A', method='bfs', user_handle=context)

print(f"Collected: {context.collected_values}")
print(f"Max value: {context.max_value}")
```

### Dynamic Function Updates

Change processing behavior mid-traversal:

```python
walker = CT_Tree_Walker(nodes, initial_func, get_links)

# First traversal with initial function
handle1, _ = walker.walk('A')

# Update the processing function
def new_process_func(node, level, user_handle=None):
    # Different processing logic
    return True

walker.update_functions(apply_func=new_process_func)

# Second traversal with new function
handle2, _ = walker.walk('A')
```

## Traversal Method Comparison

| Method | Order | Best For | Memory Usage | Call Stack |
|--------|-------|----------|--------------|------------|
| Recursive DFS | Depth-first | Deep trees, simple logic | O(depth) | Uses recursion |
| Iterative DFS | Depth-first | Deep trees, avoiding stack overflow | O(depth) | No recursion |
| BFS | Breadth-first | Level-by-level processing, shortest path | O(width) | No recursion |

## Thread Safety

The `CT_Tree_Walker` class is thread-safe for:
- Creating and managing handles
- Concurrent traversals with different handles
- State management

Note: The `nodes_dict` should not be modified during traversal.

## Performance Considerations

- **Visited Set**: Maintains O(1) lookup for cycle detection
- **Memory**: Each handle maintains its own visited set
- **Cleanup**: Call `cleanup_handle()` or `cleanup_all_handles()` to free memory after traversals

## Common Patterns

### Finding a Target Node

```python
def find_target(node, level, user_handle):
    if node['id'] == target_id:
        user_handle['found'] = node
        return CT_Tree_Walker.STOP_ALL
    return True

result = {'found': None}
walker.walk('root', user_handle=result)
if result['found']:
    print(f"Found: {result['found']}")
```

### Collecting Nodes at Specific Level

```python
def collect_at_level(node, level, user_handle):
    target_level = user_handle['target_level']
    if level == target_level:
        user_handle['nodes'].append(node)
        return CT_Tree_Walker.SKIP_CHILDREN
    elif level > target_level:
        return CT_Tree_Walker.STOP_LEVEL
    return True

context = {'target_level': 2, 'nodes': []}
walker.walk('root', user_handle=context)
print(f"Nodes at level 2: {context['nodes']}")
```

### Pruning Branches Based on Conditions

```python
def conditional_traversal(node, level, user_handle):
    # Skip entire subtree if node is marked as inactive
    if not node.get('active', True):
        return False
    
    # Process but don't go deeper for certain types
    if node.get('type') == 'leaf':
        return CT_Tree_Walker.SKIP_CHILDREN
    
    # Stop siblings if quota reached
    if len(user_handle['processed']) >= user_handle['quota']:
        return CT_Tree_Walker.STOP_SIBLINGS
    
    user_handle['processed'].append(node)
    return True
```

## License

MIT

## Contributing

[Add contribution guidelines if applicable]

## Support

[Add support information or contact details]


