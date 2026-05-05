"""farm_soil/run.py — standalone entry point for the inspect_36h solution.

Loads dev/prod config + ttn.env secrets, compiles the
`project.farm_soil.solutions.chain_tree.inspect_36h` solution, runs
it for one tick, then prints the captured log. The solution ends
with `asm_terminate_system` so the engine exits cleanly.

Usage (from the repo root):
  source enter_venv.sh
  cp robots/farm_soil/secrets/ttn.env.example robots/farm_soil/secrets/ttn.env
  # edit ttn.env: TTN_BEARER_TOKEN=NNSXS.…
  python -m robots.farm_soil.run                    # dev config, 36h lookback
  python -m robots.farm_soil.run --config prod
  python -m robots.farm_soil.run --lookback 12
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


def _load_dotenv(path: str) -> dict[str, str]:
    """Read KEY=VALUE lines (skips blanks and `#` comments)."""
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _load_yaml(path: str) -> dict:
    """Cheap YAML shim — only handles the flat `key: value` shape we use."""
    out: dict = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            k, _, v = line.partition(":")
            v = v.strip()
            if not v:
                continue
            try:
                out[k.strip()] = int(v)
            except ValueError:
                out[k.strip()] = v.strip('"').strip("'")
    return out


def main(argv: list[str]) -> int:
    _ensure_paths()
    here = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="farm_soil inspect runner")
    parser.add_argument("--config", default="dev", choices=("dev", "prod"))
    parser.add_argument("--lookback", type=int, default=None,
                        help="override lookback_hours")
    args = parser.parse_args(argv[1:])

    cfg = _load_yaml(os.path.join(here, "config", f"{args.config}.yaml"))
    secrets_env = _load_dotenv(os.path.join(here, "secrets", "ttn.env"))
    token = secrets_env.get("TTN_BEARER_TOKEN") or os.environ.get("TTN_BEARER_TOKEN")
    if not token:
        print(
            "TTN_BEARER_TOKEN not found. Either:\n"
            "  - copy robots/farm_soil/secrets/ttn.env.example to ttn.env "
            "and set TTN_BEARER_TOKEN, or\n"
            "  - export TTN_BEARER_TOKEN=...",
            file=sys.stderr,
        )
        return 2

    required = ("db_path", "ttn_application", "ttn_api_base", "ttn_url_after")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        print(
            f"missing keys in config/{args.config}.yaml: {missing}",
            file=sys.stderr,
        )
        return 2

    lookback = args.lookback if args.lookback is not None else cfg.get("lookback_hours", 48)

    from farm_soil.bootstrap import bootstrap as fs_bootstrap
    from template_language import generate_code, use_template
    from user_templates.bootstrap import bootstrap as u_bootstrap

    fs_bootstrap()
    u_bootstrap()

    op_list = use_template(
        "project.farm_soil.solutions.chain_tree.inspect_36h",
        kb_name="farm_soil_inspect",
        db_path=cfg["db_path"],
        ttn_url_base=cfg["ttn_api_base"],
        ttn_app=cfg["ttn_application"],
        ttn_url_after=cfg["ttn_url_after"],
        ttn_bearer_token=token,
        lookback_hours=lookback,
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
    chain.run(starting=["farm_soil_inspect"])

    print(
        f"=== farm_soil run: config={args.config} "
        f"app={cfg['ttn_application']} db={cfg['db_path']} lookback={lookback}h ==="
    )
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
