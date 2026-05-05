"""Smoke test for farm_soil.cimis_report.format_report.

Pre-populates a CIMIS DB with synthetic station + spatial readings
and asserts the report contains: header, per-item section,
per-date rows, both target columns, and stripped older-than-cutoff rows.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

_here = os.path.dirname(os.path.abspath(__file__))
_robot = os.path.dirname(_here)
_robots_root = os.path.dirname(_robot)
_repo = os.path.dirname(_robots_root)
for p in (_repo, _robots_root):
    if p not in sys.path:
        sys.path.insert(0, p)

from farm_soil.cimis_report import format_report  # noqa: E402
from skills.cimis.db import insert_record, open_or_create  # noqa: E402
from skills.cimis.decoder import CimisRecord  # noqa: E402


def _today_minus(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _eto(target_kind: str, target: str, days_ago: int, value: float) -> CimisRecord:
    return CimisRecord(
        target_kind=target_kind, target=target,
        date=_today_minus(days_ago), item="DayEto",
        value=value, unit="Inches", qc="Y",
    )


def test_report_header_and_targets(tmp_path):
    db = str(tmp_path / "cimis.sqlite")
    conn = open_or_create(db)
    insert_record(conn, _eto("station", "237", 1, 0.20))
    insert_record(conn, _eto("station", "237", 2, 0.22))
    insert_record(conn, _eto("spatial", "33.578,-117.299", 1, 0.18))
    insert_record(conn, _eto("spatial", "33.578,-117.299", 2, 0.21))
    # Older than 7d cutoff — must NOT appear:
    insert_record(conn, _eto("station", "237", 30, 0.99))
    conn.close()

    lines = format_report(db, lookback_days=7)
    body = "\n".join(lines)

    assert "farm_soil CIMIS report (last 7d)" in body
    assert "--- DayEto ---" in body
    assert "st-237" in body
    assert "sp(33.58,-117.30)" in body
    # The 30-days-ago row should not leak in
    assert "0.990" not in body
    # Each kept date appears once
    assert _today_minus(1) in body
    assert _today_minus(2) in body


def test_report_empty_db_message(tmp_path):
    db = str(tmp_path / "cimis_empty.sqlite")
    open_or_create(db).close()
    lines = format_report(db, lookback_days=7)
    assert any("(no data in window)" in line for line in lines)


def test_report_value_qc_columns(tmp_path):
    db = str(tmp_path / "cimis.sqlite")
    conn = open_or_create(db)
    insert_record(conn, _eto("station", "237", 1, 0.20))
    insert_record(conn, CimisRecord(
        target_kind="station", target="237",
        date=_today_minus(2), item="DayEto",
        value=None, unit="Inches", qc="M",   # missing data flagged as 'M'
    ))
    conn.close()

    lines = format_report(db, lookback_days=7)
    body = "\n".join(lines)
    assert "0.200" in body
    assert "qc=M" in body
