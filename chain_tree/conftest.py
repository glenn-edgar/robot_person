"""Root conftest: add this directory to sys.path so tests can import the
top-level packages (ct_runtime, and future ct_builtins / ct_dsl / ct_bridge)
without requiring PYTHONPATH to be set. Matches the s_engine convention of
treating each subpackage as its own top-level module.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
