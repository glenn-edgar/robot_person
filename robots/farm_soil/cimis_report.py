"""farm_soil CIMIS report — pure Python, engine-agnostic.

`format_report(db_path, lookback_days)` opens the CIMIS SQLite DB
written by `skills.cimis` and returns a list of lines: per data-item,
a per-day table comparing each station target against the spatial
target side-by-side.

Kept out of the chain_tree leaf template so the report logic is
unit-testable against a pre-populated DB without booting the engine.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from skills.cimis.db import open_or_create


def format_report(db_path: str, lookback_days: int) -> list[str]:
    """Build a per-item, per-day table sorted by date desc.

    For each `item` (e.g. DayEto), shows one row per date with one
    column per (target_kind, target) pair found in the window. Stations
    list first, spatial second; multiple stations are sorted by id.
    """
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    conn = open_or_create(db_path)
    try:
        lines: list[str] = [
            f"=== farm_soil CIMIS report (last {lookback_days}d) ===",
            f"cutoff date: {cutoff}",
            "",
        ]
        items = [r[0] for r in conn.execute(
            "SELECT DISTINCT item FROM cimis_eto WHERE date >= ? ORDER BY item",
            (cutoff,),
        ).fetchall()]
        if not items:
            lines.append("(no data in window)")
            return lines

        for item in items:
            lines.extend(_item_block(conn, item, cutoff))
            lines.append("")
        return lines
    finally:
        conn.close()


def _item_block(conn: sqlite3.Connection, item: str, cutoff: str) -> list[str]:
    """One table per measurement item."""
    columns = conn.execute(
        "SELECT DISTINCT target_kind, target FROM cimis_eto "
        "WHERE item = ? AND date >= ? "
        "ORDER BY target_kind = 'station' DESC, target",
        (item, cutoff),
    ).fetchall()
    if not columns:
        return [f"--- {item}: no data ---"]

    out: list[str] = [f"--- {item} ---"]
    unit_row = conn.execute(
        "SELECT unit FROM cimis_eto WHERE item = ? LIMIT 1", (item,)
    ).fetchone()
    unit = unit_row[0] if unit_row and unit_row[0] else ""

    header_cells = [_col_label(k, t) for k, t in columns]
    out.append("  " + "date        " + " ".join(f"{h:>14}" for h in header_cells))

    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM cimis_eto "
        "WHERE item = ? AND date >= ? ORDER BY date DESC",
        (item, cutoff),
    ).fetchall()]
    for d in dates:
        cells = []
        for kind, target in columns:
            row = conn.execute(
                "SELECT value, qc FROM cimis_eto "
                "WHERE target_kind = ? AND target = ? AND date = ? AND item = ? "
                "LIMIT 1",
                (kind, target, d, item),
            ).fetchone()
            if row is None:
                cells.append(f"{'-':>14}")
            else:
                v, qc = row
                if v is None:
                    cells.append(f"{'(qc=' + (qc or '?') + ')':>14}")
                else:
                    cells.append(f"{v:>9.3f} {qc or '':<3}")
        out.append("  " + f"{d:<12}" + " ".join(cells))

    if unit:
        out.append(f"  (unit: {unit})")
    return out


def _col_label(kind: str, target: str) -> str:
    """Compact column label per (target_kind, target)."""
    if kind == "station":
        return f"st-{target}"
    if kind == "spatial":
        # 33.578,-117.299 -> sp(33.6,-117.3) — keep narrow
        try:
            lat, lng = target.split(",")
            return f"sp({float(lat):.2f},{float(lng):.2f})"
        except Exception:
            return f"sp({target})"
    return f"{kind}:{target}"
