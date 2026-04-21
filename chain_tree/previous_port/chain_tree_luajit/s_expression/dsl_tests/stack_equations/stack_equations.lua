-- stack_test_equations.lua
-- Test for stack frame and quad operations using expression compiler
-- Rewritten from stack_test.lua to use quad_expr / quad_pred / quad_multi

local mod = start_module("stack_equations")

-- ============================================================================
-- RECORD DEFINITION
-- ============================================================================

RECORD("stack_test_state")
    FIELD("int_val_1", "int32")
    FIELD("int_val_2", "int32")
    FIELD("int_val_3", "int32")
    FIELD("uint_val_1", "uint32")
    FIELD("uint_val_2", "uint32")
    FIELD("uint_val_3", "uint32")
    FIELD("float_val_1", "float")
    FIELD("float_val_2", "float")
    FIELD("float_val_3", "float")
    FIELD("loop_count", "uint32")
END_RECORD()

-- ============================================================================
-- TREE DEFINITION
-- ============================================================================

start_tree("stack_equations")
use_record("stack_test_state")

-- ============================================================================
-- ACTION 1: Integer quad operations with frame allocation
-- Loop 100 times, each iteration:
--   int_val_2 = int_val_1 + 1
--   int_val_2 = int_val_1 + 5
--   int_val_3 = int_val_2 - 2
--   int_val_1 = int_val_3
-- Net effect per iteration: int_val_1 += 3
-- ============================================================================

action_1 = function() se_fork_join(function()
    se_while(se_state_increment_and_test(1, 100), function()
        se_frame_allocate(0, 5, 5, function()
            local v = frame_vars(
                {"a:int", "b:int", "c:int", "d:int", "e:int"},
                {"t0:int", "t1:int", "t2:int", "t3:int", "t4:int"}
            )

            se_log("frame allocated started")
            se_tick_delay(5)

            se_log_slot_integer("int_val_1 %d", "int_val_1")

            -- int_val_2 = int_val_1 + 1
            quad_expr("@int_val_2 = @int_val_1 + 1", v, {"t0"})()
            se_log_slot_integer("int_val_2 %d", "int_val_2")

            -- int_val_2 = int_val_1 + 5
            quad_expr("@int_val_2 = @int_val_1 + 5", v, {"t0"})()
            se_log_slot_integer("int_val_2 %d", "int_val_2")

            -- int_val_3 = int_val_2 - 2
            quad_expr("@int_val_3 = @int_val_2 - 2", v, {"t0"})()
            se_log_slot_integer("int_val_3 %d", "int_val_3")

            -- int_val_1 = int_val_3
            quad_expr("@int_val_1 = @int_val_3", v, {})()
            se_log_slot_integer("int_val_1 %d", "int_val_1")

            se_log("frame allocated finished")
            se_return_pipeline_terminate()
        end)
    end)
end)
end

-- ============================================================================
-- ACTION 2: Float quad operations with frame allocation
-- Loop 10 times, each iteration:
--   float_val_2 = float_val_1 + 1.0
--   float_val_2 = float_val_1 + 5.0
--   float_val_3 = float_val_2 - 2.0
--   float_val_1 = float_val_3
-- Net effect per iteration: float_val_1 += 3.0
-- ============================================================================

action_2 = function() se_fork_join(function()
    se_while(se_state_increment_and_test(1, 10), function()
        se_frame_allocate(0, 5, 5, function()
            local v = frame_vars(
                {"a:float", "b:float", "c:float", "d:float", "e:float"},
                {"t0:float", "t1:float", "t2:float", "t3:float", "t4:float"}
            )

            se_log("frame allocated started")
            se_tick_delay(5)

            se_log_slot_float("float_val_1 %f", "float_val_1")

            -- float_val_2 = float_val_1 + 1.0
            quad_expr("@float_val_2 = @float_val_1 + 1.0", v, {"t0"})()
            se_log_slot_float("float_val_2 %f", "float_val_2")

            -- float_val_2 = float_val_1 + 5.0
            quad_expr("@float_val_2 = @float_val_1 + 5.0", v, {"t0"})()
            se_log_slot_float("float_val_2 %f", "float_val_2")

            -- float_val_3 = float_val_2 - 2.0
            quad_expr("@float_val_3 = @float_val_2 - 2.0", v, {"t0"})()
            se_log_slot_float("float_val_3 %f", "float_val_3")

            -- float_val_1 = float_val_3
            quad_expr("@float_val_1 = @float_val_3", v, {})()
            se_log_slot_float("float_val_1 %f", "float_val_1")

            se_log("frame allocated finished")
            se_return_pipeline_terminate()
        end)
    end)
end)
end

-- ============================================================================
-- ACTION 3: Full call/return integration test with expressions
-- Loop 10 times, each iteration:
--   Outer frame computes:
--     a = float_val_1 + 1.0
--     float_val_2 = a + 5.0
--     b = float_val_2
--     float_val_3 = b - 2.0
--     float_val_1 = float_val_3       (net: float_val_1 += 4.0)
--   Push float_val_1, float_val_2 as call parameters
--   Call computes:
--     r0 = (p0 + 1.0 + 5.0) - 2.0    (= p0 + 4.0)
--     r1 = p1 * 2.0
--   Pop return values, store to float_val_2 and float_val_3
-- ============================================================================

action_3 = function()
    se_fork_join(function()
        quad_mov(uint_val(0), field_val("loop_count"))()

        se_while(
            p_icmp_lt_acc(field_val("loop_count"), uint_val(10), field_val("loop_count")),
            function()
                se_frame_allocate(0, 5, 5, function()
                    local v = frame_vars(
                        {"a:float", "b:float", "c:float", "e:float", "f:float"},
                        {"t0:float", "t1:float", "t2:float", "t3:float", "t4:float"}
                    )

                    se_log("frame allocated started")
                    se_tick_delay(5)

                    -- Compute using quad_multi: three assignments in one call
                    se_log_slot_float("float_val_1 %f", "float_val_1")

                    quad_multi(
                        "a = @float_val_1 + 1.0; " ..
                        "@float_val_2 = a + 5.0; " ..
                        "b = @float_val_2",
                        v, {"t0", "t1"}
                    )()
                    se_log_slot_float("float_val_2 %f", "float_val_2")

                    -- float_val_3 = b - 2.0, then float_val_1 = float_val_3
                    quad_multi(
                        "@float_val_3 = b - 2.0; " ..
                        "@float_val_1 = @float_val_3",
                        v, {"t0"}
                    )()
                    se_log_slot_float("float_val_3 %f", "float_val_3")
                    se_log_slot_float("float_val_1 %f", "float_val_1")

                    -- Push 2 parameters for call
                    quad_mov(field_val("float_val_1"), stack_push_ref())()
                    quad_mov(field_val("float_val_2"), stack_push_ref())()

                    -- Call: 2 params, 2 locals, 3 scratch, return locals 2 and 3
                    se_call(2, 2, 3, {2, 3}, {
                        function()
                            local cv = frame_vars(
                                {"p0:float", "p1:float", "r0:float", "r1:float"},
                                {"ct0:float", "ct1:float", "ct2:float"}
                            )

                            -- r0 = (p0 + 1.0 + 5.0) - 2.0
                            quad_expr("r0 = (p0 + 1.0 + 5.0) - 2.0", cv, {"ct0", "ct1"})()

                            -- r1 = p1 * 2.0
                            quad_expr("r1 = p1 * 2.0", cv, {"ct0"})()

                            se_return_pipeline_terminate()
                        end
                    })

                    -- Pop return values (reverse order)
                    quad_mov(stack_pop_ref(), v.e)()
                    quad_mov(stack_pop_ref(), v.f)()

                    -- Store to blackboard
                    quad_mov(v.e, field_val("float_val_2"))()
                    quad_mov(v.f, field_val("float_val_3"))()

                    se_log_slot_float("call result float_val_2 %f", "float_val_2")
                    se_log_slot_float("call result float_val_3 %f", "float_val_3")

                    se_log("frame allocated finished")
                    se_return_pipeline_terminate()
                end)
            end
        )
    end)
end


se_function_interface(function()
    se_log_stack()
    quad_mov(uint_val(0), field_val("int_val_1"))()
    quad_mov(float_val(0), field_val("float_val_1"))()
    action_1()
    action_2()
    quad_mov(uint_val(0), field_val("int_val_1"))()
    quad_mov(float_val(0), field_val("float_val_1"))()
    action_3()

    se_log_stack()
    se_return_terminate()
end)

end_tree("stack_equations")

return end_module(mod)