"""Test bootstrap for the farm_soil robot.

Adds repo + chain_tree + robots to sys.path so pytest can import both
`template_language` and `farm_soil`. The autouse fixture clears the
registry, recorder stack, and template roots before+after each test,
then re-bootstraps the project root, so each test starts from a
deterministic "default root + farm_soil root" state.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_robots = os.path.dirname(_here)
_repo = os.path.dirname(_robots)

for p in (_repo, os.path.join(_repo, "chain_tree"), _robots):
    if p not in sys.path:
        sys.path.insert(0, p)


import pytest  # noqa: E402

from template_language.recorder import _recorder_stack  # noqa: E402
from template_language.registry import _registry, _reset_roots  # noqa: E402

from farm_soil.bootstrap import bootstrap  # noqa: E402
from user_templates.bootstrap import bootstrap as u_bootstrap  # noqa: E402


def _evict_project_modules():
    """Drop farm_soil.templates.* and template_language.templates.* from
    sys.modules so define_template re-runs after _registry.clear()."""
    to_drop = [m for m in sys.modules
               if m.startswith("farm_soil.templates.")
               or m.startswith("template_language.templates.")
               or m.startswith("user_templates.templates.")]
    for m in to_drop:
        del sys.modules[m]


@pytest.fixture(autouse=True)
def _setup():
    _registry.clear()
    _recorder_stack.clear()
    _reset_roots()
    _evict_project_modules()
    bootstrap()
    u_bootstrap()
    yield
    _registry.clear()
    _recorder_stack.clear()
    _reset_roots()
    _evict_project_modules()
