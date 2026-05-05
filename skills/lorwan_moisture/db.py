"""SQLite schema + INSERT OR IGNORE writer for soil moisture data.

Two tables — schema is idempotent (CREATE IF NOT EXISTS), so calling
`open_or_create` twice in a row is a no-op the second time.

  moisture(device_id, received_at, measurement_id, value, f_cnt)
    PK (device_id, received_at, measurement_id)

  link(device_id, received_at, gateway_id, rssi, channel_rssi, snr,
       frequency, spreading_factor, bandwidth, coding_rate, airtime_s,
       gateway_count, battery_present, battery_value)
    PK (device_id, received_at)

`gateway_id` / `rssi` / `snr` / `channel_rssi` are from the strongest
(highest-RSSI) gateway in `rx_metadata`; `gateway_count` is the total
number of gateways that received the uplink.

`battery_present` is 1 when TTN attached `last_battery_percentage` to
the uplink (some uplinks include it, others don't); `battery_value`
is the integer percentage when present.
"""

from __future__ import annotations

import sqlite3

from .decoder import Uplink


SCHEMA = """
CREATE TABLE IF NOT EXISTS moisture (
    device_id      TEXT NOT NULL,
    received_at    TEXT NOT NULL,
    measurement_id INTEGER NOT NULL,
    value          REAL NOT NULL,
    f_cnt          INTEGER,
    PRIMARY KEY (device_id, received_at, measurement_id)
);

CREATE TABLE IF NOT EXISTS link (
    device_id          TEXT NOT NULL,
    received_at        TEXT NOT NULL,
    gateway_id         TEXT,
    rssi               INTEGER,
    channel_rssi       INTEGER,
    snr                REAL,
    frequency          TEXT,
    spreading_factor   INTEGER,
    bandwidth          INTEGER,
    coding_rate        TEXT,
    airtime_s          REAL,
    gateway_count      INTEGER NOT NULL DEFAULT 1,
    battery_present    INTEGER NOT NULL DEFAULT 0,
    battery_value      INTEGER,
    PRIMARY KEY (device_id, received_at)
);
"""


def open_or_create(db_path: str) -> sqlite3.Connection:
    """Open `db_path`, ensure schema, return the connection."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_uplink(conn: sqlite3.Connection, up: Uplink) -> int:
    """Insert one uplink's measurements + link row. Returns rows added."""
    rows = 0
    cur = conn.cursor()
    for m in up.measurements:
        cur.execute(
            "INSERT OR IGNORE INTO moisture "
            "(device_id, received_at, measurement_id, value, f_cnt) "
            "VALUES (?, ?, ?, ?, ?)",
            (up.device_id, up.received_at, m.measurement_id,
             m.value, up.f_cnt),
        )
        rows += cur.rowcount
    g = up.gateway
    cur.execute(
        "INSERT OR IGNORE INTO link "
        "(device_id, received_at, gateway_id, rssi, channel_rssi, snr, "
        " frequency, spreading_factor, bandwidth, coding_rate, airtime_s, "
        " gateway_count, battery_present, battery_value) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (up.device_id, up.received_at, g.gateway_id, g.rssi, g.channel_rssi,
         g.snr, g.frequency, g.spreading_factor, g.bandwidth,
         g.coding_rate, g.airtime_s, g.gateway_count,
         1 if up.battery_present else 0, up.battery_value),
    )
    rows += cur.rowcount
    conn.commit()
    return rows
