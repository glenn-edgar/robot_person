"""System / utility one-shots used by built-in DSL leaves.

node["data"] schemas vary per fn — documented inline.
"""

from __future__ import annotations


def cfl_log_message(handle, node) -> None:
    """node['data']['message'] → engine logger.

    Convenience leaf used by `asm_log_message`; the engine's logger
    callable receives the formatted string. With the default engine logger
    being a no-op, tests inspect kb["blackboard"] or wire up a custom
    logger that records messages.
    """
    msg = node["data"].get("message", "")
    handle["engine"]["logger"](msg)


def cfl_blackboard_set(handle, node) -> None:
    """node['data']['key'] = node['data']['value'] in the KB blackboard.

    Useful for DSL leaves that just need to flip a flag, without the user
    having to write a Python one-shot.
    """
    key = node["data"]["key"]
    handle["blackboard"][key] = node["data"].get("value")


def cfl_emit_streaming(handle, node) -> None:
    """node['data'] = {target_node, event_id, data}. Posts a streaming
    event onto the engine's normal-priority queue. Used by
    `asm_emit_streaming` DSL leaves and tests.
    """
    from ct_runtime import enqueue
    from ct_runtime.codes import CFL_EVENT_TYPE_STREAMING_DATA, PRIORITY_NORMAL
    from ct_runtime.event_queue import make_event
    enqueue(handle["engine"], make_event(
        target=node["data"]["target_node"],
        event_type=CFL_EVENT_TYPE_STREAMING_DATA,
        event_id=node["data"]["event_id"],
        data=node["data"]["data"],
        priority=PRIORITY_NORMAL,
    ))
