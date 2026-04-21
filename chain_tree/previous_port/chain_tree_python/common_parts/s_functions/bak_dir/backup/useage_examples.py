"""
Comprehensive Usage Examples for LispSequencer

This file demonstrates how to use the LispSequencer class with:
- Handle-based execution
- Mako template preprocessing
- User-defined templates
- Context variables
"""

from lisp_sequencer import LispSequencer
import json


# =============================================================================
# STEP 1: Define your execution functions
# =============================================================================

def my_run_function(handle, ast, *args, **kwargs):
    """
    Your custom function that processes the AST.
    
    Args:
        handle: The context handle you provided during initialization
        ast: The parsed Abstract Syntax Tree of the Lisp instruction
        *args, **kwargs: Any additional arguments passed to run()
    
    Returns:
        Whatever your execution logic produces
    """
    print(f"\n--- EXECUTING WITH HANDLE ---")
    print(f"Handle data: {handle}")
    print(f"AST: {ast}")
    
    # Example: Process the AST recursively
    def process_node(node):
        if isinstance(node, list):
            if len(node) > 0:
                operator = node[0]
                print(f"  Processing operator: {operator}")
                # Your custom logic here based on operator
                for child in node[1:]:
                    process_node(child)
        else:
            print(f"  Atom value: {node}")
    
    process_node(ast)
    
    return {"status": "completed", "handle_id": handle.get("id")}


def my_debug_function(handle, message):
    """
    Optional debug function for logging.
    
    Args:
        handle: The context handle
        message: Debug message from the sequencer
    """
    print(f"[DEBUG - Session {handle.get('session', 'N/A')}] {message}")


# =============================================================================
# STEP 2: Create your context handle
# =============================================================================

# Your handle can be any data structure that contains context for execution
my_handle = {
    "id": "workflow_12345",
    "session": "user_session_abc",
    "user_id": "user_789",
    "environment": "production",
    "metadata": {
        "start_time": "2025-10-23T10:00:00Z",
        "priority": "high"
    }
}


# =============================================================================
# STEP 3: Initialize the LispSequencer
# =============================================================================

print("=" * 80)
print("INITIALIZING LISPSEQUENCER")
print("=" * 80)

sequencer = LispSequencer(
    handle=my_handle,
    run_function=my_run_function,
    debug_function=my_debug_function,
    control_codes=["STOP", "PAUSE", "RESUME"],
    # Optional: Load user templates at initialization
    # user_macro_file='workflow_templates.mako',
    enable_mako=True  # Enable Mako by default
)

print(f"Sequencer initialized with handle: {my_handle['id']}\n")


# =============================================================================
# EXAMPLE 1: Basic execution without templates
# =============================================================================

print("=" * 80)
print("EXAMPLE 1: Basic execution (no templates)")
print("=" * 80)

basic_instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    (@CFL_FORK 0)
    (@DO_WORK)
    (!CFL_JOIN 0)
    'CFL_FUNCTION_TERMINATE)
"""

result1 = sequencer.run(basic_instruction, use_mako=False)
print(f"\nResult: {result1}")


# =============================================================================
# EXAMPLE 2: Using built-in templates
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 2: Using built-in fork_join template")
print("=" * 80)

templated_instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%fork_join(0)%>
    <%fork_join(1)%>
    <%fork_join(2)%>
    'CFL_FUNCTION_TERMINATE)
"""

result2 = sequencer.run(templated_instruction)
print(f"\nResult: {result2}")


# =============================================================================
# EXAMPLE 3: Using send_event template
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 3: Using send_event template")
print("=" * 80)

event_instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%send_event("workflow_started", "start_data")%>
    (@PROCESS_DATA)
    <%send_event("workflow_completed", "result_data")%>
    'CFL_FUNCTION_TERMINATE)
"""

result3 = sequencer.run(event_instruction)
print(f"\nResult: {result3}")


# =============================================================================
# EXAMPLE 4: Load and use user-defined templates
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 4: Using user-defined templates from file")
print("=" * 80)

# Load user templates
sequencer.set_user_macros_from_file('workflow_templates.mako')
print(f"Loaded templates: {sequencer.get_loaded_macro_files()}")

user_template_instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%retry_block(0, 3)%>
    <%timeout_block(1, 30)%>
    <%error_handler(2, "Critical error occurred")%>
    'CFL_FUNCTION_TERMINATE)
"""

result4 = sequencer.run(user_template_instruction)
print(f"\nResult: {result4}")


# =============================================================================
# EXAMPLE 5: Using context variables with templates
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 5: Templates with context variables")
print("=" * 80)

parametric_instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
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

result5 = sequencer.run(parametric_instruction, mako_context=context)
print(f"\nResult: {result5}")


# =============================================================================
# EXAMPLE 6: Check first, then run
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 6: Check instruction validity before running")
print("=" * 80)

instruction_to_check = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%fork_join(0)%>
    (@EXECUTE_TASK "important_task")
    'CFL_FUNCTION_TERMINATE)
"""

# Check the instruction
check_result = sequencer.check_lisp_instruction(instruction_to_check)

print(f"Valid: {check_result['valid']}")
print(f"Original: {check_result['original_text'][:50]}...")
print(f"Processed: {check_result['text']}")
print(f"Functions found: {check_result['functions']}")
print(f"Mako used: {check_result['mako_used']}")

if check_result['valid']:
    # Run the already-checked instruction (no need to pass text again)
    result6 = sequencer.run()
    print(f"\nResult: {result6}")


# =============================================================================
# EXAMPLE 7: Dynamic macro control
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 7: Enable/disable specific macros")
print("=" * 80)

print(f"Initially enabled macros: {sequencer.get_enabled_macros()}")

# Disable some macros
sequencer.disable_macro('parallel')
sequencer.disable_macro('conditional')
print(f"After disabling: {sequencer.get_enabled_macros()}")

# Try using only enabled macros
instruction7 = """
(pipeline
    <%fork_join(0)%>
    <%send_event("test", "data")%>
    'CFL_FUNCTION_TERMINATE)
"""

result7 = sequencer.run(instruction7)
print(f"\nResult: {result7}")

# Re-enable
sequencer.enable_macro('parallel')
print(f"After re-enabling parallel: {sequencer.get_enabled_macros()}")


# =============================================================================
# EXAMPLE 8: Pass additional macro files at call time
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 8: Temporary macro files for single call")
print("=" * 80)

# Create a temporary macro file
temp_macros = """
<%def name="special_sequence(id, count)">
(@SPECIAL_START ${id})
(@SPECIAL_PROCESS ${count})
(@SPECIAL_END ${id})
</%def>
"""

with open('temp_macros.mako', 'w') as f:
    f.write(temp_macros)

instruction8 = """
(pipeline
    <%special_sequence(42, 100)%>
    'CFL_FUNCTION_TERMINATE)
"""

# Pass the temporary macro file just for this call
result8 = sequencer.run(
    instruction8,
    additional_macro_files='temp_macros.mako'
)
print(f"\nResult: {result8}")

# Clean up
import os
os.remove('temp_macros.mako')


# =============================================================================
# EXAMPLE 9: Complex workflow with mixed features
# =============================================================================

print("\n" + "=" * 80)
print("EXAMPLE 9: Complex workflow combining all features")
print("=" * 80)

complex_instruction = """
(pipeline
    (@CFL_KILL_CHILDREN)
    <%send_event("workflow_init", "init_data")%>
    
    <%retry_block(0, ${max_retries})%>
    
    % for step in processing_steps:
    (@CFL_FORK ${loop.index})
    (@PROCESS_STEP "${step}")
    (!CFL_JOIN ${loop.index})
    % endfor
    
    <%parallel(10, 11, 12)%>
    
    % if enable_timeout:
    <%timeout_block(99, ${timeout_value})%>
    % endif
    
    <%send_event("workflow_complete", "final_data")%>
    'CFL_FUNCTION_TERMINATE)
"""

complex_context = {
    'max_retries': 5,
    'processing_steps': ['validate', 'transform', 'enrich', 'store'],
    'enable_timeout': True,
    'timeout_value': 300
}

result9 = sequencer.run(complex_instruction, mako_context=complex_context)
print(f"\nResult: {result9}")


# =============================================================================
# SUMMARY
# =============================================================================

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("""
The LispSequencer provides:

1. Handle-based execution: Pass your context through 'handle' parameter
2. Custom run function: Define how instructions are executed
3. Debug function: Optional logging with handle context
4. Mako preprocessing: Use templates to generate instructions
5. Built-in templates: fork_join, send_event, parallel, conditional
6. User templates: Load from files or strings
7. Context variables: Pass data to templates via mako_context
8. Dynamic control: Enable/disable macros on the fly
9. Validation: Check instructions before running
10. Flexible execution: Run immediately or check-then-run

Key Methods:
- sequencer.run(instruction)  # Execute instruction
- sequencer.check_lisp_instruction(instruction)  # Validate only
- sequencer.run()  # Run previously checked instruction
- sequencer.set_user_macros_from_file(path)  # Load templates
- sequencer.enable_macro(name) / disable_macro(name)  # Control macros
""")

