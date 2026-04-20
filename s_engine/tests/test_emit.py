"""emit_module_file tests — emit to file, re-import, run through load_module."""

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

import se_dsl as dsl
from se_runtime import (
    EVENT_TICK,
    SE_PIPELINE_DISABLE,
    emit_module_file,
    invoke_any,
    load_module,
    new_instance,
    new_module,
    register_tree,
)


def _import_file(path: Path, module_name: str):
    """Import a .py file as a module and return its namespace."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Basic emit + re-import
# ---------------------------------------------------------------------------

def test_emit_produces_valid_python_file(tmp_path):
    mod = new_module(
        dictionary={"counter": 0, "mode": "idle"},
        constants={"MAX_STEPS": 100},
    )
    register_tree(mod, "main", dsl.sequence(
        dsl.dict_inc("counter"),
        dsl.dict_set("mode", "done"),
    ))

    out = tmp_path / "emitted.py"
    emit_module_file(mod, str(out), header="# Test-emitted plan")

    # File exists, is non-empty, has `MODULE = `
    content = out.read_text()
    assert "MODULE = " in content
    assert "from se_builtins.flow_control import se_sequence" in content
    assert "from se_builtins.oneshot import" in content
    assert "# Test-emitted plan" in content


def test_emitted_module_can_be_loaded_and_executed(tmp_path):
    original_mod = new_module(
        dictionary={"counter": 0},
        constants={"MAX": 10},
    )
    register_tree(original_mod, "main", dsl.sequence(
        dsl.dict_inc("counter", delta=5),
        dsl.dict_set("mode", "done"),
    ))

    out = tmp_path / "plan.py"
    emit_module_file(original_mod, str(out))

    # Add tmp_path to sys.path so we can import it
    mod_ns = _import_file(out, "plan_module_under_test")
    loaded = load_module(mod_ns.MODULE)

    inst = new_instance(loaded, "main")
    r = invoke_any(inst, loaded["trees"]["main"], EVENT_TICK, {})
    assert r == SE_PIPELINE_DISABLE
    assert loaded["dictionary"]["counter"] == 5
    assert loaded["dictionary"]["mode"] == "done"


def test_emitted_module_preserves_constants_immutability(tmp_path):
    mod = new_module(constants={"K": 42})
    register_tree(mod, "main", dsl.nop())

    out = tmp_path / "const.py"
    emit_module_file(mod, str(out))
    mod_ns = _import_file(out, "plan_const_test")
    loaded = load_module(mod_ns.MODULE)

    assert loaded["constants"]["K"] == 42
    with pytest.raises(TypeError):
        loaded["constants"]["K"] = 99


# ---------------------------------------------------------------------------
# Tuple keys survive the emit → import → load round-trip
# ---------------------------------------------------------------------------

def test_state_machine_tuple_keys_survive_emit_round_trip(tmp_path):
    sm = dsl.state_machine(
        states={
            "idle": dsl.dict_set("st", "idle"),
            "running": dsl.dict_set("st", "running"),
        },
        transitions={
            ("idle", "start"): "running",
            ("running", "stop"): "idle",
        },
        initial="idle",
    )
    mod = new_module()
    register_tree(mod, "main", sm)

    out = tmp_path / "sm.py"
    emit_module_file(mod, str(out))

    mod_ns = _import_file(out, "plan_sm_test")
    loaded = load_module(mod_ns.MODULE)

    tree = loaded["trees"]["main"]
    transitions = tree["params"]["transitions"]
    assert transitions[("idle", "start")] == "running"
    assert transitions[("running", "stop")] == "idle"


# ---------------------------------------------------------------------------
# Multi-module imports grouped correctly
# ---------------------------------------------------------------------------

def test_emitted_imports_group_by_source_module(tmp_path):
    plan = dsl.sequence(
        dsl.if_then_else(
            dsl.dict_eq("k", 1),
            dsl.log("then"),
            dsl.log("else"),
        ),
        dsl.time_delay(0.1),
        dsl.nop(),
    )
    mod = new_module()
    register_tree(mod, "main", plan)

    out = tmp_path / "multi.py"
    emit_module_file(mod, str(out))
    content = out.read_text()

    # Every builtin module referenced should get one `from X import ...`
    assert "from se_builtins.flow_control" in content
    assert "from se_builtins.pred import dict_eq" in content
    assert "from se_builtins.delays import" in content
    assert "from se_builtins.oneshot import log" in content


# ---------------------------------------------------------------------------
# Emit rejects conflicting fns with the same __name__
# ---------------------------------------------------------------------------

def test_emit_rejects_same_name_different_fns(tmp_path):
    def fn_a(inst, node, event_id, event_data):
        return 12

    def fn_b(inst, node, event_id, event_data):
        return 12

    # Rename both to the same public name
    fn_a.__name__ = "shared_name"
    fn_b.__name__ = "shared_name"

    plan = dsl.sequence(
        dsl.make_node(fn_a, "m_call"),
        dsl.make_node(fn_b, "m_call"),
    )
    mod = new_module()
    register_tree(mod, "main", plan)

    with pytest.raises(ValueError, match="share the name"):
        emit_module_file(mod, str(tmp_path / "bad.py"))
