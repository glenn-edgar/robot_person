"""template_language — two-phase template engine over chain_tree / s_engine.

Phase A surface only: kinds, errors, recorder primitives, and the `ct`
proxy. Phase B (registry + use_template + generate_code) lands next.
See `template_design.txt`.
"""

from __future__ import annotations

from .ct import ct
from .errors import Codes, Stage, TemplateError
from .expansion import use_template
from .kinds import Kind, annotation_to_kind, validate_value_against_kind
from .recorder import Op, OpList, RecRef, Recorder
from .registry import (
    RegisteredTemplate,
    Slot,
    define_template,
    describe_template,
    get_template,
    has_template,
    list_paths,
    list_template,
    list_template_roots,
    load_all,
    register_template_root,
)
from .render import op_list_to_json, op_list_to_python
from .replay import generate_code
from .validation import validate_solution

__all__ = [
    "Codes",
    "Kind",
    "Op",
    "OpList",
    "RecRef",
    "Recorder",
    "RegisteredTemplate",
    "Slot",
    "Stage",
    "TemplateError",
    "annotation_to_kind",
    "ct",
    "define_template",
    "describe_template",
    "generate_code",
    "get_template",
    "has_template",
    "list_paths",
    "list_template",
    "list_template_roots",
    "load_all",
    "register_template_root",
    "op_list_to_json",
    "op_list_to_python",
    "use_template",
    "validate_solution",
    "validate_value_against_kind",
]
