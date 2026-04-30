"""CFL builtins for the s_engine bridge — three node types.

Decomposition rationale (continue.md):
  - se_module_load   builds the s_engine module sharing kb["blackboard"]
  - se_tree_create   instantiates a named tree from that module
  - se_tick          composite; aux fn drives interaction per CFL tick

`se_module_load` and `se_tree_create` are leaves whose MAIN returns
CFL_DISABLE on the first visit — once their INIT has stamped the module /
instance into the blackboard, they have nothing more to do. Cleanup
happens implicitly: when the KB blackboard is dropped, Python GC'es the
module and instance.

`se_tick` is composite: its CFL children are subtrees the s_engine tree
enables/disables via bridge oneshots (cfl_enable_child etc.). The owning
se_tick node ref is stamped on the instance every tick, so bridge fns can
reach it via `inst["cfl_tick_node"]`.
"""

from __future__ import annotations

from se_runtime import new_instance_from_tree, new_module

from ct_bridge import BRIDGE_FN_REGISTRY
from ct_runtime.codes import CFL_CONTINUE, CFL_DISABLE
from ct_runtime.registry import lookup_boolean


# ---------------------------------------------------------------------------
# se_module_load
# ---------------------------------------------------------------------------
#
# node["data"] schema:
#   {
#       "key":         str,                # blackboard key for the module obj
#       "trees":       {tree_name: tree_root_dict, ...}  # in-memory trees
#       "constants":   dict | None,        # passed to new_module
#       "fn_registry": dict | None,        # extra user fns merged with bridge fns
#   }

def se_module_load_init(handle, node) -> None:
    data = node["data"]
    key = data["key"]
    trees = data.get("trees") or {}

    # Bridge fns first; user fns override on name conflict.
    fn_registry = dict(BRIDGE_FN_REGISTRY)
    if data.get("fn_registry"):
        fn_registry.update(data["fn_registry"])

    engine = handle["engine"]
    module = new_module(
        dictionary=handle["blackboard"],
        constants=data.get("constants"),
        trees=trees,
        fn_registry=fn_registry,
        logger=engine["logger"],
        get_wall_time=engine.get("get_wall_time"),
        timezone=engine.get("timezone"),
    )
    # `new_module` defensively copies its `dictionary` arg. Reassign to share
    # the blackboard by reference — that identity-equality is the WHOLE point
    # of the bridge: writes from s_engine fns must be visible to CFL fns and
    # vice versa, with no copy-back step.
    module["dictionary"] = handle["blackboard"]
    handle["blackboard"][key] = module


def se_module_load_term(handle, node) -> None:
    """No-op. The module dies with the KB blackboard via Python GC; explicit
    deletion would only matter if the user wants to recycle the same
    blackboard key for a different module mid-run.
    """
    return None


def se_module_load_main(handle, bool_fn_name, node, event):
    """One-shot lifetime: INIT did the work, MAIN immediately disables so
    the column advances to the next sibling (e.g. se_tree_create).
    """
    return CFL_DISABLE


# ---------------------------------------------------------------------------
# se_tree_create
# ---------------------------------------------------------------------------
#
# node["data"] schema:
#   {
#       "key":        str,                # blackboard key for the instance
#       "module_key": str,                # blackboard key holding the module
#       "tree_name":  str,                # tree to instantiate from module
#   }

def se_tree_create_init(handle, node) -> None:
    data = node["data"]
    module = handle["blackboard"][data["module_key"]]
    tree = module["trees"][data["tree_name"]]

    inst = new_instance_from_tree(module, tree)
    # CFL back-pointers stamped here so bridge fns can find them.
    inst["_cfl_kb"] = handle
    inst["_cfl_engine"] = handle["engine"]
    inst["cfl_tick_node"] = None  # set by SE_TICK_MAIN on each tick
    handle["blackboard"][data["key"]] = inst


def se_tree_create_term(handle, node) -> None:
    return None


def se_tree_create_main(handle, bool_fn_name, node, event):
    return CFL_DISABLE


# ---------------------------------------------------------------------------
# se_tick — composite, aux-driven
# ---------------------------------------------------------------------------
#
# node["data"] schema:
#   {
#       "tree_key":    str,            # blackboard key holding the instance
#       "return_code": str,            # default code returned to walker;
#                                       # aux fn can overwrite per-tick
#   }
#
# Aux fn signature: standard boolean — fn(handle, node, event_type,
# event_id, event_data). It:
#   - reads the inst at handle["blackboard"][node["data"]["tree_key"]]
#   - pushes events into the inst, calls run_until_idle, etc.
#   - writes its chosen CFL code into node["data"]["return_code"]
#   - return value is ignored
#
# The boolean_fn_name slot on the se_tick CFL node IS the aux fn name —
# the standard "aux" hook for composites. SE_TICK_MAIN looks it up and
# calls it.

def se_tick_main(handle, aux_fn_name, node, event):
    tree_key = node["data"]["tree_key"]
    inst = handle["blackboard"].get(tree_key)
    if inst is None:
        raise RuntimeError(
            f"SE_TICK_MAIN: no s_engine instance at blackboard[{tree_key!r}] — "
            "did se_tree_create run before this tick?"
        )
    # Stamp every tick so bridge fns can reach this CFL node from the
    # instance. Idempotent.
    inst["cfl_tick_node"] = node

    if aux_fn_name and aux_fn_name != "CFL_NULL":
        aux = lookup_boolean(handle["engine"]["registry"], aux_fn_name)
        if aux is None:
            raise LookupError(
                f"SE_TICK_MAIN: aux fn {aux_fn_name!r} not in registry"
            )
        aux(handle, node, event["event_type"], event["event_id"], event["data"])

    return node["data"].get("return_code", CFL_CONTINUE)
