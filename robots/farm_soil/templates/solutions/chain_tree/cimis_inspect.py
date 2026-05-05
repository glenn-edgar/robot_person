"""project.farm_soil.solutions.chain_tree.cimis_inspect — single-tick inspector.

Solution: open KB column → fetch CIMIS station + spatial ETo over a
lookback window → print per-day table → terminate the engine.
Designed for human inspection. The retry-after-8-AM logic Glenn's
irrigation program needs lives at the upper-level chain_tree
composition (sequence_til_pass + time_gate + mark_link), NOT here.

Slots:
  kb_name            required STRING
  db_path            required STRING — CIMIS SQLite path.
  app_key            required STRING — CIMIS Web API AppKey.
  station_targets    required STRING — CSV of station ids, e.g. "237".
  spatial_targets    optional STRING — single "lat,lng" or "" to skip.
  data_items         optional STRING — defaults to "day-asce-eto"
                                        (works for both station and
                                        spatial targets).
  lookback_days      optional INT    — defaults to 7.
"""

from __future__ import annotations

from template_language import ct, define_template, use_template


def cimis_inspect(
    *,
    kb_name: str,
    db_path: str,
    app_key: str,
    station_targets: str,
    spatial_targets: str = "",
    data_items: str = "day-asce-eto",
    lookback_days: int = 7,
):
    """Build a single-tick CIMIS inspect KB: fetch -> report -> terminate."""
    ct.start_test(kb_name)
    use_template(
        "user.leaves.chain_tree.cimis_eto",
        name=kb_name,
        db_path=db_path,
        app_key=app_key,
        station_targets=station_targets,
        spatial_targets=spatial_targets,
        data_items=data_items,
        lookback_days=lookback_days,
    )
    use_template(
        "project.farm_soil.leaves.chain_tree.cimis_report",
        name=kb_name,
        db_path=db_path,
        lookback_days=lookback_days,
    )
    ct.asm_terminate_system()
    ct.end_test()


define_template(
    path="project.farm_soil.solutions.chain_tree.cimis_inspect",
    fn=cimis_inspect,
    kind="solution",
    engine="chain_tree",
    slot_examples={
        "kb_name": "farm_soil_cimis_inspect",
        "db_path": "/var/lib/farm_soil/farm_soil_cimis.sqlite",
        "app_key": "00000000-0000-0000-0000-000000000000",
        "station_targets": "237",
        "spatial_targets": "33.578,-117.299",
        "data_items": "day-asce-eto",
        "lookback_days": 7,
    },
)
