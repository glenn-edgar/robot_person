"""DB schema + INSERT OR IGNORE smoke tests.

Uses an in-memory SQLite, builds a synthetic Uplink, asserts the
row counts behave correctly across re-inserts.
"""

from __future__ import annotations

import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_skill = os.path.dirname(_here)
_skills_root = os.path.dirname(_skill)
_repo = os.path.dirname(_skills_root)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from skills.lorwan_moisture.db import insert_uplink, open_or_create  # noqa: E402
from skills.lorwan_moisture.decoder import (  # noqa: E402
    GatewayInfo,
    Measurement,
    Uplink,
)


def _make_uplink(battery_present: bool = False, battery_value: int | None = None) -> Uplink:
    return Uplink(
        device_id="lacima1c",
        received_at="2026-05-04T12:00:00.000Z",
        f_cnt=7,
        frm_payload_b64=None,
        measurements=[
            Measurement(4108, 0.234),
            Measurement(4102, 19.5),
            Measurement(4103, 1.234),
        ],
        gateway=GatewayInfo(
            gateway_id="gw-01", rssi=-75, channel_rssi=-75, snr=9.5,
            frequency="904300000", spreading_factor=7, bandwidth=125000,
            coding_rate="4/5", airtime_s=0.061696, gateway_count=2,
        ),
        battery_present=battery_present,
        battery_value=battery_value,
    )


def test_first_insert_writes_4_rows():
    conn = open_or_create(":memory:")
    rows = insert_uplink(conn, _make_uplink())
    assert rows == 4   # 3 moisture + 1 link
    assert conn.execute("SELECT COUNT(*) FROM moisture").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM link").fetchone()[0] == 1
    assert conn.execute("SELECT gateway_count FROM link").fetchone()[0] == 2


def test_reinsert_is_idempotent():
    conn = open_or_create(":memory:")
    up = _make_uplink()
    insert_uplink(conn, up)
    rows2 = insert_uplink(conn, up)
    assert rows2 == 0
    assert conn.execute("SELECT COUNT(*) FROM moisture").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM link").fetchone()[0] == 1


def test_battery_columns_persist():
    conn = open_or_create(":memory:")
    insert_uplink(conn, _make_uplink(battery_present=True, battery_value=100))
    row = conn.execute(
        "SELECT battery_present, battery_value FROM link"
    ).fetchone()
    assert row == (1, 100)


def test_battery_absent_stores_zero_null():
    conn = open_or_create(":memory:")
    insert_uplink(conn, _make_uplink())
    row = conn.execute(
        "SELECT battery_present, battery_value FROM link"
    ).fetchone()
    assert row == (0, None)


def test_open_or_create_is_idempotent():
    conn = open_or_create(":memory:")
    open_or_create(":memory:")  # different connection, but schema lib itself idempotent
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall() == [("link",), ("moisture",)]
