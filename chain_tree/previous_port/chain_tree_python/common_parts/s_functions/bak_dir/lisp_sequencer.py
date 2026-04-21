import re
import keyword
from typing import Any, Callable, Dict, List, Tuple, Union

class LispSequencer:
    """
    A Lisp-based control flow sequencer for event-driven workflows.
    
    Supports:
    - @void functions (side effects only)
    - ?boolean functions (returns true/false)
    - !control functions (returns CFL_* control codes)
    - Macro expansion for text templates
    
    Function Syntax:
    - No parameters: @fn, ?fn, !fn
    - With parameters: (@fn "arg1" 123), (?fn "arg" 45.6), (!fn "arg1" "arg2" 789)
    - Parameters can be strings or numbers
    - Maximum 10 parameters per function
    
    Macro Syntax:
    - Define: (defmacro name (param1 param2) "template text with $param1 and $param2")
    - Use: (name "value1" "value2")
    - Macros are expanded before tokenization
    
    Primitives:
    - dispatch: Event routing with pattern matching
    - pipeline: Sequential function execution
    - if: Conditional branching
    - cond: Multi-way conditionals
    - debug: Transparent debug message wrapper
    
    Key Features:
    - Stores both original text and tokenized (AST) form during check
    - Execution uses pre-tokenized form for efficiency
    - YAML/JSON compatible: ASTs can be serialized and deserialized
    - Control codes work as both tuples (parser) and lists (JSON/YAML)
    """
    '''
    CONTROL_CODES = {
        "CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", "CFL_RESET", "CFL_DISABLE", "CFL_TERMINATE_SYSTEM",
        "CFL_FUNCTION_RETURN","CFL_FUNCTION_HALT","CFL_FUNCTION_TERMINATE"
    }
    '''
    
    MAX_FUNCTION_PARAMS = 10
    
    def __init__(self, handle, run_function: Callable, debug_function: Callable = None, control_codes: List[str] = None):
        """
        Initialize the LispSequencer.
        
        Args:
            handle: Context handle passed to run_function and debug_function
            run_function: Executes functions - signature: 
                         (handle, func_type, func_name, node, event_id, event_data, params=[])
                         - func_type: '@', '?', or '!'
                         - func_name: function name string
                         - params: list of strings and/or numbers
                         Returns:
                         - @ functions: None (side effects only)
                         - ? functions: boolean (True/False)
                         - ! functions: control code string (e.g., "CFL_CONTINUE")
            debug_function: Outputs debug messages - signature: 
                          (handle, message, node, event_id, event_data)
                          If None, debug messages are silently ignored
        """
        self.handle = handle
        if control_codes is not None:
            self.CONTROL_CODES = control_codes
        else:
            raise ValueError("control_codes is required")
        if "CFL_CONTINUE" not in self.CONTROL_CODES:
            raise ValueError("CFL_CONTINUE is required in control_codes")
        self.run_function = run_function
        self.debug_function = debug_function
        
        # Macro storage: name -> (params_list, template_text)
        self.macros: Dict[str, Tuple[List[str], str]] = {}
    
    def define_macro(self, name: str, params: List[str], template: str) -> Dict[str, Any]:
        """
        Define a macro for text expansion.
        
        Args:
            name: Macro name (must be valid identifier)
            params: List of parameter names
            template: Template text with $param placeholders
            
        Returns:
            Dict with 'valid' and 'errors' keys
        """
        errors = []
        
        # Validate macro name
        if not name or not name[0].isalpha():
            errors.append(f"Macro name '{name}' must start with a letter")
        if not all(c.isalnum() or c == '_' for c in name):
            errors.append(f"Macro name '{name}' must contain only alphanumeric characters and underscore")
        if keyword.iskeyword(name):
            errors.append(f"Macro name '{name}' cannot be a Python keyword")
        
        # Validate parameters
        for param in params:
            if not param or not param[0].isalpha():
                errors.append(f"Parameter '{param}' must start with a letter")
            if not all(c.isalnum() or c == '_' for c in param):
                errors.append(f"Parameter '{param}' must contain only alphanumeric characters and underscore")
        
        # Check for duplicate parameters
        if len(params) != len(set(params)):
            errors.append(f"Macro '{name}' has duplicate parameters")
        
        if errors:
            return {"valid": False, "errors": errors}
        
        # Store the macro
        self.macros[name] = (params, template)
        return {"valid": True, "errors": []}
    
    def expand_macros(self, text: str) -> Dict[str, Any]:
        """
        Expand all macro calls in the text.
        Performs text substitution before tokenization.
        
        Args:
            text: Lisp text possibly containing macro calls
            
        Returns:
            Dict with:
                'valid' (bool): Whether expansion succeeded
                'errors' (list): List of expansion errors
                'expanded_text' (str): Text with macros expanded
                'original_text' (str): Original input text
        """
        try:
            expanded = text
            errors = []
            max_iterations = 100  # Prevent infinite recursion
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                changes_made = False
                
                # Find macro calls by scanning for '(' followed by macro name
                i = 0
                while i < len(expanded):
                    if expanded[i] == '(':
                        # Check if this is a macro call
                        j = i + 1
                        # Skip whitespace
                        while j < len(expanded) and expanded[j].isspace():
                            j += 1
                        
                        # Extract the potential macro name
                        name_start = j
                        while j < len(expanded) and (expanded[j].isalnum() or expanded[j] == '_'):
                            j += 1
                        
                        potential_name = expanded[name_start:j]
                        
                        # Check if this is a defined macro
                        if potential_name in self.macros:
                            params, template = self.macros[potential_name]
                            
                            # Find the matching closing parenthesis
                            paren_count = 1
                            k = j
                            while k < len(expanded) and paren_count > 0:
                                if expanded[k] == '(':
                                    paren_count += 1
                                elif expanded[k] == ')':
                                    paren_count -= 1
                                k += 1
                            
                            if paren_count != 0:
                                errors.append(f"Unbalanced parentheses in macro call to '{potential_name}'")
                                return {"valid": False, "errors": errors, 
                                       "expanded_text": text, "original_text": text}
                            
                            # Extract arguments
                            args_text = expanded[j:k-1].strip()
                            
                            # Parse arguments
                            args = self._parse_macro_args(args_text)
                            
                            if len(args) != len(params):
                                errors.append(
                                    f"Macro '{potential_name}' expects {len(params)} arguments, got {len(args)}"
                                )
                                return {"valid": False, "errors": errors,
                                       "expanded_text": text, "original_text": text}
                            
                            # Perform substitution
                            expanded_macro = template
                            for param, arg in zip(params, args):
                                # Replace $param with argument value
                                expanded_macro = expanded_macro.replace(f'${param}', arg)
                            
                            # Replace the macro call with expanded text
                            expanded = expanded[:i] + expanded_macro + expanded[k:]
                            changes_made = True
                            
                            # Restart from the beginning to handle nested macros
                            break
                    
                    i += 1
                
                if not changes_made:
                    break
            
            if iteration >= max_iterations:
                errors.append("Macro expansion exceeded maximum iterations (possible recursive macros)")
                return {"valid": False, "errors": errors,
                       "expanded_text": text, "original_text": text}
            
            return {"valid": True, "errors": [], 
                   "expanded_text": expanded, "original_text": text}
            
        except Exception as e:
            return {"valid": False, "errors": [str(e)],
                   "expanded_text": text, "original_text": text}
    
    def _parse_macro_args(self, args_text: str) -> List[str]:
        """
        Parse macro arguments from text.
        Handles strings, numbers, symbols, quotes, and nested S-expressions.
        """
        if not args_text or args_text.isspace():
            return []
        
        args = []
        i = 0
        
        while i < len(args_text):
            # Skip whitespace
            while i < len(args_text) and args_text[i].isspace():
                i += 1
            
            if i >= len(args_text):
                break
            
            # String literal
            if args_text[i] == '"':
                j = i + 1
                while j < len(args_text) and args_text[j] != '"':
                    if args_text[j] == '\\':
                        j += 2
                    else:
                        j += 1
                if j < len(args_text):
                    args.append(args_text[i:j+1])
                    i = j + 1
                else:
                    raise SyntaxError("Unterminated string in macro arguments")
            
            # Nested S-expression
            elif args_text[i] == '(':
                paren_count = 1
                j = i + 1
                while j < len(args_text) and paren_count > 0:
                    if args_text[j] == '"':
                        # Skip strings inside the S-expression
                        j += 1
                        while j < len(args_text) and args_text[j] != '"':
                            if args_text[j] == '\\':
                                j += 2
                            else:
                                j += 1
                        j += 1
                    elif args_text[j] == '(':
                        paren_count += 1
                        j += 1
                    elif args_text[j] == ')':
                        paren_count -= 1
                        j += 1
                    else:
                        j += 1
                args.append(args_text[i:j])
                i = j
            
            # Quote
            elif args_text[i] == "'":
                j = i + 1
                while j < len(args_text) and not args_text[j].isspace() and args_text[j] not in '()':
                    j += 1
                args.append(args_text[i:j])
                i = j
            
            # Symbol, function call, or number
            else:
                j = i
                # Check if it starts with @, ?, or ! (function call)
                if args_text[i] in '@?!':
                    j += 1
                    # Continue with the rest of the identifier
                    while j < len(args_text) and (args_text[j].isalnum() or args_text[j] == '_'):
                        j += 1
                else:
                    # Regular symbol or number
                    while j < len(args_text) and not args_text[j].isspace() and args_text[j] not in '()':
                        j += 1
                
                if j > i:
                    args.append(args_text[i:j])
                    i = j
                else:
                    i += 1
        
        return args
    
    def check_lisp_instruction_with_macros(self, lisp_text: str) -> Dict[str, Any]:
        """
        Expand macros and then validate the lisp instruction.
        This is the main entry point for using macros.
        
        Returns:
            Dict with:
                'valid' (bool): Whether the instruction is valid
                'errors' (list): List of validation/expansion errors
                'text' (str): Original lisp text
                'expanded_text' (str): Text after macro expansion
                'ast' (parsed structure): Tokenized/parsed form for execution
                'functions' (list): Functions required by this instruction
        """
        # First, expand macros
        expansion_result = self.expand_macros(lisp_text)
        
        if not expansion_result['valid']:
            return {
                "valid": False,
                "errors": expansion_result['errors'],
                "text": lisp_text,
                "expanded_text": expansion_result['expanded_text'],
                "ast": None,
                "functions": []
            }
        
        expanded_text = expansion_result['expanded_text']
        
        # Now validate the expanded text using the original check_lisp_instruction
        validation_result = self.check_lisp_instruction(expanded_text)
        
        # Add expansion info to the result
        validation_result['expanded_text'] = expanded_text
        if 'text' not in validation_result:
            validation_result['text'] = lisp_text
        
        return validation_result
    
    def check_lisp_instruction(self, lisp_text: str) -> Dict[str, Any]:
        """
        Parse and validate lisp_text sequence.
        Stores both original text and tokenized (AST) form for efficient execution.
        
        Returns:
            Dict with:
                'valid' (bool): Whether the instruction is valid
                'errors' (list): List of validation errors
                'text' (str): Original lisp text
                'ast' (parsed structure): Tokenized/parsed form for execution
                'functions' (list): Functions required by this instruction (e.g., ['@log', '?validate'])
        """
        try:
            # Parse the S-expression
            tokens = self._tokenize(lisp_text)
            ast, _ = self._parse(tokens)
            
            # Validate the AST
            errors = []
            self._validate_expr(ast, errors, context="top-level")
            
            if errors:
                return {"valid": False, "errors": errors, "text": lisp_text, "ast": None, 
                       "functions": []}
            
            # Extract all functions required by this instruction
            functions = self._extract_functions(ast)
            
            # Validate function names are valid Python identifiers
            for func_name in functions:
                func_type = func_name[0]
                name = func_name[1:]
                self._validate_function_name(func_type, name, errors)
            
            if errors:
                return {"valid": False, "errors": errors, "text": lisp_text, "ast": None, 
                       "functions": functions}
            
            return {"valid": True, "errors": [], "text": lisp_text, "ast": ast, 
                   "functions": functions}
            
        except Exception as e:
            return {"valid": False, "errors": [str(e)], "text": lisp_text, "ast": None, 
                   "functions": []}
    
    def run_lisp_instruction(self, node: Any, lisp_instruction: Union[str, List, Dict], 
                            event_id: str, event_data: Any) -> str:
        """
        Execute a lisp instruction using the pre-tokenized form for efficiency.
        
        Args:
            node: Execution context node
            lisp_instruction: Can be:
                - String: lisp text (will be parsed)
                - List: pre-parsed AST (direct execution)
                - Dict: result from check_lisp_instruction (uses 'ast' key)
            event_id: Event identifier
            event_data: Event payload data
            
        Returns:
            Control code string (e.g., "CFL_CONTINUE")
        """
        ast = None
        
        # Handle different input types
        if isinstance(lisp_instruction, dict):
            # Result from check_lisp_instruction - use tokenized form
            if not lisp_instruction.get("valid", False):
                raise ValueError(f"Invalid instruction: {lisp_instruction.get('errors', [])}")
            ast = lisp_instruction["ast"]
        elif isinstance(lisp_instruction, str):
            # Raw text - need to parse
            result = self.check_lisp_instruction(lisp_instruction)
            if not result["valid"]:
                raise ValueError(f"Invalid instruction: {result['errors']}")
            ast = result["ast"]
        else:
            # Assume it's already a parsed AST
            ast = lisp_instruction
        
        # Execute the tokenized AST
        return self._eval(ast, node, event_id, event_data)
    
    def _tokenize(self, text: str) -> List[str]:
        """Convert lisp text into tokens."""
        # Remove comments
        text = re.sub(r';[^\n]*', '', text)
        
        tokens = []
        i = 0
        while i < len(text):
            # Skip whitespace
            if text[i].isspace():
                i += 1
                continue
            
            # Handle string literals
            if text[i] == '"':
                j = i + 1
                while j < len(text) and text[j] != '"':
                    if text[j] == '\\':
                        j += 2  # Skip escaped character
                    else:
                        j += 1
                if j < len(text):
                    tokens.append(text[i:j+1])  # Include quotes
                    i = j + 1
                else:
                    raise SyntaxError("Unterminated string literal")
                continue
            
            # Handle single-character tokens
            if text[i] in '()[]\'':
                tokens.append(text[i])
                i += 1
                continue
            
            # Handle other tokens (symbols, numbers, etc.)
            j = i
            while j < len(text) and not text[j].isspace() and text[j] not in '()[]\'\"':
                j += 1
            tokens.append(text[i:j])
            i = j
        
        return tokens
    
    def _parse(self, tokens: List[str]) -> Tuple[Any, int]:
        """Parse tokens into AST. Returns (ast, tokens_consumed)."""
        if not tokens:
            raise SyntaxError("Unexpected EOF")
        
        token = tokens[0]
        
        # Handle quoted symbols (control codes)
        if token == "'":
            if len(tokens) < 2:
                raise SyntaxError("Quote requires a symbol")
            return ("quote", tokens[1]), 2
        
        # Handle lists/expressions
        if token in '([':
            close = ')' if token == '(' else ']'
            result = []
            pos = 1
            while pos < len(tokens):
                if tokens[pos] in ')]':
                    if tokens[pos] != close:
                        raise SyntaxError(f"Mismatched brackets: expected {close}, got {tokens[pos]}")
                    return result, pos + 1
                sub_expr, consumed = self._parse(tokens[pos:])
                result.append(sub_expr)
                pos += consumed
            raise SyntaxError(f"Unclosed {token}")
        
        if token in ')]':
            raise SyntaxError(f"Unexpected closing bracket {token}")
        
        # Handle atoms
        # Try to parse as number
        if re.match(r'^-?\d+$', token):
            return int(token), 1
        if re.match(r'^-?\d+\.\d+$', token):
            return float(token), 1
        
        # String literal
        if token.startswith('"') and token.endswith('"'):
            # Unescape the string
            return token[1:-1].replace('\\"', '"').replace('\\\\', '\\'), 1
        
        # Symbol
        return token, 1
    
    def _validate_expr(self, expr: Any, errors: List[str], context: str = ""):
        """Validate an expression recursively."""
        if isinstance(expr, (str, int, float)):
            return
        
        if isinstance(expr, (list, tuple)):
            if len(expr) == 0:
                errors.append(f"Empty expression in {context}")
                return
            
            # Handle quote
            if expr[0] == "quote":
                if len(expr) != 2:
                    errors.append(f"Quote must have exactly one argument in {context}")
                return
            
            # Handle primitives
            if expr[0] == "dispatch":
                self._validate_dispatch(expr, errors, context)
            elif expr[0] == "pipeline":
                self._validate_pipeline(expr, errors, context)
            elif expr[0] == "if":
                self._validate_if(expr, errors, context)
            elif expr[0] == "cond":
                self._validate_cond(expr, errors, context)
            elif expr[0] == "debug":
                self._validate_debug(expr, errors, context)
            elif expr[0] in ["and", "or", "not"]:
                self._validate_logical(expr, errors, context)
            else:
                # Function call
                self._validate_function_call(expr, errors, context)
        else:
            errors.append(f"Invalid expression type {type(expr)} in {context}")
    
    def _validate_dispatch(self, expr: Any, errors: List[str], context: str):
        """Validate dispatch expression."""
        if len(expr) < 3:
            errors.append(f"dispatch requires at least 2 arguments in {context}")
            return
        
        # First arg should be event_id or similar
        if not isinstance(expr[1], str):
            errors.append(f"dispatch first argument must be a symbol in {context}")
        
        # Remaining args are (pattern action) pairs
        for i in range(2, len(expr)):
            case = expr[i]
            if not isinstance(case, (list, tuple)) or len(case) != 2:
                errors.append(f"dispatch case must be (pattern action) pair in {context}")
                continue
            
            pattern, action = case
            # Pattern can be string, list of strings, or "default" symbol
            if isinstance(pattern, list):
                for p in pattern:
                    if not isinstance(p, str):
                        errors.append(f"dispatch pattern must be string(s) in {context}")
            elif not isinstance(pattern, str):
                errors.append(f"dispatch pattern must be string or list of strings in {context}")
            
            # Validate action
            self._validate_expr(action, errors, f"{context}/dispatch-case-{i-1}")
    
    def _validate_pipeline(self, expr: Any, errors: List[str], context: str):
        """Validate pipeline expression."""
        if len(expr) < 2:
            errors.append(f"pipeline requires at least 1 step in {context}")
            return
        
        # Each step should be a valid expression
        for i, step in enumerate(expr[1:], 1):
            self._validate_expr(step, errors, f"{context}/pipeline-step-{i}")
    
    def _validate_if(self, expr: Any, errors: List[str], context: str):
        """Validate if expression."""
        if len(expr) not in [3, 4]:
            errors.append(f"if requires 2 or 3 arguments (condition then [else]) in {context}")
            return
        
        condition, then_expr = expr[1], expr[2]
        self._validate_expr(condition, errors, f"{context}/if-condition")
        self._validate_expr(then_expr, errors, f"{context}/if-then")
        
        if len(expr) == 4:
            else_expr = expr[3]
            self._validate_expr(else_expr, errors, f"{context}/if-else")
    
    def _validate_cond(self, expr: Any, errors: List[str], context: str):
        """Validate cond expression."""
        if len(expr) < 2:
            errors.append(f"cond requires at least 1 clause in {context}")
            return
        
        for i, clause in enumerate(expr[1:], 1):
            if not isinstance(clause, (list, tuple)) or len(clause) != 2:
                errors.append(f"cond clause must be (condition action) pair in {context}")
                continue
            
            condition, action = clause
            # Special case for 'else'
            if condition != "else":
                self._validate_expr(condition, errors, f"{context}/cond-{i}-condition")
            self._validate_expr(action, errors, f"{context}/cond-{i}-action")
    
    def _validate_debug(self, expr: Any, errors: List[str], context: str):
        """Validate debug expression."""
        if len(expr) != 3:
            errors.append(f"debug requires exactly 2 arguments (message body) in {context}")
            return
        
        message = expr[1]
        if not isinstance(message, str):
            errors.append(f"debug message must be a string in {context}")
        
        self._validate_expr(expr[2], errors, f"{context}/debug-body")
    
    def _validate_logical(self, expr: Any, errors: List[str], context: str):
        """Validate logical operators (and, or, not)."""
        op = expr[0]
        
        if op == "not":
            if len(expr) != 2:
                errors.append(f"not requires exactly 1 argument in {context}")
                return
            self._validate_expr(expr[1], errors, f"{context}/not-arg")
        else:  # and, or
            if len(expr) < 2:
                errors.append(f"{op} requires at least 1 argument in {context}")
                return
            for i, arg in enumerate(expr[1:], 1):
                self._validate_expr(arg, errors, f"{context}/{op}-arg-{i}")
    
    def _validate_function_call(self, expr: Any, errors: List[str], context: str):
        """Validate function call."""
        if not isinstance(expr, (list, tuple)) or len(expr) == 0:
            errors.append(f"Invalid function call in {context}")
            return
        
        func = expr[0]
        
        # Check if it's a function symbol
        if not isinstance(func, str):
            errors.append(f"Function name must be a symbol in {context}")
            return
        
        # Check for function type prefix
        if not (func.startswith('@') or func.startswith('?') or func.startswith('!')):
            errors.append(f"Function '{func}' must start with @, ?, or ! in {context}")
            return
        
        # Check parameter count
        params = expr[1:]
        if len(params) > self.MAX_FUNCTION_PARAMS:
            errors.append(
                f"Function '{func}' has {len(params)} parameters, "
                f"maximum is {self.MAX_FUNCTION_PARAMS} in {context}"
            )
        
        # Validate each parameter is a string or number
        for i, param in enumerate(params):
            if not isinstance(param, (str, int, float)):
                errors.append(
                    f"Function '{func}' parameter {i+1} must be a string or number, "
                    f"got {type(param).__name__} in {context}"
                )
    
    def _validate_function_name(self, func_type: str, name: str, errors: List[str]):
        """Validate that function name is a valid Python identifier."""
        if not name:
            errors.append(f"Function name cannot be empty")
            return
        
        if not name[0].isalpha() and name[0] != '_':
            errors.append(f"Function name '{name}' must start with a letter or underscore")
        
        if not all(c.isalnum() or c == '_' for c in name):
            errors.append(f"Function name '{name}' must contain only alphanumeric characters and underscore")
        
        if keyword.iskeyword(name):
            errors.append(f"Function name '{name}' cannot be a Python keyword")
    
    def _extract_functions(self, expr: Any) -> List[str]:
        """Extract all function names from an expression."""
        functions = []
        
        if isinstance(expr, str):
            if expr.startswith('@') or expr.startswith('?') or expr.startswith('!'):
                functions.append(expr)
        elif isinstance(expr, (list, tuple)):
            if len(expr) > 0:
                # Check if first element is a function
                if isinstance(expr[0], str):
                    if expr[0].startswith('@') or expr[0].startswith('?') or expr[0].startswith('!'):
                        functions.append(expr[0])
                
                # Recursively extract from all elements
                for item in expr:
                    functions.extend(self._extract_functions(item))
        
        return list(set(functions))  # Remove duplicates
    
    def _eval(self, expr: Any, node: Any, event_id: str, event_data: Any) -> str:
        """Evaluate an expression and return a control code."""
        # Handle atoms
        if isinstance(expr, (int, float)):
            raise ValueError(f"Number {expr} cannot be evaluated as control flow")
        
        if isinstance(expr, str):
            # Bare function call without parameters
            if expr.startswith('@') or expr.startswith('?') or expr.startswith('!'):
                func_type = expr[0]
                func_name = expr[1:]
                result = self.run_function(
                    self.handle, func_type, func_name, node, event_id, event_data, []
                )
                
                if func_type == '@':
                    return "CFL_CONTINUE"
                elif func_type == '?':
                    raise ValueError(f"Boolean function {expr} cannot be used as control flow")
                else:  # '!'
                    return result
            else:
                raise ValueError(f"Symbol '{expr}' cannot be evaluated")
        
        # Handle quotes (control codes)
        if isinstance(expr, (list, tuple)) and len(expr) == 2 and expr[0] == "quote":
            control_code = expr[1]
            if control_code not in self.CONTROL_CODES:
                raise ValueError(f"Invalid control code: {control_code}")
            return control_code
        
        # Handle expressions
        if not isinstance(expr, (list, tuple)) or len(expr) == 0:
            raise ValueError(f"Cannot evaluate {expr}")
        
        op = expr[0]
        
        # Handle primitives
        if op == "dispatch":
            return self._eval_dispatch(expr, node, event_id, event_data)
        elif op == "pipeline":
            return self._eval_pipeline(expr, node, event_id, event_data)
        elif op == "if":
            return self._eval_if(expr, node, event_id, event_data)
        elif op == "cond":
            return self._eval_cond(expr, node, event_id, event_data)
        elif op == "debug":
            return self._eval_debug(expr, node, event_id, event_data)
        elif op in ["and", "or", "not"]:
            raise ValueError(f"Logical operator {op} cannot be used as control flow")
        else:
            # Function call with parameters
            if isinstance(op, str) and (op.startswith('@') or op.startswith('?') or op.startswith('!')):
                func_type = op[0]
                func_name = op[1:]
                params = expr[1:]
                
                result = self.run_function(
                    self.handle, func_type, func_name, node, event_id, event_data, params
                )
                
                if func_type == '@':
                    return "CFL_CONTINUE"
                elif func_type == '?':
                    raise ValueError(f"Boolean function {op} cannot be used as control flow")
                else:  # '!'
                    return result
            else:
                raise ValueError(f"Unknown operation: {op}")
    
    def _eval_dispatch(self, expr: Any, node: Any, event_id: str, event_data: Any) -> str:
        """Evaluate dispatch expression."""
        dispatch_key = expr[1]
        
        # Get the value to dispatch on (typically event_id)
        if dispatch_key == "event_id":
            match_value = event_id
        else:
            # Could extend to support other dispatch keys from event_data
            match_value = event_id
        
        # Try each case
        for case in expr[2:]:
            pattern, action = case
            
            # Check if pattern matches
            matched = False
            if pattern == "default":
                matched = True
            elif isinstance(pattern, str):
                matched = (match_value == pattern)
            elif isinstance(pattern, (list, tuple)):
                matched = any(match_value == p for p in pattern)
            
            if matched:
                return self._eval(action, node, event_id, event_data)
        
        # No match found
        return "CFL_CONTINUE"
    
    def _eval_pipeline(self, expr: Any, node: Any, event_id: str, event_data: Any) -> str:
        """Evaluate pipeline expression."""
        result = "CFL_CONTINUE"
        
        for step in expr[1:]:
            result = self._eval(step, node, event_id, event_data)
            # Pipeline continues until a non-CONTINUE is returned
            if result != "CFL_CONTINUE":
                return result
        
        return result
    
    def _eval_if(self, expr: Any, node: Any, event_id: str, event_data: Any) -> str:
        """Evaluate if expression."""
        condition = expr[1]
        then_expr = expr[2]
        else_expr = expr[3] if len(expr) > 3 else ("quote", "CFL_CONTINUE")
        
        if self._eval_bool(condition, node, event_id, event_data):
            return self._eval(then_expr, node, event_id, event_data)
        else:
            return self._eval(else_expr, node, event_id, event_data)
    
    def _eval_cond(self, expr: Any, node: Any, event_id: str, event_data: Any) -> str:
        """Evaluate cond expression."""
        for clause in expr[1:]:
            condition, action = clause
            
            # Special case for 'else'
            if condition == "else" or self._eval_bool(condition, node, event_id, event_data):
                return self._eval(action, node, event_id, event_data)
        
        return "CFL_CONTINUE"
    
    def _eval_debug(self, expr: Any, node: Any, event_id: str, event_data: Any) -> str:
        """Evaluate debug expression."""
        message = expr[1]
        body = expr[2]
        
        if self.debug_function:
            self.debug_function(self.handle, message, node, event_id, event_data)
        
        return self._eval(body, node, event_id, event_data)
    
    def _eval_bool(self, expr: Any, node: Any, event_id: str, event_data: Any) -> bool:
        """Evaluate a boolean expression."""
        if isinstance(expr, bool):
            return expr
        
        if isinstance(expr, str):
            # Boolean function call without parameters
            if expr.startswith('?'):
                func_name = expr[1:]
                return self.run_function(
                    self.handle, '?', func_name, node, event_id, event_data, []
                )
            raise ValueError(f"Symbol '{expr}' is not a boolean expression")
        
        if not isinstance(expr, (list, tuple)) or len(expr) == 0:
            raise ValueError(f"Invalid boolean expression: {expr}")
        
        op = expr[0]
        
        if op == "and":
            return all(self._eval_bool(arg, node, event_id, event_data) for arg in expr[1:])
        elif op == "or":
            return any(self._eval_bool(arg, node, event_id, event_data) for arg in expr[1:])
        elif op == "not":
            return not self._eval_bool(expr[1], node, event_id, event_data)
        elif isinstance(op, str) and op.startswith('?'):
            # Boolean function call with parameters
            func_name = op[1:]
            params = expr[1:]
            return self.run_function(
                self.handle, '?', func_name, node, event_id, event_data, params
            )
        else:
            raise ValueError(f"Invalid boolean operation: {op}")


# Example usage and tests
if __name__ == "__main__":
    
    # Define control codes
    CONTROL_CODES = [
        "CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", "CFL_RESET", "CFL_DISABLE"
    ]
    
    def run_fn(handle, func_type, func_name, node, event_id, event_data, params=[]):
        """Execute a function."""
        params_str = f" with params {params}" if params else ""
        print(f"  → Running {func_type}{func_name}{params_str}")
        
        if func_type == '@':
            print(f"    Side effect executed")
        elif func_type == '?':
            if func_name == "check_inventory":
                return True
            return True
        elif func_type == '!':
            return "CFL_CONTINUE"
    
    def debug_fn(handle, message, node, event_id, event_data):
        """Output debug messages."""
        print(f"  [DEBUG] {message}")
    
    # Create sequencer
    seq = LispSequencer("my-handle", run_fn, debug_fn, control_codes=CONTROL_CODES)
    
    print("=" * 70)
    print("MACRO EXPANSION EXAMPLES")
    print("=" * 70)
    
    # Example 1: Define a simple logging pipeline macro
    print("\n--- Example 1: Simple Macro ---")
    
    seq.define_macro("log_pipeline", ["msg", "func"], """
    (pipeline 
      (@log $msg)
      $func
      'CFL_CONTINUE)
    """)
    
    code_with_macro = """
    (dispatch event_id
      ("order.process"
       (log_pipeline "Processing order" !process_order))
      (default 'CFL_DISABLE))
    """
    
    result = seq.check_lisp_instruction_with_macros(code_with_macro)
    print(f"Valid: {result['valid']}")
    print(f"Original text: {code_with_macro.strip()}")
    print(f"Expanded text: {result['expanded_text'].strip()}")
    
    if result['valid']:
        print("\nExecuting:")
        code = seq.run_lisp_instruction("node1", result, "order.process", {})
        print(f"Result: {code}")
    
    # Example 2: Macro with multiple parameters
    print("\n--- Example 2: Macro with Multiple Parameters ---")
    
    seq.define_macro("validated_pipeline", ["check_func", "action_func", "log_msg"], """
    (if $check_func
        (pipeline 
          (@log $log_msg)
          $action_func
          'CFL_CONTINUE)
        'CFL_HALT)
    """)
    
    code_with_macro2 = """
    (dispatch event_id
      ("payment.process"
       (validated_pipeline ?check_balance !process_payment "Payment validated"))
      (default 'CFL_DISABLE))
    """
    
    result2 = seq.check_lisp_instruction_with_macros(code_with_macro2)
    print(f"Valid: {result2['valid']}")
    print(f"\nExpanded text:\n{result2['expanded_text']}")
    
    if result2['valid']:
        print("\nExecuting:")
        code = seq.run_lisp_instruction("node2", result2, "payment.process", {})
        print(f"Result: {code}")
    
    # Example 3: Nested macros
    print("\n--- Example 3: Nested Macros ---")
    
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
    
    code_with_nested = """
    (dispatch event_id
      ("data.validate"
       (full_pipeline ?validate_schema !process_data))
      (default 'CFL_DISABLE))
    """
    
    result3 = seq.check_lisp_instruction_with_macros(code_with_nested)
    print(f"Valid: {result3['valid']}")
    print(f"\nExpanded text:\n{result3['expanded_text']}")
    
    if result3['valid']:
        print("\nExecuting:")
        code = seq.run_lisp_instruction("node3", result3, "data.validate", {})
        print(f"Result: {code}")
    
    # Example 4: Macro with string parameters
    print("\n--- Example 4: Macro with String Parameters ---")
    
    seq.define_macro("notify_pipeline", ["recipient", "message"], """
    (pipeline
      (@send_notification $recipient)
      (@log $message)
      'CFL_CONTINUE)
    """)
    
    code_with_strings = """
    (dispatch event_id
      ("alert.send"
       (notify_pipeline "admin@company.com" "Alert sent to admin"))
      (default 'CFL_DISABLE))
    """
    
    result4 = seq.check_lisp_instruction_with_macros(code_with_strings)
    print(f"Valid: {result4['valid']}")
    print(f"\nExpanded text:\n{result4['expanded_text']}")
    
    if result4['valid']:
        print("\nExecuting:")
        code = seq.run_lisp_instruction("node4", result4, "alert.send", {})
        print(f"Result: {code}")
    
    # Example 5: Error handling - undefined macro
    print("\n--- Example 5: Error - Undefined Macro ---")
    
    code_with_undefined = """
    (dispatch event_id
      ("test.event"
       (undefined_macro "arg1"))
      (default 'CFL_DISABLE))
    """
    
    result5 = seq.check_lisp_instruction_with_macros(code_with_undefined)
    print(f"Valid: {result5['valid']}")
    if not result5['valid']:
        print("Errors:", result5['errors'])
    
    # Example 6: Error handling - wrong number of arguments
    print("\n--- Example 6: Error - Wrong Number of Arguments ---")
    
    code_with_wrong_args = """
    (dispatch event_id
      ("test.event"
       (log_pipeline "only_one_arg"))
      (default 'CFL_DISABLE))
    """
    
    result6 = seq.check_lisp_instruction_with_macros(code_with_wrong_args)
    print(f"Valid: {result6['valid']}")
    if not result6['valid']:
        print("Errors:", result6['errors'])
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("✓ Macros defined with define_macro(name, params, template)")
    print("✓ Macro expansion uses $param placeholder substitution")
    print("✓ Macros expand BEFORE tokenization (pure text replacement)")
    print("✓ Supports nested macro calls")
    print("✓ Preserves all existing check_lisp_instruction functionality")
    print("✓ Use check_lisp_instruction_with_macros() for macro support")
    print("=" * 70)