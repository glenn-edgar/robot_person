import re

class TokenSplitter:
    """
    A class for splitting a string into parts based on tokens starting with '@', '!', '?', or '@?',
    optionally modifying those tokens, and reconstructing the string while preserving all whitespace.
    
    This class is designed for token-based string processing, such as modifying mentions, commands,
    or queries in text while maintaining original spacing. Supports tokens like @user, !command,
    ?query, or @?placeholder.
    """
    
    def __init__(self):
        """
        Initializes the TokenSplitter with the default regex pattern for tokens.
        
        Pattern: Matches tokens starting with '@', '!', '?', or '@?' followed by word characters.
        """
        self.pattern = r'((?:@\w+|!\w+|\?\w+|@\?\w+))'
    
    def split(self, text):
        """
        Splits the input string into parts, separating tokens starting with '@', '!', '?', or '@?' 
        while preserving all whitespace.
        
        Args:
            text (str): The input string to split.
        
        Returns:
            list[str]: A list of parts, including whitespace segments and tokens.
        """
        parts = re.split(self.pattern, text)
        # Filter out empty strings, but keep all whitespace
        parts = [item for item in parts if item]
        return parts
    
    def modify_tokens(self, parts, modify_func):
        """
        Applies a modification function to tokens starting with '@', '!', '?', or '@?' in the parts list.
        
        Args:
            parts (list[str]): The list of parts from splitting.
            modify_func (callable): A function that takes a token string and returns a modified string.
        
        Returns:
            list[str]: The modified list of parts.
        """
        return [
            modify_func(item) if item.startswith(('@', '!', '?', '@?')) else item 
            for item in parts
        ]
    
    def reconstruct(self, parts):
        """
        Reconstructs the string by joining the parts back together.
        
        Args:
            parts (list[str]): The list of parts to join.
        
        Returns:
            str: The reconstructed string.
        """
        return ''.join(parts)
    
    def process(self, text, modify_func=None):
        """
        Convenience method to split, optionally modify tokens, and reconstruct the string in one call.
        
        Args:
            text (str): The input string.
            modify_func (callable, optional): A function to modify tokens.
        
        Returns:
            tuple: (reconstructed_str, parts_list)
        """
        parts = self.split(text)
        if modify_func:
            parts = self.modify_tokens(parts, modify_func)
        reconstructed = self.reconstruct(parts)
        return reconstructed, parts


# Example usage (for testing)
if __name__ == "__main__":
    splitter = TokenSplitter()
    
    # Example modification function
    def example_modify(token):
        print(f"Modifying token: {token}")
        return 'MOD_' + token
    
    text = "(pipeline (!CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ) (!CFL_WAIT 3) (@CFL_LOGM wait_for_two_seconds)\
            (!CFL_WAIT 2) (@CFL_LOGM terminate_sequence) (@CFL_LOGM wait_five_seconds_for_timeout) 'CFL_HALT))"
    reconstructed, parts = splitter.process(text, example_modify)
    print(f"Original: {text}")
    print(f"Parts: {parts}")
    print(f"Reconstructed: {reconstructed}")