# Integration Instructions: Adding Bulk Macro Registration

## Quick Integration

Add these methods to your `LispSequencer` class in `lisp_sequencer_with_macros.py`:

### 1. Add imports at the top of the file:

```python
import yaml
import json
```

### 2. Add these methods to the LispSequencer class:

```python
# Add after the define_macro() method

def define_macros_bulk(self, macro_definitions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Register multiple macros at once from a dictionary."""
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
    """Load macro definitions from a YAML file."""
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
    """Load macro definitions from a JSON file."""
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
    """Export all defined macros to a YAML file."""
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
    """List all defined macros with their details."""
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
    """Get details of a specific macro."""
    if name not in self.macros:
        return {'found': False}
    
    params, template = self.macros[name]
    return {
        'found': True,
        'params': params,
        'template': template
    }

def remove_macro(self, name: str) -> bool:
    """Remove a macro by name."""
    if name in self.macros:
        del self.macros[name]
        return True
    return False

def clear_macros(self) -> int:
    """Remove all macros."""
    count = len(self.macros)
    self.macros.clear()
    return count
```

## Complete Usage Example

```python
#!/usr/bin/env python3
"""
Complete example showing all macro registration methods.
"""

from lisp_sequencer_with_macros import LispSequencer

# Control codes
CONTROL_CODES = [
    "CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", 
    "CFL_RESET", "CFL_DISABLE"
]

# Mock functions
def run_fn(handle, func_type, func_name, node, event_id, event_data, params=[]):
    """Execute a function."""
    if func_type == '@':
        print(f"  → @{func_name}{params}")
    elif func_type == '?':
        print(f"  → ?{func_name}{params}")
        return True
    elif func_type == '!':
        print(f"  → !{func_name}{params}")
        return "CFL_CONTINUE"

def debug_fn(handle, message, node, event_id, event_data):
    """Output debug messages."""
    print(f"  [DEBUG] {message}")

# Initialize
seq = LispSequencer("handle", run_fn, debug_fn, control_codes=CONTROL_CODES)

print("=" * 70)
print("METHOD 1: Individual Registration")
print("=" * 70)

seq.define_macro("simple", ["action"], "(pipeline $action 'CFL_CONTINUE)")
print("✓ Registered 'simple' macro")

print("\n" + "=" * 70)
print("METHOD 2: Bulk Registration")
print("=" * 70)

macros = {
    "log_it": {
        "params": ["msg"],
        "template": "(@log $msg)"
    },
    "validated": {
        "params": ["check", "action"],
        "template": "(if $check $action 'CFL_HALT)"
    }
}

result = seq.define_macros_bulk(macros)
print(f"✓ Registered {len(result['registered'])} macros")

print("\n" + "=" * 70)
print("METHOD 3: Load from YAML")
print("=" * 70)

# Create a test YAML file
yaml_content = """macros:
  yaml_test:
    params: [p1]
    template: "(@test $p1)"
"""

with open("/tmp/test_macros.yaml", "w") as f:
    f.write(yaml_content)

result = seq.load_macros_from_yaml("/tmp/test_macros.yaml")
print(f"✓ Loaded {len(result['registered'])} macros from YAML")

print("\n" + "=" * 70)
print("METHOD 4: Load from JSON")
print("=" * 70)

# Create a test JSON file
json_content = """{
  "macros": {
    "json_test": {
      "params": ["p1"],
      "template": "(@test $p1)"
    }
  }
}"""

with open("/tmp/test_macros.json", "w") as f:
    f.write(json_content)

result = seq.load_macros_from_json("/tmp/test_macros.json")
print(f"✓ Loaded {len(result['registered'])} macros from JSON")

print("\n" + "=" * 70)
print("LIST ALL MACROS")
print("=" * 70)

for macro in seq.list_macros():
    print(f"  - {macro['name']}: {macro['param_count']} param(s)")

print("\n" + "=" * 70)
print("GET SPECIFIC MACRO")
print("=" * 70)

details = seq.get_macro("validated")
if details['found']:
    print(f"Name: validated")
    print(f"Params: {details['params']}")
    print(f"Template: {details['template']}")

print("\n" + "=" * 70)
print("EXPORT MACROS")
print("=" * 70)

result = seq.export_macros_to_yaml("/tmp/exported_macros.yaml")
print(f"✓ Exported {result['exported_count']} macros to YAML")

print("\n" + "=" * 70)
print("USE A MACRO")
print("=" * 70)

code = """
(dispatch event_id
  ("test.event"
   (validated ?check !action))
  (default 'CFL_DISABLE))
"""

result = seq.check_lisp_instruction_with_macros(code)
print(f"Valid: {result['valid']}")
print(f"\nExpanded code:")
print(result['expanded_text'])

if result['valid']:
    print("\nExecuting:")
    outcome = seq.run_lisp_instruction("node1", result, "test.event", {})
    print(f"Result: {outcome}")

print("\n" + "=" * 70)
print("CLEANUP")
print("=" * 70)

# Remove specific macro
if seq.remove_macro("simple"):
    print("✓ Removed 'simple' macro")

# Clear all macros
count = seq.clear_macros()
print(f"✓ Cleared {count} macros")

remaining = len(seq.list_macros())
print(f"Remaining macros: {remaining}")
```

## Testing the Integration

Run this test to verify everything works:

```bash
python your_updated_file.py
```

You should see output showing:
- ✓ Individual macro registration
- ✓ Bulk macro registration
- ✓ YAML file loading
- ✓ JSON file loading
- ✓ Macro listing
- ✓ Macro details retrieval
- ✓ Macro export
- ✓ Macro usage and expansion
- ✓ Macro removal and cleanup

## Compatibility Notes

- **Requires**: PyYAML library (`pip install pyyaml`)
- **Optional**: Can disable YAML/JSON methods if not needed
- **Backward Compatible**: All existing code continues to work
- **Thread Safe**: Macro storage uses plain dict (add locks if needed for multi-threading)

## Performance Considerations

- Bulk registration: O(n) where n = number of macros
- YAML/JSON loading: Adds file I/O overhead (~1-10ms typically)
- Macro lookup: O(1) dictionary access
- No runtime overhead once macros are loaded

Enjoy your enhanced macro system! 🚀


