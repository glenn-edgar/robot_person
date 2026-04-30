"""CFL engine handle, KB handle, event dispatch, termination, and main loop.

The engine is a plain dict; `new_engine()` constructs a fresh one. Multiple
KBs run concurrently on a single engine. They share the event queue pair,
wall-clock timer, and user-function registries; they do not share
blackboards.

This module provides:

- `new_engine` / `add_kb` / `activate_kb` / `delete_kb` — lifecycle
- `enqueue` — event enqueue convenience
- `enable_node` / `disable_node` / `terminate_node_tree` — node state mgmt
- `execute_node` — INIT-if-needed, call main fn, map CFL code → walker signal
- `execute_event` — top-level dispatch: locate KB, run walker from target
- `run` — main loop (timer tick → drain → sleep)

Per continue.md: node identity is the Python dict reference itself. The KB
that owns a node is found by walking up to the root; the root carries a
`_kb` back-pointer installed at `add_kb` time.
"""

from __future__ import annotations

import time
from datetime import tzinfo
from typing import Any, Callable, Iterable, List, Optional

from . import event_queue as eq
from . import registry as reg
from .codes import (
    CFL_CONTINUE,
    CFL_DISABLE,
    CFL_HALT,
    CFL_HOUR_EVENT,
    CFL_MINUTE_EVENT,
    CFL_RESET,
    CFL_SECOND_EVENT,
    CFL_SKIP_CONTINUE,
    CFL_TERMINATE,
    CFL_TERMINATE_EVENT,
    CFL_TERMINATE_SYSTEM,
    CFL_TERMINATE_SYSTEM_EVENT,
    CFL_TIMER_EVENT,
    CFL_EVENT_TYPE_NULL,
    CT_CONTINUE,
    CT_SKIP_CHILDREN,
    CT_STOP_ALL,
    CT_STOP_SIBLINGS,
    PRIORITY_NORMAL,
    is_valid_cfl_code,
)
from .node import enabled_children, is_leaf, walk_ancestors
from .walker import walk


# ---------------------------------------------------------------------------
# Engine / KB construction
# ---------------------------------------------------------------------------

def _default_get_wall_time() -> int:
    """Linux 64-bit epoch seconds. Matches s_engine's default."""
    return int(time.time())


def new_engine(
    tick_period: float = 0.25,
    registry: Optional[dict] = None,
    logger: Optional[Callable[[str], None]] = None,
    crash_callback: Optional[Callable[[BaseException, dict], None]] = None,
    get_time: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    get_wall_time: Optional[Callable[[], int]] = None,
    timezone: Optional[tzinfo] = None,
) -> dict:
    """Build a fresh engine handle.

    tick_period: seconds between outer iterations (fractional allowed).
    registry:    pre-built registry bundle; defaults to a fresh one.
    logger:      single-arg callable for diagnostic messages.
    crash_callback: called as fn(exc, event) when a user fn raises.
    get_time / sleep: injected for testability.
    get_wall_time: callable returning Linux 64-bit epoch seconds; used by
                   wall-clock operators (e.g. CFL_TIME_WINDOW_CHECK) and
                   forwarded to s_engine modules built via the bridge.
                   Defaults to int(time.time()).
    timezone:      tzinfo for local-time conversions. None = system local.
    """
    return {
        "kbs": {},
        "active_kbs": [],
        "event_queue": eq.new_event_queue(),
        "registry": registry or reg.new_registry(),
        "tick_period": float(tick_period),
        "running": False,
        "cfl_engine_flag": True,
        "logger": logger or (lambda msg: None),
        "crash_callback": crash_callback,
        "get_time": get_time,
        "sleep": sleep,
        "get_wall_time": get_wall_time or _default_get_wall_time,
        "timezone": timezone,
        "last_tick_time": 0.0,
    }


def new_kb(name: str, root: dict, blackboard: Optional[dict] = None) -> dict:
    """Build a KB handle wrapping a tree root."""
    return {
        "name": name,
        "root": root,
        "blackboard": blackboard if blackboard is not None else {},
        "engine": None,  # set by add_kb
    }


def add_kb(engine: dict, kb: dict) -> None:
    """Register a KB with the engine. Does not activate it yet."""
    if kb["name"] in engine["kbs"]:
        raise ValueError(f"add_kb: KB name {kb['name']!r} already registered")
    kb["engine"] = engine
    engine["kbs"][kb["name"]] = kb
    # Stamp kb ref on the root for reverse lookup from any node in its tree.
    kb["root"]["_kb"] = kb


def activate_kb(engine: dict, name: str) -> dict:
    """Enable a KB's root and add it to the active-KB list."""
    kb = engine["kbs"].get(name)
    if kb is None:
        raise ValueError(f"activate_kb: no KB named {name!r}")
    if kb in engine["active_kbs"]:
        return kb
    enable_node(kb["root"])
    engine["active_kbs"].append(kb)
    return kb


def delete_kb(engine: dict, kb: dict) -> None:
    """Terminate a KB's whole tree and remove it from active_kbs."""
    terminate_node_tree(engine, kb, kb["root"])
    if kb in engine["active_kbs"]:
        engine["active_kbs"].remove(kb)


def has_active_kbs(engine: dict) -> bool:
    return bool(engine["active_kbs"])


# ---------------------------------------------------------------------------
# Event enqueue
# ---------------------------------------------------------------------------

def enqueue(engine: dict, event: dict) -> None:
    eq.enqueue(engine["event_queue"], event)


# ---------------------------------------------------------------------------
# Node enable / disable / terminate
# ---------------------------------------------------------------------------

def enable_node(node: dict) -> None:
    """Mark a node as enabled and uninitialized.

    The next walker visit will trigger INIT + main-fn execution.
    """
    node["ct_control"]["enabled"] = True
    node["ct_control"]["initialized"] = False


def disable_node(engine: dict, kb: dict, node: dict) -> None:
    """Tear down a single node (no descent).

    Fires the boolean fn with CFL_TERMINATE_EVENT (if any) and the term
    one-shot (if any), then clears the enabled/initialized flags. Safe to
    call on already-disabled nodes (no-op).
    """
    ctrl = node["ct_control"]
    if not (ctrl["enabled"] and ctrl["initialized"]):
        ctrl["enabled"] = False
        ctrl["initialized"] = False
        return
    ctrl["enabled"] = False
    ctrl["initialized"] = False

    bool_name = node.get("boolean_fn_name")
    if bool_name:
        bool_fn = reg.lookup_boolean(engine["registry"], bool_name)
        if bool_fn is None:
            raise LookupError(
                f"disable_node: boolean fn {bool_name!r} not in registry"
            )
        _safe_call(engine, bool_fn, kb, node, CFL_EVENT_TYPE_NULL,
                   CFL_TERMINATE_EVENT, None, kind="boolean")

    term_name = node.get("term_fn_name")
    if term_name:
        term_fn = reg.lookup_one_shot(engine["registry"], term_name)
        if term_fn is None:
            raise LookupError(
                f"disable_node: term one-shot {term_name!r} not in registry"
            )
        _safe_call_one_shot(engine, term_fn, kb, node)


def terminate_node_tree(engine: dict, kb: dict, subtree_root: dict) -> None:
    """Tear down `subtree_root` and everything beneath it.

    Two phases per continue.md:
      1. Record — DFS pre-order walk collecting every enabled+initialized
         node into a list.
      2. Deliver — iterate that list in REVERSE so children are torn down
         before parents. For each node: clear flags, fire boolean with
         CFL_TERMINATE_EVENT, fire term one-shot.

    Invariant: terminate events always reach children before parents.

    Phase-1 filter: ALL enabled nodes (not just enabled+initialized). The
    spec's "enabled+initialized" filter assumes every enabled node has
    already been INITed by the walker, but that's false when terminate
    fires mid-walk: a sibling later in the parent's child-list may be
    enabled (by INIT enabling all children) but not yet visited / INITed.
    Leaving such nodes enabled means the walker would still visit them
    after the parent was supposedly torn down.

    `disable_node` is a single-node teardown that already handles both
    cases: enabled+init → fires bool(CFL_TERMINATE_EVENT) + term one-shot;
    enabled-only → just clears the flag, no fn calls.
    """
    if is_leaf(subtree_root):
        disable_node(engine, kb, subtree_root)
        return

    term_list: List[dict] = []

    def phase1_visit(node: dict, _event: Any, _level: int) -> str:
        if node["ct_control"]["enabled"]:
            term_list.append(node)
        return CT_CONTINUE

    walk(subtree_root, None, phase1_visit, get_children=enabled_children)

    for node in reversed(term_list):
        disable_node(engine, kb, node)


# ---------------------------------------------------------------------------
# Per-node execution (visited by the walker on a dispatched event)
# ---------------------------------------------------------------------------

def execute_node(
    engine: dict,
    kb: dict,
    node: dict,
    event: dict,
    level: int,
) -> str:
    """INIT-if-needed, run main fn, translate CFL code → walker signal.

    A disabled node returns CT_SKIP_CHILDREN without any fn invocation —
    events dispatched to a disabled subtree are effectively dropped at that
    branch.
    """
    ctrl = node["ct_control"]
    if not ctrl["enabled"]:
        return CT_SKIP_CHILDREN

    if not ctrl["initialized"]:
        init_name = node.get("init_fn_name")
        if init_name:
            init_fn = reg.lookup_one_shot(engine["registry"], init_name)
            if init_fn is None:
                raise LookupError(
                    f"execute_node: init fn {init_name!r} not in registry"
                )
            _safe_call_one_shot(engine, init_fn, kb, node)
        ctrl["initialized"] = True

    main_name = node.get("main_fn_name")
    if not main_name:
        # Pure container with no main fn: descend into enabled children.
        return CT_CONTINUE

    main_fn = reg.lookup_main(engine["registry"], main_name)
    if main_fn is None:
        raise LookupError(f"execute_node: main fn {main_name!r} not in registry")

    try:
        code = main_fn(kb, node.get("boolean_fn_name"), node, event)
    except BaseException as exc:  # noqa: BLE001 - crash callback observes all
        _handle_crash(engine, exc, event)
        raise

    if not is_valid_cfl_code(code):
        raise ValueError(
            f"execute_node: main fn {main_name!r} returned invalid code {code!r}"
        )

    # Non-context-dependent codes: straight table lookup.
    if code == CFL_CONTINUE:
        return CT_CONTINUE
    if code == CFL_HALT:
        return CT_STOP_SIBLINGS
    if code == CFL_SKIP_CONTINUE:
        return CT_SKIP_CHILDREN

    if code == CFL_DISABLE:
        terminate_node_tree(engine, kb, node)
        return CT_SKIP_CHILDREN

    if code == CFL_RESET:
        parent = node["parent"]
        if parent is None:
            # Root reset: full KB restart. Tear the root down and re-enable.
            terminate_node_tree(engine, kb, node)
            enable_node(node)
            return CT_STOP_ALL
        terminate_node_tree(engine, kb, parent)
        enable_node(parent)
        return CT_CONTINUE

    if code == CFL_TERMINATE:
        parent = node["parent"]
        if parent is not None:
            terminate_node_tree(engine, kb, parent)
            return CT_SKIP_CHILDREN
        disable_node(engine, kb, node)
        return CT_STOP_ALL

    if code == CFL_TERMINATE_SYSTEM:
        engine["cfl_engine_flag"] = False
        terminate_node_tree(engine, kb, event["target"])
        return CT_STOP_ALL

    # Unreachable: is_valid_cfl_code already filtered.
    raise ValueError(f"execute_node: unhandled code {code!r}")


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

def execute_event(engine: dict, event: dict) -> None:
    """Run the walker from event['target'] for this event."""
    target = event["target"]
    kb = _kb_of(target)
    if kb is None:
        raise RuntimeError(
            f"execute_event: target node {target.get('name')!r} has no owning KB"
        )

    def visit(node: dict, ev: dict, level: int) -> str:
        return execute_node(engine, kb, node, ev, level)

    walk(target, event, visit, get_children=enabled_children)


# ---------------------------------------------------------------------------
# Timer + main loop
# ---------------------------------------------------------------------------

def generate_timer_events(engine: dict) -> None:
    """Enqueue one CFL_TIMER_EVENT per active KB, plus boundary events
    (CFL_SECOND/MINUTE/HOUR_EVENT) when the corresponding wall-clock
    boundary has been crossed since the previous tick.

    Boundary detection: floor(now / N) > floor(prev / N) where N is
    1 / 60 / 3600. Uses the engine's `get_time` callable (default
    `time.monotonic`); tests can stub it. The first tick after engine
    activation does NOT fire boundary events — there's no "previous"
    tick to compare against, so we just record `now` as the baseline.
    """
    now = engine["get_time"]()
    prev = engine.get("_last_clock_time")
    engine["_last_clock_time"] = now

    second_boundary = prev is not None and int(now) > int(prev)
    minute_boundary = prev is not None and int(now / 60) > int(prev / 60)
    hour_boundary = prev is not None and int(now / 3600) > int(prev / 3600)

    for kb in engine["active_kbs"]:
        if not kb["root"]["ct_control"]["enabled"]:
            continue
        target = kb["root"]
        enqueue(engine, eq.make_event(
            target=target, event_type=CFL_EVENT_TYPE_NULL,
            event_id=CFL_TIMER_EVENT, data=None, priority=PRIORITY_NORMAL,
        ))
        if second_boundary:
            enqueue(engine, eq.make_event(
                target=target, event_type=CFL_EVENT_TYPE_NULL,
                event_id=CFL_SECOND_EVENT, data=None, priority=PRIORITY_NORMAL,
            ))
        if minute_boundary:
            enqueue(engine, eq.make_event(
                target=target, event_type=CFL_EVENT_TYPE_NULL,
                event_id=CFL_MINUTE_EVENT, data=None, priority=PRIORITY_NORMAL,
            ))
        if hour_boundary:
            enqueue(engine, eq.make_event(
                target=target, event_type=CFL_EVENT_TYPE_NULL,
                event_id=CFL_HOUR_EVENT, data=None, priority=PRIORITY_NORMAL,
            ))


def drain(engine: dict) -> bool:
    """Drain the event queue. Returns False if CFL_TERMINATE_SYSTEM_EVENT was
    seen (caller should shut the engine down); True otherwise.
    """
    q = engine["event_queue"]
    while eq.nonempty(q):
        event = eq.pop(q)
        if event is None:
            break
        if event.get("event_id") == CFL_TERMINATE_SYSTEM_EVENT:
            _shutdown_all(engine)
            return False
        execute_event(engine, event)
    return True


def run(engine: dict, starting: Iterable[str] = ()) -> None:
    """Enter the main loop. Runs until no active KBs remain or a
    CFL_TERMINATE_SYSTEM_EVENT / CFL_TERMINATE_SYSTEM code fires.
    """
    for name in starting:
        activate_kb(engine, name)

    engine["running"] = True
    engine["cfl_engine_flag"] = True
    try:
        while has_active_kbs(engine) and engine["cfl_engine_flag"]:
            generate_timer_events(engine)
            if not drain(engine):
                return
            _prune_disabled_kbs(engine)
            if not has_active_kbs(engine):
                return
            engine["sleep"](engine["tick_period"])
    finally:
        engine["running"] = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _kb_of(node: dict) -> Optional[dict]:
    """Walk up to the root and read the `_kb` back-pointer."""
    if node.get("parent") is None:
        return node.get("_kb")
    for ancestor in walk_ancestors(node):
        if ancestor.get("parent") is None:
            return ancestor.get("_kb")
    return None


def _prune_disabled_kbs(engine: dict) -> None:
    """After-drain sweep: any KB whose root is no longer enabled gets a full
    delete_kb (which runs terminate_node_tree) so leftover children get torn
    down properly. Matches the main-loop pseudo in continue.md.
    """
    for kb in list(engine["active_kbs"]):
        if not kb["root"]["ct_control"]["enabled"]:
            delete_kb(engine, kb)


def _shutdown_all(engine: dict) -> None:
    for kb in list(engine["active_kbs"]):
        terminate_node_tree(engine, kb, kb["root"])
    engine["active_kbs"].clear()
    engine["cfl_engine_flag"] = False


def _safe_call(
    engine: dict,
    fn: Callable,
    kb: dict,
    node: dict,
    event_type: str,
    event_id: str,
    event_data: Any,
    kind: str,
) -> Any:
    """Call a boolean fn with crash observation."""
    try:
        return fn(kb, node, event_type, event_id, event_data)
    except BaseException as exc:  # noqa: BLE001
        _handle_crash(engine, exc, {"event_id": event_id, "kind": kind})
        raise


def _safe_call_one_shot(engine: dict, fn: Callable, kb: dict, node: dict) -> None:
    try:
        fn(kb, node)
    except BaseException as exc:  # noqa: BLE001
        _handle_crash(engine, exc, {"kind": "one_shot"})
        raise


def _handle_crash(engine: dict, exc: BaseException, ctx: dict) -> None:
    cb = engine.get("crash_callback")
    if cb is not None:
        try:
            cb(exc, ctx)
        except BaseException:  # noqa: BLE001
            pass
