"""composites.chain_tree.am_pm_state_machine — three-state SM (initial/am/pm).

The `initial` state runs once at start, reads the wall clock via the engine
handle's `get_wall_time` callable, and posts CFL_CHANGE_STATE_EVENT to dispatch
to either `am` or `pm`. Optional slot callables are spliced into each state
column for caller-supplied side-effects (logging, terminating, etc.).

Slots:
  sm_name           required STRING — base name for the SM and its dispatch
                                       one-shot. Two instantiations need
                                       distinct names.
  initial_action    optional ACTION — runs in the initial state column
                                       before the dispatch one-shot fires.
  morning_action    optional ACTION — runs in the `am` state column.
  afternoon_action  optional ACTION — runs in the `pm` state column.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from ct_runtime import enqueue
from ct_runtime.codes import (
    CFL_CHANGE_STATE_EVENT,
    CFL_EVENT_TYPE_NULL,
    PRIORITY_HIGH,
)
from ct_runtime.event_queue import make_event

from template_language import ct, define_template


def am_pm_state_machine(
    *,
    sm_name: str,
    initial_action: Optional[Callable] = None,
    morning_action: Optional[Callable] = None,
    afternoon_action: Optional[Callable] = None,
):
    """Three-state SM that dispatches AM/PM by wall clock at startup."""

    def _decide_initial(handle, node):
        wall = handle["engine"]["get_wall_time"]()
        tz = handle["engine"].get("timezone")
        hour = datetime.fromtimestamp(wall, tz=tz).hour
        target = "am" if hour < 12 else "pm"
        sm_node = node["data"]["sm"]
        enqueue(handle["engine"], make_event(
            target=sm_node,
            event_type=CFL_EVENT_TYPE_NULL,
            event_id=CFL_CHANGE_STATE_EVENT,
            data={"sm_node": sm_node, "new_state": target},
            priority=PRIORITY_HIGH,
        ))

    ct.add_one_shot(f"{sm_name}_DECIDE", _decide_initial)

    sm = ct.define_state_machine(
        sm_name,
        state_names=["initial", "am", "pm"],
        initial_state="initial",
    )

    ct.define_state("initial")
    ct.asm_log_message(f"{sm_name} initial")
    if initial_action is not None:
        initial_action()
    ct.asm_one_shot(f"{sm_name}_DECIDE", data={"sm": sm})
    ct.end_state()

    ct.define_state("am")
    ct.asm_log_message(f"{sm_name} am")
    if morning_action is not None:
        morning_action()
    ct.end_state()

    ct.define_state("pm")
    ct.asm_log_message(f"{sm_name} pm")
    if afternoon_action is not None:
        afternoon_action()
    ct.end_state()

    ct.end_state_machine()
    return sm


define_template(
    path="composites.chain_tree.am_pm_state_machine",
    fn=am_pm_state_machine,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "sm_name": "time_of_day_sm",
        "morning_action": "lambda: ct.asm_log_message('morning')",
        "afternoon_action": "lambda: ct.asm_log_message('afternoon')",
    },
)
