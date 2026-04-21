-- ============================================================================
-- se_builtins_stack.lua
-- Mirrors s_engine_builtins_stack.h
--
-- Stack frame management functions.
-- Requires inst.stack to be initialised (se_stack.new_stack(capacity)).
-- ============================================================================

local se_runtime = require("se_runtime")
local se_stack   = require("se_stack")

local SE_EVENT_INIT          = se_runtime.SE_EVENT_INIT
local SE_EVENT_TERMINATE     = se_runtime.SE_EVENT_TERMINATE
local SE_EVENT_TICK          = se_runtime.SE_EVENT_TICK
local SE_PIPELINE_CONTINUE   = se_runtime.SE_PIPELINE_CONTINUE
local SE_PIPELINE_DISABLE    = se_runtime.SE_PIPELINE_DISABLE
local SE_PIPELINE_TERMINATE  = se_runtime.SE_PIPELINE_TERMINATE
local SE_PIPELINE_RESET      = se_runtime.SE_PIPELINE_RESET
local SE_PIPELINE_HALT       = se_runtime.SE_PIPELINE_HALT
local SE_PIPELINE_SKIP_CONTINUE = se_runtime.SE_PIPELINE_SKIP_CONTINUE
local SE_FUNCTION_HALT       = se_runtime.SE_FUNCTION_HALT

local get_ns               = se_runtime.get_ns
local param_int            = se_runtime.param_int
local child_count          = se_runtime.child_count
local child_terminate      = se_runtime.child_terminate
local children_terminate_all = se_runtime.children_terminate_all
local children_reset_all   = se_runtime.children_reset_all
local invoke_oneshot       = se_runtime.invoke_oneshot
local invoke_pred          = se_runtime.invoke_pred
local invoke_any           = se_runtime.invoke_any
local get_state            = se_runtime.get_state
local set_state            = se_runtime.set_state

local bit  = require("bit")
local band = bit.band

local FLAG_ACTIVE      = 0x01
local FLAG_INITIALIZED = 0x02

local M = {}

-- ----------------------------------------------------------------------------
-- SE_FRAME_ALLOCATE  (m_call)
-- Custom parallel orchestrator with stack frame lifecycle management.
-- params[1] = uint  num_params
-- params[2] = uint  num_locals
-- params[3] = uint  scratch_depth
-- children[0..N-1] = body callables (0-based)
--
-- INIT:     SE_PIPELINE_CONTINUE (no-op; frame pushed on TICK)
-- TERMINATE: terminate all children
-- TICK:
--   push frame, push scratch slots
--   execute each callable child:
--     oneshot/pred : invoke + terminate (don't count as active)
--     main FUNCTION_HALT   -> pop frame, return PIPELINE_HALT
--     main < PIPELINE_CONTINUE -> pop frame, propagate
--     main PIPELINE_CONTINUE   -> active_count++
--     main PIPELINE_HALT       -> pop frame, return PIPELINE_CONTINUE
--     main PIPELINE_DISABLE    -> terminate child
--     main PIPELINE_TERMINATE  -> terminate all, pop frame, propagate
--     main PIPELINE_RESET      -> terminate+reset all, pop frame, CONTINUE
--     main PIPELINE_SKIP_CONTINUE -> active_count++, break loop
--   pop frame; PIPELINE_DISABLE when active_count==0
-- ----------------------------------------------------------------------------
M.se_frame_allocate = function(inst, node, event_id, event_data)
    local stk = inst.stack
    assert(stk, "se_frame_allocate: no stack on instance")

    if event_id == SE_EVENT_TERMINATE then
        children_terminate_all(inst, node)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_INIT then
        return SE_PIPELINE_CONTINUE
    end

    -- TICK
    assert(#(node.params or {}) >= 3,
        "se_frame_allocate: requires [num_params] [num_locals] [scratch_depth]")

    local num_params    = param_int(node, 1)
    local num_locals    = param_int(node, 2)
    local scratch_depth = param_int(node, 3)
    local children      = node.children or {}

    -- Push stack frame BEFORE executing children
    assert(se_stack.push_frame(stk, num_params, num_locals),
        "se_frame_allocate: stack push failed")

    for _ = 1, scratch_depth do
        se_stack.push_int(stk, 0)
    end

    local active_count = 0

    -- Iterate from child index 3 (0-based) to skip the 3 uint params.
    -- In the Lua tree model params are already separate, so start from 0.
    -- However the C iterates logical children starting at index 3 to skip
    -- the 3 uint non-callable params. In Lua, node.children contains ONLY
    -- callables, so we start from 0.
    for i = 1, #children do
        local child = children[i]
        local ct    = child.call_type

        -- Skip inactive MAIN nodes
        if (ct == "m_call" or ct == "pt_m_call") then
            if band(get_ns(inst, child.node_index).flags, FLAG_ACTIVE) == 0 then
                goto continue_child
            end
        end

        -- ONESHOT -- fire, terminate (don't count as active)
        if ct == "o_call" or ct == "io_call" then
            invoke_oneshot(inst, child)
            child_terminate(inst, node, i - 1)
            goto continue_child
        end

        -- PRED -- evaluate, terminate (don't count as active)
        if ct == "p_call" or ct == "p_call_composite" then
            invoke_pred(inst, child)
            child_terminate(inst, node, i - 1)
            goto continue_child
        end

        -- MAIN -- invoke and handle result
        do
            local r = invoke_any(inst, child, event_id, event_data)

            if r == SE_FUNCTION_HALT then
                se_stack.pop_frame(stk)
                return SE_PIPELINE_HALT
            end

            if r < SE_PIPELINE_CONTINUE then
                -- Non-pipeline result: propagate immediately
                se_stack.pop_frame(stk)
                return r
            end

            if r == SE_PIPELINE_CONTINUE then
                active_count = active_count + 1

            elseif r == SE_PIPELINE_HALT then
                se_stack.pop_frame(stk)
                return SE_PIPELINE_CONTINUE

            elseif r == SE_PIPELINE_DISABLE then
                child_terminate(inst, node, i - 1)

            elseif r == SE_PIPELINE_TERMINATE then
                children_terminate_all(inst, node)
                se_stack.pop_frame(stk)
                return SE_PIPELINE_TERMINATE

            elseif r == SE_PIPELINE_RESET then
                children_terminate_all(inst, node)
                children_reset_all(inst, node)
                se_stack.pop_frame(stk)
                return SE_PIPELINE_CONTINUE

            elseif r == SE_PIPELINE_SKIP_CONTINUE then
                active_count = active_count + 1
                -- goto tick_complete (break out of loop)
                se_stack.pop_frame(stk)
                return (active_count == 0) and SE_PIPELINE_DISABLE or SE_PIPELINE_CONTINUE

            else
                active_count = active_count + 1
            end
        end

        ::continue_child::
    end

    -- tick_complete:
    se_stack.pop_frame(stk)
    return (active_count == 0) and SE_PIPELINE_DISABLE or SE_PIPELINE_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_FRAME_FREE  (m_call)
-- Pops the top stack frame on SE_EVENT_INIT only.
-- All other events return SE_PIPELINE_CONTINUE immediately.
--
-- C source note: the C code has an early-return for non-INIT, making the
-- TERMINATE branch unreachable. The Lua translation faithfully reproduces
-- this: only INIT pops the frame.
-- ----------------------------------------------------------------------------
M.se_frame_free = function(inst, node, event_id, event_data)
    -- C: if (event_type != SE_EVENT_INIT) return SE_PIPELINE_CONTINUE
    if event_id ~= SE_EVENT_INIT then
        return SE_PIPELINE_CONTINUE
    end

    -- event_id == SE_EVENT_INIT: pop the frame
    if inst.stack then
        se_stack.pop_frame(inst.stack)
    end

    return SE_PIPELINE_CONTINUE
end

-- ----------------------------------------------------------------------------
-- SE_LOG_STACK  (oneshot: fn(inst, node))
-- Diagnostic: prints current stack state.
-- ----------------------------------------------------------------------------
M.se_log_stack = function(inst, node)
    local stk = inst.stack
    if not stk then
        print("SE_LOG_STACK: no stack on instance")
        return
    end

    print(string.format("SE_LOG_STACK: stack capacity = %d",   stk.capacity))
    print(string.format("SE_LOG_STACK: stack free space = %d", stk.capacity - stk.sp))
    print(string.format("SE_LOG_STACK: stack stack pointer = %d", stk.sp))
    print(string.format("SE_LOG_STACK: stack frame count = %d",   stk.frame_count))

    if stk.frame_count > 0 then
        local f = stk.frames[stk.frame_count]
        print(string.format("SE_LOG_STACK: stack frame base ptr = %d",    f.base_ptr))
        print(string.format("SE_LOG_STACK: stack frame num params = %d",  f.num_params))
        print(string.format("SE_LOG_STACK: stack frame num locals = %d",  f.num_locals))
        print(string.format("SE_LOG_STACK: stack frame scratch base = %d",f.scratch_base))
    end
end

-- ----------------------------------------------------------------------------
-- SE_STACK_FRAME_INSTANCE  (m_call)
-- Stack frame lifecycle manager; called by the se_call wrapper.
-- params[1] = uint  num_params  (expected params already on stack)
-- params[2] = uint  num_locals
-- params[3] = uint  scratch_depth  (compile-time only; unused at runtime)
-- params[4] = list  return_vars    (local indices to copy back on TERMINATE)
--
-- On INIT:
--   Pop param count pushed by se_call wrapper, validate, push frame.
-- On TICK:
--   SE_PIPELINE_CONTINUE (frame stays alive, body runs in sibling nodes)
-- On TERMINATE:
--   Copy return vars from locals, pop frame.
--
-- State: ns.state 0=not_init, 1=frame_active
-- ----------------------------------------------------------------------------
M.se_stack_frame_instance = function(inst, node, event_id, event_data)
    local stk = inst.stack
    assert(stk, "se_stack_frame_instance: no stack on instance")

    local num_params = param_int(node, 1)
    local num_locals = param_int(node, 2)

    -- TERMINATE: copy return vars, pop frame
    if event_id == SE_EVENT_TERMINATE then
        if get_state(inst, node) == 1 then
            -- Collect return var values before frame is destroyed
            local ret_list = (node.params or {})[4]
            if ret_list and ret_list.type == "list_start" then
                local temps = {}
                for _, rp in ipairs(ret_list.items or {}) do
                    local local_idx = rp.value
                    temps[#temps + 1] = se_stack.get_local(stk, local_idx)
                end
                se_stack.pop_frame(stk)
                for _, v in ipairs(temps) do
                    se_stack.push(stk, v)
                end
            else
                se_stack.pop_frame(stk)
            end
        end
        set_state(inst, node, 0)
        return SE_PIPELINE_CONTINUE
    end

    -- INIT: validate arity, push frame
    if event_id == SE_EVENT_INIT then
        -- se_call wrapper pushes param count before INIT
        local passed = se_stack.pop(stk)
        passed = passed or 0

        if passed ~= num_params then
            error(string.format(
                "se_stack_frame_instance: param mismatch: expected %d got %d",
                num_params, passed))
        end

        assert(se_stack.push_frame(stk, num_params, num_locals),
            "se_stack_frame_instance: frame push failed")

        set_state(inst, node, 1)
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: frame stays active
    return SE_PIPELINE_CONTINUE
end

return M