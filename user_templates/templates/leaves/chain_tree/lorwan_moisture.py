"""user.leaves.chain_tree.lorwan_moisture — wrap MoistureFetcher as a leaf.

Registers a one-shot that constructs a `MoistureFetcher` from slot
values, calls `tick()`, and logs the row count via asm_log_message.
Multiple instances coexist by giving each a distinct `name` slot —
the one-shot is registered as `LORWAN_MOISTURE_<name>`.

Slots:
  name              required STRING — disambiguates one-shot registration.
  db_path           required STRING — SQLite file path.
  ttn_url_base      required STRING — e.g. https://nam1.cloud.thethings.network/api/v3/as/applications/
  ttn_app           required STRING — TTN application id, e.g. "seeedec".
  ttn_url_after     required STRING — e.g. "/packages/storage/uplink_message?".
  ttn_bearer_token  required STRING — TTN API bearer token (NNSXS.…).
  lookback_hours    optional INT    — defaults to 24.
"""

from __future__ import annotations

from skills.lorwan_moisture import MoistureFetcher

from template_language import ct, define_template


def lorwan_moisture(
    *,
    name: str,
    db_path: str,
    ttn_url_base: str,
    ttn_app: str,
    ttn_url_after: str,
    ttn_bearer_token: str,
    lookback_hours: int = 24,
):
    """Fetch one TTN window into SQLite via MoistureFetcher.tick()."""

    def _do_fetch(handle, node):
        logger = handle["engine"].get("logger") or print
        fetcher = MoistureFetcher(
            db_path=db_path,
            ttn_url_base=ttn_url_base,
            ttn_app=ttn_app,
            ttn_url_after=ttn_url_after,
            ttn_bearer_token=ttn_bearer_token,
            lookback_hours=lookback_hours,
            logger=logger,
        )
        rows = fetcher.tick()
        logger(f"lorwan_moisture[{name}]: final {rows} rows into {db_path}")

    one_shot_name = f"LORWAN_MOISTURE_{name}"
    ct.add_one_shot(one_shot_name, _do_fetch)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="user.leaves.chain_tree.lorwan_moisture",
    fn=lorwan_moisture,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "field_a",
        "db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "ttn_url_base": "https://nam1.cloud.thethings.network/api/v3/as/applications/",
        "ttn_app": "seeedec",
        "ttn_url_after": "/packages/storage/uplink_message?",
        "ttn_bearer_token": "NNSXS.xxxxxxxx",
        "lookback_hours": 24,
    },
)
