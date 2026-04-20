"""Public engine API.

Usage:
    from se_runtime import (
        new_module, new_instance_from_tree,
        push_event, tick_once, run_until_idle,
        SE_PIPELINE_DISABLE, EVENT_TICK,
    )
"""

from se_runtime.codes import (
    EVENT_INIT,
    EVENT_TERMINATE,
    EVENT_TICK,
    SE_CONTINUE,
    SE_DISABLE,
    SE_FUNCTION_CONTINUE,
    SE_FUNCTION_DISABLE,
    SE_FUNCTION_HALT,
    SE_FUNCTION_RESET,
    SE_FUNCTION_SKIP_CONTINUE,
    SE_FUNCTION_TERMINATE,
    SE_HALT,
    SE_PIPELINE_CONTINUE,
    SE_PIPELINE_DISABLE,
    SE_PIPELINE_HALT,
    SE_PIPELINE_RESET,
    SE_PIPELINE_SKIP_CONTINUE,
    SE_PIPELINE_TERMINATE,
    SE_RESET,
    SE_SKIP_CONTINUE,
    SE_TERMINATE,
    code_name,
    is_application,
    is_function,
    is_pipeline,
    to_application,
    to_function,
    to_pipeline,
    variant,
)
from se_runtime.dispatch import invoke_any, invoke_main, invoke_oneshot, invoke_pred
from se_runtime.instance import (
    new_instance,
    new_instance_from_tree,
    pop_event,
    push_event,
    queue_empty,
)
from se_runtime.lifecycle import (
    child_count,
    child_invoke,
    child_invoke_oneshot,
    child_invoke_pred,
    child_reset,
    child_reset_recursive,
    child_terminate,
    children_reset_all,
    children_terminate_all,
    reset_recursive,
)
from se_runtime.emit import emit_module_file
from se_runtime.module import load_module, new_module, register_tree
from se_runtime.serialize import deserialize_tree, serialize_tree
from se_runtime.tick import is_complete, run_until_idle, tick_once

__all__ = [
    # codes
    "SE_CONTINUE", "SE_HALT", "SE_TERMINATE", "SE_RESET", "SE_DISABLE", "SE_SKIP_CONTINUE",
    "SE_FUNCTION_CONTINUE", "SE_FUNCTION_HALT", "SE_FUNCTION_TERMINATE",
    "SE_FUNCTION_RESET", "SE_FUNCTION_DISABLE", "SE_FUNCTION_SKIP_CONTINUE",
    "SE_PIPELINE_CONTINUE", "SE_PIPELINE_HALT", "SE_PIPELINE_TERMINATE",
    "SE_PIPELINE_RESET", "SE_PIPELINE_DISABLE", "SE_PIPELINE_SKIP_CONTINUE",
    "EVENT_INIT", "EVENT_TICK", "EVENT_TERMINATE",
    "is_application", "is_function", "is_pipeline", "variant",
    "to_application", "to_function", "to_pipeline", "code_name",
    # module
    "new_module", "load_module", "register_tree",
    # instance
    "new_instance", "new_instance_from_tree",
    "push_event", "pop_event", "queue_empty",
    # dispatch
    "invoke_any", "invoke_main", "invoke_oneshot", "invoke_pred",
    # lifecycle
    "child_count", "child_invoke", "child_invoke_pred", "child_invoke_oneshot",
    "child_terminate", "child_reset", "child_reset_recursive",
    "children_terminate_all", "children_reset_all", "reset_recursive",
    # tick
    "tick_once", "run_until_idle", "is_complete",
    # serialization
    "serialize_tree", "deserialize_tree", "emit_module_file",
]
