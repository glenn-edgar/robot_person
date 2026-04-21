from mako.template import Template
from mako.lookup import TemplateLookup
import json
import os
import re
from typing import Dict, Any, List, Tuple, Optional, Set, Union, Callable


class LispSequencer:
    """
    Sequencer for Lisp-style instructions with configurable Mako template preprocessing support.
    Executes sequences using provided run_function and debug_function with a context handle.
    
    TOKEN STREAM ARCHITECTURE:
    - check_instruction(): Preprocesses with Mako and generates token stream
    - run(): Accepts token stream, parses to AST, and executes
    """
    
    # Internal macro definitions
    INTERNAL_MACROS = {
        'send_event': """
<%def name="send_event(event_name, data_var)">
(@SEND_EVENT "${event_name}" "${f'json.dumps({data_var})'.replace('"', '\\\\"')}")
</%def>
""",
        'fork_join': """
<%def name="fork_join(branch_id)">
(@CFL_FORK ${branch_id}) (!CFL_JOIN ${branch_id})
</%def>
""",
        'conditional': """
<%def name="conditional(condition, true_action, false_action='')">
(?IF "${condition}" ${true_action}${' ' + false_action if false_action else ''})
</%def>
""",
        'parallel': """
<%def name="parallel(*branch_ids)">
% for bid in branch_ids:
(@CFL_FORK ${bid})
% endfor
% for bid in branch_ids:
(!CFL_JOIN ${bid})
% endfor
</%def>
"""
    }

    def __init__(self, 
                 handle: Any,
                 run_function: Callable,
                 debug_function: Optional[Callable] = None,
                 control_codes: Optional[List[str]] = None,
                 user_macro_file: Optional[Union[str, List[str]]] = None,
                 enable_mako: bool = True,
                 enabled_macros: Optional[Set[str]] = None):
        """
        Initialize sequencer with execution context and configurable options.
        
        Args:
            handle: Context handle passed to run_function and debug_function
            run_function: Callable that executes instructions, receives (handle, ast, *args)
            debug_function: Optional callable for debug output, receives (handle, message)
            control_codes: Optional list of control code strings
            user_macro_file: Path to file(s) containing user-defined Mako templates.
                           Can be a single string path or list of paths.
            enable_mako: Whether Mako preprocessing is enabled by default
            enabled_macros: Set of macro names to enable. If None, all internal macros are enabled.
                          Options: 'send_event', 'fork_join', 'conditional', 'parallel'
        """
        # Store execution context
        self.handle = handle
        self.run_function = run_function
        self.debug_function = debug_function
        self.control_codes = control_codes if control_codes is not None else []
        
        # Mako template configuration
        self.user_macros = ""
        self.enable_mako_default = enable_mako
        self.user_macro_files = []  # Track loaded files
        
        # Determine which internal macros to enable
        if enabled_macros is None:
            self.enabled_macros = set(self.INTERNAL_MACROS.keys())
        else:
            # Validate that requested macros exist
            invalid_macros = enabled_macros - set(self.INTERNAL_MACROS.keys())
            if invalid_macros:
                raise ValueError(f"Unknown macros requested: {invalid_macros}")
            self.enabled_macros = enabled_macros
        
        # Load user macros if provided
        if user_macro_file:
            self._load_user_macro_files(user_macro_file)
        
        # Valid function prefixes
        self.valid_prefixes = {'@', '!', '?', "'"}
        
        # Reserved keywords
        self.reserved_keywords = {
            'CFL_KILL_CHILDREN', 'CFL_FORK', 'CFL_JOIN', 'CFL_WAIT',
            'CFL_TERMINATE', 'CFL_FUNCTION_TERMINATE', 'pipeline'
        }
        
        # Execution state - NOW STORES TOKEN STREAM instead of AST
        self.current_tokens = None
        self.current_text = None
    
    def _debug_log(self, message: str) -> None:
        """
        Log debug message if debug_function is available.
        
        Args:
            message: Debug message to log
        """
        if self.debug_function is not None:
            self.debug_function(self.handle, message)
    
    def _load_user_macro_files(self, files: Union[str, List[str]]) -> None:
        """
        Load user macro files.
        
        Args:
            files: Single file path or list of file paths
        """
        if isinstance(files, str):
            files = [files]
        
        macro_parts = []
        for filepath in files:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    content = f.read()
                    macro_parts.append(content)
                    if filepath not in self.user_macro_files:
                        self.user_macro_files.append(filepath)
                    self._debug_log(f"Loaded macro file: {filepath}")
        
        if macro_parts:
            self.user_macros = '\n\n'.join(macro_parts)
    
    def enable_macro(self, macro_name: str) -> bool:
        """
        Enable a specific internal macro.
        
        Args:
            macro_name: Name of macro to enable
            
        Returns:
            True if macro exists and was enabled, False otherwise
        """
        if macro_name in self.INTERNAL_MACROS:
            self.enabled_macros.add(macro_name)
            self._debug_log(f"Enabled macro: {macro_name}")
            return True
        return False
    
    def disable_macro(self, macro_name: str) -> bool:
        """
        Disable a specific internal macro.
        
        Args:
            macro_name: Name of macro to disable
            
        Returns:
            True if macro was disabled, False if it wasn't enabled
        """
        if macro_name in self.enabled_macros:
            self.enabled_macros.remove(macro_name)
            self._debug_log(f"Disabled macro: {macro_name}")
            return True
        return False
    
    def set_mako_default(self, enabled: bool) -> None:
        """
        Set whether Mako preprocessing is enabled by default.
        
        Args:
            enabled: True to enable Mako by default, False to disable
        """
        self.enable_mako_default = enabled
        self._debug_log(f"Mako default set to: {enabled}")
    
    def get_enabled_macros(self) -> List[str]:
        """
        Get list of currently enabled internal macros.
        
        Returns:
            List of enabled macro names
        """
        return sorted(list(self.enabled_macros))
    
    def get_available_macros(self) -> List[str]:
        """
        Get list of all available internal macros.
        
        Returns:
            List of all internal macro names
        """
        return sorted(list(self.INTERNAL_MACROS.keys()))
    
    def get_loaded_macro_files(self) -> List[str]:
        """
        Get list of loaded user macro files.
        
        Returns:
            List of file paths that have been loaded
        """
        return self.user_macro_files.copy()
    
    def _build_macro_string(self) -> str:
        """
        Build the complete macro string from enabled macros.
        
        Returns:
            Combined macro definitions string
        """
        macro_parts = []
        
        # Add enabled internal macros
        for macro_name in sorted(self.enabled_macros):
            if macro_name in self.INTERNAL_MACROS:
                macro_parts.append(self.INTERNAL_MACROS[macro_name])
        
        # Add user macros
        if self.user_macros:
            macro_parts.append(self.user_macros)
        
        return '\n'.join(macro_parts)
    
    def preprocess_with_mako(self, lisp_text: str, 
                            context: Optional[Dict] = None,
                            additional_macro_files: Optional[Union[str, List[str]]] = None) -> str:
        """
        Preprocess lisp_text through Mako template engine.
        
        Args:
            lisp_text: Raw instruction text with Mako macros
            context: Dictionary of variables available to Mako templates
            additional_macro_files: Optional additional macro file(s) to include for this call only
            
        Returns:
            Processed lisp text ready for tokenization
        """
        if context is None:
            context = {}
        
        # Build macro string from enabled macros
        macros_string = self._build_macro_string()
        
        # Load additional macro files if provided (temporary, just for this call)
        additional_macros = ""
        if additional_macro_files:
            files = additional_macro_files if isinstance(additional_macro_files, list) else [additional_macro_files]
            additional_parts = []
            for filepath in files:
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        additional_parts.append(f.read())
                    self._debug_log(f"Loaded additional macro file: {filepath}")
            if additional_parts:
                additional_macros = '\n\n'.join(additional_parts)
        
        # Combine macros and the actual text
        full_template = f"""
{macros_string}

{additional_macros}

{lisp_text}
"""
        
        try:
            # Create Mako template
            template = Template(full_template)
            
            # Render with provided context
            processed = template.render(**context)
            
            # Clean up extra whitespace while preserving structure
            processed = ' '.join(processed.split())
            
            self._debug_log(f"Mako preprocessing completed successfully")
            return processed
            
        except Exception as e:
            error_msg = f"Mako preprocessing error: {e}"
            self._debug_log(error_msg)
            raise ValueError(error_msg)
    
    def _tokenize(self, lisp_text: str) -> List[str]:
        """
        Tokenize Lisp expression into list of tokens.
        Properly handles quoted strings with spaces.
        
        Args:
            lisp_text: Lisp expression string
            
        Returns:
            List of tokens
            
        Example:
            Input:  '(pipeline (@CFL_LOGM "Invalid state") \'CFL_RETURN)'
            Output: ['(', 'pipeline', '(', '@CFL_LOGM', '"Invalid state"', ')', "'CFL_RETURN", ')']
        """
        tokens = []
        i = 0
        
        while i < len(lisp_text):
            char = lisp_text[i]
            
            # Skip whitespace
            if char.isspace():
                i += 1
                continue
            
            # Handle opening parenthesis
            if char == '(':
                tokens.append('(')
                i += 1
                continue
            
            # Handle closing parenthesis
            if char == ')':
                tokens.append(')')
                i += 1
                continue
            
            # Handle double-quoted strings (with spaces)
            if char == '"':
                j = i + 1
                # Find closing quote, handling escaped quotes
                while j < len(lisp_text):
                    if lisp_text[j] == '"' and (j == i + 1 or lisp_text[j-1] != '\\'):
                        break
                    j += 1
                
                if j < len(lisp_text):
                    # Include quotes in token
                    tokens.append(lisp_text[i:j+1])
                    i = j + 1
                else:
                    # Unterminated string - include what we have
                    tokens.append(lisp_text[i:])
                    break
                continue
            
            # Handle regular tokens (symbols, numbers, etc.)
            j = i
            while j < len(lisp_text) and not lisp_text[j].isspace() and lisp_text[j] not in '()"':
                j += 1
            
            if j > i:
                tokens.append(lisp_text[i:j])
                i = j
            else:
                # Should not happen, but advance to avoid infinite loop
                i += 1
        
        return tokens
    
    def _parse(self, tokens: List[str], index: int = 0) -> Tuple[Any, int]:
        """
        Parse tokens into AST (Abstract Syntax Tree).
        
        Args:
            tokens: List of tokens
            index: Current position in token list
            
        Returns:
            Tuple of (parsed expression, next index)
        """
        if index >= len(tokens):
            raise ValueError("Unexpected end of expression")
        
        token = tokens[index]
        
        # Handle opening parenthesis - start of list
        if token == '(':
            index += 1
            expr = []
            
            while index < len(tokens) and tokens[index] != ')':
                sub_expr, index = self._parse(tokens, index)
                expr.append(sub_expr)
            
            if index >= len(tokens):
                raise ValueError("Missing closing parenthesis")
            
            index += 1  # Skip closing parenthesis
            return expr, index
        
        # Handle closing parenthesis - error
        elif token == ')':
            raise ValueError("Unexpected closing parenthesis")
        
        # Handle atoms (numbers, strings, symbols)
        else:
            # Try to parse as number
            try:
                if '.' in token:
                    return float(token), index + 1
                else:
                    return int(token), index + 1
            except ValueError:
                pass
            
            # Handle quoted strings
            if token.startswith('"') and token.endswith('"'):
                return token[1:-1], index + 1
            
            # Return as symbol
            return token, index + 1
    
    def _validate_expr(self, expr: Any, errors: List[str], context: str = "") -> None:
        """
        Validate parsed expression recursively.
        
        Args:
            expr: Parsed expression (AST node)
            errors: List to accumulate errors
            context: Context string for error messages
        """
        if isinstance(expr, list):
            if len(expr) == 0:
                errors.append(f"Empty expression at {context}")
                return
            
            # First element should be an operator/function
            operator = expr[0]
            
            if isinstance(operator, str):
                # Check if it's a valid function call
                if operator.startswith(('@', '!', '?', "'")):
                    # Validate function name
                    if len(operator) > 1:
                        func_name = operator[1:]
                        if not func_name.replace('_', '').replace('-', '').isalnum():
                            errors.append(f"Invalid function name: {operator} at {context}")
                
                # Recursively validate sub-expressions
                for i, sub_expr in enumerate(expr[1:], 1):
                    self._validate_expr(sub_expr, errors, f"{context}[{i}]")
            
            elif isinstance(operator, list):
                # Special forms where first element can be a list
                # Examples: (cond ((condition) (action)) ...), ((lambda ...) args)
                # These are valid in Lisp - validate the operator as an expression
                self._validate_expr(operator, errors, f"{context}[0]")
                
                # Recursively validate remaining sub-expressions
                for i, sub_expr in enumerate(expr[1:], 1):
                    self._validate_expr(sub_expr, errors, f"{context}[{i}]")
            
            else:
                errors.append(f"Invalid operator type at {context}: expected string or list, got {type(operator)}")
        
        elif isinstance(expr, (int, float, str)):
            # Atoms are valid
            pass
        
        else:
            errors.append(f"Invalid expression type at {context}: {type(expr)}")
    
    def _extract_functions(self, expr: Any) -> List[str]:
        """
        Extract all function names from AST.
        
        Args:
            expr: Parsed expression (AST node)
            
        Returns:
            List of unique function names
        """
        functions = set()
        
        def extract_recursive(node):
            if isinstance(node, list):
                if len(node) > 0:
                    operator = node[0]
                    if isinstance(operator, str) and operator.startswith(('@', '!', '?', "'")):
                        functions.add(operator)
                    
                    # Recurse into sub-expressions
                    for sub_node in node[1:]:
                        extract_recursive(sub_node)
        
        extract_recursive(expr)
        return sorted(list(functions))
    
    def _validate_function_name(self, func_type: str, name: str, errors: List[str]) -> None:
        """
        Validate that function name is a valid Python identifier.
        
        Args:
            func_type: Function prefix (@, !, ?, ')
            name: Function name without prefix
            errors: List to accumulate errors
        """
        if not name:
            errors.append(f"Empty function name for type '{func_type}'")
            return
        
        # Check if it's a reserved keyword
        full_name = name
        if full_name in self.reserved_keywords:
            return  # Reserved keywords are valid
        
        # Check if it's a valid identifier (allowing underscores and hyphens)
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*$', name):
            errors.append(f"Invalid function name: {func_type}{name} (must be valid identifier)")
    
    def check_lisp_instruction(self, lisp_text: str, 
                              use_mako: Optional[bool] = None, 
                              mako_context: Optional[Dict] = None,
                              additional_macro_files: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Parse and validate lisp_text sequence with optional Mako preprocessing.
        GENERATES TOKEN STREAM - parsing happens later in run().
        
        Args:
            lisp_text: Raw instruction text (may contain Mako templates)
            use_mako: Whether to preprocess with Mako. If None, uses default setting.
            mako_context: Variables available to Mako templates
            additional_macro_files: Optional additional macro file(s) to include for this call only
            
        Returns:
            Dict with:
                'valid' (bool): Whether the instruction tokens are valid
                'errors' (list): List of validation errors
                'text' (str): Processed lisp text (after Mako if enabled)
                'original_text' (str): Original input text
                'tokens' (list): Token stream for execution (pass to run())
                'functions' (list): Functions required by this instruction (e.g., ['@log', '?validate'])
                'mako_used' (bool): Whether Mako preprocessing was used
        """
        # Use default if not specified
        if use_mako is None:
            use_mako = self.enable_mako_default
        
        self._debug_log(f"Checking Lisp instruction (Mako: {use_mako})")
        
        try:
            # Preprocess with Mako if requested
            if use_mako:
                processed_text = self.preprocess_with_mako(lisp_text, mako_context, additional_macro_files)
            else:
                processed_text = lisp_text
            
            # Generate TOKEN STREAM (not AST)
            tokens = self._tokenize(processed_text)
            
            # For validation purposes only, parse to AST
            # This ensures the tokens are valid before we return them
            ast, _ = self._parse(tokens)
            
            # Validate the AST
            errors = []
            self._validate_expr(ast, errors, context="top-level")
            
            if errors:
                self._debug_log(f"Validation errors: {errors}")
                return {
                    "valid": False, 
                    "errors": errors, 
                    "text": processed_text,
                    "original_text": lisp_text,
                    "tokens": None,  # Don't return invalid tokens
                    "functions": [],
                    "mako_used": use_mako
                }
            
            # Extract all functions required by this instruction
            functions = self._extract_functions(ast)
            
            # Validate function names are valid Python identifiers
            for func_name in functions:
                if len(func_name) > 0:
                    func_type = func_name[0]
                    name = func_name[1:]
                    self._validate_function_name(func_type, name, errors)
            
            if errors:
                self._debug_log(f"Function validation errors: {errors}")
                return {
                    "valid": False, 
                    "errors": errors, 
                    "text": processed_text,
                    "original_text": lisp_text,
                    "tokens": None,  # Don't return invalid tokens
                    "functions": functions,
                    "mako_used": use_mako
                }
            
            self._debug_log(f"Token stream generated successfully. Functions: {functions}")
            
            # Store token stream for execution (instead of AST)
            self.current_tokens = tokens
            self.current_text = processed_text
            
            return {
                "valid": True, 
                "errors": [], 
                "text": processed_text,
                "original_text": lisp_text,
                "tokens": tokens,  # Return token stream
                "functions": functions,
                "mako_used": use_mako
            }
            
        except Exception as e:
            error_msg = str(e)
            self._debug_log(f"Exception during instruction check: {error_msg}")
            return {
                "valid": False, 
                "errors": [error_msg], 
                "text": lisp_text,
                "original_text": lisp_text,
                "tokens": None,
                "functions": [],
                "mako_used": use_mako
            }
    
    def check(self, lisp_text: str,
              use_mako: Optional[bool] = None,
              mako_context: Optional[Dict] = None,
              additional_macro_files: Optional[Union[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Parse, validate, and generate token stream for a Lisp instruction.
        
        TEMPLATE PROCESSING AND TOKENIZATION HAPPEN HERE:
        - Mako templates are expanded (if use_mako=True)
        - Text is tokenized into token stream
        - Token stream is validated by test-parsing
        - Token stream is cached internally for later run() call
        
        Args:
            lisp_text: Raw instruction text (may contain Mako templates)
            use_mako: Whether to preprocess with Mako. If None, uses default setting.
            mako_context: Variables available to Mako templates
            additional_macro_files: Optional additional macro file(s) to include
            
        Returns:
            Dict with:
                'valid' (bool): Whether the instruction is valid
                'errors' (list): List of validation errors
                'text' (str): Processed text (after Mako expansion)
                'original_text' (str): Original input text
                'tokens' (list): Token stream for execution
                'functions' (list): Function names found in instruction
                'mako_used' (bool): Whether Mako preprocessing was used
                
        Example:
            # Check instruction with Mako templates
            result = sequencer.check(
                "<%fork_join(0)%> (@PROCESS)",
                use_mako=True,
                mako_context={'branch': 0}
            )
            
            if result['valid']:
                print(f"Ready to run. Functions: {result['functions']}")
                print(f"Tokens: {result['tokens']}")
                output = sequencer.run()  # Execute using cached tokens
                # OR
                output = sequencer.run(result['tokens'])  # Pass tokens explicitly
            else:
                print(f"Invalid: {result['errors']}")
        """
        return self.check_lisp_instruction(lisp_text, use_mako, mako_context, additional_macro_files)
    
    def run(self, tokens: Optional[List[str]] = None, **kwargs) -> Any:
        """Execute token stream - calls run_function for each individual function."""
        # Use provided tokens or cached tokens
        if tokens is not None:
            token_stream = tokens
            self.current_tokens = tokens
        elif self.current_tokens is not None:
            token_stream = self.current_tokens
        else:
            raise ValueError("No tokens available")
        
        self._debug_log(f"Executing token stream: {len(token_stream)} tokens")
        
        # Parse tokens to AST
        ast, _ = self._parse(token_stream)
        
        # Extract context parameters
        node = kwargs.get('node')
        event_id = kwargs.get('event_id')
        event_data = kwargs.get('event_data')
        
        # Execute the AST
        return self._execute_ast(ast, node, event_id, event_data)

    def _execute_ast(self, ast, node, event_id, event_data):
        """Execute an AST node - handles both control structures and functions."""
        if not isinstance(ast, list) or len(ast) == 0:
            raise ValueError(f"Invalid AST: {ast}")
        
        first_element = ast[0]
        
        # Check if it's a function call (starts with valid prefix)
        if isinstance(first_element, str) and len(first_element) > 0 and first_element[0] in self.valid_prefixes:
            # It's a function - call run_function
            function_type = first_element[0]
            function_name = first_element[1:]
            params = ast[1:] if len(ast) > 1 else None
            
            return self.run_function(
                self.handle,
                function_type,
                function_name,
                node,
                event_id,
                event_data,
                params
            )
        
        # Otherwise it's a control structure - iterate through children
        else:
            self._debug_log(f"Control structure: {first_element}, executing {len(ast)-1} children")
            result = None
            for sub_expr in ast[1:]:
                result = self._execute_ast(sub_expr, node, event_id, event_data)
                # Return codes handled by run_function, not here
            return result

    def _execute_function(self, ast, node, event_id, event_data):
        """Execute a single function by unpacking AST and calling run_function."""
        if not isinstance(ast, list) or len(ast) == 0:
            raise ValueError(f"Invalid function AST: {ast}")
        
        function_with_prefix = ast[0]
        
        if not isinstance(function_with_prefix, str) or len(function_with_prefix) == 0:
            raise ValueError(f"Invalid function: {function_with_prefix}")
        
        if function_with_prefix[0] not in {'@', '!', '?', "'"}:
            raise ValueError(f"Invalid function prefix: {function_with_prefix}")
        
        function_type = function_with_prefix[0]
        function_name = function_with_prefix[1:]
        params = ast[1:] if len(ast) > 1 else None
        
        # Call run_function with unpacked parameters
        return self.run_function(
            self.handle,
            function_type,
            function_name,
            node,
            event_id,
            event_data,
            params
        )
    
    def set_user_macros_from_file(self, filepath: Union[str, List[str]]) -> bool:
        """
        Load user-defined macros from file(s). Replaces existing user macros.
        
        Args:
            filepath: Path to macro definition file or list of paths
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.user_macros = ""
            self.user_macro_files = []
            self._load_user_macro_files(filepath)
            return True
        except Exception as e:
            self._debug_log(f"Error loading macro files: {e}")
            return False
    
    def add_user_macros_from_file(self, filepath: Union[str, List[str]]) -> bool:
        """
        Add user-defined macros from file(s). Appends to existing user macros.
        
        Args:
            filepath: Path to macro definition file or list of paths
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._load_user_macro_files(filepath)
            return True
        except Exception as e:
            self._debug_log(f"Error adding macro files: {e}")
            return False
    
    def set_user_macros_from_string(self, macro_string: str) -> None:
        """
        Set user-defined macros from a string. Replaces existing user macros.
        
        Args:
            macro_string: Mako macro definitions as string
        """
        self.user_macros = macro_string
        self.user_macro_files = []
        self._debug_log("User macros set from string")
    
    def add_user_macros_from_string(self, macro_string: str) -> None:
        """
        Add user-defined macros from a string. Appends to existing user macros.
        
        Args:
            macro_string: Mako macro definitions as string
        """
        if self.user_macros:
            self.user_macros += '\n\n' + macro_string
        else:
            self.user_macros = macro_string
        self._debug_log("User macros added from string")
    
    def clear_user_macros(self) -> None:
        """
        Clear all user-defined macros.
        """
        self.user_macros = ""
        self.user_macro_files = []
        self._debug_log("User macros cleared")
    
    def get_processed_text(self, lisp_text: str, 
                          use_mako: Optional[bool] = None, 
                          mako_context: Optional[Dict] = None,
                          additional_macro_files: Optional[Union[str, List[str]]] = None) -> str:
        """
        Get only the preprocessed text without validation.
        
        Args:
            lisp_text: Raw instruction text
            use_mako: Whether to preprocess with Mako. If None, uses default setting.
            mako_context: Variables available to Mako templates
            additional_macro_files: Optional additional macro file(s) to include
            
        Returns:
            Processed text string
        """
        if use_mako is None:
            use_mako = self.enable_mako_default
            
        if use_mako:
            return self.preprocess_with_mako(lisp_text, mako_context, additional_macro_files)
        else:
            return lisp_text
    
    def run_lisp_instruction(self, 
                            node: Any, 
                            lisp_instruction: Union[str, Dict, List], 
                            event_id: str, 
                            event_data: Any) -> Any:
        """
        BACKWARDS-COMPATIBLE METHOD for existing ChainTree code.
        
        This method provides compatibility with code that calls:
            chain_tree.s_lisp_engine.run_lisp_instruction(node, s_dict, event_id, event_data)
        
        TOKEN FLOW:
        1. Extract tokens from lisp_instruction (Dict/String/List)
        2. Call run(tokens) with node, event_id, event_data as kwargs
        3. Return result from run_function
        
        Args:
            node: Execution context node (passed to run_function as kwarg)
            lisp_instruction: Can be:
                - Dict: Result from check() containing 'tokens' key (s_dict)
                - String: JSON string OR raw Lisp text
                - List: Direct token stream
            event_id: Event identifier (passed to run_function as kwarg)
            event_data: Event payload data (passed to run_function as kwarg)
            
        Returns:
            Result from run_function execution
            
        Raises:
            ValueError: If instruction is invalid or tokens cannot be extracted
            
        Example usage (existing ChainTree pattern):
            # Step 1: Check and store s_dict
            s_dict = sequencer.check(lisp_text, use_mako=True)
            
            # Step 2: Later, run the stored s_dict
            result = sequencer.run_lisp_instruction(node, s_dict, event_id, event_data)
        """
        tokens = None
        print(f"Running lisp instruction: {lisp_instruction}")
        
        
        # CASE 1: Dictionary (s_dict from check)
        if isinstance(lisp_instruction, dict):
            if not lisp_instruction.get("valid", False):
                error_msg = f"Invalid instruction: {lisp_instruction.get('errors', [])}"
                self._debug_log(error_msg)
                raise ValueError(error_msg)
            
            tokens = lisp_instruction.get("tokens")
            if tokens is None:
                error_msg = "Dictionary missing 'tokens' key - not a valid check() result"
                self._debug_log(error_msg)
                raise ValueError(error_msg)
            
            self._debug_log("Extracted tokens from s_dict")
        
        # CASE 2: String (could be JSON or raw Lisp text)
        elif isinstance(lisp_instruction, str):
            # Try parsing as JSON first (common when stored in database)
            if lisp_instruction.strip().startswith('{'):
                try:
                    parsed_dict = json.loads(lisp_instruction)
                    if not parsed_dict.get("valid", False):
                        error_msg = f"Invalid instruction in JSON: {parsed_dict.get('errors', [])}"
                        self._debug_log(error_msg)
                        raise ValueError(error_msg)
                    tokens = parsed_dict.get("tokens")
                    if tokens is not None:
                        self._debug_log("Extracted tokens from JSON string")
                except json.JSONDecodeError:
                    # Not valid JSON, will treat as Lisp text below
                    pass
            
            # If no tokens yet, treat as raw Lisp text
            if tokens is None:
                self._debug_log("Treating string as raw Lisp text, calling check()")
                result = self.check(lisp_instruction)
                if not result["valid"]:
                    error_msg = f"Invalid instruction: {result['errors']}"
                    self._debug_log(error_msg)
                    raise ValueError(error_msg)
                tokens = result["tokens"]
        
        # CASE 3: List (assume it's a token stream)
        elif isinstance(lisp_instruction, list):
            tokens = lisp_instruction
            self._debug_log("Using provided token list directly")
        
        else:
            error_msg = f"Unsupported instruction type: {type(lisp_instruction).__name__}"
            self._debug_log(error_msg)
            raise ValueError(error_msg)
        
        # Execute with all context parameters
        self._debug_log(f"Executing via run_lisp_instruction: node={node}, event_id={event_id}")
        return self.run(tokens, node=node, event_id=event_id, event_data=event_data)


# Example usage demonstrating token stream architecture
if __name__ == "__main__":
    
    # Example run function that processes the AST
    def example_run_function(handle, ast, *args, **kwargs):
        """Example function that processes instructions."""
        print(f"Handle: {handle}")
        print(f"AST: {ast}")
        print(f"Additional args: {args}")
        print(f"Additional kwargs: {kwargs}")
        return {"status": "success", "ast": ast}
    
    # Example debug function
    def example_debug_function(handle, message):
        """Example debug function."""
        print(f"[DEBUG - Handle: {handle}] {message}")
    
    # Create sequencer with handle and functions
    handle = {"context_id": "test_context", "session": "abc123"}
    
    sequencer = LispSequencer(
        handle=handle,
        run_function=example_run_function,
        debug_function=example_debug_function,
        control_codes=["STOP", "PAUSE", "RESUME"]
    )
    
    print("=" * 80)
    print("EXAMPLE 1: Token Stream Architecture - check() generates tokens")
    print("=" * 80)
    
    instruction1 = "(pipeline (@CFL_KILL_CHILDREN) (@CFL_FORK 0) (!CFL_JOIN 0) 'CFL_FUNCTION_TERMINATE)"
    
    # Step 1: Check generates token stream
    check_result = sequencer.check(instruction1, use_mako=False)
    print(f"Valid: {check_result['valid']}")
    print(f"Tokens: {check_result['tokens']}")
    print(f"Functions: {check_result['functions']}")
    
    # Step 2: run() accepts token stream and parses it
    if check_result['valid']:
        print("\n--- Running with cached tokens ---")
        result1 = sequencer.run()
        print(f"Result: {result1}\n")
    
    print("=" * 80)
    print("EXAMPLE 2: Passing tokens explicitly to run()")
    print("=" * 80)
    
    instruction2 = """
    (pipeline
        (@CFL_KILL_CHILDREN)
        <%fork_join(0)%>
        <%fork_join(1)%>
        'CFL_FUNCTION_TERMINATE)
    """
    
    # Check with Mako enabled
    check_result2 = sequencer.check(instruction2, use_mako=True)
    print(f"Valid: {check_result2['valid']}")
    print(f"Processed: {check_result2['text']}")
    print(f"Tokens: {check_result2['tokens']}")
    
    # Run with explicit token stream
    if check_result2['valid']:
        print("\n--- Running with explicit tokens ---")
        result2 = sequencer.run(check_result2['tokens'])
        print(f"Result: {result2}\n")
    
    print("=" * 80)
    print("EXAMPLE 3: Direct token stream execution (no check)")
    print("=" * 80)
    
    # Create tokens directly without using check()
    direct_tokens = ['(', 'pipeline', '(@CFL_KILL_CHILDREN)', '(@DIRECT_PROCESS)', "'CFL_FUNCTION_TERMINATE", ')']
    
    print(f"Direct tokens: {direct_tokens}")
    print("\n--- Running with direct token stream ---")
    try:
        # Note: This will fail validation but demonstrates the architecture
        result3 = sequencer.run(direct_tokens)
        print(f"Result: {result3}\n")
    except Exception as e:
        print(f"Expected error (malformed tokens): {e}\n")
    
    print("=" * 80)
    print("EXAMPLE 4: Reusing token stream multiple times")
    print("=" * 80)
    
    instruction4 = "(pipeline (@CFL_FORK 0) (@PROCESS) (!CFL_JOIN 0) 'CFL_FUNCTION_TERMINATE)"
    
    check_result4 = sequencer.check(instruction4, use_mako=False)
    print(f"Valid: {check_result4['valid']}")
    print(f"Tokens (reusable): {check_result4['tokens']}")
    
    if check_result4['valid']:
        # Reuse the same token stream multiple times
        print("\nRun 1:")
        result4a = sequencer.run(check_result4['tokens'], run_id=1)
        print(f"Result: {result4a}")
        
        print("\nRun 2:")
        result4b = sequencer.run(check_result4['tokens'], run_id=2)
        print(f"Result: {result4b}")
        
        print("\nRun 3 (using cached tokens):")
        result4c = sequencer.run(run_id=3)
        print(f"Result: {result4c}\n")
    
    print("=" * 80)
    print("EXAMPLE 5: ChainTree Compatibility - run_lisp_instruction()")
    print("=" * 80)
    print("This demonstrates the EXACT pattern used in your ChainTree code\n")
    
    # Simulate ChainTree workflow
    instruction5 = "(pipeline (@CFL_KILL_CHILDREN) (@INIT_PROCESS) 'CFL_FUNCTION_TERMINATE)"
    
    # Step 1: Check and store s_dict (done once, stored in database)
    s_dict = sequencer.check(instruction5, use_mako=False)
    print(f"Step 1 - Stored s_dict: valid={s_dict['valid']}")
    print(f"         tokens={s_dict['tokens']}\n")
    
    # Simulate storing as JSON (common in databases)
    s_dict_json = json.dumps(s_dict)
    print(f"Stored in DB as JSON string (first 100 chars):")
    print(f"{s_dict_json[:100]}...\n")
    
    # Step 2: Later, run the instruction (this is what was failing!)
    node = {"node_id": "test_node", "node_data": {"value": 42}}
    event_id = "CFL_INIT_EVENT"
    event_data = {"trigger": "user_action"}
    
    print("Step 2 - Execute using run_lisp_instruction():")
    print(f"         node={node}")
    print(f"         event_id={event_id}")
    
    # THIS IS THE CALL THAT WAS FAILING IN YOUR CODE
    result5 = sequencer.run_lisp_instruction(node, s_dict, event_id, event_data)
    print(f"\n✓ Result: {result5}\n")
    
    # Also test with JSON string (if stored/retrieved from database)
    print("Step 3 - Execute from JSON string (database retrieval):")
    result5b = sequencer.run_lisp_instruction(node, s_dict_json, event_id, event_data)
    print(f"✓ Result: {result5b}\n")
    
    print("=" * 80)
    print("TOKEN STREAM ARCHITECTURE BENEFITS:")
    print("=" * 80)
    print("""
    1. Separation of Concerns:
       - check(): Mako preprocessing + tokenization
       - run(): Parsing + execution
    
    2. Flexibility:
       - Pass tokens explicitly: run(tokens)
       - Use cached tokens: run()
       - Create tokens programmatically
    
    3. Performance:
       - Tokens can be cached and reused
       - Parsing happens only when needed
       - Can serialize/deserialize tokens for storage
    
    4. Composability:
       - Token streams can be combined
       - External systems can generate tokens
       - Language-independent token format
    
    5. Backwards Compatibility:
       - run_lisp_instruction() works with existing code
       - Accepts Dict (s_dict), String (JSON/Lisp), or List (tokens)
       - No changes needed to calling code
    """)