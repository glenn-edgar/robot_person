-- ============================================================================
-- basic_primitive_test_user_functions.lua
-- LuaJIT translation of basic_primitive_test_user_functions.c
--
-- Provides:
--   M.register(mod)  -- register all functions with a mod (mirrors
--                    --   basic_primitive_test_register_all)
--
-- Shared state is accessed via inst.user_ctx, which must be a table:
--   inst.user_ctx = {
--       bitmap         = 0,   -- uint32: bit field that test_bit reads
--       trigger_events = 0,   -- uint32: bitmask of events fired this tick
--   }
--
-- The caller sets inst.user_ctx after new_instance() and before ticking,
-- mirroring the C pattern:
--   tree->user_ctx = &g_bitmap;
-- ============================================================================

local bit = require("bit")
local band, bor, lshift = bit.band, bit.bor, bit.lshift

local M = {}

-- ============================================================================
-- Event bit constants  (mirrors #define EVENT_BIT0_RISE etc. in C header)
-- Exported so test drivers can use the same names without redefining them.
-- ============================================================================

M.EVENT_BIT0_RISE   = lshift(1, 0)
M.EVENT_BIT0_FALL   = lshift(1, 1)
M.EVENT_BITS12_RISE = lshift(1, 2)
M.EVENT_BITS12_FALL = lshift(1, 3)
M.EVENT_BITS34_RISE = lshift(1, 4)
M.EVENT_BITS34_FALL = lshift(1, 5)
M.EVENT_BIT5_CLEAR  = lshift(1, 6)
M.EVENT_BIT5_SET    = lshift(1, 7)

-- ============================================================================
-- Oneshot actions  (o_call signature: fn(inst, node))
--
-- Each function ORs its event bit into inst.user_ctx.trigger_events and
-- prints the same diagnostic the C version prints.
-- ============================================================================

local function on_bit0_rise(inst, node)
    print("  >> ON_BIT0_RISE")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BIT0_RISE)
end

local function on_bit0_fall(inst, node)
    print("  >> ON_BIT0_FALL")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BIT0_FALL)
end

local function on_bits_12_rise(inst, node)
    print("  >> ON_BITS_12_RISE (bit1 AND bit2)")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BITS12_RISE)
end

local function on_bits_12_fall(inst, node)
    print("  >> ON_BITS_12_FALL (bit1 AND bit2)")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BITS12_FALL)
end

local function on_bits_34_rise(inst, node)
    print("  >> ON_BITS_34_RISE (bit3 OR bit4)")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BITS34_RISE)
end

local function on_bits_34_fall(inst, node)
    print("  >> ON_BITS_34_FALL (bit3 OR bit4)")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BITS34_FALL)
end

local function on_bit5_clear(inst, node)
    print("  >> ON_BIT5_CLEAR (NOT bit5 went true)")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BIT5_CLEAR)
end

local function on_bit5_set(inst, node)
    print("  >> ON_BIT5_SET (NOT bit5 went false)")
    inst.user_ctx.trigger_events = bor(inst.user_ctx.trigger_events, M.EVENT_BIT5_SET)
end

-- ============================================================================
-- Predicate: test_bit  (p_call signature: fn(inst, node) -> bool)
--
-- Reads the bit index from params[1] (1-based, mirrors C params[0].int_val).
-- Reads the bitmap from inst.user_ctx.bitmap (mirrors *(uint32_t*)inst->user_ctx).
--
-- C guards reproduced as Lua errors so failures are loud and traceable.
-- ============================================================================

local se_runtime  -- loaded lazily to avoid circular require at module level

local function test_bit(inst, node)
    se_runtime = se_runtime or require("se_runtime")

    assert(inst.user_ctx,        "test_bit: no user_ctx on inst")
    assert(inst.user_ctx.bitmap ~= nil, "test_bit: no bitmap in user_ctx")

    local bit_index = se_runtime.param_int(node, 1)   -- params[0].int_val in C
    assert(bit_index >= 0 and bit_index <= 31,
        string.format("test_bit: bit index out of range: %d", bit_index))

    return band(inst.user_ctx.bitmap, lshift(1, bit_index)) ~= 0
end

-- ============================================================================
-- Function table
-- Keys match the func_name strings the DSL compiler writes into module_data.
-- Names are case-insensitive in se_runtime.register_fns — keep them lowercase
-- here to match the conventional DSL output.
-- ============================================================================

local fns = {
    on_bit0_rise   = on_bit0_rise,
    on_bit0_fall   = on_bit0_fall,
    on_bits_12_rise = on_bits_12_rise,
    on_bits_12_fall = on_bits_12_fall,
    on_bits_34_rise = on_bits_34_rise,
    on_bits_34_fall = on_bits_34_fall,
    on_bit5_clear  = on_bit5_clear,
    on_bit5_set    = on_bit5_set,
    test_bit       = test_bit,
}

-- ============================================================================
-- register(mod)
-- Mirrors basic_primitive_test_register_all(s_expr_module_t* module).
-- Call this after se_runtime.new_module() and standard builtin registration,
-- before se_runtime.validate_module() / se_runtime.new_instance().
-- ============================================================================

function M.register(mod)
    local se = require("se_runtime")
    se.register_fns(mod, fns)
end

-- Also expose the raw function table for callers that prefer merge_fns style.
M.fns = fns

return M