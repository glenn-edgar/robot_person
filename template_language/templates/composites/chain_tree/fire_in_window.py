"""composites.chain_tree.fire_in_window — gate body on wall-clock window.

Wraps the canonical chain_tree "fire once per window entry" idiom from
`ct_builtins/time_window.py`:

    column <name>:
      asm_wait_until_in_time_window(start, end)    # HALT until in window
      <body splice>                                # fires once on entry
      asm_wait_until_out_of_time_window(start, end)# HALT until window closes

The column auto-disables once both wait leaves have completed and the
body has fired. To re-arm for the next window crossing, the surrounding
parent must RESET this column (subtree composition).

The chain_tree shape differs from the s_engine shape (which uses a
boolean flag + dict_eq + if_then). Per `template_design.txt` §4
(engine asymmetry), the same logical template name has different
bodies on each engine, registered at distinct ltree paths. The
s_engine version lives at composites.s_engine.fire_in_window.

Slots:
  name   required STRING — column name. Used at recording time as a
                           human-readable label and (when two
                           instantiations live in one template body) to
                           avoid the recorder's intra-template column-
                           name collision check. Cross-template column
                           collisions are handled by chain_tree itself
                           (`_mk_name` auto-suffixes), so two
                           instantiations across separate use_template
                           calls don't strictly need distinct names —
                           but distinct names still make logs and
                           op-list dumps readable.
  start  required DICT   — wall-clock window start (per-field semantics
                           per ct_builtins/time_window.py).
  end    required DICT   — wall-clock window end.
  body   required ACTION — zero-arg callable; its ct.* ops splice
                           between the two wait leaves and run once on
                           window entry.
"""

from __future__ import annotations

from typing import Callable

from template_language import ct, define_template


def fire_in_window(*, name: str, start: dict, end: dict, body: Callable):
    """Run `body` once each time the wall clock enters [start, end]."""
    ct.define_column(name)
    ct.asm_wait_until_in_time_window(start=start, end=end)
    body()
    ct.asm_wait_until_out_of_time_window(start=start, end=end)
    ct.end_column()


define_template(
    path="composites.chain_tree.fire_in_window",
    fn=fire_in_window,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "market_open_gate",
        "start": {"hour": 9, "minute": 30},
        "end": {"hour": 16, "minute": 0},
        "body": "lambda: ct.asm_log_message('market opened')",
    },
)
