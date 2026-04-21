#!/usr/bin/env luajit
-- avro_dsl.lua
-- LuaJIT DSL for generating C header files and binary schema from Avro-like definitions
-- Outputs: .h (types + wire packets), _bin.h (embedded binary), .bin (loadable binary)

-- Bit operations - compatible with LuaJIT and Lua 5.3+
-- LuaJIT has the 'bit' library; Lua 5.3+ has native operators
-- We must avoid Lua 5.3 syntax (~ & >> <<) which causes parse errors in LuaJIT
local bxor, band, rshift, lshift, tobit

local ok, bit = pcall(require, "bit")
if ok then
    -- LuaJIT
    bxor, band, rshift, lshift, tobit = bit.bxor, bit.band, bit.rshift, bit.lshift, bit.tobit
else
    -- Lua 5.3+ - use load() to avoid parse errors in LuaJIT
    bxor   = load("return function(a,b) return a ~ b end")()
    band   = load("return function(a,b) return a & b end")()
    rshift = load("return function(a,n) return a >> n end")()
    lshift = load("return function(a,n) return a << n end")()
    tobit  = load("return function(a) return a & 0xFFFFFFFF end")()
end

local M = {}

-- Current state
local current_file = nil
local current_container = nil
local current_const_packet = nil

--------------------------------------------------------------------------------
-- FNV-1a 32-BIT HASH (matches s_engine C implementation)
--------------------------------------------------------------------------------

local FNV_PRIME_32  = 0x01000193
local FNV_OFFSET_32 = 0x811C9DC5

-- 32-bit multiply with proper wrapping
local function mul32(a, b)
    local a_lo = band(a, 0xFFFF)
    local a_hi = band(rshift(a, 16), 0xFFFF)
    local b_lo = band(b, 0xFFFF)
    local b_hi = band(rshift(b, 16), 0xFFFF)
    
    local lo = a_lo * b_lo
    local mid = a_hi * b_lo + a_lo * b_hi
    
    return tobit(lo + lshift(mid, 16))
end

local function fnv1a_32(str)
    local hash = FNV_OFFSET_32
    for i = 1, #str do
        hash = bxor(hash, str:byte(i))
        hash = mul32(hash, FNV_PRIME_32)
    end
    -- Return as unsigned
    if hash < 0 then
        hash = hash + 0x100000000
    end
    return hash
end

M.fnv1a_32 = fnv1a_32  -- Export for testing

--------------------------------------------------------------------------------
-- HASH HELPERS
--------------------------------------------------------------------------------

-- Per-record hash: FNV-1a of "filename.h:record_name"
local function record_hash(record_name)
    local key = current_file.name .. ".h:" .. record_name
    return fnv1a_32(key)
end

--------------------------------------------------------------------------------
-- TYPE DEFINITIONS
--------------------------------------------------------------------------------

local type_sizes = {
    int8    = 1,  uint8   = 1,
    int16   = 2,  uint16  = 2,
    int32   = 4,  uint32  = 4,
    int64   = 8,  uint64  = 8,
    float   = 4,  double  = 8,
    bool    = 1,
}

local type_cnames = {
    int8    = "int8_t",   uint8   = "uint8_t",
    int16   = "int16_t",  uint16  = "uint16_t",
    int32   = "int32_t",  uint32  = "uint32_t",
    int64   = "int64_t",  uint64  = "uint64_t",
    float   = "float",    double  = "double",
    bool    = "bool",
}

-- Type tags for binary encoding
local type_tags = {
    int8    = 1,  uint8   = 2,
    int16   = 3,  uint16  = 4,
    int32   = 5,  uint32  = 6,
    int64   = 7,  uint64  = 8,
    float   = 9,  double  = 10,
    bool    = 11,
    enum    = 20,
    fixed   = 21,
    string  = 22,
    pointer = 23,
    struct  = 30,
    record  = 31,
}

--------------------------------------------------------------------------------
-- DSL COMMANDS
--------------------------------------------------------------------------------

function M.FILE(name)
    current_file = {
        name = name,
        includes_bracket = {},
        includes_string = {},
        enums = {},
        fixed = {},
        strings = {},
        pointers = {},
        structs = {},
        records = {},
        const_packets = {},
    }
end

function M.INCLUDE_BRACKET(header)
    table.insert(current_file.includes_bracket, header)
end

function M.INCLUDE_STRING(header)
    table.insert(current_file.includes_string, header)
end

function M.ENUM(name)
    current_container = {
        kind = "enum",
        name = name,
        values = {},
    }
end

function M.VALUE(name, val)
    table.insert(current_container.values, { name = name, val = val })
end

function M.END_ENUM()
    table.insert(current_file.enums, current_container)
    current_container = nil
end

function M.FIXED(name, size)
    table.insert(current_file.fixed, { name = name, size = size })
end

function M.STRING(name, length)
    table.insert(current_file.strings, { name = name, length = length })
end

function M.POINTER(name)
    table.insert(current_file.pointers, { name = name })
end

function M.STRUCT(name)
    current_container = {
        kind = "struct",
        name = name,
        fields = {},
    }
end

function M.RECORD(name)
    current_container = {
        kind = "record",
        name = name,
        index = #current_file.records,
        fields = {},
    }
end

function M.FIELD(name, ftype, array_size)
    table.insert(current_container.fields, {
        name = name,
        type = ftype,
        array_size = array_size,
    })
end

function M.END_STRUCT()
    table.insert(current_file.structs, current_container)
    current_container = nil
end

function M.END_RECORD()
    table.insert(current_file.records, current_container)
    current_container = nil
end

function M.CONST_PACKET(record_name, instance_name, source_node)
    -- Verify the record exists
    local found = false
    for _, r in ipairs(current_file.records) do
        if r.name == record_name then found = true; break end
    end
    if not found then
        error("CONST_PACKET: unknown record '" .. record_name .. "'")
    end
    current_const_packet = {
        record_name = record_name,
        instance_name = instance_name,
        source_node = source_node or 0,
        fields = {},
    }
end

function M.SET(field_name, value)
    if current_const_packet == nil then
        error("SET: must be inside CONST_PACKET ... END_CONST_PACKET")
    end
    current_const_packet.fields[field_name] = value
end

function M.END_CONST_PACKET()
    if current_const_packet == nil then
        error("END_CONST_PACKET: no matching CONST_PACKET")
    end
    table.insert(current_file.const_packets, current_const_packet)
    current_const_packet = nil
end

--------------------------------------------------------------------------------
-- BINARY FORMAT HELPERS
--------------------------------------------------------------------------------

-- Binary schema magic and version
local SCHEMA_MAGIC   = 0x41565244  -- "AVRD" in little-endian
local SCHEMA_VERSION = 2           -- Bumped for new header format

-- Pack little-endian integers
local function pack_u8(val)
    return string.char(band(val, 0xFF))
end

local function pack_i8(val)
    if val < 0 then val = val + 256 end
    return string.char(band(val, 0xFF))
end

local function pack_u16(val)
    return string.char(
        band(val, 0xFF),
        band(rshift(val, 8), 0xFF)
    )
end

local function pack_i16(val)
    if val < 0 then val = val + 65536 end
    return pack_u16(val)
end

local function pack_u32(val)
    return string.char(
        band(val, 0xFF),
        band(rshift(val, 8), 0xFF),
        band(rshift(val, 16), 0xFF),
        band(rshift(val, 24), 0xFF)
    )
end

local function pack_i32(val)
    if val < 0 then val = val + 0x100000000 end
    return pack_u32(val)
end

-- Float/double packing: use string.pack (Lua 5.3+) or ffi (LuaJIT)
local pack_float, pack_double

local has_ffi, ffi = pcall(require, "ffi")
if has_ffi then
    -- LuaJIT: use FFI for IEEE 754 conversion
    local float_buf = ffi.new("float[1]")
    local double_buf = ffi.new("double[1]")
    local uint8_ptr = ffi.typeof("uint8_t*")

    pack_float = function(val)
        float_buf[0] = val
        local p = ffi.cast(uint8_ptr, float_buf)
        return string.char(p[0], p[1], p[2], p[3])
    end

    pack_double = function(val)
        double_buf[0] = val
        local p = ffi.cast(uint8_ptr, double_buf)
        return string.char(p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7])
    end
else
    -- Lua 5.3+: use string.pack
    local sp = string.pack
    pack_float = function(val) return sp("<f", val) end
    pack_double = function(val) return sp("<d", val) end
end

local function pack_u64(val)
    -- For Lua 5.3+ integers or LuaJIT with ULL
    local lo = band(val, 0xFFFFFFFF)
    local hi = 0
    if val >= 0x100000000 then
        hi = math.floor(val / 0x100000000)
    end
    return pack_u32(lo) .. pack_u32(hi)
end

local function pack_i64(val)
    if val < 0 then val = val + 2^64 end
    return pack_u64(val)
end

local function pack_bool(val)
    return string.char(val and 1 or 0)
end

-- Null-terminated string
local function pack_string(str)
    return str .. "\0"
end

-- Resolve type tag for binary encoding
local function resolve_type_tag(ftype)
    if type_tags[ftype] then
        return type_tags[ftype]
    end
    for _, e in ipairs(current_file.enums) do
        if e.name == ftype then return type_tags.enum end
    end
    for _, f in ipairs(current_file.fixed) do
        if f.name == ftype then return type_tags.fixed end
    end
    for _, s in ipairs(current_file.strings) do
        if s.name == ftype then return type_tags.string end
    end
    for _, p in ipairs(current_file.pointers) do
        if p.name == ftype then return type_tags.pointer end
    end
    for _, st in ipairs(current_file.structs) do
        if st.name == ftype then return type_tags.struct end
    end
    for _, r in ipairs(current_file.records) do
        if r.name == ftype then return type_tags.record end
    end
    return 0  -- Unknown
end

-- Resolve field size
local function resolve_field_size(ftype)
    if type_sizes[ftype] then
        return type_sizes[ftype]
    end
    for _, e in ipairs(current_file.enums) do
        if e.name == ftype then return 4 end  -- Enums are int
    end
    for _, f in ipairs(current_file.fixed) do
        if f.name == ftype then return f.size end
    end
    for _, s in ipairs(current_file.strings) do
        if s.name == ftype then return s.length + 4 end  -- buffer + length + max_length
    end
    for _, p in ipairs(current_file.pointers) do
        if p.name == ftype then return 8 end  -- void* on 64-bit
    end
    -- For structs/records, would need recursive calculation
    return 0
end

-- Compute struct/record size (simplified - assumes packed)
local function compute_container_size(container)
    local size = 0
    for _, f in ipairs(container.fields) do
        local fsize = resolve_field_size(f.type)
        local count = f.array_size or 1
        size = size + fsize * count
    end
    return size
end

--------------------------------------------------------------------------------
-- BINARY GENERATION
--------------------------------------------------------------------------------

function M.GENERATE_BINARY(output_path)
    output_path = output_path or (current_file.name .. ".bin")
    
    local chunks = {}
    
    -- Header: magic(4) + version(2) + record_count(2) + total_size(4)
    table.insert(chunks, pack_u32(SCHEMA_MAGIC))
    table.insert(chunks, pack_u16(SCHEMA_VERSION))
    table.insert(chunks, pack_u16(#current_file.records))
    -- Placeholder for total_size - will patch
    local size_placeholder_pos = #chunks + 1
    table.insert(chunks, pack_u32(0))
    
    -- Schema name (null-terminated)
    table.insert(chunks, pack_string(current_file.name))
    
    -- Per-record hashes
    for _, r in ipairs(current_file.records) do
        table.insert(chunks, pack_u32(record_hash(r.name)))
    end
    
    -- Enums
    table.insert(chunks, pack_u16(#current_file.enums))
    for _, e in ipairs(current_file.enums) do
        table.insert(chunks, pack_string(e.name))
        table.insert(chunks, pack_u32(fnv1a_32(e.name)))
        table.insert(chunks, pack_u8(#e.values))
        for _, v in ipairs(e.values) do
            table.insert(chunks, pack_string(v.name))
            table.insert(chunks, pack_u32(v.val))
        end
    end
    
    -- Fixed arrays
    table.insert(chunks, pack_u16(#current_file.fixed))
    for _, f in ipairs(current_file.fixed) do
        table.insert(chunks, pack_string(f.name))
        table.insert(chunks, pack_u32(fnv1a_32(f.name)))
        table.insert(chunks, pack_u16(f.size))
    end
    
    -- Strings
    table.insert(chunks, pack_u16(#current_file.strings))
    for _, s in ipairs(current_file.strings) do
        table.insert(chunks, pack_string(s.name))
        table.insert(chunks, pack_u32(fnv1a_32(s.name)))
        table.insert(chunks, pack_u16(s.length))
    end
    
    -- Pointers
    table.insert(chunks, pack_u16(#current_file.pointers))
    for _, p in ipairs(current_file.pointers) do
        table.insert(chunks, pack_string(p.name))
        table.insert(chunks, pack_u32(fnv1a_32(p.name)))
    end
    
    -- Structs
    table.insert(chunks, pack_u16(#current_file.structs))
    for _, st in ipairs(current_file.structs) do
        table.insert(chunks, pack_string(st.name))
        table.insert(chunks, pack_u32(fnv1a_32(st.name)))
        table.insert(chunks, pack_u16(compute_container_size(st)))
        table.insert(chunks, pack_u8(#st.fields))
        
        local offset = 0
        for _, f in ipairs(st.fields) do
            table.insert(chunks, pack_string(f.name))
            table.insert(chunks, pack_u8(resolve_type_tag(f.type)))
            table.insert(chunks, pack_u16(offset))
            local fsize = resolve_field_size(f.type)
            table.insert(chunks, pack_u16(fsize))
            table.insert(chunks, pack_u16(f.array_size or 0))
            offset = offset + fsize * math.max(1, f.array_size or 1)
        end
    end
    
    -- Records
    table.insert(chunks, pack_u16(#current_file.records))
    for _, r in ipairs(current_file.records) do
        table.insert(chunks, pack_string(r.name))
        table.insert(chunks, pack_u32(record_hash(r.name)))
        table.insert(chunks, pack_u16(compute_container_size(r)))
        table.insert(chunks, pack_u8(#r.fields))
        
        local offset = 0
        for _, f in ipairs(r.fields) do
            table.insert(chunks, pack_string(f.name))
            table.insert(chunks, pack_u8(resolve_type_tag(f.type)))
            table.insert(chunks, pack_u16(offset))
            local fsize = resolve_field_size(f.type)
            table.insert(chunks, pack_u16(fsize))
            table.insert(chunks, pack_u16(f.array_size or 0))
            offset = offset + fsize * math.max(1, f.array_size or 1)
        end
    end
    
    -- Concatenate and patch total size
    local blob = table.concat(chunks)
    local total_size = #blob
    
    -- Patch total_size at offset 8 (after magic+version+record_count)
    blob = blob:sub(1, 8) .. pack_u32(total_size) .. blob:sub(13)
    
    -- Write binary file
    local out = io.open(output_path, "wb")
    if not out then
        error("Cannot open output file: " .. output_path)
    end
    out:write(blob)
    out:close()
    print("Generated binary: " .. output_path .. " (" .. total_size .. " bytes)")
    
    return blob
end




--------------------------------------------------------------------------------
-- C HEADER GENERATION
--------------------------------------------------------------------------------

local function upper_name(name)
    return name:upper()
end

local function resolve_ctype(ftype)
    if type_cnames[ftype] then
        return type_cnames[ftype]
    end
    for _, e in ipairs(current_file.enums) do
        if e.name == ftype then return ftype .. "_t" end
    end
    for _, f in ipairs(current_file.fixed) do
        if f.name == ftype then return ftype .. "_t" end
    end
    for _, s in ipairs(current_file.strings) do
        if s.name == ftype then return ftype .. "_t" end
    end
    for _, p in ipairs(current_file.pointers) do
        if p.name == ftype then return ftype .. "_t" end
    end
    for _, st in ipairs(current_file.structs) do
        if st.name == ftype then return ftype .. "_t" end
    end
    for _, r in ipairs(current_file.records) do
        if r.name == ftype then return ftype .. "_t" end
    end
    return ftype .. "_t"
end

local function emit_header(out)
    out:write("// " .. current_file.name .. ".h\n")
    out:write("// Generated by avro_dsl.lua - DO NOT EDIT\n")
    out:write("#pragma once\n\n")
    
    for _, inc in ipairs(current_file.includes_bracket) do
        out:write(string.format("#include <%s>\n", inc))
    end
    for _, inc in ipairs(current_file.includes_string) do
        out:write(string.format("#include \"%s\"\n", inc))
    end
    if #current_file.includes_string > 0 or #current_file.includes_bracket > 0 then
        out:write("\n")
    end
    
    out:write("#ifdef __cplusplus\n")
    out:write("extern \"C\" {\n")
    out:write("#endif\n\n")
end

local function emit_footer(out)
    out:write("\n#ifdef __cplusplus\n")
    out:write("}\n")
    out:write("#endif\n")
end

local function emit_file_metadata(out)
    local name_upper = upper_name(current_file.name)
    out:write("// ============ FILE METADATA ============\n")
    out:write(string.format("#define %s_RECORD_COUNT  %d\n", name_upper, #current_file.records))
    out:write(string.format("#define %s_SCHEMA_FILE   \"%s.h\"\n\n", name_upper, current_file.name))
    
    -- Per-record schema hashes
    out:write("// Per-record schema hashes: FNV-1a of \"<file>.h:<record>\"\n")
    for _, r in ipairs(current_file.records) do
        local hash = record_hash(r.name)
        out:write(string.format("#define %s_SCHEMA_HASH   0x%08XU\n", upper_name(r.name), hash))
    end
    out:write("\n")
end

local function emit_enums(out)
    if #current_file.enums == 0 then return end
    out:write("// ============ ENUMS ============\n")
    for _, e in ipairs(current_file.enums) do
        out:write(string.format("typedef enum {\n"))
        for i, v in ipairs(e.values) do
            local comma = (i < #e.values) and "," or ""
            out:write(string.format("    %s_%s = %d%s\n", upper_name(e.name), v.name, v.val, comma))
        end
        out:write(string.format("} %s_t;\n\n", e.name))
    end
end

local function emit_fixed(out)
    if #current_file.fixed == 0 then return end
    out:write("// ============ FIXED ARRAYS ============\n")
    for _, f in ipairs(current_file.fixed) do
        out:write(string.format("typedef uint8_t %s_t[%d];\n", f.name, f.size))
    end
    out:write("\n")
end

local function emit_strings(out)
    if #current_file.strings == 0 then return end
    out:write("// ============ FIXED STRINGS ============\n")
    for _, s in ipairs(current_file.strings) do
        out:write(string.format("typedef struct {\n"))
        out:write(string.format("    char buffer[%d];\n", s.length))
        out:write(string.format("    uint16_t length;\n"))
        out:write(string.format("    uint16_t max_length;\n"))
        out:write(string.format("} %s_t;\n\n", s.name))
    end
end

local function emit_pointers(out)
    if #current_file.pointers == 0 then return end
    out:write("// ============ USER POINTERS ============\n")
    for _, p in ipairs(current_file.pointers) do
        out:write(string.format("typedef struct {\n"))
        out:write(string.format("    void *ptr;\n"))
        out:write(string.format("} %s_t;\n\n", p.name))
    end
end

local function emit_struct_def(out, st)
    out:write(string.format("typedef struct {\n"))
    for _, f in ipairs(st.fields) do
        local ctype = resolve_ctype(f.type)
        if f.array_size then
            out:write(string.format("    %s %s[%d];\n", ctype, f.name, f.array_size))
        else
            out:write(string.format("    %s %s;\n", ctype, f.name))
        end
    end
    out:write(string.format("} %s_t;\n\n", st.name))
end

local function emit_structs(out)
    if #current_file.structs == 0 then return end
    out:write("// ============ STRUCTS ============\n")
    for _, st in ipairs(current_file.structs) do
        emit_struct_def(out, st)
    end
end

local function emit_records(out)
    if #current_file.records == 0 then return end
    out:write("// ============ RECORDS ============\n")
    out:write("// Note: For cross-platform wire safety, use the _wire_t variants\n\n")
    for _, r in ipairs(current_file.records) do
        emit_struct_def(out, r)
    end
end

-- Generate wire-safe record structs with explicit layout
local function emit_wire_records(out)
    if #current_file.records == 0 then return end
    
    out:write("// ============ WIRE-SAFE RECORDS ============\n")
    out:write("// Packed structs with fixed-size enums for cross-platform compatibility\n")
    out:write("// Use these for 32-bit <-> 64-bit communication\n\n")
    
    for _, r in ipairs(current_file.records) do
        out:write(string.format("#pragma pack(push, 1)\n"))
        out:write(string.format("typedef struct {\n"))
        for _, f in ipairs(r.fields) do
            local ctype = resolve_ctype(f.type)
            local is_enum = false
            
            -- Check if this is an enum type
            for _, e in ipairs(current_file.enums) do
                if e.name == f.type then
                    is_enum = true
                    break
                end
            end
            
            if is_enum then
                -- Use fixed-size int32_t for enums in wire format
                if f.array_size then
                    out:write(string.format("    int32_t %s[%d];  // enum %s\n", f.name, f.array_size, f.type))
                else
                    out:write(string.format("    int32_t %s;  // enum %s\n", f.name, f.type))
                end
            else
                if f.array_size then
                    out:write(string.format("    %s %s[%d];\n", ctype, f.name, f.array_size))
                else
                    out:write(string.format("    %s %s;\n", ctype, f.name))
                end
            end
        end
        out:write(string.format("} %s_wire_t;\n", r.name))
        out:write(string.format("#pragma pack(pop)\n\n"))
    end
    
    -- Generate conversion helpers
    out:write("// ============ WIRE CONVERSION HELPERS ============\n\n")
    for _, r in ipairs(current_file.records) do
        -- Native to wire
        out:write(string.format("static inline void %s_to_wire(const %s_t* src, %s_wire_t* dst) {\n", 
            r.name, r.name, r.name))
        for _, f in ipairs(r.fields) do
            local is_enum = false
            for _, e in ipairs(current_file.enums) do
                if e.name == f.type then is_enum = true; break end
            end
            
            if f.array_size then
                if is_enum then
                    out:write(string.format("    for (int i = 0; i < %d; i++) dst->%s[i] = (int32_t)src->%s[i];\n",
                        f.array_size, f.name, f.name))
                else
                    out:write(string.format("    memcpy(dst->%s, src->%s, sizeof(dst->%s));\n", 
                        f.name, f.name, f.name))
                end
            else
                if is_enum then
                    out:write(string.format("    dst->%s = (int32_t)src->%s;\n", f.name, f.name))
                else
                    out:write(string.format("    dst->%s = src->%s;\n", f.name, f.name))
                end
            end
        end
        out:write("}\n\n")
        
        -- Wire to native
        out:write(string.format("static inline void %s_from_wire(const %s_wire_t* src, %s_t* dst) {\n",
            r.name, r.name, r.name))
        for _, f in ipairs(r.fields) do
            local is_enum = false
            local enum_name = nil
            for _, e in ipairs(current_file.enums) do
                if e.name == f.type then is_enum = true; enum_name = e.name; break end
            end
            
            if f.array_size then
                if is_enum then
                    out:write(string.format("    for (int i = 0; i < %d; i++) dst->%s[i] = (%s_t)src->%s[i];\n",
                        f.array_size, f.name, enum_name, f.name))
                else
                    out:write(string.format("    memcpy(dst->%s, src->%s, sizeof(dst->%s));\n",
                        f.name, f.name, f.name))
                end
            else
                if is_enum then
                    out:write(string.format("    dst->%s = (%s_t)src->%s;\n", f.name, enum_name, f.name))
                else
                    out:write(string.format("    dst->%s = src->%s;\n", f.name, f.name))
                end
            end
        end
        out:write("}\n\n")
    end
end

local function emit_wire_header_type(out)
    out:write("// ============ WIRE HEADER ============\n")
    out:write("// Common header for all wire packets (16 bytes, packed)\n")
    out:write("// schema_hash is per-record: FNV-1a of \"<file>.h:<record>\"\n\n")
    
    out:write("#pragma pack(push, 1)\n")
    out:write("typedef struct {\n")
    out:write("    double      timestamp;     // 8: message timestamp (set by transport)\n")
    out:write("    uint32_t    schema_hash;   // 4: per-record FNV-1a hash\n")
    out:write("    uint16_t    seq;           // 2: sequence number (set by transport)\n")
    out:write("    uint16_t    source_node;   // 2: originating node ID\n")
    out:write(string.format("} %s_wire_header_t;\n", current_file.name))
    out:write("#pragma pack(pop)\n\n")
    
    -- Static assert for header size
    out:write(string.format("_Static_assert(sizeof(%s_wire_header_t) == 16, \"Wire header must be 16 bytes\");\n\n",
        current_file.name))
end

local function emit_wire_packets(out)
    if #current_file.records == 0 then return end
    
    local name_upper = upper_name(current_file.name)
    
    out:write("// ============ WIRE PACKETS ============\n")
    out:write("// Per-record packet types with unified header\n")
    out:write("// Socket-safe: no pointers, fixed size, per-record hash identification\n\n")
    
    for _, r in ipairs(current_file.records) do
        out:write(string.format("#pragma pack(push, 1)\n"))
        out:write(string.format("typedef struct {\n"))
        out:write(string.format("    %s_wire_header_t header;\n", current_file.name))
        out:write(string.format("    %s_wire_t        data;\n", r.name))
        out:write(string.format("} %s_packet_t;\n", r.name))
        out:write(string.format("#pragma pack(pop)\n\n"))
    end
    
    -- Static asserts for wire record sizes
    out:write("// Static assertions for wire format sizes\n")
    for _, r in ipairs(current_file.records) do
        local size = compute_container_size(r)
        out:write(string.format("_Static_assert(sizeof(%s_wire_t) == %d, \"%s_wire_t size mismatch\");\n",
            r.name, size, r.name))
    end
    out:write("\n")
    
    -- Generate encode helper per record
    out:write("// Packet encode helpers - populate header and return pointer to wire data\n")
    out:write("// Note: seq and timestamp are zeroed; set by transport layer before sending\n\n")
    for _, r in ipairs(current_file.records) do
        local rhash = record_hash(r.name)
        out:write(string.format("static inline %s_wire_t* %s_packet_init(\n", r.name, r.name))
        out:write(string.format("        %s_packet_t* pkt,\n", r.name))
        out:write("        uint16_t source_node)\n")
        out:write("{\n")
        out:write(string.format("    pkt->header.schema_hash = %s_SCHEMA_HASH;\n", upper_name(r.name)))
        out:write("    pkt->header.timestamp = 0.0;\n")
        out:write("    pkt->header.seq = 0;\n")
        out:write("    pkt->header.source_node = source_node;\n")
        out:write("    return &pkt->data;\n")
        out:write("}\n\n")
    end
    
    -- Generate verify helpers
    out:write("// Packet verify helpers - validate per-record schema hash, return wire data pointer\n\n")
    for _, r in ipairs(current_file.records) do
        out:write(string.format("static inline const %s_wire_t* %s_packet_verify(\n", r.name, r.name))
        out:write(string.format("        const %s_packet_t* pkt)\n", r.name))
        out:write("{\n")
        out:write(string.format("    if (pkt->header.schema_hash != %s_SCHEMA_HASH) return NULL;\n", upper_name(r.name)))
        out:write("    return &pkt->data;\n")
        out:write("}\n\n")
    end
    
    -- Generic dispatch helper
    out:write("// Generic packet dispatch - returns record index or -1 on error\n")
    out:write("// Matches per-record schema hash to determine record type\n")
    out:write(string.format("static inline int %s_packet_dispatch(\n", current_file.name))
    out:write("        const void* packet_buffer,\n")
    out:write("        uint16_t* source_node_out,\n")
    out:write("        const void** data_out)\n")
    out:write("{\n")
    out:write(string.format("    const %s_wire_header_t* hdr = (const %s_wire_header_t*)packet_buffer;\n",
        current_file.name, current_file.name))
    out:write("    if (source_node_out) *source_node_out = hdr->source_node;\n")
    out:write(string.format("    if (data_out) *data_out = ((const uint8_t*)packet_buffer) + sizeof(%s_wire_header_t);\n",
        current_file.name))
    for i, r in ipairs(current_file.records) do
        local idx = i - 1
        out:write(string.format("    if (hdr->schema_hash == %s_SCHEMA_HASH) return %d;\n", upper_name(r.name), idx))
    end
    out:write("    return -1;\n")
    out:write("}\n\n")
    
    -- Wire record sizes array
    out:write("// Wire record payload sizes (for buffer allocation)\n")
    out:write(string.format("static const uint16_t %s_wire_sizes[%s_RECORD_COUNT] = {\n",
        current_file.name, name_upper))
    for _, r in ipairs(current_file.records) do
        out:write(string.format("    sizeof(%s_wire_t),  // %s\n", r.name, r.name))
    end
    out:write("};\n\n")
    
    -- Packet sizes array
    out:write("// Full packet sizes including header (for socket send/recv)\n")
    out:write(string.format("static const uint16_t %s_packet_sizes[%s_RECORD_COUNT] = {\n",
        current_file.name, name_upper))
    for _, r in ipairs(current_file.records) do
        out:write(string.format("    sizeof(%s_packet_t),  // %s\n", r.name, r.name))
    end
    out:write("};\n\n")
    
    -- Per-record hash array (for runtime lookup)
    out:write("// Per-record schema hashes (for runtime dispatch tables)\n")
    out:write(string.format("static const uint32_t %s_record_hashes[%s_RECORD_COUNT] = {\n",
        current_file.name, name_upper))
    for _, r in ipairs(current_file.records) do
        out:write(string.format("    %s_SCHEMA_HASH,  // %s\n", upper_name(r.name), r.name))
    end
    out:write("};\n")
end

function M.GENERATE(output_path)
    output_path = output_path or (current_file.name .. ".h")
    
    local out = io.open(output_path, "w")
    if not out then
        error("Cannot open output file: " .. output_path)
    end
    
    emit_header(out)
    emit_file_metadata(out)
    emit_enums(out)
    emit_fixed(out)
    emit_strings(out)
    emit_pointers(out)
    emit_structs(out)
    emit_records(out)
    emit_wire_records(out)
    emit_wire_header_type(out)
    emit_wire_packets(out)
    emit_footer(out)
    out:close()
    print("Generated: " .. output_path)
end


--------------------------------------------------------------------------------
-- CONST PACKET GENERATION (_bin.h with static const packet structs)
--------------------------------------------------------------------------------

-- Format a value for C initializer based on DSL type
local function format_c_value(ftype, value)
    if ftype == "float" then
        local s = string.format("%g", value)
        -- Ensure it has a decimal point and 'f' suffix
        if not s:find("[%.eE]") then s = s .. ".0" end
        return s .. "f"
    elseif ftype == "double" then
        local s = string.format("%g", value)
        if not s:find("[%.eE]") then s = s .. ".0" end
        return s
    elseif ftype == "bool" then
        return value and "true" or "false"
    elseif ftype == "int8" or ftype == "int16" or ftype == "int32" then
        return string.format("%d", value)
    elseif ftype == "uint8" or ftype == "uint16" or ftype == "uint32" then
        return string.format("%uU", value)
    elseif ftype == "int64" then
        return string.format("%dLL", value)
    elseif ftype == "uint64" then
        return string.format("%uULL", value)
    else
        -- Enum or unknown — emit as integer
        return string.format("%d", value)
    end
end

-- Find a record definition by name
local function find_record(name)
    for _, r in ipairs(current_file.records) do
        if r.name == name then return r end
    end
    return nil
end

function M.GENERATE_CONST_PACKETS(output_path)
    if #current_file.const_packets == 0 then
        return
    end
    
    output_path = output_path or (current_file.name .. "_bin.h")
    local name_upper = current_file.name:upper()
    
    local out = io.open(output_path, "w")
    if not out then
        error("Cannot open output file: " .. output_path)
    end
    
    out:write("// " .. output_path .. "\n")
    out:write("// Generated const packets - DO NOT EDIT\n")
    out:write("#pragma once\n\n")
    out:write(string.format("#include \"%s.h\"\n\n", current_file.name))
    
    for _, cp in ipairs(current_file.const_packets) do
        local rec = find_record(cp.record_name)
        if not rec then
            error("GENERATE_CONST_PACKETS: unknown record '" .. cp.record_name .. "'")
        end
        
        local rhash = record_hash(cp.record_name)
        
        out:write(string.format("static const %s_packet_t %s = {\n", cp.record_name, cp.instance_name))
        
        -- Header
        out:write("    .header = {\n")
        out:write("        .timestamp   = 0.0,\n")
        out:write(string.format("        .schema_hash = %s_SCHEMA_HASH,\n", cp.record_name:upper()))
        out:write("        .seq         = 0,\n")
        out:write(string.format("        .source_node = %u,\n", cp.source_node))
        out:write("    },\n")
        
        -- Data fields
        out:write("    .data = {\n")
        for i, f in ipairs(rec.fields) do
            local val = cp.fields[f.name]
            if val == nil then val = 0 end
            local comma = (i < #rec.fields) and "," or ","
            
            if f.array_size then
                -- Array field: emit { val, val, ... }
                out:write(string.format("        .%s = { ", f.name))
                if type(val) == "table" then
                    for j, v in ipairs(val) do
                        out:write(format_c_value(f.type, v))
                        if j < #val then out:write(", ") end
                    end
                else
                    -- Fill array with single value
                    for j = 1, f.array_size do
                        out:write(format_c_value(f.type, val))
                        if j < f.array_size then out:write(", ") end
                    end
                end
                out:write(" }" .. comma .. "\n")
            else
                out:write(string.format("        .%s = %s%s\n", f.name, format_c_value(f.type, val), comma))
            end
        end
        out:write("    },\n")
        
        out:write("};\n\n")
    end
    
    out:close()
    print("Generated const packets: " .. output_path)
end

--------------------------------------------------------------------------------
-- BINARY CONST PACKET GENERATION (_bin.h with uint8_t[] blobs + cast macros)
--------------------------------------------------------------------------------

-- Pack a single field value into little-endian bytes
local pack_field_fns = {
    uint8   = pack_u8,
    int8    = pack_i8,
    uint16  = pack_u16,
    int16   = pack_i16,
    uint32  = pack_u32,
    int32   = pack_i32,
    uint64  = pack_u64,
    int64   = pack_i64,
    float   = pack_float,
    double  = pack_double,
    bool    = pack_bool,
}

local function pack_field_value(ftype, value)
    local fn = pack_field_fns[ftype]
    if fn then return fn(value) end
    -- Enum types → pack as int32
    for _, e in ipairs(current_file.enums) do
        if e.name == ftype then return pack_i32(value) end
    end
    -- Fixed arrays → pad with zeros
    for _, f in ipairs(current_file.fixed) do
        if f.name == ftype then
            if type(value) == "string" then
                return value .. string.rep("\0", f.size - #value)
            else
                return string.rep("\0", f.size)
            end
        end
    end
    error("pack_field_value: unsupported type '" .. ftype .. "'")
end

-- Serialize a const packet definition into a binary blob
local function serialize_const_packet(cp)
    local rec = find_record(cp.record_name)
    if not rec then
        error("serialize_const_packet: unknown record '" .. cp.record_name .. "'")
    end
    
    local rhash = record_hash(cp.record_name)
    local chunks = {}
    
    -- Header (16 bytes): timestamp(8) + schema_hash(4) + seq(2) + source_node(2)
    table.insert(chunks, pack_double(0.0))
    table.insert(chunks, pack_u32(rhash))
    table.insert(chunks, pack_u16(0))
    table.insert(chunks, pack_u16(cp.source_node))
    
    -- Data fields
    for _, f in ipairs(rec.fields) do
        local val = cp.fields[f.name]
        if val == nil then val = 0 end
        local count = f.array_size or 1
        
        if f.array_size then
            if type(val) == "table" then
                for j = 1, count do
                    table.insert(chunks, pack_field_value(f.type, val[j] or 0))
                end
            else
                for _ = 1, count do
                    table.insert(chunks, pack_field_value(f.type, val))
                end
            end
        else
            table.insert(chunks, pack_field_value(f.type, val))
        end
    end
    
    return table.concat(chunks)
end

function M.GENERATE_CONST_PACKETS_BINARY(output_path)
    if #current_file.const_packets == 0 then
        return
    end
    
    output_path = output_path or (current_file.name .. "_bin.h")
    
    local out = io.open(output_path, "w")
    if not out then
        error("Cannot open output file: " .. output_path)
    end
    
    out:write("// " .. output_path .. "\n")
    out:write("// Generated binary const packets - DO NOT EDIT\n")
    out:write("#pragma once\n\n")
    out:write("#include <stdint.h>\n")
    out:write(string.format("#include \"%s.h\"\n\n", current_file.name))
    
    for _, cp in ipairs(current_file.const_packets) do
        local blob = serialize_const_packet(cp)
        local name_upper = cp.instance_name:upper()
        
        -- Size define
        out:write(string.format("#define %s_SIZE  %d\n", name_upper, #blob))
        
        -- Binary blob
        out:write(string.format("static const uint8_t %s_bin[%d] = {\n",
            cp.instance_name, #blob))
        
        -- Emit hex bytes, 16 per line, with field comments
        local offset = 0
        
        -- Header comment block
        out:write("    // header: timestamp(8) + schema_hash(4) + seq(2) + source_node(2)\n")
        out:write("    ")
        for i = 1, 16 do
            out:write(string.format("0x%02X", blob:byte(i)))
            if i < #blob then out:write(", ") end
        end
        out:write("\n")
        offset = 16
        
        -- Data fields
        local rec = find_record(cp.record_name)
        for _, f in ipairs(rec.fields) do
            local fsize = resolve_field_size(f.type)
            local count = f.array_size or 1
            local total = fsize * count
            local val = cp.fields[f.name]
            if val == nil then val = 0 end
            
            local val_str
            if f.array_size then
                val_str = "array"
            elseif f.type == "float" or f.type == "double" then
                val_str = string.format("%g", val)
            else
                val_str = tostring(val)
            end
            
            out:write(string.format("    // %s (%s) = %s\n", f.name, f.type, val_str))
            out:write("    ")
            for i = 1, total do
                local byte_idx = offset + i
                out:write(string.format("0x%02X", blob:byte(byte_idx)))
                if byte_idx < #blob then out:write(", ") end
            end
            out:write("\n")
            offset = offset + total
        end
        
        out:write("};\n\n")
        
        -- Cast macro
        out:write(string.format("#define %s_PKT  ((const %s_packet_t*)%s_bin)\n",
            name_upper, cp.record_name, cp.instance_name))
        out:write(string.format("#define %s_DATA ((const %s_wire_t*)&%s_PKT->data)\n\n",
            name_upper, cp.record_name, name_upper))
    end
    
    out:close()
    print("Generated binary const packets: " .. output_path)
end
--------------------------------------------------------------------------------
-- BINARY HEADER GENERATION (embeddable const array)
--------------------------------------------------------------------------------

function M.GENERATE_BINARY_HEADER(output_path, blob)
    -- Generate binary schema blob if not provided
    if not blob then
        blob = M.GENERATE_BINARY()
    end

    output_path = output_path or (current_file.name .. "_bin.h")
    local name_upper = current_file.name:upper()

    local out = io.open(output_path, "w")
    if not out then
        error("Cannot open output file: " .. output_path)
    end

    -- ----------------------------------------------------------------
    -- Header
    -- ----------------------------------------------------------------
    out:write("// " .. output_path .. "\n")
    out:write("// Generated binary schema and const packets - DO NOT EDIT\n")
    out:write("#pragma once\n\n")
    out:write("#include <stdint.h>\n")
    out:write(string.format("#include \"%s.h\"\n\n", current_file.name))

    -- ----------------------------------------------------------------
    -- Schema binary blob
    -- ----------------------------------------------------------------
    out:write("// ============ SCHEMA BINARY ============\n")
    out:write(string.format("#define %s_BIN_SIZE       %d\n", name_upper, #blob))
    out:write(string.format("#define %s_RECORD_COUNT   %d\n\n", name_upper, #current_file.records))

    out:write(string.format("static const uint8_t %s_schema_bin[%d] = {\n",
        current_file.name, #blob))
    for i = 1, #blob, 16 do
        out:write("    ")
        for j = i, math.min(i + 15, #blob) do
            out:write(string.format("0x%02X", blob:byte(j)))
            if j < #blob then out:write(", ") end
        end
        out:write("\n")
    end
    out:write("};\n")

    -- ----------------------------------------------------------------
    -- Const packet blobs + cast macros
    -- ----------------------------------------------------------------
    if #current_file.const_packets > 0 then
        out:write("\n// ============ CONST PACKETS ============\n")

        for _, cp in ipairs(current_file.const_packets) do
            local cp_blob   = serialize_const_packet(cp)
            local rec       = find_record(cp.record_name)
            local inst_upper = cp.instance_name:upper()

            -- Size define
            out:write(string.format("\n#define %s_SIZE  %d\n", inst_upper, #cp_blob))

            -- Binary blob with annotated comments
            out:write(string.format("static const uint8_t %s_bin[%d] = {\n",
                cp.instance_name, #cp_blob))

            -- Header bytes
            out:write("    // header: timestamp(8) + schema_hash(4) + seq(2) + source_node(2)\n")
            out:write("    ")
            for i = 1, 16 do
                out:write(string.format("0x%02X", cp_blob:byte(i)))
                if i < #cp_blob then out:write(", ") end
            end
            out:write("\n")

            -- Data field bytes with comments
            local offset = 16
            for _, f in ipairs(rec.fields) do
                local fsize = resolve_field_size(f.type)
                local count = f.array_size or 1
                local total = fsize * count
                local val   = cp.fields[f.name]
                if val == nil then val = 0 end

                local val_str
                if f.array_size then
                    val_str = "array"
                elseif f.type == "float" or f.type == "double" then
                    val_str = string.format("%g", val)
                else
                    val_str = tostring(val)
                end

                out:write(string.format("    // %s (%s) = %s\n", f.name, f.type, val_str))
                out:write("    ")
                for i = 1, total do
                    local byte_idx = offset + i
                    out:write(string.format("0x%02X", cp_blob:byte(byte_idx)))
                    if byte_idx < #cp_blob then out:write(", ") end
                end
                out:write("\n")
                offset = offset + total
            end

            out:write("};\n\n")

            -- Cast macros so callers can treat the blob as a typed packet
            out:write(string.format(
                "#define %s_PKT  ((const %s_packet_t*)%s_bin)\n",
                inst_upper, cp.record_name, cp.instance_name))
            out:write(string.format(
                "#define %s_DATA ((const %s_wire_t*)&%s_PKT->data)\n",
                inst_upper, cp.record_name, inst_upper))
        end
    end

    out:close()
    print("Generated binary header: " .. output_path)
end

--------------------------------------------------------------------------------
-- FFI MODULE GENERATION (LuaJIT FFI bindings)
--------------------------------------------------------------------------------

-- Resolve a DSL type to its FFI cdef wire type (used inside packed structs)
local function resolve_ffi_wire_ctype(ftype)
    if type_cnames[ftype] then
        return type_cnames[ftype]
    end
    for _, e in ipairs(current_file.enums) do
        if e.name == ftype then return "int32_t" end  -- enums are int32 on wire
    end
    for _, f in ipairs(current_file.fixed) do
        if f.name == ftype then return ftype .. "_t" end
    end
    for _, s in ipairs(current_file.strings) do
        if s.name == ftype then return ftype .. "_t" end
    end
    for _, p in ipairs(current_file.pointers) do
        if p.name == ftype then return "uint64_t" end  -- fixed 8 bytes on wire
    end
    for _, st in ipairs(current_file.structs) do
        if st.name == ftype then return ftype .. "_t" end
    end
    for _, r in ipairs(current_file.records) do
        if r.name == ftype then return ftype .. "_wire_t" end
    end
    return ftype .. "_t"
end

-- Format a Lua literal for FFI const packet initializer
local function format_ffi_value(ftype, value)
    if ftype == "float" or ftype == "double" then
        local s = string.format("%g", value)
        if not s:find("[%.eE]") then s = s .. ".0" end
        return s
    elseif ftype == "bool" then
        return value and "true" or "false"
    else
        return tostring(value)
    end
end

function M.GENERATE_FFI(output_path)
    output_path = output_path or (current_file.name .. "_ffi.lua")

    local out = io.open(output_path, "w")
    if not out then
        error("Cannot open output file: " .. output_path)
    end

    local fname = current_file.name

    out:write("-- " .. output_path .. "\n")
    out:write("-- Generated by avro_dsl.lua GENERATE_FFI - DO NOT EDIT\n")
    out:write("local ffi = require(\"ffi\")\n")
    out:write("local M = {}\n\n")

    -- ----------------------------------------------------------------
    -- ffi.cdef block
    -- ----------------------------------------------------------------
    out:write("ffi.cdef[[\n")

    -- Wire header
    out:write("// Wire header (16 bytes)\n")
    out:write(string.format(
        "typedef struct __attribute__((packed)) {\n"
        .. "    double      timestamp;\n"
        .. "    uint32_t    schema_hash;\n"
        .. "    uint16_t    seq;\n"
        .. "    uint16_t    source_node;\n"
        .. "} %s_wire_header_t;\n\n", fname))

    -- Enums
    if #current_file.enums > 0 then
        out:write("// Enums (wire representation: int32_t)\n")
        for _, e in ipairs(current_file.enums) do
            out:write(string.format("typedef int32_t %s_t;\n", e.name))
            for _, v in ipairs(e.values) do
                out:write(string.format("static const int32_t %s_%s = %d;\n",
                    upper_name(e.name), v.name, v.val))
            end
            out:write("\n")
        end
    end

    -- Fixed arrays
    if #current_file.fixed > 0 then
        out:write("// Fixed arrays\n")
        for _, f in ipairs(current_file.fixed) do
            out:write(string.format(
                "typedef struct { uint8_t data[%d]; } %s_t;\n", f.size, f.name))
        end
        out:write("\n")
    end

    -- Strings
    if #current_file.strings > 0 then
        out:write("// Fixed strings\n")
        for _, s in ipairs(current_file.strings) do
            out:write(string.format(
                "typedef struct __attribute__((packed)) {\n"
                .. "    char     buffer[%d];\n"
                .. "    uint16_t length;\n"
                .. "    uint16_t max_length;\n"
                .. "} %s_t;\n\n", s.length, s.name))
        end
    end

    -- Pointers (wire format uses uint64_t, not void*)
    if #current_file.pointers > 0 then
        out:write("// Pointers (wire: fixed 8-byte uint64_t)\n")
        for _, p in ipairs(current_file.pointers) do
            out:write(string.format(
                "typedef struct { uint64_t ptr; } %s_t;\n", p.name))
        end
        out:write("\n")
    end

    -- Structs (packed)
    if #current_file.structs > 0 then
        out:write("// Structs\n")
        for _, st in ipairs(current_file.structs) do
            out:write(string.format(
                "typedef struct __attribute__((packed)) {\n"))
            for _, f in ipairs(st.fields) do
                local ctype = resolve_ffi_wire_ctype(f.type)
                if f.array_size then
                    out:write(string.format("    %s %s[%d];\n", ctype, f.name, f.array_size))
                else
                    out:write(string.format("    %s %s;\n", ctype, f.name))
                end
            end
            out:write(string.format("} %s_t;\n\n", st.name))
        end
    end

    -- Records: wire_t (data only) and packet_t (header + data)
    if #current_file.records > 0 then
        out:write("// Wire records (packed data only)\n")
        for _, r in ipairs(current_file.records) do
            out:write(string.format(
                "typedef struct __attribute__((packed)) {\n"))
            for _, f in ipairs(r.fields) do
                local ctype = resolve_ffi_wire_ctype(f.type)
                if f.array_size then
                    out:write(string.format("    %s %s[%d];\n", ctype, f.name, f.array_size))
                else
                    out:write(string.format("    %s %s;\n", ctype, f.name))
                end
            end
            out:write(string.format("} %s_wire_t;\n\n", r.name))
        end

        out:write("// Packets (header + wire data)\n")
        for _, r in ipairs(current_file.records) do
            out:write(string.format(
                "typedef struct __attribute__((packed)) {\n"
                .. "    %s_wire_header_t header;\n"
                .. "    %s_wire_t        data;\n"
                .. "} %s_packet_t;\n\n", fname, r.name, r.name))
        end
    end

    out:write("]]\n\n")

    -- ----------------------------------------------------------------
    -- Records metadata table
    -- ----------------------------------------------------------------
    out:write("-- Record metadata\n")
    out:write("M.records = {\n")
    for _, r in ipairs(current_file.records) do
        local rhash = record_hash(r.name)
        local wire_size = compute_container_size(r)
        local packet_size = 16 + wire_size  -- 16-byte header
        out:write(string.format("    [\"%s\"] = {\n", r.name))
        out:write(string.format("        schema_hash  = 0x%08X,\n", rhash))
        out:write(string.format("        wire_size    = %d,\n", wire_size))
        out:write(string.format("        packet_size  = %d,\n", packet_size))
        out:write(string.format("        packet_ct    = ffi.typeof(\"%s_packet_t\"),\n", r.name))
        out:write(string.format("        wire_ct      = ffi.typeof(\"%s_wire_t\"),\n", r.name))
        out:write("    },\n")
    end
    out:write("}\n\n")

    -- Hash-to-name reverse lookup
    out:write("-- Hash to record name lookup\n")
    out:write("M.hash_to_name = {\n")
    for _, r in ipairs(current_file.records) do
        local rhash = record_hash(r.name)
        out:write(string.format("    [0x%08X] = \"%s\",\n", rhash, r.name))
    end
    out:write("}\n\n")

    -- ----------------------------------------------------------------
    -- Helper functions
    -- ----------------------------------------------------------------
    out:write("--- Initialise a packet header for the given record.\n")
    out:write("-- @param pkt        cdata packet (e.g. from M.new_packet)\n")
    out:write("-- @param record_name string key into M.records\n")
    out:write("-- @param source_node uint16 originating node id\n")
    out:write("function M.packet_init(pkt, record_name, source_node)\n")
    out:write("    local info = M.records[record_name]\n")
    out:write("    assert(info, \"unknown record: \" .. tostring(record_name))\n")
    out:write("    pkt.header.schema_hash = info.schema_hash\n")
    out:write("    pkt.header.timestamp   = 0.0\n")
    out:write("    pkt.header.seq         = 0\n")
    out:write("    pkt.header.source_node = source_node or 0\n")
    out:write("    return pkt.data\n")
    out:write("end\n\n")

    out:write("--- Verify a packet's schema_hash matches the expected record.\n")
    out:write("-- @return pkt.data on success, nil on mismatch\n")
    out:write("function M.packet_verify(pkt, record_name)\n")
    out:write("    local info = M.records[record_name]\n")
    out:write("    if not info then return nil end\n")
    out:write("    if pkt.header.schema_hash ~= info.schema_hash then return nil end\n")
    out:write("    return pkt.data\n")
    out:write("end\n\n")

    out:write("--- Allocate a new zero-initialised packet for the given record.\n")
    out:write("function M.new_packet(record_name)\n")
    out:write("    local info = M.records[record_name]\n")
    out:write("    assert(info, \"unknown record: \" .. tostring(record_name))\n")
    out:write("    return ffi.new(info.packet_ct)\n")
    out:write("end\n\n")

    -- ----------------------------------------------------------------
    -- Const packets
    -- ----------------------------------------------------------------
    if #current_file.const_packets > 0 then
        out:write("-- ============ CONST PACKETS ============\n")
        out:write("M.const_packets = {}\n\n")

        for _, cp in ipairs(current_file.const_packets) do
            local rec = find_record(cp.record_name)
            if not rec then
                error("GENERATE_FFI: unknown record '" .. cp.record_name .. "'")
            end

            out:write(string.format("do\n"))
            out:write(string.format("    local pkt = ffi.new(\"%s_packet_t\")\n", cp.record_name))
            -- Header
            out:write(string.format("    pkt.header.schema_hash = 0x%08X\n", record_hash(cp.record_name)))
            out:write("    pkt.header.timestamp   = 0.0\n")
            out:write("    pkt.header.seq         = 0\n")
            out:write(string.format("    pkt.header.source_node = %d\n", cp.source_node))
            -- Data fields
            for _, f in ipairs(rec.fields) do
                local val = cp.fields[f.name]
                if val == nil then val = 0 end
                if f.array_size then
                    if type(val) == "table" then
                        for j, v in ipairs(val) do
                            out:write(string.format("    pkt.data.%s[%d] = %s\n",
                                f.name, j - 1, format_ffi_value(f.type, v)))
                        end
                    else
                        for j = 0, f.array_size - 1 do
                            out:write(string.format("    pkt.data.%s[%d] = %s\n",
                                f.name, j, format_ffi_value(f.type, val)))
                        end
                    end
                else
                    out:write(string.format("    pkt.data.%s = %s\n",
                        f.name, format_ffi_value(f.type, val)))
                end
            end
            out:write(string.format("    M.const_packets[\"%s\"] = pkt\n", cp.instance_name))
            out:write("end\n\n")
        end
    end

    out:write("return M\n")
    out:close()
    print("Generated FFI module: " .. output_path)
end

function M.GENERATE_ALL(base_path)
    base_path = base_path or current_file.name

    M.GENERATE(base_path .. ".h")
    local blob = M.GENERATE_BINARY(base_path .. ".bin")
    -- Single _bin.h contains both schema blob and all const packets
    M.GENERATE_BINARY_HEADER(base_path .. "_bin.h", blob)
    M.GENERATE_FFI(base_path .. "_ffi.lua")
end
--------------------------------------------------------------------------------
-- MODULE EXPORT
--------------------------------------------------------------------------------

function M.export_globals()
    _G.FILE            = M.FILE
    _G.INCLUDE_BRACKET = M.INCLUDE_BRACKET
    _G.INCLUDE_STRING  = M.INCLUDE_STRING
    _G.ENUM            = M.ENUM
    _G.VALUE           = M.VALUE
    _G.END_ENUM        = M.END_ENUM
    _G.FIXED           = M.FIXED
    _G.STRING          = M.STRING
    _G.POINTER         = M.POINTER
    _G.STRUCT          = M.STRUCT
    _G.RECORD          = M.RECORD
    _G.FIELD           = M.FIELD
    _G.END_STRUCT      = M.END_STRUCT
    _G.END_RECORD      = M.END_RECORD
    _G.CONST_PACKET    = M.CONST_PACKET
    _G.SET             = M.SET
    _G.END_CONST_PACKET = M.END_CONST_PACKET
    _G.GENERATE        = M.GENERATE
    _G.GENERATE_BINARY = M.GENERATE_BINARY
    _G.GENERATE_BINARY_HEADER = M.GENERATE_BINARY_HEADER
    _G.GENERATE_CONST_PACKETS = M.GENERATE_CONST_PACKETS
    _G.GENERATE_CONST_PACKETS_BINARY = M.GENERATE_CONST_PACKETS_BINARY
    _G.GENERATE_FFI    = M.GENERATE_FFI
    _G.GENERATE_ALL    = M.GENERATE_ALL
end

return M