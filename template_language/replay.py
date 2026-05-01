"""replay.py — `generate_code`, phase 2.

Walks the OpList against the real engine builder. Maintains a
`RecRef → real-ref` map so RecRefs that flowed through phase 1 (e.g., the
state-machine ref returned by `define_state_machine` and consumed by
`asm_change_state`) get substituted with the real builder's return value
before dispatch.

Engine-builder exceptions are wrapped in `replay_op_failed` with the
op's `template_stack` (its `source` field) preserved.

See `template_design.txt` §1, §10.3, §12.3.
"""

from __future__ import annotations

from typing import Any

from .errors import Codes, TemplateError
from .recorder import OpList, RecRef


def generate_code(op_list: OpList, **engine_kwargs) -> Any:
    """Phase 2. Replay ops against the engine's real surface; return the
    engine-native build artifact.

    chain_tree: returns the ChainTree builder (engine_kwargs forwarded
                to its constructor).
    s_engine:   returns the tree root dict (the body's return value,
                resolved through the RecRef map). engine_kwargs is
                rejected — s_engine has no per-build constructor args.

    After this returns the template engine has no further role."""
    if op_list.engine == "s_engine":
        return _replay_s_engine(op_list, engine_kwargs)
    return _replay_chain_tree(op_list, engine_kwargs)


def _replay_chain_tree(op_list: OpList, engine_kwargs: dict) -> Any:
    builder = _build_for_engine(op_list.engine, engine_kwargs)
    refs: dict[int, Any] = {}  # id(RecRef) → real ref

    for idx, op in enumerate(op_list.ops):
        try:
            args = tuple(_resolve(a, refs, op, idx) for a in op.args)
            kwargs = {k: _resolve(v, refs, op, idx) for k, v in op.kwargs.items()}
        except TemplateError:
            raise

        method = getattr(builder, op.method, None)
        if method is None:
            # Defense in depth: registry/recorder should have caught this.
            raise TemplateError(
                Codes.REPLAY_OP_FAILED,
                template_stack=list(op.source),
                details={"op_index": idx, "method": op.method,
                         "reason": "method missing on builder"},
            )

        try:
            real = method(*args, **kwargs)
        except TemplateError:
            raise
        except Exception as e:
            raise TemplateError(
                Codes.REPLAY_OP_FAILED,
                template_stack=list(op.source),
                details={
                    "op_index": idx,
                    "method": op.method,
                    "underlying": {"type": type(e).__name__, "message": str(e)},
                },
            ) from e

        # Map this op's RecRef (out_ref) to the real return so later ops
        # whose args mention the same RecRef get the real value.
        if op.out_ref is not None:
            refs[id(op.out_ref)] = real

    return builder


def _replay_s_engine(op_list: OpList, engine_kwargs: dict) -> Any:
    """s_engine replay: each op corresponds to one se_dsl function call.
    Walk ops in declaration order; arg RecRefs always reference earlier
    ops (because s_engine bodies build bottom-up). The returned tree
    root is the body's return RecRef resolved through the map."""
    if engine_kwargs:
        raise TemplateError(
            Codes.ENGINE_DISPATCH_FAILED,
            details={"engine": "s_engine",
                     "reason": "s_engine generate_code takes no kwargs",
                     "got": sorted(engine_kwargs)},
        )
    import se_dsl
    refs: dict[int, Any] = {}

    for idx, op in enumerate(op_list.ops):
        try:
            args = tuple(_resolve(a, refs, op, idx) for a in op.args)
            kwargs = {k: _resolve(v, refs, op, idx) for k, v in op.kwargs.items()}
        except TemplateError:
            raise

        fn = getattr(se_dsl, op.method, None)
        if fn is None:
            raise TemplateError(
                Codes.REPLAY_OP_FAILED,
                template_stack=list(op.source),
                details={"op_index": idx, "method": op.method,
                         "reason": "method missing on se_dsl module"},
            )
        try:
            real = fn(*args, **kwargs)
        except TemplateError:
            raise
        except Exception as e:
            raise TemplateError(
                Codes.REPLAY_OP_FAILED,
                template_stack=list(op.source),
                details={
                    "op_index": idx,
                    "method": op.method,
                    "underlying": {"type": type(e).__name__, "message": str(e)},
                },
            ) from e

        if op.out_ref is not None:
            refs[id(op.out_ref)] = real

    if op_list.body_return is None:
        # The body didn't return a RecRef. Without a designated root,
        # we can't pick one for the user. This is almost certainly an
        # author error — s_engine templates exist to construct trees.
        raise TemplateError(
            Codes.REPLAY_OP_FAILED,
            details={"engine": "s_engine",
                     "reason": "s_engine template body returned None; "
                               "expected a RecRef pointing at the tree root"},
        )
    return refs[id(op_list.body_return)]


def _build_for_engine(engine: str, kwargs: dict):
    if engine == "chain_tree":
        from ct_dsl import ChainTree
        return ChainTree(**kwargs)
    raise TemplateError(
        Codes.ENGINE_DISPATCH_FAILED,
        details={"engine": engine, "reason": "unknown engine"},
    )


def _resolve(value, refs: dict[int, Any], op, op_idx: int):
    """Walk `value`, substituting RecRefs with their real refs. Lists,
    tuples, and dicts are recursed into. Other types pass through."""
    if isinstance(value, RecRef):
        key = id(value)
        if key not in refs:
            raise TemplateError(
                Codes.UNRESOLVED_RECREF,
                template_stack=list(op.source),
                details={"op_index": op_idx, "method": op.method,
                         "recref": repr(value)},
            )
        return refs[key]
    if isinstance(value, dict):
        return {k: _resolve(v, refs, op, op_idx) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, refs, op, op_idx) for v in value]
    if isinstance(value, tuple):
        return tuple(_resolve(v, refs, op, op_idx) for v in value)
    return value
