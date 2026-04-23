# Mission: Structured Agent Specification System

A two-tier architecture for building **virtual employee** subsystems that
execute repetitive tasks 7/24 on low-end hardware (Cortex-M class and up),
configured at design time by heavy AI (or operators, or both), and bound
together by a closed-world template registry that compiles to ChainTree
behavior trees.

---

## 1. Problem Statement

The current state of the art for "agentic" systems uses **prose specifications
in markdown** that an LLM interprets at runtime to drive subsystem behavior.
This approach has three structural failure modes that are unacceptable for
unattended industrial deployment:

1. **Non-determinism.** Two LLM runs against the same markdown produce
   different runtime artifacts. Behavior cannot be reproduced, diffed, or
   signed.
2. **Unbounded vocabulary.** The LLM can generate any string, including
   primitives that don't exist, have wrong arity, or violate domain
   invariants. Errors surface late and far from their cause.
3. **Implicit composition.** Words like "then," "if," and "while" in prose
   must be re-parsed into structure. LLMs frequently get nesting wrong, and
   there is no validator that can catch the error before deployment.

For systems running on a 32 KB MCU controlling irrigation, mesh sensor nodes,
or robotic actuation, a hallucinated behavior tree is a field failure.
Markdown-driven agents are appropriate for chat applications. They are not
appropriate for control systems.

---

## 2. The Inversion

Replace prose-as-source-of-truth with **structured goal-trees as
source-of-truth**. Markdown becomes a *generated view* of the goal-tree, not
the specification itself.

```
BEFORE:   markdown spec   →  LLM (runtime)  →  ad-hoc behavior tree
AFTER:    goal-tree spec  →  HTN expander   →  validated ChainTree image
                          ↘  description    →  generated markdown
                             walker            (for human reading)
```

The two artifacts (executable image and human-readable description) are now
guaranteed consistent because they are derived from the same canonical
source. The markdown cannot drift from the runtime; the runtime cannot
diverge from the markdown.

---

## 3. Two-Tier Architecture

The system splits cleanly into two tiers with very different operating
characteristics.

### Design tier — heavy AI, episodic, expensive, supervised

- Runs off-target, on developer/operator hardware (or in the cloud).
- Invoked rarely: when commissioning a subsystem, when revising a mission,
  when adding a new template to the registry.
- Allowed to be slow, expensive, and intermittent. May invoke an LLM, a
  classical planner, an operator at a console, or a Python script. All
  produce the same artifact: a validated goal-tree.
- Has access to the full template registry source, the LLM, the markdown
  description renderer, and the human reviewer.

### Runtime tier — low-end, continuous, deterministic, unattended

- Runs on-target, from Cortex-M (32 KB flash) up through Linux servers.
- Operates continuously for months without intervention.
- Executes the compiled ChainTree binary (`.ctb` image) produced by the
  design tier. No LLM. No template source. No ambiguity.
- Performs local recovery for transient faults. Escalates to the design
  tier asynchronously only when circumstances exceed template coverage.

The boundary between the tiers is the **expanded, validated, hash-stable
goal-tree** (or its `.ctb` binary form). This is the *only* artifact that
crosses.

---

## 4. The Boundary Contract

### What crosses the tier boundary

- The expanded `.ctb` image, or fragments thereof for partial updates.
- The originating goal-tree (small, optional, retained for audit).
- Schema-constrained operational data: sensor readings, state changes,
  completion events, escalations. All as CBOR or Avro packets matching
  registered wire schemas.

### What does not cross

- The LLM. Ever. Runtime nodes have no API to call it, no dependency on
  it, no awareness it exists.
- Template source. Runtime has compiled output (CTB nodes with FNV-1a
  hashes), not the templates themselves with their `validate` / `emit`
  Python.
- Natural-language descriptions. Markdown stays on the design side.
- Free-form data. Anything reaching runtime must conform to a registered
  schema.

This boundary is the architectural property that makes the system viable.
The runtime never handles ambiguity because all ambiguity was resolved at
design time.

---

## 5. Design Tier Responsibilities

### 5.1 Template selection under ambiguity

Given a high-level mission and a registry of N templates, find the
combination that satisfies the mission. This is search over a structured,
finite space — well-suited to LLMs *and* to classical planners (HTN search,
GraphPlan, bidirectional Dijkstra over the template call graph).

### 5.2 Goal-tree construction

Emit a `Goal(template_name, **bindings)` tree. Bindings can be literal
values, references to other templates, or nested `Goal` objects. The tree is
hierarchical and matches the eventual runtime decomposition.

### 5.3 Validation against the registry

Submit the goal-tree to the HTN expander. The expander either returns the
expanded SExpr / CTB, or returns structured errors (`Param 'threshold' out
of range`, `Unknown sensor_id 'foo' — did you mean 'foo_left'?`). Errors
feed back to the author for revision.

### 5.4 Description rendering and intent verification

Walk the expanded goal-tree using each template's `description` field.
Produce a markdown rendering of *exactly what will run*. The author (LLM
or human) confirms this matches the original intent before the artifact is
deployed.

### 5.5 Template registry curation

When the existing registry cannot express a mission, the design tier
proposes a new template (params, choices, validate, emit, description) for
human review. Accepted templates are hashed and added to the registry
immutably. This is the *only* path by which the system gains new
capabilities. There is no escape hatch to "raw code at runtime."

---

## 6. Runtime Tier Responsibilities

### 6.1 Deterministic execution of the CTB image

Bounded resource use. Arena-allocated, no malloc. FNV-1a dispatch.
Predictable for thousands of nodes operating unattended.

### 6.2 Local recovery

ChainTree's robot-local recovery patterns handle transient faults without
escalation. Most failures never reach the design tier because the runtime
resolves them with registered fallback templates.

### 6.3 Structured telemetry

Every state transition flows into NATS JetStream and the ltree knowledge
base. When something does need to escalate, the design tier has full
context to reason from — not just "node X failed" but the entire local
state at the moment of failure.

### 6.4 Escalation when out of competence

When the runtime hits a situation no registered template covers, it emits a
structured `EscalationEvent` and either runs a registered fallback or
quiesces safely. It does not improvise. It does not call the LLM. It waits
asynchronously for the design tier to triage and (if needed) deploy a new
or revised CTB image.

---

## 7. Escalation Channel

The escalation event is the only mechanism by which the runtime requests
help. Its shape:

```
EscalationEvent {
    node_hash:        FNV-1a hash of the template that failed
    template_version: integer version of that template
    failure_mode:     "validate_failed" | "complete_failed" | "exhausted_methods"
    failure_reason:   short structured string
    context_snapshot: small CBOR blob of relevant local KB state
    severity:         "advisory" | "operational" | "critical"
    timestamp:        UTC nanoseconds since epoch
    node_origin:      ltree path identifying the originating node
}
```

These events flow into NATS, get aggregated, and are triaged by the design
tier on its own schedule — minutes, hours, or days later. The runtime does
not block on response. It runs the fallback, holds state, or quiesces, per
the registered failure handling for the template that emitted the event.

The escalation rate is the **primary system health metric** (see §10).

---

## 8. Evolution: LLM → Operator → Pidgin

The LLM is the *initial* design-tier driver, not the permanent one. As the
template registry matures, alternative authoring modalities become viable:

1. **LLM mode** — natural-language mission description, LLM emits goal-tree.
   Useful when the mission is novel or the operator is not yet fluent in
   the registry.
2. **Operator mode (functional Python)** — operator writes a small Python
   function decorated with `@agent`, composing template calls directly.
   Same goal-tree result, no LLM in the loop, fully deterministic.
3. **Operator mode (S-expression literal)** — operator writes a goal-tree
   as Lisp-style data. Reuses existing s_engine reader. Suitable for
   field reconfiguration of MG24 nodes over Thread/CBOR.
4. **Tabular/form-driven mode** — operator picks a template from a
   registry-constrained dropdown, fills in params (constrained to
   `choices`), and the system constructs the goal-tree. Zero syntax to
   learn. Fits the existing Qt 6 ChainTree viewer skeleton.

All four modalities produce the same canonical goal-tree, so they can
coexist in the same deployment and be swapped per-subsystem based on
cost / latency / criticality requirements.

The end state is **the LLM is one input modality among several**, not the
system. A Cortex-M node never needs an LLM in its loop. An operator at a
control console rarely does. A developer iterating on a new mission might.
Each chooses appropriately. None of them block the runtime.

---

## 9. Template Registry as the Long-Term Asset

A competitor with a better LLM cannot replicate the system unless they also
have the registry of validated, hash-stable, embedded-deployable templates.
Conversely, the system gets better as the registry grows, and registry
growth amortizes across every deployment.

This is the part that compounds. The OpenCyc parallel is exact: Cyc's
knowledge base was their actual asset; the inference engine was commodity.
Here, the template registry is the asset; the LLM (and any future planner)
is commodity.

The registry is also the system's **moat against model deprecation.** When
the LLM provider changes APIs, prices, or behavior, none of the deployed
runtime changes. The registry stays. New goal-trees may need to be
generated by a different design-tier driver, but the runtime artifacts
already in the field are immune.

---

## 10. Success Metric: Escalation Rate

Not LLM accuracy. Not template count. Not lines of generated code.

The metric is **escalations per node per unit time.** Low rate
(< 1 per node per month for a steady-state subsystem) means the registry
has matured for that domain. High rate means design-tier work is needed
to broaden coverage.

This metric tells you when a virtual employee is "trained" versus "still in
onboarding," and it is the thing reported to whoever is paying for the
deployment.

Secondary metrics:

- **Template reuse factor** — average number of deployments per template.
  Higher is better; indicates good granularity.
- **Goal-tree size distribution** — typical depth and breadth of expanded
  goal-trees per mission. Stability over time indicates registry maturity.
- **Time to new capability** — wall-clock from "registry can't do X" to
  "registry can do X." Measures how cleanly new templates can be added.

---

## 11. Why Not OpenCyc, Why Not Markdown Agents

OpenCyc bet on **runtime intelligence** — encode enough common-sense
knowledge that a runtime can reason about novel situations. It did not work
because runtime reasoning over a giant KB is too slow and too brittle for
deployment.

Markdown agents bet on **runtime interpretation** — let the LLM interpret
prose at runtime. This works for chat but fails for control systems for the
reasons in §1.

This system bets on **compile-time intelligence** — encode enough
structured templates that the design tier can compose any plausible
mission, and the runtime executes the result deterministically. This is the
same architectural bet as LLVM (smart compiler, dumb CPU), C++ template
specialization (compile-time choice, runtime dispatch), and every
successful embedded system since the 1970s.

The design tier can spend 30 seconds picking the right template (cheap
once, at commissioning). The runtime takes 30 microseconds to dispatch a
CTB node (cheap continuously, forever). The system optimizes the right
axis.

---

## 12. Integration with the ChainTree Ecosystem

This system is not a replacement for ChainTree. It is a **front-end** that
produces ChainTree-compatible artifacts.

- **Output:** s_engine S-expressions OR direct `.ctb` binary fragments.
  Both target the existing ChainTree runtime unchanged.
- **Composition:** Each template's `emit` returns SExpr / CTB structures
  that nest cleanly into parent template outputs. Bottom-up reduction
  yields a single program.
- **Hashing:** Every template carries an FNV-1a hash matching ChainTree
  conventions. Specialized templates (with bindings) get their own hash
  derived from `(template_hash, sorted_bindings_hash)`.
- **Storage:** Templates and registry live in PostgreSQL ltree alongside
  the existing knowledge base. Goal-trees are stored as CBOR blobs keyed
  by their content hash. Descriptions are generated on demand.
- **Messaging:** Goal-tree submission, expansion, validation, and CTB
  delivery all flow over NATS JetStream. Escalations flow back the same
  way. No new transport.
- **Field deployment:** A Cortex-M MG24 node receives a CTB image fragment
  over Thread, verifies integrity (CRC32 + FNV-1a chain), and atomically
  swaps it in using ArenaEnv's transactional mutex pattern. Same primitive
  already in production.

The system *is* ChainTree, with a structured spec layer on top of it. No
parallel runtime. No new language on the device. Just a more disciplined
way to generate the same artifacts that would otherwise be hand-written or
LLM-hallucinated.

---

## 13. Acceptance Criteria

The system is considered functional when:

1. A mission can be expressed as a goal-tree, expanded to SExpr, compiled
   by the existing LuaJIT s_engine pipeline, and run on a target node
   with no manual intervention between mission and runtime.
2. The same goal-tree, expanded twice, produces bit-identical output
   (canonical hash equality).
3. A failed validation produces an error precise enough that an LLM can
   revise the goal-tree and succeed on the next attempt without human
   intervention.
4. A registered template's markdown description, walked over an expanded
   goal-tree, produces prose that a domain expert agrees describes what
   the runtime will do.
5. An escalation event from a runtime node carries enough context that the
   design tier can determine the appropriate response (acknowledge,
   reparametrize, add fallback template, or human escalate) without
   querying the runtime further.
6. A new template can be added to the registry without breaking any
   existing deployed CTB images (versioning works).
7. The system runs end-to-end on a Snapdragon ARM64 / WSL2 Ubuntu
   development host, producing artifacts that load and execute on a
   Cortex-M4 SAM E51 target node.

---

## 14. Non-Goals

- **General-purpose programming.** This system generates control programs
  composed from registered templates. It is not a Turing-complete language
  the operator uses for arbitrary logic.
- **Runtime LLM inference.** The runtime never invokes a model. If a
  decision needs LLM-level intelligence, it must escalate, not improvise.
- **Replacing human review for new templates.** Every new template added
  to the registry passes through human review. The LLM may *propose*
  templates; only humans (or a deterministic policy on top of human-set
  rules) *accept* them.
- **Backward-incompatible runtime changes.** A new version of this system
  must continue to produce CTB images that the existing ChainTree runtime
  can execute. Templates may be revised, but the runtime contract is
  stable.

---

## 15. Glossary

- **Goal-tree** — the canonical specification artifact. A nested
  `Goal(template_name, **bindings)` structure produced by the design tier
  and consumed by the HTN expander.
- **Template** — a registered, hash-addressable, parameterized
  specification fragment. Has params (with optional defaults and choices),
  validate / complete / emit hooks, and a description.
- **Registry** — the closed-world set of templates available to the
  design tier. Source-of-truth for what the system can express.
- **HTN expander** — the algorithm that takes a goal-tree, recursively
  decomposes it via templates, validates at each step, and emits SExpr
  and/or CTB output.
- **CTB** — ChainTree Binary, the on-target executable image format.
  FNV-1a hash dispatch, arena-aligned, CRC32-protected.
- **Escalation** — structured event from runtime to design tier,
  asynchronous, indicating the runtime hit a situation outside template
  coverage.
- **Pidgin** — the small surface syntax that emerges when operators write
  goal-trees directly without an LLM intermediary.

