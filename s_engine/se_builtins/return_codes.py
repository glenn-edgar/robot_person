"""Return-code leaf operators (m_call).

Each is an m_call fn that returns a fixed code on every tick. Useful for
injecting a specific control code into a sequence or as a placeholder in
guarded branches.

All 18 codes get a matching fn. They ignore init/terminate events (return
the code only on other events — init/terminate return CONTINUE so the
lifecycle completes cleanly and TERMINATE fires on DISABLE).
"""

from __future__ import annotations

from se_runtime import codes as C


def _maker(code: int):
    def fn(inst, node, event_id, event_data):
        if event_id in (C.EVENT_INIT, C.EVENT_TERMINATE):
            return C.SE_PIPELINE_CONTINUE
        return code
    fn.__name__ = f"return_{C.code_name(code).lower()}"
    return fn


return_continue = _maker(C.SE_CONTINUE)
return_halt = _maker(C.SE_HALT)
return_terminate = _maker(C.SE_TERMINATE)
return_reset = _maker(C.SE_RESET)
return_disable = _maker(C.SE_DISABLE)
return_skip_continue = _maker(C.SE_SKIP_CONTINUE)

return_function_continue = _maker(C.SE_FUNCTION_CONTINUE)
return_function_halt = _maker(C.SE_FUNCTION_HALT)
return_function_terminate = _maker(C.SE_FUNCTION_TERMINATE)
return_function_reset = _maker(C.SE_FUNCTION_RESET)
return_function_disable = _maker(C.SE_FUNCTION_DISABLE)
return_function_skip_continue = _maker(C.SE_FUNCTION_SKIP_CONTINUE)

return_pipeline_continue = _maker(C.SE_PIPELINE_CONTINUE)
return_pipeline_halt = _maker(C.SE_PIPELINE_HALT)
return_pipeline_terminate = _maker(C.SE_PIPELINE_TERMINATE)
return_pipeline_reset = _maker(C.SE_PIPELINE_RESET)
return_pipeline_disable = _maker(C.SE_PIPELINE_DISABLE)
return_pipeline_skip_continue = _maker(C.SE_PIPELINE_SKIP_CONTINUE)


ALL_RETURN_FNS = {
    C.SE_CONTINUE: return_continue,
    C.SE_HALT: return_halt,
    C.SE_TERMINATE: return_terminate,
    C.SE_RESET: return_reset,
    C.SE_DISABLE: return_disable,
    C.SE_SKIP_CONTINUE: return_skip_continue,
    C.SE_FUNCTION_CONTINUE: return_function_continue,
    C.SE_FUNCTION_HALT: return_function_halt,
    C.SE_FUNCTION_TERMINATE: return_function_terminate,
    C.SE_FUNCTION_RESET: return_function_reset,
    C.SE_FUNCTION_DISABLE: return_function_disable,
    C.SE_FUNCTION_SKIP_CONTINUE: return_function_skip_continue,
    C.SE_PIPELINE_CONTINUE: return_pipeline_continue,
    C.SE_PIPELINE_HALT: return_pipeline_halt,
    C.SE_PIPELINE_TERMINATE: return_pipeline_terminate,
    C.SE_PIPELINE_RESET: return_pipeline_reset,
    C.SE_PIPELINE_DISABLE: return_pipeline_disable,
    C.SE_PIPELINE_SKIP_CONTINUE: return_pipeline_skip_continue,
}
