"""Emit a module to a Python source file.

The emitted file is an importable Python module containing:
  - Grouped `from X import Y, Z` lines for every fn referenced in the trees
  - A `MODULE` dict literal with the full shape (dictionary, constants,
    trees, optional get_time/crash_callback)

The file is importable and `MODULE` can be passed to `load_module()`. Unlike
wire serialization, the emitted file holds callable references directly —
the trust boundary is the Python import system itself.

Tuple keys (e.g., state_machine.transitions) are emitted as Python literals,
so the file produces a dict with tuple keys when imported. load_module works
unchanged on the output.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

_INDENT = "    "


# ---------------------------------------------------------------------------
# Collect fns used across all trees
# ---------------------------------------------------------------------------

def _collect_fns(module: Mapping[str, Any]) -> dict[str, Callable]:
    collected: dict[str, Callable] = {}
    for tree in (module.get("trees") or {}).values():
        _walk_tree(tree, collected)
    return collected


def _walk_tree(node: Mapping[str, Any], out: dict[str, Callable]) -> None:
    fn = node["fn"]
    name = fn.__name__
    existing = out.get(name)
    if existing is not None and existing is not fn:
        raise ValueError(
            f"emit_module_file: two different fns share the name {name!r}; "
            "rename or disambiguate before emitting."
        )
    out[name] = fn
    for child in node.get("children") or ():
        _walk_tree(child, out)


# ---------------------------------------------------------------------------
# Group imports by source module
# ---------------------------------------------------------------------------

def _group_imports(fns: Mapping[str, Callable]) -> dict[str, list[str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for name, fn in fns.items():
        module_name = getattr(fn, "__module__", None)
        if not module_name:
            raise ValueError(f"emit_module_file: fn {name!r} has no __module__")
        groups[module_name].add(name)
    return {mod: sorted(names) for mod, names in groups.items()}


def _format_imports(imports: Mapping[str, Iterable[str]]) -> list[str]:
    lines: list[str] = []
    for mod_name in sorted(imports):
        names = list(imports[mod_name])
        if len(names) == 1:
            lines.append(f"from {mod_name} import {names[0]}")
        else:
            lines.append(f"from {mod_name} import (")
            for name in names:
                lines.append(f"{_INDENT}{name},")
            lines.append(")")
    return lines


# ---------------------------------------------------------------------------
# Format dict/tree as Python source
# ---------------------------------------------------------------------------

def _format_value(value: Any, depth: int = 0) -> str:
    pad = _INDENT * depth
    inner = _INDENT * (depth + 1)

    if callable(value) and hasattr(value, "__name__"):
        return value.__name__

    if isinstance(value, dict):
        if not value:
            return "{}"
        items = []
        for k, v in value.items():
            items.append(f"{inner}{repr(k)}: {_format_value(v, depth + 1)}")
        return "{\n" + ",\n".join(items) + ",\n" + pad + "}"

    if isinstance(value, list):
        if not value:
            return "[]"
        items = [f"{inner}{_format_value(v, depth + 1)}" for v in value]
        return "[\n" + ",\n".join(items) + ",\n" + pad + "]"

    if isinstance(value, tuple):
        items = [_format_value(v, depth + 1) for v in value]
        return "(" + ", ".join(items) + (",)" if len(items) == 1 else ")")

    # Primitives — repr gives valid Python
    return repr(value)


# ---------------------------------------------------------------------------
# Build the module dict for serialization (strip MappingProxy, drop defaults)
# ---------------------------------------------------------------------------

def _module_to_source_dict(module: Mapping[str, Any]) -> dict:
    return {
        "dictionary": dict(module.get("dictionary") or {}),
        "constants": dict(module.get("constants") or {}),
        "trees": {name: tree for name, tree in (module.get("trees") or {}).items()},
    }


# ---------------------------------------------------------------------------
# emit_module_file — public
# ---------------------------------------------------------------------------

def emit_module_file(
    module: Mapping[str, Any],
    output_path: str,
    header: str | None = None,
) -> None:
    """Write `module` to `output_path` as an importable Python source file.

    The file defines a single `MODULE` dict. Import and pass to
    `load_module()` to reconstruct an engine-ready module.
    """
    fns = _collect_fns(module)
    imports = _group_imports(fns)

    lines: list[str] = []
    if header:
        for hline in header.splitlines():
            lines.append(hline.rstrip() if hline.startswith("#") else f"# {hline}".rstrip())
    lines.append(
        f"# Generated by emit_module_file at "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}."
    )
    lines.append("# Do not edit by hand — regenerate from DSL source.")
    lines.append("")
    lines.extend(_format_imports(imports))
    lines.append("")
    lines.append("")

    source_dict = _module_to_source_dict(module)
    lines.append("MODULE = " + _format_value(source_dict, depth=0))
    lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
