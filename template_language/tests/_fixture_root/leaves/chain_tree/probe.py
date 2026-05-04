"""Fixture template for multi-root tests.

Registers under the ltree path `project.fixture.leaves.chain_tree.probe`,
demonstrating that a non-default root with prefix `project.fixture`
maps the relative path `leaves.chain_tree.probe` back to this module.
"""

from __future__ import annotations

from template_language import ct, define_template


def probe():
    """Log the string 'probe' once."""
    ct.asm_log_message("probe")


define_template(
    path="project.fixture.leaves.chain_tree.probe",
    fn=probe,
    kind="leaf",
    engine="chain_tree",
)
