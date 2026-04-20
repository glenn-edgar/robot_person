from se_runtime import codes as C


def test_exact_values_match_luajit():
    assert C.SE_CONTINUE == 0
    assert C.SE_SKIP_CONTINUE == 5
    assert C.SE_FUNCTION_CONTINUE == 6
    assert C.SE_FUNCTION_SKIP_CONTINUE == 11
    assert C.SE_PIPELINE_CONTINUE == 12
    assert C.SE_PIPELINE_SKIP_CONTINUE == 17


def test_family_membership():
    assert C.is_application(C.SE_DISABLE)
    assert C.is_function(C.SE_FUNCTION_HALT)
    assert C.is_pipeline(C.SE_PIPELINE_RESET)
    assert not C.is_application(C.SE_PIPELINE_CONTINUE)


def test_variant_and_family_crossings():
    assert C.variant(C.SE_PIPELINE_HALT) == 1
    assert C.to_pipeline(C.SE_FUNCTION_HALT) == C.SE_PIPELINE_HALT
    assert C.to_function(C.SE_PIPELINE_HALT) == C.SE_FUNCTION_HALT
    assert C.to_application(C.SE_PIPELINE_DISABLE) == C.SE_DISABLE


def test_code_names():
    assert C.code_name(C.SE_PIPELINE_DISABLE) == "SE_PIPELINE_DISABLE"
    assert C.code_name(C.SE_FUNCTION_HALT) == "SE_FUNCTION_HALT"
    assert C.code_name(C.SE_RESET) == "SE_RESET"


def test_reserved_event_ids():
    assert C.is_reserved_event("init")
    assert C.is_reserved_event("tick")
    assert C.is_reserved_event("terminate")
    assert not C.is_reserved_event("sensor.temp.updated")
