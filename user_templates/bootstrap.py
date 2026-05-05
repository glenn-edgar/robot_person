"""user_templates.bootstrap — explicit registration entry point.

Call `bootstrap()` once per session before any `use_template(...)`
call against a `user.*` path. Idempotent within a session via the
registry's hard-error rule: if the prefix is already registered with
the same package, the second call is a no-op; a mismatched
re-registration raises ValueError.

Kept as an explicit function (not a side-effect on import of
`user_templates`) so test harnesses that reset registry state between
runs can re-bootstrap deterministically.
"""

from __future__ import annotations

from template_language import list_template_roots, register_template_root

PACKAGE = "user_templates.templates"
PREFIX = "user"


def bootstrap() -> None:
    """Register the user_templates root if not already present."""
    for r in list_template_roots():
        if r["prefix"] == PREFIX:
            if r["package"] == PACKAGE:
                return
            raise ValueError(
                f"user_templates.bootstrap: prefix {PREFIX!r} already "
                f"registered with package {r['package']!r}"
            )
    register_template_root(PACKAGE, prefix=PREFIX)
