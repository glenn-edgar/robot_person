"""Trivial control-flow main fns and the CFL_NULL no-op fns.

These are the building blocks the DSL composes. A leaf like `asm_terminate()`
is just a node whose main fn name is "CFL_TERMINATE" — looked up in the
registry, called, and the returned code drives the walker.

Naming convention follows the LuaJIT / yaml-Python ports: the main fn that
returns code X is named X. The string literal "CFL_DISABLE" is overloaded
between (a) the return code and (b) the name of the main fn that returns
that code; lookup table disambiguates.
"""

from __future__ import annotations

from ct_runtime.codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_HALT,
    CFL_RESET,
    CFL_TERMINATE,
    CFL_TERMINATE_SYSTEM,
)


# ---------------------------------------------------------------------------
# Main fns — each just returns its eponymous code.
# ---------------------------------------------------------------------------

def cfl_continue_main(handle, bool_fn_name, node, event):
    return CFL_CONTINUE


def cfl_halt_main(handle, bool_fn_name, node, event):
    return CFL_HALT


def cfl_disable_main(handle, bool_fn_name, node, event):
    return CFL_DISABLE


def cfl_terminate_main(handle, bool_fn_name, node, event):
    return CFL_TERMINATE


def cfl_reset_main(handle, bool_fn_name, node, event):
    return CFL_RESET


def cfl_terminate_system_main(handle, bool_fn_name, node, event):
    return CFL_TERMINATE_SYSTEM


# ---------------------------------------------------------------------------
# CFL_NULL — universal no-op fns, used as default boolean / one-shot slots.
# ---------------------------------------------------------------------------

def cfl_null_boolean(handle, node, event_type, event_id, event_data) -> bool:
    """Default boolean: always returns False so 'aux true → disable' early-outs
    do not trigger when the caller didn't supply a real aux fn.
    """
    return False


def cfl_null_one_shot(handle, node) -> None:
    """Default init/term one-shot: does nothing."""
    return None


CONTROL_MAINS = {
    "CFL_CONTINUE": cfl_continue_main,
    "CFL_HALT": cfl_halt_main,
    "CFL_DISABLE": cfl_disable_main,
    "CFL_TERMINATE": cfl_terminate_main,
    "CFL_RESET": cfl_reset_main,
    "CFL_TERMINATE_SYSTEM": cfl_terminate_system_main,
}

NULL_BOOLEAN_NAME = "CFL_NULL"
NULL_ONE_SHOT_NAME = "CFL_NULL"
