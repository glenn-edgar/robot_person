"""Builtin operators + a central registry for deserialization.

`BUILTIN_REGISTRY` maps every public builtin fn name to its callable. It is
the default lookup for `deserialize_tree` and the base of the module-level
`fn_registry` that user code merges their own fns into.

Each submodule lists its public fns in `_PUBLIC` so the registry is explicit
(no accidental exposure of internal helpers like `_maker`).
"""

from __future__ import annotations

from typing import Callable, Dict

from se_builtins import (
    delays,
    dispatch,
    flow_control,
    nested_call,
    oneshot,
    pred,
    return_codes,
    time_window,
    verify,
)

_FLOW_CONTROL = (
    "se_sequence", "se_sequence_once", "se_function_interface",
    "se_fork", "se_fork_join", "se_chain_flow",
    "se_while", "se_if_then_else", "se_cond", "se_trigger_on_change",
)

_DISPATCH = ("se_event_dispatch", "se_state_machine", "se_dict_dispatch")

_PRED = (
    "pred_and", "pred_or", "pred_not", "pred_nor", "pred_nand", "pred_xor",
    "true_pred", "false_pred", "check_event",
    "dict_eq", "dict_ne", "dict_gt", "dict_ge", "dict_lt", "dict_le",
    "dict_in_range", "dict_inc_and_test", "state_inc_and_test",
)

_DELAYS = ("se_time_delay", "se_wait_event", "se_wait", "se_wait_timeout", "se_nop")

_VERIFY = (
    "se_verify",
    "se_verify_and_check_elapsed_time",
    "se_verify_and_check_elapsed_events",
)

_ONESHOT = ("log", "dict_log", "dict_set", "dict_inc", "queue_event", "dict_load")

_RETURN_CODES = (
    "return_continue", "return_halt", "return_terminate", "return_reset",
    "return_disable", "return_skip_continue",
    "return_function_continue", "return_function_halt", "return_function_terminate",
    "return_function_reset", "return_function_disable", "return_function_skip_continue",
    "return_pipeline_continue", "return_pipeline_halt", "return_pipeline_terminate",
    "return_pipeline_reset", "return_pipeline_disable", "return_pipeline_skip_continue",
)

_NESTED = ("se_call_tree",)

_TIME_WINDOW = (
    "se_wait_until_in_time_window",
    "se_wait_until_out_of_time_window",
    "se_in_time_window",
)


def _collect() -> Dict[str, Callable]:
    registry: Dict[str, Callable] = {}
    for mod, names in (
        (flow_control, _FLOW_CONTROL),
        (dispatch, _DISPATCH),
        (pred, _PRED),
        (delays, _DELAYS),
        (verify, _VERIFY),
        (oneshot, _ONESHOT),
        (return_codes, _RETURN_CODES),
        (nested_call, _NESTED),
        (time_window, _TIME_WINDOW),
    ):
        for name in names:
            obj = getattr(mod, name, None)
            if obj is None:
                raise ImportError(f"se_builtins: expected {name!r} in {mod.__name__}")
            registry[name] = obj
    return registry


BUILTIN_REGISTRY: Dict[str, Callable] = _collect()

__all__ = [
    "BUILTIN_REGISTRY",
    "flow_control", "dispatch", "pred", "delays",
    "verify", "oneshot", "return_codes", "nested_call", "time_window",
]
