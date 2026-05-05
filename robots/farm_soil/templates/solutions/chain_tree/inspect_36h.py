"""project.farm_soil.solutions.chain_tree.inspect_36h — single-tick inspector.

Solution: open KB column → fetch the last `lookback_hours` of TTN
uplinks → print a per-device moisture/RF report sorted by device_id
→ terminate the engine. Designed for human inspection, not for
long-running deployment.

Slots:
  kb_name           required STRING — name for the surrounding KB column.
  db_path           required STRING — SQLite file path.
  ttn_url_base      required STRING — TTN application API base URL.
  ttn_app           required STRING — TTN application id.
  ttn_url_after     required STRING — storage endpoint suffix.
  ttn_bearer_token  required STRING — TTN API bearer token.
  lookback_hours    optional INT    — defaults to 36.
"""

from __future__ import annotations

from template_language import ct, define_template, use_template


def inspect_36h(
    *,
    kb_name: str,
    db_path: str,
    ttn_url_base: str,
    ttn_app: str,
    ttn_url_after: str,
    ttn_bearer_token: str,
    lookback_hours: int = 36,
):
    """Build a single-tick inspect KB: fetch → report → terminate."""
    ct.start_test(kb_name)
    use_template(
        "user.leaves.chain_tree.lorwan_moisture",
        name=kb_name,
        db_path=db_path,
        ttn_url_base=ttn_url_base,
        ttn_app=ttn_app,
        ttn_url_after=ttn_url_after,
        ttn_bearer_token=ttn_bearer_token,
        lookback_hours=lookback_hours,
    )
    use_template(
        "project.farm_soil.leaves.chain_tree.moisture_report",
        name=kb_name,
        db_path=db_path,
        lookback_hours=lookback_hours,
    )
    ct.asm_terminate_system()
    ct.end_test()


define_template(
    path="project.farm_soil.solutions.chain_tree.inspect_36h",
    fn=inspect_36h,
    kind="solution",
    engine="chain_tree",
    slot_examples={
        "kb_name": "farm_soil_inspect",
        "db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "ttn_url_base": "https://nam1.cloud.thethings.network/api/v3/as/applications/",
        "ttn_app": "seeedec",
        "ttn_url_after": "/packages/storage/uplink_message?",
        "ttn_bearer_token": "NNSXS.xxxxxxxx",
        "lookback_hours": 36,
    },
)
