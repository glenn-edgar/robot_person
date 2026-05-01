"""composites.chain_tree.state_machine — generic state machine.

Generalizes the `am_pm_state_machine` shape: caller supplies a list of
(state_name, body_callable) pairs plus the initial state. Each body is
a zero-arg callable whose `ct.*` ops splice into the state's column.

Slots:
  name           required STRING — SM name (passed to define_state_machine).
                                     Slot-derived to avoid collisions with
                                     other SMs in the same recording.
  states         required LIST — list of (state_name: str, body: Callable)
                                  tuples. Order is preserved; the recorder
                                  catches duplicate state names per SM.
  initial_state  required STRING — must appear in `states`. The engine
                                    raises at builder/init time if not.
  auto_start     optional BOOL = True — passed through to
                                          define_state_machine(auto_start=...).
"""

from __future__ import annotations

from typing import Callable

from template_language import ct, define_template


def state_machine(*, name: str, states: list, initial_state: str,
                  auto_start: bool = True):
    """Build a state machine from a list of (state_name, body) tuples."""
    state_names = [pair[0] for pair in states]
    sm = ct.define_state_machine(
        name,
        state_names=state_names,
        initial_state=initial_state,
        auto_start=auto_start,
    )
    for state_name, body in states:
        ct.define_state(state_name)
        body()
        ct.end_state()
    ct.end_state_machine()
    return sm


define_template(
    path="composites.chain_tree.state_machine",
    fn=state_machine,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "time_of_day_sm",
        "states": "[('idle', lambda: ct.asm_log_message('idle')), "
                  "('active', lambda: ct.asm_log_message('active'))]",
        "initial_state": "idle",
    },
)
