"""leaves.chain_tree.mark_link — predicate-driven sequence pass/fail mark.

Wraps the chain_tree primitive `asm_mark_sequence_if` with the user-fn
registration step so a template author supplies a Python callable
directly (no separate `add_boolean` step).

The leaf is a one-shot. At INIT time the engine calls
`boolean_function(handle, node, event_type, event_id, event_data)` and
records the result on the parent sequence:
  - True  → sequence_til_pass passes immediately; sequence_til_fail
            continues to the next child
  - False → sequence_til_fail fails immediately; sequence_til_pass
            continues to the next child

`boolean_function_data` is stored in the leaf's node["data"] (under the
`true_data` and `false_data` slots of the underlying primitive — same
dict in both, so the predicate can read it via `node["data"]["true_data"]`
regardless of outcome). Same convention as other leaves' config dicts
(asm_wait_time's time_delay, asm_verify's error_data).

Slots:
  seq                    required RECREF  — RecRef from the enclosing
                                             try_till_pass / try_till_fail
                                             frame. Pass it via the
                                             children-as-callbacks pattern.
  name                   required STRING  — boolean-fn registration name;
                                             must be unique. Slot-derived
                                             to avoid collisions when the
                                             template is instantiated more
                                             than once.
  boolean_function       required ENGINE_BOOLEAN — the predicate.
  boolean_function_data  optional DICT=None — payload available to the
                                             predicate via node["data"].
"""

from __future__ import annotations

from typing import Callable, Optional

from template_language import Kind, ct, define_template


def mark_link(
    *,
    seq: Kind.RECREF,
    name: str,
    boolean_function: Kind.ENGINE_BOOLEAN,
    boolean_function_data: Optional[dict] = None,
):
    """Probe `boolean_function` once at INIT; mark enclosing sequence."""
    ct.add_boolean(name, boolean_function)
    ct.asm_mark_sequence_if(
        seq, name,
        true_data=boolean_function_data,
        false_data=boolean_function_data,
    )


define_template(
    path="leaves.chain_tree.mark_link",
    fn=mark_link,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "login_check",
        "boolean_function": "lambda h, n, et, eid, ed: "
                            "n['data']['true_data'].get('ok', False)",
        "boolean_function_data": {"ok": True, "attempt": 1},
    },
)
