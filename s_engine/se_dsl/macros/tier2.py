"""Tier 2 macros — pattern macros that emit varying structure.

Unlike Tier 1 templates, these generate N elements or shape based on their
parameters. The emitted tree is still fully-expanded at DSL time.
"""

from __future__ import annotations

from typing import Callable, Iterable, Mapping, Tuple

from se_dsl.primitives import sequence, state_machine, time_delay


def retry_with_backoff(
    action_factory: Callable[[int], dict],
    attempts: int,
    base_delay_seconds: float,
) -> dict:
    """Generate a sequence of N retry attempts with exponential backoff.

    The action factory receives the attempt index (0, 1, 2, ...) and returns
    a fresh action node per attempt (so each attempt is a distinct subtree —
    sharing would cause state to leak between retries).

    Delays between attempts: base * 2^(i-1) for i >= 1.
    """
    if attempts < 1:
        raise ValueError("retry_with_backoff: attempts must be >= 1")
    if base_delay_seconds < 0:
        raise ValueError("retry_with_backoff: base_delay_seconds must be >= 0")

    children: list[dict] = []
    for i in range(attempts):
        if i > 0:
            delay = base_delay_seconds * (2 ** (i - 1))
            children.append(time_delay(delay))
        children.append(action_factory(i))
    return sequence(*children)


def state_machine_from_table(
    state_actions: Mapping[str, dict],
    transitions: Iterable[Tuple[str, str, str]],
    initial: str,
) -> dict:
    """Build a `state_machine` from a transition table.

    `state_actions`: {state_name: action_node} — every state, including any
                     that only appears as a transition target, must have an
                     action. This avoids the "whose action goes where?"
                     ambiguity of bundling the action into the transition tuple.

    `transitions`:   iterable of `(from_state, event_id, to_state)` triples.

    `initial`:       starting state name — must be a key in `state_actions`.
    """
    states = dict(state_actions)
    transition_map: dict[tuple, str] = {}
    for frm, ev, to in transitions:
        if frm not in states:
            raise ValueError(f"state_machine_from_table: no action for state {frm!r}")
        if to not in states:
            raise ValueError(f"state_machine_from_table: no action for state {to!r}")
        transition_map[(frm, ev)] = to

    if initial not in states:
        raise ValueError(f"state_machine_from_table: initial {initial!r} not in states")

    return state_machine(
        states=states,
        transitions=transition_map,
        initial=initial,
    )
