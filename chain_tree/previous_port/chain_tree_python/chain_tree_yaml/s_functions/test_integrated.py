"""
Test: LispSequencer with integrated Mako support
"""

from lisp_sequencer import LispSequencer, MAKO_AVAILABLE

# Setup
def run_fn(handle, func_type, func_name, node, event_id, event_data, params=[]):
    """Execute a function."""
    print(f"  → {func_type}{func_name}{f'({params})' if params else ''}")
    if func_type == '?':
        return True
    elif func_type == '!':
        return "CFL_CONTINUE"

def debug_fn(handle, message, node, event_id, event_data):
    """Output debug messages."""
    print(f"  [DEBUG] {message}")

CONTROL_CODES = ["CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", "CFL_DISABLE"]

print("=" * 80)
print("INTEGRATED LISP SEQUENCER WITH MAKO")
print("=" * 80)
print(f"Mako Available: {MAKO_AVAILABLE}")
print()

# Create sequencer - now with built-in Mako support!
seq = LispSequencer("handle", run_fn, debug_fn, control_codes=CONTROL_CODES)

# Example 1: Define macros (works with or without Mako)
print("--- Example 1: Define Macros ---")
result = seq.define_macro("log_action", ["msg", "action"], """
(pipeline 
  (@log $msg)
  $action
  'CFL_CONTINUE)
""")
print(f"Macro defined: {result['valid']}")

result = seq.define_macro("safe_handler", ["check", "action"], """
(if $check
    $action
    'CFL_HALT)
""")
print(f"Macro defined: {result['valid']}")

# Example 2: Use macros without Mako (standard expansion)
print("\n--- Example 2: Standard Macro Expansion ---")
code = """
(dispatch event_id
  ("order.process"
   (log_action "Processing order" !process_order))
  (default 'CFL_DISABLE))
"""

result = seq.check_lisp_instruction_with_macros(code)
print(f"Code valid: {result['valid']}")
if result['valid']:
    print("Executing:")
    exit_code = seq.run_lisp_instruction("node1", result, "order.process", {})
    print(f"Result: {exit_code}")

# Example 3: Mako integration (if available)
if MAKO_AVAILABLE:
    print("\n--- Example 3: Mako Template Generation ---")
    
    # Export macros for Mako use
    seq.export_macros_to_mako()
    print("✓ Macros exported to Mako")
    
    # Generate code with Mako
    template = """
% for event in events:
(dispatch event_id
  ("${event['id']}"
   ${log_action(msg=f'"{event["desc"]}"', action=event['handler'])})
  (default 'CFL_DISABLE))

% endfor
"""
    
    events = [
        {"id": "order.new", "desc": "New order", "handler": "!create_order"},
        {"id": "order.cancel", "desc": "Cancel order", "handler": "!cancel_order"},
    ]
    
    generated = seq.render_with_mako(template, events=events)
    print("Generated code:")
    print(generated)
    
    # Validate generated code
    result = seq.check_lisp_instruction_with_macros(generated)
    print(f"\nGenerated code valid: {result['valid']}")
    
    # Example 4: List macros
    print("\n--- Example 4: List Macros ---")
    macros = seq.list_macros()
    print("Available macros:")
    for name, params in macros.items():
        print(f"  {name}({', '.join(params)})")
    
    # Example 5: Worker pool generation
    print("\n--- Example 5: Generate Worker Pool ---")
    template = """
% for i in range(num_workers):
(dispatch event_id
  ("worker.${i}.task"
   (pipeline
     (@log "Worker ${i} processing")
     (!process ${i})
     'CFL_CONTINUE))
  (default 'CFL_DISABLE))

% endfor
"""
    
    generated = seq.render_with_mako(template, num_workers=3)
    print("Generated worker pool:")
    print(generated)
    
    result = seq.check_lisp_instruction_with_macros(generated)
    print(f"Worker pool valid: {result['valid']}")

else:
    print("\n--- Mako Not Installed ---")
    print("Install with: pip install mako")
    print("LispSequencer still works for standard macro expansion!")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("✓ Single LispSequencer class")
print("✓ Built-in Mako support (optional)")
print("✓ Same define_macro() method")
print("✓ Simple API: export_macros_to_mako(), render_with_mako()")
print("✓ No separate bridge class needed")
print("✓ Backward compatible")
print("=" * 80)

