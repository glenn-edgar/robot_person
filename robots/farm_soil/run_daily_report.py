"""farm_soil/run_daily_report.py — fire one daily-report cycle.

Loads dev/prod config + secrets, compiles the
`project.farm_soil.solutions.chain_tree.daily_report` solution, runs
it for one tick, prints the captured log. The solution ends with
`asm_terminate_system`, so the engine exits cleanly. A real Discord
post is made — this hits the webhook URL in secrets/ttn.env. There
is no dry-run flag; if you want a deterministic no-network path, run
the test instead:

  pytest robots/farm_soil/tests/test_daily_report_composite.py

Usage (from the repo root):
  source enter_venv.sh
  # ensure DISCORD_WEBHOOK_URL=... is in robots/farm_soil/secrets/ttn.env
  python -m robots.farm_soil.run_daily_report                # dev config
  python -m robots.farm_soil.run_daily_report --config prod
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

    parser = argparse.ArgumentParser(description="farm_soil daily-report runner")
    parser.add_argument("--config", default="dev", choices=("dev", "prod"))
    args = parser.parse_args(argv[1:])

    cfg = _load_yaml(os.path.join(here, "config", f"{args.config}.yaml"))
    secrets_env = _load_dotenv(os.path.join(here, "secrets", "ttn.env"))
    webhook_url = (
        secrets_env.get("DISCORD_WEBHOOK_URL")
        or os.environ.get("DISCORD_WEBHOOK_URL")
    )
    if not webhook_url:
        print(
            "DISCORD_WEBHOOK_URL not found. Either:\n"
            "  - add DISCORD_WEBHOOK_URL=https://... to "
            "robots/farm_soil/secrets/ttn.env, or\n"
            "  - export DISCORD_WEBHOOK_URL=...",
            file=sys.stderr,
        )
        return 2

    required = ("db_path", "cimis_db_path")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        print(
            f"missing keys in config/{args.config}.yaml: {missing}",
            file=sys.stderr,
        )
        return 2

    from farm_soil.bootstrap import bootstrap as fs_bootstrap
    from template_language import generate_code, use_template
    from user_templates.bootstrap import bootstrap as u_bootstrap

    fs_bootstrap()
    u_bootstrap()

    op_list = use_template(
        "project.farm_soil.solutions.chain_tree.daily_report",
        kb_name="farm_soil_daily_report",
        moisture_db_path=cfg["db_path"],
        cimis_db_path=cfg["cimis_db_path"],
        webhook_url=webhook_url,
        moisture_lookback_hours=cfg.get("lookback_hours", 48),
        cimis_lookback_days=cfg.get("cimis_lookback_days", 7),
        cimis_station=str(cfg.get("cimis_station_targets", "237")),
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
    chain.run(starting=["farm_soil_daily_report"])

    print(
        f"=== farm_soil daily-report run: config={args.config} "
        f"moist_db={cfg['db_path']} cimis_db={cfg['cimis_db_path']} ==="
    )
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
