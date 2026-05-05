# discord — continue

## Where we are (2026-05-05)

Fresh skill following the `skills/` convention.

  webhook_client.py — `post_message(url, payload, timeout_s)`. Pure
                       urllib + json. Discord returns 204 on success,
                       maps HTTP errors to (False, error_msg).
  main.py           — `DiscordNotifier` class. `send(content, *,
                       username=None)` -> (ok, error_msg). Truncates
                       at CONTENT_MAX = 2000 chars (Discord's limit).
                       `_post` injection point for tests; default is
                       webhook_client.post_message.

## Why webhook (not bot)

Webhooks are stateless: URL + JSON POST. No application registration,
no OAuth, no library. The URL is the auth — treat as secret.

A real bot is needed only for *receiving* messages (commands), not
sending notifications. Glenn's farm robot is one-way (robot ->
Glenn), so webhook is the right fit and avoids the bot setup tax.

## Limits to remember

- 2000 chars per message; the skill auto-truncates with an ellipsis
  and logs it.
- Rate limit: per-webhook 5 messages per 2 seconds (Discord's docs).
  We don't currently throttle; for high-volume notification storms
  we'd need a queue/coalesce step. Not relevant for irrigation events.
- 204 No Content is success; 4xx returns a JSON error body the skill
  surfaces in `error_msg`.

## Next session

1. Wire the chain_tree wrapper at
   `user_templates/templates/leaves/chain_tree/discord_notify.py` —
   in this commit. Slots: webhook_url, content, username.
2. Optional: add `send_embed(title, description, fields, color)` for
   richer farm-status messages (e.g. green for OK, red for fault).
   Discord embeds support up to 25 fields per embed.
3. Optional: build a project-local leaf in farm_soil that reads the
   moisture/cimis DBs and posts a daily summary embed.
