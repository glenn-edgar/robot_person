# robot_person

Behavior-tree representation of a robot person. Python port of the ChainTree
S-Expression engine, targeted at industrial SCADA-style operator workloads.

## Layout

- **`s_engine/`** — the engine. See [`s_engine/README.md`](s_engine/README.md)
  for the quick-start, the 74-name DSL surface, layout, and test
  instructions.
- **`continue.md`** — the authoritative design specification. Read this
  before making engine-level changes.
- **`enter_venv.sh`** — sourceable script that activates `.venv/` and sets
  `PYTHONPATH` to `s_engine/`. Use: `source enter_venv.sh`.

## Status

Library-level port complete. 173 tests passing. Runner layer
(standalone-exe supervisor + external-feeder adapter) is deferred pending
transport choice.
