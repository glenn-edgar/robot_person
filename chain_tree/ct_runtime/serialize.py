"""Tree (de)serialization — convert CFL trees to/from JSON-safe dicts.

Function names are already strings (`main_fn_name` etc.), so callable
refs aren't a concern here as they are in s_engine. The harder part is
internal node cross-references — `sm_node` in change_state leaves,
`server_node` in controlled clients, `target_node` in streaming emits,
`parent_node` in mark_sequence leaves. These are encoded as
`{"_node_ref": <id>}` markers; ids are sequential per `serialize_tree`
call, and `deserialize_tree` resolves them in a second pass after every
node has been built.

Engine-managed state (`parent` back-pointer, `ct_control` flags, `_kb`
back-pointer on the root) is stripped on the way out and rebuilt on the
way in — `ct_control` reset to {enabled: False, initialized: False},
parents re-linked from the children lists.

Round-trip survives `json.dumps` / `json.loads` for the structures the
DSL emits: lists, dicts, ints, floats, strings, bools, None. Tuples
become lists. Callables / arbitrary user objects in `data` are NOT
supported — those would force runtime resolution and leak abstraction.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


_NODE_REF = "_node_ref"


def serialize_tree(root: dict) -> dict:
    """Serialize the subtree rooted at `root` to a JSON-safe dict."""
    id_map: dict = {}

    def assign_ids(n: dict) -> None:
        id_map[id(n)] = len(id_map)
        for c in n.get("children", []) or []:
            assign_ids(c)

    assign_ids(root)

    def encode_value(v: Any) -> Any:
        # Detect a node reference by structural duck-typing — any dict
        # carrying a `ct_control` slot is one of our nodes.
        if isinstance(v, dict) and "ct_control" in v:
            return {_NODE_REF: id_map.get(id(v))}
        if isinstance(v, dict):
            return {k: encode_value(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [encode_value(x) for x in v]
        return v

    def encode_node(n: dict) -> dict:
        return {
            "_id": id_map[id(n)],
            "name": n.get("name", ""),
            "main_fn_name": n.get("main_fn_name"),
            "boolean_fn_name": n.get("boolean_fn_name"),
            "init_fn_name": n.get("init_fn_name"),
            "term_fn_name": n.get("term_fn_name"),
            "data": encode_value(n.get("data") or {}),
            "children": [encode_node(c) for c in n.get("children", []) or []],
        }

    return encode_node(root)


def deserialize_tree(wire: Mapping[str, Any], fn_registry: Optional[dict] = None) -> dict:
    """Reconstruct a CFL tree from `serialize_tree` output.

    `fn_registry` is accepted for API symmetry with s_engine's
    deserialize_tree but is unused — chain_tree resolves fn names against
    the engine registry at runtime, not at deserialize time. Pass nothing
    or your registry; either way is fine.
    """
    nodes_by_id: dict = {}

    def build(w: Mapping[str, Any]) -> dict:
        n = {
            "name": w.get("name", ""),
            "parent": None,
            "children": [],
            "main_fn_name": w.get("main_fn_name"),
            "boolean_fn_name": w.get("boolean_fn_name"),
            "init_fn_name": w.get("init_fn_name"),
            "term_fn_name": w.get("term_fn_name"),
            "ct_control": {"enabled": False, "initialized": False},
            # Stashed; resolved in pass 2.
            "data": {"__wire_data__": w.get("data") or {}},
        }
        nid = w.get("_id")
        if nid is not None:
            nodes_by_id[nid] = n
        for child_wire in w.get("children") or []:
            child = build(child_wire)
            child["parent"] = n
            n["children"].append(child)
        return n

    root = build(wire)

    def decode_value(v: Any) -> Any:
        if isinstance(v, dict) and _NODE_REF in v and len(v) == 1:
            return nodes_by_id.get(v[_NODE_REF])
        if isinstance(v, dict):
            return {k: decode_value(x) for k, x in v.items()}
        if isinstance(v, list):
            return [decode_value(x) for x in v]
        return v

    def fill_data(n: dict) -> None:
        wire_data = n["data"].pop("__wire_data__")
        n["data"] = decode_value(wire_data) if wire_data else {}
        for c in n["children"]:
            fill_data(c)

    fill_data(root)
    return root


def serialize_chain_tree(chain) -> dict:
    """Serialize every KB in a ChainTree.

    Output shape:
        {
            "kbs": {kb_name: <serialized tree>, ...},
        }

    Blackboard contents and engine clock state are NOT serialized —
    only structural definition. The receiver must construct a fresh
    ChainTree, register matching user fns, and call
    `deserialize_into(chain, wire)`.
    """
    kbs: dict = {}
    for name, kb in chain.engine["kbs"].items():
        kbs[name] = serialize_tree(kb["root"])
    return {"kbs": kbs}


def deserialize_into(chain, wire: Mapping[str, Any]) -> None:
    """Load `serialize_chain_tree` output into an existing ChainTree.

    The chain's registry must already contain every fn name referenced
    by the wire; `chain.run()`'s validation catches missing names but
    only at run time. `chain.validate()` (when available) can be called
    immediately after deserializing for early failure.
    """
    from .engine import add_kb, new_kb
    for name, root_wire in (wire.get("kbs") or {}).items():
        root = deserialize_tree(root_wire)
        kb = new_kb(name, root)
        add_kb(chain.engine, kb)
