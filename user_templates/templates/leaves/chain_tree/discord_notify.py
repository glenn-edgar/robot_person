"""user.leaves.chain_tree.discord_notify — wrap DiscordNotifier as a leaf.

Registers a one-shot that constructs a `DiscordNotifier` from slot
values, calls `send()`, and logs the outcome via the engine logger.
Multiple instances coexist by giving each a distinct `name` slot —
the one-shot is registered as `DISCORD_NOTIFY_<name>`.

Two ways to supply message content:

  - **Static** — set `content` to the literal string at template time.
    Used when the message is fixed (e.g. a smoke notification).
  - **Blackboard** — set `content_bb_key` to a blackboard key. At
    execution time the leaf reads `handle["blackboard"][content_bb_key]`
    and posts that. Used when an upstream leaf produced the message
    (e.g. `sqlite_query` formatting a daily report into the blackboard,
    then this leaf shipping it).

Exactly one mode is active per instance; setting both is a template-
time error. If `content_bb_key` resolves to a missing/empty value at
execution time, the send is skipped and the outcome is logged — that
matches the skill's own "content is empty" branch and lets the
upstream sub-tree decide retry policy.

Slots:
  name              required STRING — disambiguates one-shot registration.
  webhook_url       required STRING — Discord channel webhook URL
                                       (treat as secret).
  content           optional STRING — static message text. Mutually
                                       exclusive with content_bb_key.
                                       Truncated to 2000 chars by the
                                       skill.
  content_bb_key    optional STRING — blackboard key whose value is
                                       posted at execution time.
                                       Mutually exclusive with content.
  username          optional STRING — display name override for this
                                       single message. Empty string =
                                       use the skill default ("farm_robot").
"""

from __future__ import annotations

from skills.discord import DiscordNotifier

from template_language import ct, define_template


def discord_notify(
    *,
    name: str,
    webhook_url: str,
    content: str = "",
    content_bb_key: str = "",
    username: str = "",
):
    """Post one message to Discord on tick (static or blackboard-driven)."""
    if content and content_bb_key:
        raise ValueError(
            f"discord_notify[{name}]: set either `content` or "
            f"`content_bb_key`, not both"
        )
    if not content and not content_bb_key:
        raise ValueError(
            f"discord_notify[{name}]: one of `content` or "
            f"`content_bb_key` is required"
        )

    def _do_send(handle, node):
        logger = handle["engine"].get("logger") or print
        if content_bb_key:
            value = handle["blackboard"].get(content_bb_key)
            if value is None or value == "":
                logger(
                    f"discord_notify[{name}]: skipped — blackboard key "
                    f"{content_bb_key!r} missing or empty"
                )
                return
            message = str(value)
        else:
            message = content
        notifier = DiscordNotifier(webhook_url, logger=logger)
        ok, err = notifier.send(message, username=username or None)
        if ok:
            logger(f"discord_notify[{name}]: sent ok")
        else:
            logger(f"discord_notify[{name}]: send FAILED — {err}")

    one_shot_name = f"DISCORD_NOTIFY_{name}"
    ct.add_one_shot(one_shot_name, _do_send)
    ct.asm_one_shot(one_shot_name)


define_template(
    path="user.leaves.chain_tree.discord_notify",
    fn=discord_notify,
    kind="leaf",
    engine="chain_tree",
    slot_examples={
        "name": "farm_status",
        "webhook_url": "https://discord.com/api/webhooks/<id>/<token>",
        "content": "farm_soil: morning report ready",
        "content_bb_key": "",
        "username": "farm_soil_bot",
    },
)
