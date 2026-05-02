# ChainTree Discord Integration — continue.md

**Project:** Personal farm software robot — Discord channel for alerts, status, and operator interaction
**Stack context:** ChainTree behavior trees, NATS JetStream, SQLite (local) + PostgreSQL ltree knowledge base, LuaJIT runtime on Pi-class hardware
**Status:** Channel selection complete (Discord). Server/bot setup not yet started.

---

## 1. Goal

Stand up Discord as the primary mobile channel for the farm robot to:

1. **Push alerts** to a phone (severity-routed, with role-mention escalation on CRITICAL)
2. **Push status reports** (morning summary, end-of-day rollup, on-demand)
3. **Receive commands** (ack alerts, snooze, query state, trigger actions like "run pump 5 min")
4. **Maintain a long-term searchable archive** of farm events without paying for retention

Discord chosen over Telegram, Slack, WhatsApp because:
- Channel-based routing (severity → channel) maps naturally to NATS subject hierarchy
- Free tier has no message history cap and no bot/integration cap
- Rich embeds + interactive components (buttons, modals) good enough for an operator UI
- Sanctioned bot API, no TOS gray area
- "BOT" tag on bot users is acceptable — we want the alert sender visibly distinct

---

## 2. Architecture

```
┌──────────────────┐       ┌─────────────────┐       ┌──────────────────┐
│  ChainTree       │       │  NATS JetStream │       │  Discord Bridge  │
│  behavior trees  │──────▶│  farm.alert.>   │──────▶│  (LuaJIT worker) │
│  (sensors, SOPs) │       │  farm.status.>  │       │                  │
└──────────────────┘       │  farm.cmd.>     │       └────────┬─────────┘
         ▲                 │  farm.ack.>     │                │
         │                 └────────▲────────┘                │ HTTPS
         │                          │                         ▼
         │                          │              ┌──────────────────┐
         │                          └──────────────│  Discord API     │
         │                                         │  (api/v10)       │
         │                                         └────────┬─────────┘
         │                                                  │
         │                                                  │ Gateway WS
         │                                                  ▼
         │                                         ┌──────────────────┐
         └─────────────────────────────────────────│  Mobile Discord  │
                              (button taps,        │  app on phone    │
                              slash commands)      └──────────────────┘
```

The bridge is the only component that talks Discord protocol. ChainTree never speaks Discord directly — it publishes structured events on NATS, the bridge translates. This keeps Discord as a swappable transport (could be Telegram, Slack, ntfy in parallel or as fallback).

---

## 3. Phase 1 — Server Setup (manual, ~10 min)

### 3.1 Account and server

- Create Discord account (or reuse existing). Use a long-term email. Enable 2FA (Settings → Security).
- Create server: `+` button → "Create My Own" → "For me and my friends" → name it "Farm Ops".
- Delete default `#general` and voice channel.

### 3.2 Channel structure

Create as Text channels under an "Alerts" category:

| Channel        | Purpose                                  | Mobile notification setting |
|----------------|------------------------------------------|------------------------------|
| `#critical`    | Pump failure, freeze warning, fire/flood | All Messages                 |
| `#errors`      | Sensor offline, comms loss, calibration  | All Messages                 |
| `#warnings`    | Threshold approaching, battery low       | Only @mentions               |
| `#info`        | Routine state changes, ack confirmations | Nothing (silent archive)     |
| `#status`      | Morning/evening rollups, daily reports   | Only @mentions               |

Optional second category "Zones" for per-area channels (`#north-field`, `#pumps`, `#greenhouse`) — defer until base flow works.

### 3.3 Roles for escalation

Server Settings → Roles → Create Role:
- `on-call` — assign to self (and family members later). Used for CRITICAL pings.
- `farmhands` — broader group, for ERRORS during work hours.

Enable Developer Mode (User Settings → Advanced) to be able to right-click and copy role IDs and channel IDs.

### 3.4 Webhooks (one per channel)

For each channel: gear icon → Integrations → Webhooks → New Webhook → name "ChainTree" → copy URL.

Store URLs in `/etc/chaintree/discord.conf` (mode 0600, owned by chaintree user):

```
[webhooks]
critical  = https://discord.com/api/webhooks/...
errors    = https://discord.com/api/webhooks/...
warnings  = https://discord.com/api/webhooks/...
info      = https://discord.com/api/webhooks/...
status    = https://discord.com/api/webhooks/...

[roles]
on_call   = 123456789012345678
farmhands = 234567890123456789

[server]
guild_id  = 345678901234567890
```

### 3.5 Bot application (only needed for interactivity)

Skip if Phase 2 (webhook MVP) is sufficient. For Phase 3:

1. discord.com/developers/applications → New Application → "ChainTree"
2. Bot tab → Add Bot → copy token (this is a bearer credential, treat like a private key)
3. Privileged Gateway Intents: enable **Message Content Intent** if you want the bot to read free-form messages (not needed for slash commands only)
4. OAuth2 → URL Generator → scopes: `bot`, `applications.commands` → permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`, `Read Message History`
5. Visit generated URL, authorize bot into "Farm Ops" server

Add to config:
```
[bot]
token       = MTAxxxxxxx...
app_id      = 345678901234567891
public_key  = (from General Information tab; needed if using HTTPS interactions instead of gateway)
```

---

## 4. Phase 2 — Webhook MVP (send-only)

Goal: ChainTree publishes alerts to NATS, bridge POSTs to Discord. No interactivity yet. ~50 lines of LuaJIT.

### 4.1 NATS subject taxonomy

```
farm.alert.<severity>.<zone>.<source>     payload: AlertEvent
farm.status.<kind>                        payload: StatusReport
farm.ack.<alert_id>                       payload: AckEvent (Phase 3)
farm.cmd.<verb>.<target>                  payload: Command (Phase 3)
```

Examples:
- `farm.alert.critical.north_field.pump_01` — pump down
- `farm.alert.warning.greenhouse.temp_03`  — high temp warning
- `farm.status.morning`                     — daily rollup
- `farm.ack.alert_8821`                     — operator ack

### 4.2 Event payload (CBOR-encoded, matches existing ChainTree wire format)

```
AlertEvent {
  alert_id    : string         // ULID, generated by ChainTree at emit
  fingerprint : uint32         // FNV-1a(source ‖ code) for dedup
  severity    : enum            // INFO | WARN | ERROR | CRITICAL
  source      : string         // ltree path: north_field.pumps.pump_01
  code        : string         // PUMP_OFFLINE, MOISTURE_LOW, etc.
  message     : string         // human-readable
  fields      : map<string,    // key/value details for embed
                    string>
  ts          : uint64         // monotonic ms since epoch
  eui64       : bytes(8)       // device identity (optional)
}
```

### 4.3 LuaJIT bridge skeleton

```lua
-- discord_bridge.lua
local nats   = require("nats")        -- existing FFI binding
local http   = require("resty.http")  -- or socket.http + ssl.https
local cjson  = require("cjson.safe")
local cbor   = require("cbor")        -- existing
local cfg    = require("config").load("/etc/chaintree/discord.conf")

local SEVERITY_TO_CHANNEL = {
  CRITICAL = "critical",
  ERROR    = "errors",
  WARN     = "warnings",
  INFO     = "info",
}

local SEVERITY_COLOR = {
  CRITICAL = 15158332,  -- red
  ERROR    = 15105570,  -- orange
  WARN     = 15844367,  -- yellow
  INFO     = 3447003,   -- blue
}

local SEVERITY_EMOJI = {
  CRITICAL = "🔴",
  ERROR    = "🟠",
  WARN     = "🟡",
  INFO     = "🔵",
}

local function build_embed(evt)
  local fields = {}
  for k, v in pairs(evt.fields or {}) do
    fields[#fields+1] = { name = k, value = tostring(v), inline = true }
  end
  return {
    title       = evt.code .. ": " .. evt.message,
    description = evt.source,
    color       = SEVERITY_COLOR[evt.severity] or 0,
    fields      = fields,
    footer      = { text = "ChainTree • " .. evt.alert_id },
    timestamp   = iso8601(evt.ts),
  }
end

local function post_alert(evt)
  local channel = SEVERITY_TO_CHANNEL[evt.severity]
  local url     = cfg.webhooks[channel]
  if not url then return end

  local body = {
    embeds = { build_embed(evt) },
    allowed_mentions = { parse = {} },  -- block all mentions in content
  }

  -- CRITICAL: prepend role mention
  if evt.severity == "CRITICAL" then
    body.content = "<@&" .. cfg.roles.on_call .. ">"
    body.allowed_mentions.roles = { cfg.roles.on_call }
  end

  local httpc = http.new()
  local res, err = httpc:request_uri(url, {
    method  = "POST",
    body    = cjson.encode(body),
    headers = { ["Content-Type"] = "application/json" },
  })

  if not res then
    log.error("discord post failed: ", err)
    return
  end

  -- Honor rate limit
  if res.status == 429 then
    local retry = tonumber(res.headers["retry-after"]) or 1
    log.warn("discord rate limited, sleeping ", retry, "s")
    sleep(retry)
    return post_alert(evt)  -- retry once
  end

  if res.status >= 400 then
    log.error("discord ", res.status, ": ", res.body)
  end
end

-- NATS subscription
local sub = nats.subscribe("farm.alert.>", function(msg)
  local evt = cbor.decode(msg.data)
  post_alert(evt)
end)

nats.run()
```

### 4.4 Test sequence

1. `curl -X POST -H "Content-Type: application/json" -d '{"content":"hello"}' <webhook_url>` — bare webhook works.
2. POST a hand-built embed JSON — embed renders correctly in mobile app.
3. Publish a synthetic CBOR AlertEvent on `farm.alert.warning.test.synth` — bridge picks up and posts.
4. Test all 4 severities → all 4 channels.
5. Test CRITICAL → on-call role gets pinged on phone with proper notification.
6. Force a 429 (post 35 messages in 60s) → bridge backs off and retries.

---

## 5. Phase 3 — Bot for Interactivity

Once webhook MVP is solid, add bot for:
- **Inline buttons** on alerts: Ack, Snooze 1h, Mute zone
- **Slash commands**: `/status`, `/moisture <zone>`, `/pump <zone> <duration>`, `/silence <zone> <duration>`
- **Receive replies in threads**: operator notes attached to alert

### 5.1 Bot connection options

- **Gateway WebSocket (Socket Mode equivalent)**: bot maintains outbound WS to Discord. Works behind NAT, no public endpoint needed. Right choice for the Pi.
- **HTTPS interactions endpoint**: Discord POSTs to a public URL. Requires public TLS endpoint and signature verification. Skip.

LuaJIT WebSocket: use `lua-websockets` or `lua-resty-websocket`. Heartbeat every ~41s, handle resume tokens, reconnect on disconnect with exponential backoff capped at 60s.

### 5.2 Slash command registration

One-shot HTTP PUT at startup to register commands:
```
PUT /api/v10/applications/{app_id}/guilds/{guild_id}/commands
Headers: Authorization: Bot {token}
Body: [
  { "name": "status",  "description": "Farm status snapshot",
    "options": [...] },
  { "name": "moisture", "description": "Soil moisture for zone",
    "options": [{ "name": "zone", "type": 3, "required": true,
                  "choices": [...] }] },
  { "name": "pump",    "description": "Run pump",
    "options": [
      { "name": "zone", "type": 3, "required": true },
      { "name": "minutes", "type": 4, "required": true,
        "min_value": 1, "max_value": 30 }
    ] }
]
```

Guild commands are instant; global commands take up to an hour to propagate. Use guild commands for development.

### 5.3 Interaction handling

Bot receives `INTERACTION_CREATE` events on the gateway. Three types matter:
- `APPLICATION_COMMAND` (type 2) — slash commands
- `MESSAGE_COMPONENT` (type 3) — button/select clicks
- `MODAL_SUBMIT` (type 5) — modal form submissions

Each interaction has a `token` valid for 15 min and `id`. Respond with:
```
POST /api/v10/interactions/{id}/{token}/callback
{ "type": 4, "data": { "content": "Ack received" } }   // immediate reply
```
or defer with type 5 and follow up with PATCH later if processing takes >3s.

### 5.4 Round-trip flow for ack button

```
1. Alert posted with embed + components:
   components: [{ type: 1, components: [
     { type: 2, style: 4, label: "Ack",
       custom_id: "ack:alert_8821" },
     { type: 2, style: 2, label: "Snooze 1h",
       custom_id: "snooze:alert_8821:3600" },
   ]}]

2. User taps Ack on phone.

3. Bot receives INTERACTION_CREATE with custom_id "ack:alert_8821".

4. Bridge publishes farm.ack.alert_8821 on NATS with operator user_id.

5. ChainTree subscribes to farm.ack.>, updates alerts table:
     UPDATE alerts SET ack_ts = now(), ack_by = $1 WHERE alert_id = $2

6. Bridge edits the original message (PATCH .../messages/{id}) to remove
   the buttons and append "✅ Acked by <user> at HH:MM" to the embed.
```

---

## 6. SQLite schema (additions to existing alerts table)

```sql
-- existing
CREATE TABLE alerts (
  alert_id     TEXT PRIMARY KEY,
  fingerprint  INTEGER NOT NULL,
  severity     TEXT NOT NULL,
  source       TEXT NOT NULL,        -- ltree-style
  code         TEXT NOT NULL,
  message      TEXT NOT NULL,
  fields_json  TEXT,
  first_seen   INTEGER NOT NULL,
  last_seen    INTEGER NOT NULL,
  count        INTEGER NOT NULL DEFAULT 1,
  ack_ts       INTEGER,
  ack_by       TEXT
);

-- discord-specific
CREATE TABLE alert_discord (
  alert_id      TEXT PRIMARY KEY REFERENCES alerts(alert_id),
  channel_id    TEXT NOT NULL,
  message_id    TEXT NOT NULL,        -- needed to PATCH/edit later
  posted_ts     INTEGER NOT NULL,
  thread_id     TEXT                  -- if a thread was opened for discussion
);

CREATE INDEX idx_discord_msg ON alert_discord(message_id);
```

The bridge writes `alert_discord` after a successful POST so subsequent edits (ack confirmation, dedup count update) can find the message.

---

## 7. Dedup integration

The existing fingerprint dedup logic (FNV-1a hash of source‖code, 5 min suppression window) extends naturally:

- On duplicate within window: do **not** post a new Discord message. Instead, PATCH the existing message — update the count in the embed footer ("seen 3x in 4 min"), bump `last_seen` in DB.
- On first occurrence after window expiry: post fresh, new `alert_id`.
- On CRITICAL: bypass dedup for the first 3 occurrences (so you actually wake up), then suppress.

Pseudocode in the publish path (ChainTree side, before NATS publish):
```
fp = fnv1a(source .. code)
existing = sqlite.get_active_alert_by_fingerprint(fp, window=300)
if existing and (severity != CRITICAL or existing.count >= 3):
    sqlite.bump_count(existing.alert_id)
    nats.publish("farm.alert.update." .. severity, AlertUpdate{...})
else:
    new_id = ulid()
    sqlite.insert_alert(new_id, fp, ...)
    nats.publish("farm.alert." .. severity .. "." .. zone .. "." .. source, evt)
```

Bridge subscribes to both `farm.alert.>` (new) and `farm.alert.update.>` (PATCH existing).

---

## 8. Mobile configuration (per-device, must do on each phone)

1. Install Discord, log into account that owns Farm Ops server.
2. Per-channel notification override (long-press channel → Notification Settings):
   - `#critical`, `#errors` → All Messages
   - `#warnings`, `#status` → Only @mentions
   - `#info` → Nothing
3. Server-level default: Only Mentions (catch-all)
4. **Disable battery optimization** for Discord on Android (Settings → Battery → App Battery Usage → Discord → Don't optimize). Without this, Samsung/Xiaomi/etc. will silently kill the background process and you'll lose alerts.
5. Test: send a CRITICAL synthetic event, confirm phone notification fires within 5 seconds even with screen off.

---

## 9. Operational notes

### Rate limits
- 30 messages/min per webhook
- 5 messages/2s burst per webhook
- 50 requests/sec global per bot token
- 429 responses include `retry-after`; honor it
- Fingerprint dedup is load-bearing — without it, a flapping sensor will hit 429 and silence real alerts

### Security
- Webhook URLs are bearer credentials. Anyone with the URL can post to your channel. Rotate immediately if leaked (regenerate from channel settings).
- Bot token is also a bearer credential. Never commit to repo, even private. Discord scrapes leaked tokens and revokes them.
- Server should be private. Revoke all standing invites: Server Settings → Invites.
- 2FA on owner account is mandatory.

### Outages
- Discord has occasional outages (status.discord.com). For CRITICAL alerts, consider dual-publish to a secondary channel (ntfy self-hosted on the Pi, or Pushover) so single-service failure doesn't silence frozen-pipe-at-3am.
- Bridge should buffer to disk if NATS or Discord is unreachable, replay on reconnect. NATS JetStream gives durability for ChainTree → bridge; bridge → Discord retries are bridge's responsibility.

### File uploads
- Free tier: 10 MB per file. Sufficient for thermal images, sparklines, short clips.
- For larger artifacts (multi-day chart videos), host on Pi, embed URL in message — Discord auto-renders images and short videos from arbitrary HTTPS.

---

## 10. Testing checklist

Before declaring Phase 2 done:

- [ ] Webhook POST works from `curl`
- [ ] Embed renders correctly on mobile (colors, fields, footer)
- [ ] All 4 severities route to correct channels
- [ ] CRITICAL pings `@on-call` role and triggers phone notification
- [ ] `allowed_mentions` blocks accidental `@everyone` injection from sensor data
- [ ] 429 rate limit handled with retry-after
- [ ] Bridge reconnects to NATS after network blip
- [ ] Bridge reconnects to Discord after API outage (test by blocking discord.com in iptables for 60s)
- [ ] Mobile notifications arrive within 5s with phone screen off
- [ ] Battery optimization disabled and notifications still arrive after 6h idle

Before declaring Phase 3 done:

- [ ] `/status` returns farm snapshot
- [ ] Ack button updates alerts table and edits message to show ack
- [ ] Snooze button suppresses fingerprint for the requested window
- [ ] Slash command `/pump north 5` triggers ChainTree pump subtree, returns confirmation
- [ ] Bot reconnects to gateway after WebSocket drop
- [ ] Slash command auth: only allow members of the server (Discord enforces by default), optionally restrict to specific user IDs in bridge

---

## 11. Future extensions

- **Per-zone channels** with role mappings (one role per zone, mute zones independently)
- **Daily morning briefing** in `#status` — scheduled cron publishes `farm.status.morning`, bridge posts embed with sensor summary, weather, scheduled tasks
- **Image attachments** — thermal cam snapshots on temp alerts, soil moisture sparkline on irrigation cycle completion
- **Threads for incidents** — auto-create thread on CRITICAL, post follow-up updates as thread replies, close thread on ack
- **Voice channel TTS announcements** — bot joins voice channel, speaks alert. Useful for shop or barn with always-on speaker. Discord supports this via Opus streams.
- **Cross-publish to ntfy** — primary on Discord, mirror CRITICAL to self-hosted ntfy with priority 5 for DND bypass
- **OpenClaw bridge** — if eventually adopting OpenClaw as the agent layer, ChainTree publishes events on NATS, OpenClaw subscribes and uses its own Discord transport. ChainTree's bridge becomes redundant for the Discord channel but the NATS subject taxonomy is unchanged.

---

## 12. Open questions / decisions to make

1. **Single bot or umbrella bot?** Current plan: single "ChainTree" bot. Alternative: separate "Irrigation", "SensorNet", "Harvest" bots for visual clarity in operator list. Discord has no cap, so this is style not constraint.
2. **Timezone for timestamps in embeds.** ISO8601 UTC vs local time. Discord renders `<t:UNIX:F>` markdown as user-local time automatically — prefer that.
3. **Retention beyond Discord.** Discord keeps history forever on free, but if account is lost, history is lost. SQLite events table is the durable record; Discord is a view onto it. Confirm SQLite retention policy (keep all events forever? rotate after N years?).
4. **Family member access.** When adding family, give them their own role and on-call assignment, not the owner account. Generate single-use invite, revoke after they join.
5. **Off-network mode.** When Pi loses internet, Discord posts fail. Bridge should buffer to local SQLite and replay on reconnect. Decide buffer cap (drop oldest? drop INFO/WARN, keep ERROR/CRITICAL?).

---

## 13. Next concrete steps

1. Create Discord account if needed; create "Farm Ops" server, channels, roles per §3.
2. Create 5 webhooks, populate `/etc/chaintree/discord.conf`.
3. Implement webhook POST function in LuaJIT, test with synthetic CBOR events.
4. Wire NATS subscription `farm.alert.>` to bridge.
5. Add `alert_discord` table, persist message_id on post.
6. Test all severities, rate limit, reconnect.
7. **Stop here, run for a week** before adding bot/interactivity. Webhook-only is enough to learn whether the channel routing and notification model fits how you actually operate the farm.
8. Phase 3 starts only after a week of real-world use surfaces what's missing.

