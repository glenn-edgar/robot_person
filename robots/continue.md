# Robots + Skills + Deployment — Design State and Continuation

This file is the primary continuation document for the
robots/skills/deployments layer that sits on top of `template_language`.
For the engine-shape spec see `template_language/continue.md`; for the
s_engine port see `continue.md` at the repo root. This file is for the
real-deployment story: skills as atomic Python, leaves wrapping them
for chain_tree, sub-trees composing leaves into behaviors, robots as
per-deployment projects, deployments as per-host process manifests.

---

## SESSION LOG — 2026-05-05: scaffolding + 3 skills + first robot end-to-end

Big session. **47/47 tests passing**, 4 commits, ~3,800 lines added
across `skills/`, `user_templates/`, and `robots/farm_soil/`. The
template_language design from prior sessions ran into real data for
the first time and survived intact — every architectural prediction
held up; the only adjustments were data-shape mismatches at the wire
(SenseCAP frame layout, CIMIS spatial-target rejection, Discord
Cloudflare User-Agent block).

### Architecture established

  Three new top-level layers landed alongside the existing
  template_language / chain_tree / s_engine / examples directories:

  ```
  robot_person/
  ├── skills/                  # NEW — engine-agnostic Python; one class per skill + __main__
  │   ├── README.md            # convention doc
  │   ├── lorwan_moisture/     # input — TTN soil sensors -> SQLite
  │   ├── cimis/               # input — California ETo API -> SQLite
  │   └── discord/             # output — webhook notification
  │
  ├── user_templates/          # NEW — chain_tree wrappers around skill classes
  │   └── templates/leaves/chain_tree/
  │       ├── lorwan_moisture.py
  │       ├── cimis_eto.py
  │       └── discord_notify.py
  │
  ├── robots/                  # NEW — per-deployment projects (multi-root prefix project.<name>)
  │   └── farm_soil/           # first robot — Glenn's farm
  │       ├── bootstrap.py     # registers prefix=project.farm_soil
  │       ├── hardware.yaml
  │       ├── config/{dev,prod}.yaml
  │       ├── secrets/         # gitignored ttn.env + .env.example
  │       ├── report.py        # moisture report (per-uplink time-series)
  │       ├── cimis_report.py  # CIMIS report (per-day, station+spatial side-by-side)
  │       ├── eto_237_demo.py  # standalone irrigation-path demo
  │       ├── run.py           # moisture inspect runner
  │       ├── run_cimis.py     # CIMIS inspect runner
  │       ├── conftest.py
  │       ├── templates/{leaves,solutions}/chain_tree/
  │       └── tests/
  │
  └── deployments/             # PLANNED, not yet built — site-keyed process manifests
      └── farm/                # systemd units + inventory.yaml
  ```

### Skill convention (locked)

  Captured in `skills/README.md`:

  - One class per skill in `main.py`; one responsibility (fetch, OR
    query, OR notify — never two).
  - Engine-agnostic — no chain_tree / s_engine / template_language
    imports inside a skill. Wrappers in `user_templates/` (or per-
    robot template dirs) bind a skill class to one engine.
  - `if __name__ == "__main__":` is a real smoke test that hits real
    systems; the skill must be runnable standalone.
  - Helpers (api client, decoder, db schema) live alongside `main.py`
    in the skill directory; only `main.py` exports the public class.
  - Secrets out of code — env files in `robots/<robot>/secrets/`,
    gitignored.

  **Two-responsibility skills get split.** lorwan_moisture is fetch-
  only; the read-side ("run SQL, return rows") is the deferred
  `sqlite_query` skill (next session, see below).

### What each skill actually does

  **lorwan_moisture** (input):
  - `MoistureFetcher(...).tick()` polls TTN v3 storage API,
    decodes SenseCAP S2105 frames (7 bytes/measurement, NOT the
    8-byte layout the original `lorwan_moisture/continue.md`
    hypothesised — that "type byte" was actually the high byte of
    the LE-u16 measurement id, coincidentally always 0x10 for
    SenseCAP IDs).
  - Prefers TTN's `decoded_payload.messages` array, falls back to
    byte-frame decode if the device's payload formatter isn't
    configured.
  - Multi-gateway: picks strongest gateway (highest RSSI) for the
    `link` row, stores `gateway_count` separately.
  - Battery: `last_battery_percentage` only counted "in this uplink"
    when its f_cnt matches the uplink's f_cnt (TTN attaches the
    cached value to every uplink; equality is the only "carried
    here" signal).

  **cimis** (input):
  - `CimisFetcher(...).tick()` queries the CIMIS Web API. Default
    `data_items="day-asce-eto"` (works for both station and spatial
    targets; the legacy `day-eto` is station-only — spatial requests
    fail with ERR2006).
  - `skip_provisional=True` (default) drops `qc='A'` rows at insert
    time. Critical: without this, INSERT OR IGNORE on the PK
    `(target_kind, target, date, item)` would lock today's drifting
    partial-day value in place and silently reject tomorrow's
    finalised version.
  - `check.is_data_present(... require_finalised=True)` is the
    predicate the upper-level chain uses for "did yesterday's row
    finalise yet?". Timezone is `America/Los_Angeles` (CIMIS'
    reporting frame).
  - Spatial CIMIS via raw lat/lng: rejected with ERR2006 across
    every format variant probed (bare, parens, semicolon, brackets,
    alt endpoints). Zip-code targets work but the centroid
    mislocates Glenn's farm (different elevation, distance from
    coast). Spatial slot left in place but defaulted to `""` —
    irrigation uses station 237 only.

  **discord** (output, first IO skill):
  - `DiscordNotifier(...).send(content)` POSTs to a Discord channel
    webhook URL. URL is the auth, treated as secret (gitignored
    `ttn.env`).
  - Webhook over bot per design — one-way notifications don't need
    OAuth/library/account-flagging risk that gmail SMTP would have.
  - Cloudflare 1010 fix: edge rejects `Python-urllib/3.x` UA;
    skill sends an identified UA per Discord's webhook guidelines.
  - Truncates above CONTENT_MAX (2000 chars), preserves error_msg
    on failure so the upper-level can decide retry policy.
  - `_post` injection point in the constructor lets tests stub HTTP
    without monkeypatching.

### Cross-cutting design decisions ratified today

  1. **Streams stay separate.** TTN moisture and CIMIS ETo are
     different cadences with different failure modes; they don't
     share a DB, runner, solution, or report. `farm_soil_dev.sqlite`
     for moisture, `farm_soil_cimis_dev.sqlite` for CIMIS. Cross-
     stream composition happens at the chain_tree level (the future
     daily-report sub-tree reads both DBs), not at the storage level.

  2. **Credentials layered, not embedded.** `secrets/ttn.env` (gitignored)
     holds tokens and webhook URLs; `config/{dev,prod}.yaml` holds
     non-secret connection params (TTN app id, CIMIS station id,
     etc.); `run_*.py` carries no API strings. Adding a new sensor
     deployment is a config edit, not a code edit.

  3. **Skill = atomic; sub-tree = composed behavior; library = mix
     of skills + composite templates.** Glenn's framing this session.
     The "daily report" use case decomposes into three primitive
     leaves (record-to-DB / SQL pattern / ship-to-Discord), composed
     via system-library composites (`sequence`, `state_machine`,
     `time_gate`). The retry-after-8-AM logic is a sibling sub-tree,
     not embedded in the leaf. This is the layered-invariants thesis
     applied to behavior authoring: leaves stay portable, composites
     express behavior, the artifact is constrained-correct.

  4. **Engine-shape vs goal-shape layers stay distinct.**
     `skills/` = engine-shape primitives (Python classes, atomic).
     `user_templates/` = chain_tree binding (one class per leaf).
     `user_skills/` (planned, not built) = goal-shape composed
     sub-trees, LLM-addressable, one-deep dependency.

  5. **Predicate validation, not data trust.** The upper-level retry
     uses `is_data_present(... require_finalised=True)` to gate
     downstream work. The DB IS truth (Glenn's stated principle).
     Provisional values aren't "almost-truth"; they're filtered at
     the insert layer so they don't enter the DB at all.

  6. **48-hour moisture lookback** (changed from 24h late in the
     session). The lorwan stream now keeps a 2-day window of
     uplinks visible; the daily report sub-tree will read against
     this window.

### Commits (most recent first)

  ```
  0a40e1c  skills/discord — webhook-based Discord notifier (first IO skill)
  2606c9f  skills/cimis + farm_soil cimis stream — daily ETo for irrigation
  41cdae0  robots + skills: first robot (farm_soil) on lorwan_moisture skill
  ```

  Plus an uncommitted 48h-lookback config change tied to this
  continue.md commit.

### Test status

  47 passing (10 lorwan + 11 cimis + 7 discord + 6 farm_soil/report
  + 3 farm_soil/cimis_report + others). Single pytest run from
  `robot_person/`: `python -m pytest skills/ robots/ -q`. The
  template_language regression suite (212/212) is unaffected; the
  `farm_soil` work uses the multi-root registry Glenn shipped two
  sessions ago and didn't touch the engine.

### Live-tested against real systems

  - **Real TTN**: lacima1c / lacima1d / lacamia1b SenseCAP devices
    via `lacima-ranch-1` gateway. 36-hour fetch returned 103
    uplinks; per-uplink moisture/RF report rendered correctly with
    multi-gateway counts and battery presence flags.
  - **Real CIMIS**: station 237 returns 8 days of `DayAsceEto`;
    yesterday's finalised value (`0.110 in`) cross-checked exactly
    against the value Glenn's existing irrigation system fetched at
    08:00 UTC the same morning.
  - **Real Discord**: webhook fired two test messages to Glenn's
    `farm` server `# farm-soil` channel; visible on web and (after
    enabling notifications) on mobile.

---

## DESIGN — deployable processes layer (PLANNED, comment captured)

Glenn raised the question of where to put **deployable processes** —
the layer that says *what is actually running on the farm hardware*,
distinct from `robots/farm_soil/` which says *what the robot can do*.
Comment captured this session, layout sketched, not yet built.

  ```
  deployments/                         # NEW — site-keyed
  └── farm/                            # one dir per physical site
      ├── README.md
      ├── inventory.yaml               # what runs here, paths, env refs, restart policy
      ├── env/                         # per-host env overrides (gitignored where sensitive)
      ├── systemd/
      │   ├── farm_soil-moisture.service       # 24/7 daemon (15-min poll loop)
      │   ├── farm_soil-cimis-morning.service  # one-shot
      │   ├── farm_soil-cimis-morning.timer    # daily 08:00, retry-until-finalised inside the chain
      │   ├── farm_soil-daily-report.service   # one-shot
      │   └── farm_soil-daily-report.timer     # daily 09:00 (after CIMIS settles)
      ├── crontab.txt                  # equivalent for hosts without systemd (Pi headless)
      └── docker-compose.yml           # optional, if any service needs containerisation
  ```

  Each `.service` is a thin wrapper invoking
  `python -m robots.farm_soil.run_*` with a config flag. systemd
  gives restart-on-failure, log capture (journalctl), boot ordering,
  dependency declarations for free. Timers replace cron and integrate
  with the same logging story.

  **Scheduled vs 24/7 maps cleanly to the chain_tree composition layer:**
  scheduled solutions terminate via `asm_terminate_system` after one
  cycle (existing `inspect_36h`, `cimis_inspect`, future
  `daily_report` shape — systemd timer fires them). 24/7 solutions
  stay running with internal state machines/loops (the future
  continuous moisture poller — systemd service keeps them alive).
  The split is determined by the solution's terminator, not by the
  deployment metadata. The deployment just says "run this; restart
  on crash" — same shape for either case.

---

## Where to start tomorrow

Glenn's chosen build order (from end-of-session conversation):

1. **`skills/sqlite_query/`** — generic "run parameterised SQL ->
   format rows via template -> return string" primitive. Foundational
   for the daily-report sub-tree's middle leaf, and reusable beyond:
   the CIMIS check predicate, future irrigation logic, anything that
   reads from these DBs. **Stop here for review before composing.**

2. **`discord_notify` wrapper update** — add an optional
   `content_bb_key` slot. When set, the leaf reads message content
   from blackboard at execution time (set there by the upstream
   `sqlite_query` leaf's output) instead of the static `content`
   slot. Makes the leaves composable.

3. **Project-local sub-tree composite in `farm_soil`** —
   `daily_report` = `sequence(query_moisture, query_cimis,
   format_into_message, discord_send)`. Lives at
   `robots/farm_soil/templates/composites/chain_tree/daily_report.py`.
   This is the first real exercise of the "skill = atomic; sub-tree
   = behavior" principle on this codebase.

4. **Solution + runner** — `daily_report` solution that runs the
   sub-tree once and terminates; `run_daily_report.py` to fire it
   manually for testing.

5. **`deployments/farm/` scaffold** — README + inventory.yaml + one
   systemd timer pointing at `run_daily_report` (daily 09:00).
   Doesn't have to deploy yet; the manifest itself locks the
   convention so the next robot follows the same shape.

### Open backlog (post-1..5)

  - Continuous moisture poller (24/7 daemon shape — needs internal
    state machine instead of `asm_terminate_system`).
  - Threshold-based alert leaves: moisture < X for device Y over
    Z hours -> ping Discord with diagnostics.
  - Sensor-offline alert: device hasn't reported in N hours -> ping.
  - Other IO skills as needs surface (file/log writer, MQTT publish,
    etc.) — Glenn's stated default: "rely on Discord until we have
    a reason to move".
  - Forecast skill (NWS or OpenWeatherMap) — predicted rain to
    factor into irrigation decisions. Different from CIMIS (past-
    day actuals vs future forecast).
  - The architectural memo (`why.md`) deferred from the
    template_language session is even more defensible now that the
    layering has been exercised on real data.

### Where the convention is documented

  - `skills/README.md` — skill authoring convention.
  - `template_language/continue.md` — engine-shape spec, multi-root
    convention, three layers of templates.
  - This file — robots + deployments layer; session logs.
  - `robots/farm_soil/README.md` — example robot inventory.
  - `examples/coffee_maker/` — original reference robot, still
    valid for engine-shape patterns.

---

## File inventory by layer (as of 2026-05-05 session close)

### skills/ (3 skills, engine-agnostic)
  - `lorwan_moisture/` — TTN soil-moisture fetch + decode + SQLite.
  - `cimis/` — CIMIS Web API ETo fetch + finalisation predicate.
  - `discord/` — Discord webhook send (first IO skill).
  - `README.md` — convention.

### user_templates/ (cross-robot chain_tree wrappers, prefix `user`)
  - `bootstrap.py` — multi-root registration.
  - `templates/leaves/chain_tree/lorwan_moisture.py`
  - `templates/leaves/chain_tree/cimis_eto.py`
  - `templates/leaves/chain_tree/discord_notify.py`

### robots/farm_soil/ (first robot, prefix `project.farm_soil`)
  - Configuration: `bootstrap.py`, `hardware.yaml`, `config/{dev,prod}.yaml`,
    `secrets/ttn.env.example`, `conftest.py`.
  - Data-side helpers: `report.py`, `cimis_report.py`.
  - Standalone test program: `eto_237_demo.py`.
  - Runners: `run.py`, `run_cimis.py`.
  - Templates: project-local leaves (`brew_log`-equivalent — actually
    `moisture_report` and `cimis_report`) and solutions
    (`inspect_36h`, `cimis_inspect`).
  - Tests: `tests/test_report.py`, `tests/test_cimis_report.py`.

### deployments/ (PLANNED, not yet built)
  - sketch above.

### Skills inventory by I/O shape

  | Skill           | I/O    | Backend          | Auth                |
  | --------------- | ------ | ---------------- | ------------------- |
  | lorwan_moisture | input  | TTN v3 storage   | bearer token        |
  | cimis           | input  | et.water.ca.gov  | appKey query param  |
  | discord         | output | Discord webhook  | URL itself = secret |

  Future inputs (planned): NWS / OpenWeatherMap forecast,
  generic `sqlite_query` (next session).
  Future outputs (deferred): file/log writer, MQTT publish,
  generic HTTP webhook, SMS via Twilio.

---

## SESSION LOG — 2026-05-06: cluster architecture — design + four-stage build plan

This session re-shaped the production layer end-to-end. The earlier
sketch (per-workload systemd units pointing at `run_*.py`) is
**superseded** by a chain_tree-native cluster: one container per
site, holding a broker + a chain_tree supervisor + N chain_tree
worker subprocesses, all communicating via ZeroMQ events on a
shared bus. The deferred `sqlite_query` / `daily_report` work from
the prior session is **not dropped** — it is reordered to land
before the bus work, so the cluster gets built on a tested
single-process foundation.

The session was a chat-mode design pass. No code was written.
The output is this plan.

### Architectural decisions (locked this session — do not relitigate)

  1. **Sandbox vs production is a logical split, not a directory.**
     - Sandbox = stages 1+2 (per-skill, per-robot, in-process, fast
       iteration).
     - Staging = stage 3 (full cluster, real bus, dev box).
     - Production = stage 4 (containerized, deployed).

  2. **Subprocess model for chain_tree workers.**
     Each worker = its own Python process. Crash isolation is the
     goal. GIL-free parallelism is a side benefit. Per-process
     blackboard is in-memory + ephemeral; durable truth lives in
     app SQLite.

  3. **Supervisor IS a chain_tree.**
     Erlang OTP insight applied: the control plane is built from
     the same primitives as the things it controls. Supervisor's
     solution is composed of leaves (spawn-child, monitor-child,
     restart-policy, alert-leaf). Restart strategies (one_for_one /
     one_for_all / rest_for_one) live as composite sub-trees, NOT
     as monolithic skills.

  4. **SQLite is app-only.**
     Two distinct DB concerns kept distinct:
     - **App SQLite**: skill outputs (moisture readings, ETo values).
       Per-skill schema. The system's source of truth.
     - **KB / blackboard**: in-memory only, ephemeral. Crash loses
       it; restart rebuilds working state by querying app SQLite.
     The chain_tree runtime does NOT persist KB state to disk.

  5. **ZeroMQ for inter-process communication.**
     Event-shaped messages, not RPC. PUB/SUB pattern via a
     **dedicated broker process** (XSUB↔XPUB proxy — option (c) of
     three considered). Decouples bus from supervision so supervisor
     restarts don't drop the bus.

  6. **Topic conventions.**
     Hierarchical dotted prefixes. Examples:
     - `evt.farm_soil.moisture.tick.complete`
     - `evt.farm_soil.cimis.tick.failed`
     - `cmd.farm_soil.moisture.pause`
     - `ack.<request_id>`
     - `discord.notify`
     ZMQ subscribers filter by byte-prefix, so coarser prefixes
     get coarser fan-in for free (`evt.farm_soil.` = everything from
     that robot; `b""` = firehose).

  7. **Three semantic classes on one bus.**
     - `evt.*` — events. Telemetry, lifecycle, alerts. Many
       publishers, many subscribers, lossy fire-and-forget.
     - `cmd.*` — commands. External or internal injection of
       "do this now."
     - `ack.*` — responses, correlated to commands via `request_id`.
     Same wire, same broker, separated by topic prefix.

  8. **Wire format.**
     Multipart ZMQ frame: frame 1 = topic string (UTF-8 bytes),
     frame 2 = JSON payload `{ts, source, type, payload}`.
     Subscribers filter on frame 1, parse frame 2.
     JSON to start (debuggable, tcpdump-friendly, same shape skills
     already speak); msgpack later if volume warrants — it won't
     on a 3-sensor farm.

  9. **Engine layering — ZMQ is runtime, not skill.**
     Skills stay engine-agnostic. They do not import zmq.
     **Events are emitted by leaves, not by skills.** A leaf wraps
     a skill call and decides what to emit around it
     (`tick.started`, `tick.complete`, `tick.failed`).
     Runtime exposes:
     - `bb.emit(topic, payload)`
     - `bb.subscribe(topic_prefix, handler)`
     ZMQ is the implementation behind those calls.

 10. **Pluggable transport (falls out of stage discipline).**
     Same chain_tree code runs at stage 2 (in-process stub
     transport) and stages 3+4 (ZMQ transport). Transport is a
     runtime constructor argument, not a code change. Stub:
     `bb.emit` calls in-memory subscribers; deterministic; no
     sockets; no ports; sub-second tests.

 11. **Centralized output bridges.**
     One subscriber per output channel; everyone else emits
     events. Discord bridge example owns both directions:
     - SUBs to `discord.notify`, posts to webhook (outbound).
     - Maintains Discord Gateway WebSocket (inbound).
     - On message in `# farm-control`, parses → command, generates
       `request_id`, SUBs to `ack.<request_id>`, PUBs cmd, awaits
       ack, posts reply.
     Same shape for every IO surface (future SMS bridge, MQTT
     publish, MCP/LLM bridge): one canonical `cmd.*`/`ack.*`
     format; N bridges to N front-ends.

 12. **Discord chat is the primary command channel; `farmctl` is fallback.**
     Discord-as-command-channel works behind home NAT (outbound
     WebSocket only — no port forwarding, no ngrok, no public IP).
     `farmctl` is the local CLI that PUBs directly to the bus,
     used when Discord is down or for local-only ops. Both produce
     identical `cmd.*`/`ack.*` flow on the bus. Auth: Discord
     channel membership for the chat surface; bind broker to
     localhost or LAN-private interface for `farmctl`.

 13. **Container shape — one container per site.**
     Inside: broker + supervisor + all children + logger sink.
     **Don't go container-per-child** — subprocess isolation already
     provides the right crash boundary; container-per-child pays
     for the same cake twice.
     Volume mounts:
     - `/var/lib/<robot>/`     — app SQLite DBs (persistent).
     - `/etc/<robot>/secrets/` — read-only secrets.
     - `/etc/<robot>/config/`  — non-secret config.
     - `/var/log/<robot>/`     — logger child's rotating logs.
     Network: expose ONE port pair (broker XSUB+XPUB) for external
     bus access. Restart: `--restart=unless-stopped` keeps the
     container alive; supervisor inside keeps children alive. Two
     layers, each handling its own scope.

 14. **Four-stage development discipline.**
     A stage N test should fail for stage N reasons only. Each
     stage adds ONE new dimension of complexity:

     | Stage | Scope                                       | Tests catch                                    | Status               |
     | ----- | ------------------------------------------- | ---------------------------------------------- | -------------------- |
     | 1     | one skill + one leaf, in-process            | wire format, decoder, external API contract   | mostly solved (47 tests) |
     | 2     | full sub-tree, in-memory KB, in-process     | composition, predicates, terminator           | partial (need stub transport + assert tests) |
     | 3     | broker + supervisor + ≥2 children + ZMQ     | IPC, cmd/ack correlation, restart-on-crash     | not started          |
     | 4     | cluster packaged in container               | image build, secrets, persistence, networking  | not started          |

     Test homes:
     - Stage 1: `skills/<name>/tests/`
     - Stage 2: `robots/<name>/tests/`
     - Stage 3: `tests/cluster/` (new top-level)
     - Stage 4: `deployments/<site>/tests/`

     CI velocity tiers:
     - Stage 1+2: fast (seconds), every commit.
     - Stage 3: slow (process startup), every PR.
     - Stage 4: slowest (image build), release tag or nightly.

 15. **Harness leads.**
     At each new stage the test rig is the **first** thing built,
     not the last. Stage 3's broker-and-mini-cluster harness comes
     before any real worker is wired to the bus. Without the
     harness you can't validate the first child you wire.
     Foundation first; features on top.

---

## BUILD PLAN — six phases, mapped to the four stages

The phases land in sequence. Each phase has a clear exit
criterion; do not start phase N+1 until phase N exits cleanly.

### PHASE 0 — finish stages 1+2 before any bus work

  Goal: get the single-process foundation rock-solid before
  introducing the bus. Bus work is hard to debug; you don't want
  stage 1 or 2 bugs leaking into stage 3 diagnosis.

  This phase delivers the deferred work from the previous session.

  - **P0.1 — `skills/sqlite_query/`** — atomic skill: parameterised
    SQL → list-of-dicts. Engine-agnostic. No template/format
    coupling. (Glenn's deferred skill from prior plan.)

  - **P0.2 — Stage-2 stub transport in chain_tree runtime.**
    Add a `Transport` interface with `emit(topic, payload)` and
    `subscribe(prefix, handler)`. Implement `InProcessTransport`:
    in-memory list of (prefix, handler) pairs; emit walks the list
    synchronously and invokes matching handlers. Runtime takes a
    transport in its constructor; default is in-process. NO ZMQ yet.

  - **P0.3 — `bb.emit` / `bb.subscribe` API on blackboard.**
    Wire the runtime's transport up to the blackboard the leaves
    see. Leaves call `bb.emit("foo.bar", {...})` and it dispatches
    via whatever transport the runtime was constructed with.

  - **P0.4 — Stage-2 deterministic tests for `farm_soil`.**
    Convert `run.py` and `run_cimis.py` from inspection runners
    into pytest tests with deterministic fixture data and asserts
    on blackboard outputs. Tests use `InProcessTransport` and run
    fast (sub-second).

  - **P0.5 — `discord_notify` leaf — add `content_bb_key` slot.**
    Optional blackboard key the leaf reads at execution time
    instead of the static `content` slot. Required for the
    composed daily-report sub-tree. (Deferred from prior plan.)

  - **P0.6 — Project-local `daily_report` composite.**
    `daily_report = sequence(query_moisture, query_cimis,
    format_into_message, discord_send)`. Lives at
    `robots/farm_soil/templates/composites/chain_tree/daily_report.py`.
    First real exercise of skill=atomic, sub-tree=behavior on
    this codebase.

  - **P0.7 — Solution + runner for daily_report.**
    `daily_report` solution that runs the sub-tree once and
    terminates; `run_daily_report.py` to fire it manually. Uses
    `InProcessTransport` (no bus yet).

  **Exit criterion:** `pytest skills/ robots/` clean; daily_report
  sub-tree exercised end-to-end against test data, in-process,
  no ZMQ on the system. Stages 1+2 ratified.

### PHASE 1 — Stage 3 harness (broker + mini-cluster)

  Goal: build the test rig FIRST. Until the harness exists, no
  real worker can be tested at the cluster level.

  - **P1.1 — ZMQ wire-format spec.**
    Capture topic conventions, multipart frame layout, envelope
    schema in a short markdown spec at
    `chain_tree/runtime/transport/README.md`. Tests reference this;
    future bridges and tools follow it. Source of truth for the
    wire.

  - **P1.2 — `chain_tree/runtime/transport/zmq_transport.py`.**
    Real ZMQ implementation of the `Transport` interface. PUB
    socket connects to broker XSUB; SUB socket connects to broker
    XPUB; multipart frame send/recv; topic prefix subscribe.
    Target ~150 lines. Constructor takes broker addresses.

  - **P1.3 — `bin/broker.py` — dedicated broker process.**
    ~30 lines wrapping `zmq.proxy(XSUB, XPUB)`. Reads bind
    addresses from env or argv. Logs connect/disconnect events to
    stderr (logger child captures these eventually).

  - **P1.4 — `tests/cluster/conftest.py` — broker fixture.**
    pytest fixture that spawns `bin/broker.py` on an ephemeral
    port pair, yields the addresses, kills the broker at teardown.
    Handles startup readiness (small bind-then-connect loop).

  - **P1.5 — `tests/cluster/test_transport.py` — first stage-3 test.**
    Spawn the broker; spawn TWO trivial subprocess children
    (just `python -c` shims using `ZmqTransport`); one PUBs an
    event, the other SUBs and asserts receipt. Verifies
    subscribe-before-publish ordering, multipart frames, topic
    prefix filtering. Slow (process startup) but real.

  **Exit criterion:** `pytest tests/cluster/test_transport.py`
  passes. Two real subprocesses talking through a real broker.
  Harness works. Stage 3 is now testable.

### PHASE 2 — Stage 3 supervisor + child lifecycle

  Goal: the supervisor as a chain_tree, managing real subprocess
  children with restart policy.

  - **P2.1 — `skills/subprocess_spawn/`** — atomic. Popen + return
    handle (PID, stdout/stderr pipes, env). Engine-agnostic. ~50
    lines.

  - **P2.2 — `skills/process_status/`** — atomic. Given a handle:
    alive? exit code if dead? cpu/memory if available.
    Engine-agnostic. ~50 lines.

  - **P2.3 — `skills/process_signal/`** — atomic. Given a handle:
    send SIGTERM / SIGKILL. Engine-agnostic. ~30 lines.

  - **P2.4 — `templates/composites/chain_tree/supervise_one_for_one.py`.**
    First restart strategy as a chain_tree composite. Uses the
    three skills above + state-machine + time-gate for restart
    intensity (max-restarts-in-window). NO new skill — pure
    composition. one_for_all and rest_for_one come later as
    sibling composites.

  - **P2.5 — Supervisor solution.**
    `supervisor.solution` reads a `child_specs` list from config
    and applies `supervise_one_for_one` to each. Each child spec:
    `{name, cmd, args, env, restart_policy, max_restarts_per_min}`.

  - **P2.6 — `inventory.yaml` schema for `farm_soil`.**
    Lists workers the supervisor runs:
    - `moisture_poller` (15-min loop daemon)
    - `cimis_morning` (one-shot daily 08:00)
    - `daily_report` (one-shot daily 09:00)
    Scheduling is internal to each worker's chain_tree (time-gate
    composite), NOT a systemd timer.

  - **P2.7 — Stage-3 supervisor test.**
    Bring up broker + supervisor + two trivial children; kill one
    child externally; verify supervisor restarts it and emits
    `evt.<scope>.child.{spawned,exited,restarted}` on the bus.

  **Exit criterion:** real supervisor managing real children with
  restart policy, end-to-end on the bus, verified by a stage-3
  test.

### PHASE 3 — Stage 3 command/ack + Discord bridge + farmctl

  Goal: external command injection. Two bridges: Discord (chatops)
  and farmctl (CLI fallback). Both produce identical
  `cmd.*`/`ack.*` flow on the bus.

  - **P3.1 — Command/ack convention (distributed handling).**
    Each child SUBs to `cmd.<own-scope>.`. Commands carry
    `{request_id, args}`. Handler emits `ack.<request_id>` with
    `{ok, result}` or `{error, msg}`. (Distributed by default —
    controller stays thin. Revisit centralization if ergonomics
    suggest it.)

  - **P3.2 — `bin/farmctl` — CLI fallback.**
    ~50 lines: connect PUB and SUB to broker; SUB to
    `ack.<request_id>` first (avoid the subscribe-before-publish
    race); PUB cmd; wait for ack with timeout; print result; exit
    non-zero on error. Subcommands map directly to
    `cmd.<scope>.<action>` topics.

  - **P3.3 — Stage-3 farmctl test.**
    Bring up broker + a child that responds to `cmd.test.echo`;
    invoke farmctl as a subprocess from the test; assert ack
    received and result correct.

  - **P3.4 — `skills/discord_bot/`** — atomic. Maintains Discord
    Gateway WebSocket. Yields incoming messages from subscribed
    channels as an event stream. Accepts "post message to channel
    C" calls. Wraps `discord.py`. Engine-agnostic.

  - **P3.5 — `discord_bridge` worker — combined bot + webhook publisher.**
    Single Discord-IO process. Functions:
    - SUBs to `discord.notify`, posts to webhook URL (subsumes the
      prior centralized-publisher plan).
    - Listens on Gateway for messages on `# farm-control`, parses
      as commands (prefix syntax: `!status`, `!pause`, `!run`,
      etc.), generates `request_id`, SUBs to `ack.<request_id>`,
      PUBs `cmd.*`, posts reply with ack result.
    Lives at `robots/farm_soil/workers/discord_bridge.py` for now;
    promotes to a shared `bridges/` location once a second robot
    needs it.

  - **P3.6 — Stage-3 Discord-bridge test.**
    Mock the Discord Gateway side (the network layer outside our
    bus is the only thing we mock at stage 3). Verify that an
    incoming "message" produces the expected `cmd.*` on the bus
    and that an ack causes the expected "post message" call. Bus
    side is real.

  **Exit criterion:** external command injection works through
  both farmctl and Discord. Symmetric flow; identical bus traffic.

### PHASE 4 — Stage 3 logger sink + alert composites

  Goal: observability, replay, and the first real alert leaves.

  - **P4.1 — `logger` worker.**
    SUBs to `b""` (firehose). Writes one JSON line per event to a
    rotating log file in `/var/log/<robot>/events/`. ~50 lines.
    Replay-driven testing now possible.

  - **P4.2 — Threshold-alert composite.**
    `moisture < X for device Y over Z hours -> emit
    discord.notify`. Lives at
    `robots/farm_soil/templates/composites/chain_tree/alert_low_moisture.py`.
    First real consumer of bus events for cross-stream behavior.

  - **P4.3 — Sensor-offline alert composite.**
    `device Y hasn't reported in N hours -> emit discord.notify`.
    Same pattern.

  - **P4.4 — Stage-3 alert test.**
    Drive the threshold composite with synthetic moisture
    readings; assert that the right `discord.notify` events land
    on the bus.

  **Exit criterion:** alerts work end-to-end on the bus; logger
  captures every event for replay.

### PHASE 5 — Stage 4 container

  Goal: cluster packaged for deployment. Same code; new dimension
  is image + container runtime.

  - **P5.1 — `deployments/farm/Dockerfile`.**
    Base: `python:3.X-slim`. Install zmq C lib, pip install
    requirements. Copy source. Entry point:
    `python -m robots.farm_soil.supervisor`. Supervisor's first
    child is the broker; it spawns everyone else after the broker
    is healthy.

  - **P5.2 — `deployments/farm/docker-compose.yml`.**
    Single service (one container per site). Volume mounts as
    specified above. Restart policy `unless-stopped`. Exposes
    broker XSUB+XPUB ports on the chosen network interface
    (decision: localhost / LAN / public — see open question
    below).

  - **P5.3 — `deployments/farm/inventory.yaml`.**
    Site-specific config: which robots run here, ports, paths,
    secret refs.

  - **P5.4 — Stage-4 smoke test.**
    `docker compose up` from a fixture; wait for healthy; run
    `farmctl status` from outside the container; assert response.
    Slow (image build + container start), runs nightly or on
    release tag only.

  - **P5.5 — Pi-host setup README.**
    Brief notes on docker installation, secret provisioning, and
    network configuration. Recommend keeping broker port
    LAN-local and using Discord for remote ops.

  **Exit criterion:** container builds, runs, restarts cleanly,
  exposes the bus to a host CLI tool. Full architecture deployed.

### PHASE 6+ — Backlog (post-deployment)

  Items still relevant from prior continue.md, all preserved:

  - Continuous moisture poller (24/7 daemon shape — verify the
    restart policy actually fires when it crashes, with
    intentional crash injection).
  - Forecast skill (NWS or OpenWeatherMap).
  - Slash commands in Discord bridge (UX upgrade once we know
    which prefix commands earn dedicated slots).
  - Architectural memo (`why.md`) deferred from the
    template_language session — even more defensible now that the
    layering has been exercised at scale.
  - Second robot (validates the multi-robot story; forces the
    `bridges/` shared location).
  - Bridges other than Discord: SMS (Twilio), MQTT publish, MCP/LLM
    front-end.
  - one_for_all and rest_for_one supervisor strategies as sibling
    composites to one_for_one.

---

## Open questions deferred to next session(s)

  - **Bus authorization model.** Phase 5 forces this:
    localhost-only broker (no auth)? Private LAN with ZMQ CURVE
    keypair auth? Public exposure (CURVE + reverse proxy + thin
    HTTPS shim)? Resolve before P5.2. For a single-user farm with
    Discord as the primary remote control surface, localhost +
    LAN-private is likely sufficient.

  - **Per-process logging during dev (before P4.1).** Probably
    "supervisor pipes child stderr to its own stderr, prefixed
    with child name" is enough until P4.1 lands. Cheap to do at
    P2.1 (subprocess_spawn captures the pipes); revisit if it
    isn't.

  - **Dev-mode iteration loop.** How Glenn iterates on a single
    child without restarting the whole cluster. Likely options:
    `farmctl restart <child>` command (lands in P3); or just kill
    the OS process and let supervisor restart it. Comes naturally
    with P2 + P3 — no separate work needed.

  - **Whether the broker should itself be a chain_tree process.**
    Currently planned as a tiny `bin/broker.py` script around
    `zmq.proxy()`. Could become a chain_tree leaf inside the
    supervisor's solution to be more self-similar. Defer; revisit
    if there's a reason (extra logic in the broker that wants
    composition).

---

## File inventory after each phase (planned)

  **After Phase 0** (no bus yet):
  - `skills/sqlite_query/` (new)
  - `chain_tree/runtime/transport/` with `Transport` ABC and
    `InProcessTransport`
  - Updated `discord_notify` leaf with `content_bb_key`
  - `robots/farm_soil/templates/composites/chain_tree/daily_report.py`
  - `robots/farm_soil/run_daily_report.py`
  - Stage-2 deterministic tests in `robots/farm_soil/tests/`

  **After Phase 1** (harness exists):
  - `bin/broker.py`
  - `chain_tree/runtime/transport/zmq_transport.py`
  - `chain_tree/runtime/transport/README.md` (wire spec)
  - `tests/cluster/conftest.py` + `test_transport.py`

  **After Phase 2** (supervisor real):
  - `skills/subprocess_spawn/`, `process_status/`, `process_signal/`
  - `templates/composites/chain_tree/supervise_one_for_one.py`
  - `robots/farm_soil/supervisor.py` + `supervisor.solution`
  - `robots/farm_soil/inventory.yaml`
  - `tests/cluster/test_supervisor.py`

  **After Phase 3** (commands flow):
  - `bin/farmctl`
  - `skills/discord_bot/`
  - `robots/farm_soil/workers/discord_bridge.py`
  - `tests/cluster/test_farmctl.py`, `test_discord_bridge.py`

  **After Phase 4** (observability):
  - `robots/farm_soil/workers/logger.py`
  - `robots/farm_soil/templates/composites/chain_tree/alert_*.py`
  - `tests/cluster/test_alerts.py`

  **After Phase 5** (deployed):
  - `deployments/farm/Dockerfile`
  - `deployments/farm/docker-compose.yml`
  - `deployments/farm/inventory.yaml`
  - `deployments/farm/README.md`
  - `deployments/farm/tests/test_container_smoke.py`

---

## Where the next session starts

**Phase 0, item P0.1 — `skills/sqlite_query/`.**

The deferred skill from the prior session is the right starting
point because:
1. It's stage-1-shaped (atomic skill), which is the most-tested
   stage we have — quickest wins the green build back.
2. It's required by the daily-report composite (P0.6), which is
   required by the stage-2 deterministic tests (P0.4), which are
   required to ratify stages 1+2 before bus work (Phase 1).
3. It also unblocks future work outside the daily-report path
   (alert composites in Phase 4 use the same SQL primitive).

Ratify each Phase-0 item with a quick chat-mode review before
moving to the next. Do **not** start Phase 1 until Phase 0 exits
clean — stage 3 is the painful debug layer, and stage 1+2 bugs
hiding inside stage 3 failures is exactly the cost the staging
discipline exists to prevent.

---

## SESSION LOG — 2026-05-06 evening: Phase 0 shipped end-to-end

All seven P0 items landed in one focused session. Cadence was strict:
do one P-item, present it, Glenn says continue, do the next. **222
tests passing** (prior 183 + 39 new). No regressions. Nothing
committed yet — review and commit pass is the first thing tomorrow.

### What landed (in order)

  - **P0.1** — `skills/sqlite_query/` — atomic read-only SQL skill.
    `SqliteQuery(db_path)` + `query(sql, params=()) → (rows | None,
    err | None)`. Read-only via `mode=ro` URI; rows as list-of-dicts;
    both `?` and `:name` params. Dropped a `read_only=False` escape
    hatch from the first draft — YAGNI; this is the read skill, by
    design.

  - **P0.2** — `chain_tree/ct_runtime/transport/` sub-package.
    `Transport` ABC with `emit(topic, payload)` + `subscribe(prefix,
    handler)`. `InProcessTransport` is a list of `(prefix, handler)`
    tuples; emit walks synchronously; topic match is `topic.startswith(prefix)`
    so empty prefix = firehose (mirrors ZMQ byte-prefix subscription).
    PUB/SUB lossy: handler exceptions caught + logged; emit never
    raises; subsequent handlers still fire. `new_engine(... transport=)`
    defaults to `InProcessTransport()`. `ct.Transport` /
    `ct.InProcessTransport` re-exported.

  - **P0.3** — `chain_tree/ct_runtime/bb.py` — `bb_emit(kb, topic,
    payload)` and `bb_subscribe(kb, prefix, handler)`. One-line
    lookups of `kb["engine"]["transport"]`. **Decision (Glenn):
    blackboard stays a plain dict; cross-cutting runtime APIs hang
    off the engine, not the blackboard.** Saved as a memory addendum
    to the existing namespace rule.

  - **P0.4** — `robots/farm_soil/tests/test_inspect_solutions.py` —
    two stage-2 deterministic tests for `inspect_36h` and
    `cimis_inspect`. Monkeypatch the fetcher classes with fakes that
    seed real SQLite (via the skill's `insert_uplink` /
    `insert_record` helpers); run the full solution end-to-end;
    assert on slot wiring + fetch-leaf log + report rendering. Both
    confirm the engine's transport is the in-process default.
    `ChainTree.__init__` now accepts `transport=` (forwarded to
    `new_engine`). `farm_soil/conftest.py` autouse fixture now
    bootstraps `user_templates` too.

  - **P0.5** — `discord_notify` leaf gained an optional `content_bb_key`
    slot. Mode-exclusive with `content` (template-time error if both
    or neither). At runtime: reads `handle["blackboard"][content_bb_key]`;
    skips with a log line if missing/empty.

  - **P0.6** — daily_report composite + supporting pieces:
    - `user_templates/templates/leaves/chain_tree/sqlite_query.py` —
      leaf wrapping the skill; writes rows to `result_bb_key` on the
      blackboard.
    - `robots/farm_soil/format.py` — pure function
      `format_daily_report(moisture_rows, eto_rows, *, report_date=None)
      → str`. Engine-agnostic; mirrors the `report.py` /
      `cimis_report.py` separation.
    - `robots/farm_soil/templates/leaves/chain_tree/format_daily_report.py`
      — project-local leaf reading two bb keys, writing the formatted
      string to a third.
    - `robots/farm_soil/templates/composites/chain_tree/daily_report.py`
      — the composite. **Composite, not solution.** Sequence of four
      leaves: `sqlite_query` (moisture, 48h) → `sqlite_query` (CIMIS,
      7d for station 237) → `format_daily_report` → `discord_notify`
      with `content_bb_key`. BB keys namespaced under the composite's
      `name` slot (`daily_report.<name>.moisture_rows`, etc.) so two
      siblings can't collide.
    - `skills/sqlite_query/__init__.py` — fixed: now re-exports
      `SqliteQuery` per the convention. P0.1 left it empty; surfaced
      now because daily_report imports the skill via the package.
    - End-to-end test seeds two real DBs, runs the composite via
      inline solution, monkeypatches the notifier, asserts the
      captured Discord message contains both data sections + correct
      values + the 100h-ago row excluded by the 48h window.

  - **P0.7** — `daily_report` solution + runner:
    - `robots/farm_soil/templates/solutions/chain_tree/daily_report.py`
      — wraps the composite in `start_test`/`end_test` +
      `asm_terminate_system`. Slots forwarded directly to the
      composite (same names) so the runner passes config through
      without renaming.
    - `robots/farm_soil/run_daily_report.py` — same shape as
      `run.py` / `run_cimis.py`. Reads config + `DISCORD_WEBHOOK_URL`
      from secrets. **Hits the real Discord webhook** — no dry-run
      flag. The deterministic path is the test.
    - `test_daily_report_solution.py` — verifies the solution-layer
      shape: empty DBs → composite reads from real schemas (no error)
      → formatter renders the `(no data)` branch → all four leaves
      logged → `asm_terminate_system` cleared `cfl_engine_flag`.

### Test totals

  | | Before | After | New |
  |---|---|---|---|
  | skills | 28 | 37 | +9 (sqlite_query) |
  | chain_tree | 136 | 153 | +17 (transport, bb) |
  | robots/farm_soil | 19 | 32 | +13 (inspect ×2, discord_notify ×6, format ×6, composite + solution ×2) |
  | **Total** | **183** | **222** | **+39** |

  Run with `PYTHONPATH=s_engine .venv/bin/pytest chain_tree/tests/
  skills/ robots/ -q`. Sub-second total. Pre-existing CLAUDE.md note:
  use `source enter_venv.sh` first to get this env var set
  automatically.

### Architectural milestones reached

  1. **Stages 1+2 ratified**, per the plan's exit criterion (line 571
     of this file). Engine has a pluggable transport seam; same
     chain_tree code at stage 3 will swap the implementation, not the
     call sites.

  2. **Skill = atomic; sub-tree = composed behavior** — first
     real exercise on this codebase. None of the four daily_report
     leaves knows about "daily report"; the composite is what makes
     them one. `sqlite_query` is portable to any read use case;
     `format_daily_report` is project-local but uses no engine
     internals; `discord_notify` is generic. The SQL strings live in
     the composite (the layer that knows the schemas). The
     architectural thesis from prior sessions is now backed by code.

  3. **Blackboard as the in-process hand-off channel** — leaves
     compose via `bb["key"]` writes/reads. Bus traffic
     (`bb_emit`/`bb_subscribe` over the engine transport) is for
     cross-process events (Phase 4 alert composites onward), not for
     in-leaf hand-off within one solution.

### Implementation notes worth keeping in mind

  - **pytest monkeypatch + per-test eviction** — `monkeypatch.setattr("dotted.path")`
    fails for any path under `farm_soil.templates.*`,
    `template_language.templates.*`, or `user_templates.templates.*`
    because the conftest evicts these between tests but pytest's
    resolver holds stale parent-package attribute refs. Workaround:
    `import ... as leaf` then `monkeypatch.setattr(leaf, "Attr", value)`.
    Saved as `feedback_monkeypatch_evicted_modules` memory.

  - **Inline test-solution pattern** — for stage-2 tests of
    leaves/composites, define a one-off solution at a fixed path
    inside the test body; conftest's `_registry.clear()` between
    tests makes re-registration safe. Avoids cluttering the project's
    real solutions directory with test-only files. Used in P0.5,
    P0.6, P0.7. Saved as `pattern_inline_test_solution` memory.

  - **CIMIS station 237** is hard-coded as the composite's default
    `cimis_station` slot. Glenn's farm; matches the existing
    `cimis_inspect` solution's default. When a second farm appears,
    promote to a per-deployment config value.

  - **48h moisture lookback** is the default in the composite,
    matching the prior session's bump from 24h. The composite's
    SQL embeds this via Python f-string at template time, not
    SQL-parameter binding (the lookback isn't truly per-run dynamic).

### Memory updates this session

  - `project_robots_layer.md` — updated: Phase 0 shipped; resume at
    P1.1.
  - `feedback_blackboard_namespace.md` — appended "Shape rule":
    blackboard stays a plain dict, no .emit/.subscribe wrapping.
  - `feedback_monkeypatch_evicted_modules.md` — new.
  - `pattern_inline_test_solution.md` — new.

---

## Where the next session starts (2026-05-07 +)

**First**: review Phase 0 end-to-end and commit. Suggested commit
groupings (mostly mirror the P-items so blame remains useful):

  1. `skills/sqlite_query/` (P0.1) + the `__init__.py` re-export fix
     from P0.6.
  2. `chain_tree/ct_runtime/transport/` + `bb.py` + engine wiring +
     `ChainTree.__init__` `transport=` kwarg + new tests (P0.2 + P0.3
     + the P0.4 DSL-side change).
  3. `robots/farm_soil/conftest.py` u_bootstrap addition + the new
     `test_inspect_solutions.py` (P0.4 robot side).
  4. `discord_notify` leaf + `test_discord_notify_leaf.py` (P0.5).
  5. The composite stack — `sqlite_query` leaf, `format.py`,
     `format_daily_report` leaf, the composite, the format test, the
     end-to-end test (P0.6).
  6. The solution + runner + solution-level test (P0.7).
  7. `robots/continue.md` (this file).

**Then**: P1.1 — ZMQ wire-format spec at
`chain_tree/ct_runtime/transport/README.md`. Captures topic
conventions (`evt.* / cmd.* / ack.*`), multipart frame layout (frame 1 =
topic UTF-8 bytes, frame 2 = JSON envelope `{ts, source, type,
payload}`), envelope schema. Tests reference this; future bridges and
tools follow it. This is a markdown spec, no code; it's the foundation
the rest of Phase 1 anchors against.

**Then in order (Phase 1 build)**:
  - P1.2 — `chain_tree/ct_runtime/transport/zmq_transport.py` —
    `ZmqTransport` implementing the same `Transport` ABC; PUB/SUB
    sockets connect to broker XSUB/XPUB.
  - P1.3 — `bin/broker.py` — ~30-line `zmq.proxy(XSUB, XPUB)` wrapper.
  - P1.4 — `tests/cluster/conftest.py` — broker fixture (spawn on
    ephemeral port, yield addresses, kill on teardown).
  - P1.5 — `tests/cluster/test_transport.py` — first stage-3 test.
    Two trivial subprocess children talking through the real broker.

**Open question carried into Phase 1**: where exactly to put the
broker fixture's port-readiness loop. ZMQ's bind-then-connect race is
real; the cleanest answer is probably "loop on a small subscribe-then-
emit ping until it round-trips." Decide when writing P1.4; defer until
then.

### Backlog still valid

Same items as the 2026-05-06 morning session log called out (lines
775–793 of this file): continuous moisture poller, forecast skill,
threshold-based alerts, sensor-offline alerts, `why.md` architectural
memo, second robot, bridges other than Discord (SMS, MQTT, MCP/LLM),
one_for_all and rest_for_one supervisor strategies. Phase 0 didn't
touch any of these; they remain post-deployment work for after the
container ships in Phase 5.

---
