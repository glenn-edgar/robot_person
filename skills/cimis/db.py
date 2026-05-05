"""SQLite schema + INSERT OR IGNORE writer for CIMIS records.

One table — schema is idempotent, so calling `open_or_create` twice
in a row is a no-op the second time.

  cimis_eto(target_kind, target, date, item, value, unit, qc)
    PK (target_kind, target, date, item)

`target_kind` is 'station' or 'spatial'; `target` is the station id
as a string ('237') or the coordinate pair ('33.5785,-117.2994') the
record was queried at; `item` is CIMIS' PascalCase key
('DayAsceEto', 'DayAirTmpMax', etc.).
"""

from __future__ import annotations

import sqlite3

from .decoder import CimisRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS cimis_eto (
    target_kind  TEXT NOT NULL,
    target       TEXT NOT NULL,
    date         TEXT NOT NULL,
    item         TEXT NOT NULL,
    value        REAL,
    unit         TEXT,
    qc           TEXT,
    PRIMARY KEY (target_kind, target, date, item)
);
"""


def open_or_create(db_path: str) -> sqlite3.Connection:
    """Open `db_path`, ensure schema, return the connection."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_record(conn: sqlite3.Connection, rec: CimisRecord) -> int:
    """Insert one CimisRecord. Returns 1 if added, 0 if already present."""
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO cimis_eto "
        "(target_kind, target, date, item, value, unit, qc) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rec.target_kind, rec.target, rec.date, rec.item,
         rec.value, rec.unit, rec.qc),
    )
    conn.commit()
    return cur.rowcount
