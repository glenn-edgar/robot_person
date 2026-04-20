import pytest

from se_runtime import load_module, new_module, register_tree


def test_new_module_defaults():
    mod = new_module()
    assert mod["dictionary"] == {}
    assert dict(mod["constants"]) == {}
    assert mod["trees"] == {}
    assert callable(mod["get_time"])
    assert callable(mod["logger"])


def test_constants_are_read_only():
    mod = new_module(constants={"MAX_FLOW": 10.0})
    assert mod["constants"]["MAX_FLOW"] == 10.0
    with pytest.raises(TypeError):
        mod["constants"]["MAX_FLOW"] = 20.0


def test_dictionary_is_mutable():
    mod = new_module(dictionary={"x": 1})
    mod["dictionary"]["x"] = 2
    mod["dictionary"]["y"] = 99
    assert mod["dictionary"] == {"x": 2, "y": 99}


def test_collision_between_dictionary_and_constants_raises():
    with pytest.raises(ValueError, match="share keys"):
        new_module(dictionary={"k": 1}, constants={"k": 2})


def test_register_tree():
    mod = new_module()
    tree = {"fn": None, "call_type": "m_call", "children": []}
    register_tree(mod, "main", tree)
    assert mod["trees"]["main"] is tree


def test_load_module_wraps_constants():
    src = {
        "dictionary": {"a": 1},
        "constants": {"B": 2},
        "trees": {},
    }
    mod = load_module(src)
    with pytest.raises(TypeError):
        mod["constants"]["B"] = 3
    assert mod["dictionary"]["a"] == 1


def test_load_module_detects_collision():
    src = {"dictionary": {"k": 1}, "constants": {"k": 2}}
    with pytest.raises(ValueError):
        load_module(src)
