-- ============================================================================
-- se_builtins_quads.lua
-- Mirrors s_engine_builtins_quads.h
--
-- Three-address arithmetic/logical instructions.
--
-- SE_QUAD   (oneshot):  fn(inst, node)          -- dest = op(src1, src2)
-- SE_P_QUAD (pred):     fn(inst, node) -> bool  -- dest = op(...); return dest != 0
--
-- Parameter layout (1-based Lua params, all non-callable):
--   params[1] = uint   opcode
--   params[2] = src1   (field_ref | int | uint | float | stack_tos | stack_local | stack_pop | const_ref)
--   params[3] = src2   (same, or null for unary)
--   params[4] = dest   (field_ref | stack_tos | stack_local | stack_push)
-- ============================================================================

local se_runtime = require("se_runtime")

local bit   = require("bit")
local band, bor, bxor, bnot = bit.band, bit.bor, bit.bxor, bit.bnot
local lshift, rshift = bit.lshift, bit.rshift

-- ============================================================================
-- Opcode constants (match SE_QUAD_* / SE_P_QUAD_* C defines exactly)
-- ============================================================================
local OP = {
    -- Integer arithmetic
    IADD=0x00, ISUB=0x01, IMUL=0x02, IDIV=0x03, IMOD=0x04, INEG=0x05,
    -- Float arithmetic
    FADD=0x08, FSUB=0x09, FMUL=0x0A, FDIV=0x0B, FMOD=0x0C, FNEG=0x0D,
    -- Bitwise
    BIT_AND=0x10, BIT_OR=0x11, BIT_XOR=0x12, BIT_NOT=0x13,
    BIT_SHL=0x14, BIT_SHR=0x15,
    -- Integer comparison
    ICMP_EQ=0x20, ICMP_NE=0x21, ICMP_LT=0x22, ICMP_LE=0x23,
    ICMP_GT=0x24, ICMP_GE=0x25,
    -- Float comparison
    FCMP_EQ=0x28, FCMP_NE=0x29, FCMP_LT=0x2A, FCMP_LE=0x2B,
    FCMP_GT=0x2C, FCMP_GE=0x2D,
    -- Logical
    LOG_AND=0x30, LOG_OR=0x31, LOG_NOT=0x32,
    LOG_NAND=0x33, LOG_NOR=0x34, LOG_XOR=0x35,
    -- Move
    MOVE=0x40, MOV=0x6E,
    -- Float math
    FSQRT=0x50, FPOW=0x51, FEXP=0x52, FLOG=0x53,
    FLOG10=0x54, FLOG2=0x55, FABS=0x56,
    FSIN=0x58, FCOS=0x59, FTAN=0x5A,
    FASIN=0x5B, FACOS=0x5C, FATAN=0x5D, FATAN2=0x5E,
    FSINH=0x60, FCOSH=0x61, FTANH=0x62,
    -- Integer math
    IABS=0x68, IMIN=0x69, IMAX=0x6A,
    FMIN=0x6C, FMAX=0x6D,
    -- SE_P_QUAD accumulate variants
    P_ICMP_EQ_ACC=0x40, P_ICMP_NE_ACC=0x41, P_ICMP_LT_ACC=0x42,
    P_ICMP_LE_ACC=0x43, P_ICMP_GT_ACC=0x44, P_ICMP_GE_ACC=0x45,
    P_FCMP_EQ_ACC=0x48, P_FCMP_NE_ACC=0x49, P_FCMP_LT_ACC=0x4A,
    P_FCMP_LE_ACC=0x4B, P_FCMP_GT_ACC=0x4C, P_FCMP_GE_ACC=0x4D,
}

-- ============================================================================
-- Read integer operand from a param entry
-- Mirrors quad_read_int in C
-- ============================================================================
local function read_int(inst, p)
    if not p then return 0 end
    local t = p.type
    if t == "int"  then return p.value
    elseif t == "uint"  then return p.value
    elseif t == "float" then return math.floor(p.value)
    elseif t == "field_ref" or t == "nested_field_ref" then
        return inst.blackboard[p.value] or 0
    elseif t == "stack_tos" then
        local stk = inst.stack
        if stk then
            return require("se_stack").peek_tos(stk, p.value or 0) or 0
        end
        return 0
    elseif t == "stack_local" then
        local stk = inst.stack
        if stk then
            return require("se_stack").get_local(stk, p.value or 0) or 0
        end
        return 0
    elseif t == "stack_pop" then
        local stk = inst.stack
        if stk then
            return require("se_stack").pop(stk) or 0
        end
        return 0
    elseif t == "const_ref" then
        local consts = inst.mod.module_data and inst.mod.module_data.constants
        if consts and p.value then
            local v = consts[p.value]
            if v ~= nil then
                return type(v) == "number" and math.floor(v) or 0
            end
        end
        return 0
    end
    return 0
end

-- ============================================================================
-- Read float operand from a param entry
-- Mirrors quad_read_float in C
-- ============================================================================
local function read_float(inst, p)
    if not p then return 0.0 end
    local t = p.type
    if t == "float" then return p.value
    elseif t == "int"  then return p.value + 0.0
    elseif t == "uint" then return p.value + 0.0
    elseif t == "field_ref" or t == "nested_field_ref" then
        return (inst.blackboard[p.value] or 0) + 0.0
    elseif t == "stack_tos" then
        local stk = inst.stack
        if stk then
            return (require("se_stack").peek_tos(stk, p.value or 0) or 0) + 0.0
        end
        return 0.0
    elseif t == "stack_local" then
        local stk = inst.stack
        if stk then
            return (require("se_stack").get_local(stk, p.value or 0) or 0) + 0.0
        end
        return 0.0
    elseif t == "stack_pop" then
        local stk = inst.stack
        if stk then
            return (require("se_stack").pop(stk) or 0) + 0.0
        end
        return 0.0
    elseif t == "const_ref" then
        local consts = inst.mod.module_data and inst.mod.module_data.constants
        if consts and p.value then
            local v = consts[p.value]
            if v ~= nil then return v + 0.0 end
        end
        return 0.0
    end
    return 0.0
end

-- ============================================================================
-- Write integer result to dest param
-- Mirrors quad_write_int in C
-- ============================================================================
local function write_int(inst, p, val)
    if not p then return end
    local t = p.type
    if t == "field_ref" or t == "nested_field_ref" then
        inst.blackboard[p.value] = val
    elseif t == "stack_tos" then
        local stk = inst.stack
        if stk then require("se_stack").poke(stk, p.value or 0, val) end
    elseif t == "stack_local" then
        local stk = inst.stack
        if stk then require("se_stack").set_local(stk, p.value or 0, val) end
    elseif t == "stack_push" then
        local stk = inst.stack
        if stk then require("se_stack").push_int(stk, val) end
    end
end

-- ============================================================================
-- Write float result to dest param
-- Mirrors quad_write_float in C
-- ============================================================================
local function write_float(inst, p, val)
    if not p then return end
    local t = p.type
    if t == "field_ref" or t == "nested_field_ref" then
        inst.blackboard[p.value] = val
    elseif t == "stack_tos" then
        local stk = inst.stack
        if stk then require("se_stack").poke(stk, p.value or 0, val) end
    elseif t == "stack_local" then
        local stk = inst.stack
        if stk then require("se_stack").set_local(stk, p.value or 0, val) end
    elseif t == "stack_push" then
        local stk = inst.stack
        if stk then require("se_stack").push(stk, val) end
    end
end

-- ============================================================================
-- Execute one quad instruction; return integer result for predicate check
-- ============================================================================
local function exec_quad(inst, opcode, src1p, src2p, destp)
    local i1, i2, f1, f2, r

    -- Integer arithmetic
    if opcode==OP.IADD then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=i1+i2; write_int(inst,destp,r); return r
    elseif opcode==OP.ISUB then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=i1-i2; write_int(inst,destp,r); return r
    elseif opcode==OP.IMUL then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=i1*i2; write_int(inst,destp,r); return r
    elseif opcode==OP.IDIV then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i2~=0) and math.floor(i1/i2) or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.IMOD then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i2~=0) and (i1%i2) or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.INEG then i1=read_int(inst,src1p); r=-i1; write_int(inst,destp,r); return r

    -- Float arithmetic
    elseif opcode==OP.FADD then f1=read_float(inst,src1p); f2=read_float(inst,src2p); write_float(inst,destp,f1+f2); return (f1+f2~=0) and 1 or 0
    elseif opcode==OP.FSUB then f1=read_float(inst,src1p); f2=read_float(inst,src2p); write_float(inst,destp,f1-f2); return (f1-f2~=0) and 1 or 0
    elseif opcode==OP.FMUL then f1=read_float(inst,src1p); f2=read_float(inst,src2p); write_float(inst,destp,f1*f2); return (f1*f2~=0) and 1 or 0
    elseif opcode==OP.FDIV then f1=read_float(inst,src1p); f2=read_float(inst,src2p); local v=(f2~=0) and f1/f2 or 0.0; write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FMOD then f1=read_float(inst,src1p); f2=read_float(inst,src2p); local v=(f2~=0) and math.fmod(f1,f2) or 0.0; write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FNEG then f1=read_float(inst,src1p); write_float(inst,destp,-f1); return (-f1~=0) and 1 or 0

    -- Bitwise
    elseif opcode==OP.BIT_AND then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=band(i1,i2); write_int(inst,destp,r); return r
    elseif opcode==OP.BIT_OR  then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=bor(i1,i2);  write_int(inst,destp,r); return r
    elseif opcode==OP.BIT_XOR then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=bxor(i1,i2); write_int(inst,destp,r); return r
    elseif opcode==OP.BIT_NOT then i1=read_int(inst,src1p); r=bnot(i1); write_int(inst,destp,r); return r
    elseif opcode==OP.BIT_SHL then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=lshift(i1,band(i2,0x1F)); write_int(inst,destp,r); return r
    elseif opcode==OP.BIT_SHR then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=rshift(i1,band(i2,0x1F)); write_int(inst,destp,r); return r

    -- Integer comparison
    elseif opcode==OP.ICMP_EQ then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1==i2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.ICMP_NE then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1~=i2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.ICMP_LT then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1< i2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.ICMP_LE then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1<=i2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.ICMP_GT then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1> i2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.ICMP_GE then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1>=i2) and 1 or 0; write_int(inst,destp,r); return r

    -- Float comparison (write int result)
    elseif opcode==OP.FCMP_EQ then f1=read_float(inst,src1p); f2=read_float(inst,src2p); r=(f1==f2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.FCMP_NE then f1=read_float(inst,src1p); f2=read_float(inst,src2p); r=(f1~=f2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.FCMP_LT then f1=read_float(inst,src1p); f2=read_float(inst,src2p); r=(f1< f2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.FCMP_LE then f1=read_float(inst,src1p); f2=read_float(inst,src2p); r=(f1<=f2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.FCMP_GT then f1=read_float(inst,src1p); f2=read_float(inst,src2p); r=(f1> f2) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.FCMP_GE then f1=read_float(inst,src1p); f2=read_float(inst,src2p); r=(f1>=f2) and 1 or 0; write_int(inst,destp,r); return r

    -- Logical
    elseif opcode==OP.LOG_AND  then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1~=0 and i2~=0) and 1 or 0;   write_int(inst,destp,r); return r
    elseif opcode==OP.LOG_OR   then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1~=0 or  i2~=0) and 1 or 0;   write_int(inst,destp,r); return r
    elseif opcode==OP.LOG_NOT  then i1=read_int(inst,src1p); r=(i1==0) and 1 or 0;                                       write_int(inst,destp,r); return r
    elseif opcode==OP.LOG_NAND then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=not(i1~=0 and i2~=0) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.LOG_NOR  then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=not(i1~=0 or  i2~=0) and 1 or 0; write_int(inst,destp,r); return r
    elseif opcode==OP.LOG_XOR  then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=((i1~=0)~=(i2~=0)) and 1 or 0;  write_int(inst,destp,r); return r

    -- Move
    elseif opcode==OP.MOVE or opcode==OP.MOV then
        i1=read_int(inst,src1p); write_int(inst,destp,i1); return i1

    -- Float math
    elseif opcode==OP.FSQRT  then f1=read_float(inst,src1p); write_float(inst,destp,math.sqrt(f1)); return (math.sqrt(f1)~=0) and 1 or 0
    elseif opcode==OP.FPOW   then f1=read_float(inst,src1p); f2=read_float(inst,src2p); write_float(inst,destp,f1^f2); return (f1^f2~=0) and 1 or 0
    elseif opcode==OP.FEXP   then f1=read_float(inst,src1p); write_float(inst,destp,math.exp(f1)); return (math.exp(f1)~=0) and 1 or 0
    elseif opcode==OP.FLOG   then f1=read_float(inst,src1p); write_float(inst,destp,math.log(f1)); return (math.log(f1)~=0) and 1 or 0
    elseif opcode==OP.FLOG10 then f1=read_float(inst,src1p); local v=math.log(f1,10); write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FLOG2  then f1=read_float(inst,src1p); local v=math.log(f1,2);  write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FABS   then f1=read_float(inst,src1p); write_float(inst,destp,math.abs(f1)); return (math.abs(f1)~=0) and 1 or 0
    elseif opcode==OP.FSIN   then f1=read_float(inst,src1p); write_float(inst,destp,math.sin(f1)); return (math.sin(f1)~=0) and 1 or 0
    elseif opcode==OP.FCOS   then f1=read_float(inst,src1p); write_float(inst,destp,math.cos(f1)); return (math.cos(f1)~=0) and 1 or 0
    elseif opcode==OP.FTAN   then f1=read_float(inst,src1p); write_float(inst,destp,math.tan(f1)); return (math.tan(f1)~=0) and 1 or 0
    elseif opcode==OP.FASIN  then f1=read_float(inst,src1p); write_float(inst,destp,math.asin(f1)); return (math.asin(f1)~=0) and 1 or 0
    elseif opcode==OP.FACOS  then f1=read_float(inst,src1p); write_float(inst,destp,math.acos(f1)); return (math.acos(f1)~=0) and 1 or 0
    elseif opcode==OP.FATAN  then f1=read_float(inst,src1p); write_float(inst,destp,math.atan(f1)); return (math.atan(f1)~=0) and 1 or 0
    elseif opcode==OP.FATAN2 then f1=read_float(inst,src1p); f2=read_float(inst,src2p); write_float(inst,destp,math.atan(f1,f2)); return (math.atan(f1,f2)~=0) and 1 or 0
    elseif opcode==OP.FSINH  then f1=read_float(inst,src1p); local e=math.exp(f1); local v=(e-1/e)/2; write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FCOSH  then f1=read_float(inst,src1p); local e=math.exp(f1); local v=(e+1/e)/2; write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FTANH  then f1=read_float(inst,src1p); local e=math.exp(2*f1); local v=(e-1)/(e+1); write_float(inst,destp,v); return (v~=0) and 1 or 0

    -- Integer math
    elseif opcode==OP.IABS then i1=read_int(inst,src1p); r=(i1<0) and -i1 or i1; write_int(inst,destp,r); return r
    elseif opcode==OP.IMIN then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1<i2) and i1 or i2; write_int(inst,destp,r); return r
    elseif opcode==OP.IMAX then i1=read_int(inst,src1p); i2=read_int(inst,src2p); r=(i1>i2) and i1 or i2; write_int(inst,destp,r); return r
    elseif opcode==OP.FMIN then f1=read_float(inst,src1p); f2=read_float(inst,src2p); local v=(f1<f2) and f1 or f2; write_float(inst,destp,v); return (v~=0) and 1 or 0
    elseif opcode==OP.FMAX then f1=read_float(inst,src1p); f2=read_float(inst,src2p); local v=(f1>f2) and f1 or f2; write_float(inst,destp,v); return (v~=0) and 1 or 0
    end

    error(string.format("se_quad: unknown opcode 0x%02x", opcode))
end

local M = {}

-- ============================================================================
-- SE_QUAD  (oneshot: fn(inst, node))
-- ============================================================================
M.se_quad = function(inst, node)
    local params = node.params or {}
    assert(#params >= 4, "se_quad: requires 4 params (opcode, src1, src2, dest)")
    exec_quad(inst, params[1].value, params[2], params[3], params[4])
end

-- ============================================================================
-- SE_P_QUAD  (pred: fn(inst, node) -> bool)
-- Handles all non-accumulate opcodes via exec_quad + nonzero check.
-- Handles accumulate variants (0x40–0x4D) with dest += cmp_result pattern.
-- ============================================================================
M.se_p_quad = function(inst, node)
    local params = node.params or {}
    assert(#params >= 4, "se_p_quad: requires 4 params")

    local opcode = params[1].value
    local src1p  = params[2]
    local src2p  = params[3]
    local destp  = params[4]

    -- Accumulate variants: dest += cmp_result; return cmp_result != 0
    local function acc_cmp(cmp)
        local prev = read_int(inst, destp)
        write_int(inst, destp, prev + cmp)
        return cmp ~= 0
    end

    local i1, i2, f1, f2

    if opcode == 0x40 then i1=read_int(inst,src1p); i2=read_int(inst,src2p); return acc_cmp((i1==i2) and 1 or 0)
    elseif opcode == 0x41 then i1=read_int(inst,src1p); i2=read_int(inst,src2p); return acc_cmp((i1~=i2) and 1 or 0)
    elseif opcode == 0x42 then i1=read_int(inst,src1p); i2=read_int(inst,src2p); return acc_cmp((i1< i2) and 1 or 0)
    elseif opcode == 0x43 then i1=read_int(inst,src1p); i2=read_int(inst,src2p); return acc_cmp((i1<=i2) and 1 or 0)
    elseif opcode == 0x44 then i1=read_int(inst,src1p); i2=read_int(inst,src2p); return acc_cmp((i1> i2) and 1 or 0)
    elseif opcode == 0x45 then i1=read_int(inst,src1p); i2=read_int(inst,src2p); return acc_cmp((i1>=i2) and 1 or 0)
    elseif opcode == 0x48 then f1=read_float(inst,src1p); f2=read_float(inst,src2p); return acc_cmp((f1==f2) and 1 or 0)
    elseif opcode == 0x49 then f1=read_float(inst,src1p); f2=read_float(inst,src2p); return acc_cmp((f1~=f2) and 1 or 0)
    elseif opcode == 0x4A then f1=read_float(inst,src1p); f2=read_float(inst,src2p); return acc_cmp((f1< f2) and 1 or 0)
    elseif opcode == 0x4B then f1=read_float(inst,src1p); f2=read_float(inst,src2p); return acc_cmp((f1<=f2) and 1 or 0)
    elseif opcode == 0x4C then f1=read_float(inst,src1p); f2=read_float(inst,src2p); return acc_cmp((f1> f2) and 1 or 0)
    elseif opcode == 0x4D then f1=read_float(inst,src1p); f2=read_float(inst,src2p); return acc_cmp((f1>=f2) and 1 or 0)
    end

    -- Non-accumulate: compute via exec_quad and return dest != 0
    local result = exec_quad(inst, opcode, src1p, src2p, destp)
    return result ~= 0
end

return M