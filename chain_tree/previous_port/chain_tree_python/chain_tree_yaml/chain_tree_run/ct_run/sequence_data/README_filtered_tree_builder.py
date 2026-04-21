Here's a comprehensive README.md for the FilteredTreeBuilder class:

```markdown
# FilteredTreeBuilder

A Python class for constructing filtered tree structures from graph data with support for topological sorting.

## Overview

`FilteredTreeBuilder` traverses a graph starting from a specified node, filters nodes based on a custom boolean function, and builds a tree structure. Nodes that don't pass the filter are skipped, but their descendants are still explored and included if they pass the filter.

## Features

- **Flexible Filtering**: Use custom functions to determine which nodes to include
- **Custom Node Construction**: Transform nodes during tree building with custom constructor functions
- **Dynamic Link Resolution**: Extract links from nodes using custom functions
- **Cycle Detection**: Automatically handles cycles in the graph
- **Topological Sorting**: Generate dependency-ordered lists of tree nodes
- **Deep Traversal**: Continues searching through filtered-out nodes to find matching descendants

## Installation

Simply copy the `FilteredTreeBuilder` class into your Python project. No external dependencies required.

## Usage

### Basic Example

```python
# Define your graph
graph = {
    'A': {'value': 10, 'links': ['B', 'C']},
    'B': {'value': 5, 'links': ['D']},
    'C': {'value': 15, 'links': ['E']},
    'D': {'value': 3, 'links': []},
    'E': {'value': 20, 'links': []}
}

# Create a builder
builder = FilteredTreeBuilder(
    graph=graph,
    filter_func=lambda node: node['value'] > 7,
    links_func=lambda node: node.get('links', []),
    node_constructor=lambda node: {'value': node['value']}
)

# Build the tree starting from node 'A'
tree = builder.construct_tree('A')

# Perform topological sort
sorted_nodes = builder.topological_sort(tree)
```

### Constructor Parameters

#### `__init__(graph, filter_func, links_func, node_constructor)`

- **`graph`** (dict): Dictionary containing all nodes in the graph
- **`filter_func`** (callable): Function that takes a node and returns `True` to include it, `False` to skip it
- **`links_func`** (callable): Function that takes a node and returns a list of connected node keys
- **`node_constructor`** (callable): Function that takes a node and returns a new node object for the tree

### Methods

#### `construct_tree(start_node)`

Builds a filtered tree starting from the specified node.

**Parameters:**
- `start_node` (str): The key of the starting node in the graph

**Returns:**
- `dict`: Dictionary where keys are node identifiers and values are constructed nodes with a `links` field

**Example:**
```python
tree = builder.construct_tree('A')
# Returns: {'A': {'value': 10, 'links': ['C', 'E']}, 'C': {...}, 'E': {...}}
```

#### `topological_sort(tree)`

Performs a topological sort on the constructed tree.

**Parameters:**
- `tree` (dict): Dictionary returned by `construct_tree()`

**Returns:**
- `list`: List of node keys in topological order (dependencies before dependents)

**Raises:**
- `ValueError`: If the graph contains a cycle

**Example:**
```python
sorted_keys = builder.topological_sort(tree)
# Returns: ['A', 'C', 'E']  (parents before children)
```

## How It Works

### Filtering Behavior

The builder traverses the graph depth-first, but with special filtering behavior:

1. **Nodes that pass the filter** are included in the result with their links
2. **Nodes that fail the filter** are skipped, but their children are still explored
3. **Links are promoted** - if a node is filtered out, its valid descendants become direct children of the nearest included ancestor

### Example

Given this graph where we filter for `value > 7`:

```
A (10) → B (5) → D (12)
      → C (15)
```

Node B has `value = 5` (fails filter), but D has `value = 12` (passes filter).

Result:
- A is included with links to [C, D]
- B is excluded but its children are explored
- C is included
- D is included (promoted as direct child of A)

### Topological Sort

The topological sort uses Kahn's algorithm:

1. Calculate in-degree (number of incoming edges) for each node
2. Start with nodes that have zero in-degree
3. Process nodes and reduce in-degree of their children
4. Continue until all nodes are processed

The result is a linear ordering where each node appears before any of its descendants.

## Advanced Examples

### Custom Node Construction

Transform nodes during tree building:

```python
builder = FilteredTreeBuilder(
    graph=graph,
    filter_func=lambda node: node['value'] > 7,
    links_func=lambda node: node.get('links', []),
    node_constructor=lambda node: {
        'original_value': node['value'],
        'doubled': node['value'] * 2,
        'metadata': node.get('extra_data', 'N/A')
    }
)
```

### Conditional Link Following

Only follow certain types of links:

```python
builder = FilteredTreeBuilder(
    graph=graph,
    filter_func=lambda node: node['active'],
    links_func=lambda node: [
        link for link in node.get('links', [])
        if link.startswith('valid_')
    ],
    node_constructor=lambda node: node.copy()
)
```

### Different Link Field Names

If your graph uses a different field name for connections:

```python
builder = FilteredTreeBuilder(
    graph=graph,
    filter_func=lambda node: node['include'],
    links_func=lambda node: node.get('children', []),  # or 'connections', 'edges', etc.
    node_constructor=lambda node: node.copy()
)
```

## Result Format

The `construct_tree()` method returns a dictionary with this structure:

```python
{
    'node_key_1': {
        'links': ['node_key_2', 'node_key_3'],
        # ... other fields from node_constructor
    },
    'node_key_2': {
        'links': [],
        # ... other fields
    },
    'node_key_3': {
        'links': ['node_key_4'],
        # ... other fields
    }
}
```

- Keys are node identifiers from the original graph
- Values are nodes created by `node_constructor`
- Each node has a `links` field containing keys that reference other nodes in the same dictionary

## Common Use Cases

- **Dependency Resolution**: Build trees of dependencies and sort them for execution order
- **Graph Filtering**: Extract subgraphs that meet certain criteria
- **Tree Transformation**: Convert complex graphs into simplified tree structures
- **Build Systems**: Determine build order for projects with dependencies
- **Task Scheduling**: Order tasks based on their dependencies
- **Data Processing Pipelines**: Create execution order for data transformations

## Limitations

- The input graph must be represented as a Python dictionary
- Node keys must be hashable (strings, numbers, tuples)
- The `topological_sort` method requires an acyclic graph (DAG)
- Cycle detection during tree construction prevents infinite loops, but filtered nodes still count as visited

## License

MIT License 



## Contributing

[Specify contribution guidelines here]
```

This README provides:
- Clear overview and features
- Installation instructions
- Comprehensive usage examples
- Detailed parameter documentation
- Explanation of filtering behavior
- Advanced examples for different use cases
- Result format specification
- Common use cases
- Known limitations