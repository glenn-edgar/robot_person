"""recorder.py — phase-1 machinery.

The Recorder shadows an engine builder's public method surface. Each
`ct.method(...)` call inside a template body is appended to the active
recorder's op-list. The recorder also tracks frame discipline (define_/
start_ ↔ end_) and per-namespace name uniqueness, raising `TemplateError`
immediately at the offending call.

The recorder stack is a plain module-level list (not a contextvar) — see
`template_design.txt` §3 for the single-context rationale.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .errors import Codes, Stage, TemplateError


@dataclass
class Op:
    method: str
    args: tuple
    kwargs: dict
    source: list[str] = field(default_factory=list)
    # The RecRef returned by the recorder shim for this op. Phase 2 maps
    # `id(out_ref) → real_return_value` so later ops referencing this
    # RecRef in their args/kwargs get substituted.
    out_ref: Optional["RecRef"] = None


_recref_counter = itertools.count(1)


class RecRef:
    """Opaque sentinel returned by recorder methods. Phase 2 maps RecRef
    instances to the real engine refs the builder produces.

    `kind` is a free-form tag (typically the recorder method that produced
    the ref, e.g. "define_state_machine"); used only for debug repr.
    """

    __slots__ = ("_id", "_kind")

    def __init__(self, kind: str):
        self._id = next(_recref_counter)
        self._kind = kind

    def __repr__(self) -> str:
        return f"RecRef(#{self._id}, {self._kind})"

    def __eq__(self, other) -> bool:
        return isinstance(other, RecRef) and other._id == self._id

    def __hash__(self) -> int:
        return hash(self._id)


@dataclass
class OpList:
    engine: str
    ops: list[Op] = field(default_factory=list)


# ----------------------------------------------------------------------
# Method metadata per engine.
# ----------------------------------------------------------------------
#
# `_FRAME_OPENERS[method] = frame_kind` — calling pushes a frame; the
#                                          frame_kind must match the suffix
#                                          consumed by the corresponding closer.
# `_FRAME_CLOSERS[method] = frame_kind` — calling pops a frame; raises
#                                          recorder_stack_imbalance if the top
#                                          frame's kind doesn't match.
# `_NAME_NAMESPACE[method] = (namespace, scope, arg_index)` —
#     namespace ∈ {"engine_fn","kb","sm","state","column"}
#     scope ∈ {"global","per_sm","per_frame"}
#     arg_index — positional index of the name in the method's signature
#                 (resolved against args first, then kwargs by parameter name).
# `_NAME_KW[method] = kwarg_name` — fallback for kwarg lookup.

# Frame openers/closers — stack discipline. The frame_kind is shared by
# the opener and closer (so define_state_machine ↔ end_state_machine match).
_FRAME_OPENERS: dict[str, str] = {
    "start_test": "test",
    "define_column": "column",
    "define_state_machine": "state_machine",
    "define_state": "state",
    "define_se_tick": "se_tick",
    "define_sequence_til_pass": "seq_pass",
    "define_sequence_til_fail": "seq_fail",
    "define_supervisor": "supervisor",
    "define_supervisor_one_for_one": "supervisor",
    "define_supervisor_one_for_all": "supervisor",
    "define_supervisor_rest_for_all": "supervisor",
    "define_exception_handler": "exception_handler",
    "define_main_column": "main_column",
    "define_recovery_column": "recovery_column",
    "define_finalize_column": "finalize_column",
    "define_controlled_server": "controlled_server",
}

_FRAME_CLOSERS: dict[str, str] = {
    "end_test": "test",
    "end_column": "column",
    "end_state_machine": "state_machine",
    "end_state": "state",
    "end_se_tick": "se_tick",
    "end_sequence_til_pass": "seq_pass",
    "end_sequence_til_fail": "seq_fail",
    "end_supervisor": "supervisor",
    "end_exception_handler": "exception_handler",
    "end_main_column": "main_column",
    "end_recovery_column": "recovery_column",
    "end_finalize_column": "finalize_column",
    "end_controlled_server": "controlled_server",
}

# Per-namespace name tracking — see template_design.txt §9.
# (namespace, scope, arg_index, kw_name)
_NAME_NAMESPACE: dict[str, tuple[str, str, int, str]] = {
    "add_main":              ("engine_fn", "global", 0, "name"),
    "add_boolean":           ("engine_fn", "global", 0, "name"),
    "add_one_shot":          ("engine_fn", "global", 0, "name"),
    "add_se_main":           ("engine_fn", "global", 0, "name"),
    "add_se_pred":           ("engine_fn", "global", 0, "name"),
    "add_se_one_shot":       ("engine_fn", "global", 0, "name"),
    "add_se_io_one_shot":    ("engine_fn", "global", 0, "name"),
    "start_test":            ("kb",        "global", 0, "name"),
    "define_state_machine":  ("sm",        "global", 0, "name"),
    "define_state":          ("state",     "per_sm", 0, "state_name"),
    "define_column":         ("column",    "per_frame", 0, "name"),
}


# ----------------------------------------------------------------------
# Recorder
# ----------------------------------------------------------------------

_recorder_stack: list["Recorder"] = []


def _active() -> Optional["Recorder"]:
    return _recorder_stack[-1] if _recorder_stack else None


def _push_recorder(rec: "Recorder") -> None:
    _recorder_stack.append(rec)


def _pop_recorder(rec: "Recorder") -> None:
    if not _recorder_stack or _recorder_stack[-1] is not rec:
        raise TemplateError(
            Codes.RECORDER_STACK_IMBALANCE,
            details={"reason": "module-level recorder stack mismatched on pop"},
        )
    _recorder_stack.pop()


def _template_stack_snapshot() -> list[str]:
    return [r.template_path for r in _recorder_stack]


class Recorder:
    """One Recorder per `use_template` call. Op-list collects ops; shadow
    stack tracks frame discipline; per-namespace name registries enforce
    duplicate detection.

    `engine` and `valid_methods` are supplied by the caller (the registry,
    on lookup).
    """

    def __init__(self, *, engine: str, template_path: str, valid_methods: set[str]):
        self.engine = engine
        self.template_path = template_path
        self.valid_methods = valid_methods
        self.op_list = OpList(engine=engine)
        self._frames: list[dict] = []
        self._global_names: dict[str, set[str]] = {
            "engine_fn": set(),
            "kb": set(),
            "sm": set(),
        }
        # per_frame name sets attach to whichever frame is on top at the
        # call site; we store them inside the frame dict.
        self._method_shims: dict[str, Callable] = {}

    # -- public surface ------------------------------------------------

    def __getattr__(self, name: str):
        # __getattr__ is only called if normal attribute lookup fails.
        if name.startswith("_"):
            raise AttributeError(name)
        shims = self.__dict__.get("_method_shims")
        if shims is not None and name in shims:
            return shims[name]
        if name not in self.valid_methods:
            raise TemplateError(
                Codes.UNKNOWN_RECORDER_METHOD,
                template_stack=_template_stack_snapshot(),
                details={"method": name, "engine": self.engine},
            )
        shim = self._make_shim(name)
        if shims is not None:
            shims[name] = shim
        return shim

    def finalize(self) -> OpList:
        """Called when the template body returns. Any unclosed frames are
        a recorder_stack_imbalance error."""
        if self._frames:
            kinds = [f["kind"] for f in self._frames]
            raise TemplateError(
                Codes.RECORDER_STACK_IMBALANCE,
                template_stack=_template_stack_snapshot(),
                details={"unclosed_frames": kinds, "template": self.template_path},
            )
        return self.op_list

    def append_ops(self, ops: list[Op]) -> None:
        """Splice ops from a nested recorder into this one. Used by
        use_template when the inner template returns; the inner recorder's
        op-list is appended to the parent's. Names from the inner recording
        propagate into the parent's global name registries to enforce
        cross-template uniqueness."""
        self.op_list.ops.extend(ops)

    def merge_global_names(self, other: "Recorder") -> None:
        """After splicing a nested op-list, adopt its global name claims so
        a subsequent `add_main` (etc.) in the parent can detect collisions
        with names recorded by the child. Per-frame and per-sm names are
        scoped and do not cross template boundaries."""
        for ns, names in other._global_names.items():
            existing = self._global_names[ns]
            collisions = existing & names
            if collisions:
                raise TemplateError(
                    Codes.DUPLICATE_NAME_IN_RECORDING,
                    template_stack=_template_stack_snapshot(),
                    details={
                        "namespace": ns,
                        "names": sorted(collisions),
                        "reason": "name(s) defined in nested template collide with parent",
                    },
                )
            existing |= names

    # -- internals -----------------------------------------------------

    def _make_shim(self, method_name: str) -> Callable:
        def shim(*args, **kwargs):
            ref = RecRef(method_name)
            self._record(method_name, args, kwargs, ref)
            return ref
        shim.__name__ = f"recorder_shim:{method_name}"
        return shim

    def _record(self, method: str, args: tuple, kwargs: dict,
                out_ref: "RecRef") -> None:
        # 1) frame discipline
        if method in _FRAME_OPENERS:
            self._frames.append({
                "kind": _FRAME_OPENERS[method],
                "method": method,
                "per_frame_names": {"column": set()},
            })
        elif method in _FRAME_CLOSERS:
            expected = _FRAME_CLOSERS[method]
            if not self._frames:
                raise TemplateError(
                    Codes.RECORDER_STACK_IMBALANCE,
                    template_stack=_template_stack_snapshot(),
                    details={"method": method, "expected_open": expected,
                             "reason": "close call without matching open"},
                )
            top = self._frames[-1]
            if top["kind"] != expected:
                raise TemplateError(
                    Codes.RECORDER_STACK_IMBALANCE,
                    template_stack=_template_stack_snapshot(),
                    details={"method": method, "expected_open": expected,
                             "got_open": top["kind"], "got_open_method": top["method"]},
                )
            self._frames.pop()

        # 2) name discipline (after frame discipline so per-sm/per-frame
        #    look up against the right frame; opener pushes its own frame
        #    BEFORE we record its name claim, but the name belongs to the
        #    enclosing scope — handle below by indexing from -2 when needed.)
        if method in _NAME_NAMESPACE:
            ns, scope, arg_idx, kw_name = _NAME_NAMESPACE[method]
            name = self._extract_name(method, args, kwargs, arg_idx, kw_name)
            self._claim_name(method, ns, scope, name)

        # 3) append op
        self.op_list.ops.append(Op(
            method=method,
            args=args,
            kwargs=dict(kwargs),
            source=_template_stack_snapshot(),
            out_ref=out_ref,
        ))

    def _extract_name(self, method: str, args: tuple, kwargs: dict,
                      arg_idx: int, kw_name: str) -> str:
        if len(args) > arg_idx:
            return args[arg_idx]
        if kw_name in kwargs:
            return kwargs[kw_name]
        # Fail the same way Python would have: missing positional. The real
        # builder will also raise; we just don't track a name we can't see.
        raise TemplateError(
            Codes.DUPLICATE_NAME_IN_RECORDING,
            template_stack=_template_stack_snapshot(),
            details={"method": method, "reason": f"could not extract name "
                     f"(positional[{arg_idx}] or kw {kw_name!r})"},
        )

    def _claim_name(self, method: str, ns: str, scope: str, name: str) -> None:
        if scope == "global":
            registry = self._global_names[ns]
            if name in registry:
                raise TemplateError(
                    Codes.DUPLICATE_NAME_IN_RECORDING,
                    template_stack=_template_stack_snapshot(),
                    details={"method": method, "namespace": ns, "name": name},
                )
            registry.add(name)
            return

        if scope == "per_sm":
            # define_state — find the nearest state_machine frame. Note: the
            # state_machine frame is the parent; this method has not pushed
            # its own frame yet (state's frame goes on top after). Actually
            # define_state DOES push a frame in _FRAME_OPENERS, and the push
            # already happened above. So the nearest state_machine frame is
            # at -2.
            sm_frame = None
            for fr in reversed(self._frames[:-1]):
                if fr["kind"] == "state_machine":
                    sm_frame = fr
                    break
            if sm_frame is None:
                # The real builder will reject this; our recording invariant
                # is just "no duplicate state names within an SM". If there's
                # no SM, there's no namespace to collide in — skip.
                return
            states = sm_frame.setdefault("state_names", set())
            if name in states:
                raise TemplateError(
                    Codes.DUPLICATE_NAME_IN_RECORDING,
                    template_stack=_template_stack_snapshot(),
                    details={"method": method, "namespace": ns, "name": name,
                             "scope": "state_machine"},
                )
            states.add(name)
            return

        if scope == "per_frame":
            # define_column — name unique within the immediately enclosing
            # frame (one level above the frame this call just pushed).
            if len(self._frames) < 2:
                # define_column at top level — the builder will reject.
                return
            parent_frame = self._frames[-2]
            cols = parent_frame.setdefault("per_frame_names", {}).setdefault("column", set())
            if name in cols:
                raise TemplateError(
                    Codes.DUPLICATE_NAME_IN_RECORDING,
                    template_stack=_template_stack_snapshot(),
                    details={"method": method, "namespace": ns, "name": name,
                             "scope": parent_frame["kind"]},
                )
            cols.add(name)
            return


# ----------------------------------------------------------------------
# Engine method-surface introspection.
# ----------------------------------------------------------------------

def _public_methods(cls) -> set[str]:
    import inspect
    out = set()
    for name, val in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if inspect.isfunction(val) or inspect.ismethod(val):
            out.add(name)
    return out


def chain_tree_methods() -> set[str]:
    """Lazy import + introspect ChainTree's public method surface."""
    from ct_dsl import ChainTree
    return _public_methods(ChainTree)
