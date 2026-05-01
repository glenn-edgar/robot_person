"""Tests for registry.py — define_template + signature/kind validation."""

from __future__ import annotations

from typing import Callable, Optional

import pytest

from template_language import (
    Codes,
    Kind,
    TemplateError,
    define_template,
    get_template,
    has_template,
)
from template_language.registry import clear_registry


@pytest.fixture(autouse=True)
def _clear():
    clear_registry()
    yield
    clear_registry()


def _ok(*, name: str, value: int = 0):
    pass


def test_register_ok_minimum():
    rt = define_template("a.b", _ok, kind="leaf", engine="chain_tree")
    assert rt.path == "a.b"
    assert rt.engine == "chain_tree"
    assert has_template("a.b")
    assert {s.name for s in rt.slots} == {"name", "value"}


def test_required_vs_optional_slots():
    def fn(*, must: str, may: int = 5): pass
    rt = define_template("p", fn, kind="leaf", engine="chain_tree")
    by_name = {s.name: s for s in rt.slots}
    assert by_name["must"].required is True
    assert by_name["must"].kind is Kind.STRING
    assert by_name["may"].required is False
    assert by_name["may"].default == 5


def test_optional_callable_nullable():
    def fn(*, action: Optional[Callable] = None): pass
    rt = define_template("p", fn, kind="leaf", engine="chain_tree")
    s = rt.slots[0]
    assert s.kind is Kind.ACTION
    assert s.nullable is True
    assert s.default is None


def test_describe_falls_back_to_docstring():
    def fn(*, x: int = 0):
        """The doc."""
    rt = define_template("p", fn, kind="leaf", engine="chain_tree")
    assert rt.describe == "The doc."


def test_describe_explicit_overrides_doc():
    def fn(*, x: int = 0):
        """Doc."""
    rt = define_template("p", fn, kind="leaf", engine="chain_tree", describe="Custom")
    assert rt.describe == "Custom"


def test_slot_examples_attached():
    def fn(*, n: str): pass
    rt = define_template("p", fn, kind="leaf", engine="chain_tree",
                         slot_examples={"n": "demo"})
    assert rt.slots[0].example == "demo"


# ---- error: bad signatures ----------------------------------------

def test_positional_param_rejected():
    def fn(name): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="chain_tree")
    assert exc.value.code == Codes.BAD_SIGNATURE_POSITIONAL_PARAM


def test_var_args_rejected():
    def fn(*args): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="chain_tree")
    assert exc.value.code == Codes.BAD_SIGNATURE_VAR_ARGS


def test_var_kwargs_rejected():
    def fn(**kwargs): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="chain_tree")
    assert exc.value.code == Codes.BAD_SIGNATURE_VAR_ARGS


def test_unknown_slot_kind():
    class Weird: pass
    def fn(*, x: Weird = None): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="chain_tree")
    assert exc.value.code == Codes.UNKNOWN_SLOT_KIND


def test_default_kind_mismatch():
    def fn(*, n: str = 7): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="chain_tree")
    assert exc.value.code == Codes.DEFAULT_KIND_MISMATCH


# ---- error: registration metadata ---------------------------------

def test_unknown_engine():
    def fn(*, x: int = 0): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="bogus")
    assert exc.value.code == Codes.UNKNOWN_ENGINE


def test_unknown_kind():
    def fn(*, x: int = 0): pass
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="bogus", engine="chain_tree")
    assert exc.value.code == Codes.UNKNOWN_KIND


def test_duplicate_path():
    def fn(*, x: int = 0): pass
    define_template("p", fn, kind="leaf", engine="chain_tree")
    with pytest.raises(TemplateError) as exc:
        define_template("p", fn, kind="leaf", engine="chain_tree")
    assert exc.value.code == Codes.DUPLICATE_PATH


# ---- get_template error -------------------------------------------

def test_get_unknown_template():
    with pytest.raises(TemplateError) as exc:
        get_template("not.registered")
    assert exc.value.code == Codes.UNKNOWN_TEMPLATE
