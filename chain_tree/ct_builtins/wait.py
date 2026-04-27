"""Wait leaves: time-based and event-based.

CFL_WAIT_TIME — halts for a wall-clock duration.

    node["data"] = {"time_delay": float, "start_time": float}

CFL_WAIT_MAIN — generic event-driven wait. Aux boolean decides "wait
satisfied"; main fn handles the timeout escalation.

    node["data"] = {
        "target_event_id": str,        # used by the default aux (CFL_WAIT_FOR_EVENT)
        "target_count":    int,        # ditto
        "current_count":   int,        # written by aux
        "timeout":         int,        # 0 = no timeout; otherwise # of timeout_event_id ticks
        "timeout_event_id": str,       # default CFL_TIMER_EVENT
        "timeout_count":   int,        # written by main
        "error_fn":        str,        # one-shot fired on timeout (CFL_NULL = none)
        "error_data":      Any,        # convenience: error_fn reads node.data['error_data']
        "reset_flag":      bool,       # on timeout: True → CFL_RESET, False → CFL_TERMINATE
    }

CFL_WAIT_FOR_EVENT — boolean fn used as aux for CFL_WAIT_MAIN. Counts
occurrences of `target_event_id`; True at `target_count`. Reusable as
a standalone boolean fn for any aux slot that needs event counting.

CFL_WAIT_INIT — resets both counters to 0.
"""

from __future__ import annotations

from ct_runtime.codes import (
    CFL_DISABLE,
    CFL_HALT,
    CFL_RESET,
    CFL_TERMINATE,
    CFL_TIMER_EVENT,
)
from ct_runtime.registry import lookup_boolean, lookup_one_shot


# ---------------------------------------------------------------------------
# Time-based wait
# ---------------------------------------------------------------------------

def cfl_wait_time_init(handle, node) -> None:
    node["data"]["start_time"] = handle["engine"]["get_time"]()


def cfl_wait_time_main(handle, bool_fn_name, node, event):
    if event["event_id"] != CFL_TIMER_EVENT:
        return CFL_HALT

    now = handle["engine"]["get_time"]()
    start = node["data"].get("start_time", now)
    delay = float(node["data"].get("time_delay", 0.0))
    if (now - start) >= delay:
        return CFL_DISABLE
    return CFL_HALT


# ---------------------------------------------------------------------------
# Event-based wait
# ---------------------------------------------------------------------------

def cfl_wait_init(handle, node) -> None:
    node["data"]["current_count"] = 0
    node["data"]["timeout_count"] = 0


def cfl_wait_main(handle, bool_fn_name, node, event):
    # Aux decides: did we receive enough of the right event?
    if bool_fn_name and bool_fn_name != "CFL_NULL":
        bool_fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
        if bool_fn is None:
            raise LookupError(f"CFL_WAIT_MAIN: aux fn {bool_fn_name!r} not in registry")
        if bool_fn(handle, node, event["event_type"], event["event_id"], event["data"]):
            return CFL_DISABLE

    # Timeout handling: count occurrences of timeout_event_id (default
    # CFL_TIMER_EVENT). timeout=0 disables timeout entirely.
    timeout = int(node["data"].get("timeout", 0))
    if timeout <= 0:
        return CFL_HALT

    timeout_event = node["data"].get("timeout_event_id", CFL_TIMER_EVENT)
    if event["event_id"] != timeout_event:
        return CFL_HALT

    node["data"]["timeout_count"] = node["data"].get("timeout_count", 0) + 1
    if node["data"]["timeout_count"] < timeout:
        return CFL_HALT

    # Timeout reached — fire the error one-shot if configured, then
    # RESET the parent (retry) or TERMINATE it (give up).
    err_fn_name = node["data"].get("error_fn", "CFL_NULL")
    if err_fn_name and err_fn_name != "CFL_NULL":
        err_fn = lookup_one_shot(handle["engine"]["registry"], err_fn_name)
        if err_fn is None:
            raise LookupError(
                f"CFL_WAIT_MAIN: error fn {err_fn_name!r} not in registry"
            )
        err_fn(handle, node)

    if node["data"].get("reset_flag", False):
        return CFL_RESET
    return CFL_TERMINATE


def cfl_wait_for_event(handle, node, event_type, event_id, event_data) -> bool:
    """Standard event-counting aux: True once `target_event_id` has been seen
    `target_count` times.
    """
    if event_id != node["data"].get("target_event_id"):
        return False
    node["data"]["current_count"] = node["data"].get("current_count", 0) + 1
    return node["data"]["current_count"] >= int(node["data"].get("target_count", 1))
