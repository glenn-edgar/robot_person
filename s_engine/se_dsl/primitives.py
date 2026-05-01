"""DSL primitive wrappers.

Each function here returns a fully-formed node dict via make_node(). The
Python name drops the `se_` prefix (namespaces replace prefixes); `while` is
renamed `while_loop` to avoid the Python keyword; `se_true` / `se_false`
become `true_pred` / `false_pred` to avoid shadowing built-in names.

Predicates that read the module dictionary use the `dict_*` naming (Option B
from the design discussion). Predicates that read node-local state keep the
`state_*` prefix.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from se_builtins import delays as _D
from se_builtins import dispatch as _DI
from se_builtins import flow_control as _F
from se_builtins import nested_call as _N
from se_builtins import oneshot as _O
from se_builtins import pred as _P
from se_builtins import return_codes as _R
from se_builtins import time_window as _TW
from se_builtins import verify as _V
from se_dsl import make_node


# ---------------------------------------------------------------------------
# Flow control
# ---------------------------------------------------------------------------

def sequence(*children) -> dict:
    return make_node(_F.se_sequence, "m_call", children=children)


def sequence_once(*children) -> dict:
    return make_node(_F.se_sequence_once, "m_call", children=children)


def function_interface(*children) -> dict:
    return make_node(_F.se_function_interface, "m_call", children=children)


def fork(*children) -> dict:
    return make_node(_F.se_fork, "m_call", children=children)


def fork_join(*children) -> dict:
    return make_node(_F.se_fork_join, "m_call", children=children)


def chain_flow(*children) -> dict:
    return make_node(_F.se_chain_flow, "m_call", children=children)


def while_loop(pred: dict, body: dict) -> dict:
    return make_node(_F.se_while, "m_call", children=[pred, body])


def if_then_else(pred: dict, then_: dict, else_: Optional[dict] = None) -> dict:
    children = [pred, then_] if else_ is None else [pred, then_, else_]
    return make_node(_F.se_if_then_else, "m_call", children=children)


def if_then(pred: dict, then_: dict) -> dict:
    """Sugar for if_then_else with no else branch."""
    return if_then_else(pred, then_, else_=None)


def case(pred: dict, action: dict) -> tuple:
    """Case helper for cond(); returns a (pred, action) tuple to be flattened."""
    return (pred, action)


def cond(*cases, default: Optional[dict] = None) -> dict:
    """Multi-branch conditional.

    Arguments are (pred, action) tuples from `case()` (or bare pred, action
    pairs). Optional `default` action runs if no pred matched.
    """
    children: list = []
    for c in cases:
        pred_node, action_node = c
        children.extend([pred_node, action_node])
    has_else = default is not None
    if has_else:
        children.append(default)
    return make_node(
        _F.se_cond, "m_call",
        params={"has_else": has_else},
        children=children,
    )


def trigger_on_change(
    pred: dict,
    rising: dict,
    falling: Optional[dict] = None,
    initial: int = 0,
) -> dict:
    children = [pred, rising] if falling is None else [pred, rising, falling]
    return make_node(
        _F.se_trigger_on_change, "m_call",
        params={"initial": initial},
        children=children,
    )


def on_rising_edge(pred: dict, action: dict, initial: int = 0) -> dict:
    return trigger_on_change(pred, action, falling=None, initial=initial)


def on_falling_edge(pred: dict, action: dict, initial: int = 1) -> dict:
    """Falling-edge only — `initial=1` so the first transition to 0 registers as falling.
    Pass a no-op as the rising action."""
    return trigger_on_change(pred, nop(), falling=action, initial=initial)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def event_dispatch(cases: Mapping[str, dict]) -> dict:
    """Route events by event_id to action children.

    `cases` is a mapping `{event_id_str: action_node}`.
    """
    children = list(cases.values())
    mapping = {event_id: idx for idx, event_id in enumerate(cases)}
    return make_node(
        _DI.se_event_dispatch, "m_call",
        params={"mapping": mapping},
        children=children,
    )


def state_machine(
    states: Mapping[str, dict],
    transitions: Mapping[tuple, str],
    initial: str,
) -> dict:
    """Named-state machine.

    `states`      : {state_name: action_node}
    `transitions` : {(current_state, event_id): next_state}
    `initial`     : starting state name
    """
    if initial not in states:
        raise ValueError(f"state_machine: initial state {initial!r} not in states")
    children = list(states.values())
    idx_map = {name: idx for idx, name in enumerate(states)}
    return make_node(
        _DI.se_state_machine, "m_call",
        params={
            "states": idx_map,
            "transitions": dict(transitions),
            "initial": initial,
        },
        children=children,
    )


def dict_dispatch(key: str, cases: Mapping[Any, dict]) -> dict:
    """Route by a dictionary value. `cases` is {dict_value: action_node}."""
    children = list(cases.values())
    mapping = {value: idx for idx, value in enumerate(cases)}
    return make_node(
        _DI.se_dict_dispatch, "m_call",
        params={"key": key, "mapping": mapping},
        children=children,
    )


# ---------------------------------------------------------------------------
# Predicates — composite
# ---------------------------------------------------------------------------

def pred_and(*preds) -> dict:
    return make_node(_P.pred_and, "p_call", children=preds)


def pred_or(*preds) -> dict:
    return make_node(_P.pred_or, "p_call", children=preds)


def pred_not(p: dict) -> dict:
    return make_node(_P.pred_not, "p_call", children=[p])


def pred_nor(*preds) -> dict:
    return make_node(_P.pred_nor, "p_call", children=preds)


def pred_nand(*preds) -> dict:
    return make_node(_P.pred_nand, "p_call", children=preds)


def pred_xor(*preds) -> dict:
    return make_node(_P.pred_xor, "p_call", children=preds)


# ---------------------------------------------------------------------------
# Predicates — constants
# ---------------------------------------------------------------------------

def true_pred() -> dict:
    return make_node(_P.true_pred, "p_call")


def false_pred() -> dict:
    return make_node(_P.false_pred, "p_call")


# ---------------------------------------------------------------------------
# Predicates — event
# ---------------------------------------------------------------------------

def check_event(event_id: str) -> dict:
    return make_node(_P.check_event, "p_call", params={"event_id": event_id})


# ---------------------------------------------------------------------------
# Predicates — dict comparison
# ---------------------------------------------------------------------------

def dict_eq(key: str, value: Any) -> dict:
    return make_node(_P.dict_eq, "p_call", params={"key": key, "value": value})


def dict_ne(key: str, value: Any) -> dict:
    return make_node(_P.dict_ne, "p_call", params={"key": key, "value": value})


def dict_gt(key: str, value: Any) -> dict:
    return make_node(_P.dict_gt, "p_call", params={"key": key, "value": value})


def dict_ge(key: str, value: Any) -> dict:
    return make_node(_P.dict_ge, "p_call", params={"key": key, "value": value})


def dict_lt(key: str, value: Any) -> dict:
    return make_node(_P.dict_lt, "p_call", params={"key": key, "value": value})


def dict_le(key: str, value: Any) -> dict:
    return make_node(_P.dict_le, "p_call", params={"key": key, "value": value})


def dict_in_range(key: str, min: Any, max: Any) -> dict:
    return make_node(
        _P.dict_in_range, "p_call",
        params={"key": key, "min": min, "max": max},
    )


# ---------------------------------------------------------------------------
# Predicates — counters
# ---------------------------------------------------------------------------

def dict_inc_and_test(key: str, threshold: int) -> dict:
    return make_node(
        _P.dict_inc_and_test, "p_call",
        params={"key": key, "threshold": threshold},
    )


def state_inc_and_test(threshold: int) -> dict:
    return make_node(
        _P.state_inc_and_test, "p_call",
        params={"threshold": threshold},
    )


# ---------------------------------------------------------------------------
# Delays
# ---------------------------------------------------------------------------

def time_delay(seconds: float) -> dict:
    return make_node(_D.se_time_delay, "m_call", params={"seconds": seconds})


def wait_event(event_id: str) -> dict:
    return make_node(_D.se_wait_event, "m_call", params={"event_id": event_id})


def wait(include_tick: bool = False) -> dict:
    return make_node(_D.se_wait, "m_call", params={"include_tick": include_tick})


def wait_timeout(event_id: str, seconds: float) -> dict:
    return make_node(
        _D.se_wait_timeout, "m_call",
        params={"event_id": event_id, "seconds": seconds},
    )


def nop() -> dict:
    return make_node(_D.se_nop, "m_call")


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify(pred: dict, on_error: dict, reset: bool = False) -> dict:
    return make_node(
        _V.se_verify, "m_call",
        params={"reset_flag": reset},
        children=[pred, on_error],
    )


def verify_and_check_elapsed_time(
    on_error: dict,
    timeout_seconds: float,
    reset: bool = False,
) -> dict:
    return make_node(
        _V.se_verify_and_check_elapsed_time, "m_call",
        params={"timeout_seconds": timeout_seconds, "reset_flag": reset},
        children=[on_error],
    )


def verify_and_check_elapsed_events(
    on_error: dict,
    target_event_id: str,
    max_count: int,
    reset: bool = False,
) -> dict:
    return make_node(
        _V.se_verify_and_check_elapsed_events, "m_call",
        params={
            "target_event_id": target_event_id,
            "max_count": max_count,
            "reset_flag": reset,
        },
        children=[on_error],
    )


# ---------------------------------------------------------------------------
# Oneshots
# ---------------------------------------------------------------------------

def log(message: str) -> dict:
    return make_node(_O.log, "o_call", params={"message": message})


def dict_log(message: str, key: str) -> dict:
    return make_node(_O.dict_log, "o_call", params={"message": message, "key": key})


def dict_set(key: str, value: Any) -> dict:
    return make_node(_O.dict_set, "o_call", params={"key": key, "value": value})


def dict_inc(key: str, delta: int = 1) -> dict:
    return make_node(_O.dict_inc, "o_call", params={"key": key, "delta": delta})


def queue_event(
    event_id: str,
    priority: str = "normal",
    data: Optional[Mapping[str, Any]] = None,
) -> dict:
    return make_node(
        _O.queue_event, "o_call",
        params={
            "event_id": event_id,
            "priority": priority,
            "data": dict(data) if data else {},
        },
    )


def dict_load(source: Mapping[str, Any]) -> dict:
    return make_node(_O.dict_load, "io_call", params={"source": dict(source)})


# ---------------------------------------------------------------------------
# Return-code leaves
# ---------------------------------------------------------------------------

def _rc(fn):
    return lambda: make_node(fn, "m_call")


return_continue = _rc(_R.return_continue)
return_halt = _rc(_R.return_halt)
return_terminate = _rc(_R.return_terminate)
return_reset = _rc(_R.return_reset)
return_disable = _rc(_R.return_disable)
return_skip_continue = _rc(_R.return_skip_continue)

return_function_continue = _rc(_R.return_function_continue)
return_function_halt = _rc(_R.return_function_halt)
return_function_terminate = _rc(_R.return_function_terminate)
return_function_reset = _rc(_R.return_function_reset)
return_function_disable = _rc(_R.return_function_disable)
return_function_skip_continue = _rc(_R.return_function_skip_continue)

return_pipeline_continue = _rc(_R.return_pipeline_continue)
return_pipeline_halt = _rc(_R.return_pipeline_halt)
return_pipeline_terminate = _rc(_R.return_pipeline_terminate)
return_pipeline_reset = _rc(_R.return_pipeline_reset)
return_pipeline_disable = _rc(_R.return_pipeline_disable)
return_pipeline_skip_continue = _rc(_R.return_pipeline_skip_continue)


# ---------------------------------------------------------------------------
# Time window — three operators, all sharing field-mask logic.
# Wall clock from module.get_wall_time(); local time via module.timezone.
# Window shape (uniform per-field masks across hour/minute/sec/dow/dom) and
# paired-or-absent rule documented in se_builtins/time_window.py.
# ---------------------------------------------------------------------------

def wait_until_in_time_window(
    start: Mapping[str, int],
    end: Mapping[str, int],
) -> dict:
    """m_call: HALT while wall clock OUT of the window; DISABLE on first tick IN.

    Drops into `chain_flow` / `sequence` for wait-shaped composition. To
    re-arm, RESET the surrounding parent.
    """
    return make_node(
        _TW.se_wait_until_in_time_window, "m_call",
        params={"start": dict(start), "end": dict(end)},
    )


def wait_until_out_of_time_window(
    start: Mapping[str, int],
    end: Mapping[str, int],
) -> dict:
    """m_call: HALT while wall clock IN the window; DISABLE on first tick OUT.

    Idiomatic: place after a one-shot action inside `chain_flow` / `sequence`
    so the action fires once per window crossing. Re-arm via parent RESET.
    """
    return make_node(
        _TW.se_wait_until_out_of_time_window, "m_call",
        params={"start": dict(start), "end": dict(end)},
    )


def in_time_window(
    start: Mapping[str, int],
    end: Mapping[str, int],
) -> dict:
    """p_call: True iff current local wall-clock time is in the window.

    Plug into `if_then_else`, `cond`, `state_machine` transition guards,
    `on_rising_edge`, etc. Use `pred_not(in_time_window(...))` for the
    inverse — no separate `out_of_time_window` predicate.
    """
    return make_node(
        _TW.se_in_time_window, "p_call",
        params={"start": dict(start), "end": dict(end)},
    )


# ---------------------------------------------------------------------------
# Nested tree call
# ---------------------------------------------------------------------------

def call_tree(target) -> dict:
    """Call another tree. `target` is either a tree dict or a name string."""
    if isinstance(target, str):
        params = {"tree_name": target}
    else:
        params = {"tree": target}
    return make_node(_N.se_call_tree, "m_call", params=params)
