"""project.coffee_maker.leaves.chain_tree.brew_log — project leaf.

Logs a `coffee_maker: <message>` line. Lives in the project layer
(not the system library) because every coffee_maker solution wants
the `coffee_maker:` prefix; pulling it into the project means the
solution file doesn't repeat the prefix at every call site, and the
prefix can change in one place.

Slot:
  message  required STRING — the body of the log line, prefixed
                              automatically with `coffee_maker: `.
"""

from __future__ import annotations

from template_language import ct, define_template


def brew_log(*, message: str):
    """Log a coffee_maker-prefixed message."""
    ct.asm_log_message(f"coffee_maker: {message}")


define_template(
    path="project.coffee_maker.leaves.chain_tree.brew_log",
    fn=brew_log,
    kind="leaf",
    engine="chain_tree",
    slot_examples={"message": "starting brew"},
)
