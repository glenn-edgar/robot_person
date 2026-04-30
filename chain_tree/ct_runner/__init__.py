"""ct_runner — one-step command-line runner for chain_tree user scripts.

Public surface:

    from ct_runner import run_script, main
    run_script(path, var_name="chain_tree", starting=None) -> int

Or as a CLI:

    python -m ct_runner my_test.py [--var=name] [--starting=k1,k2]

The runner imports the user file as a module (executing its top-level
code, which constructs the `ChainTree` and builds its KBs), looks up the
ChainTree instance by attribute name, then calls `chain.run(...)`.

Exit codes:
  0 — clean completion (no active KBs left when run() returned)
  1 — runtime error: engine had active KBs left, or the user file
      raised, or the named attribute was missing / not a ChainTree.
"""

from __future__ import annotations

from .runner import main, run_script

__all__ = ["main", "run_script"]
