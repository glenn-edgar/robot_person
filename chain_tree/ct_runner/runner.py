"""Implementation of `python -m ct_runner my_test.py`.

The user file is loaded as an isolated module via importlib.util; its
top-level code constructs a `ChainTree` and builds KBs. The runner then
finds the named attribute, calls `.run(starting=...)`, and exits with a
status code reflecting whether the engine drained cleanly.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from typing import Iterable, Optional

from ct_dsl import ChainTree


def _load_user_module(path: str):
    """Load `path` (a .py file) as an anonymous module and return it."""
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"ct_runner: no such file: {abs_path}")
    spec = importlib.util.spec_from_file_location("__chain_tree_user__", abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"ct_runner: cannot load {abs_path!r} as a module")
    module = importlib.util.module_from_spec(spec)
    # Make the user file's directory importable so the script can `import`
    # sibling helper modules without ceremony.
    user_dir = os.path.dirname(abs_path)
    if user_dir and user_dir not in sys.path:
        sys.path.insert(0, user_dir)
    spec.loader.exec_module(module)
    return module


def run_script(
    path: str,
    var_name: str = "chain_tree",
    starting: Optional[Iterable[str]] = None,
) -> int:
    """Load `path`, locate its ChainTree under `var_name`, run it.

    Returns the process exit code (0 on clean completion, 1 otherwise).
    Exceptions raised by the user file or the engine propagate to the
    caller; the CLI wrapper translates them to exit code 1 + traceback.
    """
    user = _load_user_module(path)

    if not hasattr(user, var_name):
        sys.stderr.write(
            f"ct_runner: {path}: no attribute named {var_name!r}\n"
            f"           Define `{var_name} = ChainTree(...)` at module scope, "
            f"or pass --var=<name>.\n"
        )
        return 1

    chain = getattr(user, var_name)
    if not isinstance(chain, ChainTree):
        sys.stderr.write(
            f"ct_runner: {path}: attribute {var_name!r} is "
            f"{type(chain).__name__}, not ChainTree\n"
        )
        return 1

    if starting is None:
        starting = list(chain.engine["kbs"].keys())
    else:
        starting = list(starting)

    chain.run(starting=starting)

    if chain.engine["active_kbs"]:
        sys.stderr.write(
            f"ct_runner: {path}: engine returned with {len(chain.engine['active_kbs'])} "
            "active KBs still running — non-zero exit\n"
        )
        return 1
    return 0


def _parse_starting(value: Optional[str]) -> Optional[Iterable[str]]:
    if value is None:
        return None
    return [name.strip() for name in value.split(",") if name.strip()]


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI entry point. Returns the desired process exit code; the
    `__main__` shim translates that into `sys.exit(...)`.
    """
    parser = argparse.ArgumentParser(
        prog="python -m ct_runner",
        description="Load a chain_tree user script and run its ChainTree.",
    )
    parser.add_argument(
        "path", help="Path to the user .py file containing the ChainTree.")
    parser.add_argument(
        "--var", default="chain_tree",
        help="Module attribute name of the ChainTree instance (default: chain_tree).",
    )
    parser.add_argument(
        "--starting", default=None,
        help="Comma-separated KB names to activate (default: all registered KBs).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        return run_script(
            args.path,
            var_name=args.var,
            starting=_parse_starting(args.starting),
        )
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — top-level CLI catch
        import traceback
        sys.stderr.write(f"ct_runner: {args.path}: {type(exc).__name__}: {exc}\n")
        traceback.print_exc(file=sys.stderr)
        return 1
