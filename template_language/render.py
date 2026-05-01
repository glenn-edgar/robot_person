"""render.py — one-way pretty-printers over OpList.

`op_list_to_python(op_list, builder_name="chain")` renders the op-list
as the Python source you'd hand-write to construct the same artifact
against an engine builder. **Never parsed back.** Useful for DB review,
audit logs, LLM display.

`op_list_to_json(op_list)` renders the op-list as a structured dict.
RecRefs become opaque sentinels (`{"__recref__": <id>, "kind": <tag>}`),
callables become opaque markers (`{"__callable__": <name or repr>}`).
Lossy by design — also never parsed back.

See `template_design.txt` §2 (rejected text-substitution rationale; this
module is the *output*-side pretty-printer that's allowed because there
is no parse path).
"""

from __future__ import annotations

from typing import Any

from .recorder import Op, OpList, RecRef


# ----------------------------------------------------------------------
# Python-source pretty-printer
# ----------------------------------------------------------------------

def op_list_to_python(op_list: OpList, *, builder_name: str = "chain") -> str:
    """Return Python source that, if executed against a fresh builder
    bound as `builder_name`, would replay `op_list`. Never re-parsed."""
    lines: list[str] = []
    lines.append(f"# engine: {op_list.engine}")
    lines.append(f"# {len(op_list.ops)} ops")
    lines.append("")

    indent = 0
    ref_names: dict[int, str] = {}
    counters: dict[str, int] = {}

    for op in op_list.ops:
        if op.method.startswith("end_"):
            indent = max(indent - 1, 0)

        prefix = "    " * indent
        lhs = ""
        if op.out_ref is not None and _is_frame_opener(op.method):
            base = _ref_base_name(op.method)
            counters[base] = counters.get(base, 0) + 1
            n = counters[base]
            name = f"{base}_{n}" if n > 1 else base
            ref_names[id(op.out_ref)] = name
            lhs = f"{name} = "

        args_src = ", ".join(_py_arg(a, ref_names) for a in op.args)
        kwargs_src = ", ".join(
            f"{k}={_py_arg(v, ref_names)}" for k, v in op.kwargs.items()
        )
        joined = ", ".join(s for s in (args_src, kwargs_src) if s)

        lines.append(f"{prefix}{lhs}{builder_name}.{op.method}({joined})")

        if _is_frame_opener(op.method):
            indent += 1

    return "\n".join(lines) + "\n"


def _is_frame_opener(method: str) -> bool:
    return method.startswith("start_") or method.startswith("define_")


def _ref_base_name(method: str) -> str:
    if method.startswith("start_"):
        return method[len("start_"):]
    if method.startswith("define_"):
        return method[len("define_"):]
    return "ref"


def _py_arg(value: Any, ref_names: dict[int, str]) -> str:
    if isinstance(value, RecRef):
        return ref_names.get(id(value), f"<unresolved RecRef #{value._id}>")
    if isinstance(value, dict):
        items = ", ".join(
            f"{_py_arg(k, ref_names)}: {_py_arg(v, ref_names)}"
            for k, v in value.items()
        )
        return "{" + items + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_py_arg(v, ref_names) for v in value) + "]"
    if isinstance(value, tuple):
        return "(" + ", ".join(_py_arg(v, ref_names) for v in value) + ("," if len(value) == 1 else "") + ")"
    if callable(value):
        name = getattr(value, "__name__", None) or repr(value)
        return f"<callable:{name}>"
    return repr(value)


# ----------------------------------------------------------------------
# JSON pretty-printer
# ----------------------------------------------------------------------

def op_list_to_json(op_list: OpList) -> dict:
    """Return a JSON-shaped dict representing the op-list. Lossy:
    callables and RecRefs become opaque markers. Pure data on the wire."""
    return {
        "engine": op_list.engine,
        "ops": [_op_to_json(op) for op in op_list.ops],
    }


def _op_to_json(op: Op) -> dict:
    return {
        "method": op.method,
        "args": [_json_value(a) for a in op.args],
        "kwargs": {k: _json_value(v) for k, v in op.kwargs.items()},
        "source": list(op.source),
        "out_ref": _recref_marker(op.out_ref) if op.out_ref is not None else None,
    }


def _recref_marker(ref: RecRef) -> dict:
    return {"__recref__": ref._id, "kind": ref._kind}


def _json_value(value: Any) -> Any:
    if isinstance(value, RecRef):
        return _recref_marker(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if callable(value):
        name = getattr(value, "__name__", None) or repr(value)
        return {"__callable__": name}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
