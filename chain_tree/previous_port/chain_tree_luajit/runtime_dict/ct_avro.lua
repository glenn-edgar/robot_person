local ffi = require("ffi")
local M = {}

-- Schema registry: schema_name -> loaded FFI module
M.schemas = {}

-- Load a schema FFI module by name
-- Tries require("<name>_ffi") first, returns the module
function M.load_schema(name)
    if M.schemas[name] then return M.schemas[name] end
    local ok, mod = pcall(require, name .. "_ffi")
    if not ok then
        error("ct_avro: cannot load schema '" .. name .. "': " .. tostring(mod))
    end
    M.schemas[name] = mod
    return mod
end

-- Create a new packet for a record
function M.new_packet(schema_mod, record_name)
    local rec = schema_mod.records[record_name]
    if not rec then error("ct_avro: unknown record '" .. record_name .. "'") end
    return ffi.new(rec.packet_ctype)
end

-- Initialize a packet's header (schema_hash, source_node, seq=0, timestamp=0)
function M.packet_init(schema_mod, pkt, record_name, source_node)
    local rec = schema_mod.records[record_name]
    pkt.header.schema_hash = rec.schema_hash
    pkt.header.source_node = source_node or 0
    pkt.header.seq = 0
    pkt.header.timestamp = 0
    return pkt.data
end

-- Verify packet's schema_hash matches expected record, return data pointer or nil
function M.packet_verify(schema_mod, pkt, record_name)
    local rec = schema_mod.records[record_name]
    if not rec then return nil end
    if pkt.header.schema_hash ~= rec.schema_hash then return nil end
    return pkt.data
end

-- Check if a packet's schema_hash matches a port's schema_hash
function M.packet_matches_port(pkt, port)
    if not pkt or not port then return false end
    return pkt.header.schema_hash == port.schema_hash
end

-- Check if an event matches an inport (event_id match + schema_hash match)
-- event_data should be a packet (FFI cdata) or nil
function M.event_matches(event_id, event_data, inport)
    if not inport or event_id ~= inport.event_id then return false end
    if event_data == nil then return false end
    -- Check schema_hash in packet header
    if type(event_data) == "cdata" then
        local header = ffi.cast("uint32_t*", event_data)
        -- schema_hash is at offset 8 (after double timestamp)
        -- Actually: header layout is {double timestamp(8), uint32_t schema_hash(4), ...}
        -- Cast to access schema_hash
        local hash_ptr = ffi.cast("uint32_t*", ffi.cast("uint8_t*", event_data) + 8)
        return hash_ptr[0] == inport.schema_hash
    end
    return false
end

-- Update packet header with runtime timestamp and increment seq
function M.update_header(pkt, timestamp)
    pkt.header.timestamp = timestamp or 0
    pkt.header.seq = pkt.header.seq + 1
end

-- Emit a packet as a streaming event into the event queue
-- This is called by streaming builtins and user functions
function M.emit_packet(handle, outport, pkt)
    -- Update header
    M.update_header(pkt, handle.timestamp)
    pkt.header.source_node = 0 -- could be node index but we use ltree strings

    table.insert(handle.event_queue, {
        node_id = outport.event_column_id,  -- ltree of target column
        event_id = outport.event_id,
        event_type = "streaming_data",
        event_data = pkt,
    })
end

-- Emit collected packets container as event
function M.emit_collected(handle, output_event_column_id, output_event_id, container)
    table.insert(handle.event_queue, {
        node_id = output_event_column_id,
        event_id = output_event_id,
        event_type = "streaming_collected",
        event_data = container,
    })
end

return M
