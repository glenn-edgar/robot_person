local ColumnFlow = require("lua_support.column_flow")
local fnv1a      = require("lua_support.fnv1a")
local Streaming = setmetatable({}, { __index = ColumnFlow })
Streaming.__index = Streaming

--------------------------------------------------------------------------------
-- FNV-1a 32-BIT HASH (inlined — matches avro_dsl.lua and C runtime)
--------------------------------------------------------------------------------
--[[
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
    if hash < 0 then
        hash = hash + 0x100000000
    end
    return hash
end
--]]
--------------------------------------------------------------------------------

function Streaming.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, Streaming)
end

function Streaming:make_port(file_name, record_name, handler_id, event)
    if type(file_name) ~= "string" then
        error("file_name must be a string (e.g. 'stream_test_1')")
    end
    if type(record_name) ~= "string" then
        error("record_name must be a string (e.g. 'accelerometer_reading')")
    end
    if type(handler_id) ~= "number" then
        error("handler_id must be a number")
    end
    if type(event) ~= "string" then
        error("event must be a string")
    end
    local event_id    = self.ctb:register_event(event)
    local schema_hash = fnv1a.schema_hash(file_name, record_name)
    return { schema_hash = schema_hash, handler_id = handler_id, event_id = event_id }
end


function Streaming:asm_streaming_emit_packet(aux_function, aux_function_data, event_column, outport)
    local event_column_id = self.ctb:get_node_index(event_column)
    local node_data = {
        aux_data = aux_function_data,
        event_id = outport.event_id,
        outport = outport,
        event_column = event_column_id,
    }
    self:asm_one_shot_handler(aux_function, node_data)
end

function Streaming:asm_streaming_sink_packet(aux_function, aux_function_data, inport)
    local node_data = {
        aux_data = aux_function_data,
        event_id = inport.event_id,
        inport = inport,
    }
    self:define_column_link(
        "CFL_STREAMING_SINK_PACKET",
        "CFL_STREAMING_SINK_PACKET_INIT",
        aux_function,
        "CFL_STREAMING_SINK_PACKET_TERM",
        node_data
    )
end

function Streaming:asm_streaming_transform_packet(aux_function, aux_function_data, inport, outport, output_event_column)
    local output_event_column_id = self.ctb:get_node_index(output_event_column)
    local node_data = {
        aux_data = aux_function_data,
        event_id = inport.event_id,
        inport = inport,
        output_event_id = outport.event_id,
        outport = outport,
        output_event_column_id = output_event_column_id,
    }
    self:define_column_link(
        "CFL_STREAMING_TRANSFORM_PACKET",
        "CFL_STREAMING_TRANSFORM_PACKET_INIT",
        aux_function,
        "CFL_STREAMING_TRANSFORM_PACKET_TERM",
        node_data
    )
end

function Streaming:asm_streaming_filter_packet(aux_function, aux_function_data, inport)
    local node_data = {
        aux_data = aux_function_data,
        event_id = inport.event_id,
        inport = inport,
    }
    self:define_column_link(
        "CFL_STREAMING_FILTER_PACKET",
        "CFL_STREAMING_FILTER_PACKET_INIT",
        aux_function,
        "CFL_STREAMING_FILTER_PACKET_TERM",
        node_data
    )
end

--- Collector node - multiple verified inports, event-only output (no schema verification).
function Streaming:asm_streaming_collect_packets(aux_function, aux_function_data, inports, output_event, output_event_column)
    local output_event_column_id = self.ctb:get_node_index(output_event_column)
    local output_event_id = self.ctb:register_event(output_event)
    local node_data = {
        aux_data = aux_function_data,
        inports = inports,
        output_event_id = output_event_id,
        output_event_column_id = output_event_column_id,
    }
    self:define_column_link(
        "CFL_STREAMING_COLLECT_PACKETS",
        "CFL_STREAMING_COLLECT_PACKETS_INIT",
        aux_function,
        "CFL_STREAMING_COLLECT_PACKETS_TERM",
        node_data
    )
end

function Streaming:asm_streaming_tap_packet(aux_function, aux_function_data, inport)
    local node_data = {
        aux_data = aux_function_data,
        event_id = inport.event_id,
        inport = inport,
    }
    self:define_column_link(
        "CFL_STREAMING_TAP_PACKET",
        "CFL_STREAMING_TAP_PACKET_INIT",
        aux_function,
        "CFL_STREAMING_TAP_PACKET_TERM",
        node_data
    )
end

--- Sink for collector output packets - no port/schema verification, just event matching.
function Streaming:asm_streaming_sink_collected_packets(aux_function, aux_function_data, event_name)
    local event_id = self.ctb:register_event(event_name)
    local node_data = {
        aux_data = aux_function_data,
        event_id = event_id,
    }
    self:define_column_link(
        "CFL_STREAMING_SINK_COLLECTED_PACKETS",
        "CFL_STREAMING_SINK_COLLECTED_PACKETS_INIT",
        aux_function,
        "CFL_STREAMING_SINK_COLLECTED_PACKETS_TERM",
        node_data
    )
end

--- Verify packet with user-defined test function.
function Streaming:asm_streaming_verify_packet(aux_function, aux_function_data, inport,
                                                reset_flag, error_fn, error_data)
    if reset_flag == nil then reset_flag = false end
    error_fn = error_fn or "CFL_NULL"

    local node_data = {
        aux_data = aux_function_data,
        inport = inport,
        user_aux_function = aux_function,
    }
    self:asm_verify(
        "CFL_STREAMING_VERIFY_PACKET",
        node_data,
        reset_flag,
        error_fn,
        error_data
    )
end

return Streaming