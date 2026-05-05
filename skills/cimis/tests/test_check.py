"""Tests for skills.cimis.check.is_data_present."""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_skill = os.path.dirname(_here)
_skills_root = os.path.dirname(_skill)
_repo = os.path.dirname(_skills_root)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from skills.cimis.check import california_yesterday, is_data_present  # noqa: E402
from skills.cimis.db import insert_record, open_or_create  # noqa: E402
from skills.cimis.decoder import CimisRecord  # noqa: E402


def test_present_after_insert(tmp_path):
    db = str(tmp_path / "cimis.sqlite")
    conn = open_or_create(db)
    insert_record(conn, CimisRecord(
        target_kind="station", target="237",
        date="2026-05-04", item="DayEto",
        value=0.20, unit="Inches", qc="Y",
    ))
    conn.close()
    assert is_data_present(
        db, target_kind="station", target="237",
        date="2026-05-04", item="DayEto",
    ) is True


def test_absent_for_unknown_date(tmp_path):
    db = str(tmp_path / "cimis.sqlite")
    open_or_create(db).close()
    assert is_data_present(
        db, target_kind="station", target="237",
        date="2026-05-04", item="DayEto",
    ) is False


def test_absent_for_missing_db(tmp_path):
    # No file exists at this path; helper returns False, doesn't raise.
    assert is_data_present(
        str(tmp_path / "nope.sqlite"),
        target_kind="station", target="237",
        date="2026-05-04", item="DayEto",
    ) is False


def test_finalised_filter_excludes_provisional(tmp_path):
    db = str(tmp_path / "cimis.sqlite")
    conn = open_or_create(db)
    insert_record(conn, CimisRecord(
        target_kind="station", target="237",
        date="2026-05-05", item="DayAsceEto",
        value=0.21, unit="(in)", qc="A",   # provisional
    ))
    insert_record(conn, CimisRecord(
        target_kind="station", target="237",
        date="2026-05-04", item="DayAsceEto",
        value=0.11, unit="(in)", qc=" ",   # finalised
    ))
    conn.close()
    # Default mode: any row counts as "present"
    assert is_data_present(db, target_kind="station", target="237",
                            date="2026-05-05", item="DayAsceEto") is True
    # Finalised mode: provisional 'A' is rejected
    assert is_data_present(db, target_kind="station", target="237",
                            date="2026-05-05", item="DayAsceEto",
                            require_finalised=True) is False
    # Finalised mode: yesterday's blank-qc row is accepted
    assert is_data_present(db, target_kind="station", target="237",
                            date="2026-05-04", item="DayAsceEto",
                            require_finalised=True) is True


def test_finalised_filter_rejects_null_value(tmp_path):
    db = str(tmp_path / "cimis.sqlite")
    conn = open_or_create(db)
    insert_record(conn, CimisRecord(
        target_kind="station", target="237",
        date="2026-05-04", item="DayAsceEto",
        value=None, unit="(in)", qc="M",
    ))
    conn.close()
    assert is_data_present(db, target_kind="station", target="237",
                            date="2026-05-04", item="DayAsceEto") is True
    assert is_data_present(db, target_kind="station", target="237",
                            date="2026-05-04", item="DayAsceEto",
                            require_finalised=True) is False


def test_california_yesterday_format():
    """Returns a YYYY-MM-DD-shaped string."""
    s = california_yesterday()
    assert len(s) == 10 and s[4] == "-" and s[7] == "-"
    int(s[:4])  # parses
    int(s[5:7])
    int(s[8:])
