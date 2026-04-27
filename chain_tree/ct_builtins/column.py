"""CFL_COLUMN_MAIN — the workhorse parent node.

Despite the name, "column" is not strictly sequential — it's the LuaJIT/yaml
port's universal "container that watches its children" pattern. Sequencing
emerges from how children behave:

- Each child returns CFL_HALT while busy (e.g. wait_time, wait_for_event)
  → walker signal CT_STOP_SIBLINGS → no further siblings visited THIS tick.
- When a child completes it returns CFL_DISABLE → terminate_node_tree on
  the child → next tick's walker filter excludes it → walker proceeds to
  the next sibling.
- When all children have disabled, COLUMN_MAIN returns CFL_DISABLE itself.

This is the same pattern used by FORK (parallel) — the difference between
column and fork is solely whether children return HALT (sequential) or
CONTINUE (parallel). At INIT time, both enable all declared children; the
behavior split is in the leaf fns.

node["data"] schema:
    {
        "auto_start": bool,   # currently informational; honored by parents
                              # like gate_node that selectively activate
                              # children. CFL_COLUMN_INIT enables all
                              # children unconditionally.
        "column_data": Any,   # free-form user payload
    }

Aux fn contract: optional boolean. Returning True disables the column
(early-out). Returning False (or no aux fn) → continue normally. Matches
the spec convention used by supervisor and sequence_til.
"""

from __future__ import annotations

from ct_runtime import enable_node
from ct_runtime.codes import CFL_CONTINUE, CFL_DISABLE
from ct_runtime.registry import lookup_boolean


def cfl_column_main(handle, bool_fn_name, node, event):
    # Aux early-out (if user supplied a non-null aux fn).
    if bool_fn_name and bool_fn_name != "CFL_NULL":
        bool_fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
        if bool_fn is None:
            raise LookupError(
                f"CFL_COLUMN_MAIN: aux fn {bool_fn_name!r} not in registry"
            )
        if bool_fn(handle, node, event["event_type"], event["event_id"], event["data"]):
            return CFL_DISABLE

    # Scan children: any still active → continue; otherwise we're done.
    for child in node["children"]:
        if child["ct_control"]["enabled"]:
            return CFL_CONTINUE
    return CFL_DISABLE


def cfl_column_init(handle, node) -> None:
    """Enable every child link so the walker can descend into them."""
    for child in node["children"]:
        enable_node(child)


def cfl_column_term(handle, node) -> None:
    """No-op — terminate_node_tree already drove children-before-parent
    teardown by the time this fires.
    """
    return None
