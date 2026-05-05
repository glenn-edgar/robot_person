"""Read-side helper: is a (target, date, item) row in the CIMIS DB?

Pure Python — no engine, no template-language. Built so the upper-
level chain_tree composition can wrap it as an `add_boolean(...)` fn:

    from skills.cimis.check import is_data_present, california_yesterday

    def cimis_yesterday_present(handle, node):
        return is_data_present(
            db_path=node["data"]["db_path"],
            target_kind="station",
            target="237",
            date=california_yesterday(),
            item="DayAsceEto",
            require_finalised=True,   # reject qc='A' provisional rows
        )

    chain.add_boolean("cimis_yesterday_present", cimis_yesterday_present)

`mark_link` then references "cimis_yesterday_present" to pass/fail a
`sequence_til_pass` retry loop.

The TZ choice (`America/Los_Angeles`) lives here, not in the skill or
the wrapper, because "yesterday" is a property of the data source's
reporting frame (CIMIS / California), not of the engine.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    _CA_TZ = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover — zoneinfo always present on 3.9+
    _CA_TZ = None


def california_yesterday() -> str:
    """Yesterday's date in CIMIS' reporting timezone (PST/PDT) as YYYY-MM-DD."""
    from datetime import datetime
    if _CA_TZ is None:
        today = date.today()
    else:
        today = datetime.now(tz=_CA_TZ).date()
    return (today - timedelta(days=1)).isoformat()


def is_data_present(
    db_path: str,
    *,
    target_kind: str,
    target: str,
    date: str,
    item: str = "DayAsceEto",
    require_finalised: bool = False,
) -> bool:
    """Return True iff the cimis_eto table has a row matching all four keys.

    Treats a missing DB / missing table as False (no data yet) rather
    than raising — the upper-level retry sequence reads this as "keep
    trying", which is the right behavior at startup before the first
    fetch has built the schema.

    `require_finalised=True` additionally requires:
      - value IS NOT NULL
      - qc != 'A'  (CIMIS' "Active/provisional" flag — present during
                    the day before CIMIS finalises overnight)
    Use this for irrigation-grade predicates: "did *yesterday's* ETo
    become a finalised number?". A row that exists with qc='A' counts
    as "still computing", so the upper-level retry keeps polling.
    """
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return False
    try:
        sql = (
            "SELECT 1 FROM cimis_eto "
            "WHERE target_kind = ? AND target = ? AND date = ? AND item = ? "
        )
        params: tuple = (target_kind, target, date, item)
        if require_finalised:
            sql += "AND value IS NOT NULL AND (qc IS NULL OR qc != 'A') "
        sql += "LIMIT 1"
        try:
            row = conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None
    finally:
        conn.close()
