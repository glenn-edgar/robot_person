"""Oneshot builtin tests."""

from se_builtins import oneshot as O
from se_dsl import make_node
from se_runtime import (
    EVENT_TICK,
    invoke_any,
    new_instance_from_tree,
    new_module,
    pop_event,
    reset_recursive,
)


def _o_node(fn, **params):
    return make_node(fn, "o_call", params=params)


def _io_node(fn, **params):
    return make_node(fn, "io_call", params=params)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def test_log_uses_module_logger():
    captured = []
    mod = new_module(logger=captured.append)
    node = _o_node(O.log, message="hello")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert captured == ["[log] hello"]


def test_dict_log_includes_key_value():
    captured = []
    mod = new_module(dictionary={"pressure": 42}, logger=captured.append)
    node = _o_node(O.dict_log, message="reading", key="pressure")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert captured == ["[dict_log] reading pressure=42"]


def test_oneshot_fires_only_once_per_activation():
    captured = []
    mod = new_module(logger=captured.append)
    node = _o_node(O.log, message="x")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    invoke_any(inst, node, EVENT_TICK)
    invoke_any(inst, node, EVENT_TICK)
    assert captured == ["[log] x"]
    reset_recursive(inst, node)
    invoke_any(inst, node, EVENT_TICK)
    assert captured == ["[log] x", "[log] x"]


# ---------------------------------------------------------------------------
# Dictionary writes
# ---------------------------------------------------------------------------

def test_dict_set_writes_value():
    mod = new_module(dictionary={"a": 0})
    node = _o_node(O.dict_set, key="a", value=99)
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert mod["dictionary"]["a"] == 99


def test_dict_set_creates_new_key():
    mod = new_module(dictionary={})
    node = _o_node(O.dict_set, key="new", value="hello")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert mod["dictionary"]["new"] == "hello"


def test_dict_inc_defaults_to_one():
    mod = new_module(dictionary={"counter": 5})
    node = _o_node(O.dict_inc, key="counter")
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert mod["dictionary"]["counter"] == 6


def test_dict_inc_with_delta_and_negative():
    mod = new_module(dictionary={"counter": 10})
    inc = _o_node(O.dict_inc, key="counter", delta=5)
    inst = new_instance_from_tree(mod, inc)
    invoke_any(inst, inc, EVENT_TICK)
    assert mod["dictionary"]["counter"] == 15

    dec = _o_node(O.dict_inc, key="counter", delta=-3)
    inst2 = new_instance_from_tree(mod, dec)
    invoke_any(inst2, dec, EVENT_TICK)
    assert mod["dictionary"]["counter"] == 12


def test_dict_inc_creates_missing_key_starting_at_zero():
    mod = new_module(dictionary={})
    node = _o_node(O.dict_inc, key="counter", delta=1)
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert mod["dictionary"]["counter"] == 1


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def test_queue_event_pushes_with_default_priority():
    mod = new_module()
    node = _o_node(O.queue_event, event_id="sensor.updated", data={"v": 1})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)
    assert pop_event(inst) == ("sensor.updated", {"v": 1})


def test_queue_event_honors_high_priority():
    mod = new_module()
    normal = _o_node(O.queue_event, event_id="n", priority="normal")
    high = _o_node(O.queue_event, event_id="h", priority="high")

    inst = new_instance_from_tree(mod, normal)
    invoke_any(inst, normal, EVENT_TICK)
    invoke_any(inst, high, EVENT_TICK)
    # High should come out first
    assert pop_event(inst)[0] == "h"
    assert pop_event(inst)[0] == "n"


# ---------------------------------------------------------------------------
# io_call: dict_load
# ---------------------------------------------------------------------------

def test_dict_load_merges_once_per_instance_lifetime():
    mod = new_module(dictionary={"existing": 1})
    node = _io_node(O.dict_load, source={"a": 1, "b": 2, "existing": 99})
    inst = new_instance_from_tree(mod, node)

    invoke_any(inst, node, EVENT_TICK)
    assert mod["dictionary"] == {"existing": 99, "a": 1, "b": 2}

    # Re-invoke — io_call guard means it should NOT fire again
    mod["dictionary"]["a"] = 500
    invoke_any(inst, node, EVENT_TICK)
    assert mod["dictionary"]["a"] == 500  # unchanged


def test_dict_load_survives_reset_as_io_call():
    mod = new_module(dictionary={})
    node = _io_node(O.dict_load, source={"x": 1})
    inst = new_instance_from_tree(mod, node)
    invoke_any(inst, node, EVENT_TICK)

    reset_recursive(inst, node)
    mod["dictionary"]["x"] = 99
    invoke_any(inst, node, EVENT_TICK)
    # ever_init survived reset → dict_load did NOT re-run
    assert mod["dictionary"]["x"] == 99
