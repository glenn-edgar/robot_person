"""Tests for kinds.py — annotation→Kind mapping and value validation."""

from __future__ import annotations

import inspect
from typing import Callable, Optional, Union

import pytest

from template_language.kinds import (
    Kind,
    annotation_to_kind,
    validate_value_against_kind,
)
from template_language.recorder import RecRef


def test_missing_annotation_is_any():
    kind, nullable = annotation_to_kind(inspect.Parameter.empty)
    assert kind is Kind.ANY
    assert nullable is False


def test_bare_types_round_trip():
    cases = [
        (str, Kind.STRING),
        (int, Kind.INT),
        (float, Kind.FLOAT),
        (bool, Kind.BOOL),
        (dict, Kind.DICT),
        (list, Kind.LIST),
    ]
    for ann, expected in cases:
        kind, nullable = annotation_to_kind(ann)
        assert kind is expected, f"{ann}"
        assert nullable is False


def test_kind_enum_passes_through():
    kind, nullable = annotation_to_kind(Kind.RECREF)
    assert kind is Kind.RECREF
    assert nullable is False


def test_optional_marks_nullable():
    kind, nullable = annotation_to_kind(Optional[str])
    assert kind is Kind.STRING
    assert nullable is True


def test_pep604_union_with_none_is_nullable():
    kind, nullable = annotation_to_kind(int | None)
    assert kind is Kind.INT
    assert nullable is True


def test_callable_maps_to_action():
    kind, nullable = annotation_to_kind(Callable)
    assert kind is Kind.ACTION
    assert nullable is False


def test_optional_callable():
    kind, nullable = annotation_to_kind(Optional[Callable])
    assert kind is Kind.ACTION
    assert nullable is True


def test_unknown_annotation_returns_none_kind():
    class Weird: pass
    kind, _ = annotation_to_kind(Weird)
    assert kind is None


def test_validate_string_value():
    assert validate_value_against_kind("hi", Kind.STRING, False, RecRef)
    assert not validate_value_against_kind(7, Kind.STRING, False, RecRef)


def test_validate_int_excludes_bool():
    assert validate_value_against_kind(7, Kind.INT, False, RecRef)
    assert not validate_value_against_kind(True, Kind.INT, False, RecRef)


def test_validate_bool():
    assert validate_value_against_kind(True, Kind.BOOL, False, RecRef)
    assert not validate_value_against_kind(1, Kind.BOOL, False, RecRef)


def test_validate_none_against_nullable():
    assert validate_value_against_kind(None, Kind.STRING, True, RecRef)
    assert not validate_value_against_kind(None, Kind.STRING, False, RecRef)


def test_validate_recref():
    r = RecRef("x")
    assert validate_value_against_kind(r, Kind.RECREF, False, RecRef)
    assert not validate_value_against_kind("not a ref", Kind.RECREF, False, RecRef)


def test_validate_action_accepts_any_callable():
    assert validate_value_against_kind(lambda: None, Kind.ACTION, False, RecRef)
    assert validate_value_against_kind(print, Kind.ACTION, False, RecRef)
    assert not validate_value_against_kind("not callable", Kind.ACTION, False, RecRef)


def test_validate_engine_main_is_callable_check():
    def fn(rt, data): return None
    assert validate_value_against_kind(fn, Kind.ENGINE_MAIN, False, RecRef)


def test_any_passes_everything():
    for v in ("s", 1, 1.5, True, [], {}, None, lambda: 0):
        # ANY non-null
        if v is None:
            continue
        assert validate_value_against_kind(v, Kind.ANY, False, RecRef)
    # ANY non-nullable still rejects None
    assert not validate_value_against_kind(None, Kind.ANY, False, RecRef)
    assert validate_value_against_kind(None, Kind.ANY, True, RecRef)
