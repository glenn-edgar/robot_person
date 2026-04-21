# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChainTree LuaJIT is a pure-LuaJIT port of the ChainTree control flow framework. It unifies behavior trees, state machines, and sequential control flows into a single LuaJIT execution engine. The C reference implementation lives in `../chain_tree_c/`.

Both versions share the same Lua DSL frontend and JSON intermediate representation (IR).

## Running the DSL Pipeline

### Stage 1: Lua DSL to JSON IR
```bash
./s_build_json.sh <lua_test_file> <output_directory>
```
Requires `luajit`. Sets `LUA_PATH` to resolve `lua_dsl/lua_support/` modules.

### Stage 2: Load JSON IR in LuaJIT runtime
No code generation step needed — the LuaJIT runtime loads JSON IR directly via `cfl_json_loader.lua`.

## ChainTree LuaJIT Runtime (`runtime/`)

Pure Lua modules replacing the C runtime libraries (`runtime_h/`, `runtime_binary/`, `runtime_functions/` in chain_tree_c).

### Usage
```lua
local cfl_runtime = require("cfl_runtime")
local loader      = require("cfl_json_loader")
local builtins    = require("cfl_builtins")
local sm          = require("cfl_state_machine")

-- Load JSON IR
local flash = loader.load("my_test.json")

-- Register built-in + user functions
loader.register_functions(flash, builtins, sm, user_functions)

-- Create and run
local handle = cfl_runtime.create({ delta_time = 0.1, max_ticks = 500 }, flash)
cfl_runtime.reset(handle)
cfl_runtime.add_test(handle, 0)  -- 0-based KB index
cfl_runtime.run(handle)
```

### Module Architecture
```
cfl_runtime.lua          -- Top-level: create, reset, run, destroy
  cfl_engine.lua         -- Engine: KB activation, node execution, flag management
    cfl_tree_walker.lua  -- Iterative DFS tree walker (port of CT_Tree_Walker.c)
  cfl_event_queue.lua    -- Dual-priority ring buffer
  cfl_timer.lua          -- Timer system (second/minute/hour/day events)
  cfl_blackboard.lua     -- Shared mutable blackboard + constant records
  cfl_json_loader.lua    -- Load JSON IR into runtime Lua tables
  cfl_builtins.lua       -- All built-in main/boolean/one-shot functions
  cfl_state_machine.lua  -- State machine functions
  cfl_streaming.lua      -- Streaming port decode, packet matching, schema hash helpers
  cfl_common.lua         -- FNV-1a hash, node helpers, per-node state, parent exception walk
  cfl_definitions.lua    -- Constants, return codes, event types, exception stages
```

### Key Design Differences from C Version
- **Pure Lua tables** for all data structures (no FFI for core runtime)
- **JSON IR loaded directly** via cjson — no binary image (.ctb) needed
- **Node-local state** via `handle.node_state[node_id]` Lua tables (replaces C arena allocator)
- **String-keyed blackboard** (no byte offsets needed in Lua)
- **Function dispatch** via integer index into array (same as C, but holds Lua functions)
- **GC handles memory** — no perm/heap/arena allocators needed
- **FFI optional** — streaming packets can be FFI cdata (from generated `_ffi.lua`) or Lua tables

### Function Signatures (same semantics as C)
- **Main**: `fn(handle, bool_fn_idx, node_idx, event_type, event_id, event_data) -> return_code`
- **Boolean**: `fn(handle, node_idx, event_type, event_id, event_data) -> bool`
- **One-shot**: `fn(handle, node_idx) -> nil`

### Return Codes
`CFL_CONTINUE(0)`, `CFL_HALT(1)`, `CFL_TERMINATE(2)`, `CFL_RESET(3)`, `CFL_DISABLE(4)`, `CFL_SKIP_CONTINUE(5)`, `CFL_TERMINATE_SYSTEM(6)`

## S-Expression Engine (`s_expression/`)

Pure LuaJIT port of the S-Expression engine (from `building_blocks/s_expression/lua_runtime/`).

### Usage
```lua
local se = require("se_runtime")
local mod = se.new_module(module_data, builtins)
local inst = se.new_instance(mod, "tree_name")
local result = se.tick(inst)
```

### DSL Compiler
```bash
luajit s_expression/lua_dsl/s_compile.lua <input.lua> --all-bin --outdir=<dir>
```

## Streaming Pipeline (`runtime/cfl_streaming.lua` + `cfl_builtins.lua`)

Typed packet pipeline for embedded wire protocols. Packets flow through the ChainTree event system with schema verification at each stage via FNV-1a hash matching.

### Streaming Node Types
| Node | Main Function | Behavior |
|------|--------------|----------|
| Sink | `CFL_STREAMING_SINK_PACKET` | Match inport → call boolean (user processes packet) |
| Tap | `CFL_STREAMING_TAP_PACKET` | Match inport → call boolean (non-blocking observation) |
| Filter | `CFL_STREAMING_FILTER_PACKET` | Match inport → call boolean → false = CFL_HALT |
| Transform | `CFL_STREAMING_TRANSFORM_PACKET` | Match inport → call boolean (user transforms + emits on outport) |
| Collect | `CFL_STREAMING_COLLECT_PACKETS` | Match any of N inports → accumulate → emit collected event when full |
| Sink Collected | `CFL_STREAMING_SINK_COLLECTED_PACKETS` | Match collected event → call boolean → reset container |

### Port Definition (DSL)
```lua
local port = ct:make_port("stream_test_1", "accelerometer_reading", 0, "SENSOR_EVENT")
-- Returns: { schema_hash = FNV1a("stream_test_1.h:accelerometer_reading"), handler_id = 0, event_id = N }
```

### Packet Matching
`cfl_streaming.lua` provides `event_matches(event_type, event_id, event_data, port)` which checks:
1. `event_type == CFL_EVENT_TYPE_STREAMING_DATA`
2. `event_id == port.event_id`
3. `schema_hash` from packet header matches port (supports FFI cdata and Lua table packets)

### Verify Packet Boolean
`CFL_STREAMING_VERIFY_PACKET` — allocates inport + user aux function on init, delegates to user boolean for streaming events, passes through non-streaming events.

## Controlled Nodes (Client/Server RPC)

Client-server activation pattern for dormant node subtrees. Mirrors C `cfl_node_control_support.c`.

### Node Types
- **Container** (`CFL_CONTROLLED_NODE_CONTAINER_MAIN`): Structural owner, delegates to column main
- **Server** (`CFL_CONTROLLED_NODE_MAIN`): Dormant until request event; enables children on activation; sends response on termination
- **Client** (`CFL_CLIENT_CONTROLLED_NODE_MAIN`): Activates server directly (sets flags, calls init, sends request); waits for response event

### Lifecycle
1. Client init: decode ports, resolve server node index (original→final), create request packet
2. Client main (first tick): enable server + ancestor chain, call server init, send request event
3. Server main: match request → call boolean → enable children → CFL_HALT
4. Server children execute (e.g., wait_time, log_message)
5. Server term: send response to client via high-priority event
6. Client main: match response → call boolean → CFL_DISABLE

### DSL Usage
```lua
-- Server side
ct:controlled_node_container("controller")
    ct:controlled_node("fly_straight", "fly_node", "FLY_MONITOR", {},
        request_port, response_port)
        ct:asm_log_message("flying")
        ct:asm_wait_time(5.0)
    ct:end_controlled_node()
ct:end_controlled_node_container()

-- Client side
ct:client_controlled_node("fly_straight", "ON_FLY_COMPLETE", {},
    request_port, response_port)
```

## Exception Handling (3-Stage Pipeline)

`CFL_EXCEPTION_CATCH_MAIN` implements a MAIN → RECOVERY → FINALIZE pipeline with heartbeat monitoring. Mirrors C `cfl_exception_support.c`.

### Heartbeat System
- `CFL_TURN_HEARTBEAT_ON` one-shot: finds parent exception catch node, sends `CFL_TURN_HEARTBEAT_ON_EVENT` with timeout
- `CFL_HEARTBEAT_EVENT` one-shot: resets heartbeat counter ("I'm alive" signal)
- Timer tick: increments counter; on timeout → transition MAIN→RECOVERY
- `CFL_TURN_HEARTBEAT_OFF` one-shot: disables heartbeat

### Exception Stages
1. **MAIN_LINK** — normal execution path (child index 1 in catch_links)
2. **RECOVERY_LINK** — activated on exception or heartbeat timeout (child index 2)
3. **FINALIZE_LINK** — cleanup after MAIN or RECOVERY completes (child index 3)

## Avro Packet DSL (`c_avro_packets/`)

Lua DSL for generating fixed-layout C message structs and LuaJIT FFI bindings. Run with `luajit <schema>.lua`.

### Generated Outputs
- `.h` — C structs with packed wire types, packet init/verify/dispatch API
- `_ffi.lua` — LuaJIT FFI bindings with metadata tables, `packet_init()`, `packet_verify()`, `new_packet()`
- `_bin.h` — Binary schema blobs and const packet initializers

### FFI Usage in Runtime
```lua
local schema = require("stream_test_1_ffi")
local pkt = schema.new_packet("accelerometer_reading")
schema.packet_init(pkt, "accelerometer_reading", source_node_id)
pkt.data.x = 1.0; pkt.data.y = 2.0; pkt.data.z = 9.81
-- Verify on receive:
local data = schema.packet_verify(received_pkt, "accelerometer_reading")
```

## Test Harnesses

### CFL Runtime Test (`dsl_tests/incremental_binary/test_cfl.lua`)
```bash
luajit dsl_tests/incremental_binary/test_cfl.lua [kb_name_or_index|all]
```
Runs 26 tests (0-25) through the CFL runtime. Tests 19-22 = streaming, 23-25 = controlled nodes.
User functions in `user_functions_cfl.lua` use CFL signatures (integer node_idx, event_type parameter).

### Dict Runtime Test (`dsl_tests/incremental_binary/test_dict.lua`)
```bash
luajit dsl_tests/incremental_binary/test_dict.lua [kb_name_or_index]
```
Same 26 tests through the dict-based runtime. User functions in `user_functions_dict.lua`.

## JSON IR Schema

The JSON IR (`lua_dsl/README_dsl_schema.md`) is the stable contract between the DSL frontend and all backends. Schema version "1.0". Key structure:
- `nodes{}` — all tree nodes keyed by ltree path, with `label_dict` (functions, links, parent) and `node_dict` (runtime config)
- `ltree_to_index{}` — ltree path to original index mapping
- `kb_metadata{}` — per-KB config (memory factor, aliases)
- `event_string_table{}`, `bitmask_table{}` — name-to-index maps
- `blackboard{}` — optional mutable shared state definition
