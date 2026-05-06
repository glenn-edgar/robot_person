"""End-to-end stage-2 test for the daily_report composite.

Seeds two real SQLite DBs (moisture + CIMIS) via the skill db helpers,
wraps the composite in a one-shot solution, monkeypatches the Discord
notifier, runs the engine to termination, asserts the message that
would have gone to Discord covers both data sources.

Exercises P0.1 (sqlite_query skill), P0.5 (discord_notify content_bb_key),
and P0.6 (the composite + format leaf + sqlite_query leaf wiring) in
one shot.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from skills.lorwan_moisture.db import insert_uplink, open_or_create as moist_open
from skills.lorwan_moisture.decoder import GatewayInfo, Measurement, Uplink
from skills.cimis.db import insert_record as cimis_insert
from skills.cimis.db import open_or_create as cimis_open
from skills.cimis.decoder import CimisRecord
from template_language import ct, define_template, generate_code, use_template


# ---------------------------------------------------------------------------
# Fixtures — populate two real SQLite DBs the composite reads from.
# ---------------------------------------------------------------------------

def _now_minus(hours: int) -> str:
    return (
        datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _uplink(device_id: str, hours_ago: int, moisture: float) -> Uplink:
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
            gateway_id="gw-test", rssi=-72, channel_rssi=-72, snr=10.5,
            frequency="904300000", spreading_factor=7, bandwidth=125000,
            coding_rate="4/5", airtime_s=0.061696, gateway_count=1,
        ),
    )


def _seed_moisture(db_path: str) -> None:
    conn = moist_open(db_path)
    try:
        insert_uplink(conn, _uplink("lacima1c", 1,  0.30))
        insert_uplink(conn, _uplink("lacima1c", 5,  0.28))
        insert_uplink(conn, _uplink("lacima1c", 12, 0.27))
        insert_uplink(conn, _uplink("lacima1d", 2,  0.18))
        insert_uplink(conn, _uplink("lacima1d", 30, 0.17))
        # 100h ago — outside the 48h composite default; should NOT appear.
        insert_uplink(conn, _uplink("lacima1c", 100, 0.99))
    finally:
        conn.close()


def _seed_cimis(db_path: str) -> None:
    conn = cimis_open(db_path)
    try:
        today = datetime.now(tz=timezone.utc).date()
        for offset_days in (1, 2, 3):
            d = (today - timedelta(days=offset_days)).isoformat()
            cimis_insert(conn, CimisRecord(
                target_kind="station",
                target="237",
                date=d,
                item="DayAsceEto",
                value=0.10 + 0.01 * offset_days,
                unit="(in)",
                qc="Y",
            ))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Discord notifier stub
# ---------------------------------------------------------------------------

class _CapturingNotifier:
    instances: list["_CapturingNotifier"] = []

    def __init__(self, webhook_url, **_kwargs):
        self.webhook_url = webhook_url
        self.sent: list[tuple[str, dict]] = []
        _CapturingNotifier.instances.append(self)

    def send(self, content, *, username=None):
        self.sent.append((content, {"username": username}))
        return True, None


def _patch_notifier(monkeypatch):
    _CapturingNotifier.instances = []
    import user_templates.templates.leaves.chain_tree.discord_notify as leaf
    monkeypatch.setattr(leaf, "DiscordNotifier", _CapturingNotifier)


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def _run_to_termination(chain, kb_name: str) -> None:
    counter = {"n": 0}

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= 20:
            chain.engine["cfl_engine_flag"] = False

    chain.engine["sleep"] = capped_sleep
    chain.run(starting=[kb_name])


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_daily_report_composite_end_to_end(tmp_path, monkeypatch):
    moisture_db = str(tmp_path / "moisture.sqlite")
    cimis_db = str(tmp_path / "cimis.sqlite")
    _seed_moisture(moisture_db)
    _seed_cimis(cimis_db)
    _patch_notifier(monkeypatch)

    def body():
        ct.start_test("kb_daily")
        use_template(
            "project.farm_soil.composites.chain_tree.daily_report",
            name="main",
            moisture_db_path=moisture_db,
            cimis_db_path=cimis_db,
            webhook_url="https://example.invalid/wh",
            moisture_lookback_hours=48,
            cimis_lookback_days=7,
            cimis_station="237",
        )
        ct.asm_terminate_system()
        ct.end_test()

    define_template(
        path="project.farm_soil.solutions.chain_tree._test_daily_report",
        fn=body,
        kind="solution",
        engine="chain_tree",
    )
    op_list = use_template("project.farm_soil.solutions.chain_tree._test_daily_report")

    log: list[str] = []
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: int(time.time()),
        timezone=timezone.utc,
        logger=log.append,
    )
    _run_to_termination(chain, "kb_daily")

    # The composite's four leaves all logged something — confirms the
    # whole sequence ran in declaration order.
    body_log = "\n".join(log)
    assert "sqlite_query[daily_query_moisture_main]:" in body_log
    assert "sqlite_query[daily_query_eto_main]:" in body_log
    assert "format_daily_report[daily_format_main]:" in body_log
    assert "discord_notify[daily_notify_main]: sent ok" in body_log

    # Discord got exactly one message.
    assert len(_CapturingNotifier.instances) == 1
    sent = _CapturingNotifier.instances[0].sent
    assert len(sent) == 1
    msg, _ = sent[0]

    # Message contents: header + both data sections + specific values.
    assert "farm_soil daily report" in msg
    assert "Moisture (per-device latest):" in msg
    assert "lacima1c" in msg and "0.300" in msg
    assert "lacima1d" in msg and "0.180" in msg
    # The 100h-ago row was outside the 48h window and must not appear.
    assert "0.990" not in msg
    assert "ETo (CIMIS):" in msg
    # Three days seeded; values are 0.11, 0.12, 0.13.
    assert "0.110" in msg or "0.120" in msg or "0.130" in msg
    # Under the Discord 2000-char limit.
    assert len(msg) < 2000
