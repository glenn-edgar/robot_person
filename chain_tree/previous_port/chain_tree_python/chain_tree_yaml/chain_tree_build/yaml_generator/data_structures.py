from .yaml_generator import YamlGenerator
from pathlib import Path
import yaml
import tempfile
import os

class DataStructures(YamlGenerator):
    def __init__(self, yaml_file: Path):
        YamlGenerator.__init__(self, yaml_file)
        
        
    
    def kb_define_stream_field(self, stream_key, stream_length, description):
        """
        Add a new stream field to the knowledge base
        
        Args:
            stream_key (str): The key/name of the stream field
            stream_length (int): The length of the stream
          
            
        Raises:
            TypeError: If stream_key is not a string or properties is not a dictionary
        """
        if not isinstance(stream_key, str):
            raise TypeError("stream_key must be a string")
        
        if not isinstance(stream_length, int):
            raise TypeError("stream_length must be an integer")
        properties = {"stream_length": stream_length}
       
        
        # Add the node to the knowledge base
        self.define_simple_node("KB_STREAM_FIELD", stream_key, properties, {},description)
        
        
    def kb_define_rpc_client_field(self, rpc_client_key,queue_depth, description):
        """
        Add a new rpc_client field to the knowledge base
        
        Args:
            rpc_client_key (str): The key/name of the rpc_client field
            description (str): The description of the rpc_client field
            
        Raises:
            TypeError: If rpc_client_key is not a string or initial_properties is not a dictionary
        """
        if not isinstance(rpc_client_key, str):
            raise TypeError("rpc_client_key must be a string")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        if not isinstance(queue_depth, int):
            raise TypeError("queue_depth must be an integer")
        
        properties = {"queue_depth": queue_depth}
        
        
        # Convert dictionaries to JSON strings
        
        
        # Add the node to the knowledge base
        self.define_simple_node("KB_RPC_CLIENT_FIELD", rpc_client_key, properties,{})
        
        #print(f"Added rpc_client field '{rpc_client_key}' with properties: {properties}")
        
        return {
            "rpc_client": "success",
            "message": f"rpc_client field '{rpc_client_key}' added successfully",
            "properties": properties,
            "data": description
        }
        
        
    def kb_define_status_field(self, status_key, properties, description,initial_data):
        """
        Add a new status field to the knowledge base
        
        Args:
            status_key (str): The key/name of the status field
            initial_properties (dict): Initial properties for the status field
            description (str): The description of the status field
            initial_data (dict): Initial data for the status field
            
        Raises:
            TypeError: If status_key is not a string or initial_properties is not a dictionary
        """
        if not isinstance(status_key, str):
            raise TypeError("status_key must be a string")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        if not isinstance(initial_data, dict):
            raise TypeError("initial_data must be a dictionary")
            
        if  properties == None:
            initial_properties = {}
        if not isinstance(properties, dict):
            raise TypeError("properties must be a dictionary")
       
        
        #print(f"Added status field '{status_key}' with properties: {properties} and data: {initial_data}")
        
        # Add the node to the knowledge base
        self.define_simple_node("KB_STATUS_FIELD", status_key, properties, initial_data)
        
    def kb_define_rpc_server_field(self, rpc_server_key,queue_depth, description):
        """
        Add a new status field to the knowledge base
        
        Args:
            rpc_server_key (str): The key/name of the status field
            queue_depth (int): The length of the rpc_server
            description (str): The description of the rpc_server
            
        Raises:
            TypeError: If status_key is not a string or properties is not a dictionary
        """
        if not isinstance(rpc_server_key, str):
            raise TypeError("rpc_server_key must be a string")
        
        if not isinstance(queue_depth, int):
            raise TypeError("queue_depth must be an integer")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        properties = {'queue_depth': queue_depth}
 
        data = {}
        
        # Add the node to the knowledge base
        self.define_simple_node("KB_RPC_SERVER_FIELD", rpc_server_key, properties, data)

        
    def kb_define_job_field(self, job_key, job_length,description):
        """
        Add a new stream field to the knowledge base
        
        Args:
            job_key (str): The key/name of the stream field
            job_length (int): The length of the job
            description (str): The description of the job queue
            
        Raises:
            TypeError: If stream_key is not a string or properties is not a dictionary
        """
        if not isinstance(job_key, str):
            raise TypeError("job_key must be a string")
        
        if not isinstance(job_length, int):
            raise TypeError("job_length must be an integer")
        properties = {'job_length': job_length}
    
    
        data = {}
        
        # Add the node to the knowledge base
        self.define_simple_node("KB_JOB_QUEUE", job_key, properties, data)
      
        
    def nats_define_rpc_client_field(self, rpc_client_key,queue_depth, description):
        """
        Add a new rpc_client field to the knowledge base
        
        Args:
            rpc_client_key (str): The key/name of the rpc_client field
            description (str): The description of the rpc_client field
            
        Raises:
            TypeError: If rpc_client_key is not a string or initial_properties is not a dictionary
        """
        if not isinstance(rpc_client_key, str):
            raise TypeError("rpc_client_key must be a string")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        if not isinstance(queue_depth, int):
            raise TypeError("queue_depth must be an integer")
        
        properties = {"queue_depth": queue_depth}
        
        
        # Convert dictionaries to JSON strings
        
        
        # Add the node to the knowledge base
        self.define_simple_node("NATS_RPC_CLIENT_FIELD", rpc_client_key, properties,{})
        
        #print(f"Added rpc_client field '{rpc_client_key}' with properties: {properties}")
        
        return {
            "rpc_client": "success",
            "message": f"rpc_client field '{rpc_client_key}' added successfully",
            "properties": properties,
            "data": description
        }
        
        
    def nats_define_status_field(self, status_key, properties, description,initial_data):
        """
        Add a new status field to the knowledge base
        
        Args:
            status_key (str): The key/name of the status field
            initial_properties (dict): Initial properties for the status field
            description (str): The description of the status field
            initial_data (dict): Initial data for the status field
            
        Raises:
            TypeError: If status_key is not a string or initial_properties is not a dictionary
        """
        if not isinstance(status_key, str):
            raise TypeError("status_key must be a string")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        if not isinstance(initial_data, dict):
            raise TypeError("initial_data must be a dictionary")
            
        if  properties == None:
            initial_properties = {}
        if not isinstance(properties, dict):
            raise TypeError("properties must be a dictionary")
       
        
        #print(f"Added status field '{status_key}' with properties: {properties} and data: {initial_data}")
        
        # Add the node to the knowledge base
        self.define_simple_node("NATS_STATUS_FIELD", status_key, properties, initial_data)
        
    def nats_define_rpc_server_field(self, rpc_server_key,queue_depth, description):
        """
        Add a new status field to the knowledge base
        
        Args:
            rpc_server_key (str): The key/name of the status field
            queue_depth (int): The length of the rpc_server
            description (str): The description of the rpc_server
            
        Raises:
            TypeError: If status_key is not a string or properties is not a dictionary
        """
        if not isinstance(rpc_server_key, str):
            raise TypeError("rpc_server_key must be a string")
        
        if not isinstance(queue_depth, int):
            raise TypeError("queue_depth must be an integer")
        if not isinstance(description, str):
            raise TypeError("description must be a string")
        properties = {'queue_depth': queue_depth}
 
        data = {}
        
        # Add the node to the knowledge base
        self.define_simple_node("NATS_RPC_SERVER_FIELD", rpc_server_key, properties, data)

        
    def nats_define_job_field(self, job_key, job_length,description):
        """
        Add a new stream field to the knowledge base
        
        Args:
            job_key (str): The key/name of the stream field
            job_length (int): The length of the job
            description (str): The description of the job queue
            
        Raises:
            TypeError: If stream_key is not a string or properties is not a dictionary
        """
        if not isinstance(job_key, str):
            raise TypeError("job_key must be a string")
        
        if not isinstance(job_length, int):
            raise TypeError("job_length must be an integer")
        properties = {'job_length': job_length}
    
    
        data = {}
        
        # Add the node to the knowledge base
        self.define_simple_node("NATS_JOB_QUEUE", job_key, properties, data)   
 
if __name__ == "__main__":
    print("LTREE YAML Generator Test Case")
    print("=" * 50)
    
    # Use a persistent file in the current directory
    yaml_file = Path("config.yaml")
    
    print(f"Creating/Overwriting YAML file at: {yaml_file.absolute()}")
    print("-" * 50)
    
    # Initialize the generator
    generator = DataStructures(yaml_file,"app")
    
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
    print(generator.kb_dict)
    
    print("Generating LTREE YAML file...")
    data = generator.generate_yaml()
    
    # Read and display the generated YAML
    print("\nGenerated LTREE YAML content:")
    print("-" * 50)
    with open(yaml_file, 'r') as f:
        content = f.read()
        print(content)
    
    # Show the structure explanation
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