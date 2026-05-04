"""coffee_maker/run.py — standalone entry point.

Runs the `morning_kb` solution end-to-end with a stubbed wall clock
(AM by default; pass `pm` as the first arg to flip the branch). Logs
go to stdout so the demo is visible without a logger.

Usage (from the repo root):
  source enter_venv.sh
  python -m examples.coffee_maker.run        # AM run
  python -m examples.coffee_maker.run pm     # PM run
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone


def _ensure_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    examples = os.path.dirname(here)
    repo = os.path.dirname(examples)
    for p in (repo, os.path.join(repo, "chain_tree"), examples):
        if p not in sys.path:
            sys.path.insert(0, p)


def _epoch_for_hour_utc(hour: int) -> int:
    return int(datetime(2026, 5, 1, hour, 0, 0, tzinfo=timezone.utc).timestamp())


def main(argv: list[str]) -> int:
    _ensure_paths()
    from coffee_maker.bootstrap import bootstrap
    from template_language import generate_code, use_template

    bootstrap()

    branch = (argv[1] if len(argv) > 1 else "am").lower()
    if branch not in {"am", "pm"}:
        print(f"unknown branch {branch!r}; expected am or pm", file=sys.stderr)
        return 2
    hour = 9 if branch == "am" else 15

    op_list = use_template(
        "project.coffee_maker.solutions.chain_tree.morning_kb",
        kb_name="kitchen",
    )
    log: list[str] = []
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: _epoch_for_hour_utc(hour),
        timezone=timezone.utc,
        logger=log.append,
    )
    counter = {"n": 0}

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= 5:
            chain.engine["cfl_engine_flag"] = False

    chain.engine["sleep"] = capped_sleep
    chain.run(starting=["kitchen"])

    print(f"=== coffee_maker {branch.upper()} run ===")
    for line in log:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
