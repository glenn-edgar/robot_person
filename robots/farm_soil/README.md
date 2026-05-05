# farm_soil

First real robot deployment. Polls SenseCAP S2105 soil-moisture
sensors via The Things Network (TTN) storage API, writes to a local
SQLite database, runs as a chain_tree state machine.

## Layout

```
farm_soil/
├── bootstrap.py                 # registers prefix=project.farm_soil
├── hardware.yaml                # devices + TTN app + measurement IDs
├── config/{dev,prod}.yaml       # per-deployment values
├── secrets/                     # gitignored; copy ttn.env.example → ttn.env
├── drivers/                     # robot-specific glue (TBD)
├── db/                          # schema + writer (TBD; may live in skill)
├── templates/
│   ├── leaves/chain_tree/       # robot-specific chain_tree leaves (TBD)
│   ├── composites/chain_tree/   # robot-specific subtrees (TBD)
│   └── solutions/chain_tree/    # the runnable KB(s) (TBD)
├── run.py                       # entry point (TBD)
├── conftest.py                  # autouse bootstrap for pytest
└── tests/                       # smoke + integration (TBD)
```

## Skill it depends on

- `skills/lorwan_moisture/` — TTN poll + SQLite write (fetch-only).
  The robot wraps this skill via a chain_tree leaf template (location
  TBD: `user_templates/` if reused across robots, or
  `templates/leaves/chain_tree/` if farm_soil-specific).

## Run

```sh
source enter_venv.sh
python -m robots.farm_soil.run --config dev
```

## Status

Scaffolding only — no leaves, no solutions yet. Next steps:

1. Refactor `skills/lorwan_moisture/main.py` to expose one class
   (per the skills/README.md convention) with helpers split into
   `ttn_client.py`, `decoder.py`, `db.py`.
2. Decide where the chain_tree wrapper template lives
   (user_templates vs farm_soil-local).
3. Write the wrapper template + a minimal solution (one tick → one
   poll → exit).
4. Smoke test against real TTN with dev config.
