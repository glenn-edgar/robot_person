# YamlGenerator

A Python class for generating hierarchical YAML configuration files using PostgreSQL ltree-style dot-separated naming conventions.

## Overview

The `YamlGenerator` class provides a structured way to build complex, nested configuration files where each node is stored with a unique ltree-style path (e.g., `database.postgresql.connection.host`). This approach allows for easy querying, filtering, and management of hierarchical configuration data.

## Features

- **Ltree-style naming**: Uses dot-separated paths for hierarchical organization
- **Composite and simple nodes**: Support for both container nodes and leaf nodes
- **Metadata support**: Each node can store both configuration metadata and actual data
- **Path tracking**: Automatic path management with validation
- **YAML persistence**: Load existing configurations and save updates
- **Type safety**: Built-in validation for path consistency

## Installation

Requires Python 3.6+ and PyYAML:

```bash
pip install PyYAML
```

## Quick Start

```python
from pathlib import Path
from yaml_generator import YamlGenerator

# Initialize generator
generator = YamlGenerator(Path("config.yaml"))

# Add simple configuration nodes
generator.define_simple_node("app", "name", 
                            {"description": "Application name"}, 
                            {"value": "MyApp", "type": "string"})

generator.define_simple_node("app", "version", 
                            {"description": "Version info"}, 
                            {"value": "1.0.0", "build": 42})

# Create nested structure with composite nodes
generator.define_composite_node("database", "postgresql", 
                               {"description": "Database config"}, 
                               {"port": 5432, "enabled": True})

# Add nodes inside the composite
generator.define_simple_node("connection", "host", 
                            {"required": True}, 
                            {"value": "localhost"})

# Return to parent level
generator.pop_path("database", "postgresql")

# Generate the YAML file
generator.generate_yaml()
```

## API Reference

### Constructor

```python
YamlGenerator(yaml_file: Path, path_list: list = None)
```

- `yaml_file`: Path where the YAML file will be created/loaded
- `path_list`: Optional initial path context (defaults to empty list)

### Methods

#### `define_simple_node(label_name, node_name, label_dict=None, node_dict=None)`

Creates a leaf node in the configuration hierarchy.

**Parameters:**
- `label_name`: The category/label for this node
- `node_name`: The specific name of this node
- `label_dict`: Metadata about the label (validation rules, descriptions, etc.)
- `node_dict`: The actual configuration data for this node

**Example:**
```python
generator.define_simple_node("server", "port", 
                            {"min": 1, "max": 65535, "required": True}, 
                            {"value": 8080, "protocol": "HTTP"})
```

#### `define_composite_node(label_name, node_name, label_dict=None, node_dict=None)`

Creates a container node that can hold other nodes. Updates the current path context.

**Parameters:**
- Same as `define_simple_node`

**Example:**
```python
generator.define_composite_node("database", "postgresql", 
                               {"description": "PostgreSQL configuration"}, 
                               {"port": 5432, "enabled": True})
```

#### `pop_path(label_name, node_name)`

Returns to the parent level in the hierarchy by removing the specified composite node from the current path.

**Parameters:**
- `label_name`: The label name to remove from path
- `node_name`: The node name to remove from path

**Example:**
```python
generator.pop_path("database", "postgresql")
```

#### `generate_yaml()`

Saves the current configuration to the YAML file and returns the data structure.

**Returns:** Dictionary containing all ltree-named configuration nodes

#### `get_current_path()`

Returns the current path as a list.

**Returns:** List of path components

#### `get_current_ltree_prefix()`

Returns the current path as a dot-separated string.

**Returns:** String representing the current ltree prefix

## Data Structure

Each configuration entry is stored with an ltree-style key and contains four fields:

```yaml
app.name:
  label: app
  node_name: name
  label_dict:
    description: Application name
    type: string
  node_dict:
    value: MyApplication
    default: unnamed_app

database.postgresql.connection.host:
  label: connection
  node_name: host
  label_dict:
    required: true
    validation: hostname
  node_dict:
    value: localhost
    timeout: 30
```

### Field Descriptions

- **`label`**: The category or grouping for this configuration item
- **`node_name`**: The specific identifier for this configuration item
- **`label_dict`**: Metadata about the configuration (validation rules, descriptions, constraints)
- **`node_dict`**: The actual configuration values and related data

## Example Output

Running the included test case generates a YAML file like this:

```yaml
app.name:
  label: app
  label_dict:
    description: Application name
  node_dict:
    type: string
    value: MyApplication
  node_name: name

app.version:
  label: app
  label_dict:
    description: Version info
  node_dict:
    build: 42
    value: 1.0.0
  node_name: version

database.postgresql:
  label: database
  label_dict:
    description: Database configuration
  node_dict:
    enabled: true
    port: 5432
  node_name: postgresql

database.postgresql.connection.host:
  label: connection
  label_dict:
    required: true
  node_dict:
    type: hostname
    value: localhost
  node_name: host
```

## Use Cases

- **Configuration Management**: Hierarchical application settings
- **Database Schemas**: PostgreSQL ltree-compatible configuration storage
- **API Configuration**: Nested service and endpoint configurations
- **Environment Management**: Multi-environment configuration with inheritance
- **Validation Frameworks**: Configuration with built-in validation metadata

## Best Practices

1. **Use descriptive labels and node names** for better organization
2. **Store validation rules in `label_dict`** for automated validation
3. **Keep actual values in `node_dict`** separate from metadata
4. **Use composite nodes** for logical grouping of related configurations
5. **Always `pop_path()`** after defining nested structures to maintain proper hierarchy

## Error Handling

The class includes several validation checks:

- **File path validation**: Ensures parent directories exist
- **Path consistency**: Validates path operations match current state
- **Type checking**: Ensures path_list is a valid list
- **Hierarchy validation**: Prevents invalid pop operations

## License

This code is provided as-is for educational and development purposes.

## Contributing

When contributing to this project:

1. Maintain the ltree naming convention
2. Add appropriate error handling
3. Include test cases for new functionality
4. Update documentation for API changes

