"""Tests for CIMIS response decoder. No network — synthetic JSON."""

from __future__ import annotations

import json
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_skill = os.path.dirname(_here)
_skills_root = os.path.dirname(_skill)
_repo = os.path.dirname(_skills_root)
if _repo not in sys.path:
    sys.path.insert(0, _repo)

from skills.cimis.decoder import parse_response  # noqa: E402


def _station_response(station: str, date: str, eto: str) -> str:
    return json.dumps({
        "Data": {
            "Providers": [{
                "Name": "cimis",
                "Type": "station",
                "Records": [{
                    "Date": date,
                    "Hour": None,
                    "Julian": "124",
                    "Station": station,
                    "Standard": "english",
                    "ZipCodes": "92590",
                    "Scope": "daily",
                    "DayAsceEto": {"Value": eto, "Qc": "Y", "Unit": "Inches"},
                    "DayAirTmpMax": {"Value": "78.4", "Qc": "Y", "Unit": "Fahrenheit"},
                }]
            }]
        }
    })


def _spatial_response(lat: str, lng: str, date: str, eto: str) -> str:
    return json.dumps({
        "Data": {
            "Providers": [{
                "Name": "cimis",
                "Type": "spatial",
                "Records": [{
                    "Date": date,
                    "Coordinates": {"Latitude": lat, "Longitude": lng},
                    "DayAsceEto": {"Value": eto, "Qc": "Y", "Unit": "Inches"},
                }]
            }]
        }
    })


def test_station_records_extract():
    out = parse_response(_station_response("237", "2026-05-04", "0.20"))
    items = sorted({r.item for r in out})
    assert items == ["DayAirTmpMax", "DayAsceEto"]
    eto = next(r for r in out if r.item == "DayAsceEto")
    assert eto.target_kind == "station"
    assert eto.target == "237"
    assert eto.date == "2026-05-04"
    assert eto.value == 0.20
    assert eto.unit == "Inches"
    assert eto.qc == "Y"


def test_spatial_records_extract():
    out = parse_response(_spatial_response("33.5785", "-117.2994", "2026-05-04", "0.18"))
    assert len(out) == 1
    rec = out[0]
    assert rec.target_kind == "spatial"
    assert rec.target == "33.5785,-117.2994"
    assert rec.date == "2026-05-04"
    assert rec.item == "DayAsceEto"
    assert rec.value == 0.18


def test_zip_based_spatial_extract():
    """A spatial response keyed by ZipCodes (no Coordinates field) — the
    shape CIMIS returns when targets is a zip code rather than a coord."""
    body = json.dumps({
        "Data": {
            "Providers": [{
                "Name": "cimis",
                "Type": "spatial",
                "Records": [{
                    "Date": "2026-04-28",
                    "Julian": "118",
                    "Standard": "english",
                    "ZipCodes": "92590",
                    "Scope": "daily",
                    "DayAsceEto": {"Value": "0.17", "Qc": " ", "Unit": "(in)"},
                }]
            }]
        }
    })
    out = parse_response(body)
    assert len(out) == 1
    assert out[0].target_kind == "spatial"
    assert out[0].target == "92590"
    assert out[0].value == 0.17


def test_mixed_provider_response():
    """A response with both station and spatial providers in one body."""
    body = json.dumps({
        "Data": {
            "Providers": [
                {
                    "Name": "cimis",
                    "Type": "station",
                    "Records": [{
                        "Date": "2026-05-04",
                        "Station": "237",
                        "DayAsceEto": {"Value": "0.20", "Qc": "Y", "Unit": "Inches"},
                    }],
                },
                {
                    "Name": "cimis",
                    "Type": "spatial",
                    "Records": [{
                        "Date": "2026-05-04",
                        "Coordinates": {"Latitude": "33.5785", "Longitude": "-117.2994"},
                        "DayAsceEto": {"Value": "0.18", "Qc": "Y", "Unit": "Inches"},
                    }],
                },
            ]
        }
    })
    out = parse_response(body)
    kinds = sorted({r.target_kind for r in out})
    assert kinds == ["spatial", "station"]


def test_malformed_json_returns_empty():
    assert parse_response("not json") == []
    assert parse_response("") == []


def test_missing_fields_skip_record():
    body = json.dumps({
        "Data": {
            "Providers": [{
                "Name": "cimis",
                "Type": "station",
                "Records": [
                    {"Date": "2026-05-04"},                    # no Station
                    {"Station": "237"},                         # no Date
                    {"Date": "2026-05-04", "Station": "237",
                     "DayAsceEto": {"Value": "", "Qc": "M", "Unit": "Inches"}},
                ]
            }]
        }
    })
    out = parse_response(body)
    # Only the 3rd record yields an emitted row; its value is None (empty).
    assert len(out) == 1
    assert out[0].value is None
    assert out[0].qc == "M"
