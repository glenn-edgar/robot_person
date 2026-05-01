"""leaves.chain_tree.print_hello — minimal demo leaf.

A single asm_log_message("hello") with no slots. The smallest possible
template; useful as a discovery target for LLM tests and as the
canonical "instantiate me to verify the template machinery works"
example.
"""

from __future__ import annotations

from template_language import ct, define_template


def print_hello():
    """Log the string 'hello' once."""
    ct.asm_log_message("hello")


define_template(
    path="leaves.chain_tree.print_hello",
    fn=print_hello,
    kind="leaf",
    engine="chain_tree",
)
