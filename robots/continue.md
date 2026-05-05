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
