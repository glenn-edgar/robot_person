"""ct_runtime — CFL engine core.

Re-exports the most commonly needed constructors, constants, and dispatch
entry points. Builtins, DSL, and bridge functions live in sibling packages
(ct_builtins, ct_dsl, ct_bridge).
"""

from __future__ import annotations

from . import bb, codes, engine, event_queue, node, registry, serialize, transport, walker
from .bb import bb_emit, bb_subscribe
from .transport import InProcessTransport, Transport
from .codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_EVENT_TYPE_NULL,
    CFL_EVENT_TYPE_PTR,
    CFL_EVENT_TYPE_STREAMING_DATA,
    CFL_HALT,
    CFL_HEARTBEAT_EVENT,
    CFL_RAISE_EXCEPTION_EVENT,
    CFL_RESET,
    CFL_SKIP_CONTINUE,
    CFL_TERMINATE,
    CFL_TERMINATE_EVENT,
    CFL_TERMINATE_SYSTEM,
    CFL_TERMINATE_SYSTEM_EVENT,
    CFL_TIMER_EVENT,
    CT_CONTINUE,
    CT_SKIP_CHILDREN,
    CT_STOP_ALL,
    CT_STOP_SIBLINGS,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
)
from .engine import (
    activate_kb,
    add_kb,
    delete_kb,
    disable_node,
    enable_node,
    enqueue,
    execute_event,
    execute_node,
    new_engine,
    new_kb,
    run,
    terminate_node_tree,
)
from .event_queue import make_event
from .node import enabled_children, link_children, make_node
from .registry import (
    add_boolean,
    add_main,
    add_one_shot,
    add_se_io_one_shot,
    add_se_main,
    add_se_one_shot,
    add_se_pred,
    new_registry,
)
from .serialize import (
    deserialize_into,
    deserialize_tree,
    serialize_chain_tree,
    serialize_tree,
)

__all__ = [
    # constants
    "CFL_CONTINUE",
    "CFL_HALT",
    "CFL_TERMINATE",
    "CFL_RESET",
    "CFL_DISABLE",
    "CFL_SKIP_CONTINUE",
    "CFL_TERMINATE_SYSTEM",
    "CFL_TIMER_EVENT",
    "CFL_TERMINATE_EVENT",
    "CFL_TERMINATE_SYSTEM_EVENT",
    "CFL_RAISE_EXCEPTION_EVENT",
    "CFL_HEARTBEAT_EVENT",
    "CFL_EVENT_TYPE_NULL",
    "CFL_EVENT_TYPE_PTR",
    "CFL_EVENT_TYPE_STREAMING_DATA",
    "CT_CONTINUE",
    "CT_SKIP_CHILDREN",
    "CT_STOP_SIBLINGS",
    "CT_STOP_ALL",
    "PRIORITY_HIGH",
    "PRIORITY_NORMAL",
    # node construction
    "make_node",
    "link_children",
    "enabled_children",
    # engine + dispatch
    "new_engine",
    "new_kb",
    "add_kb",
    "activate_kb",
    "delete_kb",
    "enqueue",
    "enable_node",
    "disable_node",
    "terminate_node_tree",
    "execute_node",
    "execute_event",
    "run",
    "make_event",
    # registry
    "new_registry",
    "add_main",
    "add_boolean",
    "add_one_shot",
    "add_se_main",
    "add_se_pred",
    "add_se_one_shot",
    "add_se_io_one_shot",
    # serialization
    "serialize_tree",
    "deserialize_tree",
    "serialize_chain_tree",
    "deserialize_into",
    # transport (stage-2 stub today; stage-3 swaps the implementation)
    "Transport",
    "InProcessTransport",
    "bb_emit",
    "bb_subscribe",
    # submodules (for advanced users)
    "bb",
    "codes",
    "engine",
    "event_queue",
    "node",
    "registry",
    "serialize",
    "transport",
    "walker",
]
