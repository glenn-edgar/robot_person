# LispSequencer - Complete Documentation

## Overview

`LispSequencer` is a powerful class for parsing, validating, and executing Lisp-style instruction sequences with optional Mako template preprocessing. It supports handle-based execution, allowing you to pass context through your execution pipeline.

## Key Features

1. **Handle-based Execution**: Pass context through `self.handle` to your run function
2. **Mako Template Preprocessing**: Generate instructions dynamically using templates
3. **Built-in Templates**: Pre-defined macros for common patterns
4. **User-defined Templates**: Load custom templates from files or strings
5. **Context Variables**: Pass runtime data to templates
6. **Dynamic Macro Control**: Enable/disable specific templates
7. **Validation**: Check instruction validity before execution
8. **Debug Logging**: Optional debug output through custom function

## Installation

```python
from lisp_sequencer import LispSequencer
```

## Basic Usage

### 1. Define Your Execution Functions

```python
def my_run_function(handle, ast, *args, **kwargs):
    """
    Process the parsed AST using your handle context.
    
    Args:
        handle: Your context object (self.handle)
        ast: Parsed Abstract Syntax Tree
        *args, **kwargs: Additional arguments
    """
    print(f"Processing with handle: {handle}")
    # Your execution logic here
    return {"status": "success"}

def my_debug_function(handle, message):
    """Optional debug logging."""
    print(f"[DEBUG] {message}")
```

### 2. Create Your Handle and Initialize

```python
# Your context handle - can be any object
my_handle = {
    "session_id": "abc123",
    "user_id": "user_456",
    "config": {...}
}

# Initialize the sequencer
sequencer = LispSequencer(
    handle=my_handle,
    run_function=my_run_function,
    debug_function=my_debug_function,  # Optional
    control_codes=["STOP", "PAUSE"],    # Optional
    enable_mako=True                    # Enable templates by default
)
```

### 3. Execute Instructions

```python
# Simple execution without templates
instruction = "(pipeline (@CFL_FORK 0) (@PROCESS) (!CFL_JOIN 0) 'CFL_FUNCTION_TERMINATE)"
result = sequencer.run(instruction, use_mako=False)

# Execution with templates
templated = """
(pipeline
    <%fork_join(0)%>
    (@DO_WORK)
    'CFL_FUNCTION_TERMINATE)
"""
result = sequencer.run(templated)
```

## Built-in Templates

The LispSequencer comes with 4 built-in templates:

### 1. `fork_join(branch_id)`
Creates a fork and join pair.

```python
instruction = """
(pipeline
    <%fork_join(0)%>
    <%fork_join(1)%>
    'CFL_FUNCTION_TERMINATE)
"""
```

**Expands to:**
```lisp
(pipeline
    (@CFL_FORK 0) (!CFL_JOIN 0)
    (@CFL_FORK 1) (!CFL_JOIN 1)
    'CFL_FUNCTION_TERMINATE)
```

### 2. `send_event(event_name, data_var)`
Sends an event with JSON-encoded data (with proper quote escaping).

```python
instruction = """
(pipeline
    <%send_event("user_login", "user_data")%>
    'CFL_FUNCTION_TERMINATE)
"""
```

**Expands to:**
```lisp
(pipeline
    (@SEND_EVENT "user_login" "json.dumps(user_data)")
    'CFL_FUNCTION_TERMINATE)
```

### 3. `parallel(*branch_ids)`
Creates multiple parallel branches.

```python
instruction = """
(pipeline
    <%parallel(0, 1, 2, 3)%>
    'CFL_FUNCTION_TERMINATE)
"""
```

**Expands to:**
```lisp
(pipeline
    (@CFL_FORK 0) (@CFL_FORK 1) (@CFL_FORK 2) (@CFL_FORK 3)
    (!CFL_JOIN 0) (!CFL_JOIN 1) (!CFL_JOIN 2) (!CFL_JOIN 3)
    'CFL_FUNCTION_TERMINATE)
```

### 4. `conditional(condition, true_action, false_action='')`
Creates a conditional branch.

```python
instruction = """
(pipeline
    <%conditional("is_valid", "(@PROCESS)", "(@LOG_ERROR)")%>
    'CFL_FUNCTION_TERMINATE)
"""
```

## User-Defined Templates

### Creating Template Files

Create a `.mako` file with your template definitions:

**workflow_templates.mako:**
```mako
<%doc>
My custom workflow templates
</%doc>

<%def name="retry_block(branch_id, max_retries)">
(@CFL_FORK ${branch_id})
(@SET_RETRY_COUNT ${max_retries})
(@LOG "Starting retry block ${branch_id}")
(!CFL_JOIN ${branch_id})
</%def>

<%def name="timeout_block(branch_id, timeout_seconds)">
(@CFL_FORK ${branch_id})
(!CFL_WAIT ${timeout_seconds})
(?TIMEOUT_CHECK ${branch_id})
(@CFL_TERMINATE ${branch_id})
</%def>
```

### Loading Templates

**At initialization:**
```python
sequencer = LispSequencer(
    handle=my_handle,
    run_function=my_run_function,
    user_macro_file='workflow_templates.mako'  # Single file
    # OR
    user_macro_file=['file1.mako', 'file2.mako']  # Multiple files
)
```

**After initialization (replaces existing):**
```python
sequencer.set_user_macros_from_file('workflow_templates.mako')
```

**After initialization (appends):**
```python
sequencer.add_user_macros_from_file('more_templates.mako')
```

**From string:**
```python
template_string = """
<%def name="my_macro(param)">
(@SOME_FUNCTION "${param}")
</%def>
"""
sequencer.set_user_macros_from_string(template_string)
```

**At call time (temporary):**
```python
result = sequencer.run(
    instruction,
    additional_macro_files='temp_templates.mako'
)
```

### Using Your Templates

```python
instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%retry_block(0, 3)%>
    <%timeout_block(1, 30)%>
    'CFL_FUNCTION_TERMINATE)
"""

result = sequencer.run(instruction)
```

## Context Variables

Pass runtime data to your templates using `mako_context`:

```python
instruction = """
(pipeline
    <%retry_block(${branch_id}, ${retry_count})%>
    % for worker in worker_ids:
    (@PROCESS_WORKER ${worker})
    % endfor
    <%timeout_block(99, ${timeout})%>
    'CFL_FUNCTION_TERMINATE)
"""

context = {
    'branch_id': 5,
    'retry_count': 10,
    'worker_ids': [1, 2, 3, 4, 5],
    'timeout': 120
}

result = sequencer.run(instruction, mako_context=context)
```

### Advanced Mako Features

You can use all Mako features in your templates:

**Conditionals:**
```python
instruction = """
(pipeline
    % if enable_logging:
    (@LOG "Starting process")
    % endif
    (@DO_WORK)
    'CFL_FUNCTION_TERMINATE)
"""
```

**Loops:**
```python
instruction = """
(pipeline
    % for i in range(5):
    (@CFL_FORK ${i})
    % endfor
    'CFL_FUNCTION_TERMINATE)
"""
```

**Expressions:**
```python
instruction = """
(pipeline
    (@SET_VALUE ${10 * 2})
    (@LOG "Result: ${f'value is {result}'}") 
    'CFL_FUNCTION_TERMINATE)
"""
```

## Dynamic Macro Control

### Check Available and Enabled Macros

```python
# Get all available built-in macros
available = sequencer.get_available_macros()
# Returns: ['conditional', 'fork_join', 'parallel', 'send_event']

# Get currently enabled macros
enabled = sequencer.get_enabled_macros()
# Returns: ['conditional', 'fork_join', 'parallel', 'send_event']
```

### Enable/Disable Specific Macros

```python
# Disable a macro
sequencer.disable_macro('parallel')
sequencer.disable_macro('conditional')

# Enable it again
sequencer.enable_macro('parallel')
```

### Enable Only Specific Macros at Initialization

```python
sequencer = LispSequencer(
    handle=my_handle,
    run_function=my_run_function,
    enabled_macros={'fork_join', 'send_event'}  # Only these two
)
```

## Validation

### Check Before Running

```python
# Check instruction validity
result = sequencer.check_lisp_instruction(instruction)

if result['valid']:
    print(f"Functions used: {result['functions']}")
    print(f"Processed text: {result['text']}")
    
    # Run the pre-checked instruction
    execution_result = sequencer.run()
else:
    print(f"Errors: {result['errors']}")
```

### Result Dictionary

The `check_lisp_instruction` method returns:
```python
{
    'valid': bool,              # Whether instruction is valid
    'errors': list,             # List of error messages
    'text': str,                # Processed text (after Mako)
    'original_text': str,       # Original input text
    'ast': parsed_structure,    # Abstract Syntax Tree
    'functions': list,          # Function names used
    'mako_used': bool          # Whether Mako was used
}
```

## Execution Methods

### Method 1: Direct Execution

```python
result = sequencer.run(instruction_text)
```

### Method 2: Check Then Run

```python
check_result = sequencer.check_lisp_instruction(instruction_text)
if check_result['valid']:
    result = sequencer.run()  # Uses checked instruction
```

### Method 3: Get Processed Text Only

```python
processed = sequencer.get_processed_text(
    instruction_text,
    use_mako=True,
    mako_context={'var': 'value'}
)
```

## Complete Example

```python
from lisp_sequencer import LispSequencer

# 1. Define execution function
def my_executor(handle, ast, *args, **kwargs):
    print(f"Session: {handle['session_id']}")
    print(f"Processing: {ast}")
    return {"status": "done"}

# 2. Create handle
my_handle = {"session_id": "abc123", "user": "john"}

# 3. Initialize sequencer
sequencer = LispSequencer(
    handle=my_handle,
    run_function=my_executor,
    user_macro_file='my_templates.mako'
)

# 4. Execute with templates and context
instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%retry_block(${branch}, ${retries})%>
    % for worker in workers:
    (@PROCESS ${worker})
    % endfor
    <%send_event("complete", "result")%>
    'CFL_FUNCTION_TERMINATE)
"""

context = {
    'branch': 0,
    'retries': 5,
    'workers': [1, 2, 3]
}

result = sequencer.run(instruction, mako_context=context)
print(result)
```

## API Reference

### Initialization Parameters

- **handle** (required): Context object passed to run_function
- **run_function** (required): Callable(handle, ast, *args, **kwargs)
- **debug_function** (optional): Callable(handle, message)
- **control_codes** (optional): List of control code strings
- **user_macro_file** (optional): Path(s) to macro files
- **enable_mako** (optional): Enable Mako by default (default: True)
- **enabled_macros** (optional): Set of macro names to enable

### Key Methods

#### Execution
- `run(lisp_text=None, use_mako=None, mako_context=None, additional_macro_files=None, *args, **kwargs)`
- `check_lisp_instruction(lisp_text, use_mako=None, mako_context=None, additional_macro_files=None)`
- `get_processed_text(lisp_text, use_mako=None, mako_context=None, additional_macro_files=None)`

#### Template Management
- `set_user_macros_from_file(filepath)` - Replace macros
- `add_user_macros_from_file(filepath)` - Append macros
- `set_user_macros_from_string(macro_string)` - Replace with string
- `add_user_macros_from_string(macro_string)` - Append string
- `clear_user_macros()` - Clear all user macros

#### Macro Control
- `enable_macro(macro_name)` - Enable a built-in macro
- `disable_macro(macro_name)` - Disable a built-in macro
- `get_enabled_macros()` - List enabled macros
- `get_available_macros()` - List all available macros
- `get_loaded_macro_files()` - List loaded template files
- `set_mako_default(enabled)` - Set default Mako usage

## Best Practices

1. **Always validate complex instructions** before execution
2. **Use debug_function** to track execution flow
3. **Keep templates in separate .mako files** for reusability
4. **Use context variables** for runtime configuration
5. **Enable only needed macros** for better performance
6. **Store handle data** that your run_function needs
7. **Handle exceptions** in your run_function gracefully

## Error Handling

The sequencer validates:
- Lisp syntax (balanced parentheses)
- Function name format
- Expression structure

Errors are returned in the `errors` list of the result dictionary.

## License

MIT License - Use freely in your projects.
