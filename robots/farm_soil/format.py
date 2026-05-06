"""farm_soil daily-report formatter — pure Python, engine-agnostic.

`format_daily_report(moisture_rows, eto_rows)` consumes the two
list-of-dicts result sets produced by the upstream `sqlite_query`
leaves and returns a single string suitable for posting to Discord
(short, fixed-width columns, well under the 2000-char webhook limit).

Kept out of the chain_tree leaf so the format logic is unit-testable
against synthetic row lists without booting the engine.

Expected row shapes:

  moisture_rows: one dict per device, e.g.
    {"device_id": "lacima1c", "latest_value": 0.30,
     "latest_ts": "2026-05-06T08:00:00Z", "uplinks_in_window": 3}

  eto_rows: one dict per day, most-recent first, e.g.
    {"date": "2026-05-05", "value": 0.110, "unit": "(in)"}

Empty lists are rendered as "(no data)" — surface the gap rather than
producing a misleadingly-short message.
"""

from __future__ import annotations

from datetime import date


_MOISTURE_HEADER = "Moisture (per-device latest):"
_ETO_HEADER = "ETo (CIMIS):"


def format_daily_report(
    moisture_rows: list[dict],
    eto_rows: list[dict],
    *,
    report_date: date | None = None,
) -> str:
    """Build the daily-report message string.

    `report_date` is the date stamp printed in the header. Default is
    `date.today()`; passing it explicitly keeps tests deterministic.
    """
    today = (report_date or date.today()).isoformat()
    lines: list[str] = [f"=== farm_soil daily report — {today} ===", ""]

    lines.append(_MOISTURE_HEADER)
    if not moisture_rows:
        lines.append("  (no data)")
    else:
        for row in moisture_rows:
            device = row.get("device_id", "?")
            value = row.get("latest_value")
            ts = row.get("latest_ts", "")
            count = row.get("uplinks_in_window", 0)
            value_s = "?" if value is None else f"{value:0.3f}"
            ts_short = _short_time(ts) if ts else "?"
            lines.append(
                f"  {device:<10} {value_s:>6}  ts={ts_short}  "
                f"({count} uplinks)"
            )
    lines.append("")

    lines.append(_ETO_HEADER)
    if not eto_rows:
        lines.append("  (no data)")
    else:
        for row in eto_rows:
            d = row.get("date", "?")
            value = row.get("value")
            unit = row.get("unit", "")
            value_s = "?" if value is None else f"{value:0.3f}"
            lines.append(f"  {d}  {value_s:>6} {unit}".rstrip())

    return "\n".join(lines)


def _short_time(ts: str) -> str:
    """Trim subseconds: '2026-05-05T16:48:03.851Z' -> '2026-05-05T16:48:03Z'."""
    if "." in ts:
        head, _, _ = ts.partition(".")
        return head + "Z"
    return ts
