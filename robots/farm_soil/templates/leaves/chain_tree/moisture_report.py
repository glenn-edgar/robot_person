"""project.farm_soil.leaves.chain_tree.moisture_report — print a report.

Registers a one-shot that calls `farm_soil.report.format_report`
against the same SQLite DB the fetch leaf wrote, then logs each
line via `handle["engine"]["logger"]`. Output is sorted by
`device_id` per the report logic.

Slots:
  name             required STRING — disambiguates one-shot registration.
  db_path          required STRING — SQLite file path.
  lookback_hours   optional INT    — defaults to 36.
"""

from __future__ import annotations

from farm_soil.report import format_report

from template_language import ct, define_template


def moisture_report(
    *,
    name: str,
    db_path: str,
    lookback_hours: int = 36,
):
    """Log a per-device moisture/RF summary covering the last window."""

    def _do_report(handle, node):
        logger = handle["engine"].get("logger") or print
        for line in format_report(db_path, lookback_hours):
            logger(line)

    one_shot_name = f"FARM_SOIL_REPORT_{name}"
    ct.add_one_shot(one_shot_name, _do_report)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="project.farm_soil.leaves.chain_tree.moisture_report",
    fn=moisture_report,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "inspect",
        "db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "lookback_hours": 36,
    },
)
