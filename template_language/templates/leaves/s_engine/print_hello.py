"""leaves.s_engine.print_hello — minimal demo leaf for s_engine.

Returns a single `log("hello")` node. The smallest possible s_engine
template; mirror of `leaves.chain_tree.print_hello` but lives at a
distinct ltree path because the engines have non-isomorphic primitive
surfaces.
"""

from __future__ import annotations

from template_language import ct, define_template


def print_hello():
    """Return a `log('hello')` node — runtime emits 'hello' once."""
    return ct.log("hello")


define_template(
    path="leaves.s_engine.print_hello",
    fn=print_hello,
    kind="leaf",
    engine="s_engine",
)
