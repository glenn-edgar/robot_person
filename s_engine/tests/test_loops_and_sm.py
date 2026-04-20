"""Additional loop and state-machine scenarios ported from LuaJIT dsl_tests/.

Two specific edge cases not covered by the per-operator unit tests:
  1. Nested while_loop — inner counter must reset each outer iteration.
  2. Cyclic state_machine — returning to a state must re-INIT its child.
  3. Field-based (dict) counter driving a while_loop — ensures
     dict_inc_and_test composes with while_loop the same way
     state_inc_and_test does.
"""

from __future__ import annotations

import se_dsl as dsl
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_DISABLE,
    invoke_any,
    new_instance_from_tree,
    new_module,
)


# ===========================================================================
# 1. Nested while_loops — outer 3x, inner 4x → body fires 12 times total
# ===========================================================================

def test_nested_while_loops_inner_resets_each_outer_iteration():
    """Inner loop's state counter must be reset each time the outer loop
    re-enters the body — otherwise the inner pred stays false immediately
    on iteration 2 and the nested execution count is wrong."""

    inner = dsl.while_loop(
        dsl.dict_lt("inner", 4),
        dsl.sequence_once(
            dsl.dict_inc("body_hits"),
            dsl.dict_inc("inner"),
        ),
    )
    outer_body = dsl.sequence(
        dsl.dict_set("inner", 0),  # reset inner counter each outer iteration
        dsl.call_tree(inner),
        dsl.dict_inc("outer"),
    )
    plan = dsl.while_loop(dsl.dict_lt("outer", 3), outer_body)

    mod = new_module(dictionary={"outer": 0, "inner": 0, "body_hits": 0})
    inst = new_instance_from_tree(mod, plan)

    for _ in range(500):
        r = invoke_any(inst, plan, EVENT_TICK, {})
        if r == SE_PIPELINE_DISABLE:
            break

    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["outer"] == 3
    assert mod["dictionary"]["body_hits"] == 12  # 3 outer × 4 inner


# ===========================================================================
# 2. Cyclic state machine — state_a → state_b → state_c → state_a → ...
# ===========================================================================

def test_cyclic_state_machine_re_enters_state_freshly():
    """After cycling back to a previously-visited state, that state's
    action must fire again — i.e. transitioning out + back in resets
    the action's oneshot guard."""

    fire_log = []

    def logger(tag):
        def fn(inst, node):
            fire_log.append(tag)
        return dsl.make_node(fn, "o_call")

    sm = dsl.state_machine(
        states={
            "a": logger("A"),
            "b": logger("B"),
            "c": logger("C"),
        },
        transitions={
            ("a", "next"): "b",
            ("b", "next"): "c",
            ("c", "next"): "a",  # cycles back
        },
        initial="a",
    )

    mod = new_module()
    inst = new_instance_from_tree(mod, sm)

    # Tick to fire initial state action
    invoke_any(inst, sm, EVENT_TICK, {})
    assert fire_log == ["A"]

    # Step through a full cycle; each state should fire once as we enter it
    for _ in range(3):
        invoke_any(inst, sm, "next", {})

    # After a→b→c→a the sequence should be A, B, C, A
    assert fire_log == ["A", "B", "C", "A"]

    # Continue one more cycle to prove the guards stay re-entrant
    for _ in range(3):
        invoke_any(inst, sm, "next", {})
    assert fire_log == ["A", "B", "C", "A", "B", "C", "A"]


# ===========================================================================
# 3. Field-based (dict) counter driving a while_loop
# ===========================================================================
# Equivalent to loop_test_fn_2 from LuaJIT — uses dict_inc_and_test as
# the loop pred instead of state_inc_and_test. Verifies the counter value
# is tracked in the module dictionary, not on a node.

def test_while_loop_with_dict_inc_counter():
    body = dsl.sequence_once(dsl.dict_inc("body_hits"))
    # Loop until dict["counter"] reaches 5 (dict_inc_and_test returns True
    # at that point — and the while terminates on the NEXT pred evaluation
    # since dict_inc_and_test mutates and returns False while counter < 5).
    plan = dsl.while_loop(
        dsl.pred_not(dsl.dict_inc_and_test(key="counter", threshold=5)),
        body,
    )

    mod = new_module(dictionary={"counter": 0, "body_hits": 0})
    inst = new_instance_from_tree(mod, plan)

    for _ in range(100):
        r = invoke_any(inst, plan, EVENT_TICK, {})
        if r == SE_PIPELINE_DISABLE:
            break

    # dict_inc_and_test increments each tick: counter=1,2,3,4 → not(False)=True, body runs
    # At counter=5, inc_and_test returns True → pred_not returns False → loop disables
    assert r == SE_PIPELINE_DISABLE
    assert mod["dictionary"]["counter"] == 5
    assert mod["dictionary"]["body_hits"] == 4  # body ran for counter 1..4


# ===========================================================================
# 4. State machine with a long-running child action (not just oneshot)
# ===========================================================================
# LuaJIT state_machine test: each state has a tick_delay that keeps the
# state "alive" for multiple ticks before the transition fires.
# In Python, use a scripted m_call child that returns CONTINUE N times
# then DISABLE — the state_machine should keep invoking the same state's
# child until an event fires a transition, regardless of child DISABLE.

def test_state_machine_child_disable_does_not_advance_state():
    """A child returning DISABLE inside a state_machine is not a transition
    trigger — only the transition table drives state changes."""

    disables = {"a": 0, "b": 0}

    def disabling_child(tag):
        state = {"n": 0}

        def fn(inst, node, event_id, event_data):
            from se_runtime import EVENT_INIT, EVENT_TERMINATE
            if event_id in (EVENT_INIT, EVENT_TERMINATE):
                return 12  # PIPELINE_CONTINUE
            state["n"] += 1
            disables[tag] += 1
            return 16  # PIPELINE_DISABLE on every non-init tick
        return dsl.make_node(fn, "m_call")

    sm = dsl.state_machine(
        states={"a": disabling_child("a"), "b": disabling_child("b")},
        transitions={("a", "go"): "b"},
        initial="a",
    )

    mod = new_module()
    inst = new_instance_from_tree(mod, sm)

    # Tick state "a" multiple times — child keeps returning DISABLE, but sm
    # does NOT transition (no "go" event). It should keep invoking "a".
    for _ in range(3):
        invoke_any(inst, sm, EVENT_TICK, {})

    assert disables["a"] == 3
    assert disables["b"] == 0

    # Now fire the transition event
    invoke_any(inst, sm, "go", {})
    assert disables["b"] == 1
    assert sm["user_data"] == "b"
