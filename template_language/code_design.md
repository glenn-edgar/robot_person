# Code Design: HTN Template System for ChainTree Agent Generation

Implementation specification for a Hierarchical Task Network (HTN) authoring
system whose surface vocabulary is railroad/syntax-diagram constructors,
and whose output is ChainTree-compatible s_engine S-expressions and/or
direct `.ctb` binary fragments.

This document is implementation-prescriptive. A Claude Code agent reading
this should be able to build the system without consulting the conversation
history that produced it.

**Reference implementation language: Python** (per ChainTree convention —
Python is the canonical reference, LuaJIT is the production tooling port).

---

## 1. Pipeline Overview

```
  ┌────────────────┐
  │  Author        │  LLM, operator (Python @agent), s-expr literal,
  │  (any tier)    │  or tabular UI — all produce the same artifact
  └───────┬────────┘
          │  Goal(template_name, **bindings)        ← canonical spec
          ▼
  ┌────────────────┐
  │  HTN Expander  │  resolves NonTerminal refs, validates Params,
  │                │  selects methods, runs validate/complete hooks,
  │                │  drives emit hooks bottom-up
  └───────┬────────┘
          │  EmitTarget(sexpr, ctb)                 ← dual output
          ▼
  ┌────────────────┐         ┌────────────────┐
  │ s_engine       │  OR     │  Direct CTB    │
  │ (LuaJIT pipe)  │         │  serializer    │
  └───────┬────────┘         └───────┬────────┘
          │                          │
          └──────────┬───────────────┘
                     ▼
              ┌────────────────┐
              │  .ctb image    │  → deploy to runtime node
              └────────────────┘
```

The expander is the heart of the system. It is a recursive tree walker with
context, validation, and emission. Everything else is supporting machinery.

---

## 2. Formalism: HTN as Visual Syntax Diagrams

The DSL surface vocabulary is the visual vocabulary of railroad diagrams.
This is deliberate — the names are mnemonic for what the diagram *looks
like* on paper, not for what it *means* in compiler terminology.

| Visual element                   | Constructor              | HTN meaning                        |
|----------------------------------|--------------------------|------------------------------------|
| ─── horizontal track             | `Track(a, b, c)`         | Method with ordered subtasks       |
| ◯ rounded box (literal)          | `Terminal("x")` / `"x"`  | Primitive task                     |
| ▭ rectangle (rule reference)     | `NonTerminal("name")`    | Compound task call                 |
| ╪ vertical branch                | `Choice(default, ...)`   | Compound with multiple methods     |
| ⌒ bypass arc                     | `Optional(x)`            | Compound with [x] and [] methods   |
| ↻ loop, must traverse ≥ 1        | `OneOrMore(x, sep)`      | Recursive method, no empty rail    |
| ↻⌒ loop with bypass              | `ZeroOrMore(x, sep)`     | Recursive method with empty rail   |
| ┌─label─┐ framed sub-diagram     | `Group(x, "label")`      | Named, hash-addressable subtree    |
| ┊ wrap to next line              | `Stack(row1, row2)`      | Cosmetic; collapses to Track       |
| ●→ ... →● outer container        | `Diagram(...)`           | Top-level Compound for a template  |
| ◇ guard diamond on track         | `When(pred, ...)`        | Method with precondition           |

Loops carry an optional "return arc" decoration as a positional argument:
`OneOrMore(expr, ",")` reads as "traverse `expr`, on the loop-back pass over
`,`" — exactly matching the diagram.

---

## 3. Core Node Types

```python
from dataclasses import dataclass, field
from typing import Callable, Optional, Union, Any

# --- Sentinels for failure semantics ---

@dataclass
class Reject:
    """Soft fail with diagnostic. Backtrack, try next method."""
    reason: str

class Abort(Exception):
    """Hard fail. Unwind the entire expansion."""
    pass


# --- Core node types ---

@dataclass
class Terminal:
    """Primitive task — emits a token, no decomposition."""
    token: str

@dataclass
class NonTerminal:
    """Reference to another template by name. Resolved at registry link."""
    name: str
    bindings: dict[str, Any] = field(default_factory=dict)
    # Resolved at link time:
    target: Optional["Compound"] = None

@dataclass
class Method:
    """One decomposition of a Compound."""
    subtasks: list["Node"]
    guard: Optional[Callable[["Context", "NodeView"], bool]] = None

@dataclass
class Compound:
    """Non-terminal — has one or more methods, picks one to decompose."""
    name: str
    methods: list[Method] = field(default_factory=list)
    params: list["Param"] = field(default_factory=list)
    validate: Optional[Callable] = None
    complete: Optional[Callable] = None
    emit: Optional[Callable] = None
    description: Optional[str] = None
    version: int = 1
    # Computed at registry insertion:
    hash: Optional[int] = None  # FNV-1a of canonical form

@dataclass
class Param:
    """Formal parameter on a Compound."""
    name: str
    default: Any = None
    choices: Optional[list[Any]] = None
    choices_from: Optional[Callable] = None  # dynamic, evaluated at resolve()
    lazy: bool = False  # if True, do not eagerly specialize on this param

Node = Union[Terminal, NonTerminal, Compound]
```

---

## 4. Visual DSL Constructors (Reference)

Each constructor is a thin wrapper that produces a `Compound` with the
appropriate methods. All constructors accept an optional `name=` keyword;
if omitted, a gensym is generated for diagnostics.

### 4.1 `Diagram(*items, **kwargs) → Compound`

Top-level container for a template definition. Adds the top-level
`validate` / `complete` / `emit` / `description` hooks. A `Diagram` is
what gets registered in the template registry.

```python
g["if_stmt"] = Diagram(
    "if", "(", NonTerminal("cond"), ")", NonTerminal("stmt"),
    Optional(Track("else", NonTerminal("stmt"))),
    description="Conditional branch with optional else clause.",
    emit=lambda ctx, n, ch: SExpr("if", ch["cond"], ch["stmt"], ch.get("else_stmt"))
)
```

### 4.2 `Track(*items) → Compound`

Single-method Compound. The method's subtasks are the items in order.
Equivalent to `seq` in standard EBNF combinators.

### 4.3 `Terminal(token)` and bare strings

`Terminal("x")` produces a `Terminal` node. Bare strings inside
constructors are auto-promoted, so `Track("if", "(", ...)` is equivalent to
`Track(Terminal("if"), Terminal("("), ...)`.

### 4.4 `NonTerminal(name, **bindings) → NonTerminal`

A reference to another template. `name` is looked up in the registry at
`resolve()` time; `bindings` are passed to the called template's `Param`s.

```python
NonTerminal("list_of", T="number")
```

### 4.5 `Choice(default_idx, *rails) → Compound`

Multi-method Compound. Each rail becomes one method. `default_idx` is the
rail to prefer when multiple are eligible (used by the description renderer
to pick the "main" example, and by the planner as a tie-breaker).

```python
Choice(1,
    NonTerminal("number"),
    NonTerminal("ident"),                           # default
    Track("(", NonTerminal("expr"), ")"),
)
```

### 4.6 `Optional(item) → Compound`

Sugar for `Choice(0, item, Track())`. Two methods: take the item, or take
nothing.

### 4.7 `ZeroOrMore(item, sep=None) → Compound`

Recursive Compound with an empty rail and a `[item, sep, self]` rail
(the `sep` is omitted if None). The empty rail is the `default_idx=0`.

```python
ZeroOrMore(NonTerminal("expr"), ",")
# Two methods: []  and  [expr, ",", self]
```

### 4.8 `OneOrMore(item, sep=None) → Compound`

Sugar for `Track(item, ZeroOrMore(item, sep))`. Must traverse at least once.

### 4.9 `Group(item, label) → Compound`

Single-method Compound with an explicit name. Used to introduce a named
boundary in the middle of a Diagram for hashing, scoping, or addressability
purposes. Compiles to a separately-hashed CTB subtree.

### 4.10 `Stack(*rows) → Compound`

Single-method Compound that concatenates rows in order. Purely cosmetic —
collapses to `Track(*flat_items)` at compile time. Exists so the visual
renderer can wrap wide diagrams across multiple lines.

### 4.11 `When(predicate, *items) → Method-with-guard`

Wraps the items in a `Track` and attaches `predicate` as the method guard.
Use inside `Choice` to gate rails on context.

```python
Choice(0,
    When(lambda ctx: ctx.target == "cortex_m4",  Track(NonTerminal("simd_path"))),
    When(lambda ctx: ctx.streaming,              Track(NonTerminal("welford_node"))),
    NonTerminal("scalar_fallback"),              # unguarded default
)
```

### 4.12 `Param(name, default=None, choices=None, choices_from=None, lazy=False)`

Declares a formal parameter on the surrounding Diagram. Position of the
`Param` in the Diagram's items determines whether it appears before any
structural tokens (typical) or interleaved (rare, for self-documenting
position). Substitution is via `$name` in subsequent items.

```python
Diagram(
    Param("T", choices=["i32", "u32", "f32"], default="i32"),
    Param("N", default=8),
    "buffer", "[", "$T", ";", "$N", "]"
)
```

`choices_from=` accepts a callable receiving the registry; it is evaluated
at `resolve()` time. Useful for "any registered template matching pattern X"
cases:

```python
Param("body", choices_from=lambda reg: reg.matching("stmt_*"))
```

---

## 5. Template References and Recursion

### 5.1 The placeholder mechanism

`NonTerminal("name")` is a *placeholder*. At template-definition time, no
lookup happens; the registry may not even have `"name"` yet. The placeholder
holds the name and any bindings.

### 5.2 The `resolve()` pass

After all templates are added to the registry, `registry.resolve()` walks
every Compound and replaces each `NonTerminal` placeholder's `target`
field with the actual `Compound` object found by name lookup. Forward
references and self-references just work.

```python
g = Registry()
g["expr"] = Diagram(
    Choice(0,
        NonTerminal("number"),                    # forward ref
        NonTerminal("ident"),                     # forward ref
        Track("(", NonTerminal("expr"), ")"),     # self-reference
    )
)
g["number"] = Diagram(Terminal("NUMBER"))
g["ident"]  = Diagram(Terminal("IDENT"))
g.resolve()   # all NonTerminal.target fields populated
```

### 5.3 Direct and mutual recursion

Both fall out of the placeholder mechanism with no special handling:

```python
g["expr"]    = Diagram(..., NonTerminal("call"), ...)
g["call"]    = Diagram(NonTerminal("ident"), "(", NonTerminal("arglist"), ")")
g["arglist"] = Diagram(ZeroOrMore(NonTerminal("expr"), ","))
# expr → call → arglist → expr  works.
```

### 5.4 Call-graph queries

`Registry` exposes:

```python
reg.callers_of("expr")      # set of template names that reference "expr"
reg.callees_of("expr")      # set of template names that "expr" references
reg.unreachable_from("start")
reg.left_recursive()        # names that can call themselves without
                            # consuming a Terminal first  (planning hazard)
reg.matching(pattern)       # glob-style name matching
```

---

## 6. Parameterized Templates

### 6.1 Specialization

When a `NonTerminal("foo", T="number")` is encountered, the expander
produces a *specialized copy* of `foo` with `$T` substituted. Specialization
key is `(foo.hash, sorted(bindings.items()))`. Specializations are cached
in the registry; the same `(template, bindings)` always produces the same
specialized Compound, with the same FNV-1a hash.

### 6.2 Eager vs lazy

By default, specialization is **eager** — it happens at expand time and
results in a flat compiled image with one Compound per unique
`(template, bindings)` tuple. Optimal for Cortex-M targets (no runtime
indirection cost).

When a Param is marked `lazy=True`, the specialization is deferred: the
Compound stays parametric and the binding is resolved at runtime via
indirection. Use sparingly — only when the parameter genuinely varies per
invocation rather than per deployment site.

### 6.3 Combinatorial blow-up

If a parameter is passed *through* multiple template levels, eager
specialization can explode: N templates each with K choices and call depth
D yield up to K^D specializations.

Mitigation:

- Cap effective depth via a registry-level config (`max_specialization_depth`).
- Mark deeply-passed parameters `lazy=True`.
- Use `Group` to introduce a named boundary that caches specializations
  at that level.

The expander emits a warning when specialization count exceeds a
configurable threshold. Treat this as a registry design smell.

---

## 7. Validation Hooks

Two hooks per Compound, both optional. They fire at well-defined points in
the expander's traversal.

### 7.1 `validate(ctx, node) → bool | Reject | Abort`

Fires on **entry** to the node, before any children are processed. Acts as
a precondition — decides whether this node can be selected given current
context.

Return semantics:
- Truthy / `True` → proceed
- Falsy / `False` → soft fail, expander backtracks to try next method
- `Reject(reason)` → soft fail with diagnostic, attached to error trail
- `raise Abort(reason)` → hard fail, unwind entire expansion

`node` is a `NodeView` providing access to the Compound's name, params,
bindings, and parent — but *not* yet to children (they haven't been
processed).

### 7.2 `complete(ctx, node) → bool | Reject | Abort`

Fires on **exit** from the node, after all children have been processed
*successfully*. Acts as a postcondition and the natural place for
context-mutating side effects.

`node` here has full access to children's emitted outputs.

```python
g["block"] = Diagram(
    "{", ZeroOrMore(NonTerminal("stmt")), "}",
    validate=lambda ctx, n: ctx.symbols.push_scope(),     # entering: new scope
    complete=lambda ctx, n: ctx.symbols.pop_scope(),      # exiting: drop it
)
```

### 7.3 Composition order

```
enter Compound:
    1. resolve params, check Param.choices                     (built-in)
    2. run validate(ctx, node)                                  ← user hook
       on Reject/False: backtrack
    3. for each child in current method:
           recursively process child
           on child failure:
               undo any context mutations from this node so far
               try next method (if Choice) or propagate
    4. run complete(ctx, node)                                  ← user hook
       on Reject/False: undo, backtrack
    5. run emit(ctx, node, children)                            ← user hook
exit
```

### 7.4 Transactional context

`Context` must support **scoped, undoable mutations** because backtracking
needs to discard context changes from failed attempts.

Reference implementation: a layered/COW dict where each Compound entry
pushes a fresh layer, `complete` commits the layer, failure discards it.

For Cortex-M production code (LuaJIT or Zig), this maps directly to the
**ArenaEnv transactional mutex pattern** — push arena scope on entry,
promote on `complete`, reset high-water mark on failure. Zero per-node
heap traffic.

---

## 8. Emit Hook

### 8.1 `emit(ctx, node, children) → EmitTarget`

Fires after `complete` succeeds. Returns the emitted artifact.

`children` is a dict mapping child reference (by name when the child is a
NonTerminal, by position-index otherwise) to the child's already-emitted
`EmitTarget`. By the time `emit` runs, all children have completed and
emitted.

### 8.2 `EmitTarget` — dual-target output

```python
@dataclass
class EmitTarget:
    sexpr: "SExpr"                 # for s_engine path
    ctb:   Optional["CTBNode"]     # for direct binary path; None means
                                   # "let s_engine compile sexpr to ctb"

@dataclass
class SExpr:
    head: str
    args: list[Union["SExpr", str, int, float, bool]]

@dataclass
class CTBNode:
    type_hash: int               # FNV-1a of the ChainTree node type
    params:    bytes             # packed parameter blob
    children:  list["CTBNode"]
```

Templates that have a direct CTB analogue (sensor primitives, leaf actions)
should populate both fields. Composite templates can populate just `sexpr`
and let the s_engine compiler produce the CTB.

### 8.3 Composition

Each template's emit produces a fragment. Parents stitch children's
fragments together via SExpr / CTB constructors. The system never uses
string concatenation for code generation.

```python
g["loop"] = Diagram(
    Param("counter_type", choices=["i32", "u32"], default="i32"),
    Param("body"),
    "for", "(", "$counter_type", NonTerminal("ident"), "in",
              NonTerminal("range"), ")", "$body",

    emit=lambda ctx, n, ch: EmitTarget(
        sexpr = SExpr("pipeline", [
            SExpr("set", [ch["ident"].sexpr, SExpr("range_start", [ch["range"].sexpr])]),
            SExpr("while", [
                SExpr("lt", [ch["ident"].sexpr, SExpr("range_end", [ch["range"].sexpr])]),
                SExpr("pipeline", [
                    ch["body"].sexpr,
                    SExpr("incr", [ch["ident"].sexpr]),
                ])
            ])
        ]),
        ctb = None,  # let s_engine compile this
    )
)
```

### 8.4 Forward-reference handling

Most templates only need their own children's already-emitted output, which
is available by the time emit runs. For the rare case where an emit needs
to reference a name declared later in the same expansion (e.g. mutually
recursive function definitions), use **two-pass emit**:

1. Pass 1: build the expanded tree, populate `ctx.symbols` from `complete`
   hooks.
2. Pass 2: run all `emit` hooks with full symbol table available.

Pass 2 is opt-in via `Registry.expand(goal, two_pass=True)`. Default is
single-pass for performance; the typical use case (control programs over
sensor primitives) does not need two-pass.

---

## 9. Goal Trees

### 9.1 Structure

```python
@dataclass
class Goal:
    template: str
    bindings: dict[str, Any] = field(default_factory=dict)

# Example:
Goal("monitor_sensor",
     sensor_id="vl53l8cx_front",
     threshold=250,
     sample_rate="10hz",
     on_trigger=Goal("publish_alert",
                     topic="alerts.proximity",
                     severity="warn"))
```

Bindings can be:
- Literal scalars (str, int, float, bool)
- Lists of literals
- Nested `Goal` objects (these get expanded recursively)
- Already-built SExpr / CTB fragments (passed through verbatim)

### 9.2 Wire format

**JSON** for cloud / authoring tools / human inspection:

```json
{
  "template": "monitor_sensor",
  "bindings": {
    "sensor_id": "vl53l8cx_front",
    "threshold": 250,
    "on_trigger": {
      "template": "publish_alert",
      "bindings": {"topic": "alerts.proximity", "severity": "warn"}
    }
  }
}
```

**CBOR** for embedded / over-the-wire (Thread, NATS):

Same structure, CBOR-encoded with the existing Avro-inspired schema layer.
Templates and string bindings can be FNV-1a hash-substituted on-wire to save
bytes; the receiver expands hashes via the local registry.

### 9.3 Validation at construction time

`Goal` objects are inert structurally. Validation happens at `expand`
time. However, an optional `Goal.validate(registry)` method does a
lightweight check (template exists, all required params bound, all bound
params are in `choices`) without doing full expansion. Useful for
authoring-tool feedback loops.

### 9.4 Hash stability

A canonical Goal-tree always produces the same expanded output. The
canonical hash is computed as:

```
goal_hash = FNV-1a(
    template_hash ||
    sorted_canonical_binding_bytes
)
```

where binding values are themselves recursively hashed if they are nested
Goals. This gives content-addressable goal-trees suitable for caching,
deduplication, and signing.

---

## 10. Template Registry

### 10.1 Structure

```python
@dataclass
class TemplateEntry:
    name:        str
    version:     int
    template:    Compound
    hash:        int        # FNV-1a of canonical form
    description: str        # human-facing summary
    schema:      dict       # JSON-schema of accepted bindings
    examples:    list[Goal] # canonical example invocations
    added_at:    int        # epoch ns
    added_by:    str        # author identifier

class Registry:
    def __init__(self): ...

    def __setitem__(self, name: str, diagram: Compound): ...
    def __getitem__(self, name: str) -> Compound: ...

    def add(self, name: str, diagram: Compound,
            description: str, examples: list[Goal] = ()): ...

    def resolve(self): ...                           # link NonTerminal refs
    def freeze(self): ...                            # disallow further changes,
                                                     # compute final hashes

    def list_templates(self, filter: str = None) -> list[str]: ...
    def describe(self, name: str) -> dict: ...       # full metadata for LLM use

    def matching(self, pattern: str) -> list[str]: ...
    def callers_of(self, name: str) -> set[str]: ...
    def callees_of(self, name: str) -> set[str]: ...
    def left_recursive(self) -> set[str]: ...
    def unreachable_from(self, root: str) -> set[str]: ...
```

### 10.2 Versioning

Templates are **immutable once frozen**. To revise a template:

- Add the new version under the same name with `version=N+1`.
- Existing CTB images reference the *hash*, not the name + version, so
  they continue to work against the old version.
- New goal-trees expand against the latest version of any name.

The registry retains all versions; callers can request a specific version
explicitly via `NonTerminal("foo", _version=2)` if pinning is needed.

### 10.3 Persistence

The registry serializes to PostgreSQL ltree alongside the existing
ChainTree knowledge base. Path structure:

```
registry.<namespace>.<template_name>.v<N>
```

with the Compound stored as a JSONB blob. Specializations are stored
under:

```
registry.<namespace>.<template_name>.v<N>.specializations.<binding_hash>
```

This integrates with the existing Postgres-backed KB without schema
changes.

---

## 11. HTN Expander Algorithm

### 11.1 Entry point

```python
def expand(goal: Goal, context: Context,
           registry: Registry,
           two_pass: bool = False) -> EmitTarget:
    ...
```

### 11.2 Recursive descent (single-pass)

```
expand(goal, ctx, reg):
    template = reg[goal.template]                    # lookup
    apply_bindings(template, goal.bindings, ctx)     # specialize
    return walk(template, ctx)

walk(compound, ctx):
    ctx.push_scope()
    if compound.validate and not compound.validate(ctx, view(compound)):
        ctx.pop_scope_discard()
        return Failure(...)

    children = {}
    for method in compound.methods:
        if method.guard and not method.guard(ctx, view(compound)):
            continue
        try:
            method_children = {}
            for sub in method.subtasks:
                result = walk(sub, ctx)
                if isinstance(result, Failure):
                    raise BacktrackException(result)
                method_children[key_for(sub)] = result
            children = method_children
            break
        except BacktrackException:
            ctx.rewind_scope()                       # undo within scope
            continue
    else:
        ctx.pop_scope_discard()
        return Failure("exhausted methods")

    if compound.complete and not compound.complete(ctx, view(compound)):
        ctx.pop_scope_discard()
        return Failure(...)

    if compound.emit:
        emitted = compound.emit(ctx, view(compound), children)
    else:
        emitted = default_emit(compound, children)

    ctx.pop_scope_commit()
    return emitted
```

### 11.3 Method selection priority

When multiple methods are eligible:

1. Filter by `When` guards — discard methods whose guards return false.
2. Filter by `Param.choices` consistency with current bindings.
3. If a `score=` callable is attached to a method, use highest score.
4. Otherwise, prefer `Choice.default_idx` if present, else first.

### 11.4 Backtracking

Failure within a method causes the expander to:

1. Rewind context to the point of method entry.
2. Try the next eligible method.
3. If no methods remain, fail upward.

`Abort` exceptions skip backtracking entirely — they unwind to the top.

### 11.5 Two-pass mode

When `two_pass=True`:
- Pass 1 walks the tree running `validate` and `complete` only; it
  populates `ctx.symbols` but does not call `emit`.
- Pass 2 walks the same tree calling `emit`, with `ctx.symbols` fully
  populated from pass 1.

Pass 2 must be deterministic given the same context — emit functions
must not mutate context.

---

## 12. Description Rendering

Walks an expanded goal-tree using each Compound's `description` field
(a format string over bindings), producing markdown.

```python
def render_description(expanded: ExpandedNode, indent: int = 0) -> str:
    parts = []
    if expanded.compound.description:
        parts.append(" " * indent +
                     expanded.compound.description.format(**expanded.bindings))
    for child in expanded.children.values():
        parts.append(render_description(child, indent + 2))
    return "\n".join(parts)
```

The result is the **generated markdown view** of the goal-tree. It is not
the spec; it is derived from the spec. Round-trip property:

```
goal → expand → render_description → markdown
                          (cannot be parsed back; one-way)
```

The system never parses markdown. Markdown is output-only.

---

## 13. Integration with ChainTree

### 13.1 s_engine path (default)

The `EmitTarget.sexpr` is fed into the existing LuaJIT s_engine reader.
Output flows through the standard six-stage pipeline:

```
SExpr → reader → AST → resolver → IR → optimizer → CTB image
```

No changes to s_engine. This is the integration path for compositional
templates whose CTB form is best derived from the s_engine compiler.

### 13.2 Direct CTB path

When `EmitTarget.ctb` is non-None, it is serialized directly to the binary
image format, skipping the s_engine pipeline. Use this for:
- Leaf primitives with a known fixed CTB form (sensor reads, actuator
  writes).
- Performance-critical paths where s_engine compilation overhead matters.
- Targets without LuaJIT (deeply embedded C or Zig nodes).

A single goal-tree expansion can produce a mix: most nodes go through
s_engine, a few performance-critical leaves emit CTB directly. The CTB
serializer stitches them together.

### 13.3 Hash conventions

All hashes are FNV-1a, 32-bit, matching ChainTree convention.

- `template.hash` = FNV-1a of canonical Compound serialization.
- Specialized template hash = FNV-1a(template.hash || sorted_bindings_bytes).
- CTB node `type_hash` matches the corresponding template's hash, so
  on-target dispatch tables are consistent with design-time identifiers.

### 13.4 Storage and transport

- Templates → PostgreSQL ltree (KB) as JSONB.
- Goal-trees → CBOR blobs, content-addressable by goal_hash, stored in
  NATS JetStream KV.
- CTB images → existing `.ctb` file format and OTA update protocol.
- Escalation events → NATS JetStream subjects (`htn.escalation.<severity>`).

No new transport, storage, or wire format. Everything reuses existing
ChainTree infrastructure.

---

## 14. Escalation Event Protocol

```python
@dataclass
class EscalationEvent:
    node_hash:        int            # FNV-1a of failing template
    template_version: int
    failure_mode:     str            # "validate" | "complete" |
                                     # "exhausted_methods" | "abort"
    failure_reason:   str            # short structured string
    context_snapshot: bytes          # CBOR blob of relevant local KB state
    severity:         str            # "advisory" | "operational" | "critical"
    timestamp_ns:     int            # UTC nanoseconds since epoch
    node_origin:      str            # ltree path identifying the source
```

### 14.1 NATS subjects

```
htn.escalation.advisory.<node_origin>
htn.escalation.operational.<node_origin>
htn.escalation.critical.<node_origin>
```

Subscribers (the design tier triage process, audit log, alert dashboard)
register at appropriate severity levels.

### 14.2 Triage protocol

Triage is asynchronous. The runtime does not block on response. The runtime
either runs a registered fallback template (whose name is stored alongside
the failing template at registration time) or quiesces.

The design tier triage process:
1. Reads the escalation.
2. Inspects `context_snapshot` and the originating goal-tree (looked up by
   the runtime-reported `node_origin` path).
3. Decides: acknowledge / reparametrize / add fallback template / human
   escalate.
4. If a CTB update is needed, emits a new goal-tree, expands it,
   deploys the resulting CTB fragment via OTA.

---

## 15. Operator / Pidgin Frontends

All frontends produce the same `Goal` tree. They differ only in surface
syntax.

### 15.1 Functional Python (`@agent` decorator)

```python
@agent(registry=g)
def proximity_watch(sensor: str = "vl53l8cx_front"):
    monitor_sensor(
        sensor_id=sensor,
        threshold=250,
        sample_rate="10hz",
        on_trigger=publish_alert(topic="alerts.proximity", severity="warn"),
    )
```

The decorator:
1. Inspects the function body via AST.
2. Each function call becomes a `Goal(...)` constructor.
3. Sequential statements compose into a `Goal("seq", goals=[...])` (where
   `seq` is a registered meta-template).
4. The decorated function returns a `Goal` tree when called.

### 15.2 S-expression literal

```lisp
(monitor-sensor
  :sensor-id  vl53l8cx-front
  :threshold  250
  :on-trigger (publish-alert :topic "alerts.proximity" :severity warn))
```

Reuses the existing s_engine reader. A symbol in head position is the
template name; keyword args become bindings. Suitable for over-the-wire
configuration of MG24 nodes (CBOR-encoded).

### 15.3 Tabular / form-driven (Qt 6 viewer)

Operator selects template from registry-constrained dropdown, fills params
constrained to `choices`. The UI builds the `Goal` tree in memory and
submits it. Zero syntax to learn.

Builds on the existing Qt 6 ChainTree Viewer. Read-only registry browsing
and goal-tree assembly are additive features.

### 15.4 LLM mode

Author submits prose mission. LLM:
1. Queries `registry.list_templates()` and `registry.describe(name)` for
   each candidate.
2. Constructs a `Goal` tree.
3. Submits to expander.
4. On validation error, revises the goal-tree using the structured error
   message.
5. On success, walks the description renderer and confirms the output
   matches the original prose intent.

The LLM is *not* a runtime component. It is one of four authoring modes,
swappable per-subsystem.

---

## 16. Implementation Guidance

### 16.1 File organization

```
htn/
    __init__.py
    nodes.py              # Terminal, NonTerminal, Method, Compound, Param
    diagram.py            # Diagram, Track, Choice, Optional,
                          # ZeroOrMore, OneOrMore, Group, Stack, When
    registry.py           # Registry, TemplateEntry, versioning, hashing
    expander.py           # walk(), expand(), backtracking
    context.py            # Context, scope management, transactional state
    emit.py               # SExpr, CTBNode, EmitTarget, default_emit
    goal.py               # Goal, JSON/CBOR serialization, validation
    description.py        # render_description
    escalation.py         # EscalationEvent
    frontends/
        py_decorator.py   # @agent
        sexpr_reader.py   # s-expression literal mode
        llm_helper.py     # LLM authoring helpers (registry inspection)
    integrations/
        chaintree.py      # CTB serialization, FNV-1a, .ctb writer
        nats_bridge.py    # publish/subscribe helpers
        postgres_store.py # registry persistence
    tests/
        test_nodes.py
        test_diagram.py
        test_expander.py
        test_emit.py
        test_recursion.py
        test_validation.py
        test_specialization.py
        test_escalation.py
        test_chaintree_integration.py
```

### 16.2 Reference implementation style

- Python 3.11+, dataclasses, type hints throughout.
- No external dependencies for core (`htn/`); stdlib only.
- Integrations may depend on existing ChainTree libraries.
- Tests use `pytest`.
- Match the canonical Python ChainTree port style.

### 16.3 LuaJIT port (production tooling)

After Python reference stabilizes, port to LuaJIT for production use,
following the same convention as the existing six-stage `.ctb` pipeline.
LuaJIT port:
- Uses the existing FFI bindings for NATS / KV / RPC.
- Reuses the s_engine reader for s-expression literal frontend.
- Shares the FNV-1a and CBOR primitives.

---

## 17. Open Design Questions

These are deliberately under-specified in this document. Make a choice
when implementing, document the choice, revise after experience.

### 17.1 Template granularity

Too-fine templates (one per primitive) → goal-trees are huge and the
authoring tier struggles to compose them.

Too-coarse templates (one per mission type) → registry doesn't compose;
every variation needs a new template.

Heuristic: **template granularity should match what a domain expert calls a
"thing" in their field** — `monitor_sensor`, `interlock_with_timeout`,
`state_machine_with_recovery`. Roughly the granularity of a Unix command,
not a syscall and not a daemon.

Refine this heuristic empirically as the registry grows.

### 17.2 Specialization caching policy

Eager specialization with no cap can blow up. Hard cap with discard breaks
hash stability. Default policy: warn at 100 specializations per template,
hard-fail at 1000, allow per-template override.

### 17.3 Two-pass emit triggering

Currently opt-in per `expand()` call. Consider auto-detection: if any
template's `emit` accesses `ctx.symbols` for a name not yet declared,
re-run in two-pass mode automatically.

### 17.4 Versioning and registry distribution

How do nodes in the field discover that a new template version exists?
Possible: registry pushes hash deltas over NATS at low frequency, nodes
reconcile lazily. Out of scope for v1.

### 17.5 Inter-tier authentication

The design tier publishes CTB images to runtime nodes. The runtime nodes
must verify these came from a legitimate design-tier author. Out of scope
for v1; assume trusted transport (NATS JetStream within a trust boundary).

---

## 18. Acceptance Tests

The implementation passes when:

1. `Diagram(...)` constructors compose to a Compound tree with no errors
   for the canonical examples in §4.
2. `Registry.resolve()` correctly links forward and self-references
   without loops or missing targets.
3. A goal-tree with nested Goals expands to a single SExpr that the
   existing LuaJIT s_engine reader accepts and compiles.
4. The same goal-tree expanded twice produces bit-identical EmitTargets
   (canonical hash equality).
5. A goal-tree with an out-of-`choices` binding fails at expansion with a
   structured error pointing to the offending Param.
6. A `validate` returning `Reject(reason)` causes the expander to backtrack
   to the next method without crashing, and the reason appears in the
   error trail if no methods succeed.
7. A `complete` hook mutating `ctx.symbols` makes the mutation visible to
   sibling nodes processed afterward, and invisible to siblings if the
   parent fails.
8. `render_description` on an expanded tree produces markdown matching the
   structure of the original goal-tree.
9. A round-trip through CBOR serialization preserves goal-tree semantics
   (re-expand produces same EmitTarget).
10. An EscalationEvent published to NATS JetStream is consumed by a test
    triage subscriber with all fields intact.
11. Direct CTB output, written to a `.ctb` file, loads and executes on the
    existing ChainTree runtime (test harness on Linux is sufficient).

---

## 19. Out of Scope (v1)

- Runtime LLM inference. The LLM is design-tier only.
- General-purpose expression language inside templates. Templates compose;
  they do not contain arbitrary code beyond their hooks.
- Security model for cross-tier authentication.
- Distributed registry consistency (assume single source of truth).
- Performance optimization beyond what falls out of arena allocation and
  FNV-1a dispatch.
- Visual diagram rendering (the `railroad-diagrams` PyPI library can be
  fed directly from the constructor tree if needed; not part of core).
