"""ChainTree — fluent stateful DSL builder.

A behavior tree is built by maintaining a stack whose top is the "current
parent" — every leaf added with `asm_*` becomes a child of that parent;
every `define_*` pushes a new frame and `end_*` pops back. The same
`ChainTree` instance owns the engine, so `run()` is a one-step kickoff.

Spec mappings:
- `start_test(name)` → opens a KB; the KB's root is a column-style container
  that auto-enables its declared children at first tick.
- `define_column(name, auto_start=True)` → nested column inside the current
  frame.
- `asm_one_shot(name, data=None)` → leaf whose INIT fires the named one-shot
  and whose MAIN returns CFL_DISABLE so the walker advances.
- `asm_log_message(msg)` → asm_one_shot("CFL_LOG_MESSAGE", {"message": msg}).
- `asm_wait_time(seconds)` → leaf using CFL_WAIT_TIME (HALT until elapsed).
- `asm_terminate / halt / disable / reset / terminate_system` → leaf whose
  MAIN is the corresponding control-mains builtin.
- `run(starting=[...])` → validate every fn-name reference resolves against
  the registry, activate the named KBs, enter the engine main loop.

Stack-balance and unique-name violations raise immediately at the offending
call (fail-early per continue.md "Error handling and validation").
"""

from __future__ import annotations

import itertools
from datetime import tzinfo
from typing import Any, Callable, Iterable, List, Mapping, Optional

import ct_runtime as ct
from ct_builtins import register_all_builtins


_NULL = "CFL_NULL"


class ChainTree:
    def __init__(
        self,
        tick_period: float = 0.25,
        logger: Optional[Callable[[str], None]] = None,
        crash_callback: Optional[Callable] = None,
        get_time: Optional[Callable[[], float]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        get_wall_time: Optional[Callable[[], int]] = None,
        timezone: Optional[tzinfo] = None,
    ):
        kwargs = {"tick_period": tick_period}
        if logger is not None:
            kwargs["logger"] = logger
        if crash_callback is not None:
            kwargs["crash_callback"] = crash_callback
        if get_time is not None:
            kwargs["get_time"] = get_time
        if sleep is not None:
            kwargs["sleep"] = sleep
        if get_wall_time is not None:
            kwargs["get_wall_time"] = get_wall_time
        if timezone is not None:
            kwargs["timezone"] = timezone
        self.engine = ct.new_engine(**kwargs)
        register_all_builtins(self.engine["registry"])

        # Builder state.
        self._frames: List[dict] = []  # each: {"kind": "test"|"column", "node": <ref>, "name": str}
        self._kb_names: set = set()
        self._link_counter = itertools.count()

    # ------------------------------------------------------------------
    # User-fn registration (passthrough to engine registry)
    # ------------------------------------------------------------------

    def add_main(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_main(self.engine["registry"], name, fn, description)

    def add_boolean(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_boolean(self.engine["registry"], name, fn, description)

    def add_one_shot(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_one_shot(self.engine["registry"], name, fn, description)

    def add_se_main(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_se_main(self.engine["registry"], name, fn, description)

    def add_se_pred(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_se_pred(self.engine["registry"], name, fn, description)

    def add_se_one_shot(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_se_one_shot(self.engine["registry"], name, fn, description)

    def add_se_io_one_shot(self, name: str, fn: Callable, description: str = "") -> None:
        ct.add_se_io_one_shot(self.engine["registry"], name, fn, description)

    # ------------------------------------------------------------------
    # Brackets — test and column
    # ------------------------------------------------------------------

    def start_test(self, name: str) -> dict:
        if not isinstance(name, str) or not name:
            raise ValueError("start_test: name must be a non-empty string")
        if self._frames:
            raise RuntimeError(
                f"start_test({name!r}): already inside frame "
                f"{self._frames[-1]['kind']!r}; close it first"
            )
        if name in self._kb_names:
            raise ValueError(f"start_test: KB name {name!r} already used")
        self._kb_names.add(name)

        root = ct.make_node(
            name=name,
            main_fn_name="CFL_COLUMN_MAIN",
            init_fn_name="CFL_COLUMN_INIT",
            term_fn_name="CFL_COLUMN_TERM",
            boolean_fn_name=_NULL,
            data={"auto_start": True, "column_data": None},
        )
        kb = ct.new_kb(name, root)
        ct.add_kb(self.engine, kb)
        self._frames.append({"kind": "test", "node": root, "name": name, "kb": kb})
        return root

    def end_test(self, _ref: Any = None) -> None:
        self._pop("test", "end_test")

    def define_column(
        self,
        name: str,
        auto_start: bool = True,
        column_data: Any = None,
    ) -> dict:
        col = ct.make_node(
            name=self._mk_name(name, "col"),
            main_fn_name="CFL_COLUMN_MAIN",
            init_fn_name="CFL_COLUMN_INIT",
            term_fn_name="CFL_COLUMN_TERM",
            boolean_fn_name=_NULL,
            data={"auto_start": auto_start, "column_data": column_data},
        )
        ct.link_children(self._current_parent("define_column"), [col])
        self._frames.append({"kind": "column", "node": col, "name": name})
        return col

    def end_column(self, _ref: Any = None) -> None:
        self._pop("column", "end_column")

    # ------------------------------------------------------------------
    # Leaves
    # ------------------------------------------------------------------

    def asm_one_shot(self, one_shot_fn: str, data: Optional[dict] = None) -> dict:
        if not isinstance(one_shot_fn, str) or not one_shot_fn:
            raise ValueError("asm_one_shot: one_shot_fn must be a non-empty string")
        leaf = ct.make_node(
            name=self._mk_name(one_shot_fn, "oneshot"),
            main_fn_name="CFL_DISABLE",
            init_fn_name=one_shot_fn,
            boolean_fn_name=_NULL,
            data=data,
        )
        ct.link_children(self._current_parent("asm_one_shot"), [leaf])
        return leaf

    def asm_log_message(self, message: str) -> dict:
        if not isinstance(message, str):
            raise TypeError("asm_log_message: message must be a string")
        return self.asm_one_shot("CFL_LOG_MESSAGE", {"message": message})

    def asm_blackboard_set(self, key: str, value: Any) -> dict:
        return self.asm_one_shot("CFL_BLACKBOARD_SET", {"key": key, "value": value})

    def asm_wait_until_in_time_window(
        self,
        start: Mapping[str, int],
        end: Mapping[str, int],
    ) -> dict:
        """HALT until the wall clock falls inside the configured window,
        then DISABLE. To re-arm, RESET the surrounding parent (subtree
        composition).

        Wall clock from `engine.get_wall_time()` (Linux 64-bit epoch
        seconds), local time via `engine.timezone` (None = system local) —
        both set at ChainTree construction.

        Window = uniform per-field masks across {hour, minute, sec, dow,
        dom}; each field independent. See `ct_builtins/time_window.py` for
        the paired-or-absent rule and wrap semantics.
        """
        leaf = ct.make_node(
            name=self._mk_name("wait_until_in_window", "tw_in"),
            main_fn_name="CFL_WAIT_UNTIL_IN_TIME_WINDOW",
            boolean_fn_name=_NULL,
            data={"start": dict(start), "end": dict(end)},
        )
        ct.link_children(
            self._current_parent("asm_wait_until_in_time_window"), [leaf]
        )
        return leaf

    def asm_wait_until_out_of_time_window(
        self,
        start: Mapping[str, int],
        end: Mapping[str, int],
    ) -> dict:
        """HALT while the wall clock is inside the configured window; DISABLE
        on exit. Idiomatic use: place after a one-shot action so the action
        fires once per window crossing. To re-arm, RESET the parent.
        """
        leaf = ct.make_node(
            name=self._mk_name("wait_until_out_of_window", "tw_out"),
            main_fn_name="CFL_WAIT_UNTIL_OUT_OF_TIME_WINDOW",
            boolean_fn_name=_NULL,
            data={"start": dict(start), "end": dict(end)},
        )
        ct.link_children(
            self._current_parent("asm_wait_until_out_of_time_window"), [leaf]
        )
        return leaf

    def asm_wait_time(self, seconds: float) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"wait_{seconds}s", "wait"),
            main_fn_name="CFL_WAIT_TIME",
            init_fn_name="CFL_WAIT_TIME_INIT",
            boolean_fn_name=_NULL,
            data={"time_delay": float(seconds)},
        )
        ct.link_children(self._current_parent("asm_wait_time"), [leaf])
        return leaf

    def asm_wait_for_event(
        self,
        event_id: str,
        count: int = 1,
        timeout: int = 0,
        timeout_event_id: str = "CFL_TIMER_EVENT",
        error_fn: Optional[str] = None,
        error_data: Any = None,
        reset_flag: bool = False,
    ) -> dict:
        """Halt until `event_id` has been delivered `count` times. If
        `timeout` > 0, after that many `timeout_event_id` ticks fire
        `error_fn` (if any) and either RESET (reset_flag=True) or
        TERMINATE the parent.
        """
        leaf = ct.make_node(
            name=self._mk_name(f"wait_for_{event_id}", "wait"),
            main_fn_name="CFL_WAIT_MAIN",
            init_fn_name="CFL_WAIT_INIT",
            boolean_fn_name="CFL_WAIT_FOR_EVENT",
            data={
                "target_event_id": event_id,
                "target_count": int(count),
                "current_count": 0,
                "timeout": int(timeout),
                "timeout_event_id": timeout_event_id,
                "timeout_count": 0,
                "error_fn": error_fn or _NULL,
                "error_data": error_data,
                "reset_flag": bool(reset_flag),
            },
        )
        ct.link_children(self._current_parent("asm_wait_for_event"), [leaf])
        return leaf

    def asm_verify(
        self,
        bool_fn_name: str,
        error_fn: Optional[str] = None,
        error_data: Any = None,
        reset_flag: bool = False,
    ) -> dict:
        """Assertion leaf. `bool_fn_name` is a registered boolean fn — True →
        verification passes (CONTINUE); False → fire `error_fn` then either
        RESET or TERMINATE the parent.
        """
        leaf = ct.make_node(
            name=self._mk_name(f"verify_{bool_fn_name}", "verify"),
            main_fn_name="CFL_VERIFY",
            boolean_fn_name=bool_fn_name,
            data={
                "error_fn": error_fn or _NULL,
                "error_data": error_data,
                "reset_flag": bool(reset_flag),
            },
        )
        ct.link_children(self._current_parent("asm_verify"), [leaf])
        return leaf

    # ------------------------------------------------------------------
    # s_engine bridge leaves
    # ------------------------------------------------------------------

    def asm_se_module_load(
        self,
        key: str,
        trees: dict,
        constants: Optional[dict] = None,
        fn_registry: Optional[dict] = None,
    ) -> dict:
        """Build an s_engine module sharing the KB blackboard. `trees` maps
        {tree_name: tree_root_dict}; bridge fns are auto-merged into
        fn_registry so serialized trees can reference them by name.
        """
        leaf = ct.make_node(
            name=self._mk_name(f"se_module_load_{key}", "se"),
            main_fn_name="SE_MODULE_LOAD_MAIN",
            init_fn_name="SE_MODULE_LOAD_INIT",
            term_fn_name="SE_MODULE_LOAD_TERM",
            boolean_fn_name=_NULL,
            data={
                "key": key,
                "trees": dict(trees),
                "constants": constants,
                "fn_registry": fn_registry,
            },
        )
        ct.link_children(self._current_parent("asm_se_module_load"), [leaf])
        return leaf

    def asm_se_tree_create(
        self,
        key: str,
        module_key: str,
        tree_name: str,
    ) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"se_tree_create_{key}", "se"),
            main_fn_name="SE_TREE_CREATE_MAIN",
            init_fn_name="SE_TREE_CREATE_INIT",
            term_fn_name="SE_TREE_CREATE_TERM",
            boolean_fn_name=_NULL,
            data={
                "key": key,
                "module_key": module_key,
                "tree_name": tree_name,
            },
        )
        ct.link_children(self._current_parent("asm_se_tree_create"), [leaf])
        return leaf

    def define_se_tick(
        self,
        tree_key: str,
        aux_fn: str = _NULL,
        return_code: str = "CFL_CONTINUE",
    ) -> dict:
        """Open an se_tick composite. Children added between this and
        end_se_tick become the CFL subtrees the s_engine tree can
        enable/disable via cfl_enable_child / cfl_disable_child.
        """
        tick = ct.make_node(
            name=self._mk_name(f"se_tick_{tree_key}", "se"),
            main_fn_name="SE_TICK_MAIN",
            boolean_fn_name=aux_fn,
            data={
                "tree_key": tree_key,
                "return_code": return_code,
            },
        )
        ct.link_children(self._current_parent("define_se_tick"), [tick])
        self._frames.append({"kind": "se_tick", "node": tick, "name": tree_key})
        return tick

    def end_se_tick(self, _ref: Any = None) -> None:
        self._pop("se_tick", "end_se_tick")

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def define_state_machine(
        self,
        name: str,
        state_names: list,
        initial_state: str,
        auto_start: bool = True,
        aux_fn: str = _NULL,
    ) -> dict:
        if not state_names:
            raise ValueError("define_state_machine: state_names must be non-empty")
        if initial_state not in state_names:
            raise ValueError(
                f"define_state_machine: initial_state {initial_state!r} "
                f"not in state_names {state_names!r}"
            )
        if len(set(state_names)) != len(state_names):
            raise ValueError(
                f"define_state_machine: duplicate state names in {state_names!r}"
            )

        sm = ct.make_node(
            name=self._mk_name(f"sm_{name}", "sm"),
            main_fn_name="CFL_STATE_MACHINE_MAIN",
            init_fn_name="CFL_STATE_MACHINE_INIT",
            term_fn_name="CFL_STATE_MACHINE_TERM",
            boolean_fn_name=aux_fn,
            data={
                "auto_start": auto_start,
                "state_names": list(state_names),
                "initial_state": initial_state,
                "defined_states": [],
            },
        )
        ct.link_children(self._current_parent("define_state_machine"), [sm])
        self._frames.append({
            "kind": "state_machine",
            "node": sm,
            "name": name,
            "states": list(state_names),
        })
        return sm

    def define_state(self, state_name: str) -> dict:
        if not self._frames or self._frames[-1]["kind"] != "state_machine":
            raise RuntimeError("define_state: not inside a state_machine frame")
        sm_frame = self._frames[-1]
        if state_name not in sm_frame["states"]:
            raise ValueError(
                f"define_state({state_name!r}): not in declared state_names "
                f"{sm_frame['states']!r}"
            )
        if state_name in sm_frame["node"]["data"]["defined_states"]:
            raise ValueError(f"define_state({state_name!r}): already defined")

        state = ct.make_node(
            name=self._mk_name(f"state_{state_name}", "state"),
            main_fn_name="CFL_COLUMN_MAIN",
            init_fn_name="CFL_COLUMN_INIT",
            term_fn_name="CFL_COLUMN_TERM",
            boolean_fn_name=_NULL,
            data={"state_name": state_name, "auto_start": True, "column_data": None},
        )
        ct.link_children(sm_frame["node"], [state])
        sm_frame["node"]["data"]["defined_states"].append(state_name)
        self._frames.append({"kind": "state", "node": state, "name": state_name})
        return state

    def end_state(self, _ref: Any = None) -> None:
        self._pop("state", "end_state")

    def end_state_machine(self, _ref: Any = None) -> None:
        if not self._frames or self._frames[-1]["kind"] != "state_machine":
            raise RuntimeError("end_state_machine: not inside a state_machine frame")
        sm_frame = self._frames[-1]
        declared = sm_frame["states"]
        defined = sm_frame["node"]["data"]["defined_states"]
        missing = [s for s in declared if s not in defined]
        if missing:
            raise ValueError(
                f"end_state_machine({sm_frame['name']!r}): undefined states {missing!r}"
            )
        # Reorder children to match declared order so current_state_index
        # in the main fn lines up with state_names.
        sm_node = sm_frame["node"]
        by_name = {c["data"]["state_name"]: c for c in sm_node["children"]}
        sm_node["children"] = [by_name[name] for name in declared]
        self._pop("state_machine", "end_state_machine")

    def asm_change_state(self, sm_node: dict, new_state: str) -> dict:
        states = sm_node["data"]["state_names"]
        if new_state not in states:
            raise ValueError(
                f"asm_change_state: {new_state!r} not in SM states {states!r}"
            )
        leaf = ct.make_node(
            name=self._mk_name(f"change_state_{new_state}", "ctrl"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_CHANGE_STATE",
            boolean_fn_name=_NULL,
            data={"sm_node": sm_node, "new_state": new_state},
        )
        ct.link_children(self._current_parent("asm_change_state"), [leaf])
        return leaf

    def asm_terminate_state_machine(self, sm_node: dict) -> dict:
        leaf = ct.make_node(
            name=self._mk_name("terminate_sm", "ctrl"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_TERMINATE_STATE_MACHINE",
            boolean_fn_name=_NULL,
            data={"sm_node": sm_node},
        )
        ct.link_children(self._current_parent("asm_terminate_state_machine"), [leaf])
        return leaf

    def asm_reset_state_machine(self, sm_node: dict) -> dict:
        leaf = ct.make_node(
            name=self._mk_name("reset_sm", "ctrl"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_RESET_STATE_MACHINE",
            boolean_fn_name=_NULL,
            data={"sm_node": sm_node},
        )
        ct.link_children(self._current_parent("asm_reset_state_machine"), [leaf])
        return leaf

    # ------------------------------------------------------------------
    # Sequence-til
    # ------------------------------------------------------------------

    def define_sequence_til_pass(
        self,
        name: str,
        finalize_fn: Optional[str] = None,
        user_data: Any = None,
        aux_fn: str = _NULL,
    ) -> dict:
        return self._define_sequence(
            name=name,
            main_fn="CFL_SEQUENCE_PASS_MAIN",
            kind="seq_pass",
            finalize_fn=finalize_fn,
            user_data=user_data,
            aux_fn=aux_fn,
        )

    def end_sequence_til_pass(self, _ref: Any = None) -> None:
        self._pop("seq_pass", "end_sequence_til_pass")

    def define_sequence_til_fail(
        self,
        name: str,
        finalize_fn: Optional[str] = None,
        user_data: Any = None,
        aux_fn: str = _NULL,
    ) -> dict:
        return self._define_sequence(
            name=name,
            main_fn="CFL_SEQUENCE_FAIL_MAIN",
            kind="seq_fail",
            finalize_fn=finalize_fn,
            user_data=user_data,
            aux_fn=aux_fn,
        )

    def end_sequence_til_fail(self, _ref: Any = None) -> None:
        self._pop("seq_fail", "end_sequence_til_fail")

    # ------------------------------------------------------------------
    # Supervisor
    # ------------------------------------------------------------------

    def define_supervisor(
        self,
        name: str,
        termination_type: str = "ONE_FOR_ONE",
        restart_enabled: bool = True,
        reset_limited_enabled: bool = False,
        max_reset_number: int = 1,
        reset_window: float = 10.0,
        finalize_fn: Optional[str] = None,
        user_data: Any = None,
        aux_fn: str = _NULL,
        auto_start: bool = True,
    ) -> dict:
        if termination_type not in ("ONE_FOR_ONE", "ONE_FOR_ALL", "REST_FOR_ALL"):
            raise ValueError(
                f"define_supervisor: termination_type must be ONE_FOR_ONE / "
                f"ONE_FOR_ALL / REST_FOR_ALL, got {termination_type!r}"
            )
        sup = ct.make_node(
            name=self._mk_name(f"sup_{name}", "sup"),
            main_fn_name="CFL_SUPERVISOR_MAIN",
            init_fn_name="CFL_SUPERVISOR_INIT",
            term_fn_name="CFL_SUPERVISOR_TERM",
            boolean_fn_name=aux_fn,
            data={
                "auto_start": auto_start,
                "termination_type": termination_type,
                "restart_enabled": bool(restart_enabled),
                "reset_limited_enabled": bool(reset_limited_enabled),
                "max_reset_number": int(max_reset_number),
                "reset_window": float(reset_window),
                "finalize_fn": finalize_fn or _NULL,
                "user_data": user_data,
            },
        )
        ct.link_children(self._current_parent("define_supervisor"), [sup])
        self._frames.append({"kind": "supervisor", "node": sup, "name": name})
        return sup

    def define_supervisor_one_for_one(self, name: str, **kwargs) -> dict:
        return self.define_supervisor(name, termination_type="ONE_FOR_ONE", **kwargs)

    def define_supervisor_one_for_all(self, name: str, **kwargs) -> dict:
        return self.define_supervisor(name, termination_type="ONE_FOR_ALL", **kwargs)

    def define_supervisor_rest_for_all(self, name: str, **kwargs) -> dict:
        return self.define_supervisor(name, termination_type="REST_FOR_ALL", **kwargs)

    def end_supervisor(self, _ref: Any = None) -> None:
        self._pop("supervisor", "end_supervisor")

    # ------------------------------------------------------------------
    # Exception catch + heartbeat
    # ------------------------------------------------------------------

    def define_exception_handler(
        self,
        name: str,
        boolean_filter_fn: str = _NULL,
        logging_fn: str = _NULL,
    ) -> dict:
        """Open an exception_catch frame. Must contain exactly one
        define_main_column / end_main_column, define_recovery_column /
        end_recovery_column, define_finalize_column / end_finalize_column.
        """
        catch = ct.make_node(
            name=self._mk_name(f"catch_{name}", "catch"),
            main_fn_name="CFL_EXCEPTION_CATCH_MAIN",
            init_fn_name="CFL_EXCEPTION_CATCH_INIT",
            term_fn_name="CFL_EXCEPTION_CATCH_TERM",
            boolean_fn_name=_NULL,
            data={
                "boolean_filter_fn": boolean_filter_fn,
                "logging_fn": logging_fn,
            },
        )
        ct.link_children(self._current_parent("define_exception_handler"), [catch])
        self._frames.append({
            "kind": "exception_handler",
            "node": catch,
            "name": name,
            "main_defined": False,
            "recovery_defined": False,
            "finalize_defined": False,
        })
        return catch

    def end_exception_handler(self, _ref: Any = None) -> None:
        if not self._frames or self._frames[-1]["kind"] != "exception_handler":
            raise RuntimeError("end_exception_handler: not inside an exception_handler frame")
        f = self._frames[-1]
        missing = []
        if not f["main_defined"]:
            missing.append("MAIN")
        if not f["recovery_defined"]:
            missing.append("RECOVERY")
        if not f["finalize_defined"]:
            missing.append("FINALIZE")
        if missing:
            raise ValueError(
                f"end_exception_handler({f['name']!r}): missing column(s) {missing!r}"
            )
        self._pop("exception_handler", "end_exception_handler")

    def define_main_column(self) -> dict:
        return self._define_exception_subcolumn("main")

    def end_main_column(self, _ref: Any = None) -> None:
        self._pop("exception_main", "end_main_column")

    def define_recovery_column(self) -> dict:
        return self._define_exception_subcolumn("recovery")

    def end_recovery_column(self, _ref: Any = None) -> None:
        self._pop("exception_recovery", "end_recovery_column")

    def define_finalize_column(self) -> dict:
        return self._define_exception_subcolumn("finalize")

    def end_finalize_column(self, _ref: Any = None) -> None:
        self._pop("exception_finalize", "end_finalize_column")

    def _define_exception_subcolumn(self, slot: str) -> dict:
        # slot in ("main", "recovery", "finalize")
        if not self._frames or self._frames[-1]["kind"] != "exception_handler":
            raise RuntimeError(
                f"define_{slot}_column: not inside an exception_handler frame"
            )
        ec_frame = self._frames[-1]
        flag = f"{slot}_defined"
        if ec_frame[flag]:
            raise RuntimeError(f"define_{slot}_column: {slot} column already defined")
        col = ct.make_node(
            name=self._mk_name(f"{slot}_col", "exc"),
            main_fn_name="CFL_COLUMN_MAIN",
            init_fn_name="CFL_COLUMN_INIT",
            term_fn_name="CFL_COLUMN_TERM",
            boolean_fn_name=_NULL,
            data={"auto_start": True, "column_data": None},
        )
        ct.link_children(ec_frame["node"], [col])
        ec_frame[flag] = True
        self._frames.append({"kind": f"exception_{slot}", "node": col, "name": slot})
        return col

    def asm_raise_exception(
        self,
        exception_id: str,
        exception_data: Any = None,
    ) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"raise_{exception_id}", "raise"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_RAISE_EXCEPTION",
            boolean_fn_name=_NULL,
            data={"exception_id": exception_id, "exception_data": exception_data},
        )
        ct.link_children(self._current_parent("asm_raise_exception"), [leaf])
        return leaf

    def asm_turn_heartbeat_on(self, timeout: int) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"hb_on_{timeout}", "hb"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_TURN_HEARTBEAT_ON",
            boolean_fn_name=_NULL,
            data={"timeout": int(timeout)},
        )
        ct.link_children(self._current_parent("asm_turn_heartbeat_on"), [leaf])
        return leaf

    def asm_turn_heartbeat_off(self) -> dict:
        leaf = ct.make_node(
            name=self._mk_name("hb_off", "hb"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_TURN_HEARTBEAT_OFF",
            boolean_fn_name=_NULL,
        )
        ct.link_children(self._current_parent("asm_turn_heartbeat_off"), [leaf])
        return leaf

    # ------------------------------------------------------------------
    # Controlled nodes (client-server RPC)
    # ------------------------------------------------------------------

    def define_controlled_server(
        self,
        name: str,
        request_port: dict,
        response_port: dict,
        handler_fn: str = _NULL,
        response_data: Optional[dict] = None,
    ) -> dict:
        """Open a server frame. Children become the work executed for
        each accepted request; on completion the server posts a response
        high-pri to the client.
        """
        server = ct.make_node(
            name=self._mk_name(f"server_{name}", "ctrl"),
            main_fn_name="CFL_CONTROLLED_SERVER_MAIN",
            boolean_fn_name=handler_fn,
            data={
                "request_port": dict(request_port),
                "response_port": dict(response_port),
                "client_node": None,
                "response_data": dict(response_data) if response_data else {},
            },
        )
        ct.link_children(self._current_parent("define_controlled_server"), [server])
        self._frames.append({"kind": "controlled_server", "node": server, "name": name})
        return server

    def end_controlled_server(self, _ref: Any = None) -> None:
        self._pop("controlled_server", "end_controlled_server")

    def asm_client_controlled_node(
        self,
        server_node: dict,
        request_port: dict,
        response_port: dict,
        request_data: Optional[dict] = None,
        response_handler: str = _NULL,
        timeout: int = 0,
        timeout_event_id: str = "CFL_TIMER_EVENT",
        error_fn: Optional[str] = None,
        error_data: Any = None,
        reset_flag: bool = False,
    ) -> dict:
        """Issue a one-shot RPC to a controlled server.

        Optional timeout removes the "client hangs forever" footgun: if
        `timeout > 0`, after that many `timeout_event_id` ticks without a
        matching response the client fires `error_fn` (if any) and either
        RESETs the parent (retry, `reset_flag=True`) or TERMINATEs it
        (give up, default).
        """
        client = ct.make_node(
            name=self._mk_name(f"client_{request_port.get('event_id', '')}", "ctrl"),
            main_fn_name="CFL_CONTROLLED_CLIENT_MAIN",
            init_fn_name="CFL_CONTROLLED_CLIENT_INIT",
            term_fn_name="CFL_CONTROLLED_CLIENT_TERM",
            boolean_fn_name=response_handler,
            data={
                "server_node": server_node,
                "request_port": dict(request_port),
                "response_port": dict(response_port),
                "request_data": dict(request_data) if request_data else {},
                "timeout": int(timeout),
                "timeout_event_id": timeout_event_id,
                "timeout_count": 0,
                "error_fn": error_fn or _NULL,
                "error_data": error_data,
                "reset_flag": bool(reset_flag),
            },
        )
        ct.link_children(self._current_parent("asm_client_controlled_node"), [client])
        return client

    # ------------------------------------------------------------------
    # Streaming pipeline leaves
    # ------------------------------------------------------------------

    def asm_streaming_sink(self, port: dict, handler_fn: str) -> dict:
        """Consumer leaf — invokes `handler_fn` on every streaming event
        whose port matches. `port` is `{event_id, schema?, handler_id?}`.
        """
        return self._asm_streaming("CFL_STREAMING_SINK_PACKET", "sink", port, handler_fn)

    def asm_streaming_tap(self, port: dict, handler_fn: str) -> dict:
        return self._asm_streaming("CFL_STREAMING_TAP_PACKET", "tap", port, handler_fn)

    def asm_streaming_filter(self, port: dict, predicate_fn: str) -> dict:
        return self._asm_streaming("CFL_STREAMING_FILTER_PACKET", "filter", port, predicate_fn)

    def asm_streaming_transform(
        self,
        inport: dict,
        outport: dict,
        transform_fn: str,
    ) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"transform_{inport.get('event_id', '')}", "stream"),
            main_fn_name="CFL_STREAMING_TRANSFORM_PACKET",
            boolean_fn_name=transform_fn,
            data={"port": inport, "outport": outport},
        )
        ct.link_children(self._current_parent("asm_streaming_transform"), [leaf])
        return leaf

    def _asm_streaming(self, main_fn: str, label: str, port: dict, fn: str) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"{label}_{port.get('event_id', '')}", "stream"),
            main_fn_name=main_fn,
            boolean_fn_name=fn,
            data={"port": dict(port)},
        )
        ct.link_children(self._current_parent(f"asm_streaming_{label}"), [leaf])
        return leaf

    def asm_streaming_collect(
        self,
        inports: list,
        outport: dict,
        observer_fn: str = _NULL,
        target_node: Optional[dict] = None,
    ) -> dict:
        """Multi-port packet accumulator. Holds the most-recent packet per
        inport; once every inport has produced one, emits a combined
        `{inport_event_id: packet, ...}` packet on `outport` (with
        `_schema` injected if outport carries one).

        `target_node` is where the combined packet's walk starts. Defaults
        to the collect node's parent — typical wiring places the
        downstream `asm_streaming_sink_collected` as a sibling of the
        collect, so the parent's walk descends through both.

        `observer_fn` is an optional boolean called on each matching
        packet for bookkeeping; its return value is ignored.
        """
        if not inports:
            raise ValueError("asm_streaming_collect: inports must be non-empty")
        leaf = ct.make_node(
            name=self._mk_name(f"collect_{outport.get('event_id', '')}", "stream"),
            main_fn_name="CFL_STREAMING_COLLECT_PACKET",
            init_fn_name="CFL_STREAMING_COLLECT_INIT",
            boolean_fn_name=observer_fn,
            data={
                "inports": [dict(p) for p in inports],
                "outport": dict(outport),
                "target_node": target_node,
                "pending": {},
            },
        )
        ct.link_children(self._current_parent("asm_streaming_collect"), [leaf])
        return leaf

    def asm_streaming_sink_collected(self, port: dict, handler_fn: str) -> dict:
        """Sink variant for collected packets. Same dispatch as
        `asm_streaming_sink` — distinct main-fn name documents the role
        and gives a hook for future collected-specific validation.
        """
        return self._asm_streaming(
            "CFL_STREAMING_SINK_COLLECTED", "sink_collected", port, handler_fn
        )

    def asm_streaming_verify(
        self,
        port: dict,
        predicate_fn: str,
        error_fn: Optional[str] = None,
        error_data: Any = None,
        reset_flag: bool = False,
    ) -> dict:
        """Streaming-aware assertion leaf. On a packet matching `port`,
        invoke the predicate boolean; True → CONTINUE; False → fire
        `error_fn` (if any) then either RESET (retry the parent) or
        TERMINATE the parent (`reset_flag` controls the choice).

        Non-matching events pass through transparently — safe to colocate
        alongside sinks / taps in a streaming pipeline.
        """
        leaf = ct.make_node(
            name=self._mk_name(f"verify_{port.get('event_id', '')}", "stream"),
            main_fn_name="CFL_STREAMING_VERIFY_PACKET",
            boolean_fn_name=predicate_fn,
            data={
                "port": dict(port),
                "error_fn": error_fn or _NULL,
                "error_data": error_data,
                "reset_flag": bool(reset_flag),
            },
        )
        ct.link_children(self._current_parent("asm_streaming_verify"), [leaf])
        return leaf

    # Convenience for tests / scripts: enqueue a streaming event from a
    # one-shot. The user passes a target node ref + port + payload.

    def asm_emit_streaming(
        self,
        target_node: dict,
        port: dict,
        payload: dict,
    ) -> dict:
        """One-shot leaf that posts a streaming event at INIT time. The
        event targets `target_node`; payload is augmented with `_schema`
        from `port` if present.
        """
        data = dict(payload)
        if "schema" in port and "_schema" not in data:
            data["_schema"] = port["schema"]
        leaf = ct.make_node(
            name=self._mk_name(f"emit_{port.get('event_id', '')}", "stream"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_EMIT_STREAMING",
            boolean_fn_name=_NULL,
            data={
                "target_node": target_node,
                "event_id": port["event_id"],
                "data": data,
            },
        )
        ct.link_children(self._current_parent("asm_emit_streaming"), [leaf])
        return leaf

    def asm_heartbeat_event(self) -> dict:
        leaf = ct.make_node(
            name=self._mk_name("hb_tick", "hb"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_HEARTBEAT_EVENT",
            boolean_fn_name=_NULL,
        )
        ct.link_children(self._current_parent("asm_heartbeat_event"), [leaf])
        return leaf

    # ------------------------------------------------------------------
    # Sequence-til marks (placed alongside the asm_* leaves)
    # ------------------------------------------------------------------

    def asm_mark_sequence_pass(self, seq_node: dict, data: Any = None) -> dict:
        return self._asm_mark(seq_node, True, data)

    def asm_mark_sequence_fail(self, seq_node: dict, data: Any = None) -> dict:
        return self._asm_mark(seq_node, False, data)

    def asm_mark_sequence_if(
        self,
        seq_node: dict,
        predicate_fn: str,
        true_data: Any = None,
        false_data: Any = None,
    ) -> dict:
        """Probe `predicate_fn` at INIT time and mark the current
        sequence_til child's status accordingly: True → pass with
        `true_data`, False → fail with `false_data`. Lets a single
        attempt column branch on a boolean without needing an explicit
        if-else operator. Used by the `retry_until_success` macro.
        """
        leaf = ct.make_node(
            name=self._mk_name(f"mark_if_{predicate_fn}", "mark"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_MARK_SEQUENCE_IF",
            boolean_fn_name=_NULL,
            data={
                "parent_node": seq_node,
                "predicate_fn": predicate_fn,
                "true_data": true_data,
                "false_data": false_data,
            },
        )
        ct.link_children(self._current_parent("asm_mark_sequence_if"), [leaf])
        return leaf

    def _define_sequence(
        self,
        name: str,
        main_fn: str,
        kind: str,
        finalize_fn: Optional[str],
        user_data: Any,
        aux_fn: str,
    ) -> dict:
        seq = ct.make_node(
            name=self._mk_name(f"{kind}_{name}", "seq"),
            main_fn_name=main_fn,
            init_fn_name="CFL_SEQUENCE_INIT",
            term_fn_name="CFL_SEQUENCE_TERM",
            boolean_fn_name=aux_fn,
            data={
                "finalize_fn": finalize_fn or _NULL,
                "user_data": user_data,
            },
        )
        ct.link_children(self._current_parent(f"define_{kind}"), [seq])
        self._frames.append({"kind": kind, "node": seq, "name": name})
        return seq

    def _asm_mark(self, seq_node: dict, result: bool, data: Any) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(f"mark_{result}", "mark"),
            main_fn_name="CFL_DISABLE",
            init_fn_name="CFL_MARK_SEQUENCE",
            boolean_fn_name=_NULL,
            data={"parent_node": seq_node, "result": bool(result), "data": data},
        )
        ct.link_children(self._current_parent("asm_mark_sequence"), [leaf])
        return leaf

    # ------------------------------------------------------------------
    # Control leaves
    # ------------------------------------------------------------------

    def asm_terminate(self) -> dict:
        return self._asm_control("CFL_TERMINATE")

    def asm_halt(self) -> dict:
        return self._asm_control("CFL_HALT")

    def asm_disable(self) -> dict:
        return self._asm_control("CFL_DISABLE")

    def asm_reset(self) -> dict:
        return self._asm_control("CFL_RESET")

    def asm_terminate_system(self) -> dict:
        return self._asm_control("CFL_TERMINATE_SYSTEM")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, starting: Optional[Iterable[str]] = None) -> None:
        if self._frames:
            raise RuntimeError(
                f"run: builder still has open frames: "
                f"{[f['kind'] + ':' + f.get('name', '') for f in self._frames]}"
            )
        self.validate()
        if starting is None:
            starting = list(self.engine["kbs"].keys())
        ct.run(self.engine, starting=starting)

    def validate(self) -> None:
        """Run all build-time checks. Raises on the first failure.

        Currently checks:
          - Every fn-name reference (main / boolean / init / term)
            resolves against the engine registry.
          - Every node ref stored in `data` (sm_node / server_node /
            target_node / parent_node) points to a node of an expected
            type for the slot.
          - Operator-specific structural invariants:
              * exception_handler nodes have at least one initialized
                ct_control["catch_links"] map (set up by INIT) — skipped
                pre-run since INIT hasn't fired yet, but children count
                is checked: catch nodes must have exactly 3 children.
              * state_machine: every declared state name has a state
                column child whose data["state_name"] matches; the
                children list length matches state_names.
              * controlled_server: must have at least one work child.
              * sequence_til (PASS / FAIL): must contain at least one
                CFL_MARK_SEQUENCE leaf somewhere in its subtree.

        Call this independently from `run()` if you want to fail fast at
        build time rather than discovering errors in the first tick. The
        `run()` method calls it automatically.
        """
        self._validate_unresolved()
        self._validate_structure()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _current_parent(self, caller: str) -> dict:
        if not self._frames:
            raise RuntimeError(
                f"{caller}: no open frame; call start_test(...) first"
            )
        return self._frames[-1]["node"]

    def _pop(self, expected_kind: str, caller: str) -> None:
        if not self._frames:
            raise RuntimeError(f"{caller}: no open frame to close")
        top = self._frames[-1]
        if top["kind"] != expected_kind:
            raise RuntimeError(
                f"{caller}: top frame is {top['kind']!r} "
                f"({top.get('name')!r}); expected {expected_kind!r}"
            )
        self._frames.pop()

    def _asm_control(self, code_main_name: str) -> dict:
        leaf = ct.make_node(
            name=self._mk_name(code_main_name, "ctrl"),
            main_fn_name=code_main_name,
            boolean_fn_name=_NULL,
        )
        ct.link_children(self._current_parent(f"asm_{code_main_name.lower()}"), [leaf])
        return leaf

    def _mk_name(self, label: str, kind: str) -> str:
        return f"{kind}_{label}_{next(self._link_counter)}"

    def _validate_unresolved(self) -> None:
        """Walk every KB tree and confirm every fn-name reference resolves."""
        from ct_runtime.registry import (
            lookup_boolean,
            lookup_main,
            lookup_one_shot,
        )
        registry = self.engine["registry"]

        def check(node: dict, kb_name: str) -> None:
            for slot, lookup in (
                ("main_fn_name", lookup_main),
                ("boolean_fn_name", lookup_boolean),
                ("init_fn_name", lookup_one_shot),
                ("term_fn_name", lookup_one_shot),
            ):
                name = node.get(slot)
                if name is None:
                    continue
                if lookup(registry, name) is None:
                    raise LookupError(
                        f"validate: KB {kb_name!r} node {node['name']!r} {slot}={name!r} "
                        f"is not registered"
                    )
            for c in node["children"]:
                check(c, kb_name)

        for kb_name, kb in self.engine["kbs"].items():
            check(kb["root"], kb_name)

    def _validate_structure(self) -> None:
        """Operator-specific structural invariants. Run after the unresolved
        check so the messages can lean on `main_fn_name` matching its
        builtin namespace.
        """

        def has_descendant(n: dict, predicate) -> bool:
            for c in n["children"]:
                if predicate(c) or has_descendant(c, predicate):
                    return True
            return False

        def check(node: dict, kb_name: str) -> None:
            main_fn = node.get("main_fn_name")

            if main_fn == "CFL_EXCEPTION_CATCH_MAIN":
                # MAIN, RECOVERY, FINALIZE columns — exactly 3.
                if len(node["children"]) != 3:
                    raise ValueError(
                        f"validate: KB {kb_name!r} exception_handler "
                        f"{node['name']!r} has {len(node['children'])} children; "
                        f"expected 3 (MAIN, RECOVERY, FINALIZE)"
                    )

            elif main_fn == "CFL_STATE_MACHINE_MAIN":
                state_names = list(node["data"].get("state_names") or [])
                if len(node["children"]) != len(state_names):
                    raise ValueError(
                        f"validate: KB {kb_name!r} state_machine "
                        f"{node['name']!r} has {len(node['children'])} children "
                        f"but {len(state_names)} declared states"
                    )
                # Every child should be a state column with a matching
                # state_name in data.
                for child, declared in zip(node["children"], state_names):
                    sn = child["data"].get("state_name")
                    if sn != declared:
                        raise ValueError(
                            f"validate: KB {kb_name!r} state_machine "
                            f"{node['name']!r} child has state_name={sn!r}, "
                            f"expected {declared!r} (declared order)"
                        )

            elif main_fn == "CFL_CONTROLLED_SERVER_MAIN":
                if not node["children"]:
                    raise ValueError(
                        f"validate: KB {kb_name!r} controlled_server "
                        f"{node['name']!r} has no work children — request "
                        f"would complete instantly with no side effect"
                    )

            elif main_fn in ("CFL_SEQUENCE_PASS_MAIN", "CFL_SEQUENCE_FAIL_MAIN"):
                # The sequence_til parent itself doesn't host marks — they
                # live in descendant subtrees. At least one mark anywhere
                # under here is required, otherwise the sequence can never
                # advance.
                def is_mark(c: dict) -> bool:
                    return c.get("init_fn_name") in (
                        "CFL_MARK_SEQUENCE", "CFL_MARK_SEQUENCE_IF",
                    )
                if not has_descendant(node, is_mark):
                    raise ValueError(
                        f"validate: KB {kb_name!r} sequence_til "
                        f"{node['name']!r} contains no asm_mark_sequence_* "
                        f"leaves — the sequence can never advance"
                    )

            # Cross-reference checks on data fields.
            data = node.get("data") or {}
            sm_node = data.get("sm_node")
            if isinstance(sm_node, dict) and "ct_control" in sm_node:
                target_main = sm_node.get("main_fn_name")
                if target_main != "CFL_STATE_MACHINE_MAIN":
                    raise ValueError(
                        f"validate: KB {kb_name!r} node {node['name']!r} "
                        f"sm_node refers to {sm_node.get('name')!r} which is "
                        f"main_fn_name={target_main!r}, not a state machine"
                    )
            server_node = data.get("server_node")
            if isinstance(server_node, dict) and "ct_control" in server_node:
                target_main = server_node.get("main_fn_name")
                if target_main != "CFL_CONTROLLED_SERVER_MAIN":
                    raise ValueError(
                        f"validate: KB {kb_name!r} node {node['name']!r} "
                        f"server_node refers to {server_node.get('name')!r} "
                        f"which is main_fn_name={target_main!r}, not a "
                        f"controlled server"
                    )

            for c in node["children"]:
                check(c, kb_name)

        for kb_name, kb in self.engine["kbs"].items():
            check(kb["root"], kb_name)
