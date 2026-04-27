"""ct_dsl — fluent stateful builder (Model A) for ChainTree KBs.

The single public surface is the `ChainTree` class. Construct one, register
user fns, build KBs with `start_test` / `define_column` / `asm_*`, and call
`run(starting=[...])` to enter the main loop.
"""

from __future__ import annotations

from . import macros
from .builder import ChainTree

__all__ = ["ChainTree", "macros"]
