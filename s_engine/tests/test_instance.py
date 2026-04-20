import pytest

from se_runtime import (
    new_instance,
    new_instance_from_tree,
    new_module,
    pop_event,
    push_event,
    queue_empty,
    register_tree,
)


def _stub_tree():
    return {
        "fn": lambda inst, node, event_id, event_data: 16,  # SE_PIPELINE_DISABLE
        "call_type": "m_call",
        "params": {},
        "children": [],
        "active": True,
        "initialized": False,
        "ever_init": False,
        "state": 0,
        "user_data": None,
    }


def test_new_instance_from_tree_has_queues():
    mod = new_module()
    inst = new_instance_from_tree(mod, _stub_tree())
    assert inst["module"] is mod
    assert queue_empty(inst)


def test_new_instance_by_name_lookup():
    mod = new_module()
    register_tree(mod, "main", _stub_tree())
    inst = new_instance(mod, "main")
    assert inst["root"]["call_type"] == "m_call"


def test_new_instance_unknown_tree_raises():
    mod = new_module()
    with pytest.raises(KeyError):
        new_instance(mod, "does_not_exist")


def test_push_and_pop_single_queue():
    mod = new_module()
    inst = new_instance_from_tree(mod, _stub_tree())
    push_event(inst, "sensor.temp", {"value": 42})
    assert not queue_empty(inst)
    event = pop_event(inst)
    assert event == ("sensor.temp", {"value": 42})
    assert queue_empty(inst)


def test_high_priority_drained_first():
    mod = new_module()
    inst = new_instance_from_tree(mod, _stub_tree())
    push_event(inst, "normal_event", priority="normal")
    push_event(inst, "high_event", priority="high")
    push_event(inst, "another_normal", priority="normal")
    assert pop_event(inst)[0] == "high_event"
    assert pop_event(inst)[0] == "normal_event"
    assert pop_event(inst)[0] == "another_normal"
    assert pop_event(inst) is None


def test_push_event_rejects_unknown_priority():
    mod = new_module()
    inst = new_instance_from_tree(mod, _stub_tree())
    with pytest.raises(ValueError):
        push_event(inst, "x", priority="critical")


def test_event_queue_limit_enforced():
    mod = new_module(event_queue_limit=2)
    inst = new_instance_from_tree(mod, _stub_tree())
    push_event(inst, "a")
    push_event(inst, "b")
    with pytest.raises(OverflowError):
        push_event(inst, "c")
