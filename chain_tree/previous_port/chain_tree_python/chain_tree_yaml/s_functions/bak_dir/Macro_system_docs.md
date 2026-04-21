# Lisp Sequencer Macro Expansion System

## Overview

The macro expansion system provides text-based template substitution for Lisp instructions. Macros are expanded **before tokenization**, making them a pure text preprocessing step that doesn't affect the core parsing and execution logic.

## Key Design Principles

1. **Text-Only Expansion**: Macros perform simple text replacement with parameter substitution
2. **Pre-Tokenization**: Expansion happens before the token parser runs
3. **Non-Invasive**: `check_lisp_instruction()` and `run_lisp_instruction()` remain unchanged
4. **Composable**: Macros can call other macros (nested expansion)

## API Reference

### Defining Macros

```python
seq.define_macro(name, params, template)
```

**Parameters:**
- `name` (str): Macro name (must be valid identifier)
- `params` (list[str]): List of parameter names
- `template` (str): Template text with `$param` placeholders

**Returns:**
- Dict with `'valid'` (bool) and `'errors'` (list)

**Example:**
```python
seq.define_macro("log_pipeline", ["msg", "func"], """
(pipeline 
  (@log $msg)
  $func
  'CFL_CONTINUE)
""")
```

### Using Macros

Use `check_lisp_instruction_with_macros()` instead of `check_lisp_instruction()`:

```python
result = seq.check_lisp_instruction_with_macros(lisp_text)
```

**Returns:**
- Dict with:
  - `'valid'` (bool): Whether expansion and validation succeeded
  - `'errors'` (list): Any expansion or validation errors
  - `'text'` (str): Original input text
  - `'expanded_text'` (str): Text after macro expansion
  - `'ast'`: Parsed AST (if valid)
  - `'functions'` (list): Required functions

### Macro Expansion Only

If you only want to expand macros without validation:

```python
result = seq.expand_macros(lisp_text)
```

**Returns:**
- Dict with `'valid'`, `'errors'`, `'expanded_text'`, `'original_text'`

## Macro Syntax

### Defining a Macro

```lisp
; Conceptual syntax (define with seq.define_macro() in Python)
(defmacro macro_name (param1 param2)
  "template text with $param1 and $param2")
```

### Calling a Macro

```lisp
(macro_name "value1" "value2")
```

Macros are called like functions, with arguments in S-expression format.

## Examples

### Example 1: Simple Logging Pipeline

**Define:**
```python
seq.define_macro("log_pipeline", ["msg", "func"], """
(pipeline 
  (@log $msg)
  $func
  'CFL_CONTINUE)
""")
```

**Use:**
```lisp
(dispatch event_id
  ("order.process"
   (log_pipeline "Processing order" !process_order))
  (default 'CFL_DISABLE))
```

**Expands to:**
```lisp
(dispatch event_id
  ("order.process"
   (pipeline 
     (@log "Processing order")
     !process_order
     'CFL_CONTINUE))
  (default 'CFL_DISABLE))
```

### Example 2: Conditional with Validation

**Define:**
```python
seq.define_macro("validated_pipeline", ["check_func", "action_func", "log_msg"], """
(if $check_func
    (pipeline 
      (@log $log_msg)
      $action_func
      'CFL_CONTINUE)
    'CFL_HALT)
""")
```

**Use:**
```lisp
(dispatch event_id
  ("payment.process"
   (validated_pipeline ?check_balance !process_payment "Payment validated"))
  (default 'CFL_DISABLE))
```

**Expands to:**
```lisp
(dispatch event_id
  ("payment.process"
   (if ?check_balance
       (pipeline 
         (@log "Payment validated")
         !process_payment
         'CFL_CONTINUE)
       'CFL_HALT))
  (default 'CFL_DISABLE))
```

### Example 3: Nested Macros

**Define:**
```python
seq.define_macro("safe_action", ["func"], """
(pipeline 
  (@log "Starting action")
  $func
  (@log "Action completed")
  'CFL_CONTINUE)
""")

seq.define_macro("full_pipeline", ["check", "action"], """
(if $check
    (safe_action $action)
    'CFL_HALT)
""")
```

**Use:**
```lisp
(dispatch event_id
  ("data.validate"
   (full_pipeline ?validate_schema !process_data))
  (default 'CFL_DISABLE))
```

**Expands to:**
```lisp
(dispatch event_id
  ("data.validate"
   (if ?validate_schema
       (pipeline 
         (@log "Starting action")
         !process_data
         (@log "Action completed")
         'CFL_CONTINUE)
       'CFL_HALT))
  (default 'CFL_DISABLE))
```

## Parameter Types

Macros accept any valid Lisp syntax as arguments:

1. **Strings**: `"my string"`
2. **Numbers**: `123`, `45.6`
3. **Functions**: `@log`, `?check`, `!process`
4. **Quotes**: `'CFL_CONTINUE`
5. **S-expressions**: `(pipeline @a @b)`

## Error Handling

The macro system validates:

1. **Macro name**: Must be valid identifier (letters, numbers, underscores)
2. **Parameter names**: Must be valid identifiers
3. **Parameter count**: Must match macro definition
4. **Balanced parentheses**: Ensures proper S-expression structure
5. **Recursion limit**: Prevents infinite macro expansion (max 100 iterations)

### Common Errors

**Undefined Macro:**
```python
# Error: Macro 'undefined_macro' not found
(undefined_macro "arg")
```

**Wrong Number of Arguments:**
```python
# log_pipeline expects 2 arguments
seq.define_macro("log_pipeline", ["msg", "func"], "...")
(log_pipeline "only_one_arg")  # Error: expects 2, got 1
```

**Unbalanced Parentheses:**
```python
(log_pipeline "msg" !func  # Error: missing closing parenthesis
```

## Integration with Existing Code

### Without Macros (Original)
```python
result = seq.check_lisp_instruction(lisp_text)
if result['valid']:
    code = seq.run_lisp_instruction(node, result, event_id, event_data)
```

### With Macros (New)
```python
result = seq.check_lisp_instruction_with_macros(lisp_text)
if result['valid']:
    code = seq.run_lisp_instruction(node, result, event_id, event_data)
```

The `run_lisp_instruction()` method remains unchanged and works with both expanded and non-expanded instructions.

## Advanced Features

### Inspecting Expansion

```python
result = seq.check_lisp_instruction_with_macros(lisp_text)
print("Original:", result['text'])
print("Expanded:", result['expanded_text'])
```

### Macro Storage

Macros are stored in the `seq.macros` dictionary:

```python
# View all defined macros
for name, (params, template) in seq.macros.items():
    print(f"{name}({', '.join(params)})")
```

### Clearing Macros

```python
seq.macros.clear()  # Remove all macros
del seq.macros['macro_name']  # Remove specific macro
```

## Implementation Details

### Expansion Algorithm

1. Scan text for `(macro_name ...)`
2. For each macro call:
   - Extract arguments between `(` and matching `)`
   - Parse arguments handling strings, quotes, and nested S-expressions
   - Substitute `$param` in template with argument values
   - Replace macro call with expanded text
3. Repeat until no more macros found (or max iterations reached)

### Performance Considerations

- Macro expansion is O(n*m) where n = text length, m = number of macros
- Nested macros may require multiple passes
- Expansion happens once at validation time
- Execution uses pre-expanded AST (no runtime overhead)

## Best Practices

1. **Keep macros simple**: Complex logic belongs in functions, not macros
2. **Descriptive names**: Use clear names like `log_pipeline` not `lp`
3. **Document templates**: Add comments explaining macro purpose
4. **Test expansion**: Use `expand_macros()` to verify templates
5. **Avoid recursion**: Don't define macros that call themselves

## Migration Guide

### Existing Code

No changes needed! Your existing code continues to work:

```python
# Still works exactly as before
result = seq.check_lisp_instruction(lisp_text)
```

### Adding Macro Support

```python
# Step 1: Define your macros
seq.define_macro("my_macro", ["param1"], "template")

# Step 2: Use the new method
result = seq.check_lisp_instruction_with_macros(lisp_text)

# Step 3: Execute as normal
code = seq.run_lisp_instruction(node, result, event_id, event_data)
```

## Summary

The macro expansion system provides a powerful way to create reusable templates while maintaining the simplicity and elegance of the Lisp sequencer. By operating at the text level before tokenization, macros remain a lightweight preprocessing step that doesn't complicate the core execution engine.

