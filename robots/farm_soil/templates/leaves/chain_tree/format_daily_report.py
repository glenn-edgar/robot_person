"""project.farm_soil.leaves.chain_tree.format_daily_report — render to bb.

Registers a one-shot that reads two upstream blackboard keys (moisture
rows + CIMIS ETo rows produced by sqlite_query leaves) and writes the
formatted daily-report string under a third blackboard key.

Project-local because the format is specific to farm_soil's report
shape; not promoted to user_templates until a second consumer appears.

Slots:
  name              required STRING — disambiguates one-shot registration.
  moisture_bb_key   required STRING — bb key holding the moisture
                                       list-of-dicts (sqlite_query output).
  eto_bb_key        required STRING — bb key holding the ETo
                                       list-of-dicts.
  result_bb_key     required STRING — bb key to write the formatted
                                       string under.
"""

from __future__ import annotations

from farm_soil.format import format_daily_report

from template_language import ct, define_template


def format_daily_report_leaf(
    *,
    name: str,
    moisture_bb_key: str,
    eto_bb_key: str,
    result_bb_key: str,
):
    """Read two row lists from bb, format, write the message string to bb."""

    def _do_format(handle, node):
        logger = handle["engine"].get("logger") or print
        moisture_rows = handle["blackboard"].get(moisture_bb_key) or []
        eto_rows = handle["blackboard"].get(eto_bb_key) or []
        text = format_daily_report(moisture_rows, eto_rows)
        handle["blackboard"][result_bb_key] = text
        logger(
            f"format_daily_report[{name}]: wrote {len(text)} chars to "
            f"bb[{result_bb_key!r}] (moisture={len(moisture_rows)} "
            f"eto={len(eto_rows)})"
        )

    one_shot_name = f"FORMAT_DAILY_REPORT_{name}"
    ct.add_one_shot(one_shot_name, _do_format)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="project.farm_soil.leaves.chain_tree.format_daily_report",
    fn=format_daily_report_leaf,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "daily",
        "moisture_bb_key": "daily_report.moisture_rows",
        "eto_bb_key": "daily_report.eto_rows",
        "result_bb_key": "daily_report.text",
    },
)
