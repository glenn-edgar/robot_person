# LispSequencer

A Lisp-based control flow sequencer for event-driven workflows with macro expansion and Mako template integration.

## Overview

LispSequencer provides a unified approach to defining complex control flow logic using S-expressions. It's designed for embedded and distributed systems where you need consistent behavior across multiple platforms (Python, C, microcontrollers) while maintaining readable, composable control logic.

### Key Features

- **Three function types**: `@void` (side effects), `?boolean` (predicates), `!control` (flow control)
- **Control flow primitives**: `dispatch`, `pipeline`, `if`, `cond`, `debug`
- **Macro system**: Define reusable templates with parameter substitution
- **Mako integration**: Generate S-expressions using Python templates
- **Template defs**: Load Mako `<%def>` blocks as callable Python methods
- **Pre-compilation**: Parse and validate once, execute many times
- **YAML/JSON compatible**: Serialize and deserialize ASTs

## Installation

```bash
pip install mako  # Optional, for template support
```

**Dependencies:**
- Python 3.7+
- `mako` (optional, for template features)

## Quick Start

```python
from lisp_sequencer import LispSequencer

# Define control codes for your system
CONTROL_CODES = [
    "CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", 
    "CFL_RESET", "CFL_DISABLE"
]

# Implement the function executor
def run_function(handle, func_type, func_name, node, event_id, event_data, params=[]):
    """Execute functions called from S-expressions."""
    if func_type == '@':
        # Side effect - return None
        print(f"Execute: {func_name} with {params}")
        return None
    elif func_type == '?':
        # Boolean predicate - return True/False
        return True
    elif func_type == '!':
        # Control flow - return control code
        return "CFL_CONTINUE"

# Optional debug handler
def debug_function(handle, message, node, event_id, event_data):
    print(f"[DEBUG] {message}")

# Create sequencer
seq = LispSequencer(
    handle="my-context",
    run_function=run_function,
    debug_function=debug_function,
    control_codes=CONTROL_CODES
)

# Check and run an instruction
lisp_code = """
(dispatch event_id
  ("order.received" 
   (pipeline 
     (@validate_order)
     (!process_payment)
     (@ship_order)))
  (default 'CFL_CONTINUE))
"""

result = seq.check_lisp_instruction(lisp_code)
if result['valid']:
    control_code = seq.run_lisp_instruction(
        node="order_handler",
        lisp_instruction=result,
        event_id="order.received",
        event_data={"order_id": 123}
    )
    print(f"Returned: {control_code}")
```

## Function Types

### `@void` Functions (Side Effects)
Functions that perform actions but don't return values.

```lisp
(@log "Processing started")
(@send_email "user@example.com" "Order confirmed")
```

### `?boolean` Functions (Predicates)
Functions that return True/False for conditionals.

```lisp
(if ?is_valid
    (@process)
    (@reject))
```

### `!control` Functions (Control Flow)
Functions that return control flow codes.

```lisp
(!handle_error)  ; Returns "CFL_HALT", "CFL_CONTINUE", etc.
```

## Control Flow Primitives

### `dispatch` - Event Routing

```lisp
(dispatch event_id
  ("payment.success" (@log "Payment received"))
  ("payment.failed" (@notify_admin))
  (["error.timeout" "error.network"] (@retry))
  (default 'CFL_HALT))
```

### `pipeline` - Sequential Execution

```lisp
(pipeline
  (@validate_input)
  (@process_data)
  (@save_results)
  'CFL_CONTINUE)
```

Steps execute sequentially. If any step returns non-`CFL_CONTINUE`, the pipeline stops.

### `if` - Conditional Branching

```lisp
(if ?check_inventory
    (pipeline (@reserve_items) (@process_order))
    (@notify_out_of_stock))
```

### `cond` - Multi-way Conditionals

```lisp
(cond
  (?is_premium (@apply_discount 20))
  (?is_member (@apply_discount 10))
  (else (@apply_discount 0)))
```

### `debug` - Transparent Debug Wrapper

```lisp
(debug "Checking inventory"
  (if ?check_inventory
      (@process)
      (@reject)))
```

## Macro System

Define reusable templates with parameter substitution.

### Defining Macros

```python
# Define a logging pipeline macro
seq.define_macro("log_and_run", ["message", "function"], """
(pipeline
  (@log $message)
  $function
  'CFL_CONTINUE)
""")

# Use the macro
code = """
(dispatch event_id
  ("process" (log_and_run "Starting process" !execute_task))
  (default 'CFL_HALT))
"""

result = seq.check_lisp_instruction_with_macros(code)
```

### Auto-Prepending Macros

Register macros to be automatically available:

```python
seq.define_macro("safe_call", ["func"], """
(pipeline 
  (@start_transaction)
  $func
  (@commit_transaction))
""")

seq.use_macro("safe_call")

# Now safe_call is automatically available
code = "(safe_call !process_order)"
result = seq.check_lisp_instruction_with_macros(code)
```

### Nested Macros

Macros can call other macros:

```python
seq.define_macro("log_msg", ["msg"], "(@log $msg)")
seq.define_macro("safe_log", ["msg", "func"], """
(pipeline
  (log_msg $msg)
  $func)
""")
```

## Mako Template Integration

Generate S-expressions using Python's Mako templating engine.

### Basic Template Rendering

```python
seq = LispSequencer(..., template_dirs=['./templates'])

template = """
% for event in events:
(dispatch event_id
  ("${event}" (@handle_${event}))
% endfor
  (default 'CFL_CONTINUE))
"""

code = seq.render_with_mako(template, events=["order", "payment", "shipment"])
result = seq.check_lisp_instruction_with_macros(code)
```

### Template Files

Create `handlers.mako`:
```mako
% for handler in handlers:
(dispatch event_id
  ("${handler['event']}"
   (pipeline
     (@log "${handler['name']}")
     (!${handler['function']})))
% endfor
  (default 'CFL_HALT))
```

Use it:
```python
handlers = [
    {"event": "order.new", "name": "New Order", "function": "process_order"},
    {"event": "payment.received", "name": "Payment", "function": "confirm_payment"}
]

code = seq.render_file('handlers.mako', handlers=handlers)
```

## Template Defs - The Power Feature

Load Mako `<%def>` blocks as callable Python methods. This is the cleanest way to generate S-expressions programmatically.

### Step 1: Create Template File

Create `cfl_helpers.mako`:
```mako
<%!
    import json
    
    def compress_json(data):
        """Replace quotes with --- for CFL string encoding."""
        return json.dumps(data).replace('"', '---')
%>

<%def name="send_event(event_name, event_data)">
(@SEND_EVENT "${event_name}" "${compress_json(event_data)}")\
</%def>

<%def name="log_and_call(message, function)">
(pipeline (@log "${message}") ${function} 'CFL_CONTINUE)\
</%def>
```

### Step 2: Load Template Defs

```python
seq = LispSequencer(..., template_dirs=['./templates'])

# Load the defs - creates Python methods
seq.load_template_defs('cfl_helpers.mako')
```

### Step 3: Use as Python Methods

```python
# Now call them directly!
event_call = seq.send_event("STATE_CHANGE", {"state": 1, "reason": "timeout"})
# Returns: (@SEND_EVENT "STATE_CHANGE" "{---state---: 1, ---reason---: ---timeout---}")

# Build complex S-expressions with Python
pipeline = (
    "(pipeline " +
    "  (@initialize) " +
    seq.send_event("READY", {"version": "1.0"}) +
    seq.log_and_call("Processing", "!execute") +
    "  'CFL_TERMINATE)"
)

result = seq.check_lisp_instruction_with_macros(pipeline)
```

### Complete Example

```python
# Template file: event_helpers.mako
<%!
    import json
%>

<%def name="notify(recipient, message)">
(pipeline (@send_email "${recipient}") (@log "${message}"))\
</%def>

<%def name="validated_call(check_func, action_func)">
(if ${check_func} ${action_func} 'CFL_HALT)\
</%def>

# Python code
seq = LispSequencer(..., template_dirs=['.'])
seq.load_template_defs('event_helpers.mako')

# Build using Python methods
order_handler = (
    "(pipeline " +
    seq.validated_call("?check_inventory", "!reserve_items") +
    " " +
    seq.notify("admin@company.com", "Order processed") +
    " 'CFL_CONTINUE)"
)

result = seq.check_lisp_instruction_with_macros(order_handler)
```

## API Reference

### LispSequencer Constructor

```python
LispSequencer(
    handle: Any,
    run_function: Callable,
    debug_function: Callable = None,
    control_codes: List[str] = None,
    template_dirs: List[str] = None
)
```

**Parameters:**
- `handle`: Context object passed to all function calls
- `run_function`: Function executor with signature:
  ```python
  (handle, func_type, func_name, node, event_id, event_data, params=[])
  ```
- `debug_function`: Optional debug message handler
- `control_codes`: List of valid control flow codes
- `template_dirs`: Directories to search for Mako templates

### Core Methods

#### `check_lisp_instruction(lisp_text: str) -> Dict`

Parse and validate S-expression. Returns:
```python
{
    'valid': bool,
    'errors': List[str],
    'text': str,
    'ast': Any,  # Parsed structure
    'functions': List[str]  # Required functions
}
```

#### `check_lisp_instruction_with_macros(lisp_text: str) -> Dict`

Expand macros, then parse and validate. Same return format as above, plus:
```python
{
    'expanded_text': str  # Text after macro expansion
}
```

#### `run_lisp_instruction(node, lisp_instruction, event_id, event_data) -> str`

Execute instruction. Returns control code string.

**Parameters:**
- `node`: Execution context
- `lisp_instruction`: String, AST, or result dict from `check_lisp_instruction`
- `event_id`: Event identifier
- `event_data`: Event payload

### Macro Methods

#### `define_macro(name: str, params: List[str], template: str) -> Dict`

Define a macro with parameters.

```python
seq.define_macro("safe_exec", ["func"], """
(pipeline (@begin_transaction) $func (@commit_transaction))
""")
```

#### `use_macro(*macro_names: str) -> Dict`

Register macros for auto-prepending.

```python
seq.use_macro("safe_exec", "log_action")
```

#### `clear_auto_macros()`

Clear all auto-prepend macros.

#### `list_macros() -> Dict[str, List[str]]`

List all defined macros and their parameters.

### Template Methods

#### `load_template_defs(template_filename: str) -> Dict[str, List[str]]`

Load Mako `<%def>` blocks as callable methods. Returns mapping of def names to parameters.

```python
loaded = seq.load_template_defs('helpers.mako')
# Creates methods: seq.send_event(...), seq.log_action(...), etc.
```

#### `render_with_mako(template_str: str, **context) -> str`

Render a Mako template string with context variables.

#### `render_file(filename: str, **context) -> str`

Render a Mako template file.

#### `export_macros_to_mako() -> Dict[str, str]`

Export defined macros in Mako-compatible format (converts `$param` to `${param}`).

## Best Practices

### 1. Pre-compile Instructions

```python
# At initialization
handler_ast = seq.check_lisp_instruction_with_macros(lisp_code)
assert handler_ast['valid'], handler_ast['errors']

# Store the result
self.order_handler = handler_ast

# At runtime - use pre-compiled AST
def handle_order(self, order_data):
    return seq.run_lisp_instruction(
        self.node,
        self.order_handler,  # Pre-compiled
        "order.received",
        order_data
    )
```

### 2. Use Template Defs for Code Generation

Instead of string concatenation:
```python
# ❌ Hard to maintain
code = '(@SEND "' + event + '" "' + json.dumps(data) + '")'
```

Use template defs:
```python
# ✓ Clean and type-safe
code = seq.send_event(event, data)
```

### 3. Organize Templates

```
project/
├── templates/
│   ├── events.mako        # Event handling helpers
│   ├── workflows.mako     # Workflow templates
│   └── validation.mako    # Validation helpers
└── main.py
```

```python
seq = LispSequencer(..., template_dirs=['templates'])
seq.load_template_defs('events.mako')
seq.load_template_defs('workflows.mako')
seq.load_template_defs('validation.mako')
```

### 4. Separate Logic from Data

Use Mako for structure, data for content:

```mako
<%def name="dispatch_handler(events)">
(dispatch event_id
% for event in events:
  ("${event['pattern']}" ${event['handler']})
% endfor
  (default 'CFL_HALT))
</%def>
```

```python
events = [
    {"pattern": "order.*", "handler": "!handle_order"},
    {"pattern": "payment.*", "handler": "!handle_payment"}
]
code = seq.dispatch_handler(events)
```

### 5. Validate Early

```python
# At configuration time
result = seq.check_lisp_instruction_with_macros(config['handler'])
if not result['valid']:
    raise ValueError(f"Invalid handler: {result['errors']}")

# Check required functions exist
for func in result['functions']:
    if func not in available_functions:
        raise ValueError(f"Missing function: {func}")
```

## Integration with ChainTree

Example usage in a ChainTree-based system:

```python
from lisp_sequencer import LispSequencer
from chain_tree import ChainTreeMaster

# Initialize with template directory
ct = ChainTreeMaster.start_build(
    yaml_file="config.yaml",
    DataStructures=DataStructures,
    LispSequencer=LispSequencer,
    template_dirs=["chain_tree_templates"]
)

# Load template helpers
ct.lisp_sequencer.load_template_defs('basic_templates.mako')

# Build event handlers using template methods
state_change = (
    "(pipeline " +
    "  (@CFL_KILL_CHILDREN) " +
    ct.lisp_sequencer.send_current_node_event("CFL_CHANGE_STATE", {"state": 1}) +
    "  (fork_join 0) " +
    "  'CFL_FUNCTION_TERMINATE)"
)

result = ct.lisp_sequencer.check_lisp_instruction_with_macros(state_change)
```

## Error Handling

```python
# Check validation errors
result = seq.check_lisp_instruction_with_macros(code)
if not result['valid']:
    for error in result['errors']:
        print(f"Error: {error}")
    return

# Handle execution errors
try:
    control_code = seq.run_lisp_instruction(node, result, event_id, event_data)
except ValueError as e:
    print(f"Execution error: {e}")
```

## Advanced Features

### Control Code Customization

```python
CUSTOM_CODES = [
    "CFL_CONTINUE",
    "CFL_HALT", 
    "CFL_TERMINATE",
    "CFL_RETRY",
    "CFL_ESCALATE",
    "CFL_CHECKPOINT"
]

seq = LispSequencer(..., control_codes=CUSTOM_CODES)
```

### Logical Operators in Predicates

```lisp
(if (and ?is_valid ?is_premium)
    (@apply_discount)
    (@standard_price))

(if (or ?is_member ?has_coupon)
    (@apply_discount)
    'CFL_CONTINUE)

(if (not ?is_blacklisted)
    (@process_order)
    (@reject_order))
```

### Complex Dispatch Patterns

```lisp
(dispatch event_id
  ; Single pattern
  ("order.new" (@handle_new))
  
  ; Multiple patterns
  (["order.update" "order.modify"] (@handle_update))
  
  ; Wildcard default
  (default (@log_unknown)))
```

## Performance Considerations

1. **Pre-compile instructions**: Parse once at initialization, execute many times
2. **AST caching**: Store validated ASTs rather than raw text
3. **Function optimization**: Keep `run_function` fast - it's called for every function
4. **Macro complexity**: Deep macro nesting can slow compilation (limit: 100 iterations)

## Troubleshooting

### "Template not found" Error

```python
# Wrong - includes directory in filename
seq.load_template_defs('templates/helpers.mako')  # ❌

# Correct - directory already in template_dirs
seq = LispSequencer(..., template_dirs=['templates'])
seq.load_template_defs('helpers.mako')  # ✓
```

### "AttributeError: object has no attribute 'method_name'"

Make sure you called `load_template_defs()`:

```python
seq.load_template_defs('helpers.mako')  # Must call this first
seq.send_event("test", {})  # Now this works
```

### Macro Expansion Errors

Enable debugging:
```python
result = seq.expand_macros(code)
if not result['valid']:
    print(f"Original: {result['original_text']}")
    print(f"Expanded: {result['expanded_text']}")
    print(f"Errors: {result['errors']}")
```

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]

## Support

[Your Support Information Here]