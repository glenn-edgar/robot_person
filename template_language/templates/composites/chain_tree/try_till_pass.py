"""composites.chain_tree.try_till_pass — sequence_til_pass wrapper.

Opens a `define_sequence_til_pass` frame, splices each child callable in
declared order, closes. Children take the sequence RecRef as their one
argument; pass it to `mark_link` (or other ops needing the sequence ref)
inside their bodies.

Sequence semantics: children run one at a time. The first child to mark
PASS makes the sequence pass and short-circuits remaining children. If
all children mark FAIL, the sequence fails. If a child completes without
marking, the sequence treats that as undefined (the engine's contract —
templates should mark explicitly via `mark_link`).

Slots:
  name         required STRING — sequence name.
  children     required LIST   — list of one-arg callables `(seq) -> None`.
                                  The seq RecRef is the value returned by
                                  define_sequence_til_pass.
  finalize_fn  optional STRING=None — registered one-shot fn name fired
                                       on sequence completion (passes or
                                       fails). None → no finalize.

`auto_start` is intentionally absent — sequences don't have a per-node
auto_start parameter. Wrap in `container(auto_start=False, ...)` if you
need startup gating.
"""

from __future__ import annotations

from typing import Optional

from template_language import ct, define_template


def try_till_pass(*, name: str, children: list,
                  finalize_fn: Optional[str] = None):
    """Open a sequence_til_pass; pass its RecRef to each child callable."""
    seq = ct.define_sequence_til_pass(name, finalize_fn=finalize_fn)
    for child in children:
        child(seq)
    ct.end_sequence_til_pass()
    return seq


define_template(
    path="composites.chain_tree.try_till_pass",
    fn=try_till_pass,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "login_attempts",
        "children": "[lambda seq: use_template('leaves.chain_tree.mark_link', "
                    "seq=seq, name='check', boolean_function=...)]",
    },
)
