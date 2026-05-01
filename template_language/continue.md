# Template Language — Design State (2026-04-30 design / 2026-05-01 implementation)

---

## SESSION LOG — 2026-05-01: Phases A, B, C, D + lazy loader landed

132/132 tests passing. The chain_tree side of the v1 acceptance gate is
green: `am_pm_state_machine` round-trips define → use → generate → run
across multiple ticks (initial state dispatches via wall clock, AM/PM
state runs its action on the next tick) for both AM and PM clock
fixtures. All five Phase D verbs plus `op_list_to_python` /
`op_list_to_json` and the lazy-import loader are in place.

### What landed

  - **kinds.py** — `Kind` enum (16 kinds), `annotation_to_kind` (handles
    `Optional[X]`, PEP 604 `X | None`, bare types, `Callable`),
    `validate_value_against_kind` (RecRef class injected to break a
    circular import).
  - **errors.py** — `TemplateError` with `code/stage/template_stack/
    details/to_dict()`, stage auto-lookup from code, `Codes` constants.
  - **recorder.py** — `Op` (with `out_ref` field — see Spec deviations),
    `RecRef` (opaque, integer-id, hashable), `OpList`, `Recorder` with
    `__getattr__` shim that records and returns RecRef. Frame discipline
    by suffix matching (`define_X` / `start_X` push kind=X, `end_X`
    pops). Five name namespaces enforced: engine_fn / kb / sm (global),
    state (per-SM frame), column (per-frame). Module-level
    `_recorder_stack` plus `merge_global_names` for splice-time
    cross-template collision detection.
  - **ct.py** — `_CtProxy.__getattr__` resolves to active recorder;
    raises `ct_used_outside_template` on empty stack.
  - **registry.py** — `Slot`, `RegisteredTemplate`, `define_template`
    using `inspect.signature(eval_str=True)` to resolve PEP 563 lazy
    annotations. `clear_registry` test helper, `list_paths` helper.
  - **expansion.py** — `use_template`. Cross-engine check before slot
    validation. Outermost call returns `OpList`; nested returns `None`
    after splicing the inner op-list and merging the inner's global
    name claims into the parent's registries.
  - **replay.py** — `generate_code` dispatches on `op_list.engine`,
    walks ops, recursively substitutes RecRefs in args / kwargs / dicts /
    lists / tuples via `id(out_ref) → real_return` map. Wraps engine
    exceptions in `replay_op_failed` with `template_stack` from
    `op.source`.
  - **conftest.py** — adds parent dir + `chain_tree` to sys.path
    (matches chain_tree's own conftest convention).
  - **templates/composites/chain_tree/am_pm_state_machine.py** — the
    first real template. The DECIDE one-shot reads
    `handle["engine"]["get_wall_time"]()` and posts
    `CFL_CHANGE_STATE_EVENT` directly via `enqueue` + `make_event`.
  - **validation.py** — `validate_solution(path, **slots)` wraps
    `use_template + generate_code` in try/except and returns either
    `{"ok": True}` or `{"ok": False, **error.to_dict()}`. The LLM
    closed-loop verb (§12.6).
  - **render.py** — `op_list_to_python(op_list, builder_name="chain")`
    pretty-prints the op-list as Python source with frame indentation
    and RecRef-as-variable-name rewriting; `op_list_to_json(op_list)`
    produces a JSON-safe dump (callables and RecRefs become opaque
    markers). One-way per §2.
  - **registry.py lazy loader** — `get_template(path)` falls back to
    `importlib.import_module("template_language.templates." + path)`
    on registry miss. If the module is already cached but the path
    isn't in the registry (registry was cleared), the loader evicts
    from `sys.modules` and re-imports so the top-level
    `define_template(...)` runs again. `load_all()` walks
    `templates/` via `pkgutil` for bulk imports.
  - **conftest.py** — autouse `_clean_registry` fixture clears the
    registry before+after each test. Always-on templates are no longer
    hardcoded in conftest; the lazy loader handles them on demand.
  - **12 test files** under `tests/`. Coverage: **20 of 20** error
    codes raised by at least one test (audited 2026-05-01).

### Spec deviations / gaps discovered while implementing — RESOLVED

The first three items below were resolved by editing
`template_design.txt` in this session. Item 4 is informational only.

  1. **Code-count discrepancy — RESOLVED.** Spec said "21 codes" in
     four places (§0, §10, §17 twice) but enumerated 20 (7+10+3).
     Edited spec prose to say 20 everywhere. `errors.py` asserts
     `len(ALL_CODES) == 20`.

  2. **§13.2 unrunnable example — RESOLVED.** Old §13.2 called
     `chain.run(starting=["time_of_day_sm"])` as if `sm_name` were a
     KB name; `define_state_machine` requires a parent frame so the SM
     template alone never opens a KB. Edited §13.2 to show a wrapping
     `solutions.chain_tree.am_pm_demo` template that brackets the SM
     template in `start_test` / `end_test`. §13.3 op-list updated to
     include the wrapper's two extra ops. Lazy-loader note added.

  3. **`Op.out_ref` was unspec'd — RESOLVED.** §3 now describes the
     full Op dataclass (with `out_ref: Optional[RecRef]`) and explains
     the RecRef-allocation-per-op rule plus the
     `refs[id(op.out_ref)] = real_return` substitution mechanism.

  4. **Slot kind for `start_test` etc. — informational.** §5.5's
     signature constraints don't say what kind to give first-positional
     name parameters in builder-shadow methods. Not a bug — the
     recorder operates on raw args/kwargs and doesn't validate names'
     types. Name args are always strings in practice; no special kind
     needed.

### Test status

  - chain_tree: 136/136 still passing (independent).
  - s_engine: 197/197 still passing (independent).
  - template_language: 132/132.
  - The engine-side `time_window` change from §3 is **already
    committed** (86afab1: "chain_tree + s_engine: time-window wait
    leaves and predicate"). Earlier notes saying it was uncommitted
    were wrong.

### Next steps (next session, in this order)

  1. **E1**: `fire_in_window` for chain_tree. Read
     `chain_tree/ct_builtins/controlled.py` first; design the
     "gate-a-column-on-a-blackboard-bool" idiom.
  2. **E2**: `print_hello` leaves for both engines (trivial fillers
     for `templates/leaves/`).
  3. **E3**: s_engine recorder. Per `feedback_engine_independence`,
     design to s_engine's own machinery, not a chain_tree mirror —
     `_FRAME_OPENERS`, `_FRAME_CLOSERS`, `_NAME_NAMESPACE` will look
     different.
  4. **E4**: `fire_in_window` for s_engine. Distinct ltree path.
  5. **F**: DB layer — deferred per §16.

### Patterns established this session

  - **Lazy loader convention.** A template registered at ltree path
    `composites.chain_tree.foo` lives in
    `template_language/templates/composites/chain_tree/foo.py`. The
    lazy loader resolves on first `use_template` / `describe_template`
    call. Authors who deviate get `unknown_template` until they fix
    the file.
  - **Test fixture coexistence.** Conftest's autouse
    `_clean_registry` fixture coexists with per-file `_clean` fixtures
    that also clear; both run, the global runs first (outer), the
    local runs inside it. No test snapshot/restore is needed — the
    lazy loader repopulates always-on templates on demand.

---

# Template Language — Design State (2026-04-30, locked)

A two-phase template system over s_engine and chain_tree. Templates are
plain Python functions whose keyword-only parameters are slots. Phase 1
runs the body against a Recorder, producing an op-list; phase 2 replays
the op-list against the real engine builder. The DB-backed registry
(SQLite/ltree) is the eventual source of truth at runtime; the v1
implementation uses an in-process registry so the design can land
end-to-end before storage is wired in.

**Authoritative spec for the template engine machinery is now
`template_design.txt`** (rewritten in the 2026-04-30 session, ~700
lines, fully locked). This file retains the storage / DB-registry plan
and the historical session log; for everything else, defer to
`template_design.txt`.

The HTN/railroad doc `code_design.md` and the prose-direction doc
`mission.md` remain as historical context only.

---

## 0. Status — locked as of 2026-04-30

The template engine design was locked end-to-end in the 2026-04-30
session. The major decisions:

  1. **Two-phase model** — phase 1 records ops via a Recorder; phase 2
     replays into a real engine builder. Op-list is the only
     intermediate; no text substitution, no AST, no codegen.
  2. **`generate_code` returns just the engine artifact** — no
     metadata, no struct. Template engine has no role after phase 2.
  3. **Engine identity is singular and mandatory** at registration.
     No mixed-engine templates. Cross-engine composition rejected at
     expansion. Bridges (chain_tree's `add_se_*`) are slot values
     crossing between two single-engine builds, not template-internal
     mixing.
  4. **Recorder stack is a plain module-level list**, not a contextvar.
     Single-context, matching chain_tree's discipline.
  5. **Slot kinds enforced via Python annotations.** Fixed kind
     vocabulary (STRING, INT, FLOAT, BOOL, DICT, LIST, RECREF, ACTION,
     ENGINE_MAIN, ENGINE_BOOLEAN, ENGINE_ONE_SHOT, ENGINE_SE_*, ANY).
     Nullability is a slot attribute, not a kind.
  6. **Closure-based fn parameterization** — the C++ template analogy.
     Inline closures capture slot values; registered under
     slot-derived names; collisions are hard-error.
  7. **Hard-error rule for all collisions** — no `force=True`, no
     "last wins." Author must restructure or rename. Force fix.
  8. **Unified error vocabulary** — single `TemplateError` class with
     `code`, `stage`, `template_stack`, `details`. 21 codes split
     across registration / expansion / replay stages.
  9. **Invariant boundary** — recorder catches template-system
     invariants (stack, names, kinds, engine); replay catches engine-
     builder invariants (op-arg semantics, RecRef resolution).
 10. **LLMs compose pre-tested templates into solutions; they do not
     author new templates.** This narrows the LLM use case and means
     `validate_solution` is the closed-loop verb (not a generation
     loop).
 11. **Everything is a template** — leaf, composite, solution
     differ by convention only; same registry, same verbs, same
     machinery.

`template_design.txt` §17 contains the implementation plan for the
next session (Phases A–F). The v1 acceptance gate is the
`am_pm_state_machine` round-trip: define → use → generate → run for
one tick, with all 21 error codes covered by tests.

The engine-side `time_window` change in §3 below is independent of
the template engine; it ships actual code with passing tests but is
**still uncommitted** in the working tree as of 2026-04-30.

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

## 5. The chain_tree shape problem — RESOLVED 2026-04-30

**Resolution.** Direction A from the original list, but reshaped: the
two engines do not try to share a `(slots) -> dict` body shape at all.
Both engines use the same template machinery — function with kw-only
slots, op-list intermediate, closure-based fn parameterization — but
each engine's recorder shadows its own builder surface. Templates are
single-engine (`engine="chain_tree"` or `engine="s_engine"`); cross-
engine composition is rejected at expansion. Bridges (chain_tree's
`add_se_*`) are slot values crossing between two single-engine builds
at the user's solution level, not template-internal.

The `(chain, sm) -> None` callable shape proposed below is also
**superseded**. Action slots are zero-arg callables; the active builder
is reached via the module-level `ct` proxy, which resolves through the
recorder stack. RecRefs from recorder methods (e.g. `define_state_machine`
returning a state-machine RecRef) flow between templates as ordinary
slot values with kind `RECREF`.

See `template_design.txt` §3, §4, §5, §6, §7 for the locked design.

The original open question and three options below are preserved as
historical context.

---

**Original discovery (2026-04-30 morning):** chain_tree templates
cannot have the same `(slots) -> dict` shape as s_engine templates.
Three reasons, all real:

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

## 7. Next session — implementation

The 2026-04-30 design session locked the engine. The next session
implements per `template_design.txt` §17 (Phases A–F). The v1
acceptance gate is the `am_pm_state_machine` round-trip:

  1. Phase A — kinds.py, errors.py, recorder.py, ct.py
  2. Phase B — registry.py, expansion (use_template), replay.py
  3. Phase C — first real template + acceptance test
  4. Phase D — list_template, describe_template, validate_solution
  5. Phase E — second template (fire_in_window), then s_engine recorder
  6. Phase F — DB layer (deferred)

Definition of done for v1:
  - chain_tree recorder + replay implemented.
  - One leaf and one composite template hand-written + registered.
  - `am_pm_state_machine` round-trip test passes (build + one tick).
  - All 21 error codes raise from at least one test.
  - `describe_template` returns the documented JSON shape.
  - No DB, no s_engine side, no LLM verbs.

Test invocation: source `enter_venv.sh` from
`/home/gedgar/robot_person/`, run pytest from `template_language/`.

---

## 8. Repo pointers

- Root: `/home/gedgar/robot_person/`
- This package: `/home/gedgar/robot_person/template_language/` (no code
  yet — only `mission.md`, `code_design.md`, this file).
- `s_engine`: `/home/gedgar/robot_person/s_engine/` — Python port complete,
  197 tests passing.
- `chain_tree`: `/home/gedgar/robot_person/chain_tree/` — Python port
  complete, 136 tests passing.
- ltree extension: `/usr/local/lib/ltree.so`.
- ltree wrapper: `/home/glenn/knowledge_base/kb_modules/kb_python/sqlite3/`.
- Test invocation: source `/home/gedgar/robot_person/enter_venv.sh` (sets
  PYTHONPATH and activates `.venv/`). Non-interactive: see the
  `reference_test_invocation` memory.
