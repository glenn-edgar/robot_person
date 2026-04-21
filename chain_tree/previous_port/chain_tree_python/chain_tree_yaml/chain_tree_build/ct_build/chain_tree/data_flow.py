from .column_flow import ColumnFlow

#
# Making a class if more data flow column types are needed
#
#

class DataFlow(ColumnFlow):
    def __init__(self, data_structures, ctb):
        self.ds = data_structures
        self.ctb = ctb
        ColumnFlow.__init__(self, data_structures, ctb)
        
        
        
    def define_data_flow_event_mask(self, column_name:str,  aux_function:str, 
                                    user_data:dict = {},
                                    event_list:list[str] = [], auto_start:bool = False):
        
        self.ctb.add_boolean_function(aux_function)
        data_flow_data = {"event_list":event_list}
        return self.define_column(column_name,main_function = "CFL_DF_MASK_MAIN",initialization_function = "CFL_DF_MASK_INIT",
               termination_function = "CFL_DF_MASK_TERM", aux_function = aux_function, 
               column_data = {"user_data": user_data,"data_flow_data":data_flow_data}, auto_start = auto_start,label="CFL_DF_MASK")

    def define_data_flow_event_expression(self, column_name:str,  aux_function:str, 
                                    user_data:dict = {},
                                    s_expression:str = "", trigger_event:str = "CFL_SECOND_EVENT", trigger_event_count:int = 1, 
                                    auto_start:bool = False):
        
        if not isinstance(s_expression, list):
            raise TypeError("s_expression must be a list")
        if self.validate_syntax_offline(s_expression) == False:
            raise ValueError(f"Invalid s-expression with syntax: {s_expression}")
        self.ctb.add_boolean_function(aux_function)
        data_flow_data = {"event_expression":s_expression, "trigger_event":trigger_event, "trigger_event_count":trigger_event_count}
        return self.define_column(column_name,main_function = "CFL_DF_EXPRESSION_MAIN",initialization_function = "CFL_DF_EXPRESSION_INIT",
               termination_function = "CFL_DF_EXPRESSION_TERM", aux_function = aux_function, 
               column_data = {"user_data": user_data,"data_flow_data":data_flow_data}, auto_start = auto_start,label="CFL_DF_MASK")    

    def asm_define_df_token(self,token_id:str,token_description:str):
        if not isinstance(token_id, str):
            raise TypeError("token_id must be a string")
        if not isinstance(token_description, str):
            raise TypeError("token_description must be a string")
        return self.asm_one_shot_handler("CFL_DEFINE_DF_TOKEN",{"token_id": token_id, "token_description": token_description})
        
    def asm_set_df_token(self,token_id:str,event_data):
        if not isinstance(token_id, str):
            raise TypeError("token_id must be a string")
    
        return self.asm_one_shot_handler("CFL_SET_DF_TOKEN",{"token_id": token_id, "event_data": event_data})
    
    def asm_clear_df_token(self,token_id:str,event_data):
        if not isinstance(token_id, str):
            raise TypeError("token_id must be a string")
    
        return self.asm_one_shot_handler("CFL_CLEAR_DF_TOKEN",{"token_id": token_id, "event_data": event_data})
   
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