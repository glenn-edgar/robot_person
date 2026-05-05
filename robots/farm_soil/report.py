"""farm_soil moisture/RF report — pure Python, engine-agnostic.

`format_report(db_path, lookback_hours)` opens the SQLite DB written
by `skills.lorwan_moisture` and returns a list of lines: per device,
sorted by `device_id`, a time-series table with one row per uplink
showing the three measurements plus link stats from the strongest
gateway and the total gateway count.

Kept out of the chain_tree leaf template so the report logic is
unit-testable against a pre-populated DB without booting the engine.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from skills.lorwan_moisture.db import open_or_create


_M_MOISTURE = 4108
_M_SOIL_TEMP = 4102
_M_SOIL_EC = 4103


def format_report(db_path: str, lookback_hours: int) -> list[str]:
    """Build a per-device time-series, sorted by device_id."""
    cutoff = (
        datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = open_or_create(db_path)
    try:
        lines: list[str] = [
            f"=== farm_soil moisture/RF report (last {lookback_hours}h) ===",
            f"cutoff (UTC): {cutoff}",
            "",
        ]
        device_counts = conn.execute(
            "SELECT device_id, COUNT(DISTINCT received_at) "
            "FROM moisture WHERE received_at > ? "
            "GROUP BY device_id ORDER BY device_id",
            (cutoff,),
        ).fetchall()
        if not device_counts:
            lines.append("(no data in window)")
            return lines
        for device_id, count in device_counts:
            lines.append(f"--- {device_id} ({count} uplinks) ---")
            lines.extend(_device_block(conn, device_id, cutoff))
            lines.append("")
        return lines
    finally:
        conn.close()


def _device_block(conn: sqlite3.Connection, device_id: str, cutoff: str) -> list[str]:
    measurements_by_time: dict[str, dict[int, float]] = {}
    for at, mid, val in conn.execute(
        "SELECT received_at, measurement_id, value FROM moisture "
        "WHERE device_id = ? AND received_at > ? "
        "ORDER BY received_at DESC",
        (device_id, cutoff),
    ):
        measurements_by_time.setdefault(at, {})[mid] = val

    link_by_time: dict[str, tuple] = {}
    for row in conn.execute(
        "SELECT received_at, rssi, snr, gateway_id, gateway_count, "
        "       frequency, spreading_factor, bandwidth, coding_rate, "
        "       battery_present, battery_value "
        "FROM link WHERE device_id = ? AND received_at > ? "
        "ORDER BY received_at DESC",
        (device_id, cutoff),
    ):
        link_by_time[row[0]] = row[1:]

    out: list[str] = [
        f"  {'time (UTC)':<20} "
        f"{'moist':>7} {'temp':>6} {'ec':>6}  "
        f"{'rssi':>5} {'snr':>6} {'gws':>3}  "
        f"{'freq':>7} {'sf':>2} {'bw':>4} {'cr':>4} {'bat':>4}  gateway",
    ]
    for at in sorted(measurements_by_time, reverse=True):
        m = measurements_by_time[at]
        link = link_by_time.get(at, (None,) * 10)
        rssi, snr, gw, gws, freq, sf, bw, cr, bat_p, bat_v = link
        out.append(
            f"  {_short_time(at):<20} "
            f"{_fmt_num(m.get(_M_MOISTURE), 7, 3)} "
            f"{_fmt_num(m.get(_M_SOIL_TEMP), 6, 1)} "
            f"{_fmt_num(m.get(_M_SOIL_EC), 6, 1)}  "
            f"{_fmt_int(rssi, 5)} "
            f"{_fmt_num(snr, 6, 1)} "
            f"{_fmt_int(gws, 3)}  "
            f"{_fmt_freq_mhz(freq, 7)} "
            f"{_fmt_int(sf, 2)} "
            f"{_fmt_bw_khz(bw, 4)} "
            f"{_fmt_str(cr, 4)} "
            f"{_fmt_battery(bat_p, bat_v, 4)}  "
            f"{gw or '?'}"
        )
    return out


def _short_time(at: str) -> str:
    """Trim subseconds: '2026-05-05T16:48:03.851Z' -> '2026-05-05T16:48:03Z'."""
    if "." in at:
        head, _, _ = at.partition(".")
        return head + "Z"
    return at


def _fmt_num(v, width: int, prec: int) -> str:
    if v is None:
        return f"{'?':>{width}}"
    return f"{v:>{width}.{prec}f}"


def _fmt_int(v, width: int) -> str:
    if v is None:
        return f"{'?':>{width}}"
    return f"{v:>{width}}"


def _fmt_str(v, width: int) -> str:
    if v is None or v == "":
        return f"{'?':>{width}}"
    return f"{str(v):>{width}}"


def _fmt_freq_mhz(freq, width: int) -> str:
    """TTN reports frequency as a stringified Hz integer; show MHz."""
    if freq is None or freq == "":
        return f"{'?':>{width}}"
    try:
        mhz = int(freq) / 1_000_000
    except (TypeError, ValueError):
        return f"{'?':>{width}}"
    return f"{mhz:>{width}.1f}"


def _fmt_bw_khz(bw, width: int) -> str:
    """Bandwidth comes in Hz (e.g. 125000); show kHz."""
    if bw is None:
        return f"{'?':>{width}}"
    return f"{bw // 1000:>{width}}"


def _fmt_battery(present, value, width: int) -> str:
    """Battery: integer percent if present + value known, '?' otherwise."""
    if not present:
        return f"{'-':>{width}}"
    if value is None:
        return f"{'y':>{width}}"
    return f"{value:>{width}}"
