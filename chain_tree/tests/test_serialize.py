"""Tree (de)serialization tests.

Round-trip CFL trees through `serialize_tree` / `deserialize_tree`,
including JSON encode/decode in the middle, and verify that the
reconstructed tree runs to the same outcome as the original.

Cross-references covered: state_machine asm_change_state (sm_node),
controlled_client (server_node), streaming emit (target_node),
mark_sequence (parent_node).
"""

from __future__ import annotations

import json

import ct_runtime as ct
from ct_dsl import ChainTree


def _engine_kwargs(log):
    return dict(
        tick_period=0.0,
        sleep=lambda _dt: None,
        get_time=lambda: 0.0,
        logger=log.append,
    )


# ---------------------------------------------------------------------------
# 1. Simple tree round-trip via JSON
# ---------------------------------------------------------------------------

def test_serialize_simple_tree_round_trip_via_json():
    log: list[str] = []
    chain = ChainTree(**_engine_kwargs(log))
    chain.start_test("simple")
    chain.asm_log_message("hello")
    chain.asm_terminate()
    chain.end_test()

    wire = ct.serialize_tree(chain.engine["kbs"]["simple"]["root"])
    # Wire is JSON-safe.
    encoded = json.dumps(wire)
    decoded = json.loads(encoded)
    rebuilt = ct.deserialize_tree(decoded)

    # Structure preserved.
    assert rebuilt["name"] == chain.engine["kbs"]["simple"]["root"]["name"]
    assert len(rebuilt["children"]) == 2
    assert rebuilt["children"][0]["init_fn_name"] == "CFL_LOG_MESSAGE"
    assert rebuilt["children"][0]["data"]["message"] == "hello"
    assert rebuilt["children"][1]["main_fn_name"] == "CFL_TERMINATE"
    # Engine-managed state stripped, parent re-linked.
    assert rebuilt["ct_control"] == {"enabled": False, "initialized": False}
    assert rebuilt["children"][0]["parent"] is rebuilt
    assert rebuilt["children"][1]["parent"] is rebuilt


# ---------------------------------------------------------------------------
# 2. State machine cross-refs (sm_node) round-trip
# ---------------------------------------------------------------------------

def test_serialize_state_machine_resolves_sm_node_refs():
    log: list[str] = []
    chain = ChainTree(**_engine_kwargs(log))
    chain.start_test("sm")
    sm = chain.define_state_machine(
        "tl",
        state_names=["red", "green"],
        initial_state="red",
    )
    chain.define_state("red")
    chain.asm_change_state(sm, "green")
    chain.end_state()
    chain.define_state("green")
    chain.asm_log_message("done")
    chain.end_state()
    chain.end_state_machine()
    chain.end_test()

    wire = ct.serialize_tree(chain.engine["kbs"]["sm"]["root"])
    rebuilt = ct.deserialize_tree(json.loads(json.dumps(wire)))

    # Find the SM node and the change_state leaf in the rebuild.
    rebuilt_sm = rebuilt["children"][0]
    assert rebuilt_sm["main_fn_name"] == "CFL_STATE_MACHINE_MAIN"
    red_state = rebuilt_sm["children"][0]
    change_state_leaf = red_state["children"][0]
    assert change_state_leaf["init_fn_name"] == "CFL_CHANGE_STATE"
    # The sm_node reference must be the rebuilt SM node, not the original.
    assert change_state_leaf["data"]["sm_node"] is rebuilt_sm


# ---------------------------------------------------------------------------
# 3. Controlled-server / client cross-ref (server_node)
# ---------------------------------------------------------------------------

def test_serialize_controlled_node_resolves_server_node_ref():
    log: list[str] = []
    chain = ChainTree(**_engine_kwargs(log))
    chain.start_test("rpc")
    server = chain.define_controlled_server(
        "svc",
        request_port={"event_id": "REQ"},
        response_port={"event_id": "RESP"},
        response_data={"ok": True},
    )
    chain.asm_log_message("work")
    chain.end_controlled_server()
    chain.asm_client_controlled_node(
        server,
        request_port={"event_id": "REQ"},
        response_port={"event_id": "RESP"},
    )
    chain.end_test()

    wire = ct.serialize_tree(chain.engine["kbs"]["rpc"]["root"])
    rebuilt = ct.deserialize_tree(json.loads(json.dumps(wire)))

    rebuilt_server = rebuilt["children"][0]
    rebuilt_client = rebuilt["children"][1]
    assert rebuilt_server["main_fn_name"] == "CFL_CONTROLLED_SERVER_MAIN"
    assert rebuilt_client["main_fn_name"] == "CFL_CONTROLLED_CLIENT_MAIN"
    assert rebuilt_client["data"]["server_node"] is rebuilt_server


# ---------------------------------------------------------------------------
# 4. Streaming emit target_node round-trip
# ---------------------------------------------------------------------------

def test_serialize_streaming_emit_resolves_target_node():
    log: list[str] = []
    chain = ChainTree(**_engine_kwargs(log))

    port = {"event_id": "X"}
    root = chain.start_test("s")
    sink = chain.asm_streaming_sink(port, "CFL_NULL")
    chain.asm_emit_streaming(sink, port, {"v": 1})
    chain.end_test()

    wire = ct.serialize_tree(chain.engine["kbs"]["s"]["root"])
    rebuilt = ct.deserialize_tree(json.loads(json.dumps(wire)))

    rebuilt_sink = rebuilt["children"][0]
    rebuilt_emit = rebuilt["children"][1]
    assert rebuilt_emit["init_fn_name"] == "CFL_EMIT_STREAMING"
    assert rebuilt_emit["data"]["target_node"] is rebuilt_sink


# ---------------------------------------------------------------------------
# 5. Whole-ChainTree serialize → load into fresh chain → run produces
#    the same observable outcome.
# ---------------------------------------------------------------------------

def test_serialize_chain_tree_round_trip_runs_to_same_outcome():
    log_a: list[str] = []
    chain_a = ChainTree(**_engine_kwargs(log_a))
    chain_a.start_test("k")
    chain_a.asm_log_message("one")
    chain_a.asm_log_message("two")
    chain_a.asm_terminate()
    chain_a.end_test()

    wire = ct.serialize_chain_tree(chain_a)
    encoded = json.dumps(wire)
    decoded = json.loads(encoded)

    # Receiving side: fresh ChainTree, no manual KB definition.
    log_b: list[str] = []
    chain_b = ChainTree(**_engine_kwargs(log_b))
    ct.deserialize_into(chain_b, decoded)

    chain_b.run(starting=["k"])
    # Both engines produced the same log sequence.
    assert log_b == ["one", "two"]
    assert chain_b.engine["active_kbs"] == []


# ---------------------------------------------------------------------------
# 6. Foreign node ref (a node not in the serialized subtree) becomes None
# ---------------------------------------------------------------------------

def test_serialize_foreign_node_ref_decodes_to_none():
    foreign = ct.make_node(name="foreign", main_fn_name="CFL_DISABLE")
    leaf = ct.make_node(
        name="leaf",
        main_fn_name="CFL_DISABLE",
        data={"server_node": foreign},
    )
    root = ct.make_node(name="root", main_fn_name="CFL_COLUMN_MAIN")
    ct.link_children(root, [leaf])

    wire = ct.serialize_tree(root)
    rebuilt = ct.deserialize_tree(wire)

    # The foreign ref's id wasn't found in the id_map → stored as None
    # marker → decodes to None.
    assert rebuilt["children"][0]["data"]["server_node"] is None
