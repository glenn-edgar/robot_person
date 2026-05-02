# continue.md — ROSClaw, Templates, and the Layered Invariants Bet

**Date:** May 2026
**Context:** Conversation comparing ChainTree's nested template + virtual node architecture against current LLM-robotics approaches (ROSClaw, BTGenBot, LLM-as-BT-Planner, RoboMatrix, LRLL, BETR-XP-LLM, CoMuRoS), grounding the comparison in information-theoretic and architectural arguments, and closing on the inheritance/transfer strategy.

---

## 1. The ROSClaw Landscape (March–April 2026)

Three distinct projects share the "ROSClaw" name:

1. **Cardenas / PlaiPin ROSClaw** (`PlaiPin/rosclaw`, Apache-2.0, arXiv 2603.26997) — OpenClaw ↔ ROS 2 bridge. Formal contract C = ⟨A, O, V, L⟩: affordance manifest, observation normalizer, pre-execution validator, audit logger. Empirical contribution: uniform substrate as measurement instrument — same robot, same tools, same envelope, swap only the foundation model. Reports up to 4.8× variation in out-of-policy action proposal rates across backends, ~3.4× among frontier models.
2. **Zhao et al.** (arXiv 2604.04664) — hierarchical multi-robot variant. Adds "asynchronous decoupling of 1Hz reasoning from 100–1000Hz control." Same brain/cerebellum split, different vocabulary.
3. **rosclaw.io** — independent commercial framing.

All three preserve the classical four-layer stack (cognition / executive / BT-or-SM / hardware). None take the position that the plan output should *be* the behavior tree.

---

## 2. How LLMs Actually Interact with BTs in ROSClaw

**The LLM does not touch the BT.** Separated by an action-server boundary. Loop:

1. Affordance manifest A — LLM sees `navigate_to_pose(pose)`, `pick_object(id)`, `dock()`. Does NOT see Nav2's BT XML.
2. Validator V checks against safety envelope before dispatch.
3. Action server runs internal BT (`ComputePathToPose → FollowPath`, fallback recoveries) — invisible to LLM.
4. Feedback through observation normalizer O — canonicalized schema.
5. Result + provenance through audit log L — `SUCCESS / ABORTED / CANCELED`.

**Hard consequence:** any recovery requiring tree modification is invisible to the LLM and must be pre-baked into BT XML by the integrator. When `navigate_to_pose` returns `ABORTED`, the LLM gets a status code — not "subtree at /root/follow_path/recovery/spin returned FAILURE on tick 47."

### Five LLM+BT integration patterns

1. **Goal-setter** — LLM produces goal string; BT hand-authored, fixed. (Nav2-with-LLM-frontend.)
2. **Leaf invoker** — BT is top-level; specific leaves call LLM. (SayCan, Inner Monologue.)
3. **Synthesizer** — LLM emits BT XML/code once; executor runs it LLM-free. (Code-as-Policies. Closest in spirit to Drive Program structurally.)
4. **Patcher** — LLM observes ticks, surgically edits subtrees. (Research prototypes.)
5. **Executive above** — LLM in tool-calling abstraction; BT opaque inside action server. (ROSClaw, ROSA.)

ROSClaw is mode 5. Drive Program is a stronger version of mode 3 with the planner non-LLM.

---

## 3. Is the LLM a Planner in ROSClaw?

**Yes, in the weak sense.** Reactive tool selection, not classical planning. No PDDL, no STRIPS, no plan artifact, no preconditions/effects model.

### Planner taxonomy

1. **Classical planner** (PDDL/STRIPS/HTN) — searches state space, provable plan validity. No LLM.
2. **LLM-as-PDDL-frontend** (LLM+P) — LLM translates NL → PDDL, classical planner solves.
3. **LLM-as-plan-generator** (Code-as-Policies, ProgPrompt) — LLM emits plan once, executor runs.
4. **LLM-as-policy** (ReAct loops) — no plan; LLM queried each step.
5. **Hierarchical** (most VLA/VLN) — LLM high-level, classical/learned low-level.

ROSClaw is **mode 4 with safety filter**. The validator V moves precondition checking from plan-time (where classical planners do it) to execution-time (per action), because there is no plan to validate against in advance.

### Diagnostic question

In any LLM-robotics paper, ask: **what is the persistent artifact between LLM reasoning and robot actuators?**
- ROSClaw: conversation history + audit log. Neither is a plan.
- LLM+P: a PDDL plan.
- Code-as-Policies: emitted code.
- Drive Program: the behavior tree itself.

The presence and structure of that artifact is what determines whether the system is a planner in any non-marketing sense.

---

## 4. Three Positions on LLM ↔ BT Coupling

- **Position A (ROSClaw today):** LLM reasons over opaque tree. No introspection, no edits.
- **Position B (transparent tree):** LLM sees BT as data, can propose edits/patches. Strictly better than A.
- **Position C (Drive Program):** Plan output IS the tree. No translation seam.

**B → C wins** because B has two representations of intent (LLM's internal state + BT). Every edit is a translation, with translation failure modes. C makes effect/verify pairing structural (cannot be edited away without notice). C also frees the planner from being an LLM at all.

ROSClaw cannot make the B → C move because the OpenClaw/ROS 2 boundary is load-bearing for them — model-agnostic, platform-agnostic *requires* opaque action servers.

---

## 5. Template Approach in the Literature

**Found four flavors. None match ChainTree's nested template + same-construction-interface combination.**

1. **BT templates as LLM scaffolding** — Action Template Library (Yang et al. 2025, Sci. Direct). Closest direct match. Field deprioritized this thread once direct BT generation became feasible — fashion choice, not principled.
2. **Skill libraries with LLM composition** — RoboMatrix, LRLL, CoMuRoS (Nov 2025), Semantic-Geometric-Physical Skill Transfer. Skills are usually learned policies (VLA) or Python functions, not BT subtrees. Composition at Python/scheduling layer, not BT structure.
3. **Direct BT generation** — BTGenBot, BTGenBot-2, LLM-as-BT-Planner (ICRA 2025). No template layer; LLM emits BT XML whole. Position B with structural-fidelity tax.
4. **BT expansion with LLM** — BETR-XP-LLM. Skill library + LLM extends tree when classical planner stalls. Explicitly flags as future work the case where skill library is missing actions and LLM constructs them from primitives — recognizes the gap ChainTree has filled, but hasn't filled it.

**LRLL is closest in spirit:** wake/sleep cycle building skill library without gradient updates. But skills are Python over visual primitives, and there's no classical planner sharing construction primitives.

The structural reason: most work starts from "LLM is the planner" and bolts on safety as needed. ChainTree starts from "the BT is the executable, and we need a representation any planner — classical, LLM, or human — can compose into."

---

## 6. Virtual Actions: ROSPlan and ChainTree

ROSPlan is the canonical virtual-action planner in the ROS world. PDDL operators with declared preconditions/effects; planner sequences over the interface; dispatcher binds to ROS action servers. Planner never sees implementation.

**Why it worked:** abstraction did the structural work. Closed vocabulary with formal semantics; narrow, well-defined seam.

**ChainTree's extension:** capability declarations registered at runtime, not baked into a domain file. Service registry semantics rather than fixed operator domain. Robots advertise capabilities; planner discovers them; bidirectional Dijkstra runs over current registration. Same abstraction, dynamic membership.

**Why it's important:** ROSPlan's brittleness came from PDDL's closed-world assumption, not from the operator concept. The operator concept is what's worth preserving.

Recent LLM-robotics has walked away from this layer — direct generation treats virtual actions as inlinable, Code-as-Policies treats them as Python primitives. Both lose the symbolic interface the planner can reason over. Lost property: pre-execution consistency checking (preconditions of step N satisfied by effects of steps 1..N-1).

---

## 7. The Information-Theoretic Argument (Beizer Hidden States)

**Direct BT generation:** N · log(B) bits of structural commitment. N ≈ 100 nodes, B ≈ 50 (operators × parameter combinations) → ~560 bits in one shot.

**Templated composition:** D · log(T · P). D=6 depth, T=10 templates, P=5 parameters → ~34 bits.

**Compression:** 17× in description length, ~10^160 reduction in plan-space size.

At that ratio, direct generation isn't searching — it's pattern-matching against the training distribution. Templates also preserve invariants raw space lets you violate, so what gets compressed is the *valid* region of the space. Verification reduces correspondingly: each template tested once, each composition rule once, instead of full path coverage with hidden-state interactions.

**Connection to literature:** HTN macro-operators (Korf 1985) cut classical-planner search depth by the same compression mechanism. The field is empirically rediscovering Beizer's hidden-state argument under fresh names: "structural fidelity tax," "long-horizon failure," "compositional generalization gap."

**Why direct BT generation looks viable in current papers:** benchmarks are short-horizon (5–10 steps) where 50^10 is reachable for fine-tuned frontier models with demonstrations. Long-horizon is where the exponent bites — exactly the regime those papers flag as their open problem.

---

## 8. Layered Invariants Architecture

Invariants don't all live at the same level:

- **State-machine-level** (exactly one active state, explicit transitions) → state machine
- **Tree-level** (tick-to-completion, total return codes) → BT
- **Domain-level** (effect/verify co-location, action+precondition, recovery+timeout) → templates
- **Capability-level** (interface contracts, parameter types) → virtual nodes
- **Task-level** (ambiguity resolution, goal grounding) → LLM

Each layer's composition operation is *incapable* of producing the bad shape *at that level*. Trying to make any single layer enforce invariants from all layers (the flat-BT-generation approach) is what causes hidden-state explosion.

**Deeper principle:** the way to make abstract reasoners safe is not to constrain the reasoner — it's to constrain the artifact they can produce. Constraining the reasoner gives you alignment problems, evals, fine-tuning. Constraining the artifact via composition rules and typed building blocks gives you a generator that *can't* produce the bad shape, regardless of internals. Different theory of safety, much stronger guarantees.

---

## 9. LLM vs Classical Planner: Where Each Wins

**Closed, well-modeled domains:** classical planner wins decisively. Valmeekam et al. 2023 — GPT-4 ~35% on Blocksworld at sizes Fast Downward solves 100% in <1s. Reasoning models close gap on small instances, gap reopens on larger. LLMs don't search; classical planners do.

**Closed domain, messy specification:** LLM-as-translator wins. LLM+P pattern beats either component alone.

**Open domain, no clean state representation:** LLM wins by default — no alternative.

### ChainTree mapping

| Layer | Regime | Right tool |
|---|---|---|
| Drive Program over topological graph | Closed, well-modeled | Bidirectional Dijkstra (classical) |
| Method/template choice | Closed, combinatorial | Classical HTN search; LLM fallback |
| Parameter binding from NL | Messy specification | LLM-as-translator |
| Top-level intent resolution | Open | LLM |

In a properly layered system, LLM does ~5% of cognitive work (top, language grounding). Other 95% (search, scheduling, allocation, recovery, validation) is classical, fast, provably correct. Most current work has the ratio inverted because it lacks the layers to push classical methods into.

---

## 10. Funding Distortion (Honest Note)

Three distortions in current LLM-robotics literature:

1. Methods get LLM-ified for non-technical reasons — reviewer pool expects it.
2. Classical baselines weakly represented — many papers don't compare against competent classical planner, or use strawman.
3. Negative results underpublished — finding LLM worse than classical method is hard to place.

ICAPS community has shrunk; classical planning research defunded for ~decade; PhD students steered toward learned methods. ChainTree's value proposition ("robots that work reliably for years") is what customers pay for and what grants don't fund. Right alignment for industrial deployment, wrong alignment for academic capture.

**Crack starting to show:** 2025–26 wave of agentic-AI papers hitting long-horizon failure, rising number of papers studying LLM planning failures, "neurosymbolic" rebrand emerging. Grant language follows results with ~5-year lag. Classical techniques will come back under new vocabulary.

---

## 11. The Bet ChainTree Is Making

Templates-over-virtual-nodes is the right artifact for LLM-era robotics, the same way:

- Make replaced hand-written shell scripts
- Statecharts replaced ad-hoc state machines
- HTN replaced flat planning
- BTs replaced flat state machines
- Typed configuration replaced hand-rolled scripts

**Three things make the bet sound:**

1. The structural argument is independent of LLM capability. Templates are right even with no LLM. Asymmetric: works if LLMs improve, works if they plateau.
2. The pattern has played out repeatedly in adjacent fields — raises the prior.
3. The failure modes the field flags as open problems are exactly the failure modes ChainTree's architecture was designed not to have.

**The risk is adoptional, not architectural.** Lisp lost to C; Smalltalk lost to Java; Plan 9 lost to Linux. Right artifacts have lost to wrong artifacts when the wrong artifact had a more legible on-ramp. Equivalent risk: the field locks into direct-BT-generation because that's what major frameworks ship, leaving template approach technically superior but ecosystem-marginal.

Mitigation: legible on-ramp for each kind of author (human, classical planner, LLM). Strategy problem, separable from the technical core.

---

## 12. Inheritance Strategy (Operative Variable)

Glenn is 71. The operative goal is **transferable asset** for kids, not academic positioning.

The asset is fifty years of pattern recognition compiled into an architecture. The unfair advantage is *codified judgment*, not code:
- Effect/verify co-location
- Virtual nodes belong in service registry, not domain file
- LLM is a leaf, not orchestrator
- Templates are where invariants live

These take decades to learn by being burned by their absence. ChainTree packages the conclusions so someone else inherits them without re-suffering.

### What makes the asset transferable

1. **Documentation of the *why*, not the *what*.** Architectural memos (Drive Program docs, layered-invariants reasoning, template/virtual-node distinction) are the most valuable artifacts in the repo — more so than code, because they encode what the code is *for*. Code can be rewritten. The reasoning cannot be reconstructed from source. Keep writing memos.
2. **People who can receive the asset.** ChainTree compounds in hands of someone with embedded systems background + architectural openness + reason to trust the source. Family is one of few places that combination is naturally present. FLL/WRO competition robotics work is structurally relevant — kids on Pybricks today are demographic that will be senior engineers in 15 years looking for an architecture that doesn't fight them. Plant recognition early; recognition is what compounds. Specific syntax doesn't.
3. **Working deployments outlive working architectures.** The 2013 irrigation controller is more valuable as inheritance than any document, because it's a 13+-year continuous demonstration that the philosophy works in the real world without intervention. Future engineers believe a system that has been running for ten years far more readily than they believe a paper arguing it should run for ten years. Get one or two more deployments running on current ChainTree stack — even small, even unglamorous.

### Open priorities (informational)

- Architectural memo set: clear Drive Program write-up, layered-invariants document, template/virtual-node distinction document, recovery model document. These should read for someone who hasn't seen ChainTree before.
- Deployment demonstration: a second long-running deployment besides the irrigation controller. Even small. Operational duration is the proof.
- On-ramps: legible entry path for human authors, classical planners, and LLM authors using the same template construction primitives.
- FLL/WRO toy version: simplified ChainTree on Pybricks/SPIKE Prime that surfaces the layered-invariants idea at a level competition kids can use. Plants the recognition.
- Repo curation: 33+ repos at github.com/glenn-edgar — flagging which are canonical, which are exploratory, which are deprecated. Future maintainers won't know without that signal.

The construction is mostly done. The transfer — making it legible, deployed, and inherited by people who can extend it — is where remaining returns are. Different kind of engineering than what got Glenn here. Worth treating as its own project.
