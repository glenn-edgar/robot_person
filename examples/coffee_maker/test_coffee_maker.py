"""Smoke tests for the coffee_maker worked example.

Run from the repo root:
  source enter_venv.sh
  python -m pytest examples/coffee_maker/

These tests exercise the full multi-root flow:
  - System library template (`composites.chain_tree.am_pm_state_machine`)
    resolves via the default empty-prefix root.
  - Project template (`project.coffee_maker.leaves.chain_tree.brew_log`)
    resolves via the prefixed root registered by `bootstrap()`.
  - The solution composes both layers plus an inline lambda.
"""

from __future__ import annotations

from datetime import datetime, timezone

from template_language import (
    describe_template,
    generate_code,
    list_template,
    use_template,
)


KB_NAME = "kitchen"
SOLUTION_PATH = "project.coffee_maker.solutions.chain_tree.morning_kb"
BREW_LOG_PATH = "project.coffee_maker.leaves.chain_tree.brew_log"


def _epoch_for_hour_utc(hour: int) -> int:
    return int(datetime(2026, 5, 1, hour, 0, 0, tzinfo=timezone.utc).timestamp())


def _build(op_list, *, hour_utc: int, log: list[str], max_ticks: int = 5):
    counter = {"n": 0}
    chain = generate_code(
        op_list,
        tick_period=0.0,
        sleep=lambda dt: None,
        get_time=lambda: 0.0,
        get_wall_time=lambda: _epoch_for_hour_utc(hour_utc),
        timezone=timezone.utc,
        logger=log.append,
    )

    def capped_sleep(_dt):
        counter["n"] += 1
        if counter["n"] >= max_ticks:
            chain.engine["cfl_engine_flag"] = False

    chain.engine["sleep"] = capped_sleep
    return chain


# ---- discovery via multi-root -----------------------------------

def test_project_solution_discoverable():
    """The lazy loader resolves the project-prefixed solution path
    via the coffee_maker templates root."""
    d = describe_template(SOLUTION_PATH)
    assert d["kind"] == "solution"
    assert d["engine"] == "chain_tree"
    assert {s["name"] for s in d["slots"]} == {"kb_name"}


def test_project_leaf_discoverable():
    d = describe_template(BREW_LOG_PATH)
    assert d["kind"] == "leaf"
    assert {s["name"] for s in d["slots"]} == {"message"}


def test_list_template_filters_to_project_namespace():
    """`path_under` cleanly scopes discovery to the project."""
    use_template(SOLUTION_PATH, kb_name="discovery")  # forces project loads
    project_paths = {m["path"] for m in list_template(path_under="project.coffee_maker")}
    assert SOLUTION_PATH in project_paths
    assert BREW_LOG_PATH in project_paths
    # Nothing outside the project namespace is in this slice.
    assert all(p.startswith("project.coffee_maker") for p in project_paths)


# ---- end-to-end behavior ----------------------------------------

def test_am_run_brews_coffee():
    op_list = use_template(SOLUTION_PATH, kb_name=KB_NAME)
    log: list[str] = []
    chain = _build(op_list, hour_utc=9, log=log)
    chain.run(starting=[KB_NAME])

    assert "coffee_maker: powering on" in log
    assert "coffee_maker: brewing coffee" in log
    assert "coffee_maker: descaling unit" not in log
    assert log.index("coffee_maker: powering on") < log.index("coffee_maker: brewing coffee")


def test_pm_run_descales():
    op_list = use_template(SOLUTION_PATH, kb_name=KB_NAME)
    log: list[str] = []
    chain = _build(op_list, hour_utc=15, log=log)
    chain.run(starting=[KB_NAME])

    assert "coffee_maker: powering on" in log
    assert "coffee_maker: descaling unit" in log
    assert "coffee_maker: brewing coffee" not in log


# ---- composition shape (the proof that all three layers compose) -----

def test_op_list_mixes_system_and_project_ops():
    """The op-list contains ops from system and project templates,
    plus the inline lambda's op, in the expected order."""
    op_list = use_template(SOLUTION_PATH, kb_name=KB_NAME)
    log_messages = [op.args[0] for op in op_list.ops if op.method == "asm_log_message"]

    # System SM emits "<sm> initial" / "am" / "pm" labels.
    assert f"{KB_NAME}_sm initial" in log_messages
    assert f"{KB_NAME}_sm am" in log_messages
    assert f"{KB_NAME}_sm pm" in log_messages
    # Inline lambda contributes the "powering on" line.
    assert "coffee_maker: powering on" in log_messages
    # Project leaf contributes "brewing coffee" and "descaling unit".
    assert "coffee_maker: brewing coffee" in log_messages
    assert "coffee_maker: descaling unit" in log_messages
