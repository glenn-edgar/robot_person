"""user.leaves.chain_tree.sqlite_query — wrap SqliteQuery as a leaf.

Registers a one-shot that constructs a `SqliteQuery` from slot values,
calls `query()`, and writes the resulting list-of-dicts to the
blackboard under `result_bb_key`. Multiple instances coexist by giving
each a distinct `name` slot — the one-shot is registered as
`SQLITE_QUERY_<name>`.

This is the read-side counterpart to fetch leaves (lorwan_moisture,
cimis_eto). Composes with downstream leaves (format_*, discord_notify)
that read the rows from the blackboard. Per the namespace rule the
blackboard is the user-owned hand-off channel; the engine itself does
not write there.

Slots:
  name           required STRING — disambiguates one-shot registration.
  db_path        required STRING — SQLite file path. Read-only.
  sql            required STRING — parameterised SELECT statement.
                                     Use SQLite functions for relative
                                     dates (e.g. `datetime('now', '-24 hours')`)
                                     when slot-time literals aren't enough.
  result_bb_key  required STRING — blackboard key to write rows under.

On error (missing DB, syntax error, write attempt): writes an empty
list to the blackboard and logs the error. Downstream leaves that
expected rows can detect this by checking the list length.
"""

from __future__ import annotations

from skills.sqlite_query import SqliteQuery

from template_language import ct, define_template


def sqlite_query(
    *,
    name: str,
    db_path: str,
    sql: str,
    result_bb_key: str,
):
    """Run a SELECT and stash the rows on the blackboard."""

    def _do_query(handle, node):
        logger = handle["engine"].get("logger") or print
        q = SqliteQuery(db_path, logger=logger)
        rows, err = q.query(sql)
        if err is not None:
            logger(
                f"sqlite_query[{name}]: FAILED — {err}; writing [] to "
                f"bb[{result_bb_key!r}]"
            )
            handle["blackboard"][result_bb_key] = []
            return
        handle["blackboard"][result_bb_key] = rows
        logger(
            f"sqlite_query[{name}]: wrote {len(rows)} row(s) to "
            f"bb[{result_bb_key!r}]"
        )

    one_shot_name = f"SQLITE_QUERY_{name}"
    ct.add_one_shot(one_shot_name, _do_query)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="user.leaves.chain_tree.sqlite_query",
    fn=sqlite_query,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "moisture_recent",
        "db_path": "/var/lib/farm_soil/farm_soil.sqlite",
        "sql": (
            "SELECT device_id, value FROM moisture "
            "WHERE measurement_id = 4108 "
            "AND received_at > datetime('now', '-24 hours') "
            "ORDER BY received_at DESC"
        ),
        "result_bb_key": "daily_report.moisture_rows",
    },
)
