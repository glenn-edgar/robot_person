"""user.leaves.chain_tree.discord_notify — wrap DiscordNotifier as a leaf.

Registers a one-shot that constructs a `DiscordNotifier` from slot
values, calls `send()`, and logs the outcome via the engine logger.
Multiple instances coexist by giving each a distinct `name` slot —
the one-shot is registered as `DISCORD_NOTIFY_<name>`.

Slots:
  name              required STRING — disambiguates one-shot registration.
  webhook_url       required STRING — Discord channel webhook URL
                                       (treat as secret).
  content           required STRING — message text. Truncated to
                                       2000 chars by the skill.
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
    content: str,
    username: str = "",
):
    """Post one message to Discord on tick."""

    def _do_send(handle, node):
        logger = handle["engine"].get("logger") or print
        notifier = DiscordNotifier(webhook_url, logger=logger)
        ok, err = notifier.send(content, username=username or None)
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
        "username": "farm_soil_bot",
    },
)
