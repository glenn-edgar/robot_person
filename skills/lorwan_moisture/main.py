"""skills.lorwan_moisture — fetch SenseCAP S2105 uplinks from TTN to SQLite.

Per the skills convention (skills/README.md): one class + __main__ test
driver. Engine-agnostic — no chain_tree / s_engine imports.

Public class:
  MoistureFetcher — `__init__(...)` + `tick() -> int` (rows inserted).

Helper modules in the same directory:
  ttn_client.py — TTNStorageClient (urllib wrapper)
  decoder.py    — TTN SSE response + SenseCAP frame parser
  db.py         — SQLite schema + INSERT OR IGNORE writer
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from .db import insert_uplink, open_or_create
from .decoder import parse_uplinks
from .ttn_client import TTNStorageClient


class MoistureFetcher:
    """Polls a TTN application and stores SenseCAP uplinks in SQLite.

    `tick()` queries the last `lookback_hours` window each call and
    INSERTs OR IGNOREs every uplink. Idempotent: re-running the same
    tick window is a no-op past the first insert.

    Pass a `logger` callable (str -> None) to receive step-by-step
    diagnostics: request URL, HTTP outcome, body size, parsed uplink
    count, rows inserted. Defaults to a no-op logger; chain_tree
    wraps it with the engine's logger.
    """

    def __init__(
        self,
        db_path: str,
        ttn_url_base: str,
        ttn_app: str,
        ttn_url_after: str,
        ttn_bearer_token: str,
        lookback_hours: int = 24,
        limit: int = 200,
        logger=None,
    ):
        self.db_path = db_path
        self.lookback_hours = lookback_hours
        self.logger = logger or (lambda msg: None)
        self.client = TTNStorageClient(
            url_base=ttn_url_base,
            app_name=ttn_app,
            url_after=ttn_url_after,
            bearer_token=ttn_bearer_token,
            limit=limit,
        )

    def _after_iso(self) -> str:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=self.lookback_hours)
        return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    def tick(self) -> int:
        """Fetch one window, write to SQLite, return rows inserted."""
        after = self._after_iso()
        url = self.client._request_url(after)
        self.logger(f"lorwan_moisture: GET {url}")
        body, ok, err = self.client.fetch(after)
        if not ok:
            self.logger(f"lorwan_moisture: fetch FAILED — {err}")
            return 0
        self.logger(f"lorwan_moisture: response {len(body)} bytes")
        uplinks = parse_uplinks(body)
        self.logger(f"lorwan_moisture: parsed {len(uplinks)} uplinks")
        if not uplinks:
            if body:
                preview = body[:300].replace("\n", "\\n")
                self.logger(f"lorwan_moisture: body preview: {preview}")
            return 0
        conn = open_or_create(self.db_path)
        try:
            rows = sum(insert_uplink(conn, up) for up in uplinks)
            self.logger(f"lorwan_moisture: inserted {rows} rows")
            return rows
        finally:
            conn.close()


if __name__ == "__main__":
    token = os.environ.get("TTN_BEARER_TOKEN")
    if not token:
        print(
            "TTN_BEARER_TOKEN not set; "
            "export it (see robots/farm_soil/secrets/ttn.env.example) "
            "and re-run.",
            file=sys.stderr,
        )
        sys.exit(2)

    fetcher = MoistureFetcher(
        db_path="./lorwan_moisture_smoke.sqlite",
        ttn_url_base="https://nam1.cloud.thethings.network/api/v3/as/applications/",
        ttn_app="seeedec",
        ttn_url_after="/packages/storage/uplink_message?",
        ttn_bearer_token=token,
        lookback_hours=24,
        logger=print,
    )
    rows = fetcher.tick()
    print(f"final: inserted {rows} rows into {fetcher.db_path}")
