# Continue: Accessibility Tree Snapshots for Web Agents

**Date:** 2026-05-01
**Context:** OpenClaw-style web agent semantic snapshots, AJAX handling, ChainTree integration angle

---

## Topic 1: How a11y tree snapshotting works

Modern browsers build an **accessibility tree** alongside the DOM — the same structure screen readers (NVDA, VoiceOver) consume. Each node carries:

- **Role** (`button`, `textbox`, `link`, `heading`, `listitem`, ...)
- **Accessible name** (computed from label / aria-label / text content per the W3C accname algorithm)
- **State flags** (checked, expanded, disabled, focused, required)
- **Tree position** (parent/child relationships)

The browser has already normalized "this `<div>` with classes and an onclick handler" into "this is a button labeled 'Submit'." Web agents exploit this.

### Pipeline

1. **Snapshot** via Chrome DevTools Protocol (`Accessibility.getFullAXTree`) or Playwright's `page.accessibility.snapshot()`
2. **Filter** to interactive and meaningful nodes (skip decorative, hidden, off-screen)
3. **Serialize** as indented text with numeric refs on actionable elements
4. **Feed** to LLM, which emits actions like `click(42)` or `fill(17, "hello")`

### Concrete example

Raw HTML:
```html
<div class="btn-wrapper-x4f">
  <button data-testid="..." aria-label="Submit form">
    <span class="icon"></span><span>Submit</span>
  </button>
</div>
```

Serialized a11y tree:
```
[42] button "Submit form"
```

50+ tokens → 5 tokens.

### Why it beats alternatives

- **vs raw HTML:** HTML is dominated by styling/layout noise. The a11y tree is normalized — `<button>`, `<div role="button">`, or `<a>` styled as a button all surface as `role: button`.
- **vs screenshots:** Vision models are slower, costlier, and bad at dense text UIs. A11y gives exact text and structure deterministically. No OCR errors.

### Caveats

- Quality depends on developer a11y hygiene. Sites that fail WCAG fail agents.
- Canvas/WebGL apps (Figma, Google Maps interior) have no useful a11y tree.
- Shadow DOM and cross-origin iframes need separate snapshotting.
- Dynamic content requires re-snapshot after every action.

---

## Topic 2: Does this work for AJAX / JavaScript-driven content?

**Yes** — the a11y tree is *live*. It updates automatically as the DOM mutates. React rerenders, HTMX swaps, Vue reactive updates → next snapshot reflects new state. No stale data like a one-shot `curl` would give.

The hard problem is **timing**: when to snapshot.

### Synchronization strategies

| Strategy | Mechanism | Trade-off |
|---|---|---|
| Network idle | `wait_for_load_state('networkidle')` (500ms quiet) | Crude but works |
| Specific element | `wait_for_selector('[data-testid="results"]')` | Reliable if target known |
| ARIA live regions | Listen for `aria-live="polite"` events | Best on well-built sites |
| Mutation observers | CDP `Accessibility.childNodeInserted` | Event-driven, precise |
| Poll-and-diff | Snapshot every 200ms, stop when stable | Reliable, expensive |

### Edge cases

- **Infinite scroll / virtualization** (react-window, TanStack Virtual): only visible rows are in DOM. Must scroll → snapshot → scroll → snapshot, and dedupe across snapshots since refs change.
- **Optimistic UI:** tree shows optimistic state before server confirms. On failure, UI reverts and agent's mental model goes stale. Wait for *settled*, not optimistic state.
- **Streaming (SSE / WebSocket):** no "done" event. Use debounce on tree stability, or semantic cues (stop button → send button = response complete).
- **SPA client routing:** `pushState` doesn't fire `load`. Watch URL change + tree quiescence.

---

## ChainTree connection

This synchronization problem is structurally identical to the **polled-return-channel** pattern in the ChainTree RS-422 protocol: the system is event-driven, but the observer samples. The question is always *when has the system reached a stable state worth observing*.

Two approaches:

1. **OpenClaw-style heuristics:** network idle + tree quiescence. Generic, works on most sites, occasionally wrong.
2. **ChainTree-style formal predicates:** explicit `results_ready` predicate nodes in the behavior tree. Deterministic, but requires per-site authoring — same authoring cost pattern noted earlier where effective OpenClaw skill authors informally reinvent behavior trees in prose.

The ChainTree advantage here is the same as in the warehouse robotics analysis: explicit behavioral mode switching and graph-native goal addressing instead of implicit state inference. A web-agent ChainTree could model:

- **Behavior tree nodes** for page interactions (click, fill, wait_for_predicate)
- **Predicate nodes** wrapping a11y tree queries (`element_present(role=button, name="Submit")`, `aria_live_settled`)
- **Recovery subtrees** for the optimistic-UI revert case (analog to GPS reroute)
- **EUI-64-style stable identity** for elements across re-renders — currently the weak point of all web agents, since accessibility tree refs are ephemeral

---

## Possible next directions

1. **a11y tree → ChainTree predicate library.** Build a vocabulary of reusable web predicates (form_ready, results_settled, modal_dismissed) analogous to the Hangul-radical sentence parser. FNV-1a dispatch on predicate names.
2. **Stable element identity across re-renders.** Hash on (role, accname, ancestor-chain) rather than ephemeral refs. Open question: how to handle list items where accname is non-unique.
3. **Web-agent variant of the virtual operator concept.** SOPs as behavior trees that interact with web dashboards (e.g., a moon-base scenario where the operator console is browser-based).
4. **Comparison artifact.** Side-by-side: OpenClaw skill (prose + heuristics) vs ChainTree behavior tree (formal predicates) for the same web task. Quantify token cost, determinism, and authoring effort.

---

## Open questions

- How does the OpenClaw approach handle Shadow DOM specifically? Does it walk into shadow roots automatically or is it opt-in?
- What's the right primitive for "wait until stable"? A pure timer is brittle; a CDP mutation observer might be the right ChainTree node type.
- Does it make sense to cache a11y subtrees between actions when only part of the page changed? Diff-based snapshotting would cut token costs further.

