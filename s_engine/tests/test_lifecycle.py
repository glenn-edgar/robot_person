"""Child helper tests — terminate / reset behavior on children."""

from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    child_invoke,
    child_reset,
    child_terminate,
    children_reset_all,
    children_terminate_all,
    new_instance_from_tree,
    new_module,
    reset_recursive,
)


def _node(fn, call_type, children=None, **overrides):
    base = {
        "fn": fn,
        "call_type": call_type,
        "params": {},
        "children": children or [],
        "active": True,
        "initialized": False,
        "ever_init": False,
        "state": 0,
        "user_data": None,
    }
    base.update(overrides)
    return base


def _tracking_fn(events):
    def fn(inst, node, event_id, event_data):
        events.append((id(node), event_id))
        return SE_PIPELINE_CONTINUE
    return fn


def test_child_terminate_fires_terminate_on_initialized_m_call():
    events = []
    child = _node(_tracking_fn(events), "m_call")
    parent = _node(lambda *_: SE_PIPELINE_CONTINUE, "m_call", children=[child])

    mod = new_module()
    inst = new_instance_from_tree(mod, parent)

    child_invoke(inst, parent, 0, EVENT_TICK, {})
    assert child["initialized"] is True
    assert any(e[1] == EVENT_INIT for e in events)

    child_terminate(inst, parent, 0)
    assert any(e[1] == EVENT_TERMINATE for e in events)
    assert child["initialized"] is False
    assert child["state"] == 0
    assert child["active"] is False  # terminate deactivates


def test_child_terminate_skips_uninitialized_m_call():
    events = []
    child = _node(_tracking_fn(events), "m_call")
    parent = _node(lambda *_: SE_PIPELINE_CONTINUE, "m_call", children=[child])
    mod = new_module()
    inst = new_instance_from_tree(mod, parent)
    child_terminate(inst, parent, 0)
    # No TERMINATE event fired because child was never initialized
    assert not any(e[1] == EVENT_TERMINATE for e in events)


def test_child_reset_clears_state_without_terminate():
    events = []
    child = _node(_tracking_fn(events), "m_call", state=7, user_data={"x": 1})
    parent = _node(lambda *_: SE_PIPELINE_CONTINUE, "m_call", children=[child])
    mod = new_module()
    inst = new_instance_from_tree(mod, parent)

    child_invoke(inst, parent, 0, EVENT_TICK, {})
    child["state"] = 42  # simulate operator-managed state
    child_reset(inst, parent, 0)
    assert child["state"] == 0
    assert child["user_data"] is None
    assert child["initialized"] is False
    # No TERMINATE event because child_reset does not call the fn
    assert not any(e[1] == EVENT_TERMINATE for e in events)


def test_reset_recursive_preserves_ever_init():
    child = _node(lambda *_: None, "io_call", ever_init=True, initialized=True)
    parent = _node(lambda *_: SE_PIPELINE_CONTINUE, "m_call", children=[child])
    mod = new_module()
    inst = new_instance_from_tree(mod, parent)
    reset_recursive(inst, parent)
    assert child["ever_init"] is True  # io_call semantic: survives reset
    assert child["initialized"] is False


def test_children_terminate_all_walks_reverse_order():
    order = []

    def make_fn(name):
        def fn(inst, node, event_id, event_data):
            order.append((name, event_id))
            return SE_PIPELINE_CONTINUE
        return fn

    c1 = _node(make_fn("c1"), "m_call")
    c2 = _node(make_fn("c2"), "m_call")
    c3 = _node(make_fn("c3"), "m_call")
    parent = _node(lambda *_: SE_PIPELINE_CONTINUE, "m_call", children=[c1, c2, c3])
    mod = new_module()
    inst = new_instance_from_tree(mod, parent)

    # Initialize all children first
    for i in range(3):
        child_invoke(inst, parent, i, EVENT_TICK, {})
    order.clear()

    children_terminate_all(inst, parent)
    terminate_order = [name for name, eid in order if eid == EVENT_TERMINATE]
    assert terminate_order == ["c3", "c2", "c1"]


def test_children_reset_all_does_not_fire_terminate():
    events = []
    c1 = _node(_tracking_fn(events), "m_call")
    c2 = _node(_tracking_fn(events), "m_call")
    parent = _node(lambda *_: SE_PIPELINE_CONTINUE, "m_call", children=[c1, c2])
    mod = new_module()
    inst = new_instance_from_tree(mod, parent)

    child_invoke(inst, parent, 0, EVENT_TICK, {})
    child_invoke(inst, parent, 1, EVENT_TICK, {})
    events.clear()

    children_reset_all(inst, parent)
    assert not any(e[1] == EVENT_TERMINATE for e in events)
    assert c1["initialized"] is False
    assert c2["initialized"] is False
