"""project.farm_soil.leaves.chain_tree.cimis_report — print CIMIS report.

Registers a one-shot that calls `farm_soil.cimis_report.format_report`
against the CIMIS SQLite DB and logs each line via the engine logger.

Slots:
  name             required STRING — disambiguates one-shot registration.
  db_path          required STRING — CIMIS SQLite file path.
  lookback_days    optional INT    — defaults to 7.
"""

from __future__ import annotations

from farm_soil.cimis_report import format_report

from template_language import ct, define_template


def cimis_report(
    *,
    name: str,
    db_path: str,
    lookback_days: int = 7,
):
    """Log a per-item, per-day CIMIS table over the last window."""

    def _do_report(handle, node):
        logger = handle["engine"].get("logger") or print
        for line in format_report(db_path, lookback_days):
            logger(line)

    one_shot_name = f"FARM_SOIL_CIMIS_REPORT_{name}"
    ct.add_one_shot(one_shot_name, _do_report)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="project.farm_soil.leaves.chain_tree.cimis_report",
    fn=cimis_report,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "inspect",
        "db_path": "/var/lib/farm_soil/farm_soil_cimis.sqlite",
        "lookback_days": 7,
    },
)
