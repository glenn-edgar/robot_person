"""Tests for the SenseCAP frame decoder + TTN uplink parser.

No network, no DB — pure parsing. Builds a synthetic 24-byte frame
covering all three measurement IDs and confirms decode + scaling.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_skill = os.path.dirname(_here)
_skills_root = os.path.dirname(_skill)
_repo = os.path.dirname(_skills_root)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from skills.lorwan_moisture.decoder import (  # noqa: E402
    decode_sensecap_frame,
    parse_uplinks,
)


def _build_frame(measurements: list[tuple[int, float]]) -> bytes:
    """Build a SenseCAP byte-frame from (measurement_id, value) pairs.

    7 bytes per measurement: 0x01 + id LE u16 + value LE i32 (×1000).
    """
    out = bytearray()
    for mid, val in measurements:
        out.append(0x01)
        out.extend(struct.pack("<H", mid))
        out.extend(struct.pack("<i", round(val * 1000)))
    return bytes(out)


def test_decode_real_sensecap_payload():
    """Real frm_payload from a TTN uplink (lacima1d, 2026-05-04).

    Hex: 010C1012020000010610CC420000010710B4780000B06B
    Decoded by TTN's payload formatter:
      4108 -> 0.530, 4102 -> 17.1, 4103 -> 30.9
    """
    payload = bytes.fromhex("010C1012020000010610CC420000010710B4780000B06B")
    out = list(decode_sensecap_frame(payload))
    assert [m.measurement_id for m in out] == [4108, 4102, 4103]
    assert abs(out[0].value - 0.530) < 1e-6
    assert abs(out[1].value - 17.1) < 1e-6
    assert abs(out[2].value - 30.9) < 1e-6


def test_decode_three_measurements():
    payload = _build_frame([(4108, 0.234), (4102, 19.5), (4103, 1.234)])
    out = list(decode_sensecap_frame(payload))
    assert [m.measurement_id for m in out] == [4108, 4102, 4103]
    assert abs(out[0].value - 0.234) < 1e-6
    assert abs(out[1].value - 19.5) < 1e-6
    assert abs(out[2].value - 1.234) < 1e-6


def test_decode_negative_temp():
    payload = _build_frame([(4102, -5.125)])
    out = list(decode_sensecap_frame(payload))
    assert len(out) == 1
    assert abs(out[0].value - (-5.125)) < 1e-6


def test_decode_stops_on_bad_channel_byte():
    good = _build_frame([(4108, 1.0)])
    bad = good + b"\x99\x00\x00\x00\x00\x00\x00"
    out = list(decode_sensecap_frame(bad))
    assert len(out) == 1
    assert out[0].measurement_id == 4108


def test_parse_uplinks_prefers_decoded_payload():
    """When TTN provides decoded_payload.messages, use those directly."""
    uplink = {
        "result": {
            "end_device_ids": {"device_id": "lacima1d"},
            "received_at": "2026-05-04T00:34:54.779712873Z",
            "uplink_message": {
                "f_cnt": 4115,
                "frm_payload": "AQwQEgIAAAEGEMxCAAABBxC0eAAAsGs=",
                "decoded_payload": {
                    "err": 0,
                    "messages": [
                        {"measurementId": 4108, "measurementValue": 0.53,
                         "type": "report_telemetry"},
                        {"measurementId": 4102, "measurementValue": 17.1,
                         "type": "report_telemetry"},
                        {"measurementId": 4103, "measurementValue": 30.9,
                         "type": "report_telemetry"},
                    ],
                },
                "rx_metadata": [{
                    "gateway_ids": {"gateway_id": "lacima-ranch-1"},
                    "rssi": -100, "channel_rssi": -100, "snr": 7.25,
                }],
                "settings": {
                    "data_rate": {"lora": {
                        "bandwidth": 125000,
                        "spreading_factor": 7,
                        "coding_rate": "4/5",
                    }},
                    "frequency": "904700000",
                },
                "consumed_airtime": "0.082176s",
            },
        }
    }
    body = f"data: {json.dumps(uplink)}\n\n"
    out = parse_uplinks(body)
    assert len(out) == 1
    up = out[0]
    assert up.device_id == "lacima1d"
    assert up.f_cnt == 4115
    assert [(m.measurement_id, round(m.value, 3)) for m in up.measurements] == [
        (4108, 0.530), (4102, 17.1), (4103, 30.9),
    ]
    assert up.gateway.gateway_id == "lacima-ranch-1"
    assert up.gateway.rssi == -100
    assert abs(up.gateway.airtime_s - 0.082176) < 1e-9


def test_parse_uplinks_falls_back_to_byte_decode():
    """No decoded_payload — use the byte-frame decoder."""
    payload_b64 = base64.b64encode(_build_frame([(4108, 0.5)])).decode("ascii")
    uplink = {
        "result": {
            "end_device_ids": {"device_id": "lacima1c"},
            "received_at": "2026-05-04T12:00:00.000Z",
            "uplink_message": {
                "f_cnt": 7,
                "frm_payload": payload_b64,
                "rx_metadata": [{"gateway_ids": {"gateway_id": "gw"}}],
                "settings": {},
            },
        }
    }
    body = f"data: {json.dumps(uplink)}\n\n"
    out = parse_uplinks(body)
    assert len(out) == 1
    assert len(out[0].measurements) == 1
    assert out[0].measurements[0].measurement_id == 4108
    assert abs(out[0].measurements[0].value - 0.5) < 1e-6


def _uplink_with_battery(uplink_f_cnt: int, batt_f_cnt: int, value=100):
    return {
        "result": {
            "end_device_ids": {"device_id": "lacima1d"},
            "received_at": "2026-05-05T17:34:34Z",
            "uplink_message": {
                "f_cnt": uplink_f_cnt,
                "decoded_payload": {
                    "messages": [
                        {"measurementId": 4108, "measurementValue": 0.35},
                    ],
                },
                "rx_metadata": [{"gateway_ids": {"gateway_id": "gw"}, "rssi": -99}],
                "settings": {},
                "last_battery_percentage": {
                    "f_cnt": batt_f_cnt, "value": value,
                    "received_at": "2026-05-05T11:34:33Z",
                },
            },
        }
    }


def test_battery_present_when_f_cnt_matches_uplink():
    """Battery counts as 'in this uplink' only when its cached f_cnt
    matches the uplink's own f_cnt — TTN attaches the last-known battery
    to every uplink, so equality is the only signal it came in this one."""
    out = parse_uplinks(f"data: {json.dumps(_uplink_with_battery(4150, 4150, 100))}\n\n")
    assert len(out) == 1
    assert out[0].battery_present is True
    assert out[0].battery_value == 100


def test_battery_absent_when_cached_f_cnt_differs():
    """When the cached battery is from an earlier uplink (different
    f_cnt), this uplink did NOT carry battery telemetry."""
    out = parse_uplinks(f"data: {json.dumps(_uplink_with_battery(4156, 4150, 100))}\n\n")
    assert len(out) == 1
    assert out[0].battery_present is False
    assert out[0].battery_value is None


def test_battery_absent_when_field_missing():
    uplink = {
        "result": {
            "end_device_ids": {"device_id": "lacima1c"},
            "received_at": "2026-05-05T17:34:34Z",
            "uplink_message": {
                "f_cnt": 1,
                "decoded_payload": {
                    "messages": [{"measurementId": 4108, "measurementValue": 0.5}],
                },
                "rx_metadata": [{"gateway_ids": {"gateway_id": "gw"}, "rssi": -75}],
                "settings": {},
            },
        }
    }
    out = parse_uplinks(f"data: {json.dumps(uplink)}\n\n")
    assert len(out) == 1
    assert out[0].battery_present is False
    assert out[0].battery_value is None


def test_parse_uplinks_picks_strongest_gateway():
    """rx_metadata with 3 gateways: pick highest RSSI, count all 3."""
    uplink = {
        "result": {
            "end_device_ids": {"device_id": "lacima1d"},
            "received_at": "2026-05-04T00:34:54Z",
            "uplink_message": {
                "f_cnt": 1,
                "decoded_payload": {
                    "messages": [
                        {"measurementId": 4108, "measurementValue": 0.5},
                    ],
                },
                "rx_metadata": [
                    {"gateway_ids": {"gateway_id": "gw-far"},
                     "rssi": -110, "snr": -2.0},
                    {"gateway_ids": {"gateway_id": "gw-near"},
                     "rssi": -75, "snr": 9.5},
                    {"gateway_ids": {"gateway_id": "gw-mid"},
                     "rssi": -95, "snr": 4.0},
                ],
                "settings": {},
            },
        }
    }
    body = f"data: {json.dumps(uplink)}\n\n"
    out = parse_uplinks(body)
    assert len(out) == 1
    g = out[0].gateway
    assert g.gateway_id == "gw-near"
    assert g.rssi == -75
    assert g.snr == 9.5
    assert g.gateway_count == 3


def test_parse_uplinks_skips_garbage_lines():
    body = "garbage\n\ndata: not-json\n\ndata: {}\n"
    assert parse_uplinks(body) == []
