"""Stage-2 test for the daily_report solution wrapper.

Distinct from test_daily_report_composite.py: this exercises the
*solution* layer (start_test → composite → asm_terminate_system →
end_test) which the runner invokes. Keeps the composite test focused
on data-flow correctness and this one focused on lifecycle —
templates resolve, the engine activates the solution's KB, and the
solution terminates the engine cleanly after a single tick.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

from skills.cimis.db import open_or_create as cimis_open
from skills.lorwan_moisture.db import open_or_create as moist_open
from template_language import generate_code, use_template


def _seed_minimal(moisture_db: str, cimis_db: str) -> None:
    """Bare-minimum schema init so the SELECTs return empty without erroring."""
    moist_open(moisture_db).close()
    cimis_open(cimis_db).close()


class _NullNotifier:
    instances: list["_NullNotifier"] = []

    def __init__(self, webhook_url, **_kwargs):
        self.webhook_url = webhook_url
        _NullNotifier.instances.append(self)

    def send(self, content, *, username=None):
        return True, None


def _patch_notifier(monkeypatch):
    _NullNotifier.instances = []
    import user_templates.templates.leaves.chain_tree.discord_notify as leaf
    monkeypatch.setattr(leaf, "DiscordNotifier", _NullNotifier)


def test_daily_report_solution_runs_and_terminates(tmp_path, monkeypatch):
    moisture_db = str(tmp_path / "moisture.sqlite")
    cimis_db = str(tmp_path / "cimis.sqlite")
    _seed_minimal(moisture_db, cimis_db)
    _patch_notifier(monkeypatch)

    op_list = use_template(
        "project.farm_soil.solutions.chain_tree.daily_report",
        kb_name="farm_soil_daily_report",
        moisture_db_path=moisture_db,
        cimis_db_path=cimis_db,
        webhook_url="https://example.invalid/wh",
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

    # Hard cap: if asm_terminate_system fails to fire, we want the test
    # to fail fast rather than spin.
    counter = {"n": 0}

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= 5:
            raise RuntimeError("solution did not terminate within 5 ticks")

    chain.engine["sleep"] = capped_sleep
    chain.run(starting=["farm_soil_daily_report"])

    body = "\n".join(log)
    # All four composite leaves ran.
    assert "sqlite_query[daily_query_moisture_farm_soil_daily_report]:" in body
    assert "sqlite_query[daily_query_eto_farm_soil_daily_report]:" in body
    assert "format_daily_report[daily_format_farm_soil_daily_report]:" in body
    assert "discord_notify[daily_notify_farm_soil_daily_report]: sent ok" in body

    # Notifier was constructed and would have posted. Empty-DBs branch
    # of the formatter renders "(no data)" twice — surfaces the gap.
    assert len(_NullNotifier.instances) == 1
    assert "cfl_engine_flag" not in body
    assert chain.engine["cfl_engine_flag"] is False, (
        "asm_terminate_system did not clear cfl_engine_flag"
    )
