"""Decode TTN SSE response + SenseCAP S2105 payload.

Two layers:
  1. `parse_uplinks(body)` — splits the TTN SSE/NDJSON response into
     individual uplink dicts. Tolerates `data: ` prefixes and the
     `{"result": {...}}` wrapper that TTN v3 storage emits.
  2. Measurement extraction prefers TTN's `decoded_payload.messages`
     (already parsed by TTN's payload formatter) and falls back to
     `decode_sensecap_frame(payload_bytes)` if the formatter isn't
     configured.

SenseCAP S2105 byte-frame layout (per measurement, repeating):
    0x01           (channel)
    <id LE u16>    measurement id
    <value LE i32, scaled by SCALE>
= 7 bytes per measurement. Trailing bytes (e.g. battery / CRC) that
don't start with 0x01 are ignored.

Known measurement IDs (see robots/farm_soil/hardware.yaml):
  4108 — volumetric water content (m^3/m^3)
  4102 — soil temperature (C)
  4103 — soil EC (mS/cm)
"""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass


CHANNEL_BYTE = 0x01
FRAME_LEN = 7  # 1 + 2 + 4
SCALE = 0.001


@dataclass
class Measurement:
    measurement_id: int
    value: float


@dataclass
class GatewayInfo:
    gateway_id: str | None
    rssi: int | None
    channel_rssi: int | None
    snr: float | None
    frequency: str | None
    spreading_factor: int | None
    bandwidth: int | None
    coding_rate: str | None
    airtime_s: float | None
    gateway_count: int


@dataclass
class Uplink:
    device_id: str
    received_at: str
    f_cnt: int | None
    frm_payload_b64: str | None
    measurements: list[Measurement]
    gateway: GatewayInfo
    battery_present: bool = False
    battery_value: int | None = None


def parse_uplinks(body: str) -> list[Uplink]:
    """Parse a TTN storage response body into Uplink objects.

    Skips lines that aren't JSON, tolerates SSE `data: ` prefixes and
    the `{"result": {...}}` wrapper. Decoded payloads that don't fit
    the SenseCAP frame shape are returned with `measurements=[]` so
    the caller can still record link/gateway data.
    """
    out: list[Uplink] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        if not line or not (line.startswith("{") or line.startswith("[")):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = obj.get("result", obj) if isinstance(obj, dict) else None
        if not isinstance(result, dict):
            continue
        uplink = _uplink_from_result(result)
        if uplink is not None:
            out.append(uplink)
    return out


def _uplink_from_result(result: dict) -> Uplink | None:
    eds = result.get("end_device_ids") or {}
    device_id = eds.get("device_id")
    received_at = result.get("received_at")
    if not device_id or not received_at:
        return None
    msg = result.get("uplink_message") or {}
    f_cnt = msg.get("f_cnt")
    frm_b64 = msg.get("frm_payload")
    uplink_f_cnt = f_cnt if isinstance(f_cnt, int) else None
    bat_present, bat_value = _battery_from_msg(msg, uplink_f_cnt)
    return Uplink(
        device_id=device_id,
        received_at=received_at,
        f_cnt=uplink_f_cnt,
        frm_payload_b64=frm_b64,
        measurements=_measurements_from_msg(msg),
        gateway=_gateway_from_msg(msg),
        battery_present=bat_present,
        battery_value=bat_value,
    )


def _battery_from_msg(
    msg: dict, uplink_f_cnt: int | None
) -> tuple[bool, int | None]:
    """Battery is "present in this uplink" only when the cached f_cnt matches.

    TTN attaches `last_battery_percentage` to every uplink — the latest
    known battery state, regardless of whether *this* uplink carried it.
    The cached entry's `f_cnt` is the uplink that originally carried it.
    Treat the field as present here only when those f_cnts match.
    """
    batt = msg.get("last_battery_percentage")
    if not isinstance(batt, dict):
        return False, None
    bf_cnt = batt.get("f_cnt")
    if not (
        isinstance(uplink_f_cnt, int)
        and isinstance(bf_cnt, int)
        and bf_cnt == uplink_f_cnt
    ):
        return False, None
    v = batt.get("value")
    if isinstance(v, bool):
        return True, None
    if isinstance(v, int):
        return True, v
    if isinstance(v, float):
        return True, round(v)
    return True, None


def _measurements_from_msg(msg: dict) -> list[Measurement]:
    """Prefer TTN's decoded_payload.messages; fall back to byte decoding."""
    decoded = msg.get("decoded_payload") or {}
    messages = decoded.get("messages")
    if isinstance(messages, list) and messages:
        out: list[Measurement] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            mid = m.get("measurementId")
            val = m.get("measurementValue")
            if isinstance(mid, int) and isinstance(val, (int, float)):
                out.append(Measurement(mid, float(val)))
        if out:
            return out
    frm_b64 = msg.get("frm_payload")
    if isinstance(frm_b64, str) and frm_b64:
        try:
            return list(decode_sensecap_frame(base64.b64decode(frm_b64)))
        except (ValueError, struct.error):
            return []
    return []


def _gateway_from_msg(msg: dict) -> GatewayInfo:
    """Pick the strongest gateway (highest RSSI) and the gateway count."""
    rx_list = [r for r in (msg.get("rx_metadata") or []) if isinstance(r, dict)]

    def _rssi_key(rx: dict) -> float:
        r = rx.get("rssi")
        return float(r) if isinstance(r, (int, float)) else float("-inf")

    strongest: dict = max(rx_list, key=_rssi_key) if rx_list else {}
    settings = msg.get("settings") or {}
    data_rate = (settings.get("data_rate") or {}).get("lora") or {}
    airtime = msg.get("consumed_airtime")
    airtime_s: float | None = None
    if isinstance(airtime, str) and airtime.endswith("s"):
        try:
            airtime_s = float(airtime[:-1])
        except ValueError:
            airtime_s = None
    return GatewayInfo(
        gateway_id=(strongest.get("gateway_ids") or {}).get("gateway_id"),
        rssi=strongest.get("rssi"),
        channel_rssi=strongest.get("channel_rssi"),
        snr=strongest.get("snr"),
        frequency=settings.get("frequency"),
        spreading_factor=data_rate.get("spreading_factor"),
        bandwidth=data_rate.get("bandwidth"),
        coding_rate=data_rate.get("coding_rate"),
        airtime_s=airtime_s,
        gateway_count=len(rx_list),
    )


def decode_sensecap_frame(payload: bytes):
    """Yield Measurement per 7-byte frame in `payload`.

    Stops at the first frame whose start byte isn't 0x01 — trailing
    bytes (battery indicator, CRC, etc.) are ignored rather than
    raised as errors.
    """
    off = 0
    while off + FRAME_LEN <= len(payload):
        if payload[off] != CHANNEL_BYTE:
            return
        mid = struct.unpack_from("<H", payload, off + 1)[0]
        raw = struct.unpack_from("<i", payload, off + 3)[0]
        yield Measurement(mid, raw * SCALE)
        off += FRAME_LEN
