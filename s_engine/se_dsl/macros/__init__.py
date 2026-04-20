"""DSL macros — compile-time helpers that return fully-expanded node dicts.

Tier 1: template macros. Fixed subtree shape with parameter slots.
Tier 2: pattern macros. Generate varying structure based on parameters.

Macros expand when the Python DSL function is called; the engine only ever
sees fully-expanded trees. This keeps the engine minimal and lets macros be
arbitrarily complex (full Python) without runtime cost.
"""

from se_dsl.macros.tier1 import (
    every_n_ticks,
    guarded_action,
    if_dict,
    on_event,
    with_timeout,
)
from se_dsl.macros.tier2 import (
    retry_with_backoff,
    state_machine_from_table,
)

__all__ = [
    # Tier 1
    "with_timeout", "guarded_action", "if_dict", "on_event", "every_n_ticks",
    # Tier 2
    "retry_with_backoff", "state_machine_from_table",
]
