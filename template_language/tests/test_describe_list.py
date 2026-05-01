"""Tests for describe_template and list_template (Phase D1+D2).

`describe_template` produces a §15-shaped JSON dict for one template.
`list_template` returns short-form metadata for templates matching all
supplied predicates. Together these are the LLM-discovery surface.
"""

from __future__ import annotations

from typing import Callable, Optional

import pytest

from template_language import (
    Codes,
    Kind,
    TemplateError,
    define_template,
    describe_template,
    list_template,
)
from template_language.recorder import _recorder_stack
from template_language.registry import clear_registry


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    _recorder_stack.clear()
    yield
    clear_registry()
    _recorder_stack.clear()


# ---- describe_template -----------------------------------------------

def test_describe_unknown_template_raises():
    with pytest.raises(TemplateError) as exc:
        describe_template("not.there")
    assert exc.value.code == Codes.UNKNOWN_TEMPLATE


def test_describe_minimal_shape():
    def fn(*, n: str): pass
    define_template("p", fn, kind="leaf", engine="chain_tree", describe="hi")
    d = describe_template("p")
    assert d == {
        "path": "p",
        "kind": "leaf",
        "engine": "chain_tree",
        "describe": "hi",
        "slots": [{
            "name": "n",
            "required": True,
            "kind": "STRING",
            "nullable": False,
            "default": None,
            "annotation": "str",
            "example": None,
        }],
    }


def test_describe_optional_callable_slot():
    def fn(*, action: Optional[Callable] = None):
        """Doc fallback."""
    define_template("p", fn, kind="leaf", engine="chain_tree")
    d = describe_template("p")
    assert d["describe"] == "Doc fallback."
    s = d["slots"][0]
    assert s["kind"] == "ACTION"
    assert s["nullable"] is True
    assert s["required"] is False
    assert s["default"] is None


def test_describe_includes_examples():
    def fn(*, a: str, b: int = 5): pass
    define_template("p", fn, kind="leaf", engine="chain_tree",
                    slot_examples={"a": "alpha", "b": 42})
    d = describe_template("p")
    examples = {s["name"]: s["example"] for s in d["slots"]}
    assert examples == {"a": "alpha", "b": 42}


def test_describe_composite_with_mixed_slot_kinds():
    """Mirror the §15 example shape: required STRING + optional ACTION."""
    def fn(*, sm_name: str, morning_action: Optional[Callable] = None):
        """SM that dispatches AM/PM by wall clock."""
    define_template("p", fn, kind="composite", engine="chain_tree",
                    slot_examples={"sm_name": "time_of_day_sm"})
    d = describe_template("p")
    assert d["kind"] == "composite"
    assert d["engine"] == "chain_tree"
    by_name = {s["name"]: s for s in d["slots"]}
    assert by_name["sm_name"]["required"] is True
    assert by_name["sm_name"]["kind"] == "STRING"
    assert by_name["morning_action"]["required"] is False
    assert by_name["morning_action"]["nullable"] is True
    assert by_name["morning_action"]["kind"] == "ACTION"
    assert by_name["sm_name"]["example"] == "time_of_day_sm"


# ---- list_template ---------------------------------------------------

def _seed():
    def leaf_ct(*, msg: str = "hi"): pass
    def comp_ct(*, action: Callable): pass
    def leaf_se(*, n: int = 0): pass
    def sol_ct(*, x: str = "x"): pass

    define_template("leaves.chain_tree.print", leaf_ct,
                    kind="leaf", engine="chain_tree", describe="ct leaf")
    define_template("composites.chain_tree.runner", comp_ct,
                    kind="composite", engine="chain_tree", describe="ct comp")
    define_template("leaves.s_engine.print", leaf_se,
                    kind="leaf", engine="s_engine", describe="se leaf")
    define_template("solutions.chain_tree.demo", sol_ct,
                    kind="solution", engine="chain_tree", describe="ct sol")


def test_list_returns_all_no_predicates():
    _seed()
    paths = [m["path"] for m in list_template()]
    assert paths == [
        "composites.chain_tree.runner",
        "leaves.chain_tree.print",
        "leaves.s_engine.print",
        "solutions.chain_tree.demo",
    ]


def test_list_short_form_shape():
    _seed()
    m = list_template(path_under="leaves.chain_tree")[0]
    assert m == {
        "path": "leaves.chain_tree.print",
        "kind": "leaf",
        "engine": "chain_tree",
        "describe": "ct leaf",
        "slot_count": 1,
    }


def test_list_filter_kind():
    _seed()
    paths = [m["path"] for m in list_template(kind="leaf")]
    assert paths == ["leaves.chain_tree.print", "leaves.s_engine.print"]


def test_list_filter_engine():
    _seed()
    paths = [m["path"] for m in list_template(engine="s_engine")]
    assert paths == ["leaves.s_engine.print"]


def test_list_filter_path_under_strict_prefix():
    """path_under matches the prefix itself and immediate descendants;
    not 'composite' as a prefix of 'composites'."""
    _seed()
    # path_under="composites" should NOT match "composites.chain_tree.runner"
    # under the prefix matching of "composites" (it should — same first dot
    # boundary). Verify exact-match + prefix-with-dot semantics:
    paths = [m["path"] for m in list_template(path_under="composites")]
    assert paths == ["composites.chain_tree.runner"]
    # but path_under="composit" should NOT match composites.* because the
    # next char is 'e', not '.'.
    paths_partial = [m["path"] for m in list_template(path_under="composit")]
    assert paths_partial == []


def test_list_filter_name_like_glob():
    _seed()
    paths = [m["path"] for m in list_template(name_like="leaves.%.print")]
    assert paths == ["leaves.chain_tree.print", "leaves.s_engine.print"]


def test_list_filter_slot_kinds_include():
    _seed()
    paths = [m["path"] for m in list_template(slot_kinds_include=Kind.ACTION)]
    assert paths == ["composites.chain_tree.runner"]


def test_list_filter_slot_kinds_include_string():
    _seed()
    paths = [m["path"] for m in list_template(slot_kinds_include="ACTION")]
    assert paths == ["composites.chain_tree.runner"]


def test_list_filter_slot_kinds_include_iterable():
    _seed()
    paths = [m["path"] for m in list_template(
        slot_kinds_include=[Kind.STRING, Kind.INT])]
    # All four templates have a STRING or INT slot.
    assert set(paths) == {
        "composites.chain_tree.runner",  # no — only ACTION slot
        "leaves.chain_tree.print",
        "leaves.s_engine.print",
        "solutions.chain_tree.demo",
    } - {"composites.chain_tree.runner"}


def test_list_combined_predicates():
    _seed()
    paths = [m["path"] for m in list_template(
        kind="leaf", engine="chain_tree")]
    assert paths == ["leaves.chain_tree.print"]


def test_list_unknown_predicate_raises():
    _seed()
    with pytest.raises(ValueError) as exc:
        list_template(bogus=True)
    assert "bogus" in str(exc.value)


def test_list_empty_registry():
    assert list_template() == []
