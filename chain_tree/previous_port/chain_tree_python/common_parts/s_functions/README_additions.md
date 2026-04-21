# LispSequencer with Mako Integration

Generate Lisp control flow code using Mako templates.

## One-Minute Overview

```python
from lisp_sequencer_with_mako import LispSequencer

# Create sequencer (same as before)
seq = LispSequencer(handle, run_fn, debug_fn, control_codes=CONTROL_CODES)

# Define macros (same as before)
seq.define_macro("log_action", ["msg", "action"], """
(pipeline (@log $msg) $action 'CFL_CONTINUE)
""")

# NEW: Export to Mako
seq.export_macros_to_mako()

# NEW: Generate code with Mako
code = seq.render_with_mako("""
% for event in events:
(dispatch event_id
  ("${event['id']}" ${log_action(msg=event['msg'], action=event['handler'])})
  (default 'CFL_DISABLE))
% endfor
""", events=[{"id": "order.new", "msg": '"Processing"', "handler": "!process"}])

# Validate and execute (same as before)
result = seq.check_lisp_instruction_with_macros(code)
if result['valid']:
    seq.run_lisp_instruction(node, result, event_id, data)
```

## What's New?

**LispSequencer now has built-in Mako support!**

- ✅ Same `define_macro()` method you know
- ✅ Three new methods: `export_macros_to_mako()`, `render_with_mako()`, `render_file()`
- ✅ No separate bridge class needed
- ✅ Backward compatible
- ✅ Mako is optional (works without it)

## Installation

```bash
pip install mako  # Optional, for template generation
```

## Files

| File | Description |
|------|-------------|
| **lisp_sequencer_with_mako.py** | ⭐ Main class (use this!) |
| **SIMPLE_API_GUIDE.md** | Complete API documentation |
| **test_integrated.py** | Working examples |
| **event_handler_template.mako** | Starter template |
| **INDEX.md** | Package overview |

## API

### Define Macros (Unchanged)
```python
seq.define_macro(name, params, template)
```

### Export to Mako (New)
```python
seq.export_macros_to_mako()  # Call once after defining macros
```

### Generate Code (New)
```python
# From string
code = seq.render_with_mako(template_string, **context)

# From file
code = seq.render_file('template.mako', **context)
```

### Validate & Execute (Unchanged)
```python
result = seq.check_lisp_instruction_with_macros(code)
if result['valid']:
    seq.run_lisp_instruction(node, result, event_id, data)
```

## Examples

### Event Handler Generation
```python
template = """
% for event in events:
(dispatch event_id ("${event['id']}" !${event['handler']}))
% endfor
"""

code = seq.render_with_mako(template, events=[
    {"id": "order.new", "handler": "create_order"},
    {"id": "order.cancel", "handler": "cancel_order"}
])
```

### Worker Pool
```python
template = """
% for i in range(num_workers):
(dispatch event_id ("worker.${i}.task" (!process ${i})))
% endfor
"""

code = seq.render_with_mako(template, num_workers=8)
```

### With Macros
```python
seq.define_macro("safe_action", ["check", "action"], """
(if $check $action 'CFL_HALT)
""")
seq.export_macros_to_mako()

template = """
% for event in events:
${safe_action(check=event['guard'], action=event['handler'])}
% endfor
"""

code = seq.render_with_mako(template, events=[...])
```

## Migration from Bridge Pattern

**Old way:**
```python
from mako_lisp_bridge import MakoLispBridge
bridge = MakoLispBridge(seq)
bridge.export_lisp_macros_to_mako()
code = bridge.render_lisp_with_mako(template, **context)
```

**New way:**
```python
# No bridge needed!
seq.export_macros_to_mako()
code = seq.render_with_mako(template, **context)
```

## Documentation

- **SIMPLE_API_GUIDE.md** - Start here for the integrated version
- **QUICK_REFERENCE.md** - Quick syntax reference
- **INTEGRATION_GUIDE.md** - Complete guide (bridge pattern)
- **INDEX.md** - Full package overview

## Key Features

✓ **Single class** - LispSequencer does everything  
✓ **Same define_macro()** - No API changes  
✓ **Optional Mako** - Works without Mako installed  
✓ **Backward compatible** - Existing code works  
✓ **Template files** - Use `.mako` files  
✓ **Type safe** - Validation before execution  

## Without Mako

If Mako isn't installed, LispSequencer works normally for macro expansion:

```python
# These work without Mako
seq.define_macro(...)
result = seq.check_lisp_instruction_with_macros(code)
seq.run_lisp_instruction(...)

# These require Mako
seq.export_macros_to_mako()  # ImportError with install instructions
seq.render_with_mako(...)     # ImportError with install instructions
```

## Use Cases

- **Configuration-driven generation** - Generate from YAML/JSON
- **Multi-tenant systems** - Custom handlers per tenant
- **Development scaffolding** - Generate boilerplate
- **Runtime adaptation** - Dynamic control flows
- **Distributed systems** - Event handler generation

## License

(Your license here)

## Getting Started

1. Read **SIMPLE_API_GUIDE.md**
2. Run `python test_integrated.py`
3. Try modifying `event_handler_template.mako`
4. Build your own templates

**Questions?** Check the docs or examples!
