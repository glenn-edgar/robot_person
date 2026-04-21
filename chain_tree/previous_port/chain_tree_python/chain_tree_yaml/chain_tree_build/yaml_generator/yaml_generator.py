from pathlib import Path
import yaml
import tempfile
import os


class YamlGenerator:
    def __init__(self, yaml_file: Path):
        
        self.yaml_file = yaml_file
        self.path_list = []
        self.kb_log_dict = {}
        self.kb_dict = {}
        self.working_kb = None
        self.yaml_data = {}  # Flat structure with ltree keys
        self.separator = "."  # Fixed separator for ltree names
        
        # check yaml file path is valid (parent directory exists)
        if not self.yaml_file.parent.exists():
            raise FileNotFoundError(f"Parent directory for yaml file does not exist: {self.yaml_file.parent}")
        
        #self.define_composite_node("kb",starting_kb,{},{})
 
        
      
    
    def _create_ltree_name(self, label_name: str, node_name: str) -> str:
        """Create an ltree name from current path plus label and node"""
        all_parts = self.path_list + [label_name, node_name]
        return self.separator.join(all_parts),self.separator.join(self.path_list)
    
    def generate_yaml(self):
        self.yaml_data["kb_log_dict"] = self.kb_log_dict
        if len(self.kb_dict.keys()) != 0:
            raise ValueError(f"DBS still open: {self.kb_dict.keys()}")
        
        
        with open(self.yaml_file, 'w') as f:
            yaml.dump(self.yaml_data, f, default_flow_style=False, sort_keys=False)
        
        return self.yaml_data
    
    def define_composite_node(self, label_name: str, node_name: str, 
                            label_dict: dict = None, node_dict: dict = None):
        """Define a composite node that updates the path for nested nodes"""
        label_dict = label_dict or {}
        node_dict = node_dict or {}
        
        # Create ltree name for this node
        ltree_name,parent_ltree_name = self._create_ltree_name(label_name, node_name)
        label_dict["parent_ltree_name"] = parent_ltree_name
        label_dict["ltree_name"] = ltree_name
        # Store as a dictionary with all four fields
        self.yaml_data[ltree_name] = {
            "label": label_name,
            "node_name": node_name,
            "label_dict": label_dict,
            "node_dict": node_dict
        }
        
        # Update path list to include this composite node
        self.path_list.append(label_name)
        self.path_list.append(node_name)
        return ltree_name
        
    def define_simple_node(self, label_name: str, node_name: str, 
                          label_dict: dict = None, node_dict: dict = None):
        """Define a simple node (leaf node) in the ltree structure"""
        label_dict = label_dict or {}
        node_dict = node_dict or {}
        
        # Create ltree name for this node
        ltree_name,parent_ltree_name = self._create_ltree_name(label_name, node_name)
        label_dict["parent_ltree_name"] = parent_ltree_name
        label_dict["ltree_name"] = ltree_name
        # Store as a dictionary with all four fields
        self.yaml_data[ltree_name] = {
            "label": label_name,
            "node_name": node_name,
            "label_dict": label_dict,
            "node_dict": node_dict
        }
        return ltree_name
        
        # Don't update self.path_list for simple nodes
        
    def pop_path(self, label_name: str, node_name: str):
        """Pop the path to go back up the hierarchy"""
        if len(self.path_list) < 2:
            raise ValueError("Path list is too short to pop")
        
        local_node = self.path_list.pop()
        local_label = self.path_list.pop()
        
        if local_node != node_name or local_label != label_name:
            raise ValueError(f"Path mismatch: expected ({label_name}, {node_name}), "
                           f"got ({local_label}, {local_node})")
    
    def get_current_path(self) -> list:
        """Get the current path as a list"""
        return self.path_list.copy()
  
    def set_path_list(self, path_list: list):
    
        if not isinstance(path_list, list):
            raise TypeError("Path list must be a list")
        self.path_list = path_list.copy()
    
    def get_current_ltree_prefix(self) -> str:
        """Get the current path as an ltree prefix"""
        return self.separator.join(self.path_list) if self.path_list else ""

    def add_kb(self, kb_name):
        #print("Adding knowledge base",kb_name)
        if kb_name in self.kb_dict:
            raise ValueError(f"Knowledge base {kb_name} already exists")
        path_list = ["kb",kb_name]
        self.kb_dict[kb_name] = path_list
        self.kb_log_dict[kb_name] = path_list.copy()
        
        #self.define_composite_node("kb",kb_name,{},{})
 
    def select_kb(self, kb_name):
        #print("Selecting knowledge base",kb_name)
        if kb_name == self.working_kb:
            return 
        if kb_name not in self.kb_dict:
            #print(kb_name,self.kb_dict)
            raise ValueError(f"Knowledge base {kb_name} does not exist")
        self.path_list = self.kb_dict[kb_name]
        self.working_kb = kb_name
         
        
    def get_working_kb(self):
        return self.working_kb
    
    def leave_kb(self):
    
        #print("Leaving knowledge base",self.working_kb,self.path_list)
        if len(self.path_list) != 2:
    
            raise ValueError("Path list is not at the root level")
        self.pop_path(self.path_list[0],self.path_list[1])
        #print("Leaving knowledge base",self.working_kb,self.kb_dict)
        del self.kb_dict[self.working_kb]
        self.working_kb = None
        
        
if __name__ == "__main__":
    print("LTREE YAML Generator Test Case")
    print("=" * 50)
    
    # Use a persistent file in the current directory
    yaml_file = Path("config.yaml")
    
    print(f"Creating/Overwriting YAML file at: {yaml_file.absolute()}")
    print("-" * 50)
    
    # Initialize the generator
    generator = YamlGenerator(yaml_file,"app")
    
    # Build a configuration structure with ltree names
    print("Building configuration with ltree structure...")
    
    
    
    
    # Add some top-level simple nodes
    generator.define_simple_node("app", "name", 
                                {"description": "Application name"}, 
                                {"value": "MyApplication", "type": "string"})
    
    generator.define_simple_node("app", "version", 
                                {"description": "Version info"}, 
                                {"value": "1.0.0", "build": 42})
    
    # Create a composite node for database settings
    generator.define_composite_node("database", "postgresql", 
                                   {"description": "Database configuration"}, 
                                   {"port": 5432, "enabled": True})
    
    # Add settings inside the database composite node
    generator.define_simple_node("connection", "host", 
                                {"required": True}, 
                                {"value": "localhost", "type": "hostname"})
    
    generator.define_simple_node("connection", "max_connections", 
                                {"min": 1, "max": 1000}, 
                                {"value": 100, "timeout": 30})
    
    generator.define_simple_node("auth", "username", 
                                {"required": True}, 
                                {"value": "db_user"})
    
    generator.define_simple_node("auth", "password", 
                                {"required": True, "sensitive": True}, 
                                {"value": "secret123", "encrypted": False})
    
    # Create a deeper nested structure
    generator.define_composite_node("pool", "settings", 
                                   {"description": "Connection pool settings"}, 
                                   {"size": 10, "overflow": 5})
    
    generator.define_simple_node("timeout", "connection", 
                                {"unit": "seconds"}, 
                                {"seconds": 30})
    
    generator.define_simple_node("timeout", "idle", 
                                {"unit": "seconds"}, 
                                {"seconds": 300})
    
    generator.pop_path("pool", "settings")
    
    # Pop back to root level
    generator.pop_path("database", "postgresql")
    
    # Add another top-level node
    generator.define_simple_node("logging", "level", 
                                {"options": ["DEBUG", "INFO", "WARNING", "ERROR"]}, 
                                {"value": "INFO", "format": "json"})
    
    generator.define_simple_node("logging", "file", 
                                {"description": "Log file configuration"}, 
                                {"path": "/var/log/app.log", "rotate": True, "max_size": "10MB"})
    
    # Add server configuration
    generator.define_simple_node("server", "host", 
                                {"description": "Server binding address"}, 
                                {"value": "0.0.0.0"})
    
    generator.define_simple_node("server", "port", 
                                {"description": "Server port", "min": 1, "max": 65535}, 
                                {"value": 8080})
    
    generator.leave_kb()
    
    print("Generating LTREE YAML file...")
    data = generator.generate_yaml()
    
    # Read and display the generated YAML
    print("\nGenerated LTREE YAML content:")
    print("-" * 50)
    with open(yaml_file, 'r') as f:
        content = f.read()
        print(content)
    
    # Show the structure explanationk
    print("\nStructure Explanation:")
    print("-" * 50)
    print("Each entry has:")
    print("- LTREE name (key): The full dot-separated path")
    print("- Dictionary value with fields:")
    print("  - label: The label part of this node")
    print("  - node_name: The node name part")
    print("  - label_dict: Metadata/configuration for the label")
    print("  - node_dict: The actual data for the node")
    print()
    
    # Verify the structure
    print("Verifying LTREE structure...")
    print("-" * 50)
    
    # Load the YAML to verify it's valid
    with open(yaml_file, 'r') as f:
        loaded_data = yaml.safe_load(f)
    
    # Show some example entries
    print("\nExample entries:")
    example_keys = [
        "app.name",
        "app.version",
        "database.postgresql",
        "database.postgresql.connection.host",
        "database.postgresql.pool.settings.timeout.idle"
    ]
    
    for key in example_keys:
        if key in loaded_data:
            entry = loaded_data[key]
            print(f"\nLTREE: {key}")
            print(f"  label: {entry['label']}")
            print(f"  node_name: {entry['node_name']}")
            print(f"  label_dict: {entry['label_dict']}")
            print(f"  node_dict: {entry['node_dict']}")
    
    print("\n" + "-" * 50)
    
    # Check specific elements
    checks = [
        ("app.name exists", "app.name" in loaded_data),
        ("app.name has correct structure", 
         loaded_data.get("app.name", {}).get("label") == "app" and
         loaded_data.get("app.name", {}).get("node_name") == "name"),
        ("database.postgresql exists", "database.postgresql" in loaded_data),
        ("Nested path exists", "database.postgresql.connection.host" in loaded_data),
        ("Deep nested path exists", "database.postgresql.pool.settings.timeout.idle" in loaded_data),
        ("Node data preserved", 
         loaded_data.get("database.postgresql", {}).get("node_dict", {}).get("port") == 5432),
        ("Label metadata preserved",
         loaded_data.get("auth.password", {}).get("label_dict", {}).get("sensitive") == True if "auth.password" in loaded_data else
         loaded_data.get("database.postgresql.auth.password", {}).get("label_dict", {}).get("sensitive") == True),
    ]
    
    all_passed = True
    for check_name, result in checks:
        status = "✓" if result else "✗"
        print(f"{status} {check_name}")
        if not result:
            all_passed = False
    
    print("-" * 50)
    print(f"Total LTREE entries in YAML: {len(loaded_data)}")
    print("-" * 50)
    
    if all_passed:
        print("✓ All tests passed successfully!")
    else:
        print("✗ Some tests failed!")
    
    print("=" * 50)
    print(f"\nYAML file created in current directory:")
    print(f"  - {yaml_file.absolute()}")
    print("\nThis file will persist and be overwritten on the next run.")