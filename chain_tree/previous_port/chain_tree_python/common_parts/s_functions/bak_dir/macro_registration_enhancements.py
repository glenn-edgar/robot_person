# Macro Registration Enhancements for LispSequencer
# Add these methods to the LispSequencer class

import yaml
import json
from typing import Dict, List, Any

# =============================================================================
# Add these methods to your LispSequencer class
# =============================================================================

def define_macros_bulk(self, macro_definitions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Register multiple macros at once from a dictionary.
    
    Args:
        macro_definitions: Dict of {
            "macro_name": {
                "params": ["param1", "param2"],
                "template": "template text with $param1"
            }
        }
    
    Returns:
        Dict with 'valid', 'errors', and 'registered' (list of successful macro names)
    """
    errors = []
    registered = []
    
    for name, definition in macro_definitions.items():
        if not isinstance(definition, dict):
            errors.append(f"Macro '{name}': definition must be a dictionary")
            continue
        
        if 'params' not in definition:
            errors.append(f"Macro '{name}': missing 'params' field")
            continue
        
        if 'template' not in definition:
            errors.append(f"Macro '{name}': missing 'template' field")
            continue
        
        params = definition['params']
        template = definition['template']
        
        # Validate and register
        result = self.define_macro(name, params, template)
        
        if result['valid']:
            registered.append(name)
        else:
            for error in result['errors']:
                errors.append(f"Macro '{name}': {error}")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'registered': registered,
        'failed': len(macro_definitions) - len(registered)
    }


def load_macros_from_yaml(self, yaml_path: str) -> Dict[str, Any]:
    """
    Load macro definitions from a YAML file.
    
    YAML format:
        macros:
          macro_name:
            params: [param1, param2]
            template: |
              template text
              with $param1 and $param2
    
    Args:
        yaml_path: Path to YAML file
    
    Returns:
        Dict with 'valid', 'errors', 'registered'
    """
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        if not data or 'macros' not in data:
            return {
                'valid': False,
                'errors': ["YAML file must contain 'macros' key"],
                'registered': []
            }
        
        return self.define_macros_bulk(data['macros'])
        
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Failed to load YAML: {str(e)}"],
            'registered': []
        }


def load_macros_from_json(self, json_path: str) -> Dict[str, Any]:
    """
    Load macro definitions from a JSON file.
    
    JSON format:
        {
          "macros": {
            "macro_name": {
              "params": ["param1", "param2"],
              "template": "template with $param1"
            }
          }
        }
    
    Args:
        json_path: Path to JSON file
    
    Returns:
        Dict with 'valid', 'errors', 'registered'
    """
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        if not data or 'macros' not in data:
            return {
                'valid': False,
                'errors': ["JSON file must contain 'macros' key"],
                'registered': []
            }
        
        return self.define_macros_bulk(data['macros'])
        
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Failed to load JSON: {str(e)}"],
            'registered': []
        }


def export_macros_to_yaml(self, yaml_path: str) -> Dict[str, Any]:
    """
    Export all defined macros to a YAML file.
    
    Args:
        yaml_path: Path where YAML file will be written
    
    Returns:
        Dict with 'valid', 'errors', 'exported_count'
    """
    try:
        macros_dict = {}
        for name, (params, template) in self.macros.items():
            macros_dict[name] = {
                'params': params,
                'template': template
            }
        
        data = {'macros': macros_dict}
        
        with open(yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        
        return {
            'valid': True,
            'errors': [],
            'exported_count': len(macros_dict)
        }
        
    except Exception as e:
        return {
            'valid': False,
            'errors': [f"Failed to export YAML: {str(e)}"],
            'exported_count': 0
        }


def list_macros(self) -> List[Dict[str, Any]]:
    """
    List all defined macros with their details.
    
    Returns:
        List of dicts with 'name', 'params', 'param_count', 'template_length'
    """
    return [
        {
            'name': name,
            'params': params,
            'param_count': len(params),
            'template_length': len(template)
        }
        for name, (params, template) in self.macros.items()
    ]


def get_macro(self, name: str) -> Dict[str, Any]:
    """
    Get details of a specific macro.
    
    Args:
        name: Macro name
    
    Returns:
        Dict with 'found', 'params', 'template'
    """
    if name not in self.macros:
        return {'found': False}
    
    params, template = self.macros[name]
    return {
        'found': True,
        'params': params,
        'template': template
    }


def remove_macro(self, name: str) -> bool:
    """
    Remove a macro by name.
    
    Args:
        name: Macro name to remove
    
    Returns:
        True if removed, False if not found
    """
    if name in self.macros:
        del self.macros[name]
        return True
    return False


def clear_macros(self) -> int:
    """
    Remove all macros.
    
    Returns:
        Number of macros removed
    """
    count = len(self.macros)
    self.macros.clear()
    return count


# =============================================================================
# USAGE EXAMPLES
# =============================================================================

if __name__ == "__main__":
    # Example 1: Bulk registration with dictionary
    print("=" * 70)
    print("Example 1: Bulk Macro Registration")
    print("=" * 70)
    
    macro_definitions = {
        "log_pipeline": {
            "params": ["msg", "func"],
            "template": """
(pipeline 
  (@log $msg)
  $func
  'CFL_CONTINUE)
"""
        },
        
        "validated_action": {
            "params": ["check", "action"],
            "template": """
(if $check
    (pipeline $action 'CFL_CONTINUE)
    'CFL_HALT)
"""
        },
        
        "safe_action": {
            "params": ["func"],
            "template": """
(pipeline 
  (@log "Starting")
  $func
  (@log "Done")
  'CFL_CONTINUE)
"""
        }
    }
    
    # In your code, you would do:
    # result = seq.define_macros_bulk(macro_definitions)
    print("Macro definitions:")
    for name, definition in macro_definitions.items():
        params = ", ".join(definition['params'])
        print(f"  - {name}({params})")
    
    print(f"\nTotal: {len(macro_definitions)} macros")
    
    # Example 2: YAML file format
    print("\n" + "=" * 70)
    print("Example 2: YAML Configuration File")
    print("=" * 70)
    
    yaml_example = """macros:
  log_pipeline:
    params: [msg, func]
    template: |
      (pipeline 
        (@log $msg)
        $func
        'CFL_CONTINUE)
  
  validated_action:
    params: [check, action]
    template: |
      (if $check
          (pipeline $action 'CFL_CONTINUE)
          'CFL_HALT)
  
  safe_action:
    params: [func]
    template: |
      (pipeline 
        (@log "Starting")
        $func
        (@log "Done")
        'CFL_CONTINUE)
  
  event_handler:
    params: [validator, processor, notifier]
    template: |
      (pipeline
        $validator
        $processor
        $notifier
        'CFL_CONTINUE)
"""
    
    print("Content of macros.yaml:")
    print(yaml_example)
    
    # Example 3: JSON file format
    print("\n" + "=" * 70)
    print("Example 3: JSON Configuration File")
    print("=" * 70)
    
    json_example = """{
  "macros": {
    "log_pipeline": {
      "params": ["msg", "func"],
      "template": "(pipeline (@log $msg) $func 'CFL_CONTINUE)"
    },
    "validated_action": {
      "params": ["check", "action"],
      "template": "(if $check (pipeline $action 'CFL_CONTINUE) 'CFL_HALT)"
    }
  }
}"""
    
    print("Content of macros.json:")
    print(json_example)
    
    # Example 4: Usage patterns
    print("\n" + "=" * 70)
    print("Example 4: Usage Patterns")
    print("=" * 70)
    
    usage_code = """
# Pattern 1: Inline dictionary registration
macro_defs = {
    "my_macro": {
        "params": ["p1", "p2"],
        "template": "($p1 $p2 'CFL_CONTINUE)"
    }
}
result = seq.define_macros_bulk(macro_defs)

# Pattern 2: Load from YAML file
result = seq.load_macros_from_yaml("macros.yaml")
print(f"Registered {len(result['registered'])} macros")

# Pattern 3: Load from JSON file
result = seq.load_macros_from_json("macros.json")

# Pattern 4: List all macros
macros = seq.list_macros()
for macro in macros:
    print(f"{macro['name']}: {macro['param_count']} params")

# Pattern 5: Get specific macro details
details = seq.get_macro("log_pipeline")
if details['found']:
    print(f"Template: {details['template']}")

# Pattern 6: Remove specific macro
if seq.remove_macro("old_macro"):
    print("Macro removed")

# Pattern 7: Clear all macros
count = seq.clear_macros()
print(f"Removed {count} macros")

# Pattern 8: Export current macros
result = seq.export_macros_to_yaml("exported_macros.yaml")
print(f"Exported {result['exported_count']} macros")
"""
    
    print(usage_code)
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("✓ Bulk registration with define_macros_bulk()")
    print("✓ Load from YAML with load_macros_from_yaml()")
    print("✓ Load from JSON with load_macros_from_json()")
    print("✓ Export to YAML with export_macros_to_yaml()")
    print("✓ List macros with list_macros()")
    print("✓ Query macro with get_macro()")
    print("✓ Remove macro with remove_macro()")
    print("✓ Clear all with clear_macros()")
    print("=" * 70)
