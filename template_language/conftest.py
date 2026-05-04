"""Test bootstrap.

  - sys.path: add parent dir + chain_tree (mirrors chain_tree's own
    conftest convention) so tests can `import template_language`,
    `import ct_dsl`, `import ct_runtime`, etc.

  - `_clean_registry` (autouse, function-scoped): clears the template
    registry before AND after each test. Tests that need a template
    register it explicitly (or rely on the lazy-loader fallback in
    `get_template`, which imports the conventional file on demand).
    No more conftest-hardcoded "always-on" template list.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_here)
_chain_tree = os.path.join(_parent, "chain_tree")

for p in (_parent, _chain_tree):
    if p not in sys.path:
        sys.path.insert(0, p)


import pytest  # noqa: E402

from template_language.registry import _registry, _reset_roots  # noqa: E402
from template_language.recorder import _recorder_stack  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_registry():
    _registry.clear()
    _recorder_stack.clear()
    _reset_roots()
    yield
    _registry.clear()
    _recorder_stack.clear()
    _reset_roots()
