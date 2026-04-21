class ExpressionValidator:
    """
    Validates S-expression syntax for logical operations.
    Can validate structure only or structure with token existence.
    """
    
    def __init__(self, token_checker=None):
        """
        Initialize the validator.
        
        Args:
            token_checker: Optional callable that checks if a token exists.
                          Should accept a token_id string and return bool.
        """
        self.token_checker = token_checker
        self.valid_operators = ['and', 'or', 'not', 'xor', 'nand', 'nor']
        self.max_depth = 100
    
    def validate_syntax_only(self, expression) -> bool:
        """
        Validate s-expression syntax without checking if tokens exist.
        
        Args:
            expression: S-expression (list or string) to validate
            
        Returns:
            bool: True if syntax is valid, False otherwise
        """
        errors = []
        warnings = []
        
        try:
            self._validate_structure(expression, errors, warnings, 
                                    check_tokens=False, depth=0)
            return len(errors) == 0
        except Exception:
            return False
    
    def validate_with_tokens(self, expression) -> bool:
        """
        Validate syntax AND verify that all referenced tokens exist.
        
        Args:
            expression: S-expression (list or string) to validate
            
        Returns:
            bool: True if syntax and all tokens are valid, False otherwise
        """
        if self.token_checker is None:
            raise ValueError("Token checker not provided to validator")
        
        errors = []
        warnings = []
        
        try:
            self._validate_structure(expression, errors, warnings, 
                                    check_tokens=True, depth=0)
            return len(errors) == 0
        except Exception:
            return False
    
    def validate_detailed(self, expression, check_tokens=False) -> tuple[bool, list, list]:
        """
        Validate and return detailed errors and warnings.
        
        Args:
            expression: S-expression to validate
            check_tokens: Whether to verify token existence
            
        Returns:
            tuple: (is_valid: bool, errors: list[str], warnings: list[str])
        """
        errors = []
        warnings = []
        
        try:
            self._validate_structure(expression, errors, warnings, 
                                    check_tokens, depth=0)
            return (len(errors) == 0, errors, warnings)
        except Exception as e:
            errors.append(f"Validation exception: {str(e)}")
            return (False, errors, warnings)
    
    def _validate_structure(self, expr, errors, warnings, check_tokens, depth):
        """
        Recursively validate the structure of an s-expression.
        
        Args:
            expr: Expression to validate
            errors: List to append error messages to
            warnings: List to append warning messages to
            check_tokens: Whether to check if tokens exist
            depth: Current recursion depth
        """
        # Check recursion depth
        if depth > self.max_depth:
            errors.append(f"Expression nesting is too deep (max {self.max_depth} levels)")
            return
        
        # Base case: string token ID
        if isinstance(expr, str):
            if not expr:
                errors.append("Empty string token ID found")
                return
            
            # Check for valid token ID format
            if not expr.replace('_', '').replace('-', '').isalnum():
                warnings.append(f"Token ID '{expr}' contains unusual characters")
            
            # Check if token exists
            if check_tokens and self.token_checker and not self.token_checker(expr):
                errors.append(f"Token '{expr}' does not exist")
            
            return
        
        # Expression must be a list
        if not isinstance(expr, list):
            errors.append(f"Expression must be a list or string, got {type(expr).__name__}")
            return
        
        # List must not be empty
        if len(expr) == 0:
            errors.append("Empty list expression found")
            return
        
        # First element must be an operator (string)
        if not isinstance(expr[0], str):
            errors.append(f"Operator must be a string, got {type(expr[0]).__name__}")
            return
        
        operator = expr[0].lower()
        
        if operator not in self.valid_operators:
            errors.append(f"Invalid operator '{expr[0]}'. Valid operators are: {', '.join(self.valid_operators)}")
            return
        
        # Get operands
        operands = expr[1:]
        
        # Validate operand count
        if operator == 'not':
            if len(operands) != 1:
                errors.append(f"'not' operator requires exactly 1 operand, got {len(operands)}")
                return
        else:
            if len(operands) == 0:
                errors.append(f"'{operator}' operator requires at least 1 operand, got 0")
                return
            
            if operator in ['and', 'or'] and len(operands) == 1:
                warnings.append(f"'{operator}' operator with only 1 operand has no effect")
        
        # Recursively validate each operand
        for operand in operands:
            self._validate_structure(operand, errors, warnings, check_tokens, depth + 1)

