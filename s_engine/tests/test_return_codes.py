"""Return-code leaf tests."""

from se_builtins import return_codes as RC
from se_dsl import make_node
from se_runtime import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_CONTINUE,
    SE_FUNCTION_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_RESET,
    invoke_any,
    new_instance_from_tree,
    new_module,
)


def _leaf(fn):
    return make_node(fn, "m_call")


def test_all_18_fns_exist():
    assert len(RC.ALL_RETURN_FNS) == 18


def test_return_pipeline_halt_fires_on_non_lifecycle_events():
    mod = new_module()
    node = _leaf(RC.return_pipeline_halt)
    inst = new_instance_from_tree(mod, node)
    # Fresh invoke: INIT fires first (returns CONTINUE), then TICK returns HALT
    result = invoke_any(inst, node, EVENT_TICK, {})
    assert result == SE_PIPELINE_HALT


def test_return_pipeline_disable_triggers_terminate():
    """PIPELINE_DISABLE from root should fire the TERMINATE event and deactivate."""
    events = []

    def fn(inst, node, event_id, event_data):
        events.append(event_id)
        if event_id in (EVENT_INIT, EVENT_TERMINATE):
            return SE_PIPELINE_CONTINUE
        return SE_PIPELINE_DISABLE

    mod = new_module()
    node = make_node(fn, "m_call")
    inst = new_instance_from_tree(mod, node)
    result = invoke_any(inst, node, EVENT_TICK, {})
    assert result == SE_PIPELINE_DISABLE
    assert events == [EVENT_INIT, EVENT_TICK, EVENT_TERMINATE]
    assert node["active"] is False


def test_return_code_variants_emit_correct_values():
    mod = new_module()
    checks = [
        (RC.return_continue, SE_CONTINUE),
        (RC.return_pipeline_halt, SE_PIPELINE_HALT),
        (RC.return_pipeline_reset, SE_PIPELINE_RESET),
        (RC.return_function_halt, SE_FUNCTION_HALT),
    ]
    for fn, expected in checks:
        node = _leaf(fn)
        inst = new_instance_from_tree(mod, node)
        assert invoke_any(inst, node, EVENT_TICK, {}) == expected


def test_init_and_terminate_events_never_return_non_continue():
    """Leaves should return PIPELINE_CONTINUE during INIT/TERMINATE so the lifecycle is clean."""
    mod = new_module()
    node = _leaf(RC.return_pipeline_halt)
    inst = new_instance_from_tree(mod, node)
    # Call the fn directly (bypass dispatch) to see raw per-event-id behavior
    assert node["fn"](inst, node, EVENT_INIT, {}) == SE_PIPELINE_CONTINUE
    assert node["fn"](inst, node, EVENT_TERMINATE, {}) == SE_PIPELINE_CONTINUE
    assert node["fn"](inst, node, EVENT_TICK, {}) == SE_PIPELINE_HALT
