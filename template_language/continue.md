# Template Language — Design State (2026-04-30)

A template system for composing s_engine and chain_tree dict-trees. Templates
are plain Python functions stored in a SQLite/ltree-backed registry. The
runtime user never imports the Python files — they interact only with the
DB via four verbs (`use_template`, `store_template`, `delete_template`,
`list_template`).

This file supersedes the prior `continue.md` (v1, restricted-Python pidgin
proposal). The HTN/railroad doc `code_design.md` and the prose-direction
doc `mission.md` remain as historical context only.

---

## 0. Nothing is locked in yet

**Status: exploratory.** The user has explicitly said they have not done
this kind of system before and the working stance is "feel our way." No
code has been written for the template language itself (the
`template_language/` directory contains only design docs). Every
"decision" recorded below is a tentative resting point from the chat —
**any of it can change** when the user returns with hand-written
templates and we see how the design holds up against real authoring.

In particular: the four-verb API, the function-as-template shape, the
SQLite/ltree storage choice, the per-engine label scheme, the chain_tree
slot-type proposal — none of these are committed. They are the current
best guesses from a conversation that ended deliberately before
implementation. Treat §2 below as "where the design discussion landed,"
not as "what the system is."

The only thing that is real and committed is the engine-side `time_window`
change in §3 — that ships actual code with passing tests, independent of
whatever the template language ultimately becomes.

---

## 1. Where the system sits

```
  user authoring (Python files, locally tested)
              │
              │   store_template(file_or_fn, path=..., kind=..., engines=..., ...)
              ▼
   ┌────────────────────────────────────────┐
   │  SQLite DB with ltree extension        │   .so at /usr/local/lib/ltree.so
   │  ───────────────────────────────────   │   wrapper: /home/glenn/knowledge_base
   │  templates(path, name, version,        │            /kb_modules/kb_python
   │            kind, engines, body_python, │            /sqlite3/ (Construct_KB)
   │            properties JSON, ...)       │
   └────────────────────────────────────────┘
              │
              │   use_template(path, **overrides) → s_engine or chain_tree dict-tree
              ▼
   se_runtime / chain_tree runtime  (unchanged — they consume the dict-tree
                                     exactly as if hand-authored in se_dsl /
                                     ct_dsl)
```

The DB is the **single source of truth and the only registry the runtime
sees**. Python source files are an authoring artifact, smoke-tested locally,
then submitted to the DB. The registry is reusable across LuaJIT later — no
Python decorators, no metaclasses, plain functions plus an explicit
`register(...)` call.

---

## 2. Where the design discussion landed (tentative — see §0)

These are *current resting points*, not commitments. Each was discussed
to a degree of consensus during the session, but the user reserved the
right to revise any of them once real templates expose problems. Read
this section as "the most likely shape" rather than "the agreed shape."

1. **Storage.** SQLite with the ltree.so extension. Use the existing wrapper
   `Construct_KB` from `/home/glenn/knowledge_base/kb_modules/kb_python/sqlite3/`.
   The DB schema is *not yet committed* (see §6 open items).

2. **Surface syntax.** No new DSL. Templates and template-instantiations
   look like ordinary `se_dsl` / `ct_dsl` Python code. No Lisp parens. No
   restricted-Python pidgin via AST parsing (that was the v1 idea and was
   rejected).

3. **Template body shape (Option C).** A template is a plain Python function
   whose **parameters are its slots**. Defaults → optional slot. No default
   → required slot. No `@deftemplate` decorator (LuaJIT portability — Lua
   has no decorators).

4. **Registration (Option 1A).** Plain function + explicit `register(...)`
   call:
   ```python
   def fire_in_window(start, end, child, key="in_window"):
       return se_dsl.sequence(...)

   register(
       path     = "composites.s_engine.fire_in_window",
       kind     = "composite",
       engines  = ["s_engine"],
       body     = fire_in_window,
       describe = "Run child only when wall-clock matches the window.",
   )
   ```
   Both `register(...)` and the template function are visible at module
   import time; the loader runs the file and accumulates the registrations.

5. **Authoring file convention.** One template per Python file. The file
   contains the function, the `register(...)` call, and an
   `if __name__ == "__main__":` smoke test that exercises the template with
   real values and prints / runs the result. The runtime user does **not**
   import these files — they call `store_template(file)` to push the
   contents into the DB, then use the DB. The smoke test stays in the file
   for the author; whether it is preserved in the DB row is open (§6).

6. **API surface — four verbs (probable fifth):**
   - `use_template(path, **overrides)` — resolves an ltree path, runs the
     stored function with overrides, returns its result (an `se_dsl` /
     `ct_dsl` dict-tree fragment, or for chain_tree see §5). Composes inside
     other template bodies and inside solution scripts.
   - `store_template(...)` — write a template into the DB. Takes either a
     function object (uses `inspect.getsource`) or a path to a `.py` file.
   - `delete_template(path)` — remove. Open: cascade behavior when other
     instances reference it.
   - `list_template(**predicates)` — query with kwargs like
     `kind="composite"`, `engine="chain_tree"`, `path_under="composites"`,
     `name_like="%timeout%"`. Builds the WHERE clause itself, no SQL string.
   - `describe_template(path)` — likely needed for LLM authoring; returns
     full slot signature + description for one template.

7. **ltree path = instantiation identity.** Instantiating a template means
   writing a new row at a new ltree path; that row's properties carry the
   override deltas and a parent_path pointing at the source template. To
   "use an instance as a template," reference its ltree path — no separate
   instance API.

8. **`labels` vs `properties`.**
   - `labels` are SQL-searchable indexed columns (probably split into typed
     columns or a side table): `engine_label ∈ {s_engine, chain_tree}`,
     `kind_label ∈ {composite, leaf}`, plus tags. Used in `WHERE` clauses.
   - `properties` is one JSON blob carrying the slot schema, defaults,
     choices, emit refs, override deltas, description, etc. Read whole,
     parsed in Python, never filtered server-side.

9. **Composites and leaves.** Leaves only attach to composites (composites
   can have leaf children; leaves cannot have children). Composites can
   also have composite children. The kind label is what the SQL filter
   uses to enumerate "things I can start a solution with" (composites only).

10. **Engine asymmetry.** s_engine and chain_tree have non-isomorphic
    primitives. The same logical template name has **different bodies on
    each engine**, registered at distinct ltree paths
    (`composites.s_engine.X` vs `composites.chain_tree.X`), with the
    `engines` label distinguishing them in queries. No internal
    `if engine == "..."` branching in template bodies.

11. **Working stance.** Feel-our-way, no premature lock-in. Build the
    smallest end-to-end demo first; let API choices fall out of "what does
    this real template need?" Pick the dumb option when in doubt.

12. **LLM authoring is a real constraint.** The four verbs must be small
    and stable. `list_template` and `describe_template` must return enough
    structured metadata for an LLM to pick + compose templates without
    reading source. Errors must be structured ("unknown slot 'foo'; valid
    slots are [...]") so the LLM can self-correct.

---

## 3. Engine-side change already landed (real code, committed-ready)

The wall-clock `time_window` operator was rewritten in **both engines** to
support per-field semantics (the previous "compose into seconds-of-day"
shape couldn't express "fire every minute when sec=15"). User signed off,
all tests passing.

**New semantics (uniform across `hour, minute, sec, dow, dom`):**
- Both `start[f]` and `end[f]` present → field constrained to
  `[start[f], end[f]]` inclusive, wrap-aware (end < start wraps).
- Both absent → field unconstrained.
- Exactly one present → ValueError (paired-or-absent rule).
- Final answer = AND of all five per-field checks.

**Files changed:**
- `s_engine/se_builtins/time_window.py` — implementation rewritten, helper
  `_sod_from_parts` removed, all five fields routed through the existing
  `_mask_field_ok`. Module docstring updated.
- `chain_tree/ct_builtins/time_window.py` — identical change.
- `s_engine/se_dsl/primitives.py` — `time_window_check` docstring updated.
- `chain_tree/ct_dsl/builder.py` — `asm_time_window_check` docstring updated.
- `s_engine/tests/test_time_window.py` — replaced
  `test_start_minute_boundary_excludes_earlier`, added
  `test_paired_minute_constrains_per_field`,
  `test_half_specified_{minute,sec,hour}_raises`, plus four per-field
  semantics tests.
- `chain_tree/tests/test_time_window.py` — parallel additions on the
  native side.

**Test status:** s_engine 197/197, chain_tree 136/136.

The user's "every time when sec=15" demo case is now expressible as
`start={"sec":15}, end={"sec":15}`.

---

## 4. The three demo templates (the working scope)

These were chosen as the smallest concrete grist for the design. The user
is **hand-writing them in the next session**; this file describes their
intended shapes.

### 4.1 `print_hello` (leaf)

- `leaves.s_engine.print_hello` — `def print_hello(): return se_dsl.log("hello")`. No slots.
- `leaves.chain_tree.print_hello` — equivalent using chain_tree primitives. Shape per §5.

### 4.2 `fire_in_window` (composite, gates a child on a time window)

- `composites.s_engine.fire_in_window`:
  ```python
  def fire_in_window(start, end, child, key="in_window"):
      return se_dsl.sequence(
          se_dsl.time_window_check(key=key, start=start, end=end),
          se_dsl.if_then(
              pred  = se_dsl.dict_eq(key=key, value=True),
              then_ = child,
          ),
      )
  ```
  Slots: `start`, `end` (required, dict), `child` (required, dict-or-template),
  `key` (optional, default `"in_window"`).

- `composites.chain_tree.fire_in_window` — pending; chain_tree doesn't
  ship a clean conditional composite, so the body is non-obvious. Probably
  a column with an aux boolean fn that reads the blackboard flag set by
  `asm_time_window_check`. Decide when writing.

### 4.3 `am_pm_state_machine` (composite, three-state)

States: `unknown` (initial), `am`, `pm`. The `unknown` state runs once at
startup, reads the wall clock, dispatches to `am` or `pm`, and is never
re-entered. AM/PM each watch the wall clock for noon crossings and post
transitions back the other way.

Slots: `am_action`, `pm_action`. Both required; both accept a leaf, a
composite, or another instantiated template.

The s_engine and chain_tree bodies look fundamentally different — see §5.
This is the template that exposed the engine-asymmetry problem most
clearly.

---

## 5. The chain_tree shape problem (open architectural question)

**Discovery from this session:** chain_tree templates cannot have the
same `(slots) -> dict` shape as s_engine templates. Three reasons, all
real:

1. **chain_tree is builder-based.** `define_state_machine` /
   `define_state` / `end_state_machine` push and pop frames on a
   `ChainTree` instance. There is no "return a state-machine dict
   fragment" form — the SM is constructed by side effect on the builder.

2. **`asm_change_state(sm, "target")` requires a Python ref to the SM
   node**, and this ref only exists after the SM has been opened. So
   any leaf that fires a transition has to be constructed inside the SM's
   builder context, not in a separately-emitted fragment.

3. **No native if-then-else primitive.** `asm_verify` is
   "if-not-then-terminate-parent." Conditional state changes (the
   `unknown` state's wall-clock dispatch) require a custom **user-
   registered main fn** (or one-shot) that reads the clock and posts a
   `CFL_CHANGE_STATE_EVENT`. The template body has to call
   `chain.add_main("AM_PM_DECIDE", fn, ...)` itself.

**Therefore chain_tree template bodies are likely shaped:**
```python
def am_pm_state_machine(chain, am_action, pm_action):
    chain.add_one_shot("AM_PM_DECIDE_INITIAL", _decide_initial)
    chain.add_main("AM_PM_WATCH",              _watch_for_noon_cross)
    sm = chain.define_state_machine("am_pm",
        state_names=["unknown","am","pm"], initial_state="unknown")
    chain.define_state("unknown")
    chain.asm_one_shot("AM_PM_DECIDE_INITIAL", data={"sm_node": sm})
    chain.end_state()
    chain.define_state("am")
    am_action(chain, sm)        # slot is a callable, not a dict
    chain.end_state()
    chain.define_state("pm")
    pm_action(chain, sm)
    chain.end_state()
    chain.end_state_machine()
    return sm
```

Implications, all unresolved:

- **First parameter is the `ChainTree` builder**, not a slot. The user
  doesn't supply it; it's supplied by the surrounding construction
  context.
- **Slot type for action slots is `(chain, sm) -> None`** (a callable),
  not a dict. The user "attaches a leaf" by passing a small function
  that issues the right builder calls.
- **`use_template("...chain_tree...")` returns a closure** over (chain,
  sm), not a dict. Different mental model than s_engine's "use_template
  returns a tree dict."
- **Templates may need to register engine-side user fns** as part of
  body execution. That is more than dict-composition — it pokes the
  engine's fn registry.

**Decision deferred** to when the user brings their hand-written templates.
Three plausible directions:

A. Accept the asymmetry. Per-template slot type declarations in
   `properties`. The registry knows "this slot expects a callable, that
   one expects a dict." `use_template` returns whichever the called
   template's body returns.

B. Define a thin shim layer on top of chain_tree that exposes a more
   functional, dict-returning composition (similar to what `ct.make_node`
   already supports for leaves), so chain_tree templates can adopt the
   same `(slots) -> dict` shape as s_engine. Costs: probably need a
   parallel mini-DSL for chain_tree state machines.

C. Drop the "same logical template across engines" goal entirely. Treat
   s_engine and chain_tree as separate registries with no overlap claim;
   each engine has its own template authoring style.

---

## 6. Open items (not blocking the next session, but listed)

1. **SQLite schema** — proposed shape exists in chat history but is not
   committed. Single `templates` table (or two: templates + instances).
   Columns: `path` (ltree), `name`, `version`, `kind` (composite|leaf),
   `engines` (or `engine_label` indexed column), `parent_path`,
   `body_python` (text), `properties` (JSON), `description`,
   `frozen`, audit columns.

2. **chain_tree slot-type asymmetry** (§5) — decide A / B / C.

3. **Granular list/dict writes**, version pinning, override-precedence
   rules, caching policy, exec sandboxing — all deferred per "feel-our-
   way" stance until a real template forces the question.

4. **Whether `if __name__ == "__main__":` blocks are stored** in the DB
   `body_python` column or stripped at `store_template` time.

5. **chain_tree `fire_in_window` body** — needs writing; depends on
   reading `ct_builtins/controlled.py` and figuring out the natural
   "gate a column on a blackboard bool" idiom.

6. **`initial` state choice on first tick** in the s_engine state machine
   variant (clock-aware initial vs. one-tick lag). Not relevant to
   chain_tree because the `unknown` state explicitly handles startup.

---

## 7. The user is writing templates next session

User stated they will hand-write the three demo templates and bring them
in. The intent is to use the templates as concrete grist — let the API
shape fall out of "what does this template need to be expressible?"
rather than designing the API in the abstract.

When the user returns with templates:

1. Read what they wrote — function signature reveals their slot
   intuitions, body reveals which DSL primitives they reach for, smoke
   test reveals their preferred call shape.
2. Match the templates against the (still-tentative) shapes in §4–§5.
3. Resolve §5's slot-type question if the chain_tree templates are
   among them. If only s_engine, defer.
4. From the resolved shapes, draft `register(...)` and the four DB
   verbs. Don't generalize beyond what the three templates need.

---

## 8. Repo pointers

- Root: `/home/glenn/robot_person/`
- This package: `/home/glenn/robot_person/template_language/` (no code
  yet — only `mission.md`, `code_design.md`, this file).
- `s_engine`: `/home/glenn/robot_person/s_engine/` — Python port complete,
  197 tests passing.
- `chain_tree`: `/home/glenn/robot_person/chain_tree/` — Python port
  complete, 136 tests passing.
- ltree extension: `/usr/local/lib/ltree.so`.
- ltree wrapper: `/home/glenn/knowledge_base/kb_modules/kb_python/sqlite3/`.
- Test invocation: source `/home/glenn/robot_person/enter_venv.sh` (sets
  PYTHONPATH and activates `.venv/`). Non-interactive: see the
  `reference_test_invocation` memory.
