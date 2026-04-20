"""Nested tree-call tests — call_tree primitive."""

import pytest

from se_builtins import flow_control as F
from se_builtins import nested_call as N
from se_builtins import oneshot as O
from se_builtins import return_codes as RC
from se_dsl import make_node
from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    invoke_any,
    new_instance_from_tree,
    new_module,
    register_tree,
)


def _child_tree_that_disables_after_n(n, counter):
    """Return a tree-root m_call that returns CONTINUE n times then DISABLE."""
    def fn(inst, node, event_id, event_data):
        if event_id in (EVENT_INIT, EVENT_TERMINATE):
            return SE_PIPELINE_CONTINUE
        counter["n"] += 1
        if counter["n"] >= n:
            return SE_PIPELINE_DISABLE
        return SE_PIPELINE_CONTINUE

    return make_node(fn, "m_call")


# ---------------------------------------------------------------------------
# Direct tree reference (no registry lookup)
# ---------------------------------------------------------------------------

def test_call_tree_direct_reference_disables_parent_when_child_completes():
    counter = {"n": 0}
    child_root = _child_tree_that_disables_after_n(2, counter)

    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    mod = new_module()
    inst = new_instance_from_tree(mod, call)

    # tick 1: child returns CONTINUE
    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_PIPELINE_CONTINUE
    assert counter["n"] == 1

    # tick 2: child returns DISABLE
    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert counter["n"] == 2


# ---------------------------------------------------------------------------
# Tree-by-name resolution via module registry
# ---------------------------------------------------------------------------

def test_call_tree_by_name_resolves_from_registry():
    counter = {"n": 0}
    mod = new_module()
    register_tree(mod, "subtree", _child_tree_that_disables_after_n(1, counter))

    call = make_node(N.se_call_tree, "m_call", params={"tree_name": "subtree"})
    inst = new_instance_from_tree(mod, call)

    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert counter["n"] == 1


def test_call_tree_unknown_name_raises():
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree_name": "nope"})
    inst = new_instance_from_tree(mod, call)
    with pytest.raises(KeyError, match="unknown tree"):
        invoke_any(inst, call, EVENT_TICK, {})


# ---------------------------------------------------------------------------
# Module sharing: child sees parent's dictionary
# ---------------------------------------------------------------------------

def test_child_shares_parent_dictionary():
    """A child tree should read and write the same dict as its parent."""
    # Child that increments a shared counter on every tick.
    child_root = make_node(F.se_sequence_once, "m_call",
                           children=[make_node(O.dict_inc, "o_call",
                                               params={"key": "shared"})])

    mod = new_module(dictionary={"shared": 0})
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)

    # The child sequence_once fires the oneshot once then disables → parent sees DISABLE
    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["shared"] == 1


def test_child_and_parent_share_constants():
    child_root = make_node(lambda *_: SE_PIPELINE_DISABLE, "m_call")
    mod = new_module(constants={"PI": 3.14})
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)
    invoke_any(inst, call, EVENT_TICK, {})
    # Both parent and child (on the same module) see the same constants mapping
    # Verify by checking module identity — there's only one module.
    assert inst["module"]["constants"]["PI"] == 3.14


# ---------------------------------------------------------------------------
# Event queues are separate
# ---------------------------------------------------------------------------

def test_child_has_own_event_queue():
    """queue_event inside the child pushes to the child's queue, not parent's."""
    # Child: sequence_once — fires queue_event oneshot then disables
    child_root = make_node(F.se_sequence_once, "m_call", children=[
        make_node(O.queue_event, "o_call",
                  params={"event_id": "child_event", "data": {}}),
    ])
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)

    invoke_any(inst, call, EVENT_TICK, {})
    # Parent's queues should be empty
    from se_runtime import queue_empty
    assert queue_empty(inst)


# ---------------------------------------------------------------------------
# Boundary translation: function codes → pipeline codes
# ---------------------------------------------------------------------------

def test_child_function_halt_translated_to_pipeline_halt():
    child_root = make_node(RC.return_function_halt, "m_call")
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)
    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_PIPELINE_HALT


def test_child_function_disable_translated_to_pipeline_disable():
    child_root = make_node(RC.return_function_disable, "m_call")
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)
    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE


def test_application_codes_escape_through_call_tree_unchanged():
    """An application-level SE_HALT should propagate up unchanged."""
    child_root = make_node(RC.return_halt, "m_call")  # SE_HALT = 1
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)
    r = invoke_any(inst, call, EVENT_TICK, {})
    assert r == SE_HALT


# ---------------------------------------------------------------------------
# Call_tree nested inside a sequence
# ---------------------------------------------------------------------------

def test_call_tree_inside_sequence_advances_when_child_disables():
    """Once the call_tree child disables, the parent sequence should advance."""
    after_call = []

    def after_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            after_call.append(1)
        return SE_PIPELINE_DISABLE

    child_root = _child_tree_that_disables_after_n(1, {"n": 0})

    seq = make_node(F.se_sequence, "m_call", children=[
        make_node(N.se_call_tree, "m_call", params={"tree": child_root}),
        make_node(after_fn, "m_call"),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, seq)

    r = invoke_any(inst, seq, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert after_call == [1]


# ---------------------------------------------------------------------------
# Child's internal queue is drained by the call
# ---------------------------------------------------------------------------

def test_child_internal_queue_drained_within_one_parent_tick():
    """Child tree that queue_events itself during a tick should have those
    events drained before call_tree returns."""
    counter = {"n": 0}

    def worker(inst, node, event_id, event_data):
        if event_id in (EVENT_INIT, EVENT_TERMINATE):
            return SE_PIPELINE_CONTINUE
        counter["n"] += 1
        if event_id == "internal_go":
            # Once we've handled the internal event, complete.
            return SE_PIPELINE_DISABLE
        # On the first tick, queue an internal event for ourselves, stay CONTINUE
        from se_runtime import push_event
        push_event(inst, "internal_go", {})
        return SE_PIPELINE_CONTINUE

    child_root = make_node(worker, "m_call")
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)

    r = invoke_any(inst, call, EVENT_TICK, {})
    # Drain happens inside call_tree — both the initial tick and the
    # queued "internal_go" fire within one parent tick.
    assert r == SE_PIPELINE_DISABLE
    assert counter["n"] == 2


# ---------------------------------------------------------------------------
# Terminate forwards to child
# ---------------------------------------------------------------------------

def test_terminate_forwards_to_child():
    term_events = []

    def child_fn(inst, node, event_id, event_data):
        if event_id == EVENT_TERMINATE:
            term_events.append(1)
        return SE_PIPELINE_CONTINUE

    child_root = make_node(child_fn, "m_call")
    mod = new_module()
    call = make_node(N.se_call_tree, "m_call", params={"tree": child_root})
    inst = new_instance_from_tree(mod, call)

    # Initialize the call (which initializes the child)
    invoke_any(inst, call, EVENT_TICK, {})
    # Now terminate the call — should forward TERMINATE to the child
    call["fn"](inst, call, EVENT_TERMINATE, {})
    assert term_events == [1]
