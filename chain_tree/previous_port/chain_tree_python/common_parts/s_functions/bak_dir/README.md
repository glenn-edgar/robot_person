# LispSequencer

A Lisp-based control flow sequencer for event-driven workflows with type-safe function markers, compile-time validation, and macro expansion.

## Overview

LispSequencer provides a minimal yet powerful S-expression based language for defining event processing workflows. It combines the simplicity of Lisp with type safety enforced at parse time, making it ideal for reliable event-driven systems.

### Key Features

- **Type-safe function markers**: Three function types with compile-time validation
- **Macro system**: Text-based template expansion for reusable patterns
- **Control flow primitives**: dispatch, pipeline, if, cond, debug
- **Pre-compilation**: Parse once, execute many times with tokenized AST
- **CFL_ control codes**: Compatible with existing control flow engines
- **Debug support**: Built-in transparent debug message primitive
- **Parameter support**: Functions accept strings and numbers (up to 10 parameters)
- **YAML/JSON compatible**: ASTs and macros can be serialized and deserialized
- **Simplified API**: Core methods (check and run) with optional macro support

## Installation

```python
# Copy lisp_sequencer_with_macros.py to your project
from lisp_sequencer_with_macros import LispSequencer
```

## Quick Start

```python
from lisp_sequencer_with_macros import LispSequencer

# Define run_function callback
def run_fn(handle, func_type, func_name, node, event_id, event_data, params=[]):
    if func_type == '@':
        print(f"Side effect: {func_name}")
    elif func_type == '?':
        return True  # Boolean result
    elif func_type == '!':
        return "CFL_CONTINUE"  # Control code

# Create sequencer
CONTROL_CODES = ["CFL_CONTINUE", "CFL_HALT", "CFL_RESET", "CFL_DISABLE"]
seq = LispSequencer("my-app", run_fn, control_codes=CONTROL_CODES)

# Define workflow
workflow = """
(dispatch event_id
  ("user.created"
   (pipeline @log_start !create_user @notify 'CFL_CONTINUE))
  (default 'CFL_DISABLE))
"""

# Compile once
result = seq.check_lisp_instruction(workflow)

# Execute many times
code = seq.run_lisp_instruction("node1", result, "user.created", {})
print(f"Result: {code}")
```

## Quick Start with Macros

```python
# Define reusable macro templates
seq.define_macro("log_pipeline", ["msg", "func"], """
(pipeline 
  (@log $msg)
  $func
  'CFL_CONTINUE)
""")

# Use macro in workflow
workflow = """
(dispatch event_id
  ("user.created"
   (log_pipeline "Creating user" !create_user))
  (default 'CFL_DISABLE))
"""

# Expand macros and compile
result = seq.check_lisp_instruction_with_macros(workflow)

# Execute (same as before)
code = seq.run_lisp_instruction("node1", result, "user.created", {})
```

## Language Specification

### Function Markers

Functions are prefixed with special markers that define their type and return behavior:

| Marker | Type | Returns | Usage |
|--------|------|---------|-------|
| `@` | Void | Nothing (side effects only) | `@log_start`, `@send_email` |
| `?` | Boolean | `True` or `False` | `?validate_schema`, `?is_premium` |
| `!` | Control | CFL_* control code | `!process_payment`, `!create_user` |

**Function Syntax:**
```lisp
; No parameters
@log_start
?is_valid
!process_data

; With parameters (strings and numbers)
(@log "Starting process" 1)
(?check_threshold 100 "USD")
(!process_payment "stripe" 99.99)
```

**Function Naming Rules:**
- Must be valid Python identifiers
- Start with letter (a-z, A-Z) or underscore (_)
- Can contain letters, digits, underscores
- Cannot start with digit
- Cannot be Python keywords (e.g., `class`, `if`, `for`)

**Valid Examples:**
```lisp
@log_start  ?is_valid  !process_0  @_helper  ?check2fa
```

**Invalid Examples:**
```lisp
@123invalid  ; Cannot start with digit
!class       ; Python keyword
@my-func     ; Hyphens not allowed
```

### Control Codes

Control codes are passed in as a parameter.
The only control code that is required is 'CFL_CONTINUE'.
When evaluating a user supplied function !function, 
any value other than CFL_CONTINUE terminates the pipeline.

All control codes use the `CFL_` prefix.

### Parameters

Functions support up to 10 parameters:
- **Strings**: `"hello world"`
- **Integers**: `123`, `-45`
- **Floats**: `99.99`, `-3.14`, `0.05`

```lisp
(@log "Order processed" 12345 99.99)
(?check_balance 1000 "USD")
(!send_notification "user@example.com" "Welcome" 1)
```

## Core Primitives

### 1. dispatch - Event Routing

Routes events to handlers based on pattern matching.

**Syntax:**
```lisp
(dispatch event_id
  (pattern expression)
  (pattern expression)
  ...
  (default expression))
```

**Patterns:**
- Single event: `"event-name"`
- Multiple events: `["event1" "event2" "event3"]`
- Default: `default` (required)

**Example:**
```lisp
(dispatch event_id
  ("user.created"
   (pipeline @log_start !create_user 'CFL_CONTINUE))
  
  (["user.updated" "user.modified"]
   (pipeline @log_update !update_user 'CFL_CONTINUE))
  
  (["payment.success" "payment.completed"]
   (pipeline !process_payment @notify 'CFL_CONTINUE))
  
  (default 'CFL_DISABLE))
```

### 2. pipeline - Sequential Execution

Executes functions in sequence with control flow bubbling.

**Syntax:**
```lisp
(pipeline step1 step2 ... stepN control-code)
```

**Steps:**
- `@void-fn` - Always continues to next step
- `!control-fn` - If returns `CFL_CONTINUE`, continues; otherwise stops and returns that code

**Short-Circuit Behavior:**
```lisp
(pipeline 
  @validate_input      ; Always continues
  !process_data        ; If returns CFL_HALT → stops here
  @send_notification   ; Only runs if !process_data returned CFL_CONTINUE
  'CFL_CONTINUE)       ; Final code if all steps complete
```

**Example:**
```lisp
(pipeline 
  (@log "Starting" 1)
  !validate 
  !process 
  (@notify "admin@company.com")
  'CFL_CONTINUE)
```

### 3. if - Conditional Branch

Binary conditional execution.

**Syntax:**
```lisp
(if predicate then-expression else-expression)
```

**Example:**
```lisp
(if ?is_premium
    (pipeline !process_priority 'CFL_CONTINUE)
    (pipeline !process_standard 'CFL_CONTINUE))
```

**With boolean combinators:**
```lisp
(if (and ?is_authenticated (not ?is_suspended))
    (pipeline @grant_access 'CFL_CONTINUE)
    'CFL_HALT)
```

### 4. cond - Multi-way Conditional

Multi-branch conditional (like switch/case).

**Syntax:**
```lisp
(cond
  (predicate1 expression1)
  (predicate2 expression2)
  ...
  (else expressionN))
```

**Requirements:**
- At least one predicate case
- `else` clause is required
- First match wins (evaluated top to bottom)

**Example:**
```lisp
(cond
  ((and ?validate_schema ?check_balance)
   (pipeline @log_valid !process_payment 'CFL_CONTINUE))
  
  (?validate_schema
   (pipeline @log_insufficient 'CFL_RESET))
  
  (else
   (pipeline @log_invalid 'CFL_HALT)))
```

### 5. debug - Debug Messages

Transparent wrapper for debug output (does not affect control flow).

**Syntax:**
```lisp
(debug "debug message" body-expression)
```

**Behavior:**
- Calls `debug_function(handle, message, node, event_id, event_data)`
- Executes body-expression
- Returns result of body-expression (transparent passthrough)
- If `debug_function` is None, silently ignored

**Example:**
```lisp
(debug "Starting payment validation"
  (if ?validate_payment
      (debug "Payment valid, processing"
        (pipeline !process_payment 'CFL_CONTINUE))
      (debug "Payment invalid"
        'CFL_HALT)))
```

### Boolean Combinators

Combine boolean predicates for complex conditions:

| Combinator | Syntax | Description |
|------------|--------|-------------|
| `and` | `(and ?p1 ?p2 ... ?pN)` | All predicates must be true |
| `or` | `(or ?p1 ?p2 ... ?pN)` | At least one predicate must be true |
| `not` | `(not ?predicate)` | Negates the predicate |

**Example:**
```lisp
(if (and ?is_authenticated 
         (or ?is_admin ?is_moderator)
         (not ?is_suspended))
    (pipeline @grant_access 'CFL_CONTINUE)
    'CFL_HALT)
```

## Macro System

Macros provide text-based template expansion for reusable workflow patterns. Macros are expanded **before tokenization**, making them a pure text preprocessing step.

### Defining Macros

**Method 1: Individual Registration**
```python
seq.define_macro("macro_name", ["param1", "param2"], """
template text with $param1 and $param2
""")
```

**Method 2: Bulk Registration**
```python
macros = {
    "log_pipeline": {
        "params": ["msg", "func"],
        "template": "(pipeline (@log $msg) $func 'CFL_CONTINUE)"
    },
    "validated_action": {
        "params": ["check", "action"],
        "template": "(if $check (pipeline $action 'CFL_CONTINUE) 'CFL_HALT)"
    }
}
result = seq.define_macros_bulk(macros)
```

**Method 3: Load from YAML**
```yaml
# macros.yaml
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
```

```python
result = seq.load_macros_from_yaml("macros.yaml")
print(f"Loaded {len(result['registered'])} macros")
```

**Method 4: Load from JSON**
```python
result = seq.load_macros_from_json("macros.json")
```

### Using Macros

```python
# Define macros
seq.define_macro("log_pipeline", ["msg", "func"], """
(pipeline 
  (@log $msg)
  $func
  'CFL_CONTINUE)
""")

# Use in workflow
workflow = """
(dispatch event_id
  ("order.process"
   (log_pipeline "Processing order" !process_order))
  (default 'CFL_DISABLE))
"""

# Expand and validate
result = seq.check_lisp_instruction_with_macros(workflow)

# View expanded form
print("Expanded:", result['expanded_text'])

# Execute (no difference from non-macro code)
code = seq.run_lisp_instruction("node", result, "order.process", {})
```

### Macro Examples

**Example 1: Logging Wrapper**
```python
seq.define_macro("with_logging", ["action", "message"], """
(pipeline
  (@log_start $message)
  $action
  (@log_end $message)
  'CFL_CONTINUE)
""")

# Usage
"""
(with_logging !process_data "Processing customer data")
"""

# Expands to:
"""
(pipeline
  (@log_start "Processing customer data")
  !process_data
  (@log_end "Processing customer data")
  'CFL_CONTINUE)
"""
```

**Example 2: Conditional Validation**
```python
seq.define_macro("validated_pipeline", ["check", "action", "log_msg"], """
(if $check
    (pipeline 
      (@log $log_msg)
      $action
      'CFL_CONTINUE)
    'CFL_HALT)
""")

# Usage
"""
(validated_pipeline ?check_balance !process_payment "Payment validated")
"""
```

**Example 3: Error Handling Pattern**
```python
seq.define_macro("try_action", ["action", "fallback"], """
(cond
  ($action (pipeline (@log "Success") 'CFL_CONTINUE))
  (else (pipeline (@log "Failed") $fallback 'CFL_RESET)))
""")

# Usage
"""
(try_action !risky_operation !safe_fallback)
"""
```

**Example 4: Nested Macros**
```python
# Define base macro
seq.define_macro("safe_action", ["func"], """
(pipeline 
  (@log "Starting action")
  $func
  (@log "Action completed")
  'CFL_CONTINUE)
""")

# Define composed macro
seq.define_macro("full_pipeline", ["check", "action"], """
(if $check
    (safe_action $action)
    'CFL_HALT)
""")

# Usage
"""
(full_pipeline ?validate_schema !process_data)
"""

# Expands to:
"""
(if ?validate_schema
    (pipeline 
      (@log "Starting action")
      !process_data
      (@log "Action completed")
      'CFL_CONTINUE)
    'CFL_HALT)
"""
```

### Macro API Reference

| Method | Purpose |
|--------|---------|
| `define_macro(name, params, template)` | Define a single macro |
| `define_macros_bulk(macro_dict)` | Define multiple macros at once |
| `load_macros_from_yaml(path)` | Load macros from YAML file |
| `load_macros_from_json(path)` | Load macros from JSON file |
| `export_macros_to_yaml(path)` | Export all macros to YAML |
| `check_lisp_instruction_with_macros(text)` | Expand macros and validate |
| `expand_macros(text)` | Just expand macros (no validation) |
| `list_macros()` | List all defined macros |
| `get_macro(name)` | Get details of specific macro |
| `remove_macro(name)` | Remove a macro |
| `clear_macros()` | Remove all macros |

### Macro Features

- **Text-based expansion**: Operates before tokenization
- **Parameter substitution**: `$param` replaced with argument values
- **Nested expansion**: Macros can call other macros
- **Type agnostic**: Accepts strings, numbers, functions, S-expressions
- **Error checking**: Validates parameter count and syntax
- **Composable**: Build complex patterns from simple macros

### Macro Best Practices

1. **Keep macros simple**: Complex logic belongs in functions
2. **Use descriptive names**: `log_pipeline` not `lp`
3. **Document purpose**: Add comments in YAML/JSON files
4. **Test expansion**: Use `expand_macros()` to verify templates
5. **Avoid recursion**: Don't define macros that call themselves
6. **Organize by feature**: Group related macros in separate files

## Complete Examples

### Example 1: Payment Processing

```python
from lisp_sequencer_with_macros import LispSequencer

CONTROL_CODES = ["CFL_CONTINUE", "CFL_HALT", "CFL_RESET", "CFL_DISABLE"]

def run_fn(handle, func_type, func_name, node, event_id, event_data, params):
    if func_type == '@':
        print(f"Action: {func_name}")
    elif func_type == '?':
        if func_name == "validate_schema":
            return event_data.get("valid", False)
        elif func_name == "check_balance":
            return event_data.get("balance", 0) > 0
        return True
    elif func_type == '!':
        if func_name == "process_payment":
            return "CFL_CONTINUE" if event_data.get("paid") else "CFL_HALT"
        return "CFL_CONTINUE"

seq = LispSequencer("payment", run_fn, control_codes=CONTROL_CODES)

# Define macros
seq.define_macro("validated_payment", ["validator", "processor"], """
(if (and $validator ?check_balance)
    (pipeline 
      (@log "Payment processing")
      $processor
      (@notify_success)
      'CFL_CONTINUE)
    (pipeline
      (@log "Validation failed")
      'CFL_HALT))
""")

# Use macro
workflow = """
(dispatch event_id
  ("payment.process"
   (validated_payment ?validate_schema !process_payment))
  (default 'CFL_DISABLE))
"""

result = seq.check_lisp_instruction_with_macros(workflow)

# Execute
payment_data = {"valid": True, "balance": 100, "paid": True}
code = seq.run_lisp_instruction("node", result, "payment.process", payment_data)
print(f"Result: {code}")
```

### Example 2: State Machine (from original README)

```python
# State machine for order processing
state_machine = """
(dispatch event_id
  ("order.process"
   (cond
     (?is_state_new
      (debug "State: NEW → VALIDATED"
        (if ?validate_order
            (pipeline 
              (@set_state "validated")
              (@emit_event "order.validated")
              'CFL_CONTINUE)
            (pipeline
              (@set_state "invalid")
              (@emit_event "order.invalid")
              'CFL_HALT))))
     
     (?is_state_validated
      (debug "State: VALIDATED → PAID"
        (if !process_payment
            (pipeline 
              (@set_state "paid")
              (@emit_event "order.paid")
              'CFL_CONTINUE)
            'CFL_HALT)))
     
     (?is_state_paid
      (debug "State: PAID → SHIPPED"
        (pipeline 
          !create_shipment
          (@set_state "shipped")
          (@emit_event "order.shipped")
          'CFL_CONTINUE)))
     
     (?is_state_shipped
      (debug "State: SHIPPED → COMPLETED"
        (if ?is_delivered
            (pipeline 
              (@set_state "completed")
              (@emit_event "order.completed")
              'CFL_CONTINUE)
            'CFL_CONTINUE)))
     
     (else
      (debug "Invalid state transition" 'CFL_HALT))))
  
  ("order.cancel"
   (cond
     ((or ?is_state_new ?is_state_validated)
      (debug "Cancelling order"
        (pipeline 
          (@set_state "cancelled")
          (@emit_event "order.cancelled")
          'CFL_CONTINUE)))
     
     (?is_state_paid
      (debug "Refunding order"
        (pipeline 
          !process_refund
          (@set_state "refunded")
          (@emit_event "order.refunded")
          'CFL_CONTINUE)))
     
     (else
      (debug "Cannot cancel in current state" 'CFL_HALT))))
  
  (default 'CFL_DISABLE))
"""

# Implementation
def run_fn(handle, func_type, func_name, node, event_id, event_data, params):
    if func_type == '?':
        # State checking predicates
        if func_name.startswith("is_state_"):
            state = func_name[9:]  # Remove "is_state_" prefix
            return event_data.get("state") == state
        elif func_name == "is_delivered":
            return event_data.get("delivered", False)
    
    elif func_type == '@':
        # State transitions
        if func_name == "set_state":
            event_data["state"] = params[0]
        elif func_name == "emit_event":
            print(f"Event emitted: {params[0]}")
    
    elif func_type == '!':
        # Business logic
        if func_name == "validate_order":
            return "CFL_CONTINUE" if event_data.get("valid") else "CFL_HALT"
        elif func_name == "process_payment":
            return "CFL_CONTINUE" if event_data.get("paid") else "CFL_HALT"
        # ...

# Execute state machine
CONTROL_CODES = ["CFL_CONTINUE", "CFL_HALT", "CFL_RESET"]
seq = LispSequencer("order-system", run_fn, control_codes=CONTROL_CODES)
compiled = seq.check_lisp_instruction(state_machine)

order_data = {"order_id": "12345", "state": "new", "valid": True}

result = seq.run_lisp_instruction("order-node", compiled, "order.process", order_data)
print(f"State: {order_data['state']}, Result: {result}")
```

## Best Practices

### 1. Function Naming

Use descriptive names with underscores:
```lisp
; Good
@log_user_action
?validate_email_format
!process_payment_request

; Avoid (too short)
@log
?valid
!process
```

### 2. Use Debug for Traceability

Wrap complex logic with debug messages:
```lisp
(debug "Entering payment validation"
  (if (and ?validate_schema ?check_balance)
      (debug "Validation passed, processing"
        (pipeline !process 'CFL_CONTINUE))
      (debug "Validation failed"
        'CFL_HALT)))
```

### 3. Reuse Tokenized Forms

Parse once, execute many:
```python
# Parse at startup
workflow = seq.check_lisp_instruction(code)

# Execute in event loop
for event in event_stream:
    code = seq.run_lisp_instruction(node, workflow, event.id, event.data)
```

### 4. Use cond for Multi-way Branches

Prefer `cond` over nested `if` when you have 3+ branches:
```lisp
; Good
(cond
  (?is_admin (pipeline !admin_action 'CFL_CONTINUE))
  (?is_moderator (pipeline !mod_action 'CFL_CONTINUE))
  (?is_user (pipeline !user_action 'CFL_CONTINUE))
  (else 'CFL_HALT))
```

### 5. Store State in event_data

Make `event_data` a mutable dictionary for state machines:
```python
# State stored in event_data
order_data = {"state": "new", "amount": 99.99}
seq.run_lisp_instruction("node1", workflow, "order.process", order_data)
print(order_data["state"])  # Updated by workflow
```

### 6. Use Parameters for Configuration

Pass configuration as parameters:
```lisp
(pipeline 
  (@log "Starting" 1)
  (@set_timeout 300)
  (?check_threshold 1000 "USD")
  (@send_notification "admin@company.com" "Process started")
  'CFL_CONTINUE)
```

### 7. Organize Macros by Feature

For large projects, organize macros in separate files:
```
macros/
  ├── logging.yaml       # Logging-related macros
  ├── validation.yaml    # Validation patterns
  ├── workflows.yaml     # Common workflows
  └── error_handling.yaml
```

```python
# Load all macro files
seq.load_macros_from_yaml("macros/logging.yaml")
seq.load_macros_from_yaml("macros/validation.yaml")
seq.load_macros_from_yaml("macros/workflows.yaml")
```

### 8. Use Macros for Repeated Patterns

Identify common patterns and create macros:
```python
# Common pattern: log → validate → process → notify
seq.define_macro("standard_workflow", ["validator", "processor"], """
(pipeline
  (@log "Starting workflow")
  (if $validator
      (pipeline 
        $processor
        (@notify_success)
        'CFL_CONTINUE)
      (pipeline
        (@notify_failure)
        'CFL_HALT)))
""")
```

## Error Handling

Common validation errors and solutions:

| Error | Cause | Solution |
|-------|-------|----------|
| "Boolean in pipeline" | Used `?fn` in pipeline | Use `@fn` or `!fn` instead |
| "Non-boolean in conditional" | Used `@fn` or `!fn` in if/cond | Use `?fn` instead |
| "dispatch missing default case" | No default clause | Add `(default 'CFL_DISABLE)` |
| "Invalid function name" | Not valid Python identifier | Use valid identifier (letter/underscore start) |
| "cannot start with a digit" | Function name starts with number | Start with letter: `!fn0` not `!0fn` |
| "cannot use Python keyword" | Used reserved word like `class` | Rename: `?is_class` not `?class` |
| "too many parameters" | More than 10 parameters | Reduce to 10 or fewer |
| "Parameter must be string or number" | Invalid parameter type | Use only strings, ints, floats |
| "Unmatched opening parenthesis" | Syntax error | Check parentheses balance |
| "Macro expects N arguments" | Wrong macro argument count | Match parameter count in definition |
| "Unbalanced parentheses in macro" | Macro call syntax error | Balance parentheses |
| "Macro not found" | Undefined macro used | Define macro before use |

## Performance Considerations

- **Parse once, execute many**: Store result of `check_lisp_instruction` and reuse
- **Tokenized execution**: No re-parsing on each execution
- **Macro expansion**: Happens once at validation time, zero runtime overhead
- **Control flow short-circuit**: Pipeline stops immediately on non-CONTINUE control codes
- **YAML/JSON overhead**: Minimal - control codes work as both tuples and lists

## Type Safety Rules

The parser enforces type constraints at compile time:

| Context | Allowed | Error Example |
|---------|---------|---------------|
| pipeline steps | `@fn`, `!fn` | `?fn` → "Boolean in pipeline" |
| if/cond predicate | `?fn`, `and`, `or`, `not` | `@fn` → "Non-boolean in conditional" |
| Top-level | Must return control code | `?fn` → "Invalid return" |

## Grammar Summary (BNF)

```
<expr> ::= <dispatch> | <pipeline> | <if> | <cond> | <debug> | <control-code> | <macro-call>

<dispatch> ::= (dispatch event_id <case>+ (default <expr>))
<case> ::= (<pattern> <expr>)
<pattern> ::= <string> | <string-list>

<pipeline> ::= (pipeline <step>+ <control-code>)
<step> ::= <void-fn> | <control-fn> | <void-fn-call> | <control-fn-call>

<if> ::= (if <predicate> <expr> <expr>)

<cond> ::= (cond <cond-case>+ (else <expr>))
<cond-case> ::= (<predicate> <expr>)

<debug> ::= (debug <string> <expr>)

<macro-call> ::= (<macro-name> <arg>*)
<arg> ::= <string> | <number> | <function> | <quote> | <expr>

<predicate> ::= <bool-fn> | <bool-fn-call> | <bool-combinator>
<bool-combinator> ::= (and <predicate>+) | (or <predicate>+) | (not <predicate>)

<void-fn> ::= @<identifier>
<bool-fn> ::= ?<identifier>
<control-fn> ::= !<identifier>

<void-fn-call> ::= (@<identifier> <param>*)
<bool-fn-call> ::= (?<identifier> <param>*)
<control-fn-call> ::= (!<identifier> <param>*)

<param> ::= <string> | <number>
<number> ::= <integer> | <float>

<control-code> ::= 'CFL_CONTINUE | 'CFL_HALT | 'CFL_TERMINATE | 
                   'CFL_RESET | 'CFL_DISABLE | 'CFL_TERMINATE_SYSTEM
```

## License

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Version History

- **3.0.0** - Macro system release
  - Added text-based macro expansion system
  - Macros expand before tokenization
  - Support for bulk registration, YAML, and JSON macro files
  - New methods: `define_macro`, `define_macros_bulk`, `load_macros_from_yaml`, `load_macros_from_json`
  - New validation method: `check_lisp_instruction_with_macros`
  - Macro management utilities: `list_macros`, `get_macro`, `remove_macro`, `clear_macros`
  - 100% backward compatible - all existing code works unchanged
  
- **2.0.0** - Simplified API release
  - Removed `get_function`, `store_function`, `validate_functions`
  - Functions stored as full names (`'@log'` not `('@', 'log')`)
  - Added string and number parameter support
  - YAML/JSON compatibility (tuples and lists both work)
  - Simplified to 2 public methods: `check_lisp_instruction`, `run_lisp_instruction`
  
- **1.0.0** - Initial release
  - Core primitives: dispatch, pipeline, if, cond, debug
  - Type-safe function markers
  - Pre-compilation support

## Contributing

Contributions are welcome! Areas for enhancement:
- Additional primitives (loop, try-catch, etc.)
- Performance optimizations
- Extended validation rules
- More comprehensive error messages
- Additional macro utilities and standard library

## Support

For questions, issues, or feature requests, please open an issue on the project repository.