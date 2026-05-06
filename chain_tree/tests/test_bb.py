"""Tests for bb_emit / bb_subscribe — leaf-level transport helpers.

These helpers look up `kb["engine"]["transport"]`. They are the documented
indirection so leaf code doesn't depend on the engine dict's internal
layout. The blackboard itself stays a plain dict — these helpers do not
attach themselves to it.
"""

from __future__ import annotations

import ct_runtime as ct
from ct_runtime.transport import InProcessTransport


def _make_kb_on_engine(transport=None):
    engine = ct.new_engine(transport=transport)
    root = ct.make_node(name="root", main_fn_name=None)
    kb = ct.new_kb("k", root)
    ct.add_kb(engine, kb)
    return engine, kb


def test_bb_emit_reaches_engine_transport():
    captured = []
    custom = InProcessTransport()
    custom.subscribe("", lambda topic, payload: captured.append((topic, payload)))
    _, kb = _make_kb_on_engine(transport=custom)
    ct.bb_emit(kb, "evt.farm.moisture.tick", {"device": "lacima1c"})
    assert captured == [("evt.farm.moisture.tick", {"device": "lacima1c"})]


def test_bb_subscribe_registers_on_engine_transport():
    _, kb = _make_kb_on_engine()
    received = []
    ct.bb_subscribe(kb, "evt.", lambda topic, payload: received.append(topic))
    # Round-trip: emit through the same kb.
    ct.bb_emit(kb, "evt.test", {"v": 1})
    ct.bb_emit(kb, "cmd.ignored", {"v": 2})
    assert received == ["evt.test"]


def test_blackboard_remains_a_plain_dict():
    # The shape rule: blackboard stays dict; helpers never decorate it.
    _, kb = _make_kb_on_engine()
    assert type(kb["blackboard"]) is dict
    # Round-trip a kv pair and confirm normal dict semantics.
    kb["blackboard"]["key"] = "value"
    assert kb["blackboard"]["key"] == "value"
    # bb_emit / bb_subscribe must not have stamped attrs onto the dict.
    assert not hasattr(kb["blackboard"], "emit")
    assert not hasattr(kb["blackboard"], "subscribe")


def test_two_kbs_share_engine_transport():
    # Cross-KB delivery: subscriber on KB A receives events emitted from KB B,
    # because the transport hangs off the shared engine.
    engine = ct.new_engine()
    root_a = ct.make_node(name="a_root", main_fn_name=None)
    root_b = ct.make_node(name="b_root", main_fn_name=None)
    kb_a = ct.new_kb("a", root_a)
    kb_b = ct.new_kb("b", root_b)
    ct.add_kb(engine, kb_a)
    ct.add_kb(engine, kb_b)

    received = []
    ct.bb_subscribe(kb_a, "evt.", lambda topic, payload: received.append(topic))
    ct.bb_emit(kb_b, "evt.from_b", {})
    assert received == ["evt.from_b"]
