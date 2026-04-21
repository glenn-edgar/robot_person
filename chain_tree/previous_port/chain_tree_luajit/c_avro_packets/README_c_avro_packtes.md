# Avro DSL for Embedded C

A Lua DSL that generates C headers and optional binary blobs for fixed-layout message exchange in embedded systems. Inspired by Apache Avro's concept of schema-defined serialization, redesigned from scratch for resource-constrained microcontrollers.

## What It Generates

| Output | Generator | Description |
|--------|-----------|-------------|
| `<n>.h` | `GENERATE()` | C header with structs, packed wire types, packet encode/verify/dispatch API, and per-record hash constants |
| `<n>.bin` | `GENERATE_BINARY()` | Binary schema blob for file-based operations |
| `<n>_bin.h` | `GENERATE_BINARY_HEADER()` | Schema binary blob **and** all const packet blobs in a single file |
| `<n>_bin.h` | `GENERATE_CONST_PACKETS()` | Pre-initialized packets as C struct initializers (standalone) |
| `<n>_bin.h` | `GENERATE_CONST_PACKETS_BINARY()` | Pre-initialized packets as raw `uint8_t[]` blobs with cast macros (standalone) |
| `.h` + `.bin` + `_bin.h` | `GENERATE_ALL()` | Convenience: runs `GENERATE` + `GENERATE_BINARY` + `GENERATE_BINARY_HEADER` |

Most users only need `GENERATE()`. The const packet generators are for pre-baked default/template packets in flash. Runtime packet creation requires only the `.h`.

### Output File Summary

`GENERATE_ALL()` produces exactly three files:

| File | Contents |
|------|----------|
| `<n>.h` | C types, wire structs, packet init/verify/dispatch helpers |
| `<n>.bin` | Loadable binary schema blob |
| `<n>_bin.h` | Schema `uint8_t[]` blob **plus** any const packet blobs and cast macros |

The `_bin.h` file is the single authoritative binary header — it always contains the schema blob, and if any `CONST_PACKET` definitions exist, their binary blobs and cast macros are appended in the same file under a `// ============ CONST PACKETS ============` section.

## Quick Start

### Define a Schema
```lua
-- sensor_msgs.lua
require("avro_dsl").export_globals()

FILE("sensor_msgs")
INCLUDE_BRACKET("stdint.h")
INCLUDE_BRACKET("stdbool.h")
INCLUDE_BRACKET("string.h")

FIXED("mac_addr", 6)

ENUM("sensor_type")
    VALUE("TEMPERATURE", 0)
    VALUE("PRESSURE",    1)
    VALUE("HUMIDITY",    2)
END_ENUM()

RECORD("sensor_reading")
    FIELD("sensor_id",   "uint16")
    FIELD("sensor_type", "sensor_type")
    FIELD("value",       "float")
    FIELD("timestamp",   "double")
END_RECORD()

RECORD("device_status")
    FIELD("node_id",  "uint8")
    FIELD("uptime",   "uint32")
    FIELD("mac",      "mac_addr")
    FIELD("healthy",  "bool")
END_RECORD()

-- Optional: define pre-initialized packet templates
CONST_PACKET("sensor_reading", "default_sensor", 0)
    SET("sensor_id", 0x0042)
    SET("value", 25.5)
    SET("timestamp", 0.0)
END_CONST_PACKET()

-- Generates sensor_msgs.h + sensor_msgs.bin + sensor_msgs_bin.h
-- sensor_msgs_bin.h contains both the schema blob and the default_sensor const packet
GENERATE_ALL()
```

### Run It
```bash
luajit sensor_msgs.lua
# => Generated: sensor_msgs.h
# => Generated binary: sensor_msgs.bin (N bytes)
# => Generated binary header: sensor_msgs_bin.h
```

### Use the Generated C API
```c
#include "sensor_msgs.h"

// === Send side ===
sensor_reading_packet_t pkt;
sensor_reading_wire_t* data = sensor_reading_packet_init(&pkt, my_node_id);
data->sensor_id   = 0x0042;
data->sensor_type = SENSOR_TYPE_TEMPERATURE;
data->value       = 23.5f;
data->timestamp   = get_time();

// Transport layer sets pkt.header.timestamp and pkt.header.seq before sending
send(fd, &pkt, sizeof(pkt));

// === Receive side ===
sensor_reading_packet_t rx_buf;
recv(fd, &rx_buf, sizeof(rx_buf));

const sensor_reading_wire_t* rx = sensor_reading_packet_verify(&rx_buf);
if (rx) {
    printf("Sensor %u: %.2f\n", rx->sensor_id, rx->value);
}

// === Generic dispatch (when record type is unknown) ===
uint16_t source;
const void* payload;
int index = sensor_msgs_packet_dispatch(&rx_buf, &source, &payload);
switch (index) {
    case 0: handle_reading((const sensor_reading_wire_t*)payload); break;
    case 1: handle_status((const device_status_wire_t*)payload);   break;
    default: break;  // unknown or invalid
}
```

## DSL Reference

### File Setup

| Command | Description |
|---------|-------------|
| `FILE(name)` | Start a schema definition. Determines output filenames. |
| `INCLUDE_BRACKET(header)` | Add `#include <header>` to generated `.h` |
| `INCLUDE_STRING(header)` | Add `#include "header"` to generated `.h` |

### Type Definitions

#### Primitives

| DSL Type | C Type | Size |
|----------|--------|------|
| `uint8` / `int8` | `uint8_t` / `int8_t` | 1 |
| `uint16` / `int16` | `uint16_t` / `int16_t` | 2 |
| `uint32` / `int32` | `uint32_t` / `int32_t` | 4 |
| `uint64` / `int64` | `uint64_t` / `int64_t` | 8 |
| `float` | `float` | 4 |
| `double` | `double` | 8 |
| `bool` | `bool` | 1 |

#### Composites
```lua
FIXED("mac_addr", 6)          -- typedef uint8_t mac_addr_t[6];

STRING("label", 32)           -- struct with char buffer[32], uint16 length, uint16 max_length

POINTER("user_data")          -- struct wrapping void*

ENUM("mode")                  -- typedef enum { MODE_IDLE = 0, ... } mode_t;
    VALUE("IDLE", 0)
    VALUE("RUN",  1)
END_ENUM()

STRUCT("config")              -- plain typedef struct (no wire packet generated)
    FIELD("threshold", "float")
    FIELD("enabled",   "bool")
END_STRUCT()
```

#### Records (Wire Packet Types)

Records are the primary message types. Each record gets its own unique schema hash and produces a native `_t` struct, a packed `_wire_t` struct, a `_packet_t` (header + wire data), and encode/verify functions.
```lua
RECORD("telemetry")
    FIELD("altitude", "float")
    FIELD("speed",    "float")
    FIELD("heading",  "uint16")
    FIELD("gps_fix",  "bool")
END_RECORD()
```

Array fields use the optional third argument:
```lua
FIELD("samples",  "float",  8)    -- float samples[8]
FIELD("channels", "uint16", 4)    -- uint16_t channels[4]
```

Records vs. structs: `STRUCT` produces only a plain C typedef. `RECORD` produces a full wire packet with header, verification, dispatch, and cross-platform wire conversion. Use `STRUCT` for local data structures and `RECORD` for anything sent over a wire.

### Generators

| Command | Output | When to Use |
|---------|--------|-------------|
| `GENERATE()` | `<n>.h` | Always — this is the primary output |
| `GENERATE_BINARY()` | `<n>.bin` | Binary schema blob for file operations |
| `GENERATE_BINARY_HEADER()` | `<n>_bin.h` | Schema blob + const packets in one file |
| `GENERATE_ALL()` | `.h` + `.bin` + `_bin.h` | Recommended: all three outputs in one call |
| `GENERATE_CONST_PACKETS()` | `<n>_bin.h` | Standalone: C struct initializers only |
| `GENERATE_CONST_PACKETS_BINARY()` | `<n>_bin.h` | Standalone: raw byte arrays only |

**Preferred workflow:** use `GENERATE_ALL()`. It produces the `.h`, `.bin`, and a unified `_bin.h` that contains both the schema blob and all const packet blobs in a single file.

The standalone `GENERATE_CONST_PACKETS()` and `GENERATE_CONST_PACKETS_BINARY()` are still available when you need const packets without the schema blob, or need C struct initializers instead of binary blobs. Pass explicit output paths if using multiple generators targeting the same filename:
```lua
GENERATE_CONST_PACKETS("sensor_msgs_const.h")
GENERATE_CONST_PACKETS_BINARY("sensor_msgs_raw.h")
```

### Const Packets (Pre-Initialized Templates)

Define pre-initialized packet instances for ROM storage or as copy templates. These are defined after your records:
```lua
CONST_PACKET("sensor_reading", "default_sensor", 0)
    SET("sensor_id", 0x0042)
    SET("value", 25.5)
    SET("timestamp", 0.0)
END_CONST_PACKET()
```

| Command | Description |
|---------|-------------|
| `CONST_PACKET(record, name, source_node)` | Start a const packet. `source_node` defaults to 0. |
| `SET(field, value)` | Set a data field. Unset fields default to 0. Arrays accept tables: `SET("samples", {1.0, 2.0, 3.0})` |
| `END_CONST_PACKET()` | Finish the const packet definition. |

When using `GENERATE_ALL()` or `GENERATE_BINARY_HEADER()`, const packets are emitted into `_bin.h` immediately after the schema blob:
```c
// ============ SCHEMA BINARY ============
#define SENSOR_MSGS_BIN_SIZE       167
#define SENSOR_MSGS_RECORD_COUNT   2
static const uint8_t sensor_msgs_schema_bin[167] = { ... };

// ============ CONST PACKETS ============
#define DEFAULT_SENSOR_SIZE  36
static const uint8_t default_sensor_bin[36] = {
    // header: timestamp(8) + schema_hash(4) + seq(2) + source_node(2)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, ...
    // sensor_id (uint16) = 66
    0x42, 0x00,
    // value (float) = 25.5
    0x00, 0x00, 0xCC, 0x41,
    ...
};

#define DEFAULT_SENSOR_PKT  ((const sensor_reading_packet_t*)default_sensor_bin)
#define DEFAULT_SENSOR_DATA ((const sensor_reading_wire_t*)&DEFAULT_SENSOR_PKT->data)
```

C usage:
```c
#include "sensor_msgs_bin.h"

// Direct ROM access via cast macros (zero-copy)
printf("value = %f\n", DEFAULT_SENSOR_DATA->value);

// Copy as mutable template
sensor_reading_packet_t pkt;
memcpy(&pkt, default_sensor_bin, DEFAULT_SENSOR_SIZE);
pkt.data.value = new_value;
```

## Wire Format

### Packet Header (16 bytes, packed)
```
Offset  Size  Field         Description
─────────────────────────────────────────────────────
  0      8    timestamp     double — set by transport layer
  8      4    schema_hash   FNV-1a 32-bit per-record hash
 12      2    seq           Sequence number — set by transport layer
 14      2    source_node   Originating node ID (uint16)
```

The header is defined as `<n>_wire_header_t` with a `_Static_assert` enforcing 16 bytes. `timestamp` and `seq` are zeroed by `_packet_init()` — the transport layer fills them before transmission.

### Per-Record Schema Hash

Each record type gets its own unique hash, computed as FNV-1a 32-bit over the string `"<filename>.h:<record_name>"`. For example, given `FILE("sensor_msgs")` and `RECORD("sensor_reading")`, the hash is `fnv1a_32("sensor_msgs.h:sensor_reading")`.

The `schema_hash` field alone uniquely identifies the record type — no separate index field is needed. Verification requires only a single integer comparison.

The FNV-1a implementation is shared across all modules via `lua_support/fnv1a.lua`, which exports two functions:
```lua
local fnv1a = require("lua_support.fnv1a")

fnv1a.fnv1a_32(str)                        -- raw unsigned 32-bit hash
fnv1a.schema_hash(file_name, record_name)  -- signed int32 hash of "<file>.h:<record>"
```

Both `streaming.lua` and `controlled_nodes.lua` use this shared module to guarantee identical hash values across the Lua DSL and C runtime.

### Complete Packet
```
┌──────────────────────────┐
│  <n>_wire_header_t       │  16 bytes
├──────────────────────────┤
│  <record>_wire_t         │  record-specific (packed)
└──────────────────────────┘
```

## Generated API Per Record

Given `RECORD("sensor_reading") ... END_RECORD()`, the `.h` contains:

### Types and Constants
```c
// Per-record schema hash
#define SENSOR_READING_SCHEMA_HASH   0x...U

typedef struct { ... } sensor_reading_t;          // Native struct
typedef struct { ... } sensor_reading_wire_t;     // Packed, fixed-size enums (int32_t)
typedef struct {
    sensor_msgs_wire_header_t header;
    sensor_reading_wire_t     data;
} sensor_reading_packet_t;                        // Complete wire packet
```

### Functions
```c
// Stamp header with per-record hash, return pointer to wire data
sensor_reading_wire_t* sensor_reading_packet_init(
    sensor_reading_packet_t* pkt,
    uint16_t source_node);

// Validate per-record schema hash, return wire data or NULL
const sensor_reading_wire_t* sensor_reading_packet_verify(
    const sensor_reading_packet_t* pkt);

// Native ↔ wire conversion (handles enum sizing differences)
void sensor_reading_to_wire(const sensor_reading_t* src, sensor_reading_wire_t* dst);
void sensor_reading_from_wire(const sensor_reading_wire_t* src, sensor_reading_t* dst);
```

### Schema-Level Functions and Tables
```c
#define SENSOR_MSGS_RECORD_COUNT  2

// Generic dispatch — matches per-record hash, returns record index or -1
int sensor_msgs_packet_dispatch(
    const void* packet_buffer,
    uint16_t* source_node_out,
    const void** data_out);

// Per-record payload and full packet sizes (for buffer allocation)
static const uint16_t sensor_msgs_wire_sizes[SENSOR_MSGS_RECORD_COUNT];
static const uint16_t sensor_msgs_packet_sizes[SENSOR_MSGS_RECORD_COUNT];

// Per-record hash table (for runtime dispatch)
static const uint32_t sensor_msgs_record_hashes[SENSOR_MSGS_RECORD_COUNT];
```

## Cross-Platform Wire Safety

The DSL generates two struct variants per record:

| Variant | Packing | Enum Representation | Use |
|---------|---------|---------------------|-----|
| `_t` | Platform-default | Platform `enum` (varies) | Local computation |
| `_wire_t` | `#pragma pack(push, 1)` | `int32_t` (fixed 4 bytes) | Wire transmission |

This matters when 32-bit and 64-bit systems communicate — `enum` size and struct padding can differ. The `_to_wire()` / `_from_wire()` helpers handle conversion. If all nodes share the same architecture, you can use `_wire_t` directly without conversion.

## ChainTree Streaming Integration

The DSL integrates with the ChainTree streaming subsystem through a Lua assembly layer and a C runtime support library.

### Streaming Ports (`streaming.lua`)

`streaming.lua` provides `make_port` for typed streaming connections. It takes a base filename (without `.h`), record name, handler ID, and event name. The schema hash is computed internally via `lua_support/fnv1a`:
```lua
local Streaming = require("lua_support.streaming")
local ct = Streaming.new(ctb)

-- Create ports (hash computed automatically from file + record name)
local raw_port      = ct:make_port("stream_test_1", "accelerometer_reading",          0, "ACCEL_RAW")
local filtered_port = ct:make_port("stream_test_1", "accelerometer_reading_filtered", 1, "ACCEL_FILTERED")

-- Emit, sink, transform, filter, tap, collect, verify
ct:asm_streaming_emit_packet("GENERATOR", { device_id = 1 }, event_column, raw_port)
ct:asm_streaming_sink_packet("SINK", { sink_message = "received" }, raw_port)
ct:asm_streaming_transform_packet("TRANSFORM", { average = 5 }, raw_port, filtered_port, event_column)
ct:asm_streaming_filter_packet("FILTER", { x = 0.5 }, raw_port)
ct:asm_streaming_tap_packet("TAP", { log_message = "seen" }, raw_port)
ct:asm_streaming_verify_packet("VERIFY", { min_x = 0.0, max_x = 0.5 }, raw_port, true)
```

Ports returned by `make_port` contain `{ schema_hash, handler_id, event_id }`.

### Controlled Node Ports (`controlled_nodes.lua`)

`controlled_nodes.lua` provides `make_control_port` for typed client/server controlled node connections. The signature mirrors `make_port` and uses the same shared FNV-1a hash:
```lua
-- file_name: base name without .h extension
-- record_name: record type name within that file
-- handler_id: buffer slot index
-- event: event name for ChainTree routing
local request_port  = ct:make_control_port("drone_control", "fly_straight_request",  0, "fly_straight_request")
local response_port = ct:make_control_port("drone_control", "fly_straight_response", 1, "fly_straight_response")
```

The two port constructors are intentionally distinct — `make_port` (streaming) and `make_control_port` (controlled nodes) — to prevent accidental cross-use between the two subsystems, even though both compute `{ schema_hash, handler_id, event_id }` with identical hash logic.

### C Runtime Support

The `avro_common.h` / `avro_common.c` runtime provides generic packet operations matching the wire header:
```c
// Generic header (matches all generated _wire_header_t structs)
typedef struct __attribute__((packed)) {
    double      timestamp;     // 8 bytes
    uint32_t    schema_hash;   // 4 bytes — per-record hash
    uint16_t    seq;           // 2 bytes
    uint16_t    source_node;   // 2 bytes
} avro_packet_header_t;       // 16 bytes total

// Port descriptor for event routing
typedef struct {
    uint32_t    schema_hash;   // Per-record hash for matching
    unsigned    handler_id;
    unsigned    event_id;
    void        *packet_pointer;
    void        *data_pointer;
} cfl_port_t;

// Transport layer fills timestamp and seq before send
void cfl_avro_update_packet_header(cfl_runtime_handle_t *runtime, void *packet);

// Matches packet schema_hash against port schema_hash
bool cfl_packet_matches_port(const void *packet, const cfl_port_t *port);
```

## Design Tradeoffs vs. Apache Avro

| | Apache Avro | This DSL |
|---|---|---|
| **Target** | JVM / Big Data | ARM Cortex-M, 32KB flash |
| **Schema format** | JSON | Lua → C headers |
| **Wire format** | Variable-length, compressed | Fixed-layout, packed structs |
| **Field access** | Parse/decode | Direct memory-mapped cast |
| **Schema evolution** | Built-in | None — firmware updates are coordinated |
| **Optional fields** | Yes | No — all fields always present |
| **Compression** | Yes | No — predictability over size |
| **Record identification** | Schema fingerprint | Per-record FNV-1a hash |

These are deliberate choices for deterministic, low-latency messaging on constrained hardware.

## Files

| File | Description |
|------|-------------|
| `avro_dsl.lua` | The DSL generator (LuaJIT and Lua 5.3+ compatible) |
| `avro_common.h` | Runtime generic header type and port matching (inline + declarations) |
| `avro_common.c` | Runtime port matching and header update implementation |
| `lua_support/fnv1a.lua` | Shared FNV-1a 32-bit hash module used by `streaming.lua` and `controlled_nodes.lua` |
| `lua_support/streaming.lua` | ChainTree streaming assembly layer (`make_port`) |
| `lua_support/controlled_nodes.lua` | ChainTree controlled node assembly layer (`make_control_port`) |

## Target Platforms

The wire format is little-endian with packed structs, targeting ARM32, ARM64, and x86. Minimum platform is ARM Cortex-M0+ with 32KB flash and 8KB RAM.

## Requirements

LuaJIT or Lua 5.3+. No external dependencies. The bit-operation compatibility layer is handled internally.

## License

MIT