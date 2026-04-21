-- stack_test.lua
-- Test for stack frame and quad operations

local mod = start_module("stack_test")

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

start_tree("stack_test")
use_record("stack_test_state")



action_1 = function() se_fork_join(function()
    
           se_while(se_state_increment_and_test(1, 100), function()
            se_frame_allocate(0, 5, 5, function()
                --se_log_stack()
                se_log("frame allocated started")
                se_tick_delay(5)
                se_log_slot_integer("int_val_1 %d", "int_val_1")
                quad_iadd(field_val("int_val_1"), float_val(1), field_val("int_val_2"))()
                se_log_slot_integer("int_val_2 %d", "int_val_2")
                quad_iadd(field_val("int_val_1"), uint_val(5), field_val("int_val_2"))()
                se_log_slot_integer("int_val_2 %d", "int_val_2")
                quad_isub(field_val("int_val_2"), float_val(2), field_val("int_val_3"))()
                se_log_slot_integer("int_val_3 %d", "int_val_3")
                quad_mov(field_val("int_val_3"), field_val("int_val_1"))()
                se_log_slot_integer("int_val_1 %d", "int_val_1")
                --se_log_stack()
                se_log("frame allocated finished")
                se_return_pipeline_terminate()
            end)
        end)
    end)
end
action_2 = function() se_fork_join(function()
    se_while(se_state_increment_and_test(1, 10), function()
     se_frame_allocate(0, 5, 5, function()
         --se_log_stack()
         se_log("frame allocated started")
         se_tick_delay(5)
         se_log_slot_float("float_val_1 %f", "float_val_1")
         quad_fadd(field_val("float_val_1"), float_val(1), field_val("float_val_2"))()
         se_log_slot_float("float_val_2 %f", "float_val_2")
         quad_fadd(field_val("float_val_1"), float_val(5), field_val("float_val_2"))()
         se_log_slot_float("float_val_2 %f", "float_val_2")
         quad_fsub(field_val("float_val_2"), uint_val(2), field_val("float_val_3"))()
         se_log_slot_float("float_val_3 %f", "float_val_3")
         quad_mov(field_val("float_val_3"), field_val("float_val_1"))()
         se_log_slot_float("float_val_1 %f", "float_val_1")
         --se_log_stack()
         se_log("frame allocated finished")
         se_return_pipeline_terminate()
     end)
 end)
end)
end

action_3 = function() se_fork_join(function()
    
    quad_mov(uint_val(0), field_val("loop_count"))()
    se_while(p_icmp_lt_acc(field_val("loop_count"), uint_val(10), field_val("loop_count")), function()
        se_frame_allocate(0, 5, 5, function()
            local v =frame_vars({"a","b","c","e","f"},{"ts_a","ts_b","ts_c","ts_e","ts_f"})
            --se_log_stack()
            se_log("frame allocated started")
            se_tick_delay(5)
            se_log_slot_float("float_val_1 %f", "float_val_1")
            quad_fadd(field_val("float_val_1"), float_val(1), v.a)()
            quad_fadd(v.a, float_val(5), field_val("float_val_2"))()
            quad_mov(field_val("float_val_2"), v.b)()
            se_log_slot_float("float_val_2 %f", "float_val_2")
            quad_fsub(v.b, uint_val(2), field_val("float_val_3"))()
            quad_mov(field_val("float_val_3"), v.ts_a)()
            se_log_slot_float("float_val_3 %f", "float_val_3")
            quad_mov(v.ts_a, field_val("float_val_1"))()
            se_log_slot_float("float_val_1 %f", "float_val_1")
            --se_log_stack()
            se_log("frame allocated finished")
            se_return_pipeline_terminate()
        end)
    end)
end)
end

action_3 = function()
    se_fork_join(function()
        quad_mov(uint_val(0), field_val("loop_count"))()

        se_while(
            p_icmp_lt_acc(field_val("loop_count"), uint_val(10), field_val("loop_count")),
            function()
                se_frame_allocate(0, 5, 5, function()
                    local v = frame_vars(
                        {"a", "b", "c", "e", "f"},
                        {"t0", "t1", "t2", "t3", "t4"}
                    )

                    se_log("frame allocated started")
                    se_tick_delay(5)

                    -- a = float_val_1 + 1.0
                    quad_fadd(field_val("float_val_1"), float_val(1.0), v.a)()
                    -- float_val_2 = a + 5.0
                    quad_fadd(v.a, float_val(5.0), field_val("float_val_2"))()
                    se_log_slot_float("float_val_2 %f", "float_val_2")

                    -- float_val_3 = float_val_2 - 2.0
                    quad_mov(field_val("float_val_2"), v.b)()
                    quad_fsub(v.b, float_val(2.0), field_val("float_val_3"))()
                    se_log_slot_float("float_val_3 %f", "float_val_3")

                    -- float_val_1 = float_val_3
                    quad_mov(field_val("float_val_3"), field_val("float_val_1"))()
                    se_log_slot_float("float_val_1 %f", "float_val_1")

                    -- Push 2 parameters for call
                    quad_mov(field_val("float_val_1"), stack_push_ref())()
                    quad_mov(field_val("float_val_2"), stack_push_ref())()
                   
                    -- Call: 2 params, 2 locals, 3 scratch, return locals 2 and 3
                    se_call(2, 2, 3, {2, 3}, {
                        function()
                            local cv = frame_vars(
                                {"p0", "p1", "r0", "r1"},
                                {"ct0", "ct1", "ct2"}
                            )

                            -- r0 = (p0 + 1.0 + 5.0) - 2.0
                            quad_fadd(cv.p0, float_val(1.0), cv.ct0)()
                            quad_fadd(cv.ct0, float_val(5.0), cv.ct1)()
                            quad_fsub(cv.ct1, float_val(2.0), cv.r0)()

                            -- r1 = p1 * 2.0
                            quad_fmul(cv.p1, float_val(2.0), cv.r1)()
                            se_return_pipeline_terminate()
                            -- Debug: copy r0 and r1 to blackboard to verify
                            
                            
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
    quad_mov(uint_val(0),field_val("int_val_1"))()
    quad_mov(float_val(0),field_val("float_val_1"))()
    action_1()
    action_2()
    quad_mov(uint_val(0),field_val("int_val_1"))()
    quad_mov(float_val(0),field_val("float_val_1"))()
    action_3()

    se_log_stack()
    se_return_terminate()
end)

end_tree("stack_test")

return end_module(mod)