"""skills.sqlite_query — read-only parameterised SQL against a SQLite DB.

Per the skills convention (skills/README.md): one class + __main__ test
driver. Engine-agnostic — no chain_tree / s_engine imports.

Public class:
  SqliteQuery — `__init__(db_path, ...)` + `query(sql, params=())`
                returning `(rows | None, error_msg | None)`.

The atomic read-side counterpart to the fetch skills (lorwan_moisture,
cimis). Those skills own writing to their respective DBs; this skill
owns reading from any of them. The shape is deliberately generic —
caller passes the SQL, this skill executes and returns rows.

Connections open in read-only URI mode (`mode=ro`) so a stray
INSERT/UPDATE/DELETE in the SQL is rejected by the driver. This skill
is the read-side counterpart to fetch skills; writes belong to the
fetch skills (or a future dedicated writer skill), never here.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from typing import Any, Callable, Optional, Sequence, Union


ParamsType = Union[Sequence[Any], dict[str, Any]]


class SqliteQuery:
    """Run a parameterised SELECT against a SQLite DB, return list-of-dicts.

    One instance is bound to one `db_path`. Composing across multiple
    DBs (the daily-report case — moisture DB + CIMIS DB) is done at the
    sub-tree level with two SqliteQuery leaves, not by configuring one
    instance with multiple paths. Matches the "skill = atomic" rule.

    Pass a `logger` callable (str -> None) to receive diagnostics:
    SQL preview, row count, error class.
    """

    def __init__(
        self,
        db_path: str,
        *,
        logger: Optional[Callable[[str], None]] = None,
    ):
        if not db_path:
            raise ValueError("SqliteQuery: db_path is required")
        self.db_path = db_path
        self.logger = logger or (lambda msg: None)

    def _connect(self) -> sqlite3.Connection:
        # URI form lets us request mode=ro. Driver rejects writes with
        # `attempt to write a readonly database`. File must exist —
        # read-only mode does not create it.
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def query(
        self,
        sql: str,
        params: ParamsType = (),
    ) -> tuple[Optional[list[dict]], Optional[str]]:
        """Execute `sql` with `params`, return (rows, error_msg).

        On success: `(list_of_dicts, None)` — empty list if the query
        returned no rows.
        On error: `(None, error_message)` — covers missing DB, SQL
        syntax errors, write attempts in read-only mode, etc.

        `params` is either a sequence (for `?` placeholders) or a
        mapping (for `:name` placeholders). The sqlite3 driver accepts
        both natively.
        """
        if not sql or not sql.strip():
            return None, "sql is empty"
        preview = " ".join(sql.split())[:100]
        self.logger(f"sqlite_query: {self.db_path} :: {preview}")
        conn = None
        try:
            conn = self._connect()
            cur = conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            self.logger(f"sqlite_query: returned {len(rows)} row(s)")
            return rows, None
        except sqlite3.OperationalError as e:
            msg = f"OperationalError: {e}"
            self.logger(f"sqlite_query: FAILED — {msg}")
            return None, msg
        except sqlite3.DatabaseError as e:
            msg = f"DatabaseError: {e}"
            self.logger(f"sqlite_query: FAILED — {msg}")
            return None, msg
        finally:
            if conn is not None:
                conn.close()


if __name__ == "__main__":
    # Self-contained smoke test: build a temp DB, populate three rows,
    # exercise positional + named params, then exit. No external
    # secrets needed (unlike the other input/output skills).
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    db = tmp.name
    try:
        seed = sqlite3.connect(db)
        seed.executescript(
            """
            CREATE TABLE moisture (
                device_id TEXT NOT NULL,
                ts        TEXT NOT NULL,
                value     REAL NOT NULL
            );
            INSERT INTO moisture VALUES ('lacima1c', '2026-05-05T08:00:00Z', 0.32);
            INSERT INTO moisture VALUES ('lacima1c', '2026-05-05T09:00:00Z', 0.31);
            INSERT INTO moisture VALUES ('lacima1d', '2026-05-05T08:00:00Z', 0.45);
            """
        )
        seed.commit()
        seed.close()

        q = SqliteQuery(db, logger=print)

        rows, err = q.query(
            "SELECT device_id, ts, value FROM moisture "
            "WHERE device_id = ? ORDER BY ts",
            ("lacima1c",),
        )
        print(f"positional: rows={rows} err={err}")
        assert err is None and len(rows) == 2, "positional params failed"

        rows, err = q.query(
            "SELECT COUNT(*) AS n FROM moisture WHERE value > :threshold",
            {"threshold": 0.4},
        )
        print(f"named:      rows={rows} err={err}")
        assert err is None and rows == [{"n": 1}], "named params failed"

        rows, err = q.query(
            "SELECT * FROM moisture WHERE device_id = ?", ("nonexistent",)
        )
        print(f"empty:      rows={rows} err={err}")
        assert err is None and rows == [], "empty result should be ([], None)"

        rows, err = q.query("INSERT INTO moisture VALUES ('x','y',0.0)")
        print(f"write-rej:  rows={rows} err={err}")
        assert rows is None and err and "readonly" in err.lower(), (
            "read-only mode should reject writes"
        )

        print("final: ok")
    finally:
        os.unlink(db)
