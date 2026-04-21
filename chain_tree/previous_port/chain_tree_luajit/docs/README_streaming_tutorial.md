# Streaming Pipeline Tutorial

ChainTree's streaming subsystem provides a typed packet pipeline for embedded wire protocols. Packets flow through tap → filter → transform → sink nodes, with schema verification at each stage.

## Concepts

- **Port**: Typed connection point defined by schema hash, handler ID, and event ID
- **Packet**: Fixed-layout C struct with an `avro_packet_header_t` prefix (schema hash, sequence number, timestamp, source node)
- **Tap**: Generates packets on a timer or event
- **Sink**: Receives and processes packets
- **Filter**: Passes or blocks packets based on a boolean function
- **Transform**: Reads input packet, produces output packet
- **Collect**: Aggregates packets from multiple sources

## DSL Usage

### Define Ports

```lua
-- make_port(schema_hash, handler_id, event_id)
local port_sensor = ct:make_port("sensor_packet_hash", 0, "CFL_SECOND_EVENT")
local port_motor  = ct:make_port("motor_packet_hash", 1, "CFL_TIMER_EVENT")
```

### Packet Generator (Tap)

```lua
ct:asm_streaming_emit_packet(
    "SENSOR_GENERATOR",          -- user boolean function (generates packet)
    { sample_rate = 10 },        -- function data
    event_column,                -- column that receives the event
    port_sensor                  -- output port
)
```

The boolean function is called each tick. It fills the packet and returns `true` to emit, `false` to skip.

### Packet Sink

```lua
ct:asm_streaming_sink_packet(
    "SENSOR_HANDLER",            -- user boolean function (processes packet)
    { log_level = 1 },           -- function data
    port_sensor                  -- input port (must match generator's port)
)
```

### Packet Filter

```lua
ct:asm_streaming_filter_packet(
    "RANGE_CHECK",               -- user boolean: true=pass, false=block
    { min = 0, max = 100 },
    port_sensor                  -- input port
)
```

### Packet Transform

```lua
ct:asm_streaming_transform_packet(
    "CELSIUS_TO_FAHRENHEIT",     -- user boolean function
    { offset = 32 },
    port_sensor,                 -- input port
    port_motor,                  -- output port
    output_event_column          -- column for output events
)
```

### Packet Collector

```lua
ct:asm_streaming_collect_packets(
    "AGGREGATE_READINGS",        -- user boolean function
    {},
    { port_sensor_a, port_sensor_b },  -- input ports (multiple)
    "COLLECTION_COMPLETE",       -- output event name
    output_event_column          -- column for output events
)
```

### Verified Sink

```lua
ct:asm_streaming_verify_packet(
    "VERIFY_SENSOR",             -- user boolean function
    {},
    port_sensor,                 -- input port
    verify_fn, reset_flag, timeout, error_fn, error_data
)
```

## Complete Pipeline Example

```lua
local function streaming_test(ct, kb_name)
    ct:start_test(kb_name)

    local col = ct:define_column("pipeline", nil, nil, nil, nil, nil, true)

        -- Define ports
        local port_raw = ct:make_port("raw_sensor", 0, "CFL_SECOND_EVENT")
        local port_filtered = ct:make_port("filtered_sensor", 1, "CFL_SECOND_EVENT")

        -- Generator → produces raw sensor packets
        local gen_col = ct:define_column("gen_events")
            ct:asm_streaming_emit_packet("SENSOR_GEN", {}, gen_col, port_raw)
        ct:end_column(gen_col)

        -- Filter → passes only valid readings
        ct:asm_streaming_filter_packet("RANGE_FILTER", {min=0, max=1000}, port_raw)

        -- Sink → processes filtered packets
        ct:asm_streaming_sink_packet("DATA_LOGGER", {}, port_raw)

        ct:asm_wait_time(10.0)
        ct:asm_terminate_system()

    ct:end_column(col)

    ct:end_test()
end
```

## User Function Signatures

All streaming user functions are boolean functions.

### C Signatures
```c
// Sink/Tap/Filter/Transform — process or filter packet
bool my_fn(void *handle, unsigned node_index,
           unsigned event_type, unsigned event_id, void *event_data);
```

### LuaJIT CFL Runtime Signatures
```lua
-- Boolean (sink, tap, filter, transform, collector, collector_sink, verify)
function MY_FN(handle, node_idx, event_type, event_id, event_data)
    -- event_data is FFI cdata packet or Lua table
    -- return true/false
end

-- One-shot (emit packet / generator)
function MY_GENERATOR(handle, node_idx)
    local schema = require("stream_test_1_ffi")
    local pkt = schema.new_packet("accelerometer_reading")
    schema.packet_init(pkt, "accelerometer_reading", node_idx)
    pkt.data.x = 1.0
    -- Emit via streaming helper
    local streaming = require("cfl_streaming")
    local nd = require("cfl_common").get_node_data(handle, node_idx)
    streaming.send_streaming_event(handle, target_node, nd.outport.event_id, pkt)
end
```

## Runtime Implementation (`runtime/`)

The streaming subsystem is implemented across two modules:

### `cfl_streaming.lua` — Port and Packet Matching
- `decode_port(handle, node_idx, path)` — reads port config from JSON IR node_data
- `event_matches(event_type, event_id, event_data, port)` — checks event_type == STREAMING_DATA, event_id match, and schema_hash match
- `get_schema_hash(packet)` — extracts hash from FFI cdata (header offset 8) or Lua table
- `send_streaming_event(handle, target, event_id, packet)` — sends via CFL event queue
- `send_collected_event(handle, target, event_id, container)` — sends collected packets event

### `cfl_builtins.lua` — Streaming Functions
Each streaming node type has init/main/term functions. Init decodes ports from node_data into node_state. Main matches events and dispatches to user boolean. Term clears node_state.

| Function | Init Reads | Main Behavior |
|----------|-----------|---------------|
| `CFL_STREAMING_SINK_PACKET` | `inport` | match → call boolean |
| `CFL_STREAMING_TAP_PACKET` | `inport` | match → call boolean (same as sink) |
| `CFL_STREAMING_FILTER_PACKET` | `inport` | match → call boolean → false=CFL_HALT |
| `CFL_STREAMING_TRANSFORM_PACKET` | `inport`, `outport`, `output_event_column_id` | match → call boolean (user emits on outport) |
| `CFL_STREAMING_COLLECT_PACKETS` | `inports[]`, container config | match any inport → accumulate → emit when full |
| `CFL_STREAMING_SINK_COLLECTED_PACKETS` | `event_id` | match collected event → call boolean → reset container |
| `CFL_STREAMING_VERIFY_PACKET` | `fn_data.inport`, `fn_data.user_aux_function` | delegate to user boolean for matched packets |

### Packet Format

Packets use a 16-byte packed header followed by application-defined fields:

```c
typedef struct __attribute__((packed)) {
    double      timestamp;     // 8 bytes (offset 0)
    uint32_t    schema_hash;   // 4 bytes (offset 8) — FNV-1a of "file.h:record"
    uint16_t    seq;           // 2 bytes (offset 12)
    uint16_t    source_node;   // 2 bytes (offset 14)
} avro_packet_header_t;       // 16 bytes total
```

The Avro DSL generates both C headers and LuaJIT FFI bindings (`_ffi.lua`) with `packet_init()`, `packet_verify()`, and `new_packet()` helpers. Schema hash is `FNV-1a("<file>.h:<record>")`.

### Test Coverage

Tests 19-22 in `dsl_tests/incremental_binary/` exercise all streaming node types:
- Test 19 (`twenty_third_test`): Basic packet emit + verify
- Test 20 (`twenty_fourth_test`): Sink, tap, filter, transform pipeline
- Test 21 (`twenty_fifth_test`): Multi-source collector + sink collected
- Test 22 (`twenty_sixth_test`): Streaming verify packet with reset

Run with: `luajit dsl_tests/incremental_binary/test_cfl.lua 19`

See [avro/README_avro_commands.md](avro/README_avro_commands.md) and [avro/README_c_avro_packtes.md](avro/README_c_avro_packtes.md) for the Avro packet DSL and format details.
