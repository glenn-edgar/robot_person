import re
import keyword
from typing import Any, Callable, Dict, List, Tuple, Union
import inspect


# Mako imports - optional dependency
try:
    from mako.template import Template
    from mako.lookup import TemplateLookup
    MAKO_AVAILABLE = True
except ImportError:
    MAKO_AVAILABLE = False
            
import os
class LispSequencer:
    """
    A Lisp-based control flow sequencer for event-driven workflows.
    
    Supports:
    - @void functions (side effects only)
    - ?boolean functions (returns true/false)
    - !control functions (returns CFL_* control codes)
    - Macro expansion for text templates
    - Mako template defs as callable methods
    
    Function Syntax:
    - No parameters: @fn, ?fn, !fn
    - With parameters: (@fn "arg1" 123), (?fn "arg" 45.6), (!fn "arg1" "arg2" 789)
    - Parameters can be strings or numbers
    - Maximum 10 parameters per function
    
    Macro Syntax:
    - Define: (defmacro name (param1 param2) "template text with $param1 and $param2")
    - Use: (name "value1" "value2")
    - Macros are expanded before tokenization
    
    Template Defs:
    - Load from .mako files with load_template_defs()
    - Become callable methods: seq.send_event("name", {"data": 1})
    - Return rendered S-expression strings
    
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
    - Auto-prepend macros via use_macro() for convenience
    """
    '''
    CONTROL_CODES = {
        "CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", "CFL_RESET", "CFL_DISABLE", "CFL_TERMINATE_SYSTEM",
        "CFL_FUNCTION_RETURN","CFL_FUNCTION_HALT","CFL_FUNCTION_TERMINATE"
    }
    '''
    
    MAX_FUNCTION_PARAMS = 10
    
    def __init__(self, handle, run_function: Callable, debug_function: Callable = None, control_codes: List[str] = None, template_dirs: List[str] = None):
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
            control_codes: List of valid control flow codes
            template_dirs: List of directories to search for Mako templates
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
        self.template_strings: Dict[str, str] = {}
        self._auto_macros: List[str] = []  # Macros to auto-prepend
        
        
        
        # Mako integration
        self.template_dirs = template_dirs if template_dirs is not None else ['.']
        self._mako_templates: Dict[str, Tuple[List[str], str]] = {}  # Mako versions of macros
        self._template_defs: Dict[str, str] = {}  # Loaded template def names -> filenames
        if MAKO_AVAILABLE:
            self.lookup = TemplateLookup(directories=self.template_dirs)
        else:
            self.lookup = None

    def list_loaded_template_defs(self) -> List[str]:
        """
        List all template def methods that have been loaded and are callable.
        
        Returns:
            List of method names
        """
        methods = []
        for def_name in self._template_defs.keys():
            if hasattr(self, def_name):
                methods.append(def_name)
        return methods
    
    def load_templates(self, directory):
        """Load template strings from .mako files and parse defs."""
        for filename in os.listdir(directory):
            if filename.endswith('.mako'):
                filepath = os.path.join(directory, filename)
                with open(filepath, 'r') as file:
                    content = file.read()
                template_name = os.path.splitext(filename)[0]
                self.template_strings[template_name] = content
                
                # NEW: Also parse and load template defs automatically
                if MAKO_AVAILABLE:
                    try:
                        # Parse <%def> blocks
                        def_pattern = r'<%def\s+name="([a-zA-Z_][a-zA-Z0-9_]*)\(([^)]*)\)">'
                        matches = re.finditer(def_pattern, content)
                        
                        for match in matches:
                            def_name = match.group(1)
                            params_str = match.group(2).strip()
                            
                            # Parse parameters
                            if params_str:
                                params = [p.strip() for p in params_str.split(',')]
                            else:
                                params = []
                            
                            # Store and create method
                            self._template_defs[def_name] = filename
                            self._create_template_def_method(def_name, params, filename)
                            
                    except Exception as e:
                        print(f"Warning: Could not parse defs in {filename}: {e}")
    
    def load_template_defs(self, template_filename: str) -> Dict[str, List[str]]:
        """
        Load Mako template defs and create callable methods on this instance.
        
        Parses the template file for <%def name="func_name(arg1, arg2)"> blocks
        and creates methods like self.func_name(arg1, arg2) that render the def
        and return the resulting string.
        
        Args:
            template_filename: Name of .mako file in template_dirs
            
        Returns:
            Dict mapping def names to their parameter lists
            
        Example:
            # In cfl_helpers.mako:
            # <%def name="send_event(name, data)">
            # (@SEND_EVENT "${name}" "${data}")
            # </%def>
            
            seq.load_template_defs('cfl_helpers.mako')
            
            # Now you can call it directly:
            code = seq.send_event("test", "payload")
            # Returns: (@SEND_EVENT "test" "payload")
        """
        if not MAKO_AVAILABLE:
            raise ImportError("Mako is not installed. Install with: pip install mako")
        
        # Find the template file
        template_path = None
        for directory in self.template_dirs:
            full_path = os.path.join(directory, template_filename)
            if os.path.exists(full_path):
                template_path = full_path
                break
        
        if not template_path:
            raise FileNotFoundError(f"Template {template_filename} not found in {self.template_dirs}")
        
        # Read template content
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        # Parse <%def> blocks using regex
        # Match: <%def name="func_name(param1, param2, ...)">
        def_pattern = r'<%def\s+name="([a-zA-Z_][a-zA-Z0-9_]*)\(([^)]*)\)">'
        matches = re.finditer(def_pattern, template_content)
        
        loaded_defs = {}
        
        for match in matches:
            def_name = match.group(1)
            params_str = match.group(2).strip()
            
            # Parse parameters
            if params_str:
                params = [p.strip() for p in params_str.split(',')]
            else:
                params = []
            
            loaded_defs[def_name] = params
            self._template_defs[def_name] = template_filename
            
            # Create a method on this instance
            self._create_template_def_method(def_name, params, template_filename)
            
            # Verify it was created
            if not hasattr(self, def_name):
                print(f"WARNING: Failed to create method '{def_name}'")
            else:
                pass #print(f"Created method: {def_name}({', '.join(params)})")
        
        if not loaded_defs:
            print(f"WARNING: No template defs found in {template_filename}")
            print("Template content preview:")
            print(template_content[:500])
        
        return loaded_defs

    def _create_template_def_method(self, def_name: str, params: List[str], template_filename: str):
        """
        Create a callable method on this instance for a template def.
        
        Args:
            def_name: Name of the def
            params: List of parameter names
            template_filename: Filename containing the def
        """
        # Create a closure that captures the context
        def make_template_method(name, param_list, filename):
            def template_method(*args, **kwargs):
                """Dynamically created method to render a Mako def."""
                # Build the template that calls the def
                
                # Build call string with parameters
                if args:
                    # Positional args
                    if len(args) != len(param_list):
                        raise TypeError(f"{name}() takes {len(param_list)} arguments but {len(args)} were given")
                    # Convert args to kwargs
                    call_kwargs = {p: v for p, v in zip(param_list, args)}
                else:
                    call_kwargs = kwargs
                
                # Build Mako context
                context = {}
                for param in param_list:
                    if param in call_kwargs:
                        context[param] = call_kwargs[param]
                    else:
                        raise TypeError(f"{name}() missing required argument: '{param}'")
                
                # Create template string that calls the def
                template_str = f'''<%namespace name="ns" file="{filename}"/>
                    ${{ns.{name}({', '.join([f"{p}={p}" for p in param_list])})}}'''
                
                # Render through Mako
                result = self.render_with_mako(template_str, **context)
                return result.strip()
            
            return template_method
        
        # Create the method
        method = make_template_method(def_name, params, template_filename)
        
        # Set method metadata
        method.__name__ = def_name
        method.__doc__ = f"Render {def_name}({', '.join(params)}) from {template_filename}"
        
        # Bind to this instance
        setattr(self, def_name, method)
        
    def _create_template_def_method(self, def_name: str, params: List[str], template_filename: str):
            """
            Create a callable method on this instance for a template def.
            
            Args:
                def_name: Name of the def
                params: List of parameter names
                template_filename: Filename containing the def
            """
            def template_method(*args, **kwargs):
                """Dynamically created method to render a Mako def."""
                # Build the template that calls the def
                namespace_name = os.path.splitext(template_filename)[0].replace('-', '_').replace('.', '_')
                
                # Build call string with parameters
                if args:
                    # Positional args
                    if len(args) != len(params):
                        raise TypeError(f"{def_name}() takes {len(params)} arguments but {len(args)} were given")
                    call_args = ', '.join([f"{p}={repr(v)}" for p, v in zip(params, args)])
                elif kwargs:
                    # Keyword args
                    call_args = ', '.join([f"{k}={repr(v)}" for k, v in kwargs.items()])
                else:
                    # No args
                    call_args = ''
                
                template_str = f'''<%namespace name="ns" file="{template_filename}"/>
                    ${{ns.{def_name}({call_args})}}'''
                
                # Render through Mako
                result = self.render_with_mako(template_str)
                return result.strip()
            
            # Set method metadata
            template_method.__name__ = def_name
            template_method.__doc__ = f"Render {def_name} from {template_filename}"
            
            # Bind to this instance
            setattr(self, def_name, template_method)
        
    def list_template_defs(self) -> Dict[str, Tuple[str, List[str]]]:
        """
        List all loaded template defs.
        
        Returns:
            Dict mapping def names to (filename, params) tuples
        """
        result = {}
        for def_name, filename in self._template_defs.items():
            method = getattr(self, def_name, None)
            if method:
                # Try to get original params - stored in loaded_defs during load
                result[def_name] = (filename, [])
        return result
    
    def expand_macros_only(self, lisp_text: str, add_markers: bool = False) -> str:
        """
        Expand macros and return the expanded text stream.
        Works with pre-registered macros (via define_macro/use_macro) and 
        inline defmacro definitions.
        
        Args:
            lisp_text: Original lisp text with macro calls
            add_markers: If True, adds _x markers for debugging
        
        Returns:
            Expanded text string
            
        Raises:
            ValueError: If macro expansion fails
        """
        # Step 1: Prepend auto-macro definitions if any are registered
        if self._auto_macros:
            macro_defs = self._generate_macro_definitions()
            lisp_text = macro_defs + "\n" + lisp_text
        
        # Step 2: Process any inline (defmacro ...) definitions
        # Only if the method exists - you may not have added preprocess_defmacros yet
        if hasattr(self, 'preprocess_defmacros'):
            defmacro_result = self.preprocess_defmacros(lisp_text)
            if not defmacro_result['valid']:
                error_msg = "; ".join(defmacro_result['errors'])
                raise ValueError(f"Defmacro processing failed: {error_msg}")
            lisp_text = defmacro_result['processed_text']
        
        # Step 3: Expand all macro calls
        expansion_result = self.expand_macros(lisp_text)
        
        if not expansion_result['valid']:
            error_msg = "; ".join(expansion_result['errors'])
            raise ValueError(f"Macro expansion failed: {error_msg}")
        
        expanded = expansion_result['expanded_text']
        
        if add_markers:
            expanded = f"; _x_expanded_start\n{expanded}\n; _x_expanded_end\n"
        
        return expanded
    
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
    
    def use_macro(self, *macro_names: str) -> Dict[str, Any]:
        """
        Register macros to be automatically prepended when checking instructions.
        
        When check_lisp_instruction_with_macros() is called, these macro definitions
        will be prepended to the input string, making them available without needing
        to explicitly define them each time.
        
        Args:
            *macro_names: Names of macros to automatically include
            
        Returns:
            Dict with 'valid' and 'errors' keys
            
        Example:
            seq.define_macro("log_action", ["msg"], "(@log $msg)")
            seq.use_macro("log_action")
            
            # Now log_action is automatically available
            result = seq.check_lisp_instruction_with_macros("(log_action 'test')")
        """
        errors = []
        
        for name in macro_names:
            if name not in self.macros and name not in self.template_strings:
                errors.append(f"Macro or template '{name}' is not defined")
            elif name not in self._auto_macros:
                self._auto_macros.append(name)
        
        if errors:
            return {"valid": False, "errors": errors}
        
        return {"valid": True, "errors": []}
    
    def clear_auto_macros(self):
        """Clear all registered auto-prepend macros."""
        self._auto_macros.clear()
    
    def get_auto_macros(self) -> List[str]:
        """Get list of macros that will be auto-prepended."""
        return self._auto_macros.copy()
    
    def _generate_macro_definitions(self) -> str:
        """
        Generate defmacro S-expressions for auto-prepend macros.
        
        Returns:
            String containing all defmacro definitions
        """
        definitions = []
        
        for name in self._auto_macros:
            if name in self.macros:
                params, template = self.macros[name]
                # Generate the defmacro form
                params_str = " ".join(params)
                # Escape the template string properly
                template_escaped = template.replace('\\', '\\\\').replace('"', '\\"')
                defmacro = f'(defmacro {name} ({params_str}) "{template_escaped}")'
                definitions.append(defmacro)
            elif name in self.template_strings:
                # For template strings loaded from files, treat as parameter-less macros
                template = self.template_strings[name]
                template_escaped = template.replace('\\', '\\\\').replace('"', '\\"')
                defmacro = f'(defmacro {name} () "{template_escaped}")'
                definitions.append(defmacro)
        
        return "\n".join(definitions)
    
    # ====================================================================================
    # MAKO INTEGRATION METHODS
    # ====================================================================================
    def render_template_file(self, template_name: str, **context) -> str:
        """
        Load and render a Mako template file.
        
        Args:
            template_name: Name of template file in template_dirs (e.g., 'motor.mako')
            **context: Variables to pass to the template
            
        Returns:
            Rendered Lisp code as string
            
        Example:
            code = seq.render_template_file('motor.mako', motors=motor_list)
        """
        if not MAKO_AVAILABLE:
            raise ImportError("Mako is not installed")
        
        template = self.lookup.get_template(template_name)
        return template.render(**context)
    
    def export_macros_to_mako(self) -> Dict[str, str]:
        """
        Export all macros in Mako-compatible format.
        Converts $param to ${param} for Mako.
        
        Returns:
            Dict mapping macro names to Mako template strings
            
        Raises:
            ImportError: If Mako is not installed
        """
        if not MAKO_AVAILABLE:
            raise ImportError("Mako is not installed. Install with: pip install mako")
        
        mako_templates = {}
        
        for name, (params, template) in self.macros.items():
            # Convert $param to ${param} for Mako
            mako_template = template
            for param in params:
                # Use word boundaries to avoid partial replacements
                mako_template = re.sub(
                    rf'\${param}\b', 
                    f'${{{param}}}', 
                    mako_template
                )
            
            mako_templates[name] = mako_template
            self._mako_templates[name] = (params, mako_template)
        
        return mako_templates
    
    def render_with_mako(self, template_str: str, **context) -> str:
        """
        Render a Mako template to generate Lisp code.
        
        Exported macros and loaded templates are available as functions in the template.
        Use ${macro_name(param1='value1', param2='value2')}
        
        Args:
            template_str: Mako template string
            **context: Context variables for the template
            
        Returns:
            Rendered Lisp code string
            
        Raises:
            ImportError: If Mako is not installed
            
        Example:
            template = '''
            % for i in range(count):
            (@init ${i})
            % endfor
            '''
            code = seq.render_with_mako(template, count=5)
        """
        if not MAKO_AVAILABLE:
            raise ImportError("Mako is not installed. Install with: pip install mako")
        
        template = Template(template_str, lookup=self.lookup)
        
        # Create macro functions for Mako (from defined macros)
        macro_functions = {}
        for name, (params, mako_template) in self._mako_templates.items():
            def make_macro_func(macro_template, macro_params):
                def macro_func(**kwargs):
                    result = macro_template
                    for param in macro_params:
                        if param in kwargs:
                            result = result.replace(f'${{{param}}}', str(kwargs[param]))
                    return result
                return macro_func
            
            macro_functions[name] = make_macro_func(mako_template, params)
        
        # Add loaded template strings as parameter-less functions
        for name, template_content in self.template_strings.items():
            if name not in macro_functions:  # Don't override if already a macro
                # Convert template string to Mako format
                mako_content = template_content
                # Simple conversion - could be enhanced based on template format
                macro_functions[name] = lambda content=mako_content: content
        
        # Merge with user context
        full_context = {**macro_functions, **context}
        
        return template.render(**full_context)
    
    def render_file(self, filename: str, **context) -> str:
        """
        Render a Mako template file to generate Lisp code.
        
        Args:
            filename: Template filename (relative to template_dirs)
            **context: Context variables for the template
            
        Returns:
            Rendered Lisp code string
            
        Raises:
            ImportError: If Mako is not installed
            
        Example:
            code = seq.render_file('handlers.mako', 
                                   events=events,
                                   enable_logging=True)
        """
        if not MAKO_AVAILABLE:
            raise ImportError("Mako is not installed. Install with: pip install mako")
        
        template = self.lookup.get_template(filename)
        
        # Create macro functions (from defined macros)
        macro_functions = {}
        for name, (params, mako_template) in self._mako_templates.items():
            def make_macro_func(macro_template, macro_params):
                def macro_func(**kwargs):
                    result = macro_template
                    for param in macro_params:
                        if param in kwargs:
                            result = result.replace(f'${{{param}}}', str(kwargs[param]))
                    return result
                return macro_func
            
            macro_functions[name] = make_macro_func(mako_template, params)
        
        # Add loaded template strings
        for name, template_content in self.template_strings.items():
            if name not in macro_functions:
                macro_functions[name] = lambda content=template_content: content
        
        full_context = {**macro_functions, **context}
        
        return template.render(**full_context)
    
    def list_macros(self) -> Dict[str, List[str]]:
        """
        List all defined macros and their parameters.
        
        Returns:
            Dict mapping macro names to parameter lists
        """
        return {name: list(params) for name, (params, _) in self.macros.items()}
    
    
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
        
        Auto-registered macros (via use_macro) are automatically prepended.
        
        Returns:
            Dict with:
                'valid' (bool): Whether the instruction is valid
                'errors' (list): List of validation/expansion errors
                'text' (str): Original lisp text
                'expanded_text' (str): Text after macro expansion
                'ast' (parsed structure): Tokenized/parsed form for execution
                'functions' (list): Functions required by this instruction
        """
        # Prepend auto-macro definitions if any are registered
        if self._auto_macros:
            macro_defs = self._generate_macro_definitions()
            lisp_text = macro_defs + "\n" + lisp_text
        
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
        "CFL_CONTINUE", "CFL_HALT", "CFL_TERMINATE", "CFL_RESET", "CFL_DISABLE", 
        "CFL_FUNCTION_TERMINATE"
    ]
    
    def run_fn(handle, func_type, func_name, node, event_id, event_data, params=[]):
        """Execute a function."""
        params_str = f" with params {params}" if params else ""
        print(f"  → Running {func_type}{func_name}{params_str}")
        
        if func_type == '@':
            print(f"    Side effect executed")
        elif func_type == '?':
            return True
        elif func_type == '!':
            return "CFL_CONTINUE"
    
    def debug_fn(handle, message, node, event_id, event_data):
        """Output debug messages."""
        print(f"  [DEBUG] {message}")
    
    # Create sequencer
    seq = LispSequencer("my-handle", run_fn, debug_fn, 
                       control_codes=CONTROL_CODES,
                       template_dirs=['.'])
    
    print("=" * 70)
    print("BASIC MACRO TESTS")
    print("=" * 70)
    
    # Test 1: Basic macro
    print("\n--- Test 1: Basic Macro ---")
    seq.define_macro("log_action", ["msg"], "(@log $msg)")
    seq.use_macro("log_action")
    
    code1 = "(pipeline (log_action \"test\") 'CFL_CONTINUE)"
    result1 = seq.check_lisp_instruction_with_macros(code1)
    print(f"Valid: {result1['valid']}")
    
    if result1['valid']:
        ret = seq.run_lisp_instruction("node1", result1, "test_event", {})
        print(f"Result: {ret}")
    
    # Test Mako integration only if available
    if MAKO_AVAILABLE:
        print("\n" + "=" * 70)
        print("MAKO TEMPLATE DEF TESTS")
        print("=" * 70)
        
        # Create test template file
        print("\n--- Creating test template file ---")
        cfl_helpers_content = '''<%!
    import json
    
    def compress_json(data):
        """Replace quotes with --- for CFL string encoding."""
        return json.dumps(data).replace('"', '---')
%>

<%def name="send_system_event(event_name, event_data)">
(@CFL_SEND_SYSTEM_EVENT "${event_name}" "${compress_json(event_data)}")\
</%def>

<%def name="send_current_node_event(event_name, event_data)">
(@CFL_SEND_CURRENT_NODE_EVENT "${event_name}" "${compress_json(event_data)}")\
</%def>
'''
        
        try:
            with open('cfl_helpers.mako', 'w') as f:
                f.write(cfl_helpers_content)
            print("✓ Created cfl_helpers.mako")
        except Exception as e:
            print(f"✗ Failed to create template file: {e}")
            import sys
            sys.exit(1)
        
        # Load the template defs
        print("\n--- Loading template defs ---")
        try:
            loaded = seq.load_template_defs('cfl_helpers.mako')
            print(f"✓ Loaded template defs: {loaded}")
        except Exception as e:
            print(f"✗ Failed to load template defs: {e}")
            import traceback
            traceback.print_exc()
            import sys
            sys.exit(1)
        
        # Verify methods were created
        print("\n--- Verifying methods ---")
        if hasattr(seq, 'send_current_node_event'):
            print("✓ send_current_node_event is available")
        else:
            print("✗ send_current_node_event NOT available")
            print("Available methods:", [m for m in dir(seq) if not m.startswith('_')])
            import sys
            sys.exit(1)
        
        if hasattr(seq, 'send_system_event'):
            print("✓ send_system_event is available")
        else:
            print("✗ send_system_event NOT available")
        
        # Test calling the methods
        print("\n--- Test 2: Call template def methods ---")
        try:
            event_call = seq.send_current_node_event("CFL_CHANGE_STATE", {"state": 1})
            print(f"Generated: {event_call}")
            
            # Build a pipeline
            macro_test_2 = (
                "(pipeline (@CFL_KILL_CHILDREN) (fork_join 0) (fork_join 1) " +
                event_call +
                " (fork_join 2) 'CFL_FUNCTION_TERMINATE)"
            )
            
            print(f"\nPipeline: {macro_test_2}")
            
            # Check and run
            result2 = seq.check_lisp_instruction_with_macros(macro_test_2)
            print(f"Valid: {result2['valid']}")
            
            if result2['valid']:
                ret = seq.run_lisp_instruction("node1", result2, "test_event", {})
                print(f"Result: {ret}")
            else:
                print(f"Errors: {result2['errors']}")
                
        except Exception as e:
            print(f"✗ Error during test: {e}")
            import traceback
            traceback.print_exc()
            import sys
            sys.exit(1)
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("Mako not available - skipping template def tests")
        print("Install with: pip install mako")
        print("=" * 70)