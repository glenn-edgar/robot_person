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
    SINK            — match → call boolean (consumer); always CFL_CONTINUE
    TAP             — match → call boolean (observer); always CFL_CONTINUE
    FILTER          — match → call boolean → False ⇒ CFL_HALT (blocks
                      downstream siblings until next match); True ⇒ CONTINUE
    TRANSFORM       — match → call boolean (user emits on outport); CONTINUE
    COLLECT         — multi-port packet accumulator: holds the most-recent
                      packet from each inport and emits a combined packet
                      on the outport once every inport has produced one.
                      Always CONTINUE.
    SINK_COLLECTED  — semantic alias of SINK; documents that the matched
                      packet is expected to be a collected-shape dict
                      (inport_event_id → packet) emitted by COLLECT.

All nodes use:
    node["data"]["port"]    = inport spec dict
    boolean_fn_name slot    = the user handler / predicate / transformer

Transform additionally reads node["data"]["outport"] for outbound emit
(user code reads it from node["data"] inside the boolean).

Collect schema:
    node["data"]["inports"]      = [inport_spec, ...]
    node["data"]["outport"]      = outport_spec
    node["data"]["target_node"]  = optional emit target (defaults to parent)
    node["data"]["pending"]      = {inport_event_id: latest_packet}, runtime
"""

from __future__ import annotations

from ct_runtime import enqueue
from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_EVENT_TYPE_STREAMING_DATA,
    CFL_HALT,
    CFL_RESET,
    CFL_TERMINATE,
    PRIORITY_NORMAL,
)
from ct_runtime.event_queue import make_event
from ct_runtime.registry import lookup_boolean, lookup_one_shot


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


# ---------------------------------------------------------------------------
# Multi-port packet accumulator
# ---------------------------------------------------------------------------

def cfl_streaming_collect_init(handle, node) -> None:
    """Reset the pending-packet store on each (re-)activation."""
    node["data"]["pending"] = {}


def cfl_streaming_collect_packet(handle, bool_fn_name, node, event):
    """Accumulate packets across multiple inports; emit one combined packet
    on the outport once every inport has produced at least one packet.

    Behavior:
      - On a packet matching any configured inport, store/overwrite the
        latest packet keyed by the inport's event_id.
      - When every inport has at least one packet, build the combined
        payload `{inport_event_id: packet, ...}` (with `_schema` from the
        outport injected if configured), enqueue a streaming event on the
        outport targeting `data["target_node"]` (defaulting to the
        collect node's parent), then clear the pending store.
      - Always returns CFL_CONTINUE — collect is transparent like sink/tap.

    The optional `bool_fn_name` aux, if present, is invoked on each
    matching packet for observer-side bookkeeping; its return value is
    ignored. Useful for counting / logging without deciding control flow.
    """
    inports = node["data"].get("inports") or []
    if not inports:
        return CFL_CONTINUE

    matched_port = None
    for ip in inports:
        if event_matches(event, ip):
            matched_port = ip
            break
    if matched_port is None:
        return CFL_CONTINUE

    pending = node["data"].setdefault("pending", {})
    pending[matched_port["event_id"]] = dict(event.get("data") or {})

    # Optional observer hook (does not gate the emit).
    if bool_fn_name and bool_fn_name != "CFL_NULL":
        _call_boolean(handle, bool_fn_name, node, event)

    if all(ip["event_id"] in pending for ip in inports):
        outport = node["data"].get("outport") or {}
        target = node["data"].get("target_node") or node["parent"]
        combined = dict(pending)
        if "schema" in outport:
            combined["_schema"] = outport["schema"]
        enqueue(handle["engine"], make_event(
            target=target,
            event_type=CFL_EVENT_TYPE_STREAMING_DATA,
            event_id=outport["event_id"],
            data=combined,
            priority=PRIORITY_NORMAL,
        ))
        node["data"]["pending"] = {}

    return CFL_CONTINUE


def cfl_streaming_sink_collected(handle, bool_fn_name, node, event):
    """Sink variant for collected packets. Dispatch is identical to
    CFL_STREAMING_SINK_PACKET; the distinct main fn exists so DSL builders
    and grep can identify the role, and so future collected-specific
    validation has a place to live.
    """
    return cfl_streaming_sink_packet(handle, bool_fn_name, node, event)


# ---------------------------------------------------------------------------
# Streaming assertion
# ---------------------------------------------------------------------------

def cfl_streaming_verify_packet(handle, bool_fn_name, node, event):
    """Streaming-aware assertion. On a packet matching the configured port,
    call the predicate boolean; True → CONTINUE; False → fire optional
    error one-shot then RESET or TERMINATE the parent (same escalation
    shape as CFL_VERIFY).

    Non-matching events pass through transparently (CONTINUE) so this node
    can sit alongside sinks/taps in a streaming pipeline.

    node["data"] schema:
        {
            "port":       inport spec,
            "error_fn":   one-shot to fire on failure (CFL_NULL = none),
            "error_data": Any (convenience: error_fn reads node.data),
            "reset_flag": True → CFL_RESET, False → CFL_TERMINATE,
        }
    """
    port = node["data"].get("port") or {}
    if not event_matches(event, port):
        return CFL_CONTINUE

    if _call_boolean(handle, bool_fn_name, node, event):
        return CFL_CONTINUE

    err_fn_name = node["data"].get("error_fn", "CFL_NULL")
    if err_fn_name and err_fn_name != "CFL_NULL":
        err_fn = lookup_one_shot(handle["engine"]["registry"], err_fn_name)
        if err_fn is None:
            raise LookupError(
                f"CFL_STREAMING_VERIFY_PACKET: error fn {err_fn_name!r} not in registry"
            )
        err_fn(handle, node)

    if node["data"].get("reset_flag", False):
        return CFL_RESET
    return CFL_TERMINATE
