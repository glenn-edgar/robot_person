"""Smoke tests for ct_runtime.

Covers the core dispatch loop end-to-end on hand-built trees:

- Single-KB single-node tick loop; CFL_TERMINATE on root disables it.
- Multi-node tree with INIT enabling children; CFL_CONTINUE drives descent.
- terminate_node_tree fires TERM events in reverse topological order.
- Event queue priority: high pops before normal.
- Unresolved function name raises at dispatch time.
"""

from __future__ import annotations

import ct_runtime as ct
from ct_runtime import event_queue as eq
from ct_runtime import (
    CFL_CONTINUE,
    CFL_EVENT_TYPE_NULL,
    CFL_TERMINATE,
    CFL_TERMINATE_EVENT,
    CFL_TIMER_EVENT,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
)


def _mk_engine():
    """Build an engine with sleep/time stubbed so run() is deterministic."""
    return ct.new_engine(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
    )


# ---------------------------------------------------------------------------
# 1. Single-node KB: root ticks a few times then self-terminates.
# ---------------------------------------------------------------------------

def test_single_node_tick_and_terminate():
    ticks = []

    def root_main(handle, _bool_name, node, event):
        assert event["event_id"] == CFL_TIMER_EVENT
        handle["blackboard"].setdefault("ticks", 0)
        handle["blackboard"]["ticks"] += 1
        ticks.append(handle["blackboard"]["ticks"])
        if handle["blackboard"]["ticks"] >= 3:
            return CFL_TERMINATE
        return CFL_CONTINUE

    engine = _mk_engine()
    ct.add_main(engine["registry"], "ROOT_MAIN", root_main)

    root = ct.make_node(name="root", main_fn_name="ROOT_MAIN")
    kb = ct.new_kb("k", root)
    ct.add_kb(engine, kb)

    ct.run(engine, starting=["k"])

    assert ticks == [1, 2, 3]
    assert kb["blackboard"]["ticks"] == 3
    assert root["ct_control"]["enabled"] is False
    assert root["ct_control"]["initialized"] is False
    assert engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 2. Multi-node: INIT enables children; CFL_CONTINUE descent runs them.
# ---------------------------------------------------------------------------

def test_multinode_init_enables_and_descends():
    def parent_init(handle, node):
        # INIT one-shot: enable both structural children.
        for c in node["children"]:
            ct.enable_node(c)

    def pass_through(handle, _bn, node, event):
        return CFL_CONTINUE

    def counter_main(handle, _bn, node, event):
        key = node["data"]["key"]
        handle["blackboard"][key] = handle["blackboard"].get(key, 0) + 1
        return CFL_CONTINUE

    def terminator(handle, _bn, node, event):
        handle["blackboard"]["outer_ticks"] = handle["blackboard"].get("outer_ticks", 0) + 1
        # On the 3rd tick, terminate. DFS pre-order means children run AFTER
        # the parent main fn on each tick — so children run on ticks 1 and 2,
        # then on tick 3 the parent terminates before children get a chance.
        if handle["blackboard"]["outer_ticks"] >= 3:
            return CFL_TERMINATE
        return CFL_CONTINUE

    engine = _mk_engine()
    ct.add_one_shot(engine["registry"], "PARENT_INIT", parent_init)
    ct.add_main(engine["registry"], "PASS", pass_through)
    ct.add_main(engine["registry"], "COUNTER", counter_main)
    ct.add_main(engine["registry"], "TERMINATOR", terminator)

    child_a = ct.make_node(name="a", main_fn_name="COUNTER", data={"key": "a"})
    child_b = ct.make_node(name="b", main_fn_name="COUNTER", data={"key": "b"})
    inner = ct.make_node(name="inner", main_fn_name="PASS", init_fn_name="PARENT_INIT")
    ct.link_children(inner, [child_a, child_b])
    root = ct.make_node(name="root", main_fn_name="TERMINATOR", init_fn_name="PARENT_INIT")
    ct.link_children(root, [inner])

    kb = ct.new_kb("k", root)
    ct.add_kb(engine, kb)

    ct.run(engine, starting=["k"])

    # Three outer ticks: ticks 1+2 ran the counters; tick 3 terminated before
    # descent. Children ran twice, outer ran three times.
    assert kb["blackboard"]["a"] == 2
    assert kb["blackboard"]["b"] == 2
    assert kb["blackboard"]["outer_ticks"] == 3
    # Everything torn down.
    assert root["ct_control"]["enabled"] is False
    assert inner["ct_control"]["enabled"] is False
    assert child_a["ct_control"]["enabled"] is False
    assert child_b["ct_control"]["enabled"] is False


# ---------------------------------------------------------------------------
# 3. terminate_node_tree: TERM events fire children-before-parents.
# ---------------------------------------------------------------------------

def test_terminate_node_tree_reverse_topo_order():
    term_order = []

    def term_marker(handle, node, event_type, event_id, event_data):
        # boolean fn doubles as the termination observer: called with
        # CFL_TERMINATE_EVENT when disable_node fires.
        if event_id == CFL_TERMINATE_EVENT:
            term_order.append(node["name"])
        return True

    def parent_init(handle, node):
        for c in node["children"]:
            ct.enable_node(c)

    def pass_through(handle, _bn, node, event):
        return CFL_CONTINUE

    engine = _mk_engine()
    ct.add_one_shot(engine["registry"], "PARENT_INIT", parent_init)
    ct.add_main(engine["registry"], "PASS", pass_through)
    ct.add_boolean(engine["registry"], "TERM_MARK", term_marker)

    # Build: root → [inner → [a, b], c]
    a = ct.make_node(name="a", main_fn_name="PASS", boolean_fn_name="TERM_MARK")
    b = ct.make_node(name="b", main_fn_name="PASS", boolean_fn_name="TERM_MARK")
    c = ct.make_node(name="c", main_fn_name="PASS", boolean_fn_name="TERM_MARK")
    inner = ct.make_node(
        name="inner",
        main_fn_name="PASS",
        boolean_fn_name="TERM_MARK",
        init_fn_name="PARENT_INIT",
    )
    ct.link_children(inner, [a, b])
    root = ct.make_node(
        name="root",
        main_fn_name="PASS",
        boolean_fn_name="TERM_MARK",
        init_fn_name="PARENT_INIT",
    )
    ct.link_children(root, [inner, c])

    kb = ct.new_kb("k", root)
    ct.add_kb(engine, kb)

    # Warm up: one timer tick to run INIT and enable descendants.
    ct.activate_kb(engine, "k")
    ct.engine.generate_timer_events(engine)
    ct.engine.drain(engine)

    # All enabled + initialized now.
    for n in (root, inner, a, b, c):
        assert n["ct_control"]["enabled"] is True
        assert n["ct_control"]["initialized"] is True

    # Trigger explicit teardown of the whole subtree.
    ct.terminate_node_tree(engine, kb, root)

    # Invariant: children before parents. Order within a level may vary in
    # principle but DFS pre-order + reverse gives a deterministic sequence:
    #   pre-order   : root, inner, a, b, c
    #   reversed    : c, b, a, inner, root
    assert term_order == ["c", "b", "a", "inner", "root"]
    assert root["ct_control"]["enabled"] is False


# ---------------------------------------------------------------------------
# 4. Event queue priority: high pops before normal.
# ---------------------------------------------------------------------------

def test_event_queue_high_priority_drains_first():
    q = eq.new_event_queue()
    eq.enqueue(q, eq.make_event(target=None, event_type="T", event_id="N1",
                                priority=PRIORITY_NORMAL))
    eq.enqueue(q, eq.make_event(target=None, event_type="T", event_id="H1",
                                priority=PRIORITY_HIGH))
    eq.enqueue(q, eq.make_event(target=None, event_type="T", event_id="N2",
                                priority=PRIORITY_NORMAL))
    eq.enqueue(q, eq.make_event(target=None, event_type="T", event_id="H2",
                                priority=PRIORITY_HIGH))

    popped = []
    while eq.nonempty(q):
        popped.append(eq.pop(q)["event_id"])
    assert popped == ["H1", "H2", "N1", "N2"]


# ---------------------------------------------------------------------------
# 5. Unresolved function name raises at dispatch.
# ---------------------------------------------------------------------------

def test_unresolved_main_fn_raises():
    engine = _mk_engine()
    root = ct.make_node(name="root", main_fn_name="DOES_NOT_EXIST")
    kb = ct.new_kb("k", root)
    ct.add_kb(engine, kb)
    ct.activate_kb(engine, "k")

    ct.enqueue(engine, eq.make_event(
        target=root,
        event_type=CFL_EVENT_TYPE_NULL,
        event_id=CFL_TIMER_EVENT,
    ))

    import pytest
    with pytest.raises(LookupError):
        ct.engine.drain(engine)
