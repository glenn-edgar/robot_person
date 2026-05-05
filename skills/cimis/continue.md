# cimis — continue

## Where we are (2026-05-05)

Fresh skill following the `skills/` convention (one class + `__main__`,
engine-agnostic, helpers alongside `main.py`).

  api.py      — `CimisClient` urllib wrapper around `et.water.ca.gov/api/data`.
                 HTTPS by default; appKey passed as query param.
  decoder.py  — `parse_response(body)` walks `Data.Providers[].Records[]`,
                 extracts target (station id or "lat,lng"), date, and any
                 `Day*` / `Hly*` measurement fields.
  db.py       — single `cimis_eto` table:
                   PK (target_kind, target, date, item)
                 INSERT OR IGNORE.
  main.py     — `CimisFetcher` with `tick() -> int`. Two CSV slots:
                 `station_targets="237"`, `spatial_targets="lat,lng"`.

## Verified against synthetic data

Tests exercise: station-only response, spatial-only response, mixed
provider response, malformed JSON, missing fields. No real network in
the test suite.

## Not yet verified

- Real CIMIS response shape (only fetched a sample shape from CIMIS
  docs and sample responses; real fetch may surface differences).
- Multi-coordinate spatial queries — CIMIS' `targets` parameter uses
  comma both as multi-target separator AND as lat/lng separator. For
  v1, `spatial_targets` is one point. If multiple spatial points are
  needed, instantiate multiple leaf templates.

## Next session

1. Run `python -m skills.cimis.main` with `CIMIS_APP_KEY` set; confirm
   the response parses without falling back to the body-preview
   diagnostic. Adjust decoder if shape diverges.
2. Wire into `farm_soil` either as an additional leaf in
   `inspect_36h` (if the same DB makes sense for both) or a new
   solution that fetches both lorwan_moisture and CIMIS data.
3. Optional: extend `farm_soil/report.py` to also include CIMIS ETo
   per day alongside the per-uplink moisture/RF table.
