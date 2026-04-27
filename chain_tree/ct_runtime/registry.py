"""User-function registries.

Two parallel registries live on every engine handle:

- **CFL-side** — functions invoked by the CFL walker as leaf main / boolean /
  one-shot callbacks. Three tables (main, boolean, one_shot).
- **s_engine-side** — functions registered into s_engine modules constructed
  for that engine (m_call / p_call / o_call / io_call). Four tables.

Names are strings; lookup is by string at runtime. Distinct namespace from the
CFL side — the same name may mean different things in the two registries
without collision. Built-in CFL node mains (CFL_COLUMN_MAIN, etc.) live in
the same main table, pre-populated by the engine.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, Optional


def new_registry() -> dict:
    """Build a fresh registry bundle (both sides)."""
    return {
        "cfl": {
            "main": {},
            "boolean": {},
            "one_shot": {},
            "descriptions": {},
        },
        "se": {
            "m_call": {},
            "p_call": {},
            "o_call": {},
            "io_call": {},
            "descriptions": {},
        },
    }


# ---------------------------------------------------------------------------
# CFL-side
# ---------------------------------------------------------------------------

def add_main(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["cfl"], "main", name, fn, description)


def add_boolean(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["cfl"], "boolean", name, fn, description)


def add_one_shot(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["cfl"], "one_shot", name, fn, description)


def lookup_main(registry: dict, name: str) -> Optional[Callable]:
    return registry["cfl"]["main"].get(name)


def lookup_boolean(registry: dict, name: str) -> Optional[Callable]:
    return registry["cfl"]["boolean"].get(name)


def lookup_one_shot(registry: dict, name: str) -> Optional[Callable]:
    return registry["cfl"]["one_shot"].get(name)


# ---------------------------------------------------------------------------
# s_engine-side
# ---------------------------------------------------------------------------

def add_se_main(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["se"], "m_call", name, fn, description)


def add_se_pred(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["se"], "p_call", name, fn, description)


def add_se_one_shot(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["se"], "o_call", name, fn, description)


def add_se_io_one_shot(registry: dict, name: str, fn: Callable, description: str = "") -> None:
    _register(registry["se"], "io_call", name, fn, description)


def lookup_se(registry: dict, table: str, name: str) -> Optional[Callable]:
    return registry["se"][table].get(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def all_cfl_names(registry: dict) -> Iterator[str]:
    for table in ("main", "boolean", "one_shot"):
        yield from registry["cfl"][table].keys()


def _register(
    side: Dict[str, Any],
    table: str,
    name: str,
    fn: Callable,
    description: str,
) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError(f"registry: name must be a non-empty string, got {name!r}")
    if not callable(fn):
        raise TypeError(f"registry: fn for {name!r} must be callable, got {fn!r}")
    existing = side[table].get(name)
    if existing is not None and existing is not fn:
        raise ValueError(
            f"registry: {table} name {name!r} already registered to a different callable"
        )
    side[table][name] = fn
    if description:
        side["descriptions"][name] = description
