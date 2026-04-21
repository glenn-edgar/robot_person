# LispSequencer Quick Reference

## S-Expression Syntax and Built-in Functions

### Function Types

LispSequencer uses three function prefixes:
- `@function` - Void functions (side effects, returns nothing)
- `?function` - Boolean functions (returns true/false)
- `!function` - Control functions (returns control codes like `CFL_CONTINUE`)

### Built-in Control Flow Primitives

#### `pipeline` - Sequential Execution

Execute steps in order. If any step returns non-`CFL_CONTINUE`, the pipeline stops.

```lisp
(pipeline
  (@initialize)
  (@process_data)
  (@cleanup)
  'CFL_CONTINUE)
```

#### Nested Pipelines

Pipelines can be nested to create complex workflows:

```lisp
(pipeline
  (@setup)
  (pipeline
    (@validate_input)
    (@transform_data)
    (@save_temp))
  (if ?check_results
      (pipeline
        (@finalize)
        (@notify_success))
      (@rollback))
  'CFL_CONTINUE)
```

#### `dispatch` - Event Routing

Route based on event patterns:

```lisp
(dispatch event_id
  ("order.new" (@handle_new_order))
  (["order.update" "order.modify"] (@handle_update))
  (default 'CFL_HALT))
```

#### `if` - Conditional

```lisp
(if ?is_valid
    (@process)
    (@reject))
```

#### `cond` - Multi-way Conditional

```lisp
(cond
  (?is_premium (@discount_20))
  (?is_member (@discount_10))
  (else 'CFL_CONTINUE))
```

### Control Codes

Use single-quote to return control codes:

```lisp
'CFL_CONTINUE
'CFL_HALT
'CFL_TERMINATE
```

---

## Defining and Using Macros

Macros provide text substitution with parameters using `$param` syntax.

### Define a Macro

```python
seq.define_macro("log_and_run", ["message", "function"], """
(pipeline
  (@log $message)
  $function
  'CFL_CONTINUE)
""")
```

### Use the Macro

```lisp
(dispatch event_id
  ("process" (log_and_run "Starting task" !execute_task))
  (default 'CFL_HALT))
```

**Important:** Use `check_lisp_instruction_with_macros()` instead of `check_lisp_instruction()` to enable macro expansion:

```python
result = seq.check_lisp_instruction_with_macros(code)
```

### Auto-Using Macros

Register macros to be automatically available in all instructions:

```python
seq.define_macro("safe_call", ["func"], """
(pipeline (@begin_transaction) $func (@commit_transaction))
""")

seq.use_macro("safe_call")

# Now safe_call is automatically available without explicit definition
code = "(safe_call !process_order)"
result = seq.check_lisp_instruction_with_macros(code)
```

### Macro Parameters

Macros can have multiple parameters and can be nested:

```python
# Define helper macros
seq.define_macro("log_msg", ["msg"], "(@log $msg)")

# Use in another macro
seq.define_macro("traced_call", ["msg", "func"], """
(pipeline
  (log_msg $msg)
  $func
  (log_msg "Complete"))
""")
```

---

## Template Defs - Callable Python Methods

Template defs convert Mako `<%def>` blocks into callable Python methods on the LispSequencer instance.

### Step 1: Create Template File

Create `basic_templates.mako`:

```mako
<%!
    import json
    
    def compress_json(data):
        return json.dumps(data).replace('"', '---')
%>

<%def name="send_event(event_name, event_data)">
(@SEND_EVENT "${event_name}" "${compress_json(event_data)}")\
</%def>

<%def name="log_action(message)">
(@log "${message}")\
</%def>
```

### Step 2: Load Template Defs

**Critical:** You must load template defs before using them:

```python
seq = LispSequencer(..., template_dirs=['templates'])

# Load the template - this creates Python methods
seq.load_template_defs('basic_templates.mako')
```

**Important:** Use **only the filename**, not the directory path:

```python
# ✓ Correct
seq.load_template_defs('basic_templates.mako')

# ✗ Wrong - will fail with "Template not found"
seq.load_template_defs('templates/basic_templates.mako')
```

The directory is already specified in `template_dirs`, so only pass the filename.

### Step 3: Use as Python Methods

Once loaded, call the defs as Python methods:

```python
# Generate S-expression fragments
event_call = seq.send_event("STATE_CHANGE", {"state": 1})
# Returns: (@SEND_EVENT "STATE_CHANGE" "{---state---: 1}")

log_call = seq.log_action("Processing started")
# Returns: (@log "Processing started")

# Build complete S-expressions with Python string concatenation
pipeline = (
    "(pipeline " +
    seq.log_action("Starting") +
    " (@initialize) " +
    seq.send_event("READY", {"version": "1.0"}) +
    " 'CFL_CONTINUE)"
)

result = seq.check_lisp_instruction_with_macros(pipeline)
```

### Complete Example

```python
# Setup
seq = LispSequencer(
    handle="context",
    run_function=my_run_function,
    control_codes=["CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE"],
    template_dirs=['chain_tree_templates']
)

# Load templates - MUST DO THIS FIRST
seq.load_template_defs('basic_templates.mako')

# Now use template methods to build S-expressions
order_handler = (
    "(pipeline " +
    "  (@validate_order) " +
    seq.send_event("ORDER_VALIDATED", {"order_id": 123}) +
    "  (!process_payment) " +
    seq.log_action("Order complete") +
    "  'CFL_TERMINATE)"
)

# Check and execute
result = seq.check_lisp_instruction_with_macros(order_handler)
if result['valid']:
    control_code = seq.run_lisp_instruction(
        node="order_node",
        lisp_instruction=result,
        event_id="order.new",
        event_data={"order_id": 123}
    )
```

### Why Template Defs?

Template defs provide a clean Python API for generating S-expressions:

**Without template defs (string manipulation):**
```python
# ❌ Error-prone and hard to maintain
event = f'(@SEND_EVENT "{name}" "{json.dumps(data).replace(chr(34), "---")}")'
```

**With template defs:**
```python
# ✓ Clean, type-safe, and maintainable
event = seq.send_event(name, data)
```