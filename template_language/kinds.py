"""kinds.py — slot-kind vocabulary and annotation mapping.

The `Kind` enum is the fixed slot-kind vocabulary from `template_design.txt` §5.2.
`annotation_to_kind` maps a Python type annotation (or `inspect.Parameter.empty`)
to a `(Kind, nullable)` pair. `validate_value_against_kind` checks a runtime
value against a kind.

Engine-fn kinds (ENGINE_MAIN, ENGINE_BOOLEAN, ENGINE_*) and ACTION are all
"is callable" at the value level — the signature contract is documentation,
not enforcement (Python's `inspect.signature` is unreliable on lambdas /
partials). RECREF is an instance check against the recorder's RecRef class.
DICT, LIST, BOOL, INT, FLOAT, STRING are normal isinstance checks. ANY
passes everything.
"""

from __future__ import annotations

import enum
import inspect
import types
import typing
from typing import Any, Callable, Optional


class Kind(str, enum.Enum):
    STRING = "STRING"
    INT = "INT"
    FLOAT = "FLOAT"
    BOOL = "BOOL"
    DICT = "DICT"
    LIST = "LIST"
    RECREF = "RECREF"
    ACTION = "ACTION"
    ENGINE_MAIN = "ENGINE_MAIN"
    ENGINE_BOOLEAN = "ENGINE_BOOLEAN"
    ENGINE_ONE_SHOT = "ENGINE_ONE_SHOT"
    ENGINE_SE_MAIN = "ENGINE_SE_MAIN"
    ENGINE_SE_PRED = "ENGINE_SE_PRED"
    ENGINE_SE_ONE_SHOT = "ENGINE_SE_ONE_SHOT"
    ENGINE_SE_IO_ONE_SHOT = "ENGINE_SE_IO_ONE_SHOT"
    ANY = "ANY"


_CALLABLE_KINDS = frozenset({
    Kind.ACTION,
    Kind.ENGINE_MAIN,
    Kind.ENGINE_BOOLEAN,
    Kind.ENGINE_ONE_SHOT,
    Kind.ENGINE_SE_MAIN,
    Kind.ENGINE_SE_PRED,
    Kind.ENGINE_SE_ONE_SHOT,
    Kind.ENGINE_SE_IO_ONE_SHOT,
})


_BARE_TYPE_TO_KIND = {
    str: Kind.STRING,
    int: Kind.INT,
    float: Kind.FLOAT,
    bool: Kind.BOOL,
    dict: Kind.DICT,
    list: Kind.LIST,
}


def _strip_optional(annotation):
    """Return (inner, nullable). Recognizes Optional[X] and X | None."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == len(args):
            return annotation, False
        if len(non_none) == 1:
            return non_none[0], True
        return annotation, True
    return annotation, False


def annotation_to_kind(annotation) -> tuple[Optional[Kind], bool]:
    """Map a Python annotation to (Kind, nullable).

    Returns (None, False) if the annotation cannot be mapped. The caller
    decides whether to raise `unknown_slot_kind` or fall back to ANY.

    Missing annotation (`inspect.Parameter.empty`) → (Kind.ANY, False).
    Bare `Kind` enum value (e.g. `Kind.RECREF`) → (Kind.RECREF, False).
    `Optional[X]` / `X | None` → strip Optional, recurse, nullable=True.
    """
    if annotation is inspect.Parameter.empty:
        return Kind.ANY, False

    if isinstance(annotation, Kind):
        return annotation, False

    inner, nullable = _strip_optional(annotation)

    if isinstance(inner, Kind):
        return inner, nullable

    if inner in _BARE_TYPE_TO_KIND:
        return _BARE_TYPE_TO_KIND[inner], nullable

    if inner is Callable or typing.get_origin(inner) is collections_abc_Callable():
        return Kind.ACTION, nullable

    origin = typing.get_origin(inner)
    if origin in _BARE_TYPE_TO_KIND:
        return _BARE_TYPE_TO_KIND[origin], nullable

    if inner is typing.Any:
        return Kind.ANY, nullable

    return None, nullable


def collections_abc_Callable():
    import collections.abc
    return collections.abc.Callable


def validate_value_against_kind(value: Any, kind: Kind, nullable: bool, recref_cls: type) -> bool:
    """True if value satisfies (kind, nullable). recref_cls is passed in to
    avoid a circular import with recorder.py."""
    if value is None:
        return nullable
    if kind is Kind.ANY:
        return True
    if kind is Kind.STRING:
        return isinstance(value, str)
    if kind is Kind.INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind is Kind.FLOAT:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind is Kind.BOOL:
        return isinstance(value, bool)
    if kind is Kind.DICT:
        return isinstance(value, dict)
    if kind is Kind.LIST:
        return isinstance(value, list)
    if kind is Kind.RECREF:
        return isinstance(value, recref_cls)
    if kind in _CALLABLE_KINDS:
        return callable(value)
    return False
