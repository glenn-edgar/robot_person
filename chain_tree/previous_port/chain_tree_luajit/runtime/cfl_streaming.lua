-- ============================================================================
-- cfl_streaming.lua
-- ChainTree LuaJIT Runtime — streaming port and packet matching helpers
-- Mirrors avro_common.c, cfl_streaming_support.h port/matching logic
-- ============================================================================

local M = {}

local ffi_ok, ffi = pcall(require, "ffi")

local defs = require("cfl_definitions")

-- ============================================================================
-- Port decode from node_data
--
-- DSL writes port tables as: { schema_hash, handler_id, event_id }
-- This reads them from node_dict paths like "inport" or "column_data.request_port"
-- ============================================================================

function M.decode_port(handle, node_idx, path)
    local common = require("cfl_common")
    local port_data = common.get_node_data_field(handle, node_idx, path)
    if not port_data then return nil end
    return {
        schema_hash = port_data.schema_hash or 0,
        handler_id  = port_data.handler_id or 0,
        event_id    = port_data.event_id or 0,
    }
end

-- ============================================================================
-- Schema hash extraction from packet data
--
-- Packets can be:
--   1. FFI cdata with .header.schema_hash (generated _ffi.lua types)
--   2. Lua table with .schema_hash or .header.schema_hash
--
-- The Avro wire header layout (all packets):
--   offset 0:  double   timestamp     (8 bytes)
--   offset 8:  uint32   schema_hash   (4 bytes)
--   offset 12: uint16   seq           (2 bytes)
--   offset 14: uint16   source_node   (2 bytes)
-- ============================================================================

-- FFI definition for reading raw packet headers (only defined once)
if ffi_ok then
    pcall(function()
        ffi.cdef[[
            typedef struct __attribute__((packed)) {
                double      timestamp;
                uint32_t    schema_hash;
                uint16_t    seq;
                uint16_t    source_node;
            } cfl_avro_header_t;
        ]]
    end)
end

function M.get_schema_hash(packet)
    if packet == nil then return nil end

    -- Lua table packet
    if type(packet) == "table" then
        if packet.schema_hash then return packet.schema_hash end
        if packet.header and packet.header.schema_hash then
            return packet.header.schema_hash
        end
        return nil
    end

    -- FFI cdata packet — try .header.schema_hash first (typed packet)
    if ffi_ok and type(packet) == "cdata" then
        local ok, hash = pcall(function() return packet.header.schema_hash end)
        if ok then return hash end
        -- Fall back to casting raw pointer as header
        local ok2, hash2 = pcall(function()
            local hdr = ffi.cast("cfl_avro_header_t*", packet)
            return hdr.schema_hash
        end)
        if ok2 then return hash2 end
    end

    return nil
end

function M.get_source_node(packet)
    if packet == nil then return nil end
    if type(packet) == "table" then
        if packet.source_node then return packet.source_node end
        if packet.header and packet.header.source_node then
            return packet.header.source_node
        end
        return nil
    end
    if ffi_ok and type(packet) == "cdata" then
        local ok, val = pcall(function() return packet.header.source_node end)
        if ok then return val end
    end
    return nil
end

-- ============================================================================
-- Event matching (mirrors cfl_streaming_event_matches)
--
-- Returns true if the event is a streaming data event that matches the port.
-- ============================================================================

function M.event_matches(event_type, event_id, event_data, port)
    if not port then return false end
    if event_type ~= defs.CFL_EVENT_TYPE_STREAMING_DATA then return false end
    if event_id ~= port.event_id then return false end

    local hash = M.get_schema_hash(event_data)
    if not hash then return false end

    -- Handle signed/unsigned hash comparison (DSL may emit signed int32)
    local port_hash = port.schema_hash
    if port_hash < 0 then port_hash = port_hash + 0x100000000 end
    if hash < 0 then hash = hash + 0x100000000 end

    return hash == port_hash
end

-- ============================================================================
-- Collected packets event matching
-- ============================================================================

function M.collected_event_matches(event_type, event_id, expected_event_id)
    return event_type == defs.CFL_EVENT_TYPE_STREAMING_COLLECTED_PACKETS
       and event_id == expected_event_id
end

-- ============================================================================
-- Send streaming data event
-- ============================================================================

function M.send_streaming_event(handle, target_node, event_id, packet_data)
    local eq = require("cfl_event_queue")
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
        target_node, defs.CFL_EVENT_TYPE_STREAMING_DATA,
        event_id, packet_data)
end

function M.send_collected_event(handle, target_node, event_id, container)
    local eq = require("cfl_event_queue")
    eq.send(handle.event_queue, defs.CFL_EVENT_PRIORITY_LOW,
        target_node, defs.CFL_EVENT_TYPE_STREAMING_COLLECTED_PACKETS,
        event_id, container)
end

return M
