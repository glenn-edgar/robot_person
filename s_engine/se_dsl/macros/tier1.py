"""Tier 1 macros — template macros with a fixed subtree shape.

Each macro is a Python function that composes lower-level DSL primitives
into a specific pattern. The engine sees the fully-expanded tree — there
is no runtime difference between a tree built by hand and one built by a
macro.
"""

from __future__ import annotations

from typing import Any, Optional

from se_dsl.primitives import (
    check_event,
    dict_eq,
    fork_join,
    if_then,
    if_then_else,
    state_inc_and_test,
    verify_and_check_elapsed_time,
)


def with_timeout(
    action: dict,
    seconds: float,
    on_timeout: dict,
    reset_on_timeout: bool = False,
) -> dict:
    """Run `action` with a timeout watchdog.

    The action runs in parallel with a `verify_and_check_elapsed_time`
    watchdog. If the watchdog fires before the action completes, `on_timeout`
    is invoked and the watchdog returns TERMINATE (or RESET). When the action
    completes normally the fork_join returns PIPELINE_DISABLE.

    Note: the watchdog currently self-terminates inside the fork_join rather
    than propagating TERMINATE up through the fork. For strict timeout-kills-
    the-whole-thing semantics, build with `fork_join` + a FUNCTION_TERMINATE
    return code leaf instead.
    """
    watchdog = verify_and_check_elapsed_time(
        on_error=on_timeout,
        timeout_seconds=seconds,
        reset=reset_on_timeout,
    )
    return fork_join(action, watchdog)


def guarded_action(predicate: dict, action: dict) -> dict:
    """Run `action` only if `predicate` evaluates True (re-evaluated each tick)."""
    return if_then(predicate, action)


def if_dict(key: str, value: Any, then_: dict, else_: Optional[dict] = None) -> dict:
    """Sugar for if_then_else with a dict_eq predicate."""
    return if_then_else(dict_eq(key, value), then_, else_)


def on_event(event_id: str, action: dict) -> dict:
    """Run `action` iff the current event is `event_id`."""
    return if_then(check_event(event_id), action)


def every_n_ticks(n: int, action: dict) -> dict:
    """Run `action` every Nth invocation via a node-local counter."""
    return if_then(state_inc_and_test(threshold=n), action)
