"""Controlled nodes — client-server RPC built on directed events.

Two node types:

  CFL_CONTROLLED_SERVER_MAIN — a passive listener whose children are the
    work performed for one request. Server is "transparent" (CONTINUE on
    no match) so it doesn't block siblings. On a matching request:
      - record client_node ref from event data
      - call user handler boolean (optional)
      - enable all children
      - return CFL_CONTINUE so walker descends into the just-enabled
        children to start the work
    On subsequent TIMER ticks: poll children. When all disabled AND a
    client_node is set, send the response high-pri to the client, clear
    client_node, return CFL_DISABLE.

  CFL_CONTROLLED_CLIENT_MAIN — a leaf-style requester.
    INIT (CFL_CONTROLLED_CLIENT_INIT): construct request payload (auto-
    augmented with `_client_node`=self and optional `_schema`), enqueue
    high-pri request targeting the server.
    MAIN: HALT until a matching response event arrives; on match, call
    user response_handler boolean (optional) and CFL_DISABLE.

Both nodes use port dicts:
    {event_id: str, schema?: str, event_type?: str (default streaming)}

The mechanism is the same as streaming nodes — directed events with dict
payloads. The difference is the lifecycle pattern: streaming is a
long-running pipeline; controlled is one-shot RPC activation.
"""

from __future__ import annotations

from ct_runtime import enable_node, enqueue
from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_EVENT_TYPE_STREAMING_DATA,
    CFL_HALT,
    CFL_RESET,
    CFL_TERMINATE,
    CFL_TIMER_EVENT,
    PRIORITY_HIGH,
)
from ct_runtime.event_queue import make_event
from ct_runtime.registry import lookup_boolean, lookup_one_shot


# ---------------------------------------------------------------------------
# Port matching (looser than streaming.event_matches — port chooses event_type)
# ---------------------------------------------------------------------------

def _port_event_type(port: dict) -> str:
    return port.get("event_type", CFL_EVENT_TYPE_STREAMING_DATA)


def _event_matches_port(event: dict, port: dict) -> bool:
    if event.get("event_type") != _port_event_type(port):
        return False
    if event.get("event_id") != port.get("event_id"):
        return False
    if "schema" in port:
        data = event.get("data") or {}
        if data.get("_schema") != port["schema"]:
            return False
    return True


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def cfl_controlled_server_main(handle, bool_fn_name, node, event):
    request_port = node["data"].get("request_port") or {}

    # Match: a fresh request arrived → record client, run handler, enable
    # work-children, descend on the same walk to start them.
    if _event_matches_port(event, request_port):
        ed = event["data"] or {}
        node["data"]["client_node"] = ed.get("_client_node")
        node["data"]["request_data"] = ed
        if bool_fn_name and bool_fn_name != "CFL_NULL":
            fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
            if fn is None:
                raise LookupError(
                    f"controlled_server: handler {bool_fn_name!r} not in registry"
                )
            fn(handle, node, event["event_type"], event["event_id"], event["data"])
        for c in node["children"]:
            enable_node(c)
        return CFL_CONTINUE

    # Polling: on each timer tick after a request was accepted, check
    # whether the work is done. If so, send the response and disable.
    if event["event_id"] == CFL_TIMER_EVENT:
        if node["data"].get("client_node") is not None:
            any_running = any(
                c["ct_control"]["enabled"] for c in node["children"]
            )
            if not any_running:
                _send_response(handle, node)
                node["data"]["client_node"] = None
                return CFL_DISABLE

    return CFL_CONTINUE


def _send_response(handle, server_node) -> None:
    response_port = server_node["data"]["response_port"]
    client = server_node["data"]["client_node"]
    response_data = dict(server_node["data"].get("response_data") or {})
    if "schema" in response_port:
        response_data.setdefault("_schema", response_port["schema"])
    enqueue(handle["engine"], make_event(
        target=client,
        event_type=_port_event_type(response_port),
        event_id=response_port["event_id"],
        data=response_data,
        priority=PRIORITY_HIGH,
    ))


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

def cfl_controlled_client_init(handle, node) -> None:
    server = node["data"]["server_node"]
    request_port = node["data"]["request_port"]
    request_data = dict(node["data"].get("request_data") or {})
    request_data["_client_node"] = node
    if "schema" in request_port:
        request_data.setdefault("_schema", request_port["schema"])
    # Reset timeout counter every (re-)activation. Pairs with the timeout
    # kwargs on asm_client_controlled_node — leaving it at zero on a reset
    # would cause the next timeout window to start mid-count.
    node["data"]["timeout_count"] = 0
    enqueue(handle["engine"], make_event(
        target=server,
        event_type=_port_event_type(request_port),
        event_id=request_port["event_id"],
        data=request_data,
        priority=PRIORITY_HIGH,
    ))


def cfl_controlled_client_main(handle, bool_fn_name, node, event):
    response_port = node["data"]["response_port"]
    if _event_matches_port(event, response_port):
        if bool_fn_name and bool_fn_name != "CFL_NULL":
            fn = lookup_boolean(handle["engine"]["registry"], bool_fn_name)
            if fn is None:
                raise LookupError(
                    f"controlled_client: response handler {bool_fn_name!r} not in registry"
                )
            fn(handle, node, event["event_type"], event["event_id"], event["data"])
        return CFL_DISABLE

    # Optional timeout: count occurrences of timeout_event_id (default
    # CFL_TIMER_EVENT). timeout=0 disables the timeout entirely.
    timeout = int(node["data"].get("timeout", 0))
    if timeout <= 0:
        return CFL_HALT

    timeout_event = node["data"].get("timeout_event_id", CFL_TIMER_EVENT)
    if event["event_id"] != timeout_event:
        return CFL_HALT

    node["data"]["timeout_count"] = node["data"].get("timeout_count", 0) + 1
    if node["data"]["timeout_count"] < timeout:
        return CFL_HALT

    # Timeout reached. Fire optional error one-shot, then RESET (retry the
    # parent) or TERMINATE (give up). Mirrors CFL_WAIT_MAIN semantics.
    err_fn_name = node["data"].get("error_fn", "CFL_NULL")
    if err_fn_name and err_fn_name != "CFL_NULL":
        err_fn = lookup_one_shot(handle["engine"]["registry"], err_fn_name)
        if err_fn is None:
            raise LookupError(
                f"controlled_client: error fn {err_fn_name!r} not in registry"
            )
        err_fn(handle, node)

    if node["data"].get("reset_flag", False):
        return CFL_RESET
    return CFL_TERMINATE


def cfl_controlled_client_term(handle, node) -> None:
    return None
