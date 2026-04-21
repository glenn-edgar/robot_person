# LispSequencer - Quick Reference

## Initialization

```python
from lisp_sequencer import LispSequencer

# Minimal setup
sequencer = LispSequencer(
    handle=my_context_object,
    run_function=my_executor
)

# Full setup
sequencer = LispSequencer(
    handle=my_context_object,
    run_function=my_executor,
    debug_function=my_debugger,
    control_codes=["STOP", "PAUSE"],
    user_macro_file='templates.mako',
    enable_mako=True,
    enabled_macros={'fork_join', 'send_event'}
)
```

## Execution

```python
# Direct execution
result = sequencer.run(instruction_text)

# With Mako disabled
result = sequencer.run(instruction_text, use_mako=False)

# With context variables
result = sequencer.run(
    instruction_text,
    mako_context={'var': 'value'}
)

# Check then run
check = sequencer.check_lisp_instruction(instruction_text)
if check['valid']:
    result = sequencer.run()
```

## Built-in Templates

```python
# fork_join(branch_id)
"<%fork_join(0)%>"
# Expands to: (@CFL_FORK 0) (!CFL_JOIN 0)

# send_event(event_name, data_var)
"<%send_event('login', 'user_data')%>"
# Expands to: (@SEND_EVENT "login" "json.dumps(user_data)")

# parallel(*branch_ids)
"<%parallel(0, 1, 2)%>"
# Expands to: (@CFL_FORK 0) (@CFL_FORK 1) (@CFL_FORK 2)
#             (!CFL_JOIN 0) (!CFL_JOIN 1) (!CFL_JOIN 2)

# conditional(condition, true_action, false_action='')
"<%conditional('valid', '(@PROCESS)', '(@ERROR)')%>"
```

## Template Management

```python
# Load from file (replace)
sequencer.set_user_macros_from_file('templates.mako')

# Load from file (append)
sequencer.add_user_macros_from_file('more.mako')

# Load from string
sequencer.set_user_macros_from_string("""
<%def name="my_macro(x)">
(@FUNC ${x})
</%def>
""")

# Load temporarily for one call
sequencer.run(text, additional_macro_files='temp.mako')

# Clear all user macros
sequencer.clear_user_macros()
```

## Macro Control

```python
# View macros
sequencer.get_available_macros()  # All built-in macros
sequencer.get_enabled_macros()    # Currently enabled
sequencer.get_loaded_macro_files()  # Loaded files

# Enable/disable
sequencer.enable_macro('parallel')
sequencer.disable_macro('conditional')
sequencer.set_mako_default(True)  # Enable by default
```

## Creating Templates

**File: my_templates.mako**
```mako
<%def name="retry_block(branch_id, max_retries)">
(@CFL_FORK ${branch_id})
(@SET_RETRY ${max_retries})
(!CFL_JOIN ${branch_id})
</%def>

<%def name="batch_process(*items)">
% for i, item in enumerate(items):
(@PROCESS ${i} "${item}")
% endfor
</%def>
```

**Usage:**
```python
sequencer.set_user_macros_from_file('my_templates.mako')

instruction = """
(pipeline
    <%retry_block(0, 5)%>
    <%batch_process('a', 'b', 'c')%>
    'CFL_FUNCTION_TERMINATE)
"""
result = sequencer.run(instruction)
```

## Context Variables

```python
instruction = """
(pipeline
    (@LOG "User: ${user_name}")
    % for id in task_ids:
    (@TASK ${id})
    % endfor
    % if enable_backup:
    (@BACKUP)
    % endif
    'CFL_FUNCTION_TERMINATE)
"""

context = {
    'user_name': 'John',
    'task_ids': [1, 2, 3],
    'enable_backup': True
}

result = sequencer.run(instruction, mako_context=context)
```

## Your Run Function

```python
def my_run_function(handle, ast, *args, **kwargs):
    """
    Args:
        handle: Your context object (self.handle from sequencer)
        ast: Parsed Abstract Syntax Tree
        *args, **kwargs: Additional arguments from run() call
    
    Returns:
        Whatever you want
    """
    # Access handle data
    session_id = handle['session_id']
    
    # Process AST
    def process(node):
        if isinstance(node, list):
            operator = node[0]
            # Your logic based on operator
            if operator == '@CFL_FORK':
                branch_id = node[1]
                # Handle fork...
        # ...
    
    process(ast)
    return {"status": "success"}
```

## Your Debug Function

```python
def my_debug_function(handle, message):
    """
    Optional debug logging.
    
    Args:
        handle: Your context object
        message: Debug message from sequencer
    """
    print(f"[{handle['session']}] {message}")
```

## Common Patterns

### Pattern 1: Retry Logic
```python
instruction = """
(pipeline
    <%retry_block(0, 3)%>
    (@DO_WORK)
    'CFL_FUNCTION_TERMINATE)
"""
```

### Pattern 2: Parallel Processing
```python
instruction = """
(pipeline
    <%parallel(0, 1, 2, 3)%>
    'CFL_FUNCTION_TERMINATE)
"""
```

### Pattern 3: Conditional Workflow
```python
instruction = """
(pipeline
    % if ${condition}:
    (@PATH_A)
    % else:
    (@PATH_B)
    % endif
    'CFL_FUNCTION_TERMINATE)
"""
```

### Pattern 4: Dynamic Branches
```python
instruction = """
(pipeline
    % for i in range(${num_workers}):
    <%fork_join(${i})%>
    % endfor
    'CFL_FUNCTION_TERMINATE)
"""
```

### Pattern 5: Error Handling
```python
instruction = """
(pipeline
    (@TRY_OPERATION)
    (?CHECK_ERROR)
    <%error_handler(0, "Operation failed")%>
    'CFL_FUNCTION_TERMINATE)
"""
```

## Mako Template Syntax

```mako
# Variables
${variable_name}
${expression + 123}
${f'formatted {value}'}

# Conditionals
% if condition:
    ...
% elif other:
    ...
% else:
    ...
% endif

# Loops
% for item in items:
    ${item}
% endfor

% for i in range(10):
    ${i}
% endfor

# Loop variables
${loop.index}    # 0-based index
${loop.first}    # Is first iteration
${loop.last}     # Is last iteration

# Comments
<%doc>
This is a comment
</%doc>

# Macro definition
<%def name="my_macro(param1, param2='default')">
    content with ${param1} and ${param2}
</%def>
```

## Validation Result

```python
result = sequencer.check_lisp_instruction(text)
# Returns:
{
    'valid': True/False,
    'errors': ['error1', 'error2'],
    'text': 'processed text',
    'original_text': 'input text',
    'ast': parsed_structure,
    'functions': ['@FUNC1', '!FUNC2'],
    'mako_used': True/False
}
```

## Reserved Keywords

```python
# These are valid control flow keywords:
- CFL_KILL_CHILDREN
- CFL_FORK
- CFL_JOIN
- CFL_WAIT
- CFL_TERMINATE
- CFL_FUNCTION_TERMINATE
- pipeline
```

## Function Prefixes

```python
@ - Standard function call
! - Join/synchronization operation
? - Query/check operation
' - Literal/symbol
```

## Tips

1. **Test templates** with `get_processed_text()` first
2. **Use debug_function** to track execution
3. **Validate complex instructions** before production use
4. **Keep templates modular** for reusability
5. **Use context variables** for configuration
6. **Handle exceptions** in your run_function
7. **Enable only needed macros** for clarity

## Complete Minimal Example

```python
# 1. Define executor
def run(handle, ast):
    print(f"Handle: {handle}")
    print(f"AST: {ast}")
    return "done"

# 2. Create sequencer
seq = LispSequencer(
    handle={"id": 123},
    run_function=run
)

# 3. Execute
result = seq.run("(pipeline (@WORK) 'CFL_FUNCTION_TERMINATE)")
print(result)  # "done"
```


