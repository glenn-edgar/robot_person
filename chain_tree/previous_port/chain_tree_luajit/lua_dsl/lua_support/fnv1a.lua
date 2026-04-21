-- lua_support/fnv1a.lua
-- FNV-1a 32-bit hash matching the C runtime.
-- Hash key format: "<file>.h:<record>"
-- Shared by controlled_nodes.lua and streaming.lua.

local bxor, band, rshift, lshift, tobit

local ok, bit = pcall(require, "bit")
if ok then
    bxor, band, rshift, lshift, tobit = bit.bxor, bit.band, bit.rshift, bit.lshift, bit.tobit
else
    bxor   = load("return function(a,b) return a ~ b end")()
    band   = load("return function(a,b) return a & b end")()
    rshift = load("return function(a,n) return a >> n end")()
    lshift = load("return function(a,n) return a << n end")()
    tobit  = load("return function(a) return a & 0xFFFFFFFF end")()
end

local FNV_PRIME_32  = 0x01000193
local FNV_OFFSET_32 = 0x811C9DC5

local function mul32(a, b)
    local a_lo = band(a, 0xFFFF)
    local a_hi = band(rshift(a, 16), 0xFFFF)
    local b_lo = band(b, 0xFFFF)
    local b_hi = band(rshift(b, 16), 0xFFFF)
    local lo   = a_lo * b_lo
    local mid  = a_hi * b_lo + a_lo * b_hi
    return tobit(lo + lshift(mid, 16))
end

--- Compute FNV-1a 32-bit hash of a string.
--- Returns an unsigned 32-bit integer.
--- @param str string
--- @return number
local function fnv1a_32(str)
    local hash = FNV_OFFSET_32
    for i = 1, #str do
        hash = bxor(hash, str:byte(i))
        hash = mul32(hash, FNV_PRIME_32)
    end
    if hash < 0 then
        hash = hash + 0x100000000
    end
    return hash
end

--- Compute schema hash and convert to signed int32 for JSON round-trip.
--- Key format: "<file>.h:<record>"
--- @param file_name string   File base name (without .h extension)
--- @param record_name string  Record type name
--- @return number  Signed int32 schema hash
local function schema_hash(file_name, record_name)
    local hash_key = file_name .. ".h:" .. record_name
    local h = fnv1a_32(hash_key)
    if h > 0x7FFFFFFF then
        h = h - 0x100000000
    end
    return h
end

return {
    fnv1a_32    = fnv1a_32,
    schema_hash = schema_hash,
}