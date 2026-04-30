"""Parametric subtree helpers — Python functions that emit DSL fragments.

Each macro takes a `ChainTree` builder as the first arg (`ct`) and calls
existing `define_*` / `asm_*` methods to insert a subtree at the current
builder position. Expansion is at build time — no runtime templates.

Available macros:
  repeat_n              — run a one-shot N times with optional wait between
  every_n_seconds       — run a one-shot every N seconds, forever (until
                          parent terminates)
  timeout_wrap          — wrap an action block in an exception+heartbeat
                          timeout, with optional on_timeout one-shot
  guarded_action        — run a one-shot only if a predicate boolean
                          returns True
  wait_then_act         — wait for N events of a given id, then fire a
                          one-shot
  retry_until_success   — try N attempts of an action; sequence_til_pass
                          stops on the first marked-pass attempt
  state_machine_from_table
                        — build an SM from a flat (state, event, next,
                          action) tuple list

These are meant as starting points — copy/extend them rather than treating
them as a stable API. The whole point of "macros = Python functions" is
that the user can write their own without engine support.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence, Tuple


def repeat_n(
    ct,
    name: str,
    action_one_shot: str,
    count: int,
    between_seconds: float = 0.0,
    action_data: Optional[dict] = None,
) -> dict:
    """N-times executor. Emits a column with `count` copies of
    `asm_one_shot(action_one_shot, action_data)`, separated by
    `asm_wait_time(between_seconds)` if `between_seconds > 0`.
    """
    if count <= 0:
        raise ValueError("repeat_n: count must be positive")
    col = ct.define_column(name)
    for i in range(count):
        ct.asm_one_shot(action_one_shot, action_data)
        if between_seconds > 0 and i < count - 1:
            ct.asm_wait_time(between_seconds)
    ct.end_column()
    return col


def every_n_seconds(
    ct,
    name: str,
    action_one_shot: str,
    period_seconds: float,
    action_data: Optional[dict] = None,
) -> dict:
    """Periodic forever: action → wait → reset (re-enables this column)
    → action again. The parent terminates the column (e.g. via a sibling
    asm_terminate or external CFL_TERMINATE_SYSTEM event) to stop the loop.
    """
    if period_seconds < 0:
        raise ValueError("every_n_seconds: period must be non-negative")
    col = ct.define_column(name)
    ct.asm_one_shot(action_one_shot, action_data)
    if period_seconds > 0:
        ct.asm_wait_time(period_seconds)
    ct.asm_reset()
    ct.end_column()
    return col


def timeout_wrap(
    ct,
    name: str,
    build_main: Callable,
    timeout_ticks: int,
    on_timeout: Optional[str] = None,
    on_finalize: Optional[str] = None,
    logging_fn: Optional[str] = None,
) -> dict:
    """Wrap an action in an exception handler with heartbeat-driven
    timeout. `build_main(ct)` is invoked to populate the MAIN column
    BETWEEN the heartbeat-on leaf and the end. If the action takes longer
    than `timeout_ticks` timer ticks without sending a heartbeat, RECOVERY
    runs `on_timeout` (if set), then FINALIZE runs `on_finalize` (if set).
    """
    if timeout_ticks <= 0:
        raise ValueError("timeout_wrap: timeout_ticks must be positive")
    handler = ct.define_exception_handler(name, logging_fn=logging_fn or "CFL_NULL")
    ct.define_main_column()
    ct.asm_turn_heartbeat_on(timeout=timeout_ticks)
    build_main(ct)
    ct.end_main_column()
    ct.define_recovery_column()
    if on_timeout:
        ct.asm_one_shot(on_timeout)
    ct.end_recovery_column()
    ct.define_finalize_column()
    if on_finalize:
        ct.asm_one_shot(on_finalize)
    ct.end_finalize_column()
    ct.end_exception_handler()
    return handler


def guarded_action(
    ct,
    predicate_fn: str,
    action_one_shot: str,
    action_data: Optional[dict] = None,
    error_fn: Optional[str] = None,
) -> None:
    """Run the action only if `predicate_fn` returns True. If False:
    optional `error_fn` fires, then the parent column TERMINATEs (the
    standard CFL_VERIFY semantic).
    """
    ct.asm_verify(predicate_fn, error_fn=error_fn or "CFL_NULL")
    ct.asm_one_shot(action_one_shot, action_data)


def wait_then_act(
    ct,
    event_id: str,
    action_one_shot: str,
    count: int = 1,
    action_data: Optional[dict] = None,
) -> None:
    """Wait for `count` occurrences of `event_id`, then fire the action.
    Common reactive idiom (e.g. wait for a sensor reading, then process).
    """
    ct.asm_wait_for_event(event_id=event_id, count=count)
    ct.asm_one_shot(action_one_shot, action_data)


def retry_until_success(
    ct,
    name: str,
    attempt_one_shot: str,
    success_predicate_fn: str,
    max_attempts: int = 3,
    between_seconds: float = 0.0,
    attempt_data: Optional[dict] = None,
    finalize_fn: Optional[str] = None,
) -> dict:
    """Try `attempt_one_shot` up to `max_attempts` times; stop on the
    first attempt for which `success_predicate_fn` returns True.

    Implementation: a `sequence_til_pass` whose children are step columns
    each running [attempt_one_shot, asm_mark_sequence_if(predicate)].
    The mark leaf probes the predicate at INIT time and marks the
    sequence's current child as pass-or-fail accordingly; sequence_til
    short-circuits on the first marked-pass attempt and advances to the
    next child on a marked-fail.

    `between_seconds` inserts an `asm_wait_time` between attempts (no
    wait after the last attempt — nothing left to wait for).

    Returns the sequence_til_pass node ref.
    """
    if max_attempts <= 0:
        raise ValueError("retry_until_success: max_attempts must be positive")

    seq = ct.define_sequence_til_pass(name, finalize_fn=finalize_fn)
    for i in range(max_attempts):
        ct.define_column(f"{name}_attempt_{i}")
        ct.asm_one_shot(attempt_one_shot, attempt_data)
        ct.asm_mark_sequence_if(seq, success_predicate_fn)
        ct.end_column()
        if between_seconds > 0 and i < max_attempts - 1:
            ct.asm_wait_time(between_seconds)
    ct.end_sequence_til_pass()
    return seq


def state_machine_from_table(
    ct,
    name: str,
    transitions: Sequence[Tuple[str, str, str, Optional[str]]],
    initial_state: str,
    auto_start: bool = True,
) -> dict:
    """Build an `define_state_machine` block from a flat transition table.

    `transitions` is a sequence of `(from_state, event_id, to_state,
    action_one_shot)` tuples. `action_one_shot` may be None or the
    sentinel "CFL_NULL" — only registered names produce an asm_one_shot
    leaf. Each unique state from-from-to gets a state column whose body
    is one `asm_wait_for_event(event_id) → action → asm_change_state`
    triple per outgoing transition.

    When a state has multiple outgoing transitions on different events,
    the column waits for each in order; the first to fire wins (the
    transition fires its asm_change_state which terminates the column).
    Equivalent semantics to LuaJIT's CFL state-machine `transitions`
    table param, with the wait+change_state expansion done at DSL
    emit time.

    Returns the SM node ref.
    """
    # Collect declared states in first-seen order, plus their outgoing
    # transitions.
    states: list = []
    outgoing: dict = {}
    for frm, ev, to, action in transitions:
        for s in (frm, to):
            if s not in outgoing:
                outgoing[s] = []
                states.append(s)
        outgoing[frm].append((ev, to, action))

    if initial_state not in outgoing:
        raise ValueError(
            f"state_machine_from_table: initial_state {initial_state!r} "
            f"is not part of any transition (states: {states!r})"
        )

    sm = ct.define_state_machine(
        name,
        state_names=states,
        initial_state=initial_state,
        auto_start=auto_start,
    )
    for s in states:
        ct.define_state(s)
        for ev, to, action in outgoing[s]:
            ct.asm_wait_for_event(event_id=ev, count=1)
            if action and action != "CFL_NULL":
                ct.asm_one_shot(action)
            ct.asm_change_state(sm, to)
        ct.end_state()
    ct.end_state_machine()
    return sm
