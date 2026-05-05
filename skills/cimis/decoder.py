"""Parse CIMIS /api/data JSON responses into flat CimisRecord rows.

Response shape (documented at et.water.ca.gov):
  {"Data": {"Providers": [
    {"Name": "cimis", "Type": "station"|"spatial",
     "Records": [{
        "Date": "2026-05-04",
        "Station": "237",            # station type
        "Coordinates": {"Latitude": "...", "Longitude": "..."},   # spatial type
        "DayAsceEto": {"Value": "0.20", "Qc": "Y", "Unit": "Inches"},
        ...other Day*/Hly* fields...
     }]}
  ]}}

Each `Day*` / `Hly*` key is a measurement; the parser yields one
CimisRecord per (target, date, item).
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class CimisRecord:
    target_kind: str       # 'station' or 'spatial'
    target: str            # station id string, or 'lat,lng'
    date: str              # YYYY-MM-DD
    item: str              # CIMIS PascalCase key, e.g. 'DayAsceEto'
    value: float | None
    unit: str | None
    qc: str | None


def parse_response(body: str) -> list[CimisRecord]:
    """Parse a CIMIS JSON response body into flat CimisRecord rows."""
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []
    out: list[CimisRecord] = []
    providers = ((obj.get("Data") or {}).get("Providers")) or []
    for prov in providers:
        if not isinstance(prov, dict):
            continue
        ptype = prov.get("Type")
        for rec in prov.get("Records") or []:
            if not isinstance(rec, dict):
                continue
            date = rec.get("Date")
            target = _target_from_record(rec, ptype)
            if not target or not date or not ptype:
                continue
            for key, val in rec.items():
                if not (key.startswith("Day") or key.startswith("Hly")):
                    continue
                if not isinstance(val, dict):
                    continue
                out.append(CimisRecord(
                    target_kind=ptype,
                    target=target,
                    date=date,
                    item=key,
                    value=_to_float(val.get("Value")),
                    unit=val.get("Unit"),
                    qc=val.get("Qc"),
                ))
    return out


def _target_from_record(rec: dict, ptype: str | None) -> str | None:
    if ptype == "station":
        s = rec.get("Station")
        return str(s) if s is not None else None
    if ptype == "spatial":
        # Coordinate-based spatial: response carries Coordinates dict.
        coords = rec.get("Coordinates") or {}
        lat = coords.get("Latitude")
        lng = coords.get("Longitude")
        if lat is not None and lng is not None:
            return f"{lat},{lng}"
        # Zip-based spatial: response carries ZipCodes string.
        zips = rec.get("ZipCodes")
        if zips:
            return str(zips)
        return None
    return None


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
