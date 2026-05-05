"""farm_soil/run_cimis.py — standalone entry point for cimis_inspect.

Loads dev/prod config + CIMIS_APP_KEY from secrets/ttn.env, compiles
the `project.farm_soil.solutions.chain_tree.cimis_inspect` solution,
runs it for one tick, prints the captured log. Terminates after one
fetch via asm_terminate_system in the solution body.

Usage:
  source enter_venv.sh
  # ensure CIMIS_APP_KEY=... is in robots/farm_soil/secrets/ttn.env
  python -m robots.farm_soil.run_cimis                    # dev, 7d
  python -m robots.farm_soil.run_cimis --config prod
  python -m robots.farm_soil.run_cimis --lookback 14
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timezone


def _ensure_paths() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    robots = os.path.dirname(here)
    repo = os.path.dirname(robots)
    for p in (repo, os.path.join(repo, "chain_tree"), robots):
        if p not in sys.path:
            sys.path.insert(0, p)


_ensure_paths()
from farm_soil.run import _load_dotenv, _load_yaml  # noqa: E402


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="farm_soil CIMIS inspect runner")
    parser.add_argument("--config", default="dev", choices=("dev", "prod"))
    parser.add_argument("--lookback", type=int, default=None,
                        help="override cimis_lookback_days from config")
    args = parser.parse_args(argv[1:])

    cfg = _load_yaml(os.path.join(here, "config", f"{args.config}.yaml"))
    secrets_env = _load_dotenv(os.path.join(here, "secrets", "ttn.env"))
    app_key = secrets_env.get("CIMIS_APP_KEY") or os.environ.get("CIMIS_APP_KEY")
    if not app_key:
        print(
            "CIMIS_APP_KEY not found. Either:\n"
            "  - add CIMIS_APP_KEY=<your_key> to robots/farm_soil/secrets/ttn.env, or\n"
            "  - export CIMIS_APP_KEY=...",
            file=sys.stderr,
        )
        return 2

    required = ("cimis_db_path", "cimis_station_targets")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        print(
            f"missing keys in config/{args.config}.yaml: {missing}",
            file=sys.stderr,
        )
        return 2

    lookback = args.lookback if args.lookback is not None else cfg.get("cimis_lookback_days", 7)

    from farm_soil.bootstrap import bootstrap as fs_bootstrap
    from template_language import generate_code, use_template
    from user_templates.bootstrap import bootstrap as u_bootstrap

    fs_bootstrap()
    u_bootstrap()

    op_list = use_template(
        "project.farm_soil.solutions.chain_tree.cimis_inspect",
        kb_name="farm_soil_cimis_inspect",
        db_path=cfg["cimis_db_path"],
        app_key=app_key,
        station_targets=str(cfg["cimis_station_targets"]),
        spatial_targets=str(cfg.get("cimis_spatial_targets", "") or ""),
        data_items=cfg.get("cimis_data_items", "day-eto"),
        lookback_days=lookback,
    )

    log: list[str] = []
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: int(time.time()),
        timezone=timezone.utc,
        logger=log.append,
    )

    counter = {"n": 0}

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= 20:
            chain.engine["cfl_engine_flag"] = False

    chain.engine["sleep"] = capped_sleep
    chain.run(starting=["farm_soil_cimis_inspect"])

    print(
        f"=== farm_soil CIMIS run: config={args.config} "
        f"db={cfg['cimis_db_path']} station={cfg['cimis_station_targets']} "
        f"spatial={cfg.get('cimis_spatial_targets', '-')} lookback={lookback}d ==="
    )
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
