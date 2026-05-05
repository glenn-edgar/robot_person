"""Standalone test program for CIMIS station 237 ETo.

Engine-agnostic: no chain_tree, no template_language. Demonstrates
the irrigation-grade fetch + finalisation check in one file so the
CIMIS half can be validated independently of the larger system.

What it does:
  1. Loads CIMIS_APP_KEY from robots/farm_soil/secrets/ttn.env (or env).
  2. Fetches the last 7 days of `day-asce-eto` from station 237.
  3. INSERTs OR IGNOREs into ./eto_237_demo.sqlite (idempotent).
  4. Checks `is_data_present(... require_finalised=True)` for
     California-yesterday — the predicate the upper-level chain_tree
     retry will use.
  5. Prints a 7-day table so you can see what's in the DB.

Run (from the repo root):
  source enter_venv.sh
  python -m robots.farm_soil.eto_237_demo

Re-running is safe: INSERT OR IGNORE means rerunning before any new
data lands inserts 0 new rows. Once CIMIS finalises yesterday's
reading, `finalised? True` flips and the irrigation logic can proceed.
"""

from __future__ import annotations

import os
import sqlite3
import sys


def _ensure_paths() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(here))
    if repo not in sys.path:
        sys.path.insert(0, repo)


_ensure_paths()
from robots.farm_soil.run import _load_dotenv  # noqa: E402
from skills.cimis import CimisFetcher          # noqa: E402
from skills.cimis.check import (                # noqa: E402
    california_yesterday,
    is_data_present,
)


DB_PATH = "./eto_237_demo.sqlite"
STATION = "237"
DATA_ITEM_REQUEST = "day-asce-eto"
DATA_ITEM_FIELD = "DayAsceEto"
LOOKBACK_DAYS = 7


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    secrets = _load_dotenv(os.path.join(here, "secrets", "ttn.env"))
    key = secrets.get("CIMIS_APP_KEY") or os.environ.get("CIMIS_APP_KEY")
    if not key:
        print(
            "CIMIS_APP_KEY not found. Add it to "
            "robots/farm_soil/secrets/ttn.env or export it.",
            file=sys.stderr,
        )
        return 2

    print(f"=== eto_237_demo: station {STATION}, item {DATA_ITEM_FIELD} ===")
    print()

    fetcher = CimisFetcher(
        db_path=DB_PATH,
        app_key=key,
        station_targets=STATION,
        spatial_targets="",
        data_items=DATA_ITEM_REQUEST,
        lookback_days=LOOKBACK_DAYS,
        logger=print,
    )
    rows = fetcher.tick()
    print(f"--- inserted {rows} new rows into {DB_PATH} ---")
    print()

    yesterday = california_yesterday()
    present_any = is_data_present(
        DB_PATH,
        target_kind="station", target=STATION,
        date=yesterday, item=DATA_ITEM_FIELD,
    )
    present_finalised = is_data_present(
        DB_PATH,
        target_kind="station", target=STATION,
        date=yesterday, item=DATA_ITEM_FIELD,
        require_finalised=True,
    )
    print(f"--- predicate checks for yesterday ({yesterday}) ---")
    print(f"  is_data_present (any row):                    {present_any}")
    print(f"  is_data_present (require_finalised=True):     {present_finalised}")
    if present_any and not present_finalised:
        print("  -> CIMIS has a provisional row (qc='A' or value=NULL);")
        print("     upper-level retry will keep polling until it finalises.")
    elif present_finalised:
        print("  -> ready: irrigation logic can proceed.")
    else:
        print("  -> no row yet; first fetch of the day or CIMIS not yet")
        print("     produced yesterday's reading.")
    print()

    conn = sqlite3.connect(DB_PATH)
    try:
        finalised = conn.execute(
            "SELECT date, value, unit FROM cimis_eto "
            "WHERE target_kind = ? AND target = ? AND item = ? "
            "ORDER BY date DESC LIMIT ?",
            ("station", STATION, DATA_ITEM_FIELD, LOOKBACK_DAYS),
        ).fetchall()
    finally:
        conn.close()

    print(f"--- last {LOOKBACK_DAYS} days for station {STATION} ---")
    print(f"  {'date':<12} {'value':>8} {'unit':<8}")
    if not finalised:
        print("  (none — CIMIS hasn't finalised any day in the window yet)")
    for date_, val, unit in finalised:
        val_str = f"{val:.3f}" if val is not None else "(null)"
        print(f"  {date_:<12} {val_str:>8} {unit or '-':<8}")
    print()
    print("  CimisFetcher(skip_provisional=True) discards qc='A' rows at the")
    print("  insert layer, so the DB only ever holds finalised values.")
    print("  Irrigation logic uses yesterday's row from this table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
