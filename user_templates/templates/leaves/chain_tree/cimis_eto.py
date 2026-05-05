"""user.leaves.chain_tree.cimis_eto — wrap CimisFetcher as a leaf.

Registers a one-shot that constructs a `CimisFetcher` from slot
values, calls `tick()`, and logs progress via the engine logger.
Multiple instances coexist by giving each a distinct `name` slot —
the one-shot is registered as `CIMIS_ETO_<name>`.

Slots:
  name              required STRING — disambiguates one-shot registration.
  db_path           required STRING — SQLite file path (may be shared
                                       across leaves).
  app_key           required STRING — CIMIS Web API AppKey.
  station_targets   optional STRING — CSV of station ids, e.g. "237"
                                       or "237,238". "" to skip.
  spatial_targets   optional STRING — single "lat,lng" coord, e.g.
                                       "33.578,-117.299". "" to skip.
  data_items        optional STRING — CSV of CIMIS data-item codes,
                                       defaults to "day-asce-eto".
                                       Note: "day-eto" is station-only;
                                       spatial requests need ASCE.
  lookback_days     optional INT    — defaults to 7.
"""

from __future__ import annotations

from skills.cimis import CimisFetcher

from template_language import ct, define_template


def cimis_eto(
    *,
    name: str,
    db_path: str,
    app_key: str,
    station_targets: str = "",
    spatial_targets: str = "",
    data_items: str = "day-asce-eto",
    lookback_days: int = 7,
):
    """Fetch one CIMIS window into SQLite via CimisFetcher.tick()."""

    def _do_fetch(handle, node):
        logger = handle["engine"].get("logger") or print
        fetcher = CimisFetcher(
            db_path=db_path,
            app_key=app_key,
            station_targets=station_targets,
            spatial_targets=spatial_targets,
            data_items=data_items,
            lookback_days=lookback_days,
            logger=logger,
        )
        rows = fetcher.tick()
        logger(f"cimis_eto[{name}]: final {rows} new rows into {db_path}")

    one_shot_name = f"CIMIS_ETO_{name}"
    ct.add_one_shot(one_shot_name, _do_fetch)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="user.leaves.chain_tree.cimis_eto",
    fn=cimis_eto,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "farm_eto",
        "db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "app_key": "00000000-0000-0000-0000-000000000000",
        "station_targets": "237",
        "spatial_targets": "33.578,-117.299",
        "data_items": "day-asce-eto",
        "lookback_days": 7,
    },
)
