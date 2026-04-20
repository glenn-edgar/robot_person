"""Flow-control operator tests.

Builds trees using make_node and the real builtins. Custom m_call leaves
scripted to return specified codes exercise the dispatch tables.
"""

import pytest

from se_builtins import flow_control as F
from se_builtins import oneshot as O
from se_builtins import pred as P
from se_builtins import return_codes as RC
from se_dsl import make_node
from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_FUNCTION_DISABLE,
    SE_FUNCTION_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_RESET,
    invoke_any,
    new_instance_from_tree,
    new_module,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def m(fn, **params):
    return make_node(fn, "m_call", params=params)


def pred(fn, **params):
    return make_node(fn, "p_call", params=params)


def o(fn, **params):
    return make_node(fn, "o_call", params=params)


def scripted_m(codes):
    """m_call node that returns codes from a list across successive TICKs.
    INIT/TERMINATE always return PIPELINE_CONTINUE."""
    state = {"i": 0}

    def fn(inst, node, event_id, event_data):
        if event_id in (EVENT_INIT, EVENT_TERMINATE):
            return SE_PIPELINE_CONTINUE
        code = codes[state["i"]] if state["i"] < len(codes) else codes[-1]
        state["i"] += 1
        return code

    return make_node(fn, "m_call")


# ---------------------------------------------------------------------------
# se_sequence — dispatch table
# ---------------------------------------------------------------------------

def test_sequence_advances_oneshot_then_main_then_oneshot():
    events = []

    def log(inst, node):
        events.append(node["params"]["tag"])

    c1 = o(log, tag="one")
    c2 = scripted_m([SE_PIPELINE_DISABLE])
    c3 = o(log, tag="three")
    seq = make_node(F.se_sequence, "m_call", children=[c1, c2, c3])

    mod = new_module()
    inst = new_instance_from_tree(mod, seq)
    r = invoke_any(inst, seq, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert events == ["one", "three"]


def test_sequence_child_halts_sequence_pauses():
    body = scripted_m([SE_PIPELINE_HALT, SE_PIPELINE_DISABLE])
    seq = make_node(F.se_sequence, "m_call", children=[body])
    mod = new_module()
    inst = new_instance_from_tree(mod, seq)
    r1 = invoke_any(inst, seq, EVENT_TICK, {})
    assert r1 == SE_PIPELINE_CONTINUE  # body halted, seq pauses
    r2 = invoke_any(inst, seq, EVENT_TICK, {})
    assert r2 == SE_PIPELINE_DISABLE   # body disabled, seq complete


def test_sequence_rewrites_function_halt_to_pipeline_halt():
    body = make_node(RC.return_function_halt, "m_call")
    seq = make_node(F.se_sequence, "m_call", children=[body])
    mod = new_module()
    inst = new_instance_from_tree(mod, seq)
    r = invoke_any(inst, seq, EVENT_TICK, {})
    # FUNCTION_HALT from child → sequence returns PIPELINE_HALT
    assert r == SE_PIPELINE_HALT


def test_sequence_propagates_application_codes_unchanged():
    body = make_node(RC.return_halt, "m_call")  # application SE_HALT = 1
    seq = make_node(F.se_sequence, "m_call", children=[body])
    mod = new_module()
    inst = new_instance_from_tree(mod, seq)
    r = invoke_any(inst, seq, EVENT_TICK, {})
    from se_runtime import SE_HALT
    assert r == SE_HALT  # propagated unchanged


# ---------------------------------------------------------------------------
# se_sequence_once — fires all children in one tick
# ---------------------------------------------------------------------------

def test_sequence_once_fires_all_children_one_tick():
    events = []

    def log(inst, node):
        events.append(node["params"]["tag"])

    c1 = o(log, tag="a")
    c2 = o(log, tag="b")
    c3 = o(log, tag="c")
    seq = make_node(F.se_sequence_once, "m_call", children=[c1, c2, c3])

    mod = new_module()
    inst = new_instance_from_tree(mod, seq)
    r = invoke_any(inst, seq, EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert events == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# se_if_then_else
# ---------------------------------------------------------------------------

def test_if_then_else_picks_then_when_true():
    then_calls = []
    else_calls = []

    def then_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            then_calls.append(1)
        return SE_PIPELINE_DISABLE

    def else_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            else_calls.append(1)
        return SE_PIPELINE_DISABLE

    tree = make_node(F.se_if_then_else, "m_call", children=[
        pred(P.true_pred),
        make_node(then_fn, "m_call"),
        make_node(else_fn, "m_call"),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_TICK, {})
    assert then_calls == [1]
    assert else_calls == []


def test_if_then_else_picks_else_when_false():
    else_calls = []

    def else_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            else_calls.append(1)
        return SE_PIPELINE_DISABLE

    tree = make_node(F.se_if_then_else, "m_call", children=[
        pred(P.false_pred),
        make_node(lambda *_: SE_PIPELINE_DISABLE, "m_call"),
        make_node(else_fn, "m_call"),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_TICK, {})
    assert else_calls == [1]


def test_if_then_with_no_else_and_false_pred_returns_continue():
    tree = make_node(F.se_if_then_else, "m_call", children=[
        pred(P.false_pred),
        make_node(lambda *_: SE_PIPELINE_DISABLE, "m_call"),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    r = invoke_any(inst, tree, EVENT_TICK, {})
    assert r == SE_PIPELINE_CONTINUE


def test_if_then_else_requires_at_least_2_children():
    tree = make_node(F.se_if_then_else, "m_call", children=[pred(P.true_pred)])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    with pytest.raises(ValueError, match="at least predicate"):
        invoke_any(inst, tree, EVENT_TICK, {})


# ---------------------------------------------------------------------------
# se_while
# ---------------------------------------------------------------------------

def test_while_runs_body_until_pred_false():
    # Predicate reads a dict counter; body increments it; loop stops at 3.
    pred_node = pred(P.dict_lt, key="i", value=3)
    body_oneshot = o(O.dict_inc, key="i")
    # Wrap oneshot in a sequence so it returns PIPELINE_DISABLE when done
    body = make_node(F.se_sequence_once, "m_call", children=[body_oneshot])
    w = make_node(F.se_while, "m_call", children=[pred_node, body])

    mod = new_module(dictionary={"i": 0})
    inst = new_instance_from_tree(mod, w)

    # Tick until DISABLE. While uses FUNCTION_HALT/PIPELINE_HALT between iterations.
    results = []
    for _ in range(30):
        r = invoke_any(inst, w, EVENT_TICK, {})
        results.append(r)
        if r == SE_PIPELINE_DISABLE:
            break
    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["i"] == 3


# ---------------------------------------------------------------------------
# se_cond
# ---------------------------------------------------------------------------

def test_cond_picks_first_matching_pred():
    def action(tag):
        def fn(inst, node, event_id, event_data):
            if event_id not in (EVENT_INIT, EVENT_TERMINATE):
                node["user_data"] = tag
            return SE_PIPELINE_CONTINUE
        return make_node(fn, "m_call")

    a1 = action("matched_a")
    a2 = action("matched_b")

    tree = make_node(F.se_cond, "m_call",
                     params={"has_else": False},
                     children=[pred(P.false_pred), a1, pred(P.true_pred), a2])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_TICK, {})
    assert a2["user_data"] == "matched_b"
    assert a1.get("user_data") is None


def test_cond_uses_default_when_nothing_matches():
    default_called = []

    def default_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            default_called.append(1)
        return SE_PIPELINE_CONTINUE

    tree = make_node(F.se_cond, "m_call",
                     params={"has_else": True},
                     children=[
                         pred(P.false_pred),
                         make_node(lambda *_: SE_PIPELINE_CONTINUE, "m_call"),
                         make_node(default_fn, "m_call"),
                     ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_TICK, {})
    assert default_called == [1]


# ---------------------------------------------------------------------------
# se_trigger_on_change
# ---------------------------------------------------------------------------

def test_trigger_on_change_rising_fires_on_edge():
    rising_calls = []

    def rising_action(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            rising_calls.append(1)
        return SE_PIPELINE_DISABLE

    tree = make_node(F.se_trigger_on_change, "m_call",
                     params={"initial": 0},
                     children=[
                         pred(P.dict_eq, key="flag", value=1),
                         make_node(rising_action, "m_call"),
                     ])

    mod = new_module(dictionary={"flag": 0})
    inst = new_instance_from_tree(mod, tree)

    # tick 1: flag=0, no edge
    invoke_any(inst, tree, EVENT_TICK, {})
    assert rising_calls == []

    # tick 2: flag=1, rising edge → fires
    mod["dictionary"]["flag"] = 1
    invoke_any(inst, tree, EVENT_TICK, {})
    assert rising_calls == [1]

    # tick 3: flag still 1, no edge
    invoke_any(inst, tree, EVENT_TICK, {})
    assert rising_calls == [1]


def test_trigger_on_change_falling_optional():
    rising = []
    falling = []

    def rising_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            rising.append(1)
        return SE_PIPELINE_DISABLE

    def falling_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            falling.append(1)
        return SE_PIPELINE_DISABLE

    tree = make_node(F.se_trigger_on_change, "m_call",
                     params={"initial": 0},
                     children=[
                         pred(P.dict_eq, key="flag", value=1),
                         make_node(rising_fn, "m_call"),
                         make_node(falling_fn, "m_call"),
                     ])

    mod = new_module(dictionary={"flag": 0})
    inst = new_instance_from_tree(mod, tree)

    mod["dictionary"]["flag"] = 1
    invoke_any(inst, tree, EVENT_TICK, {})  # rising
    mod["dictionary"]["flag"] = 0
    invoke_any(inst, tree, EVENT_TICK, {})  # falling

    assert rising == [1]
    assert falling == [1]


# ---------------------------------------------------------------------------
# se_chain_flow
# ---------------------------------------------------------------------------

def test_chain_flow_ticks_every_active_child_each_event():
    c1_count = []
    c2_count = []

    def c1_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            c1_count.append(1)
        return SE_PIPELINE_CONTINUE

    def c2_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            c2_count.append(1)
        return SE_PIPELINE_CONTINUE

    tree = make_node(F.se_chain_flow, "m_call", children=[
        make_node(c1_fn, "m_call"),
        make_node(c2_fn, "m_call"),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    for _ in range(3):
        invoke_any(inst, tree, EVENT_TICK, {})
    assert len(c1_count) == 3
    assert len(c2_count) == 3


def test_chain_flow_disables_child_on_pipeline_disable():
    c1_count = []

    def c1_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            c1_count.append(1)
            return SE_PIPELINE_DISABLE
        return SE_PIPELINE_CONTINUE

    c2_count = []

    def c2_fn(inst, node, event_id, event_data):
        if event_id not in (EVENT_INIT, EVENT_TERMINATE):
            c2_count.append(1)
        return SE_PIPELINE_CONTINUE

    tree = make_node(F.se_chain_flow, "m_call", children=[
        make_node(c1_fn, "m_call"),
        make_node(c2_fn, "m_call"),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    invoke_any(inst, tree, EVENT_TICK, {})
    invoke_any(inst, tree, EVENT_TICK, {})
    assert len(c1_count) == 1  # DISABLED after first tick
    assert len(c2_count) == 2  # keeps running


# ---------------------------------------------------------------------------
# se_fork
# ---------------------------------------------------------------------------

def test_fork_completes_when_all_main_children_disable():
    tree = make_node(F.se_fork, "m_call", children=[
        scripted_m([SE_PIPELINE_DISABLE]),
        scripted_m([SE_PIPELINE_CONTINUE, SE_PIPELINE_DISABLE]),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    r1 = invoke_any(inst, tree, EVENT_TICK, {})
    assert r1 == SE_PIPELINE_CONTINUE  # second child still running
    r2 = invoke_any(inst, tree, EVENT_TICK, {})
    assert r2 == SE_PIPELINE_DISABLE  # both done


# ---------------------------------------------------------------------------
# se_fork_join
# ---------------------------------------------------------------------------

def test_fork_join_returns_function_halt_while_children_running():
    tree = make_node(F.se_fork_join, "m_call", children=[
        scripted_m([SE_PIPELINE_CONTINUE, SE_PIPELINE_DISABLE]),
        scripted_m([SE_PIPELINE_CONTINUE, SE_PIPELINE_DISABLE]),
    ])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    r1 = invoke_any(inst, tree, EVENT_TICK, {})
    assert r1 == SE_FUNCTION_HALT
    r2 = invoke_any(inst, tree, EVENT_TICK, {})
    assert r2 == SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# se_function_interface
# ---------------------------------------------------------------------------

def test_function_interface_returns_function_disable_when_empty():
    tree = make_node(F.se_function_interface, "m_call", children=[])
    mod = new_module()
    inst = new_instance_from_tree(mod, tree)
    r = invoke_any(inst, tree, EVENT_TICK, {})
    assert r == SE_FUNCTION_DISABLE
