"""DSL layer — functions that return tree-node dicts.

The engine only ever sees fully-expanded trees; macros expand at DSL-emit
time. Every DSL function builds on `make_node()` so that required fields
are always present. Each call produces a fresh dict tree — never share
mutable node dicts across calls (see spec §Macro Hygiene).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Optional

_VALID_CALL_TYPES = frozenset({"m_call", "o_call", "io_call", "p_call"})


def make_node(
    fn: Callable,
    call_type: str,
    params: Optional[Mapping[str, Any]] = None,
    children: Optional[Iterable[dict]] = None,
) -> dict:
    """Build a node dict with all dispatch-managed fields at their defaults."""
    if call_type not in _VALID_CALL_TYPES:
        raise ValueError(
            f"make_node: call_type must be one of {sorted(_VALID_CALL_TYPES)}, got {call_type!r}"
        )
    return {
        "fn": fn,
        "call_type": call_type,
        "params": dict(params) if params else {},
        "children": list(children) if children else [],
        "active": True,
        "initialized": False,
        "ever_init": False,
        "state": 0,
        "user_data": None,
    }


# Re-export the primitive surface + macros
from se_dsl.primitives import (  # noqa: E402
    # Flow control
    sequence, sequence_once, function_interface, fork, fork_join, chain_flow,
    while_loop, if_then_else, if_then, cond, case,
    trigger_on_change, on_rising_edge, on_falling_edge,
    # Dispatch
    event_dispatch, state_machine, dict_dispatch,
    # Predicates
    pred_and, pred_or, pred_not, pred_nor, pred_nand, pred_xor,
    true_pred, false_pred,
    check_event,
    dict_eq, dict_ne, dict_gt, dict_ge, dict_lt, dict_le,
    dict_in_range, dict_inc_and_test, state_inc_and_test,
    # Delays
    time_delay, wait_event, wait, wait_timeout, nop,
    # Verify
    verify, verify_and_check_elapsed_time, verify_and_check_elapsed_events,
    # Oneshots
    log, dict_log, dict_set, dict_inc, queue_event, dict_load,
    # Return codes
    return_continue, return_halt, return_terminate, return_reset,
    return_disable, return_skip_continue,
    return_function_continue, return_function_halt, return_function_terminate,
    return_function_reset, return_function_disable, return_function_skip_continue,
    return_pipeline_continue, return_pipeline_halt, return_pipeline_terminate,
    return_pipeline_reset, return_pipeline_disable, return_pipeline_skip_continue,
    # Time window
    time_window_check,
    # Nested
    call_tree,
)
from se_dsl.macros import (  # noqa: E402
    with_timeout, guarded_action, if_dict, on_event, every_n_ticks,
    retry_with_backoff, state_machine_from_table,
)

__all__ = [
    "make_node",
    # Flow control
    "sequence", "sequence_once", "function_interface",
    "fork", "fork_join", "chain_flow",
    "while_loop", "if_then_else", "if_then", "cond", "case",
    "trigger_on_change", "on_rising_edge", "on_falling_edge",
    # Dispatch
    "event_dispatch", "state_machine", "dict_dispatch",
    # Predicates
    "pred_and", "pred_or", "pred_not", "pred_nor", "pred_nand", "pred_xor",
    "true_pred", "false_pred",
    "check_event",
    "dict_eq", "dict_ne", "dict_gt", "dict_ge", "dict_lt", "dict_le",
    "dict_in_range", "dict_inc_and_test", "state_inc_and_test",
    # Delays
    "time_delay", "wait_event", "wait", "wait_timeout", "nop",
    # Verify
    "verify", "verify_and_check_elapsed_time", "verify_and_check_elapsed_events",
    # Oneshots
    "log", "dict_log", "dict_set", "dict_inc", "queue_event", "dict_load",
    # Return codes (18)
    "return_continue", "return_halt", "return_terminate", "return_reset",
    "return_disable", "return_skip_continue",
    "return_function_continue", "return_function_halt", "return_function_terminate",
    "return_function_reset", "return_function_disable", "return_function_skip_continue",
    "return_pipeline_continue", "return_pipeline_halt", "return_pipeline_terminate",
    "return_pipeline_reset", "return_pipeline_disable", "return_pipeline_skip_continue",
    # Time window
    "time_window_check",
    # Nested
    "call_tree",
    # Macros
    "with_timeout", "guarded_action", "if_dict", "on_event", "every_n_ticks",
    "retry_with_backoff", "state_machine_from_table",
]
