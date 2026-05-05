"""Smoke test for farm_soil.report.format_report.

Pre-populates an in-memory SQLite via the lorwan_moisture skill's db
helpers, then asserts the report contains every device sorted by
device_id, the right measurement labels, and the RF stats line.

No network, no template machinery — pure data-side validation.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_robot = os.path.dirname(_here)
_robots_root = os.path.dirname(_robot)
_repo = os.path.dirname(_robots_root)
for p in (_repo, _robots_root):
    if p not in sys.path:
        sys.path.insert(0, p)

from datetime import datetime, timedelta, timezone  # noqa: E402

from farm_soil.report import format_report  # noqa: E402
from skills.lorwan_moisture.db import insert_uplink, open_or_create  # noqa: E402
from skills.lorwan_moisture.decoder import (  # noqa: E402
    GatewayInfo,
    Measurement,
    Uplink,
)


def _now_minus(hours: int) -> str:
    return (
        datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uplink(device_id: str, hours_ago: int, moisture: float, rssi: int, snr: float,
            gws: int = 1) -> Uplink:
    return Uplink(
        device_id=device_id,
        received_at=_now_minus(hours_ago),
        f_cnt=hours_ago,
        frm_payload_b64=None,
        measurements=[
            Measurement(4108, moisture),
            Measurement(4102, 19.5),
            Measurement(4103, 1.234),
        ],
        gateway=GatewayInfo(
            gateway_id="gw-01", rssi=rssi, channel_rssi=rssi, snr=snr,
            frequency="904300000", spreading_factor=7, bandwidth=125000,
            coding_rate="4/5", airtime_s=0.061696, gateway_count=gws,
        ),
    )


def test_report_sorted_and_filtered(tmp_path):
    db_path = str(tmp_path / "report.sqlite")
    conn = open_or_create(db_path)
    # Two devices, two uplinks each, all within 36h
    insert_uplink(conn, _uplink("lacima1d", hours_ago=2,  moisture=0.21, rssi=-72, snr=10.5, gws=2))
    insert_uplink(conn, _uplink("lacima1d", hours_ago=20, moisture=0.18, rssi=-78, snr=8.5, gws=1))
    insert_uplink(conn, _uplink("lacima1c", hours_ago=1,  moisture=0.30, rssi=-70, snr=11.0, gws=3))
    insert_uplink(conn, _uplink("lacima1c", hours_ago=30, moisture=0.27, rssi=-80, snr=7.5, gws=2))
    # Older than 36h — must NOT appear in the report
    insert_uplink(conn, _uplink("lacima1c", hours_ago=48, moisture=0.99, rssi=-50, snr=15.0))
    conn.close()

    lines = format_report(db_path, lookback_hours=36)
    body = "\n".join(lines)

    # Header present
    assert "farm_soil moisture/RF report (last 36h)" in body

    # Both devices present, lacima1c first (alphabetical)
    c_idx = body.index("--- lacima1c")
    d_idx = body.index("--- lacima1d")
    assert c_idx < d_idx

    # Within-window uplinks counted (not the 48h-ago row)
    assert "--- lacima1c (2 uplinks) ---" in body
    assert "--- lacima1d (2 uplinks) ---" in body

    # Time-series header present once per device
    assert body.count("time (UTC)") == 2

    # All four kept rows show their moisture values (ordered most-recent first)
    assert "0.300" in body and "0.270" in body
    assert "0.210" in body and "0.180" in body
    # The 48h-ago row must NOT appear
    assert "0.990" not in body

    # gws column populated; lacima1c rows are gws=3 (1h ago) and gws=2 (30h ago)
    c_block = body[c_idx:d_idx]
    assert "gws" in c_block
    rows_after_header = c_block.split("\n")[2:4]
    assert "0.300" in rows_after_header[0] and rows_after_header[0].rstrip().endswith("gw-01")
    assert "0.270" in rows_after_header[1]


def test_report_empty_db_message(tmp_path):
    db_path = str(tmp_path / "empty.sqlite")
    open_or_create(db_path).close()
    lines = format_report(db_path, lookback_hours=36)
    assert any("(no data in window)" in line for line in lines)
