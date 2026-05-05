"""CIMIS Web API HTTP client.

Thin urllib wrapper around https://et.water.ca.gov/api/data. The
appKey is sent as a query parameter per the CIMIS docs; we use the
HTTPS host so the key isn't sent in the clear over the wire.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request


class CimisClient:
    """Fetches a single CIMIS data window for one target group."""

    def __init__(
        self,
        app_key: str,
        api_base: str = "https://et.water.ca.gov/api/data",
    ):
        self.app_key = app_key
        self.api_base = api_base

    def _request_url(
        self,
        targets: str,
        data_items: str,
        start_date: str,
        end_date: str,
        units: str = "E",
    ) -> str:
        params = {
            "appKey": self.app_key,
            "targets": targets,
            "dataItems": data_items,
            "startDate": start_date,
            "endDate": end_date,
            "unitOfMeasure": units,
        }
        return f"{self.api_base}?{urllib.parse.urlencode(params)}"

    def fetch(
        self,
        targets: str,
        data_items: str,
        start_date: str,
        end_date: str,
        units: str = "E",
    ) -> tuple[str, bool, str | None]:
        """GET one CIMIS window. Returns (body, ok, error_msg)."""
        url = self._request_url(targets, data_items, start_date, end_date, units)
        req = urllib.request.Request(
            url, method="GET", headers={"Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.read().decode("utf-8", errors="replace"), True, None
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                body = ""
            return "", False, f"HTTP {e.code} {e.reason}: {body}"
        except urllib.error.URLError as e:
            return "", False, f"URL error: {e.reason}"
        except Exception as e:  # noqa: BLE001
            return "", False, f"{type(e).__name__}: {e}"
