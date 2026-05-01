"""composites.s_engine.fire_in_window — gate body on wall-clock window.

s_engine variant of `composites.chain_tree.fire_in_window`. Distinct
ltree path; non-isomorphic body. Per `template_design.txt` §4 (engine
asymmetry), the same logical template name has different bodies on each
engine.

s_engine's primitive surface includes `in_time_window` — a `p_call`
predicate that returns True iff the wall clock is inside the configured
window — and `if_then(pred, then_)`. Composing them yields:

    if_then(
        pred=in_time_window(start, end),
        then_=<body>,
    )

The body is evaluated only on ticks where the predicate is True.

Slots:
  start  required DICT   — wall-clock window start (per-field semantics
                           per `s_engine/se_builtins/time_window.py`).
  end    required DICT   — wall-clock window end.
  body   required ACTION — zero-arg callable that returns a node RecRef
                           (the tree slotted into the `then_` branch).
                           Differs from the chain_tree ACTION slot:
                           s_engine bodies *return* their tree, not just
                           splice ops.
"""

from __future__ import annotations

from typing import Callable

from template_language import ct, define_template


def fire_in_window(*, start: dict, end: dict, body: Callable):
    """Return an `if_then` node that gates `body` on the wall-clock window."""
    return ct.if_then(
        pred=ct.in_time_window(start=start, end=end),
        then_=body(),
    )


define_template(
    path="composites.s_engine.fire_in_window",
    fn=fire_in_window,
    kind="composite",
    engine="s_engine",
    slot_examples={
        "start": {"hour": 9, "minute": 30},
        "end": {"hour": 16, "minute": 0},
        "body": "lambda: ct.log('market opened')",
    },
)
