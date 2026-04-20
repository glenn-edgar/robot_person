"""Dispatch operator tests — event_dispatch, state_machine, dict_dispatch."""

from se_builtins import dispatch as D
from se_builtins import oneshot as O
from se_dsl import make_node
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    invoke_any,
    new_instance_from_tree,
    new_module,
)


def _handler(tag):
    """m_call handler that records the event_id it saw."""
    def fn(inst, node, event_id, event_data):
        from se_runtime import EVENT_INIT, EVENT_TERMINATE, SE_PIPELINE_CONTINUE
        if event_id in (EVENT_INIT, EVENT_TERMINATE):
            return SE_PIPELINE_CONTINUE
        node["user_data"] = tag
        return SE_PIPELINE_CONTINUE
    return make_node(fn, "m_call")


# ---------------------------------------------------------------------------
# event_dispatch
# ---------------------------------------------------------------------------

def test_event_dispatch_routes_to_matching_child():
    h_a = _handler("saw_a")
    h_b = _handler("saw_b")
    tree = make_node(D.se_event_dispatch, "m_call",
                     params={"mapping": {"event_a": 0, "event_b": 1}},
                     children=[h_a, h_b])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)

    invoke_any(inst, tree, "event_a", {})
    assert h_a["user_data"] == "saw_a"
    assert h_b.get("user_data") is None

    invoke_any(inst, tree, "event_b", {})
    assert h_b["user_data"] == "saw_b"


def test_event_dispatch_unmapped_event_is_passthrough():
    h = _handler("saw_it")
    tree = make_node(D.se_event_dispatch, "m_call",
                     params={"mapping": {"known": 0}},
                     children=[h])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)

    r = invoke_any(inst, tree, "unknown", {})
    assert r == SE_PIPELINE_CONTINUE
    assert h.get("user_data") is None


# ---------------------------------------------------------------------------
# state_machine
# ---------------------------------------------------------------------------

def test_state_machine_starts_in_initial_state():
    idle = _handler("in_idle")
    running = _handler("in_running")

    tree = make_node(D.se_state_machine, "m_call",
                     params={
                         "states": {"idle": 0, "running": 1},
                         "transitions": {("idle", "start"): "running"},
                         "initial": "idle",
                     },
                     children=[idle, running])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)

    invoke_any(inst, tree, EVENT_TICK, {})
    assert tree["user_data"] == "idle"
    assert idle["user_data"] == "in_idle"


def test_state_machine_transitions_on_matching_event():
    idle_counts = []
    running_counts = []

    def idle_fn(inst, node, event_id, event_data):
        from se_runtime import EVENT_INIT, EVENT_TERMINATE
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            idle_counts.append(event_id)
        return SE_PIPELINE_CONTINUE

    def running_fn(inst, node, event_id, event_data):
        from se_runtime import EVENT_INIT, EVENT_TERMINATE
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            running_counts.append(event_id)
        return SE_PIPELINE_CONTINUE

    tree = make_node(D.se_state_machine, "m_call",
                     params={
                         "states": {"idle": 0, "running": 1},
                         "transitions": {("idle", "start"): "running",
                                         ("running", "stop"): "idle"},
                         "initial": "idle",
                     },
                     children=[
                         make_node(idle_fn, "m_call"),
                         make_node(running_fn, "m_call"),
                     ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)

    invoke_any(inst, tree, "start", {})
    assert tree["user_data"] == "running"
    # After transition, the new state's child is invoked with the same event
    assert running_counts == ["start"]

    invoke_any(inst, tree, EVENT_TICK, {})
    assert running_counts == ["start", EVENT_TICK]

    invoke_any(inst, tree, "stop", {})
    assert tree["user_data"] == "idle"


def test_state_machine_non_transition_event_passes_to_current_state():
    idle_events = []

    def idle_fn(inst, node, event_id, event_data):
        from se_runtime import EVENT_INIT, EVENT_TERMINATE
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            idle_events.append(event_id)
        return SE_PIPELINE_CONTINUE

    tree = make_node(D.se_state_machine, "m_call",
                     params={
                         "states": {"idle": 0},
                         "transitions": {},
                         "initial": "idle",
                     },
                     children=[make_node(idle_fn, "m_call")])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)

    invoke_any(inst, tree, "random_event", {})
    assert idle_events == ["random_event"]


# ---------------------------------------------------------------------------
# dict_dispatch
# ---------------------------------------------------------------------------

def test_dict_dispatch_routes_by_dict_value():
    h_a = _handler("saw_a")
    h_b = _handler("saw_b")
    tree = make_node(D.se_dict_dispatch, "m_call",
                     params={"key": "mode", "mapping": {"run": 0, "pause": 1}},
                     children=[h_a, h_b])

    mod = new_module(dictionary={"mode": "run"})
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_TICK, {})
    assert h_a["user_data"] == "saw_a"

    mod["dictionary"]["mode"] = "pause"
    invoke_any(inst, tree, EVENT_TICK, {})
    assert h_b["user_data"] == "saw_b"


def test_dict_dispatch_unmapped_value_passthrough():
    h = _handler("saw_it")
    tree = make_node(D.se_dict_dispatch, "m_call",
                     params={"key": "mode", "mapping": {"run": 0}},
                     children=[h])
    mod = new_module(dictionary={"mode": "other"})
    inst = new_instance_from_tree(mod, tree)

    r = invoke_any(inst, tree, EVENT_TICK, {})
    assert r == SE_PIPELINE_CONTINUE
    assert h.get("user_data") is None
