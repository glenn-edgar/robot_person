-- ============================================================================
-- se_stack.lua
-- Call-stack implementation for ChainTree s-expression engine.
-- Mirrors the s_expr_stack_t C structure.
--
-- Stack entries are plain Lua values (numbers, strings, nil).
-- Frames provide param and local variable windows.
--
-- API:
--   local stk = se_stack.new_stack(capacity)
--   se_stack.push(stk, value)
--   se_stack.push_int(stk, n)
--   local v = se_stack.pop(stk)         → value or nil
--   local v = se_stack.peek_tos(stk, offset)
--   se_stack.poke(stk, offset, value)
--   se_stack.push_frame(stk, num_params, num_locals) → bool
--   se_stack.pop_frame(stk)
--   local v = se_stack.get_local(stk, local_idx)
--   se_stack.set_local(stk, local_idx, value)
-- ============================================================================

local M = {}

-- Create a new stack with given capacity
function M.new_stack(capacity)
    return {
        data        = {},           -- 1-based; index 1..sp
        sp          = 0,            -- next free slot (0 = empty)
        capacity    = capacity,
        frames      = {},           -- 1-based array of frame records
        frame_count = 0,
    }
end

-- Push a value
function M.push(stk, value)
    assert(stk.sp < stk.capacity, "se_stack: push overflow")
    stk.sp = stk.sp + 1
    stk.data[stk.sp] = value
end

-- Push an integer (alias for clarity)
function M.push_int(stk, n)
    M.push(stk, n)
end

-- Pop a value (returns nil on empty)
function M.pop(stk)
    if stk.sp == 0 then return nil end
    local v = stk.data[stk.sp]
    stk.data[stk.sp] = nil
    stk.sp = stk.sp - 1
    return v
end

-- Peek at TOS - offset (offset=0 → top of stack)
function M.peek_tos(stk, offset)
    local idx = stk.sp - offset
    if idx < 1 then return nil end
    return stk.data[idx]
end

-- Overwrite a slot relative to TOS (offset=0 → top)
function M.poke(stk, offset, value)
    local idx = stk.sp - offset
    if idx >= 1 then stk.data[idx] = value end
end

-- ============================================================================
-- Frame management
-- Frame layout in data[]:
--   [base_ptr+1 .. base_ptr+num_params]   = params  (already on stack)
--   [base_ptr+num_params+1 .. base_ptr+num_params+num_locals] = locals (zeroed)
-- sp is advanced past locals after push.
-- ============================================================================

-- Push a new frame.  Returns false if capacity exceeded.
function M.push_frame(stk, num_params, num_locals)
    -- base_ptr is the index BELOW the first param (0-based for frame math)
    local base_ptr = stk.sp - num_params

    -- Verify params are actually on the stack
    if base_ptr < 0 then return false end

    -- Allocate locals (zeroed)
    for _ = 1, num_locals do
        if stk.sp >= stk.capacity then return false end
        stk.sp = stk.sp + 1
        stk.data[stk.sp] = 0
    end

    stk.frame_count = stk.frame_count + 1
    stk.frames[stk.frame_count] = {
        base_ptr     = base_ptr,
        num_params   = num_params,
        num_locals   = num_locals,
        scratch_base = stk.sp,   -- scratch starts above locals
        saved_sp     = stk.sp,   -- sp after locals (used by pop to restore)
    }

    return true
end

-- Pop the top frame, restoring sp to before params.
function M.pop_frame(stk)
    if stk.frame_count == 0 then return end
    local f = stk.frames[stk.frame_count]
    -- Restore sp to before params
    stk.sp = f.base_ptr
    stk.frames[stk.frame_count] = nil
    stk.frame_count = stk.frame_count - 1
end

-- Get local variable value (0-based local_idx within current frame)
function M.get_local(stk, local_idx)
    if stk.frame_count == 0 then return nil end
    local f = stk.frames[stk.frame_count]
    local idx = f.base_ptr + f.num_params + local_idx + 1  -- 1-based data[]
    if idx > stk.sp then return nil end
    return stk.data[idx]
end

-- Set local variable value (0-based local_idx within current frame)
function M.set_local(stk, local_idx, value)
    if stk.frame_count == 0 then return end
    local f = stk.frames[stk.frame_count]
    local idx = f.base_ptr + f.num_params + local_idx + 1
    if idx <= stk.capacity then
        stk.data[idx] = value
        if idx > stk.sp then stk.sp = idx end
    end
end

-- Get param value (0-based param_idx within current frame)
function M.get_param(stk, param_idx)
    if stk.frame_count == 0 then return nil end
    local f = stk.frames[stk.frame_count]
    local idx = f.base_ptr + param_idx + 1
    return stk.data[idx]
end

return M