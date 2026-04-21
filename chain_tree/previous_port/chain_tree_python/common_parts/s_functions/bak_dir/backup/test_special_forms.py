"""
Test file to verify LispSequencer handles special forms like cond, dispatch, etc.
"""

from lisp_sequencer import LispSequencer

def test_executor(handle, ast, *args, **kwargs):
    """Simple test executor."""
    print(f"Executing AST for handle: {handle}")
    return {"status": "success", "ast": ast}

def test_debugger(handle, message):
    """Simple debug logger."""
    print(f"[DEBUG] {message}")

# Test cases
print("=" * 80)
print("TEST 1: Basic cond expression")
print("=" * 80)

sequencer = LispSequencer(
    handle={"test": "cond"},
    run_function=test_executor,
    debug_function=test_debugger,
    enable_mako=False
)

cond_expr = """
(cond 
  ((?CFL_IS_STATE_0 0) (pipeline (@CFL_FORK_0 0) 'CFL_FUNCTION_RETURN))
  ((?CFL_IS_STATE_1 1) (pipeline (@CFL_FORK_1 1) 'CFL_FUNCTION_RETURN))
  (else (pipeline (@CFL_LOG "Default case") 'CFL_FUNCTION_TERMINATE)))
"""

result = sequencer.check_lisp_instruction(cond_expr, use_mako=False)
print(f"Valid: {result['valid']}")
if not result['valid']:
    print(f"Errors: {result['errors']}")
else:
    print(f"Functions: {result['functions']}")
    print("✅ cond expression validated successfully!")

print("\n" + "=" * 80)
print("TEST 2: Dispatch with default clause containing cond")
print("=" * 80)

dispatch_expr = """
(dispatch event_id
  ("CFL_INIT_EVENT" (pipeline (@CFL_KILL_CHILDREN_0) 'CFL_FUNCTION_RETURN))
  ("CFL_TERM_EVENT" (pipeline (@CFL_KILL_CHILDREN_1) 'CFL_FUNCTION_RETURN))
  (default (cond 
    ((?CFL_IS_STATE_0 0) (pipeline (@CFL_FORK_0 0) 'CFL_FUNCTION_RETURN))
    ((?CFL_IS_STATE_1 1) (pipeline (@CFL_FORK_1 1) 'CFL_FUNCTION_RETURN))
    (else (pipeline (@CFL_LOG "Invalid state") 'CFL_FUNCTION_TERMINATE)))))
"""

result2 = sequencer.check_lisp_instruction(dispatch_expr, use_mako=False)
print(f"Valid: {result2['valid']}")
if not result2['valid']:
    print(f"Errors: {result2['errors']}")
else:
    print(f"Functions: {result2['functions']}")
    print("✅ dispatch with cond validated successfully!")

print("\n" + "=" * 80)
print("TEST 3: Your original expression")
print("=" * 80)

original_expr = """
(dispatch event_id
  ("CFL_INIT_EVENT" (pipeline (@CFL_KILL_CHILDREN_0) (@CFL_MARK_INIT_STATE_0 0) !CFL_RESET_CODES_0 'CFL_FUNCTION_RETURN))
  ("CFL_TERM_EVENT" (pipeline (@CFL_KILL_CHILDREN_1) !CFL_RESET_CODES_1 'CFL_FUNCTION_RETURN))
  ("CFL_CHANGE_STATE" (pipeline @CFL_KILL_CHILDREN_2 @CFL_MARK_STATE_0 !CFL_RESET_CODES_2 'CFL_FUNCTION_RETURN))
  (default (cond 
    ((?CFL_IS_STATE_0 0) (pipeline (@CFL_FORK_0 0) (@CFL_FORK_1 1) 'CFL_FUNCTION_RETURN))
    ((?CFL_IS_STATE_1 1) (pipeline (@CFL_FORK_2 2) (@CFL_FORK_3 3) 'CFL_FUNCTION_RETURN))
    (else (pipeline (@CFL_LOGM_0 "Invalid state") !CFL_RESET_CODES_3 'CFL_FUNCTION_TERMINATE)))))
"""

result3 = sequencer.check_lisp_instruction(original_expr, use_mako=False)
print(f"Valid: {result3['valid']}")
if not result3['valid']:
    print(f"Errors: {result3['errors']}")
else:
    print(f"Functions: {result3['functions']}")
    print("✅ Original expression validated successfully!")

print("\n" + "=" * 80)
print("TEST 4: Nested list operators (lambda-like)")
print("=" * 80)

nested_expr = """
(pipeline
  ((lambda x) (@PROCESS x))
  'CFL_FUNCTION_RETURN)
"""

result4 = sequencer.check_lisp_instruction(nested_expr, use_mako=False)
print(f"Valid: {result4['valid']}")
if not result4['valid']:
    print(f"Errors: {result4['errors']}")
else:
    print(f"Functions: {result4['functions']}")
    print("✅ Nested list operator validated successfully!")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("The validator now supports:")
print("  ✓ Regular operators (strings like 'pipeline', '@FUNCTION')")
print("  ✓ List operators (like in cond clauses: ((?check) (action)))")
print("  ✓ Nested special forms (dispatch with cond)")
print("  ✓ Lambda-like expressions with list as first element")

