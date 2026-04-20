"""Predicate builtin tests."""

import pytest

from se_builtins import pred as P
from se_dsl import make_node
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_HALT,
    invoke_any,
    invoke_pred,
    new_instance_from_tree,
    new_module,
)


def _pred(fn, **params):
    return make_node(fn, "p_call", params=params)


def _composite(fn, *children):
    return make_node(fn, "p_call", children=children)


def _inst(dictionary=None):
    mod = new_module(dictionary=dictionary or {})
    # Needs some root; we'll directly call invoke_pred on the pred node below.
    return mod


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_true_pred_and_false_pred():
    mod = _inst()
    inst = new_instance_from_tree(mod, _pred(P.true_pred))
    assert invoke_pred(inst, _pred(P.true_pred)) is True
    assert invoke_pred(inst, _pred(P.false_pred)) is False


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------

def test_pred_and_short_circuits():
    mod = _inst()
    tracker = {"right_hit": 0}

    def tracking_false(inst, node):
        tracker["right_hit"] += 1
        return False

    tracked = make_node(tracking_false, "p_call")
    node = _composite(P.pred_and, _pred(P.false_pred), tracked)
    inst = new_instance_from_tree(mod, node)
    assert invoke_pred(inst, node) is False
    assert tracker["right_hit"] == 0  # short-circuited on first False


def test_pred_or_short_circuits():
    mod = _inst()
    tracker = {"right_hit": 0}

    def tracking_true(inst, node):
        tracker["right_hit"] += 1
        return True

    tracked = make_node(tracking_true, "p_call")
    node = _composite(P.pred_or, _pred(P.true_pred), tracked)
    inst = new_instance_from_tree(mod, node)
    assert invoke_pred(inst, node) is True
    assert tracker["right_hit"] == 0


def test_pred_not_requires_exactly_one_child():
    mod = _inst()
    node = _composite(P.pred_not, _pred(P.true_pred), _pred(P.true_pred))
    inst = new_instance_from_tree(mod, node)
    with pytest.raises(ValueError, match="exactly 1 child"):
        invoke_pred(inst, node)


def test_pred_not_negates():
    mod = _inst()
    inst = new_instance_from_tree(mod, _pred(P.true_pred))
    t = _composite(P.pred_not, _pred(P.true_pred))
    f = _composite(P.pred_not, _pred(P.false_pred))
    assert invoke_pred(inst, t) is False
    assert invoke_pred(inst, f) is True


def test_pred_nor_and_nand():
    mod = _inst()
    inst = new_instance_from_tree(mod, _pred(P.true_pred))
    nor = _composite(P.pred_nor, _pred(P.false_pred), _pred(P.false_pred))
    nand = _composite(P.pred_nand, _pred(P.true_pred), _pred(P.false_pred))
    assert invoke_pred(inst, nor) is True
    assert invoke_pred(inst, nand) is True


def test_pred_xor_counts_odd_trues():
    mod = _inst()
    inst = new_instance_from_tree(mod, _pred(P.true_pred))
    odd = _composite(P.pred_xor, _pred(P.true_pred), _pred(P.false_pred), _pred(P.false_pred))
    even = _composite(P.pred_xor, _pred(P.true_pred), _pred(P.true_pred))
    assert invoke_pred(inst, odd) is True
    assert invoke_pred(inst, even) is False


# ---------------------------------------------------------------------------
# Event predicate
# ---------------------------------------------------------------------------

def test_check_event_matches_current_event_id():
    mod = _inst()
    node = _pred(P.check_event, event_id="sensor.updated")
    inst = new_instance_from_tree(mod, node)
    # Simulate that we're mid-tick handling this event
    inst["current_event_id"] = "sensor.updated"
    assert invoke_pred(inst, node) is True
    inst["current_event_id"] = "other"
    assert invoke_pred(inst, node) is False


# ---------------------------------------------------------------------------
# Dict comparisons
# ---------------------------------------------------------------------------

def test_dict_eq_and_ne():
    mod = _inst({"temp": 42})
    inst = new_instance_from_tree(mod, _pred(P.dict_eq, key="temp", value=42))
    assert invoke_pred(inst, _pred(P.dict_eq, key="temp", value=42)) is True
    assert invoke_pred(inst, _pred(P.dict_eq, key="temp", value=0)) is False
    assert invoke_pred(inst, _pred(P.dict_ne, key="temp", value=0)) is True


def test_dict_comparison_family():
    mod = _inst({"x": 5})
    inst = new_instance_from_tree(mod, _pred(P.dict_gt, key="x", value=0))
    assert invoke_pred(inst, _pred(P.dict_gt, key="x", value=4)) is True
    assert invoke_pred(inst, _pred(P.dict_ge, key="x", value=5)) is True
    assert invoke_pred(inst, _pred(P.dict_lt, key="x", value=6)) is True
    assert invoke_pred(inst, _pred(P.dict_le, key="x", value=5)) is True
    assert invoke_pred(inst, _pred(P.dict_gt, key="x", value=5)) is False


def test_dict_in_range():
    mod = _inst({"pressure": 42})
    inst = new_instance_from_tree(mod, _pred(P.dict_in_range, key="pressure", min=0, max=100))
    assert invoke_pred(inst, _pred(P.dict_in_range, key="pressure", min=0, max=100)) is True
    assert invoke_pred(inst, _pred(P.dict_in_range, key="pressure", min=50, max=100)) is False
    assert invoke_pred(inst, _pred(P.dict_in_range, key="pressure", min=42, max=42)) is True


# ---------------------------------------------------------------------------
# Counter predicates
# ---------------------------------------------------------------------------

def test_dict_inc_and_test():
    mod = _inst({})
    node = _pred(P.dict_inc_and_test, key="counter", threshold=3)
    inst = new_instance_from_tree(mod, node)
    assert invoke_pred(inst, node) is False  # counter = 1
    assert invoke_pred(inst, node) is False  # counter = 2
    assert invoke_pred(inst, node) is True   # counter = 3
    assert mod["dictionary"]["counter"] == 3


def test_state_inc_and_test():
    mod = _inst()
    node = _pred(P.state_inc_and_test, threshold=2)
    inst = new_instance_from_tree(mod, node)
    assert invoke_pred(inst, node) is False  # state = 1
    assert invoke_pred(inst, node) is True   # state = 2
    assert node["state"] == 2


# ---------------------------------------------------------------------------
# Pipeline integration — pred via invoke_any returns PIPELINE_CONTINUE/HALT
# ---------------------------------------------------------------------------

def test_pred_via_invoke_any_returns_pipeline_codes():
    mod = _inst({"x": 5})
    inst = new_instance_from_tree(mod, _pred(P.true_pred))
    assert invoke_any(inst, _pred(P.true_pred), EVENT_TICK, {}) == SE_PIPELINE_CONTINUE
    assert invoke_any(inst, _pred(P.false_pred), EVENT_TICK, {}) == SE_PIPELINE_HALT
