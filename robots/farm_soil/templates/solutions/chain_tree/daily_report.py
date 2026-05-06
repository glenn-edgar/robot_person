"""project.farm_soil.solutions.chain_tree.daily_report — one-shot solution.

Opens a KB column, expands the daily_report composite, then calls
asm_terminate_system so the engine exits after one cycle. The
chain_tree-native equivalent of `python -m robots.farm_soil.run_*`
for the report path: scheduling lives outside the engine (a systemd
timer or `loop` script fires it daily), and the solution itself is
fire-and-exit.

Slots are forwarded directly to the composite (same names, same
defaults) — keeping the surface flat means the runner can pass the
config dict through without renaming keys.
"""

from __future__ import annotations

from template_language import ct, define_template, use_template


def daily_report_solution(
    *,
    kb_name: str,
    moisture_db_path: str,
    cimis_db_path: str,
    webhook_url: str,
    moisture_lookback_hours: int = 48,
    cimis_lookback_days: int = 7,
    cimis_station: str = "237",
):
    """Build a single-tick daily-report KB: composite -> terminate."""
    ct.start_test(kb_name)
    use_template(
        "project.farm_soil.composites.chain_tree.daily_report",
        name=kb_name,
        moisture_db_path=moisture_db_path,
        cimis_db_path=cimis_db_path,
        webhook_url=webhook_url,
        moisture_lookback_hours=moisture_lookback_hours,
        cimis_lookback_days=cimis_lookback_days,
        cimis_station=cimis_station,
    )
    ct.asm_terminate_system()
    ct.end_test()


define_template(
    path="project.farm_soil.solutions.chain_tree.daily_report",
    fn=daily_report_solution,
    kind="solution",
    engine="chain_tree",
    slot_examples={
        "kb_name": "farm_soil_daily_report",
        "moisture_db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "cimis_db_path": "/var/lib/farm_soil/farm_soil_cimis.sqlite",
        "webhook_url": "https://discord.com/api/webhooks/<id>/<token>",
        "moisture_lookback_hours": 48,
        "cimis_lookback_days": 7,
        "cimis_station": "237",
    },
)
