"""DB schema + INSERT OR IGNORE smoke tests for cimis."""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_skill = os.path.dirname(_here)
_skills_root = os.path.dirname(_skill)
_repo = os.path.dirname(_skills_root)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from skills.cimis.db import insert_record, open_or_create  # noqa: E402
from skills.cimis.decoder import CimisRecord  # noqa: E402


def _rec(item: str = "DayAsceEto", value: float = 0.20) -> CimisRecord:
    return CimisRecord(
        target_kind="station",
        target="237",
        date="2026-05-04",
        item=item,
        value=value,
        unit="Inches",
        qc="Y",
    )


def test_first_insert_writes_one_row():
    conn = open_or_create(":memory:")
    assert insert_record(conn, _rec()) == 1
    assert conn.execute("SELECT COUNT(*) FROM cimis_eto").fetchone()[0] == 1


def test_reinsert_is_idempotent():
    conn = open_or_create(":memory:")
    insert_record(conn, _rec())
    assert insert_record(conn, _rec()) == 0
    assert conn.execute("SELECT COUNT(*) FROM cimis_eto").fetchone()[0] == 1


def test_different_items_coexist():
    conn = open_or_create(":memory:")
    insert_record(conn, _rec(item="DayAsceEto", value=0.20))
    insert_record(conn, _rec(item="DayAirTmpMax", value=78.4))
    rows = conn.execute(
        "SELECT item, value FROM cimis_eto ORDER BY item"
    ).fetchall()
    assert rows == [("DayAirTmpMax", 78.4), ("DayAsceEto", 0.20)]


def test_skip_provisional_filters_qc_a(tmp_path):
    """CimisFetcher with skip_provisional=True (default) must not insert
    rows where qc='A' (CIMIS' partial-day provisional flag)."""
    from skills.cimis.api import CimisClient
    from skills.cimis.main import CimisFetcher

    fake_response = (
        '{"Data":{"Providers":[{"Name":"cimis","Type":"station","Records":['
        '{"Date":"2026-05-04","Station":"237","DayAsceEto":'
        '{"Value":"0.11","Qc":" ","Unit":"(in)"}},'
        '{"Date":"2026-05-05","Station":"237","DayAsceEto":'
        '{"Value":"0.21","Qc":"A","Unit":"(in)"}}'
        ']}]}}'
    )

    class _StubClient(CimisClient):
        def fetch(self, **kw):
            return fake_response, True, None

    db = str(tmp_path / "skip_provisional.sqlite")
    f = CimisFetcher(
        db_path=db, app_key="x",
        station_targets="237", spatial_targets="",
        data_items="day-asce-eto", lookback_days=2,
    )
    f.client = _StubClient(app_key="x")
    rows = f.tick()
    assert rows == 1   # only the qc=' ' row counts
    import sqlite3
    conn = sqlite3.connect(db)
    dates = sorted(r[0] for r in conn.execute(
        "SELECT date FROM cimis_eto").fetchall())
    conn.close()
    assert dates == ["2026-05-04"]


def test_keep_provisional_when_flag_off(tmp_path):
    """With skip_provisional=False, qc='A' rows are inserted alongside finalised ones."""
    from skills.cimis.api import CimisClient
    from skills.cimis.main import CimisFetcher

    fake_response = (
        '{"Data":{"Providers":[{"Name":"cimis","Type":"station","Records":['
        '{"Date":"2026-05-05","Station":"237","DayAsceEto":'
        '{"Value":"0.21","Qc":"A","Unit":"(in)"}}'
        ']}]}}'
    )

    class _StubClient(CimisClient):
        def fetch(self, **kw):
            return fake_response, True, None

    db = str(tmp_path / "keep_provisional.sqlite")
    f = CimisFetcher(
        db_path=db, app_key="x",
        station_targets="237", spatial_targets="",
        data_items="day-asce-eto", lookback_days=1,
        skip_provisional=False,
    )
    f.client = _StubClient(app_key="x")
    assert f.tick() == 1


def test_wrap_spatial():
    from skills.cimis.main import _wrap_spatial
    # Coordinate pairs get wrapped (recognised by '.')
    assert _wrap_spatial("33.578,-117.299") == "(33.578,-117.299)"
    assert _wrap_spatial("(33.578,-117.299)") == "(33.578,-117.299)"
    assert _wrap_spatial("33.578,-117.299;34.0,-118.0") == "(33.578,-117.299),(34.0,-118.0)"
    # Zip codes pass through (no decimal point)
    assert _wrap_spatial("92590") == "92590"
    assert _wrap_spatial("92590,92591") == "92590,92591"
    # Empty stays empty
    assert _wrap_spatial("") == ""


def test_station_and_spatial_coexist():
    conn = open_or_create(":memory:")
    insert_record(conn, _rec())
    insert_record(conn, CimisRecord(
        target_kind="spatial", target="33.5785,-117.2994",
        date="2026-05-04", item="DayAsceEto",
        value=0.18, unit="Inches", qc="Y",
    ))
    kinds = sorted(r[0] for r in conn.execute(
        "SELECT DISTINCT target_kind FROM cimis_eto"
    ).fetchall())
    assert kinds == ["spatial", "station"]
