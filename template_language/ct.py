"""ct.py — module-level proxy that resolves to the active recorder.

Inside a template body, authors call `ct.method(...)`. The proxy resolves
`method` against the recorder on top of the recorder stack and dispatches
the call. With no active recorder, any access raises
`ct_used_outside_template` — the proxy is exclusively for template-body
authoring; hand-authored construction uses `ChainTree(); chain.foo()`
directly.

See `template_design.txt` §3.
"""

from __future__ import annotations

from .errors import Codes, TemplateError
from .recorder import _active


class _CtProxy:
    __slots__ = ()

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        rec = _active()
        if rec is None:
            raise TemplateError(
                Codes.CT_USED_OUTSIDE_TEMPLATE,
                details={"method": name},
            )
        return getattr(rec, name)

    def __repr__(self) -> str:
        return "<template_language.ct proxy>"


ct = _CtProxy()
