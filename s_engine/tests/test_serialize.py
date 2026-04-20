"""serialize_tree / deserialize_tree round-trip tests."""

import json

import pytest

import se_dsl as dsl
from se_builtins import BUILTIN_REGISTRY
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_DISABLE,
    deserialize_tree,
    invoke_any,
    new_instance_from_tree,
    new_module,
    serialize_tree,
)


# ---------------------------------------------------------------------------
# Shape-only serialization
# ---------------------------------------------------------------------------

def test_serialize_produces_json_safe_dict():
    plan = dsl.sequence(
        dsl.dict_set("x", 1),
        dsl.dict_inc("x", delta=2),
    )
    wire = serialize_tree(plan)
    # Round-trip through json must not raise
    s = json.dumps(wire)
    parsed = json.loads(s)
    assert parsed["fn"] == "se_sequence"
    assert len(parsed["children"]) == 2
    assert parsed["children"][0]["fn"] == "dict_set"
    assert parsed["children"][0]["params"]["value"] == 1
    assert parsed["children"][1]["fn"] == "dict_inc"


def test_serialize_omits_dispatch_fields():
    plan = dsl.dict_set("k", "v")
    plan["initialized"] = True  # simulate runtime state on the node
    plan["state"] = 7
    wire = serialize_tree(plan)
    # shape only — no runtime state in wire form
    assert set(wire) == {"fn", "call_type", "params", "children"}


def test_serialize_rejects_uncallable_fn():
    bad = dsl.make_node(lambda *_: None, "m_call")
    bad["fn"] = "not_callable"
    with pytest.raises(TypeError, match="not callable"):
        serialize_tree(bad)


# ---------------------------------------------------------------------------
# Tuple-keyed params (state_machine.transitions)
# ---------------------------------------------------------------------------

def test_serialize_handles_tuple_keyed_transitions():
    plan = dsl.state_machine(
        states={
            "idle": dsl.nop(),
            "running": dsl.nop(),
        },
        transitions={
            ("idle", "start"): "running",
            ("running", "stop"): "idle",
        },
        initial="idle",
    )
    wire = serialize_tree(plan)
    s = json.dumps(wire)
    parsed = json.loads(s)
    # Check the tuple-key marker is present
    assert "__tuple_keyed__" in parsed["params"]["transitions"]

    restored = deserialize_tree(parsed, BUILTIN_REGISTRY)
    assert restored["params"]["transitions"][("idle", "start")] == "running"
    assert restored["params"]["transitions"][("running", "stop")] == "idle"


# ---------------------------------------------------------------------------
# Round-trip — tree runs the same after wire transport
# ---------------------------------------------------------------------------

def test_round_trip_plan_executes_identically():
    plan = dsl.cond(
        dsl.case(
            dsl.dict_gt("counter", 0),
            dsl.sequence_once(
                dsl.dict_set("state", "starting"),
                dsl.dict_inc("counter", delta=3),
                dsl.dict_set("state", "ready"),
            ),
        ),
        default=dsl.sequence_once(dsl.dict_set("state", "idle")),
    )
    wire = serialize_tree(plan)
    restored = deserialize_tree(wire, BUILTIN_REGISTRY)

    mod = new_module(dictionary={"counter": 5})
    inst = new_instance_from_tree(mod, restored)
    r = invoke_any(inst, restored, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["counter"] == 8
    assert mod["dictionary"]["state"] == "ready"


def test_round_trip_state_machine_executes_correctly():
    plan = dsl.state_machine(
        states={
            "idle": dsl.dict_set("st", "idle"),
            "running": dsl.dict_set("st", "running"),
        },
        transitions={
            ("idle", "start"): "running",
            ("running", "stop"): "idle",
        },
        initial="idle",
    )
    wire = serialize_tree(plan)
    restored = deserialize_tree(json.loads(json.dumps(wire)), BUILTIN_REGISTRY)

    mod = new_module(dictionary={})
    inst = new_instance_from_tree(mod, restored)
    invoke_any(inst, restored, EVENT_TICK, {})
    assert mod["dictionary"]["st"] == "idle"
    invoke_any(inst, restored, "start", {})
    assert mod["dictionary"]["st"] == "running"


# ---------------------------------------------------------------------------
# Trust boundary
# ---------------------------------------------------------------------------

def test_deserialize_unknown_fn_raises():
    wire = {"fn": "evil_code", "call_type": "m_call", "params": {}, "children": []}
    with pytest.raises(KeyError, match="evil_code"):
        deserialize_tree(wire, BUILTIN_REGISTRY)


def test_deserialize_restores_default_dispatch_fields():
    plan = dsl.sequence_once(dsl.log("hi"))
    wire = serialize_tree(plan)
    restored = deserialize_tree(wire, BUILTIN_REGISTRY)
    assert restored["active"] is True
    assert restored["initialized"] is False
    assert restored["ever_init"] is False
    assert restored["state"] == 0
    assert restored["user_data"] is None


# ---------------------------------------------------------------------------
# User fn merging
# ---------------------------------------------------------------------------

def test_user_fn_in_registry_deserializes_correctly():
    def my_custom(inst, node, event_id, event_data):
        from se_runtime import EVENT_INIT, EVENT_TERMINATE
        if event_id in (EVENT_INIT, EVENT_TERMINATE):
            return 12  # PIPELINE_CONTINUE
        inst["module"]["dictionary"]["hit"] = True
        return 16  # PIPELINE_DISABLE

    plan = dsl.make_node(my_custom, "m_call")
    wire = serialize_tree(plan)

    # Builtin registry doesn't know about my_custom; compose a merged registry
    merged = dict(BUILTIN_REGISTRY)
    merged["my_custom"] = my_custom

    restored = deserialize_tree(wire, merged)
    mod = new_module(dictionary={})
    inst = new_instance_from_tree(mod, restored)
    invoke_any(inst, restored, EVENT_TICK, {})
    assert mod["dictionary"]["hit"] is True
