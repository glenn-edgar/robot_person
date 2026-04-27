"""CFL_VERIFY — assertion leaf with optional error handler.

The aux boolean is the assertion. Returning True → CFL_CONTINUE
(verification passed; walker proceeds normally). Returning False → fire
the error one-shot if configured, then either CFL_RESET (retry the
parent) or CFL_TERMINATE (abort the parent).

node["data"] schema:
    {
        "error_fn":   str,          # one-shot to fire on failure (CFL_NULL = none)
        "error_data": Any,          # convenience: error_fn reads from node.data
        "reset_flag": bool,         # True → CFL_RESET, False → CFL_TERMINATE
    }
"""

from __future__ import annotations

from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_RESET,
    CFL_TERMINATE,
)
from ct_runtime.registry import lookup_boolean, lookup_one_shot


def cfl_verify_main(handle, bool_fn_name, node, event):
    if not bool_fn_name or bool_fn_name == "CFL_NULL":
        # No predicate — vacuously passes. Common when verify is being used
        # as a structural placeholder.
        return CFL_CONTINUE

    bool_fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
    if bool_fn is None:
        raise LookupError(f"CFL_VERIFY: aux fn {bool_fn_name!r} not in registry")

    if bool_fn(handle, node, event["event_type"], event["event_id"], event["data"]):
        return CFL_CONTINUE

    # Failed — fire error fn (if any), then escalate.
    err_fn_name = node["data"].get("error_fn", "CFL_NULL")
    if err_fn_name and err_fn_name != "CFL_NULL":
        err_fn = lookup_one_shot(handle["engine"]["registry"], err_fn_name)
        if err_fn is None:
            raise LookupError(
                f"CFL_VERIFY: error fn {err_fn_name!r} not in registry"
            )
        err_fn(handle, node)

    if node["data"].get("reset_flag", False):
        return CFL_RESET
    return CFL_TERMINATE
