"""s_engine-side bridge fns.

These are the callables an s_engine tree invokes to reach back into the CFL
engine. They follow s_engine's call signatures:

  o_call:  fn(inst, node) -> None
  p_call:  fn(inst, node) -> bool
  m_call:  fn(inst, node, event_id, event_data) -> int

Bridge fns find their CFL context via fields stamped onto the s_engine
instance by SE_TREE_CREATE_INIT and SE_TICK_MAIN:

  inst["module"]["dictionary"]    is the KB blackboard (shared by reference)
  inst["_cfl_kb"]                 the KB handle
  inst["_cfl_engine"]             the engine handle
  inst["cfl_tick_node"]           the owning se_tick CFL node
                                  (None until first se_tick MAIN call)

Per-call arguments live in node["params"]. s_engine bakes args into nodes —
e.g. an o_call leaf {fn: cfl_enable_child, params: {child_index: 0}} fires
once and enables the 0th CFL child.
"""

from __future__ import annotations

from ct_runtime import enable_node, enqueue, terminate_node_tree
from ct_runtime.codes import (
    CFL_EVENT_TYPE_NULL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
)
from ct_runtime.event_queue import make_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tick_node(inst: dict) -> dict:
    tick = inst.get("cfl_tick_node")
    if tick is None:
        raise RuntimeError(
            "ct_bridge: cfl_tick_node not set on instance — bridge fns can "
            "only run inside a se_tick MAIN dispatch"
        )
    return tick


# ---------------------------------------------------------------------------
# Child control
# ---------------------------------------------------------------------------

def cfl_enable_child(inst: dict, node: dict) -> None:
    """params: {child_index: int}"""
    enable_node(_tick_node(inst)["children"][node["params"]["child_index"]])


def cfl_disable_child(inst: dict, node: dict) -> None:
    """params: {child_index: int}"""
    tick = _tick_node(inst)
    child = tick["children"][node["params"]["child_index"]]
    terminate_node_tree(inst["_cfl_engine"], inst["_cfl_kb"], child)


def cfl_enable_children(inst: dict, node: dict) -> None:
    for c in _tick_node(inst)["children"]:
        enable_node(c)


def cfl_disable_children(inst: dict, node: dict) -> None:
    tick = _tick_node(inst)
    engine = inst["_cfl_engine"]
    kb = inst["_cfl_kb"]
    for c in tick["children"]:
        terminate_node_tree(engine, kb, c)


def cfl_i_disable_children(inst: dict, node: dict) -> None:
    """io_call variant — fires once per instance lifetime, useful for the
    start-of-life "disable everything until I say" idiom.
    """
    cfl_disable_children(inst, node)


def cfl_wait_child_disabled(inst: dict, node: dict, event_id, event_data):
    """m_call. params: {child_index: int}.
    Returns SE_PIPELINE_HALT while the named child is enabled, otherwise
    SE_PIPELINE_DISABLE so the s_engine subtree can advance.
    """
    from se_runtime import SE_PIPELINE_DISABLE, SE_PIPELINE_HALT
    child = _tick_node(inst)["children"][node["params"]["child_index"]]
    if child["ct_control"]["enabled"]:
        return SE_PIPELINE_HALT
    return SE_PIPELINE_DISABLE


# ---------------------------------------------------------------------------
# Bitmap / blackboard ops
# ---------------------------------------------------------------------------

def _names(node: dict) -> list:
    p = node["params"]
    if "names" in p:
        return list(p["names"])
    if "name" in p:
        return [p["name"]]
    return []


def cfl_set_bits(inst: dict, node: dict) -> None:
    bb = inst["module"]["dictionary"]
    for n in _names(node):
        bb[n] = True


def cfl_clear_bits(inst: dict, node: dict) -> None:
    bb = inst["module"]["dictionary"]
    for n in _names(node):
        bb[n] = False


def cfl_read_bit(inst: dict, node: dict) -> bool:
    """p_call. params: {name: str}"""
    return bool(inst["module"]["dictionary"].get(node["params"]["name"], False))


def cfl_s_bit_and(inst: dict, node: dict) -> bool:
    bb = inst["module"]["dictionary"]
    return all(bb.get(n, False) for n in _names(node))


def cfl_s_bit_or(inst: dict, node: dict) -> bool:
    bb = inst["module"]["dictionary"]
    return any(bb.get(n, False) for n in _names(node))


def cfl_s_bit_nor(inst: dict, node: dict) -> bool:
    return not cfl_s_bit_or(inst, node)


def cfl_s_bit_nand(inst: dict, node: dict) -> bool:
    return not cfl_s_bit_and(inst, node)


def cfl_s_bit_xor(inst: dict, node: dict) -> bool:
    bb = inst["module"]["dictionary"]
    return sum(1 for n in _names(node) if bb.get(n, False)) % 2 == 1


# ---------------------------------------------------------------------------
# Internal events — push back into the CFL engine queue
# ---------------------------------------------------------------------------

def cfl_internal_event(inst: dict, node: dict) -> None:
    """params:
        event_id:    str (required)
        event_type:  str = CFL_EVENT_TYPE_NULL
        event_data:  Any = None
        priority:    "normal" | "high" = "normal"
        target_node: <node ref> = owning se_tick node
    """
    p = node["params"]
    event = make_event(
        target=p.get("target_node") or _tick_node(inst),
        event_type=p.get("event_type", CFL_EVENT_TYPE_NULL),
        event_id=p["event_id"],
        data=p.get("event_data"),
        priority=p.get("priority", PRIORITY_NORMAL),
    )
    enqueue(inst["_cfl_engine"], event)


def cfl_internal_event_high(inst: dict, node: dict) -> None:
    """As cfl_internal_event but forces high priority. Convenience for the
    common 'preempt the normal queue' case.
    """
    p = dict(node["params"])
    p["priority"] = PRIORITY_HIGH
    cfl_internal_event(inst, {"params": p})


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def cfl_log(inst: dict, node: dict) -> None:
    inst["_cfl_engine"]["logger"](node["params"].get("message", ""))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BRIDGE_FN_REGISTRY = {
    "cfl_enable_child": cfl_enable_child,
    "cfl_disable_child": cfl_disable_child,
    "cfl_enable_children": cfl_enable_children,
    "cfl_disable_children": cfl_disable_children,
    "cfl_i_disable_children": cfl_i_disable_children,
    "cfl_wait_child_disabled": cfl_wait_child_disabled,
    "cfl_set_bits": cfl_set_bits,
    "cfl_clear_bits": cfl_clear_bits,
    "cfl_read_bit": cfl_read_bit,
    "cfl_s_bit_and": cfl_s_bit_and,
    "cfl_s_bit_or": cfl_s_bit_or,
    "cfl_s_bit_nor": cfl_s_bit_nor,
    "cfl_s_bit_nand": cfl_s_bit_nand,
    "cfl_s_bit_xor": cfl_s_bit_xor,
    "cfl_internal_event": cfl_internal_event,
    "cfl_internal_event_high": cfl_internal_event_high,
    "cfl_log": cfl_log,
}
