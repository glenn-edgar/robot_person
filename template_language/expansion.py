"""expansion.py — `use_template`, the phase-1 entry point.

Look up the registered template, validate caller-supplied slots against
the schema, push a Recorder, run the body, pop, finalize. Outermost call
returns the OpList; nested call returns None and splices its ops into the
parent's recorder.

See `template_design.txt` §7 (templates calling templates), §10.2
(expansion error codes), §12.2.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import Codes, TemplateError
from .kinds import validate_value_against_kind
from .recorder import (
    OpList,
    RecRef,
    Recorder,
    _active,
    _pop_recorder,
    _push_recorder,
    _recorder_stack,
    _template_stack_snapshot,
    chain_tree_methods,
)
from .registry import RegisteredTemplate, get_template


def _engine_methods(engine: str) -> set[str]:
    if engine == "chain_tree":
        return chain_tree_methods()
    if engine == "s_engine":
        from .recorder import s_engine_methods
        return s_engine_methods()
    raise TemplateError(
        Codes.UNKNOWN_ENGINE,
        details={"engine": engine, "context": "expansion"},
    )


def _validate_slots(rt: RegisteredTemplate, supplied: dict) -> dict:
    """Validate caller-supplied slots against the template's schema.
    Returns a fully-populated kwargs dict (defaults filled in)."""
    schema_by_name = {s.name: s for s in rt.slots}
    schema_names = set(schema_by_name)
    supplied_names = set(supplied)

    unknown = supplied_names - schema_names
    if unknown:
        raise TemplateError(
            Codes.UNKNOWN_SLOT,
            template_stack=_template_stack_snapshot() + [rt.path],
            details={"path": rt.path, "unknown": sorted(unknown),
                     "valid": sorted(schema_names)},
        )

    final: dict = {}
    for slot in rt.slots:
        if slot.name in supplied:
            value = supplied[slot.name]
        elif slot.required:
            raise TemplateError(
                Codes.MISSING_REQUIRED_SLOT,
                template_stack=_template_stack_snapshot() + [rt.path],
                details={"path": rt.path, "slot": slot.name,
                         "kind": slot.kind.value},
            )
        else:
            value = slot.default

        # null check
        if value is None and not slot.nullable:
            raise TemplateError(
                Codes.SLOT_NULL_NOT_ALLOWED,
                template_stack=_template_stack_snapshot() + [rt.path],
                details={"path": rt.path, "slot": slot.name,
                         "kind": slot.kind.value},
            )

        if not validate_value_against_kind(value, slot.kind, slot.nullable, RecRef):
            raise TemplateError(
                Codes.SLOT_KIND_MISMATCH,
                template_stack=_template_stack_snapshot() + [rt.path],
                details={"path": rt.path, "slot": slot.name,
                         "expected_kind": slot.kind.value,
                         "nullable": slot.nullable,
                         "got_type": type(value).__name__},
            )
        final[slot.name] = value

    return final


def use_template(path: str, **slots) -> Optional[OpList]:
    """Phase 1. Look up `path`, validate slots, run the body against a
    fresh Recorder, return the OpList (outermost) or None (nested)."""
    rt = get_template(path)

    # Cross-engine check before slot validation so the error points at the
    # composition rather than at a slot mismatch in the wrong engine.
    active = _active()
    if active is not None and active.engine != rt.engine:
        raise TemplateError(
            Codes.CROSS_ENGINE_COMPOSITION,
            template_stack=_template_stack_snapshot() + [rt.path],
            details={"path": rt.path,
                     "inner_engine": rt.engine,
                     "active_engine": active.engine},
        )

    final_kwargs = _validate_slots(rt, slots)

    recorder = Recorder(
        engine=rt.engine,
        template_path=rt.path,
        valid_methods=_engine_methods(rt.engine),
    )
    nested = active is not None
    _push_recorder(recorder)
    try:
        body_return = rt.fn(**final_kwargs)
        recorder.finalize()
    finally:
        _pop_recorder(recorder)
    if isinstance(body_return, RecRef):
        recorder.op_list.body_return = body_return

    if nested:
        # Splice into the parent's op-list; merge global names so cross-
        # template duplicates are caught at the parent's recording level.
        parent = _active()
        # parent is non-None here: we entered nested with an active recorder.
        parent.merge_global_names(recorder)
        parent.append_ops(recorder.op_list.ops)
        # s_engine pattern: the inner body returns its tree root as a
        # RecRef; the parent passes that RecRef into its own dsl call as
        # an arg. chain_tree pattern: bodies return None; this returns
        # None too.
        return recorder.op_list.body_return

    return recorder.op_list
