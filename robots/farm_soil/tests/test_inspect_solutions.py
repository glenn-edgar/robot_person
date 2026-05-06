"""Stage-2 deterministic tests for the inspect_36h and cimis_inspect solutions.

These exercise the same code path as `python -m robots.farm_soil.run` and
`python -m robots.farm_soil.run_cimis` — template resolution, slot binding,
multi-root prefix dispatch, leaf one-shot wiring, asm_terminate_system —
without hitting TTN or CIMIS. The fetch skill is monkeypatched with a
fake that seeds a real SQLite via the skill's own db helpers, so the
report leaf reads from a real schema and renders a real report.

Stage 2 (per the plan): in-process transport, sub-second runtime, no
network. These complement the live-system runners (kept in run.py /
run_cimis.py) which Glenn uses for cross-checks against real CIMIS /
TTN data.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from skills.lorwan_moisture.db import insert_uplink, open_or_create as moist_open
from skills.lorwan_moisture.decoder import GatewayInfo, Measurement, Uplink
from skills.cimis.db import insert_record as cimis_insert
from skills.cimis.db import open_or_create as cimis_open
from skills.cimis.decoder import CimisRecord
from template_language import generate_code, use_template
from ct_runtime.transport import InProcessTransport


# ---------------------------------------------------------------------------
# Helpers shared with test_report.py — recreate a mini moisture fixture.
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


def _run_to_termination(chain, kb_name: str) -> None:
    """Run the engine but cap iterations so a buggy solution can't hang."""
    counter = {"n": 0}

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= 20:
            chain.engine["cfl_engine_flag"] = False

    chain.engine["sleep"] = capped_sleep
    chain.run(starting=[kb_name])


# ---------------------------------------------------------------------------
# inspect_36h — moisture path
# ---------------------------------------------------------------------------

class _FakeMoistureFetcher:
    """Stand-in for skills.lorwan_moisture.MoistureFetcher.

    Records constructor args (so slot wiring can be asserted) and seeds
    the test SQLite with two devices' worth of toy uplinks on tick().
    """

    last_kwargs: dict | None = None

    def __init__(self, **kwargs):
        _FakeMoistureFetcher.last_kwargs = kwargs
        self._db_path = kwargs["db_path"]

    def tick(self) -> int:
        conn = moist_open(self._db_path)
        try:
            rows = 0
            rows += insert_uplink(conn, _uplink("lacima1d", 2,  moisture=0.21))
            rows += insert_uplink(conn, _uplink("lacima1d", 20, moisture=0.18))
            rows += insert_uplink(conn, _uplink("lacima1c", 1,  moisture=0.30))
            rows += insert_uplink(conn, _uplink("lacima1c", 30, moisture=0.27))
            return rows
        finally:
            conn.close()


def test_inspect_36h_solution_runs_deterministically(tmp_path, monkeypatch):
    db_path = str(tmp_path / "moist.sqlite")
    _FakeMoistureFetcher.last_kwargs = None
    # Import the leaf module first so monkeypatch operates on the freshly-
    # loaded module object — sidesteps the stale-attribute hazard from
    # conftest's per-test eviction of `user_templates.templates.*`.
    import user_templates.templates.leaves.chain_tree.lorwan_moisture as leaf
    monkeypatch.setattr(leaf, "MoistureFetcher", _FakeMoistureFetcher)

    op_list = use_template(
        "project.farm_soil.solutions.chain_tree.inspect_36h",
        kb_name="farm_soil_inspect",
        db_path=db_path,
        ttn_url_base="https://example.invalid/api/v3/as/applications/",
        ttn_app="seeedec",
        ttn_url_after="/packages/storage/uplink_message?",
        ttn_bearer_token="NNSXS.fake",
        lookback_hours=36,
    )

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

    # Plan-level invariant: stage-2 tests use InProcessTransport (the default).
    assert isinstance(chain.engine["transport"], InProcessTransport)

    _run_to_termination(chain, "farm_soil_inspect")

    body = "\n".join(log)

    # Slot wiring: the fake captured what the leaf passed to MoistureFetcher.
    kwargs = _FakeMoistureFetcher.last_kwargs
    assert kwargs is not None, "FakeMoistureFetcher was never instantiated"
    assert kwargs["db_path"] == db_path
    assert kwargs["ttn_app"] == "seeedec"
    assert kwargs["ttn_bearer_token"] == "NNSXS.fake"
    assert kwargs["lookback_hours"] == 36

    # Fetch leaf logs the row count using the leaf's name slot.
    assert "lorwan_moisture[farm_soil_inspect]: final" in body

    # Report leaf renders the same headers test_report.py asserts on.
    assert "farm_soil moisture/RF report (last 36h)" in body
    # Both seeded devices show up, sorted alphabetically.
    c_idx = body.index("--- lacima1c")
    d_idx = body.index("--- lacima1d")
    assert c_idx < d_idx
    assert "--- lacima1c (2 uplinks) ---" in body
    assert "--- lacima1d (2 uplinks) ---" in body
    # Specific moisture values are present.
    assert "0.300" in body and "0.180" in body


# ---------------------------------------------------------------------------
# cimis_inspect — ETo path
# ---------------------------------------------------------------------------

class _FakeCimisFetcher:
    last_kwargs: dict | None = None

    def __init__(self, **kwargs):
        _FakeCimisFetcher.last_kwargs = kwargs
        self._db_path = kwargs["db_path"]

    def tick(self) -> int:
        conn = cimis_open(self._db_path)
        try:
            rows = 0
            today = datetime.now(tz=timezone.utc).date()
            for offset_days in (1, 2, 3):
                d = (today - timedelta(days=offset_days)).isoformat()
                rec = CimisRecord(
                    target_kind="station",
                    target="237",
                    date=d,
                    item="DayAsceEto",
                    value=0.10 + 0.01 * offset_days,
                    unit="(in)",
                    qc="Y",
                )
                rows += cimis_insert(conn, rec)
            return rows
        finally:
            conn.close()


def test_cimis_inspect_solution_runs_deterministically(tmp_path, monkeypatch):
    db_path = str(tmp_path / "cimis.sqlite")
    _FakeCimisFetcher.last_kwargs = None
    import user_templates.templates.leaves.chain_tree.cimis_eto as leaf
    monkeypatch.setattr(leaf, "CimisFetcher", _FakeCimisFetcher)

    op_list = use_template(
        "project.farm_soil.solutions.chain_tree.cimis_inspect",
        kb_name="farm_soil_cimis_inspect",
        db_path=db_path,
        app_key="00000000-0000-0000-0000-000000000000",
        station_targets="237",
        spatial_targets="",
        data_items="day-asce-eto",
        lookback_days=7,
    )

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

    assert isinstance(chain.engine["transport"], InProcessTransport)

    _run_to_termination(chain, "farm_soil_cimis_inspect")

    body = "\n".join(log)

    kwargs = _FakeCimisFetcher.last_kwargs
    assert kwargs is not None, "FakeCimisFetcher was never instantiated"
    assert kwargs["db_path"] == db_path
    assert kwargs["station_targets"] == "237"
    assert kwargs["data_items"] == "day-asce-eto"
    assert kwargs["lookback_days"] == 7

    # Fetch leaf logs the new-row count.
    assert "cimis_eto[farm_soil_cimis_inspect]: final" in body
    # Report leaf renders something station-237-shaped (per cimis_report.py
    # output — header includes lookback days; station id appears in output).
    assert "237" in body
