# Macro Registration Patterns Guide

## Overview

There are multiple ways to register macros in LispSequencer, each suited for different use cases:

1. **Individual Registration** - One at a time
2. **Bulk Registration** - Dictionary of macros
3. **YAML File** - Configuration file
4. **JSON File** - Alternative configuration
5. **Hybrid Approach** - Combination of methods

---

## Pattern 1: Individual Registration

**Best for:** Quick testing, dynamic macro creation, small number of macros

```python
from lisp_sequencer_with_macros import LispSequencer

# Initialize sequencer
seq = LispSequencer(handle, run_fn, debug_fn, control_codes=CONTROL_CODES)

# Register macros one by one
seq.define_macro("log_pipeline", ["msg", "func"], """
(pipeline 
  (@log $msg)
  $func
  'CFL_CONTINUE)
""")

seq.define_macro("validated_action", ["check", "action"], """
(if $check
    (pipeline $action 'CFL_CONTINUE)
    'CFL_HALT)
""")

# Check registration status
result = seq.define_macro("my_macro", ["param"], "template")
if not result['valid']:
    print("Error:", result['errors'])
```

**Pros:**
- Simple and straightforward
- Immediate error feedback
- Good for learning and testing

**Cons:**
- Verbose for many macros
- Harder to organize
- No easy way to share across projects

---

## Pattern 2: Bulk Registration from Dictionary

**Best for:** Programmatic macro generation, grouped macro definitions

```python
# Define all macros in a dictionary
MACRO_DEFINITIONS = {
    "log_pipeline": {
        "params": ["msg", "func"],
        "template": "(pipeline (@log $msg) $func 'CFL_CONTINUE)"
    },
    
    "validated_action": {
        "params": ["check", "action"],
        "template": "(if $check (pipeline $action 'CFL_CONTINUE) 'CFL_HALT)"
    },
    
    "safe_action": {
        "params": ["func"],
        "template": "(pipeline (@log \"Starting\") $func (@log \"Done\") 'CFL_CONTINUE)"
    }
}

# Register all at once
result = seq.define_macros_bulk(MACRO_DEFINITIONS)

print(f"Registered: {len(result['registered'])} macros")
print(f"Failed: {result['failed']}")

if result['errors']:
    print("Errors:")
    for error in result['errors']:
        print(f"  - {error}")
```

**Pros:**
- Clean organization
- Easy to see all macros at once
- Good for version control
- Can be generated programmatically

**Cons:**
- Still in Python code
- Harder to share across different tools

---

## Pattern 3: YAML Configuration File

**Best for:** Shared configurations, team environments, documentation

### Create YAML file (macros.yaml):

```yaml
macros:
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
```

### Load in Python:

```python
# Load from YAML file
result = seq.load_macros_from_yaml("macros.yaml")

print(f"Loaded: {len(result['registered'])} macros")

if not result['valid']:
    print("Errors:")
    for error in result['errors']:
        print(f"  - {error}")

# List loaded macros
for macro in seq.list_macros():
    print(f"  - {macro['name']}: {macro['param_count']} params")
```

**Pros:**
- Human-readable
- Easy to edit without Python knowledge
- Can include comments and documentation
- Shareable across projects and teams
- Version control friendly

**Cons:**
- Requires YAML library
- Slight file I/O overhead (negligible)

---

## Pattern 4: JSON Configuration File

**Best for:** API integration, automated generation, strict schemas

### Create JSON file (macros.json):

```json
{
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
}
```

### Load in Python:

```python
# Load from JSON file
result = seq.load_macros_from_json("macros.json")

print(f"Loaded: {len(result['registered'])} macros")

if not result['valid']:
    print("Errors:")
    for error in result['errors']:
        print(f"  - {error}")
```

**Pros:**
- Standard format
- Easy for API/web integration
- Works with JSON Schema validation
- Most programming languages can generate

**Cons:**
- Less human-readable than YAML
- No multi-line support (need escaping)
- No comments

---

## Pattern 5: Hybrid Approach

**Best for:** Production systems with core + custom macros

```python
# 1. Load core macros from YAML
result = seq.load_macros_from_yaml("core_macros.yaml")
print(f"Core macros: {len(result['registered'])}")

# 2. Load project-specific macros from JSON
result = seq.load_macros_from_json("project_macros.json")
print(f"Project macros: {len(result['registered'])}")

# 3. Add dynamic/runtime macros
seq.define_macro("custom_workflow", ["step1", "step2"], """
(pipeline 
  $step1
  $step2
  'CFL_CONTINUE)
""")

# 4. List all loaded macros
print("\nAll macros:")
for macro in seq.list_macros():
    print(f"  - {macro['name']}")
```

**Pros:**
- Flexible
- Separates concerns (core vs. custom)
- Best of all worlds

**Cons:**
- More complex setup
- Need to manage multiple sources

---

## Pattern 6: Organization by Feature

**Best for:** Large projects with many macros

### Directory structure:
```
macros/
  ├── logging_macros.yaml
  ├── validation_macros.yaml
  ├── notification_macros.yaml
  └── workflow_macros.yaml
```

### Load all macro files:

```python
import os
import glob

def load_macro_directory(seq, directory):
    """Load all YAML macro files from a directory."""
    total_loaded = 0
    
    for yaml_file in glob.glob(os.path.join(directory, "*.yaml")):
        print(f"Loading {os.path.basename(yaml_file)}...")
        result = seq.load_macros_from_yaml(yaml_file)
        
        if result['valid']:
            total_loaded += len(result['registered'])
            print(f"  ✓ Loaded {len(result['registered'])} macros")
        else:
            print(f"  ✗ Errors: {result['errors']}")
    
    return total_loaded

# Load all macros
total = load_macro_directory(seq, "macros/")
print(f"\nTotal macros loaded: {total}")
```

---

## Pattern 7: Environment-Specific Macros

**Best for:** Different configurations for dev/test/prod

```python
import os

# Determine environment
env = os.getenv("ENVIRONMENT", "development")

# Load environment-specific macros
macro_file = f"macros_{env}.yaml"

if os.path.exists(macro_file):
    result = seq.load_macros_from_yaml(macro_file)
    print(f"Loaded {len(result['registered'])} {env} macros")
else:
    print(f"Warning: No macro file for {env} environment")
    # Fall back to default
    seq.load_macros_from_yaml("macros_default.yaml")
```

**File structure:**
```
macros_development.yaml   # More debugging/logging macros
macros_testing.yaml       # Mock/stub macros
macros_production.yaml    # Optimized macros
```

---

## Pattern 8: Macro Management Utilities

```python
class MacroManager:
    """Helper class for managing macros across projects."""
    
    def __init__(self, sequencer):
        self.seq = sequencer
    
    def load_standard_library(self):
        """Load commonly used macros."""
        return self.seq.load_macros_from_yaml("stdlib_macros.yaml")
    
    def load_project_macros(self, project_name):
        """Load project-specific macros."""
        return self.seq.load_macros_from_yaml(f"{project_name}_macros.yaml")
    
    def backup_macros(self, backup_path):
        """Export current macros to backup file."""
        return self.seq.export_macros_to_yaml(backup_path)
    
    def list_by_param_count(self):
        """Group macros by parameter count."""
        from collections import defaultdict
        grouped = defaultdict(list)
        
        for macro in self.seq.list_macros():
            grouped[macro['param_count']].append(macro['name'])
        
        return dict(grouped)
    
    def find_macro(self, search_term):
        """Find macros containing search term."""
        results = []
        for name, (params, template) in self.seq.macros.items():
            if search_term in name or search_term in template:
                results.append(name)
        return results

# Usage
manager = MacroManager(seq)
manager.load_standard_library()
manager.load_project_macros("payment_processor")

# Find all logging-related macros
logging_macros = manager.find_macro("@log")
print("Logging macros:", logging_macros)
```

---

## Recommended Approach for Production

```python
class ProductionMacroSetup:
    """Production-ready macro setup pattern."""
    
    @staticmethod
    def initialize(seq, config_dir="config/macros"):
        """
        Initialize macros from configuration directory.
        
        Directory structure:
            config/macros/
                ├── 00_core.yaml        # Core macros (loaded first)
                ├── 10_logging.yaml     # Logging macros
                ├── 20_validation.yaml  # Validation macros
                ├── 30_workflows.yaml   # Workflow macros
                └── 99_custom.yaml      # Custom/override macros
        """
        results = {
            'total_loaded': 0,
            'total_failed': 0,
            'files_processed': 0,
            'errors': []
        }
        
        # Load files in sorted order (00_, 10_, 20_, etc.)
        macro_files = sorted(glob.glob(os.path.join(config_dir, "*.yaml")))
        
        for macro_file in macro_files:
            results['files_processed'] += 1
            filename = os.path.basename(macro_file)
            
            result = seq.load_macros_from_yaml(macro_file)
            
            if result['valid']:
                results['total_loaded'] += len(result['registered'])
                print(f"✓ {filename}: {len(result['registered'])} macros")
            else:
                results['total_failed'] += result['failed']
                results['errors'].extend(result['errors'])
                print(f"✗ {filename}: {len(result['errors'])} errors")
        
        return results

# Usage
from lisp_sequencer_with_macros import LispSequencer

seq = LispSequencer(handle, run_fn, debug_fn, control_codes=CONTROL_CODES)

# Load all production macros
setup_result = ProductionMacroSetup.initialize(seq)

print(f"\nSummary:")
print(f"  Files processed: {setup_result['files_processed']}")
print(f"  Macros loaded: {setup_result['total_loaded']}")
print(f"  Failures: {setup_result['total_failed']}")

if setup_result['errors']:
    print("\nErrors:")
    for error in setup_result['errors']:
        print(f"  - {error}")
```

---

## Summary Comparison

| Pattern | Use Case | Pros | Cons |
|---------|----------|------|------|
| Individual | Testing, prototyping | Simple | Verbose |
| Bulk Dict | Grouped definitions | Organized | Still in code |
| YAML File | Team projects | Shareable, readable | File I/O |
| JSON File | API integration | Standard format | Less readable |
| Hybrid | Production | Flexible | More complex |
| By Feature | Large projects | Well-organized | Many files |
| Environment | Multi-env deploys | Environment-specific | Multiple configs |
| Managed | Enterprise | Full control | Most complex |

## Best Practice Recommendation

**For most projects, use this approach:**

1. **Core macros** → YAML file (version controlled)
2. **Project macros** → YAML file (project-specific)
3. **Runtime macros** → Individual registration (if needed)

```python
# Best practice setup
seq = LispSequencer(handle, run_fn, debug_fn, control_codes=CONTROL_CODES)

# 1. Load core library
seq.load_macros_from_yaml("macros/core.yaml")

# 2. Load project-specific
seq.load_macros_from_yaml(f"macros/{project_name}.yaml")

# 3. Add any runtime macros
if debug_mode:
    seq.define_macro("debug_trace", ["action"], 
                     "(debug \"Trace\" (pipeline $action 'CFL_CONTINUE))")

# Ready to use!
```

This gives you the best balance of flexibility, maintainability, and ease of use.

