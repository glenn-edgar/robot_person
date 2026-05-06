"""project.farm_soil.composites.chain_tree.daily_report — sequence sub-tree.

The first project composite. Wires four leaves in declaration order
inside the caller's open column / KB:

    sqlite_query (moisture) ─┐
    sqlite_query (ETo)       │   each writes rows to a bb key
    format_daily_report      ├─> reads both, writes the message string
    discord_notify           ┘   reads the message, posts via webhook

Composite, not solution: it does NOT open a KB or call
`asm_terminate_system`. The caller (P0.7's `daily_report` solution)
provides those. Keeping the composite pure means it can be reused
inside richer wrappers — e.g. a sequence_til_pass that retries the
report path on failure — without forcing them to re-open a column
around it.

Skill = atomic, sub-tree = composed behavior. None of the four leaves
knows about "daily report" specifically; the composite is what makes
them a daily report. This is the architectural thesis from prior
sessions, finally exercised on real code.

Slots:
  name                     required STRING — used as suffix for each
                                               leaf's `name` slot so
                                               sibling composites don't
                                               collide on one-shot
                                               registration.
  moisture_db_path         required STRING — moisture SQLite path.
  cimis_db_path            required STRING — CIMIS SQLite path.
  webhook_url              required STRING — Discord webhook (secret).
  moisture_lookback_hours  optional INT    — default 48; matches the
                                               persistence window of
                                               `lorwan_moisture` (kept
                                               48h since the prior
                                               session's lookback bump).
  cimis_lookback_days      optional INT    — default 7.
  cimis_station            optional STRING — default "237" (Glenn's
                                               farm).
"""

from __future__ import annotations

from template_language import define_template, use_template


# Blackboard key conventions — namespaced under the composite's name to
# avoid collisions with siblings. We append `<name>` so two daily_report
# composites in one KB couldn't shadow each other.
_BB_MOISTURE = "daily_report.{name}.moisture_rows"
_BB_ETO = "daily_report.{name}.eto_rows"
_BB_TEXT = "daily_report.{name}.text"


def daily_report(
    *,
    name: str,
    moisture_db_path: str,
    cimis_db_path: str,
    webhook_url: str,
    moisture_lookback_hours: int = 48,
    cimis_lookback_days: int = 7,
    cimis_station: str = "237",
):
    """Compose the daily-report sequence into the caller's open scope."""
    bb_moisture = _BB_MOISTURE.format(name=name)
    bb_eto = _BB_ETO.format(name=name)
    bb_text = _BB_TEXT.format(name=name)

    # 1. moisture — per-device latest reading + uplink count over the window.
    moisture_sql = (
        "SELECT device_id, "
        "       MAX(received_at) AS latest_ts, "
        "       (SELECT m2.value FROM moisture m2 "
        "         WHERE m2.device_id = m.device_id "
        "         AND m2.measurement_id = 4108 "
        f"        AND m2.received_at > datetime('now', '-{moisture_lookback_hours} hours') "
        "         ORDER BY m2.received_at DESC LIMIT 1) AS latest_value, "
        "       COUNT(DISTINCT received_at) AS uplinks_in_window "
        "FROM moisture m "
        "WHERE measurement_id = 4108 "
        f"AND received_at > datetime('now', '-{moisture_lookback_hours} hours') "
        "GROUP BY device_id ORDER BY device_id"
    )
    use_template(
        "user.leaves.chain_tree.sqlite_query",
        name=f"daily_query_moisture_{name}",
        db_path=moisture_db_path,
        sql=moisture_sql,
        result_bb_key=bb_moisture,
    )

    # 2. ETo — last `cimis_lookback_days` finalised values for the station.
    eto_sql = (
        "SELECT date, value, unit FROM cimis_eto "
        f"WHERE target_kind = 'station' AND target = '{cimis_station}' "
        "AND item = 'DayAsceEto' "
        f"AND date >= date('now', '-{cimis_lookback_days} days') "
        "ORDER BY date DESC"
    )
    use_template(
        "user.leaves.chain_tree.sqlite_query",
        name=f"daily_query_eto_{name}",
        db_path=cimis_db_path,
        sql=eto_sql,
        result_bb_key=bb_eto,
    )

    # 3. format — read the two row lists, write the message string.
    use_template(
        "project.farm_soil.leaves.chain_tree.format_daily_report",
        name=f"daily_format_{name}",
        moisture_bb_key=bb_moisture,
        eto_bb_key=bb_eto,
        result_bb_key=bb_text,
    )

    # 4. notify — read the message string, post to Discord.
    use_template(
        "user.leaves.chain_tree.discord_notify",
        name=f"daily_notify_{name}",
        webhook_url=webhook_url,
        content_bb_key=bb_text,
    )


define_template(
    path="project.farm_soil.composites.chain_tree.daily_report",
    fn=daily_report,
    kind="composite",
    engine="chain_tree",
    slot_examples={
        "name": "main",
        "moisture_db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "cimis_db_path": "/var/lib/farm_soil/farm_soil_cimis.sqlite",
        "webhook_url": "https://discord.com/api/webhooks/<id>/<token>",
        "moisture_lookback_hours": 48,
        "cimis_lookback_days": 7,
        "cimis_station": "237",
    },
)
