class TokenDictionary:
    """
    A class for managing a dictionary of boolean (bit) values with support
    for evaluating S-expression logical operations.
    """
    
    def __init__(self):
        """Initialize the token dictionary."""
    
        self.token_data = {}
        self.token_description_dict = {}
        self.token_state = {}
        self.token_mask = {}
        self.event_mask = 0
        self.current_mask = 1
        
    def reset_token_dictionary(self):
        """Reset the token dictionary."""
        self.token_data = {}
        self.token_description_dict = {}
        self.token_state = {}
        self.token_mask = {}
        self.event_mask = 0
        self.current_mask = 1
    
    
    
    def define_token(self, token_id: str, token_description: str, token_data: dict = {}):
        """Define a new token with description and initial data."""
        if token_id in self.token_data:
            raise ValueError(f"Token {token_id} already exists")
        if not isinstance(token_data, dict):
            raise TypeError(f"token_data must be a dict, got {type(token_data)}")
        
        self.token_mask[token_id] = self.current_mask
        self.current_mask = self.current_mask << 1
        self.token_data[token_id] = token_data
        self.token_description_dict[token_id] = token_description
        self.token_state[token_id] = False
        
    
    def set_token(self, token_id: str, token_data= None):
        """
        Set a token to True state and optionally update its data.
        
        Args:
            token_id: The token identifier
            token_data: Optional new data dict. If None, keeps existing data.
        """
        if token_id not in self.token_data:
            raise ValueError(f"Token {token_id} does not exist")
        self.token_data[token_id] = token_data
        self.token_state[token_id] = True
        
        self.event_mask = self.event_mask | self.token_mask[token_id]
        
    
    def clear_token(self, token_id: str, token_data = None):
        """
        Clear a token to False state and optionally update its data.
        
        Args:
            token_id: The token identifier
            token_data: Optional new data dict. If None, keeps existing data.
        """
        if token_id not in self.token_data:
            raise ValueError(f"Token {token_id} does not exist")
        self.token_data[token_id] = token_data
        self.token_state[token_id] = False
        self.event_mask = self.event_mask & ~self.token_mask[token_id]
    
    def get_token(self, token_id: str) -> tuple[bool, dict]:
        """
        Get token state and data.
        
        Returns:
            Tuple of (state: bool,mask: int, data: dict)
        """
        if token_id not in self.token_data:
            raise KeyError(f"Token '{token_id}' not found in dictionary")
        return self.token_state[token_id], self.token_mask[token_id], self.token_data[token_id]
    
    def get_token_state(self, token_id: str) -> bool:
        """Get only the token state (boolean value)."""
        if token_id not in self.token_data:
            raise KeyError(f"Token '{token_id}' not found in dictionary")
        return self.token_state[token_id]
    
    def get_token_data(self, token_id: str) -> dict:
        """Get only the token data."""
        if token_id not in self.token_data:
            raise KeyError(f"Token '{token_id}' not found in dictionary")
        return self.token_data[token_id]
    
    def get_token_mask(self, token_id: str) -> int:
        """Get the token mask."""
        if token_id not in self.token_data:
            raise KeyError(f"Token '{token_id}' not found in dictionary")
        return self.token_mask[token_id]    
    
    def generate_event_mask(self,token_list: list[str]) -> int:
        """Generate an event mask from a list of token IDs."""
        event_mask = 0
        for token_id in token_list:
            if token_id not in self.token_data:
                raise KeyError(f"Token '{token_id}' not found in dictionary")
            event_mask = event_mask | self.token_mask[token_id]
        return event_mask
        
    def get_current_event_mask(self) -> int:
        """Get the current event mask."""
        return self.event_mask
    
    def determine_event_match(self,event_mask) -> int:
        """Determine if the event mask matches the current event mask."""
        return self.event_mask & event_mask == event_mask
    
    def get_token_description(self, token_id: str) -> str:
        """Get the token description."""
        if token_id not in self.token_description_dict:
            raise KeyError(f"Token '{token_id}' not found in dictionary")
        return self.token_description_dict[token_id]
    
    def token_exists(self, token_id: str) -> bool:
        """Check if a token exists."""
        return token_id in self.token_data
    
    def get_all_token_ids(self) -> list[str]:
        """Get a list of all token IDs."""
        return list(self.token_data.keys())
    
    def get_active_tokens(self) -> list[str]:
        """Get a list of all tokens that are set to True."""
        return [tid for tid, state in self.token_state.items() if state]
    
    def remove_token(self, token_id: str):
        """Remove a token from the dictionary."""
        if token_id not in self.token_data:
            raise KeyError(f"Token '{token_id}' not found in dictionary")
        del self.token_data[token_id]
        del self.token_description_dict[token_id]
        del self.token_state[token_id]
    
    def reset_all_tokens(self):
        """Set all tokens to False state."""
        for token_id in self.token_state:
            self.token_state[token_id] = False
    
    def evaluate_expression(self, expr):
        """
        Evaluate an S-expression with logical operations.
        
        S-expressions are nested lists where:
        - First element is the operator: 'and', 'or', 'not', 'xor', 'nand', 'nor'
        - Remaining elements are either:
          - Token ID strings (keys in the dictionary)
          - Nested S-expressions (lists)
        
        Examples:
            ['and', 'token1', 'token2']
            ['or', ['and', 'token1', 'token2'], 'token3']
            ['not', 'token1']
            ['xor', 'token1', 'token2', 'token3']
        
        Args:
            expr: Nested list representing an S-expression or a string token ID
            
        Returns:
            Boolean result of the evaluation
        """
        # Base case: if expr is a string, it's a token ID
        if isinstance(expr, str):
            state = self.get_token_state(expr)
            return state
        
        # expr should be a list with operator and operands
        if not isinstance(expr, list) or len(expr) < 1:
            raise ValueError("Expression must be a non-empty list")
        
        operator = expr[0].lower()
        if operator not in ['and', 'or', 'not', 'xor', 'nand', 'nor']:
            raise ValueError(f"Unknown operator: {operator}")
        
        operands = expr[1:]
        
        # Validate operand count for NOT
        if operator == 'not' and len(operands) != 1:
            raise ValueError("NOT operation requires exactly one operand")
        
        if len(operands) == 0:
            raise ValueError(f"Operator '{operator}' requires at least one operand")
        
        # Recursively evaluate operands
        evaluated_operands = [self.evaluate_expression(op) for op in operands]
        
        # Apply the logical operation
        if operator == 'and':
            return all(evaluated_operands)
        elif operator == 'or':
            return any(evaluated_operands)
        elif operator == 'not':
            return not evaluated_operands[0]
        elif operator == 'xor':
            # XOR of multiple values: odd number of True values
            return sum(evaluated_operands) % 2 == 1
        elif operator == 'nand':
            return not all(evaluated_operands)
        elif operator == 'nor':
            return not any(evaluated_operands)
    
    def __repr__(self):
        return f"TokenDictionary(tokens={len(self.token_data)})"
    
    def __str__(self):
        lines = ["TokenDictionary:"]
        for token_id in self.token_data:
            state = self.token_state[token_id]
            desc = self.token_description_dict[token_id]
            lines.append(f"  {token_id}: {state} - {desc}")
        return "\n".join(lines)

    def validate_syntax_offline(self, expression) -> bool:
        """
        Validate s-expression syntax without checking if tokens exist.
        Ignores whether token_ids are valid, only checks structure.
        
        Args:
            expression: S-expression (list or string) to validate
            
        Returns:
            bool: True if syntax is valid, False otherwise
                
        Example expressions:
            ['and', 'token1', 'token2']
            ['or', ['and', 'token1', 'token2'], 'token3']
            ['not', 'token1']
            'token1'  # Simple token reference
        """
        errors = []
        warnings = []
        
        try:
            self._validate_expression_structure(expression, errors, warnings, check_tokens=False)
            return len(errors) == 0
        except Exception:
            return False


    def validate_syntax_with_tokens(self, expression) -> bool:
        """
        Validate s-expression syntax AND verify that all referenced tokens exist.
        Checks both syntax validity and token_id validity against the token dictionary.
        
        Args:
            expression: S-expression (list or string) to validate
            
        Returns:
            bool: True if syntax and all tokens are valid, False otherwise
        """
        errors = []
        warnings = []
        
        try:
            # Validate structure
            self._validate_expression_structure(expression, errors, warnings, check_tokens=True)
            
            if len(errors) > 0:
                return False
            
            # Extract and check all token IDs
            all_tokens = self._extract_all_tokens(expression)
            
            for token_id in all_tokens:
                if not self.token_exists(token_id):
                    return False
            
            return True
            
        except Exception:
            return False


    def _validate_expression_structure(self, expr, errors, warnings, check_tokens=False, depth=0):
        """
        Recursively validate the structure of an s-expression.
        
        Args:
            expr: Expression to validate
            errors: List to append error messages to
            warnings: List to append warning messages to
            check_tokens: Whether to check if tokens exist
            depth: Current recursion depth (for detecting overly deep expressions)
        """
        # Check recursion depth
        if depth > 100:
            errors.append("Expression nesting is too deep (max 100 levels)")
            return
        
        # Base case: string token ID
        if isinstance(expr, str):
            if not expr:
                errors.append("Empty string token ID found")
                return
            
            # Check for valid token ID format (optional - adjust as needed)
            if not expr.replace('_', '').replace('-', '').isalnum():
                warnings.append(f"Token ID '{expr}' contains unusual characters")
            
            if check_tokens and not self.token_exists(expr):
                # This will be caught by the calling function
                pass
            
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
        valid_operators = ['and', 'or', 'not', 'xor', 'nand', 'nor']
        
        if operator not in valid_operators:
            errors.append(f"Invalid operator '{expr[0]}'. Valid operators are: {', '.join(valid_operators)}")
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
        for i, operand in enumerate(operands):
            self._validate_expression_structure(operand, errors, warnings, check_tokens, depth + 1)


    def _extract_all_tokens(self, expr):
        """
        Extract all token IDs from an s-expression.
        
        Args:
            expr: Expression to extract tokens from
            
        Returns:
            list: List of unique token IDs (preserves order of first occurrence)
        """
        tokens = []
        seen = set()
        
        def extract_recursive(e):
            if isinstance(e, str):
                if e not in seen:
                    tokens.append(e)
                    seen.add(e)
            elif isinstance(e, list) and len(e) > 0:
                # Skip the operator (first element), process operands
                for operand in e[1:]:
                    extract_recursive(operand)
        
        extract_recursive(expr)
        return tokens

# Example usage and tests
if __name__ == "__main__":
    bd = TokenDictionary()
    
   
    
    bd.define_token('a','Token A',{})
    bd.define_token('b','Token B',{})
    bd.define_token('c','Token C',{})
    bd.define_token('d','Token D',{})
    
    bd.set_token('a', {'value': 'test_a'})
    bd.clear_token('b', {'value': 'test_b'})
    bd.set_token('c', {'value': 'test_c'})
    bd.clear_token('d', {'value': 'test_d'})
    
    print(bd)
    print()
    
    # Simple AND operation
    result1 = bd.evaluate_expression(['and', 'a', 'c'])
    print("['and', 'a', 'c'] =", result1)  # True AND True = True
    
    # OR operation
    result2 = bd.evaluate_expression(['or', 'b', 'd'])
    print("['or', 'b', 'd'] =", result2)  # False OR False = False
    
    # NOT operation
    result3 = bd.evaluate_expression(['not', 'b'])
    print("['not', 'b'] =", result3)  # NOT False = True
    
    # Nested expression: (a AND b) OR c
    result4 = bd.evaluate_expression(['or', ['and', 'a', 'b'], 'c'])
    print("['or', ['and', 'a', 'b'], 'c'] =", result4)
    
    # Complex nested expression: NOT((a OR b) AND (c OR d))
    result5 = bd.evaluate_expression(['not', ['and', ['or', 'a', 'b'], ['or', 'c', 'd']]])
    print("['not', ['and', ['or', 'a', 'b'], ['or', 'c', 'd']]] =", result5)
    
    # XOR operation
    result6 = bd.evaluate_expression(['xor', 'a', 'b', 'c'])
    print("['xor', 'a', 'b', 'c'] =", result6)  # True XOR False XOR True = False
    
    # Get active tokens
    print("\nActive tokens:", bd.get_active_tokens())
    
    # Get token info
    state, desctiption, data = bd.get_token('a')
    print(f"\nToken 'a': state={state}, desctiption={desctiption}, data={data}")