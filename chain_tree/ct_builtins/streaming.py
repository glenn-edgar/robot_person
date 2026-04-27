"""Streaming nodes — schema-tagged event pipelines.

Streaming events flow through the regular CFL event queue. A "packet" is
the `event["data"]` dict; a "port" is a `{event_id, schema?, handler_id?}`
dict the consumer matches against. All streaming nodes are TRANSPARENT
to non-matching events (return CFL_CONTINUE) — they only act when a
matching streaming event is delivered.

Port matching:
    event_type == "CFL_EVENT_TYPE_STREAMING_DATA"
    event_id   == port["event_id"]
    if port has "schema": event["data"]["_schema"] == port["schema"]

Node types (return-code semantics from LuaJIT cfl_builtins.lua):
    SINK       — match → call boolean (consumer); always CFL_CONTINUE
    TAP        — match → call boolean (observer); always CFL_CONTINUE
    FILTER     — match → call boolean → False ⇒ CFL_HALT (blocks downstream
                 siblings until next match); True ⇒ CFL_CONTINUE
    TRANSFORM  — match → call boolean (user emits on outport); CFL_CONTINUE

All nodes use:
    node["data"]["port"]    = inport spec dict
    boolean_fn_name slot    = the user handler / predicate / transformer

Transform additionally reads node["data"]["outport"] for outbound emit
(user code reads it from node["data"] inside the boolean).
"""

from __future__ import annotations

from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_EVENT_TYPE_STREAMING_DATA,
    CFL_HALT,
)
from ct_runtime.registry import lookup_boolean


CFL_EVENT_TYPE_STREAMING_DATA = "CFL_EVENT_TYPE_STREAMING_DATA"


# ---------------------------------------------------------------------------
# Matching predicate
# ---------------------------------------------------------------------------

def event_matches(event: dict, port: dict) -> bool:
    if event.get("event_type") != CFL_EVENT_TYPE_STREAMING_DATA:
        return False
    if event.get("event_id") != port.get("event_id"):
        return False
    if "schema" in port:
        data = event.get("data") or {}
        if data.get("_schema") != port["schema"]:
            return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_boolean(handle, bool_fn_name, node, event) -> bool:
    if not bool_fn_name or bool_fn_name == "CFL_NULL":
        return True   # default: pass-through
    fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
    if fn is None:
        raise LookupError(
            f"streaming: boolean fn {bool_fn_name!r} not in registry"
        )
    return bool(fn(handle, node, event["event_type"], event["event_id"], event["data"]))


# ---------------------------------------------------------------------------
# Main fns
# ---------------------------------------------------------------------------

def cfl_streaming_sink_packet(handle, bool_fn_name, node, event):
    port = node["data"].get("port") or {}
    if event_matches(event, port):
        _call_boolean(handle, bool_fn_name, node, event)
    return CFL_CONTINUE


def cfl_streaming_tap_packet(handle, bool_fn_name, node, event):
    # Same dispatch shape as sink — semantic distinction is "tap = observer,
    # the user MAY NOT consume the packet; sink owns it." Engine treats them
    # identically; the contract is documentation-only.
    port = node["data"].get("port") or {}
    if event_matches(event, port):
        _call_boolean(handle, bool_fn_name, node, event)
    return CFL_CONTINUE


def cfl_streaming_filter_packet(handle, bool_fn_name, node, event):
    """Boolean True (or no-match / no-boolean) → pass through (CONTINUE).
    Boolean False on a matching packet → CFL_HALT, blocking downstream
    siblings until the next event arrives.
    """
    port = node["data"].get("port") or {}
    if event_matches(event, port):
        if not _call_boolean(handle, bool_fn_name, node, event):
            return CFL_HALT
    return CFL_CONTINUE


def cfl_streaming_transform_packet(handle, bool_fn_name, node, event):
    """User boolean is the transformer: it reads the inbound packet, runs
    its transform, and emits the result on `node["data"]["outport"]` via
    a regular `enqueue(...)` — the engine does not auto-emit anything.
    """
    port = node["data"].get("port") or {}
    if event_matches(event, port):
        _call_boolean(handle, bool_fn_name, node, event)
    return CFL_CONTINUE
