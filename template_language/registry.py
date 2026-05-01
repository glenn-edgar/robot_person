"""registry.py — in-process template registry.

`define_template(path, fn, *, kind, engine, describe=None, slot_examples=None)`
introspects `fn`'s signature, builds a slot schema via `kinds.py`, validates
the function shape and the registration metadata, and stores the entry under
`path`. The registry itself is a module-level dict — DB-backed storage lands
in Phase F.

See `template_design.txt` §5.5, §10.1, §12.1.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .errors import Codes, Stage, TemplateError
from .kinds import Kind, annotation_to_kind, validate_value_against_kind
from .recorder import RecRef


VALID_ENGINES = frozenset({"chain_tree", "s_engine"})
VALID_KINDS = frozenset({"composite", "leaf", "solution"})


@dataclass
class Slot:
    name: str
    required: bool
    kind: Kind
    nullable: bool
    default: Any
    annotation: Any
    example: Any = None


@dataclass
class RegisteredTemplate:
    path: str
    fn: Callable
    kind: str
    engine: str
    describe: str
    slots: list[Slot]
    slot_examples: dict


_registry: dict[str, RegisteredTemplate] = {}


def define_template(
    path: str,
    fn: Callable,
    *,
    kind: str,
    engine: str,
    describe: Optional[str] = None,
    slot_examples: Optional[dict] = None,
) -> RegisteredTemplate:
    """Register `fn` at `path`. Validates and stores; raises TemplateError
    on any registration-stage problem."""
    if engine not in VALID_ENGINES:
        raise TemplateError(
            Codes.UNKNOWN_ENGINE,
            details={"engine": engine, "valid": sorted(VALID_ENGINES)},
        )
    if kind not in VALID_KINDS:
        raise TemplateError(
            Codes.UNKNOWN_KIND,
            details={"kind": kind, "valid": sorted(VALID_KINDS)},
        )
    if path in _registry:
        raise TemplateError(
            Codes.DUPLICATE_PATH,
            details={"path": path},
        )

    slots = _build_slot_schema(fn)

    # Default-vs-kind compatibility: defaults must satisfy their kind.
    for slot in slots:
        if not slot.required:
            ok = validate_value_against_kind(slot.default, slot.kind, slot.nullable, RecRef)
            if not ok:
                raise TemplateError(
                    Codes.DEFAULT_KIND_MISMATCH,
                    details={"slot": slot.name, "kind": slot.kind.value,
                             "nullable": slot.nullable,
                             "default_type": type(slot.default).__name__},
                )

    examples = dict(slot_examples) if slot_examples else {}
    for slot in slots:
        if slot.name in examples:
            slot.example = examples[slot.name]

    entry = RegisteredTemplate(
        path=path,
        fn=fn,
        kind=kind,
        engine=engine,
        describe=(describe or fn.__doc__ or "").strip(),
        slots=slots,
        slot_examples=examples,
    )
    _registry[path] = entry
    return entry


def _build_slot_schema(fn: Callable) -> list[Slot]:
    """Inspect `fn`'s signature; raise TemplateError on any signature
    constraint violation; return a list of Slots.

    `eval_str=True` resolves PEP 563 lazy annotations (modules using
    `from __future__ import annotations`)."""
    try:
        sig = inspect.signature(fn, eval_str=True)
    except (NameError, TypeError):
        # Fall back to unevaluated if eval fails (e.g. forward refs to
        # symbols not yet defined). Authors get unknown_slot_kind on the
        # affected slot, which is the right error.
        sig = inspect.signature(fn)
    out: list[Slot] = []

    for name, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            raise TemplateError(
                Codes.BAD_SIGNATURE_VAR_ARGS,
                details={"param": name, "form": "*args"},
            )
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            raise TemplateError(
                Codes.BAD_SIGNATURE_VAR_ARGS,
                details={"param": name, "form": "**kwargs"},
            )
        if param.kind is not inspect.Parameter.KEYWORD_ONLY:
            raise TemplateError(
                Codes.BAD_SIGNATURE_POSITIONAL_PARAM,
                details={"param": name, "form": str(param.kind)},
            )

        kind, nullable = annotation_to_kind(param.annotation)
        if kind is None:
            raise TemplateError(
                Codes.UNKNOWN_SLOT_KIND,
                details={"slot": name, "annotation": repr(param.annotation)},
            )

        required = param.default is inspect.Parameter.empty
        default = None if required else param.default

        out.append(Slot(
            name=name,
            required=required,
            kind=kind,
            nullable=nullable,
            default=default,
            annotation=param.annotation if param.annotation is not inspect.Parameter.empty else None,
        ))

    return out


_LAZY_PACKAGE = "template_language.templates"


def get_template(path: str) -> RegisteredTemplate:
    """Look up a registered template; lazy-import on miss.

    Convention: a template registered at ltree path `composites.X.foo`
    lives in `template_language/templates/composites/X/foo.py`. If the
    path isn't in the registry, attempt that import; the module's
    top-level `define_template(...)` populates the registry as a side
    effect. Recheck and return, or raise UNKNOWN_TEMPLATE.

    Authors who deviate from the file-mirrors-path convention are
    responsible for explicitly importing their module before any
    `use_template` call.
    """
    if path in _registry:
        return _registry[path]

    import sys
    module_name = f"{_LAZY_PACKAGE}.{path}"
    # If the module is already in sys.modules but the path isn't in the
    # registry, the registry was cleared after a previous import. Evict
    # and re-import so the module's top-level define_template runs again.
    if module_name in sys.modules:
        del sys.modules[module_name]
    try:
        importlib.import_module(module_name)
    except ImportError:
        pass

    if path in _registry:
        return _registry[path]

    raise TemplateError(
        Codes.UNKNOWN_TEMPLATE,
        details={"path": path, "tried_module": module_name},
    )


def load_all() -> int:
    """Walk `template_language.templates` and import every leaf module.
    Each import runs the module's `define_template(...)` call as a side
    effect, populating the registry. Returns the count of modules that
    were *newly* loaded by this call (modules already in sys.modules
    are not double-counted).

    Used by demos, tests, and any "show me everything" flow. Not
    required for normal `use_template` lookup — the lazy fallback in
    `get_template` handles single-template imports on demand.
    """
    import sys

    pkg = importlib.import_module(_LAZY_PACKAGE)
    before = set(sys.modules)
    for _, modname, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        if not ispkg:
            importlib.import_module(modname)
    after = set(sys.modules)
    return len(after - before)


def has_template(path: str) -> bool:
    return path in _registry


def clear_registry() -> None:
    """Test-only — wipe the registry between tests."""
    _registry.clear()


def list_paths() -> list[str]:
    return sorted(_registry.keys())


# ----------------------------------------------------------------------
# describe_template — full schema for one template (LLM-consumable).
# Shape per template_design.txt §15.
# ----------------------------------------------------------------------


def describe_template(path: str) -> dict:
    """Return the full JSON-shaped schema for the template at `path`.

    Raises `unknown_template` if not registered. The shape:
        {
          "path": str, "kind": str, "engine": str, "describe": str,
          "slots": [
            {"name", "required", "kind", "nullable", "default",
             "annotation", "example"},
            ...
          ]
        }
    """
    rt = get_template(path)
    return {
        "path": rt.path,
        "kind": rt.kind,
        "engine": rt.engine,
        "describe": rt.describe,
        "slots": [_slot_to_dict(s) for s in rt.slots],
    }


def _slot_to_dict(slot: Slot) -> dict:
    return {
        "name": slot.name,
        "required": slot.required,
        "kind": slot.kind.value,
        "nullable": slot.nullable,
        "default": slot.default,
        "annotation": _annotation_repr(slot.annotation),
        "example": slot.example,
    }


def _annotation_repr(annotation) -> Optional[str]:
    if annotation is None:
        return None
    if isinstance(annotation, type):
        return annotation.__name__
    return repr(annotation)


# ----------------------------------------------------------------------
# list_template — predicate-driven registry query.
# Predicates per template_design.txt §12.4.
# ----------------------------------------------------------------------


def list_template(**predicates) -> list[dict]:
    """Return short-form metadata for every registered template that
    matches ALL supplied predicates. Unknown predicate keys raise ValueError
    (fail-fast — LLMs need a specific error to self-correct).

    Predicates:
      kind=                 exact match against rt.kind
      engine=               exact match against rt.engine
      path_under=           ltree prefix; matches `rt.path == prefix`
                            or `rt.path.startswith(prefix + ".")`
      name_like=            SQL-LIKE glob: `_` = one char, `%` = many
      slot_kinds_include=   any of the named kinds appears in the
                            template's slot schema. Accepts a Kind, a
                            Kind value-string, or an iterable of either.

    Returns one dict per match: {path, kind, engine, describe, slot_count}.
    Sorted by path.
    """
    valid = {"kind", "engine", "path_under", "name_like", "slot_kinds_include"}
    unknown = set(predicates) - valid
    if unknown:
        raise ValueError(f"list_template: unknown predicates {sorted(unknown)}; "
                         f"valid keys are {sorted(valid)}")

    matches: list[dict] = []
    for path in sorted(_registry):
        rt = _registry[path]
        if not _matches(rt, predicates):
            continue
        matches.append({
            "path": rt.path,
            "kind": rt.kind,
            "engine": rt.engine,
            "describe": rt.describe,
            "slot_count": len(rt.slots),
        })
    return matches


def _matches(rt: RegisteredTemplate, predicates: dict) -> bool:
    if "kind" in predicates and rt.kind != predicates["kind"]:
        return False
    if "engine" in predicates and rt.engine != predicates["engine"]:
        return False
    if "path_under" in predicates:
        prefix = predicates["path_under"]
        if rt.path != prefix and not rt.path.startswith(prefix + "."):
            return False
    if "name_like" in predicates:
        if not _sql_like(rt.path, predicates["name_like"]):
            return False
    if "slot_kinds_include" in predicates:
        wanted = _normalize_kinds(predicates["slot_kinds_include"])
        if not any(s.kind in wanted for s in rt.slots):
            return False
    return True


def _sql_like(value: str, pattern: str) -> bool:
    """Minimal SQL LIKE matcher: `_` matches one char, `%` matches any."""
    import re
    rx = "^"
    for ch in pattern:
        if ch == "%":
            rx += ".*"
        elif ch == "_":
            rx += "."
        else:
            rx += re.escape(ch)
    rx += "$"
    return re.match(rx, value) is not None


def _normalize_kinds(arg) -> set[Kind]:
    if isinstance(arg, Kind):
        return {arg}
    if isinstance(arg, str):
        return {Kind(arg)}
    out: set[Kind] = set()
    for x in arg:
        if isinstance(x, Kind):
            out.add(x)
        elif isinstance(x, str):
            out.add(Kind(x))
        else:
            raise ValueError(f"slot_kinds_include: unrecognized {x!r}")
    return out
