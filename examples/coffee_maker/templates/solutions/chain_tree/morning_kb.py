"""project.coffee_maker.solutions.chain_tree.morning_kb — main solution.

Coffee maker daily routine. The system library's
`composites.chain_tree.am_pm_state_machine` dispatches by wall clock
at startup; the AM branch logs a "brewing coffee" step, the PM
branch logs a "descaling unit" step. Both branches reuse the
project-local `brew_log` leaf so the `coffee_maker:` prefix is
defined once.

Demonstrates the three-layer model end-to-end:
  - SYSTEM: `composites.chain_tree.am_pm_state_machine` — generic SM
            shape (cross-project).
  - PROJECT: `project.coffee_maker.leaves.chain_tree.brew_log` —
            reused in two action slots within this solution.
  - INLINE: `lambda: ct.asm_log_message("coffee_maker: powering on")`
            — one-off startup line, no reuse.

Slot:
  kb_name  required STRING — name for the surrounding KB and base for
                              the SM name.
"""

from __future__ import annotations

from template_language import ct, define_template, use_template


def morning_kb(*, kb_name: str):
    """Build a coffee_maker KB. AM brews, PM descales."""
    ct.start_test(kb_name)
    use_template(
        "composites.chain_tree.am_pm_state_machine",
        sm_name=f"{kb_name}_sm",
        initial_action=lambda: ct.asm_log_message("coffee_maker: powering on"),
        morning_action=lambda: use_template(
            "project.coffee_maker.leaves.chain_tree.brew_log",
            message="brewing coffee",
        ),
        afternoon_action=lambda: use_template(
            "project.coffee_maker.leaves.chain_tree.brew_log",
            message="descaling unit",
        ),
    )
    ct.end_test()


define_template(
    path="project.coffee_maker.solutions.chain_tree.morning_kb",
    fn=morning_kb,
    kind="solution",
    engine="chain_tree",
    slot_examples={"kb_name": "kitchen"},
)
