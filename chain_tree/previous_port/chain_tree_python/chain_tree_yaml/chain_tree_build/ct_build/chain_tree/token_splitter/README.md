# TokenSplitter

A lightweight Python class for splitting strings based on special tokens (starting with `@`, `!`, `?`, or `@?`), optionally modifying those tokens, and reconstructing the string while preserving all original whitespace. Ideal for processing text with mentions, commands, queries, or placeholders (e.g., in configuration files, scripts, or lisp-like expressions).

## Features
- **Token Detection**: Identifies tokens starting with `@` (e.g., `@user`), `!` (e.g., `!command`), `?` (e.g., `?query`), or `@?` (e.g., `@?placeholder`).
- **Whitespace Preservation**: Maintains all spaces, tabs, and newlines exactly as in the input.
- **Flexible Modification**: Pass a custom function to transform detected tokens.
- **Easy Reconstruction**: Seamlessly joins parts back into a modified string.
- **Pure Python**: No external dependencies beyond the standard `re` module.

## Installation
No installation required! Just copy the `TokenSplitter` class into your Python project. It uses only built-in modules.

```bash
# Usage in your script
# Simply import re if not already available
Usage
Basic Splitting
pythonfrom your_module import TokenSplitter  # Replace with actual import

splitter = TokenSplitter()
text = "(pipeline (!CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ) (!CFL_WAIT 3))"
parts = splitter.split(text)
print(parts)
# Output: ['(pipeline (', '!CFL_TIME_OUT', ' 10) (', '@CFL_LOGM', ' wait_for_three_seconds ) (', '!CFL_WAIT', ' 3))']
Modifying Tokens
Define a modification function and apply it:
pythondef uppercase_token(token):
    return token.upper()

splitter = TokenSplitter()
text = "(pipeline (!CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ))"
reconstructed, parts = splitter.process(text, uppercase_token)
print(reconstructed)
# Output: '(pipeline (!CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ))'  # Note: Uppercase would apply if modified
Full Workflow
The process method handles everything in one go:
pythondef add_prefix(token):
    return f"NEW_{token}"

splitter = TokenSplitter()
text = "(pipeline (!CFL_TIME_OUT 10) (@CFL_LOGM wait_for_three_seconds ) (!CFL_WAIT 3))"
result, parts = splitter.process(text, add_prefix)
print(result)
# Output: '(pipeline (NEW_!CFL_TIME_OUT 10) (NEW_@CFL_LOGM wait_for_three_seconds ) (NEW_!CFL_WAIT 3))'
Advanced: Custom Pattern
You can subclass TokenSplitter to change the regex pattern:
pythonclass CustomSplitter(TokenSplitter):
    def __init__(self):
        super().__init__()
        self.pattern = r'((?:#|\$|@!\w+))'  # e.g., for # or $ or @!-starting tokens

splitter = CustomSplitter()
# Now splits on #, $, or @!-starting tokens
Examples
Example 1: Prepending to Tokens
pythondef prepend_mod(token):
    return 'MOD_' + token

splitter = TokenSplitter()
text = "  @spaced   ?out  @?example  !command"
reconstructed, _ = splitter.process(text, prepend_mod)
print(reconstructed)
# Output: '  MOD_@spaced   MOD_?out  MOD_@?example  MOD_!command'
Example 2: No Modification
pythonsplitter = TokenSplitter()
text = "No markers here"
reconstructed, _ = splitter.process(text)
print(reconstructed)
# Output: 'No markers here'
Example 3: Handling Edge Cases

Empty string: Returns ('', [])
All whitespace: Preserves spaces (e.g., '   ' → ['   '])
Consecutive tokens: Splits correctly with empty/whitespace in between if present.
Lisp-like expressions: Properly isolates !CFL_TIME_OUT or @CFL_LOGM while keeping parentheses and args intact.

API Reference
TokenSplitter()

Initializes with default pattern r'((?:@\w+|!\w+|\?\w+|@\?\w+))'.

split(text: str) -> list[str]

Splits text into parts.

modify_tokens(parts: list[str], modify_func: callable) -> list[str]

Modifies tokens in parts using modify_func(token: str) -> str.

reconstruct(parts: list[str]) -> str

Joins parts into a string.

process(text: str, modify_func: callable = None) -> tuple[str, list[str]]

Full pipeline: split → (modify) → reconstruct.

Testing
Run the class with if __name__ == "__main__": for a quick demo:
bashpython token_splitter.py
Contributing
Feel free to fork and submit pull requests for enhancements, like additional patterns or token types.
License
MIT License - use freely!