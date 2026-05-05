"""skills.cimis — fetch CIMIS station + spatial ETo data into SQLite.

Per the skills convention (skills/README.md): one class + __main__
test driver. Engine-agnostic — no chain_tree / s_engine imports.

Public class:
  CimisFetcher — `__init__(...)` + `tick() -> int` (rows inserted).

CIMIS provides station-based readings (named weather stations across
California) and spatially-interpolated estimates (any lat/lng). This
skill fetches either or both in one tick and writes to a single
table; the report layer picks them apart by `target_kind`.

Helper modules:
  api.py      — CimisClient (urllib wrapper)
  decoder.py  — JSON response parser
  db.py       — SQLite schema + INSERT OR IGNORE writer
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

from .api import CimisClient
from .db import insert_record, open_or_create
from .decoder import parse_response


class CimisFetcher:
    """Fetch CIMIS station + spatial data over a lookback window.

    `station_targets` and `spatial_targets` are CSV strings — pass
    "" (empty) to skip that side.
      station_targets="237"             — single station
      station_targets="237,238"         — multiple stations
      spatial_targets="92590"           — zip code (RECOMMENDED — CIMIS
                                          interpolates to zip centroid
                                          and returns Type=spatial)
      spatial_targets="33.578,-117.299" — coordinate pair (currently
                                          rejected by CIMIS with ERR2006
                                          regardless of wrapping; use a
                                          zip code instead)

    CIMIS uses `,` as the multi-target delimiter in `targets`, so
    coordinate pairs (when they work) must be wrapped in parens to
    escape the lat/lng comma. The skill wraps automatically. Zip
    codes pass through unchanged (no internal comma).

    `data_items` is a CSV of CIMIS data-item codes:
      "day-asce-eto"                  — daily ASCE-EWRI ETo (default —
                                          works for BOTH station and
                                          spatial targets).
      "day-eto"                       — legacy daily ETo. STATION-ONLY;
                                          spatial requests fail with
                                          ERR2006 "INVALID TARGET" since
                                          CIMIS doesn't compute legacy
                                          ETo on the spatial grid.
      "day-asce-eto,day-air-tmp-max"  — multiple

    `tick()` queries today minus `lookback_days` through today,
    INSERTs OR IGNOREs each record, returns rows inserted. Idempotent
    across calls — re-running the same window inserts nothing new.

    `skip_provisional=True` (default) drops rows whose `Qc` is "A"
    before they hit the DB. CIMIS marks today's reading "A" while it's
    still computing the running cumulative-of-day; the value drifts
    upward through the day and finalises overnight. Storing it would
    pollute the DB AND lock the provisional value in place, since
    INSERT OR IGNORE on the (target_kind, target, date, item) PK would
    silently reject tomorrow's finalised version. For irrigation
    scheduling — which uses yesterday's finalised value — provisional
    rows are noise. Set `skip_provisional=False` only if you need the
    real-time partial-day value for monitoring purposes.
    """

    def __init__(
        self,
        db_path: str,
        app_key: str,
        station_targets: str = "",
        spatial_targets: str = "",
        data_items: str = "day-asce-eto",
        lookback_days: int = 7,
        api_base: str = "https://et.water.ca.gov/api/data",
        skip_provisional: bool = True,
        logger=None,
    ):
        self.db_path = db_path
        self.station_targets = station_targets.strip()
        self.spatial_targets = spatial_targets.strip()
        self.data_items = data_items
        self.lookback_days = lookback_days
        self.skip_provisional = skip_provisional
        self.logger = logger or (lambda msg: None)
        self.client = CimisClient(app_key=app_key, api_base=api_base)

    def _date_range(self) -> tuple[str, str]:
        today = date.today()
        start = today - timedelta(days=self.lookback_days)
        return start.isoformat(), today.isoformat()

    def tick(self) -> int:
        start_date, end_date = self._date_range()
        groups: list[tuple[str, str]] = []
        if self.station_targets:
            groups.append(("station", self.station_targets))
        if self.spatial_targets:
            groups.append(("spatial", _wrap_spatial(self.spatial_targets)))
        if not groups:
            self.logger("cimis: no station_targets or spatial_targets configured")
            return 0

        rows = 0
        conn = open_or_create(self.db_path)
        try:
            for kind, targets in groups:
                self.logger(
                    f"cimis: fetching {kind} targets={targets} "
                    f"items={self.data_items} {start_date}..{end_date}"
                )
                body, ok, err = self.client.fetch(
                    targets=targets,
                    data_items=self.data_items,
                    start_date=start_date,
                    end_date=end_date,
                )
                if not ok:
                    self.logger(f"cimis: {kind} fetch FAILED — {err}")
                    continue
                self.logger(f"cimis: {kind} response {len(body)} bytes")
                records = parse_response(body)
                self.logger(f"cimis: {kind} parsed {len(records)} records")
                if not records and body:
                    preview = body[:300].replace("\n", "\\n")
                    self.logger(f"cimis: body preview: {preview}")
                skipped = 0
                for rec in records:
                    if self.skip_provisional and rec.qc == "A":
                        skipped += 1
                        continue
                    rows += insert_record(conn, rec)
                if skipped:
                    self.logger(
                        f"cimis: {kind} skipped {skipped} provisional (qc='A') row(s)"
                    )
            self.logger(f"cimis: inserted {rows} new rows into {self.db_path}")
            return rows
        finally:
            conn.close()


def _wrap_spatial(spec: str) -> str:
    """Format spatial targets for CIMIS' `targets` parameter.

    CIMIS accepts three target types in `targets`: station ids, zip
    codes, and coordinate pairs. Zip codes pass through unchanged
    (they're integer-shaped, no comma collision with the multi-target
    delimiter). Coordinate pairs (anything containing a `.`) get
    wrapped in parens to escape the lat/lng comma.

    Accepts:
      "92590"                     -> "92590"
      "92590,92591"               -> "92590,92591"
      "33.578,-117.299"           -> "(33.578,-117.299)"
      "33.578,-117.299;34.0,-118.0" -> "(33.578,-117.299),(34.0,-118.0)"
      "(33.578,-117.299)"         -> unchanged

    Note: as of 2026-05-05, raw lat/lng pairs are rejected by CIMIS
    with ERR2006 regardless of wrapping. Zip codes work and return
    spatial-type data interpolated to the zip's centroid — that's
    the recommended way to get spatial ETo for a location.
    """
    spec = spec.strip()
    if not spec or spec.startswith("("):
        return spec
    if "." not in spec:
        return spec  # zip code(s), no wrap
    pairs = [p.strip() for p in spec.split(";") if p.strip()]
    return ",".join(f"({p})" for p in pairs)


if __name__ == "__main__":
    key = os.environ.get("CIMIS_APP_KEY")
    if not key:
        print(
            "CIMIS_APP_KEY not set; export it (or add a CIMIS_APP_KEY=... "
            "line to robots/<robot>/secrets/ttn.env) and re-run.",
            file=sys.stderr,
        )
        sys.exit(2)

    fetcher = CimisFetcher(
        db_path="./cimis_smoke.sqlite",
        app_key=key,
        station_targets="237",
        spatial_targets="",            # spatial disabled by default; see docstring
        data_items="day-asce-eto",
        lookback_days=7,
        logger=print,
    )
    rows = fetcher.tick()
    print(f"final: inserted {rows} rows into {fetcher.db_path}")
