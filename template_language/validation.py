"""validation.py — `validate_solution`, the LLM closed-loop verb.

Runs phase 1 + phase 2 in dry-run mode. On success returns
`{"ok": True}`. On the first `TemplateError` returns its `to_dict()`.

The "dry-run" of phase 2 is just `generate_code` without `chain.run()`;
the engine builder is constructed and ops are dispatched so engine-arg
errors surface, but no main loop runs. This is enough for the LLM to
detect a malformed solution and self-correct.

See `template_design.txt` §12.6, §15 (closed loop).
"""

from __future__ import annotations

from typing import Any

from .errors import TemplateError
from .expansion import use_template
from .replay import generate_code


def validate_solution(path: str, **slots) -> dict[str, Any]:
    """Phase 1 + phase 2 dry-run. Returns either:
        {"ok": True}
    or the first error's to_dict() shape:
        {"ok": False, "stage": ..., "code": ..., "details": ...,
         "template_stack": [...]}
    """
    try:
        op_list = use_template(path, **slots)
    except TemplateError as e:
        return {"ok": False, **e.to_dict()}

    try:
        generate_code(op_list)
    except TemplateError as e:
        return {"ok": False, **e.to_dict()}

    return {"ok": True}
