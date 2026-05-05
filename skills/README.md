# skills/

Engine-agnostic Python skills. Each skill is a small directory with one
public class plus an `if __name__ == "__main__":` test driver.

## Convention

```
skills/<skill_name>/
├── main.py        # exports ONE class; ends with `if __name__ == "__main__":` block
├── continue.md    # session notes (optional but encouraged)
├── tests/         # pytest unit tests (optional; complement to __main__)
└── ...            # helper modules: drivers, decoders, schemas
```

Rules:

1. **One class per skill.** The class represents a leaf or a subtree.
   If a skill grows a second responsibility, factor that responsibility
   into a *new* skill rather than adding methods. Example:
   `lorwan_moisture` is fetch-only; the SQL-read side becomes a separate
   `sqlite_query` skill that any sensor skill can compose with.

2. **Engine-agnostic.** No `chain_tree` or `s_engine` imports inside a
   skill. Engine integration happens via thin template adapters under
   `user_templates/templates/leaves/<engine>/` (or per-robot template
   directories), which import the skill's class and call it from inside
   an `asm_*` body.

3. **`__main__` is a real smoke test.** It runs the class against real
   systems (real TTN, real DB, real hardware where reasonable). It is
   the standalone proof that the skill works before any wrapping. Fast
   unit tests live under `tests/`.

4. **Helper modules live alongside `main.py`.** `ttn_client.py`,
   `decoder.py`, `db.py`, etc. are imported by `main.py`. Only `main.py`
   exports the skill's public class.

5. **Secrets out of code.** Credentials live in env files or per-robot
   `secrets/` directories, never embedded in the skill source.

## Layers above this one

- `user_templates/` — thin chain_tree/s_engine wrappers around skill
  classes; multi-root prefix `user`.
- `user_skills/` — goal-shaped, LLM-addressable solution-fragments
  composed of templates; multi-root prefix `skill`. (Different from
  this directory: `skills/` here is engine-agnostic Python, not a
  template-language artifact.)
- `robots/<robot_name>/` — per-deployment projects that compose
  templates (which wrap skills) into runnable solutions.
