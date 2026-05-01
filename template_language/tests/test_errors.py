"""Tests for errors.py — code catalog and TemplateError shape."""

from __future__ import annotations

import pytest

from template_language.errors import ALL_CODES, Codes, Stage, TemplateError


def test_catalog_count():
    # Spec prose says 21 but enumerates 20 (7+10+3). Aligned to enumeration.
    assert len(ALL_CODES) == 20


def test_codes_partition_by_stage():
    # All registration codes have stage=registration, etc.
    reg = {
        Codes.BAD_SIGNATURE_POSITIONAL_PARAM,
        Codes.BAD_SIGNATURE_VAR_ARGS,
        Codes.UNKNOWN_SLOT_KIND,
        Codes.DEFAULT_KIND_MISMATCH,
        Codes.UNKNOWN_ENGINE,
        Codes.UNKNOWN_KIND,
        Codes.DUPLICATE_PATH,
    }
    for c in reg:
        e = TemplateError(c)
        assert e.stage == Stage.REGISTRATION

    exp = {
        Codes.UNKNOWN_TEMPLATE,
        Codes.UNKNOWN_SLOT,
        Codes.MISSING_REQUIRED_SLOT,
        Codes.SLOT_KIND_MISMATCH,
        Codes.SLOT_NULL_NOT_ALLOWED,
        Codes.CROSS_ENGINE_COMPOSITION,
        Codes.UNKNOWN_RECORDER_METHOD,
        Codes.RECORDER_STACK_IMBALANCE,
        Codes.DUPLICATE_NAME_IN_RECORDING,
        Codes.CT_USED_OUTSIDE_TEMPLATE,
    }
    for c in exp:
        e = TemplateError(c)
        assert e.stage == Stage.EXPANSION

    rep = {
        Codes.REPLAY_OP_FAILED,
        Codes.UNRESOLVED_RECREF,
        Codes.ENGINE_DISPATCH_FAILED,
    }
    for c in rep:
        e = TemplateError(c)
        assert e.stage == Stage.REPLAY


def test_to_dict_round_trip():
    e = TemplateError(
        Codes.SLOT_KIND_MISMATCH,
        template_stack=["a.b.c", "x.y"],
        details={"slot": "body", "expected_kind": "ACTION", "got_type": "str"},
    )
    d = e.to_dict()
    assert d["code"] == Codes.SLOT_KIND_MISMATCH
    assert d["stage"] == Stage.EXPANSION
    assert d["template_stack"] == ["a.b.c", "x.y"]
    assert d["details"]["slot"] == "body"


def test_template_stack_is_copy_not_reference():
    stack = ["one"]
    e = TemplateError(Codes.UNKNOWN_TEMPLATE, template_stack=stack)
    stack.append("two")
    assert e.template_stack == ["one"]


def test_details_default_empty():
    e = TemplateError(Codes.UNKNOWN_TEMPLATE)
    assert e.details == {}
    assert e.template_stack == []


def test_unknown_code_raises():
    with pytest.raises(ValueError):
        TemplateError("not_a_real_code")


def test_explicit_stage_overrides_lookup():
    # Defense: if a caller insists, they can pass stage. Real callers don't.
    e = TemplateError(Codes.UNKNOWN_TEMPLATE, stage="custom")
    assert e.stage == "custom"
