"""Pure-function tests for farm_soil.format.format_daily_report.

No engine, no template machinery — synthetic row lists in, formatted
string out. Covers the populated path, the empty-on-each-side branches,
and the both-empty case (so the message still surfaces the gap).
"""

from __future__ import annotations

from datetime import date

from farm_soil.format import format_daily_report


_FIXED_DATE = date(2026, 5, 6)


def test_populated_report_renders_both_sections():
    moisture_rows = [
        {
            "device_id": "lacima1c",
            "latest_value": 0.300,
            "latest_ts": "2026-05-06T08:00:00Z",
            "uplinks_in_window": 3,
        },
        {
            "device_id": "lacima1d",
            "latest_value": 0.180,
            "latest_ts": "2026-05-06T07:00:00Z",
            "uplinks_in_window": 2,
        },
    ]
    eto_rows = [
        {"date": "2026-05-05", "value": 0.110, "unit": "(in)"},
        {"date": "2026-05-04", "value": 0.105, "unit": "(in)"},
    ]
    out = format_daily_report(moisture_rows, eto_rows, report_date=_FIXED_DATE)

    assert "=== farm_soil daily report — 2026-05-06 ===" in out
    assert "Moisture (per-device latest):" in out
    # Both devices show their values + uplink counts.
    assert "lacima1c" in out and "0.300" in out and "(3 uplinks)" in out
    assert "lacima1d" in out and "0.180" in out and "(2 uplinks)" in out
    assert "ETo (CIMIS):" in out
    assert "2026-05-05" in out and "0.110" in out and "(in)" in out
    assert "(no data)" not in out


def test_empty_moisture_renders_no_data_branch():
    eto_rows = [{"date": "2026-05-05", "value": 0.110, "unit": "(in)"}]
    out = format_daily_report([], eto_rows, report_date=_FIXED_DATE)
    # Moisture section says no data; ETo still rendered.
    moist_idx = out.index("Moisture (per-device latest):")
    eto_idx = out.index("ETo (CIMIS):")
    assert "(no data)" in out[moist_idx:eto_idx]
    assert "0.110" in out[eto_idx:]


def test_empty_eto_renders_no_data_branch():
    moisture_rows = [
        {
            "device_id": "lacima1c",
            "latest_value": 0.30,
            "latest_ts": "2026-05-06T08:00:00Z",
            "uplinks_in_window": 1,
        }
    ]
    out = format_daily_report(moisture_rows, [], report_date=_FIXED_DATE)
    moist_idx = out.index("Moisture (per-device latest):")
    eto_idx = out.index("ETo (CIMIS):")
    assert "lacima1c" in out[moist_idx:eto_idx]
    assert "(no data)" in out[eto_idx:]


def test_both_empty_still_surfaces_two_no_data_lines():
    out = format_daily_report([], [], report_date=_FIXED_DATE)
    assert out.count("(no data)") == 2


def test_subsecond_timestamp_trimmed():
    rows = [
        {
            "device_id": "lacima1c",
            "latest_value": 0.30,
            "latest_ts": "2026-05-06T08:00:00.851Z",
            "uplinks_in_window": 1,
        }
    ]
    out = format_daily_report(rows, [], report_date=_FIXED_DATE)
    assert "2026-05-06T08:00:00Z" in out
    assert ".851" not in out


def test_message_under_discord_2000_char_limit_for_typical_input():
    # Five devices × five days of ETo — roughly the worst case we expect
    # for a single farm. Confirms typical output stays well under the
    # 2000-char webhook ceiling.
    moisture = [
        {
            "device_id": f"sensor_{i}",
            "latest_value": 0.20 + 0.01 * i,
            "latest_ts": "2026-05-06T08:00:00Z",
            "uplinks_in_window": 4,
        }
        for i in range(5)
    ]
    eto = [
        {"date": f"2026-05-{5 - i:02d}", "value": 0.10 + 0.005 * i, "unit": "(in)"}
        for i in range(5)
    ]
    out = format_daily_report(moisture, eto, report_date=_FIXED_DATE)
    assert len(out) < 2000
