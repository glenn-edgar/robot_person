# Template Language — Design Spec

A **preprocessor** that sits above `../s_engine` and generates `se_dsl`
dict-trees (the s_engine's existing tree format). The engine never sees
templates — it runs the fully-expanded tree exactly as if it had been
hand-authored in `se_dsl`.

Supersedes the prose direction in `mission.md` and the HTN/railroad
proposal in `code_design.md` for this repository. Those documents remain
for historical context.

---

## 1. Position in the stack

```
  design time     │ startup                            │ engine time
                  │                                    │
  registry.add(…) │ instance = deep_expand(registry)   │ new_module(...)
  registry.freeze │ pidgin_exec(script, instance)      │ register_tree(mod,
                  │ validate(instance)                 │   "main", tree)
                  │ tree = emit(instance)              │ push_event / tick
                  │ ──────────────────────────────     │
                  │       engine boundary              │
```

Preprocessing is **offline and independent of the engine**. By the time
`se_runtime` touches anything, only a `se_dsl` dict-tree exists.

The 74 existing `se_dsl` functions (~67 primitives + 7 macros in
`s_engine/se_dsl/`) are **library code, untouched.** Templates compose
them. Slot values reach those functions only as arguments to `se_dsl.*`
calls.

---

## 2. Core data structures

Two top-level dicts. Plain Python. No classes, no metaclasses.

```python
registry = {
    template_name: {
        slot_name: {
            "type":          str,       # primitive or registered template name
            "value":         Any,       # absent key = required slot
            "choices":       list,      # optional; enumerated legal values
            "element_type":  str,       # optional; list/dict homogeneity (strict)
        },
        ...
    },
    ...
}

commands = {
    template_name: {
        "emit":     callable,   # the override hotspot
        "validate": callable,
        "describe": callable,
        "get":      callable,
        "set":      callable,
    },
    ...
}
```

### 2.1 Slot shape

Uniform `{type, value, choices?, element_type?}`. Key invariants:

- **Required slot:** `value` key is absent. Presence of `value` means a
  baked default. (`None` is a legitimate bound value; don't use it as a
  required sentinel.)
- **`choices`:** if present, `value` must be a member.
- **`element_type`:** if present, strict — every element's `type` must
  equal it. Absence means heterogeneous.

### 2.2 Type alphabet

Closed, system-defined set:

- **Primitives:** `"string"`, `"number"`, `"bool"`, `"list"`, `"dict"`.
- **Registered template names:** every top-level key of `registry` is
  also a legal `type`. A slot with `type == "email"` means "an instance
  of the `email` template; `value` is the bindings dict."
- **Abstract placeholders** (pidgin-bound at use time):
  `"template"` (any registered template), `"list"` / `"dict"`
  without `element_type` (any homogeneous or heterogeneous container).

### 2.3 Uniform namespace addressing

Every slot anywhere in the tree is reachable by dotted path from a
registry root:

```
my_agent.watchdog.seconds          # primitive slot
my_agent.retry.action.0            # nth element of a list slot
my_agent.sm.states.idle.action     # dict-key into a dict slot, then sub-slot
```

The rule: to step into a `value`, if it is a dict of slot records, key
or integer-index into it. Works for sub-template bindings, list
elements, and dict entries identically.

### 2.4 Container slots

Lists and dicts hold **slot records** recursively:

```python
{
    "type": "list",
    "element_type": "email",   # optional strict constraint
    "value": [
        {"type": "email", "value": {...}},
        {"type": "email", "value": {...}},
    ],
}

{
    "type": "dict",
    "element_type": "action",
    "value": {
        "idle":    {"type": "action", "value": {...}},
        "running": {"type": "action", "value": {...}},
    },
}
```

---

## 3. DSL helper (design time)

Explicit, pure-ish registration. Matches `se_dsl.make_node` style — no
hidden module-level state.

```python
from template_language import Registry, slot

registry = Registry()

registry.add("with_timeout",
    slot("action",           type="template"),
    slot("seconds",          type="number", value=30),
    slot("on_timeout",       type="template"),
    slot("reset_on_timeout", type="bool", value=False, choices=[True, False]),
    emit=tier1.with_timeout,
)
```

- `registry.add(name, *slots, emit=<fn>, validate=<fn>, describe=<fn>)`
  registers a template. `slot(name, **kwargs)` returns a
  `(name, slot_dict)` tuple that `add` collects into a dict.
- The five reference commands auto-populate on registration. User
  overrides by passing `emit=`, `validate=`, etc. to `add`, or by
  writing into `commands[name]` afterward.
- `emit=<callable>` binding mode: **kwargs by default.** The wrapper
  calls `emit(**filled_slot_values)`. An escape hatch (proposed:
  `@full_emit` decorator on the function) passes the whole instance
  record instead, for templates that need full-tree context.

### 3.1 Profile templates

Profile proliferation is expected and **encouraged**. Two templates
sharing an emit function but shipping different baked defaults is the
normal pattern:

```python
registry.add("retry_aggressive",
    slot("attempts",   type="number", value=10),
    slot("base_delay", type="number", value=0.1),
    slot("action",     type="template"),
    emit=tier2.retry_with_backoff,
)

registry.add("retry_careful",
    slot("attempts",   type="number", value=3),
    slot("base_delay", type="number", value=5.0),
    slot("action",     type="template"),
    emit=tier2.retry_with_backoff,
)
```

The value of the system is that **canned profiles pre-fill most slots**,
so user pidgin is a handful of overrides:

```
my_agent.recovery = retry_careful(action=escalate_to_operator())
```

**No `registry.profile(base=..., overrides=...)` shorthand in v1.**
Revisit if duplication becomes painful.

---

## 4. Registry freeze

After all `add()` calls, `registry.freeze()`:

1. Walks every slot with `type` ∈ registered template names, confirms
   the target exists. Unknown references → hard error.
2. Walks the template dependency graph. Detects cycles. A cycle → hard
   error (eager expansion requires acyclic graph).
3. Marks registry immutable. Further `add()` calls raise.

Freeze is cheap (single pass). The cost of late failure is much higher
than running freeze every startup.

---

## 5. Instantiation (startup)

**Eager deep expansion.** Takes a frozen registry + a root template
name, returns a concrete, filled-in instance tree.

```python
instance = deep_expand(registry, root="my_agent")
```

Rules, applied recursively:

- Slot `type` is a **registered template name** → replace `value` with
  a deep copy of that template's slot-dict (baked defaults pulled in).
  Recurse into the copy.
- Slot `type` is `"template"` (abstract) → leave alone. Slot is
  required; pidgin must bind it.
- Slot `type` is `"list"` or `"dict"` with `element_type` → leave the
  container empty-but-typed. Pidgin populates.
- Slot `type` is a primitive → already has `value` (from baked default)
  or is required.

Post-expansion, every dotted path resolves to a real slot record —
pidgin needs no "descend into references" logic. Uniform tree walk.

---

## 6. Pidgin (user / AI config)

Restricted Python subset, parsed via `ast.parse`. Grammar:

### 6.1 Accepted

- **Dotted-path assignments**, LHS rooted at a registry namespace:
  ```
  my_agent.watchdog.seconds = 30
  my_agent.retry.action     = [publish_alert(...), publish_alert(...)]
  ```
- **Python literals**: numbers, strings, bools, `None`, list `[...]`,
  dict `{...}`.
- **Template constructors**: any bare name resolving to a registered
  template is a callable. `name(slot=val, ...)` returns a slot record
  `{"type": name, "value": {slot: filled, ...}}`.
- **Attribute / subscript on LHS** to step into sub-template, list
  index, or dict key:
  ```
  sm.states.idle.action = ...
  sm.states["idle"].action = ...
  retry.action.0.severity = "crit"     # granular writes are DEFERRED (see §6.4)
  ```

### 6.2 Rejected

- `import`, `def`, `class`, `if`, `for`, `while`, `try`, `with` —
  no control flow, no definitions, no context managers.
- Free variables that do not resolve to a registered template or a
  prior assignment.
- Any LHS not rooted in the registry namespace.

### 6.3 Implementation

`ast.parse` → `NodeVisitor`. Whitelisted node types:
`Module`, `Assign`, `Attribute`, `Subscript`, `Call(func=Name)`,
`Constant`, `List`, `Dict`, `Name`, `keyword`, `Load`, `Store`.
Anything else → syntax error.

Template-name callables are synthesized from the frozen registry at
parse start.

### 6.4 List/dict mutation — v1 limit

**Full-replace only:**
```
my_agent.retry.action = [publish_alert(...), publish_alert(...)]
```

Deferred to v2: `append(...)`, index assignment, dict-key assignment.
Revisit when ergonomics demand.

### 6.5 Error handling

- **Parse errors** (syntax, unknown template, unresolved name,
  unresolvable path) → **fail-fast**, stop on first.
- **Bind errors** (type mismatch on RHS, out-of-choices value,
  element_type violation) → **collect-all** into the validation error
  list (§7).

### 6.6 Commands not callable from pidgin

`emit`, `validate`, `describe`, `get`, `set` are programmatic API,
invoked by the runner. Pidgin binds values. That's all.

---

## 7. Default validate

Runs after pidgin completes. Collects all errors before reporting.

Checks:

1. **Required present.** Every slot with `value` key still absent is
   flagged.
2. **Type match.** `value` for a primitive slot is the right Python
   type. `value` for a template-typed slot is a slot record whose
   `type` equals the declared template name.
3. **`choices` membership.** If `choices` is set, `value ∈ choices`.
4. **`element_type` strict.** For list/dict slots with `element_type`,
   every element's `type` equals `element_type`.
5. **Template ref resolution.** Any referenced template name exists in
   the registry (already checked at freeze; re-checked because pidgin
   may introduce names).

### 7.1 Error format

```python
@dataclass
class ValidationError:
    path:    str        # "my_agent.watchdog.seconds"
    code:    str        # "required" | "type" | "choices" | "element_type" | "unknown_template"
    message: str
```

Returned as a list; empty list = success.

### 7.2 Per-template override

User-provided `validate` runs **after** defaults. It receives the same
instance view and returns additional errors. It cannot bypass defaults.

---

## 8. Emit

Bottom-up walk of the validated instance. Every template's `emit`
command is called with its filled slot values. The result of each call
is a `se_dsl` dict (or dict sub-tree). Parents receive their children's
already-emitted sub-trees as slot arguments.

```python
tree = emit(instance)
```

The emitted tree is **byte-for-byte the shape `se_dsl` would produce
by hand**. No new node types, no wrapper layer.

### 8.1 Emit at scale

Templates may produce arbitrarily large sub-trees. A single `emit` can
call `se_dsl.*` hundreds of times and return a nested structure
dozens of levels deep. This is the point of the system — one template
call replaces a lot of hand-written DSL.

Example:

```python
def interlock_with_timeout_emit(
    sensor_id, threshold, action, timeout_sec, fallback,
):
    return se_dsl.sequence(
        se_dsl.wait_event(sensor_id),
        se_dsl.if_then_else(
            se_dsl.dict_gt(sensor_id, threshold),
            se_dsl.with_timeout(
                action=action,
                seconds=timeout_sec,
                on_timeout=fallback,
            ),
            fallback,
        ),
        se_dsl.log(f"interlock complete on {sensor_id}"),
    )
```

### 8.2 Composition

When template A has a slot of type B, emit walks bottom-up: B's emit
runs first, produces its dict sub-tree, A's emit receives that
sub-tree as the value of the corresponding slot and splices it into
A's output. Never string concatenation, always dict composition.

---

## 9. What we reuse from s_engine, unmodified

- **All 74 `se_dsl` functions** — composed inside `emit` bodies.
- **`se_runtime.serialize_tree` / `deserialize_tree`** — JSON wire
  format for our emitted trees, unchanged.
- **`new_module` / `register_tree` / `push_event` / `run_until_idle`** —
  the runner pattern described in `s_engine/README.md`.
- **`BUILTIN_REGISTRY`** — precedent for our `commands` dict as a
  registered, overridable, trust-bounded callable table.

---

## 10. Non-goals (v1)

- **No hashing.** This is a Python system end-to-end. FNV-1a and
  content-addressable storage belong on the embedded/C side (`ctb`,
  LuaJIT port) and are not part of this preprocessor.
- **No versioning.** Templates are mutable during authoring, frozen for
  the run. Revising = re-register. Version discipline, if needed, is
  an application-level concern.
- **No runtime escalation protocol.** This is a preprocessor. Runtime
  behavior is whatever `s_engine` provides.
- **No NATS / CBOR / CTB.** Those live in s_engine or below it.
- **No profile shorthand.** Use separate `registry.add(...)` calls.
- **No granular list/dict pidgin writes.** Full-replace only.
- **No cross-tier authentication or distributed registry.** Single
  process, single source of truth.

---

## 11. File layout (proposed)

```
template_language/
    __init__.py
    registry.py      # Registry class, slot(), add(), freeze, cycle detection
    expand.py        # deep_expand
    pidgin.py        # ast-based parser, pidgin_exec
    validate.py      # default_validate + error types
    emit.py          # bottom-up walker, default_emit wrapper
    commands.py      # reference command set, default_get/set/describe
    errors.py        # ValidationError, PidginSyntaxError
    tests/
        test_registry.py
        test_expand.py
        test_pidgin.py
        test_validate.py
        test_emit.py
        test_end_to_end.py   # pidgin script → engine run
```

---

## 12. Acceptance tests

The implementation is complete when:

1. A `registry.add(...)` call registers both `registry[name]` and
   `commands[name]` with the five reference commands auto-populated.
2. `freeze()` detects and rejects cycles; passes acyclic graphs.
3. `deep_expand(registry, root)` returns a tree where every dotted
   path to a concrete slot resolves.
4. A pidgin script that sets every required slot leaves the instance
   fully bound; `validate` returns `[]`.
5. A pidgin script missing a required slot → `validate` returns a
   `ValidationError` with `code="required"` and the correct `path`.
6. Bad `type`, out-of-`choices`, bad `element_type` each return the
   matching error code with correct path.
7. `emit(instance)` produces a dict-tree that `se_runtime.new_module`
   / `register_tree` / `push_event` / `run_until_idle` can execute
   unchanged.
8. Two profile templates (e.g. `retry_aggressive`, `retry_careful`)
   sharing the same `emit` produce distinct dict-trees reflecting
   their different baked defaults.
9. A template whose `emit` returns a sub-tree of ≥50 `se_dsl` nodes
   composes correctly when called as a sub-slot of another template.
10. Pidgin parse error on the first bad line; subsequent lines
    unparsed.
11. JSON round-trip: `emit → serialize_tree → deserialize_tree`
    produces a dict equal to the original emitted tree.

---

## 13. Next steps

1. Build `registry.py` + `slot()` + `add()` + `freeze()` (~200 LOC).
2. Build `expand.py` (~100 LOC).
3. Build `pidgin.py` (ast walker, ~300 LOC).
4. Build `validate.py` + `emit.py` + `commands.py` (~200 LOC combined).
5. Write 3–5 real templates by hand, composed in a pidgin script,
   executed on `s_engine`. This is the v1 acceptance demo and the
   thing that tells us whether the slot types / profile pattern feels
   right.
6. If hand-writing templates for `se_dsl` primitives feels burdensome
   (and only then), build a codegen helper that reads
   `inspect.signature(se_dsl.<fn>)` and emits a starter
   `registry.add(...)` block for a human to review.

---

## 14. Locked decisions (reference)

Summary of design decisions pinned during the session that produced
this document:

- Two top-level dicts: `registry`, `commands`.
- Slot shape: `{type, value?, choices?, element_type?}`. Required =
  `value` absent.
- Type alphabet = primitives ∪ registered template names ∪ abstract
  placeholders (`template`, `list`, `dict`).
- `element_type` strict when present.
- Dotted-path addressing uniform across primitives, sub-templates,
  list indices, dict keys.
- DSL helper = explicit `Registry.add(...)`; no module-level mutable
  state.
- `emit` binding = kwargs by default; full-instance via escape hatch.
- Eager deep expansion at startup; acyclic template graph required.
- Pidgin = restricted Python subset via `ast.parse`.
- List/dict writes in pidgin = full-replace only in v1.
- Pidgin errors: parse fail-fast; bind errors collect-all.
- Commands not callable from pidgin.
- Five reference commands auto-populated; user-overridable.
- Default validate checks: required, type, choices, element_type,
  refs. Structured error list.
- Per-template validate runs after defaults, additive only.
- No hashing, no versioning, no CTB, no NATS in v1.
- Profile templates are the primary reuse pattern; no shorthand.
