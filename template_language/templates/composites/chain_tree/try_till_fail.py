"""composites.chain_tree.try_till_fail — sequence_til_fail wrapper.

Opens a `define_sequence_til_fail` frame, splices each child callable in
declared order, closes. Children take the sequence RecRef as their one
argument; pass it to `mark_link` (or other ops needing the sequence ref)
inside their bodies.

Sequence semantics: children run one at a time. The first child to mark
FAIL makes the sequence fail and short-circuits remaining children. If
all children mark PASS, the sequence passes.

Mirror of `try_till_pass`; the difference is the underlying engine
primitive's pass/fail bias. Use `try_till_fail` when "all checks must
pass" is the success criterion.

Slots:
  name         required STRING — sequence name.
  children     required LIST   — list of one-arg callables `(seq) -> None`.
  finalize_fn  optional STRING=None — registered one-shot fn name fired
                                       on completion.

`auto_start` is intentionally absent — see `try_till_pass` docstring.
"""

from __future__ import annotations

from typing import Optional

from template_language import ct, define_template


def try_till_fail(*, name: str, children: list,
                  finalize_fn: Optional[str] = None):
    """Open a sequence_til_fail; pass its RecRef to each child callable."""
    seq = ct.define_sequence_til_fail(name, finalize_fn=finalize_fn)
    for child in children:
        child(seq)
    ct.end_sequence_til_fail()
    return seq


define_template(
    path="composites.chain_tree.try_till_fail",
    fn=try_till_fail,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "preflight_checks",
        "children": "[lambda seq: use_template('leaves.chain_tree.mark_link', "
                    "seq=seq, name='check', boolean_function=...)]",
    },
)
