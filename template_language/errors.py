"""errors.py — TemplateError and the 21-code catalog.

One exception class for the entire template engine; consumers switch on
`code`. `to_dict()` is the form returned to LLM loops by `validate_solution`
and is what tests assert against. The exception itself carries the stack
trace for human use. See `template_design.txt` §10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class Stage:
    REGISTRATION = "registration"
    EXPANSION = "expansion"
    REPLAY = "replay"


class Codes:
    # Registration (raised by define_template)
    BAD_SIGNATURE_POSITIONAL_PARAM = "bad_signature_positional_param"
    BAD_SIGNATURE_VAR_ARGS = "bad_signature_var_args"
    UNKNOWN_SLOT_KIND = "unknown_slot_kind"
    DEFAULT_KIND_MISMATCH = "default_kind_mismatch"
    UNKNOWN_ENGINE = "unknown_engine"
    UNKNOWN_KIND = "unknown_kind"
    DUPLICATE_PATH = "duplicate_path"

    # Expansion (raised by use_template / Recorder)
    UNKNOWN_TEMPLATE = "unknown_template"
    UNKNOWN_SLOT = "unknown_slot"
    MISSING_REQUIRED_SLOT = "missing_required_slot"
    SLOT_KIND_MISMATCH = "slot_kind_mismatch"
    SLOT_NULL_NOT_ALLOWED = "slot_null_not_allowed"
    CROSS_ENGINE_COMPOSITION = "cross_engine_composition"
    UNKNOWN_RECORDER_METHOD = "unknown_recorder_method"
    RECORDER_STACK_IMBALANCE = "recorder_stack_imbalance"
    DUPLICATE_NAME_IN_RECORDING = "duplicate_name_in_recording"
    CT_USED_OUTSIDE_TEMPLATE = "ct_used_outside_template"

    # Replay (raised by generate_code)
    REPLAY_OP_FAILED = "replay_op_failed"
    UNRESOLVED_RECREF = "unresolved_recref"
    ENGINE_DISPATCH_FAILED = "engine_dispatch_failed"


ALL_CODES = frozenset(
    v for k, v in Codes.__dict__.items() if not k.startswith("_") and isinstance(v, str)
)
# Spec §10 prose says "21 codes" but enumerates 7 + 10 + 3 = 20. Tracked
# in continue.md for next-session reconciliation.
assert len(ALL_CODES) == 20, f"Codes catalog must have 20 entries, got {len(ALL_CODES)}"


_REGISTRATION_CODES = frozenset({
    Codes.BAD_SIGNATURE_POSITIONAL_PARAM,
    Codes.BAD_SIGNATURE_VAR_ARGS,
    Codes.UNKNOWN_SLOT_KIND,
    Codes.DEFAULT_KIND_MISMATCH,
    Codes.UNKNOWN_ENGINE,
    Codes.UNKNOWN_KIND,
    Codes.DUPLICATE_PATH,
})

_EXPANSION_CODES = frozenset({
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
})

_REPLAY_CODES = frozenset({
    Codes.REPLAY_OP_FAILED,
    Codes.UNRESOLVED_RECREF,
    Codes.ENGINE_DISPATCH_FAILED,
})


def _stage_for_code(code: str) -> str:
    if code in _REGISTRATION_CODES:
        return Stage.REGISTRATION
    if code in _EXPANSION_CODES:
        return Stage.EXPANSION
    if code in _REPLAY_CODES:
        return Stage.REPLAY
    raise ValueError(f"unknown TemplateError code: {code!r}")


class TemplateError(Exception):
    """The single exception class for the template engine."""

    def __init__(
        self,
        code: str,
        *,
        stage: str | None = None,
        template_stack: list[str] | None = None,
        details: dict | None = None,
    ):
        if stage is None:
            stage = _stage_for_code(code)
        self.code = code
        self.stage = stage
        self.template_stack = list(template_stack) if template_stack else []
        self.details = dict(details) if details else {}
        super().__init__(self._render_message())

    def _render_message(self) -> str:
        parts = [f"[{self.stage}:{self.code}]"]
        if self.template_stack:
            parts.append(f"in {'/'.join(self.template_stack)}")
        if self.details:
            parts.append(repr(self.details))
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "template_stack": list(self.template_stack),
            "details": dict(self.details),
        }
