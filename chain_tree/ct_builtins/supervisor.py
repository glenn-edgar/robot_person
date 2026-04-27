"""Erlang/OTP-style supervisor.

Watches a fixed set of children. When any child disables, applies a
restart policy:

  ONE_FOR_ONE   — restart only the failed child; other siblings keep running.
  ONE_FOR_ALL   — terminate every still-running sibling, then restart all.
  REST_FOR_ALL  — terminate and restart the failed child plus every sibling
                  declared *after* it (preserving declaration order).

Restarts can be rate-limited via a monotonic-time sliding window: at most
`max_reset_number` restarts per `reset_window` seconds. Exceeding the
limit fires the optional finalize one-shot and disables the supervisor.

node["data"] schema:
    {
        "auto_start":            bool,
        "termination_type":      "ONE_FOR_ONE" | "ONE_FOR_ALL" | "REST_FOR_ALL",
        "restart_enabled":       bool,         # False → never restart, just DISABLE on first failure
        "reset_limited_enabled": bool,         # True → enforce max_reset_number/reset_window
        "max_reset_number":      int,
        "reset_window":          float,        # seconds (monotonic)
        "finalize_fn":           str,          # one-shot, "CFL_NULL" = none
        "user_data":             Any,
    }

node["ct_control"]["supervisor_state"]:
    {
        "reset_count":     int,                # total restarts since init
        "failure_counter": SupervisorFailureCounter,
    }
"""

from __future__ import annotations

from collections import deque
from typing import Callable

from ct_runtime import enable_node, terminate_node_tree
from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_TIMER_EVENT,
)
from ct_runtime.registry import lookup_boolean, lookup_one_shot


# ---------------------------------------------------------------------------
# Sliding-window failure counter
# ---------------------------------------------------------------------------

class SupervisorFailureCounter:
    """Monotonic-time sliding-window failure counter.

    Records failure timestamps in a deque; queries purge stale entries
    older than `window` seconds. Use `record_failure()` per restart and
    `is_threshold_exceeded(max_n)` to check the rate limit.

    Time is read from a caller-supplied callable (defaults to
    `time.monotonic`) so tests can inject a stub clock.
    """

    def __init__(self, window: float, get_time: Callable[[], float] = None):
        import time as _time
        self._window = float(window)
        self._get_time = get_time or _time.monotonic
        self._failures: deque = deque()

    def record_failure(self) -> None:
        self._failures.append(self._get_time())

    def record_success(self) -> None:
        # Not part of the "exceeded" calculation but kept for parity with
        # the yaml port's API.
        pass

    def _purge(self) -> None:
        cutoff = self._get_time() - self._window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def get_failure_count(self) -> int:
        self._purge()
        return len(self._failures)

    def is_threshold_exceeded(self, max_n: int) -> bool:
        return self.get_failure_count() >= int(max_n)

    def reset(self) -> None:
        self._failures.clear()


# ---------------------------------------------------------------------------
# Main / init / term
# ---------------------------------------------------------------------------

_VALID_POLICIES = ("ONE_FOR_ONE", "ONE_FOR_ALL", "REST_FOR_ALL")


def cfl_supervisor_init(handle, node) -> None:
    policy = node["data"].get("termination_type", "ONE_FOR_ONE")
    if policy not in _VALID_POLICIES:
        raise ValueError(
            f"CFL_SUPERVISOR_INIT: termination_type {policy!r} not one of {_VALID_POLICIES}"
        )

    node["ct_control"]["supervisor_state"] = {
        "reset_count": 0,
        "failure_counter": SupervisorFailureCounter(
            node["data"].get("reset_window", 10.0),
            get_time=handle["engine"]["get_time"],
        ),
    }
    for c in node["children"]:
        enable_node(c)


def cfl_supervisor_term(handle, node) -> None:
    return None


def cfl_supervisor_main(handle, bool_fn_name, node, event):
    if bool_fn_name and bool_fn_name != "CFL_NULL":
        bool_fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
        if bool_fn is None:
            raise LookupError(
                f"CFL_SUPERVISOR_MAIN: aux fn {bool_fn_name!r} not in registry"
            )
        if bool_fn(handle, node, event["event_type"], event["event_id"], event["data"]):
            return CFL_DISABLE

    if event["event_id"] != CFL_TIMER_EVENT:
        return CFL_CONTINUE

    children = node["children"]
    if not children:
        return CFL_DISABLE

    state = node["ct_control"]["supervisor_state"]
    policy = node["data"].get("termination_type", "ONE_FOR_ONE")

    # Identify failed children.
    failed_indices = [i for i, c in enumerate(children) if not c["ct_control"]["enabled"]]
    if not failed_indices:
        # Everyone still running.
        return CFL_CONTINUE

    # At least one child has failed — decide whether to restart.
    if not _can_restart(handle, node, state):
        _fire_finalize(handle, node)
        return CFL_DISABLE

    # Apply restart policy.
    engine = handle["engine"]
    if policy == "ONE_FOR_ONE":
        targets = failed_indices
    elif policy == "ONE_FOR_ALL":
        targets = list(range(len(children)))
    elif policy == "REST_FOR_ALL":
        first_failed = failed_indices[0]
        targets = list(range(first_failed, len(children)))
    else:  # unreachable thanks to INIT validation
        raise ValueError(f"unknown termination_type: {policy}")

    for i in targets:
        terminate_node_tree(engine, handle, children[i])
    for i in targets:
        enable_node(children[i])

    state["reset_count"] += 1
    state["failure_counter"].record_failure()

    return CFL_CONTINUE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _can_restart(handle, node, state) -> bool:
    if not node["data"].get("restart_enabled", True):
        return False
    if not node["data"].get("reset_limited_enabled", False):
        return True
    max_n = int(node["data"].get("max_reset_number", 1))
    return not state["failure_counter"].is_threshold_exceeded(max_n)


def _fire_finalize(handle, node) -> None:
    fn_name = node["data"].get("finalize_fn", "CFL_NULL")
    if not fn_name or fn_name == "CFL_NULL":
        return
    fn = lookup_one_shot(handle["engine"]["registry"], fn_name)
    if fn is None:
        raise LookupError(
            f"CFL_SUPERVISOR_MAIN: finalize fn {fn_name!r} not in registry"
        )
    fn(handle, node)
