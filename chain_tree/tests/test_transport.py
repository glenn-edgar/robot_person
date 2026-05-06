"""Tests for the chain_tree transport ABC and InProcessTransport stub.

Stage-2 mechanism only: in-memory dispatch, prefix matching, exception
isolation, deterministic ordering. Stage-3 ZmqTransport tests live
under tests/cluster/ (not yet built).
"""

from __future__ import annotations

import pytest

import ct_runtime as ct
from ct_runtime.transport import InProcessTransport, Transport


# ---------------------------------------------------------------------------
# Transport ABC — public surface check
# ---------------------------------------------------------------------------

def test_transport_is_abstract():
    with pytest.raises(TypeError):
        Transport()


def test_in_process_transport_implements_interface():
    t = InProcessTransport()
    assert isinstance(t, Transport)


# ---------------------------------------------------------------------------
# Emit + subscribe basics
# ---------------------------------------------------------------------------

def test_emit_with_no_subscribers_is_noop():
    t = InProcessTransport()
    t.emit("evt.anything", {"v": 1})  # must not raise


def test_subscribe_then_emit_delivers():
    t = InProcessTransport()
    received = []
    t.subscribe("evt.farm.", lambda topic, payload: received.append((topic, payload)))
    t.emit("evt.farm.moisture.tick", {"device": "lacima1c"})
    assert received == [("evt.farm.moisture.tick", {"device": "lacima1c"})]


def test_non_matching_prefix_does_not_deliver():
    t = InProcessTransport()
    received = []
    t.subscribe("evt.farm.", lambda topic, payload: received.append(topic))
    t.emit("evt.cimis.tick", {})
    assert received == []


def test_empty_prefix_is_firehose():
    t = InProcessTransport()
    received = []
    t.subscribe("", lambda topic, payload: received.append(topic))
    t.emit("evt.farm.x", {})
    t.emit("cmd.something", {})
    t.emit("ack.123", {})
    assert received == ["evt.farm.x", "cmd.something", "ack.123"]


def test_multiple_matching_subscribers_all_called_in_subscription_order():
    t = InProcessTransport()
    log: list[str] = []
    t.subscribe("evt.", lambda topic, payload: log.append("first"))
    t.subscribe("evt.farm.", lambda topic, payload: log.append("second"))
    t.subscribe("", lambda topic, payload: log.append("third"))
    t.emit("evt.farm.moisture.tick", {})
    assert log == ["first", "second", "third"]


def test_payload_passes_through_unchanged():
    t = InProcessTransport()
    received = []
    t.subscribe("", lambda topic, payload: received.append(payload))
    payload = {"a": 1, "b": [2, 3], "c": {"nested": True}}
    t.emit("any.topic", payload)
    # Same dict reference (the transport doesn't copy — that's the
    # publisher's responsibility if mutation is a concern).
    assert received[0] is payload


# ---------------------------------------------------------------------------
# PUB/SUB lossy semantics — handler exception must not crash publisher
# ---------------------------------------------------------------------------

def test_handler_exception_does_not_crash_emit():
    log_lines = []
    t = InProcessTransport(logger=log_lines.append)

    def boom(topic, payload):
        raise RuntimeError("subscriber broke")

    delivered = []
    t.subscribe("", boom)
    t.subscribe("", lambda topic, payload: delivered.append(topic))
    t.emit("evt.test", {})  # must not raise
    # Following subscriber still got called.
    assert delivered == ["evt.test"]
    # And the exception was logged.
    assert any("subscriber broke" in line for line in log_lines)


def test_handler_exception_in_one_does_not_block_subsequent_handlers():
    t = InProcessTransport(logger=lambda _msg: None)
    received = []

    def boom(topic, payload):
        raise ValueError("boom")

    t.subscribe("", lambda topic, payload: received.append("a"))
    t.subscribe("", boom)
    t.subscribe("", lambda topic, payload: received.append("c"))
    t.emit("any", {})
    assert received == ["a", "c"]


# ---------------------------------------------------------------------------
# Engine wiring — new_engine carries a transport
# ---------------------------------------------------------------------------

def test_new_engine_default_transport_is_in_process():
    engine = ct.new_engine()
    assert isinstance(engine["transport"], InProcessTransport)


def test_new_engine_accepts_custom_transport():
    custom = InProcessTransport()
    engine = ct.new_engine(transport=custom)
    assert engine["transport"] is custom


def test_engine_transport_is_re_exported_at_package_root():
    # Public surface: callers can `from ct_runtime import InProcessTransport`.
    assert ct.InProcessTransport is InProcessTransport
    assert ct.Transport is Transport
