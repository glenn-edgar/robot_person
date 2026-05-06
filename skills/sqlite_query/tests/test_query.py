"""Unit tests for SqliteQuery.

Covers each branch of the (rows, err) return contract:
  - successful SELECT with positional and named params
  - empty result vs. error result distinction
  - missing-DB error path
  - read-only mode rejects writes
  - empty SQL rejected before connecting
"""

from __future__ import annotations

import sqlite3

import pytest

from skills.sqlite_query.main import SqliteQuery


@pytest.fixture
def populated_db(tmp_path):
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE readings (
            device TEXT NOT NULL,
            ts     TEXT NOT NULL,
            value  REAL NOT NULL
        );
        INSERT INTO readings VALUES ('a', '2026-05-01T00:00:00Z', 0.10);
        INSERT INTO readings VALUES ('a', '2026-05-02T00:00:00Z', 0.20);
        INSERT INTO readings VALUES ('b', '2026-05-01T00:00:00Z', 0.30);
        """
    )
    conn.commit()
    conn.close()
    return str(db)


def test_select_positional_params(populated_db):
    q = SqliteQuery(populated_db)
    rows, err = q.query(
        "SELECT device, value FROM readings WHERE device = ? ORDER BY ts",
        ("a",),
    )
    assert err is None
    assert rows == [
        {"device": "a", "value": 0.10},
        {"device": "a", "value": 0.20},
    ]


def test_select_named_params(populated_db):
    q = SqliteQuery(populated_db)
    rows, err = q.query(
        "SELECT COUNT(*) AS n FROM readings WHERE value >= :lo",
        {"lo": 0.20},
    )
    assert err is None
    assert rows == [{"n": 2}]


def test_empty_result_is_empty_list_not_error(populated_db):
    q = SqliteQuery(populated_db)
    rows, err = q.query(
        "SELECT * FROM readings WHERE device = ?", ("nonexistent",)
    )
    assert err is None
    assert rows == []


def test_missing_db_returns_error(tmp_path):
    q = SqliteQuery(str(tmp_path / "does_not_exist.sqlite"))
    rows, err = q.query("SELECT 1")
    assert rows is None
    assert err is not None
    assert "unable to open" in err.lower() or "no such" in err.lower()


def test_read_only_rejects_write(populated_db):
    q = SqliteQuery(populated_db)
    rows, err = q.query("DELETE FROM readings")
    assert rows is None
    assert err is not None
    assert "readonly" in err.lower()


def test_empty_sql_rejected(populated_db):
    q = SqliteQuery(populated_db)
    rows, err = q.query("   ")
    assert rows is None
    assert err is not None


def test_syntax_error_returns_error(populated_db):
    q = SqliteQuery(populated_db)
    rows, err = q.query("SLECT * FROM readings")
    assert rows is None
    assert err is not None


def test_logger_called(populated_db):
    captured = []
    q = SqliteQuery(populated_db, logger=captured.append)
    q.query("SELECT 1 AS one")
    assert any("SELECT 1" in line for line in captured)
    assert any("returned 1 row" in line for line in captured)


def test_db_path_required():
    with pytest.raises(ValueError):
        SqliteQuery("")
