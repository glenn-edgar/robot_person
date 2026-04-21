# ChainTree Lua DSL Reference

The ChainTree Lua DSL defines control flow graphs that compile to JSON IR, then to binary images or C headers for the ChainTree runtime engine.

## DSL Structure

A ChainTree DSL file defines one or more knowledge bases (tests), each containing a tree of nodes:

```lua
local ChainTreeMaster = require("chain_tree_master")

local function my_test(ct, kb_name)
    ct:start_test(kb_name)
    -- ... node definitions ...
    ct:end_test()
end

local ct = ChainTreeMaster.new(output_file)
my_test(ct, "my_test")
ct:check_and_generate_yaml()
ct:generate_debug_yaml()
```

## Blackboard Definition

One blackboard per configuration, shared across all knowledge bases:

```lua
ct:define_blackboard("system_state")
    ct:bb_field("mode",        "int32",  0)
    ct:bb_field("temperature", "float",  20.0)
    ct:bb_field("debug_ptr",   "uint64", 0)
ct:end_blackboard()
```

Supported types: `int32`, `uint32`, `uint16`, `float`, `uint64`.

## Composite Nodes

### Column (Sequential)
Children execute sequentially. Column stays active while any child is enabled.

```lua
local col = ct:define_column("my_column", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("step 1")
    ct:asm_wait_time(2.0)
    ct:asm_log_message("step 2")
    ct:asm_terminate_system()
ct:end_column(col)
```

Parameters: `(name, main_fn, init_fn, term_fn, aux_fn, data, auto_start, label, links_flag)`

### Gate Node
Selectively auto-starts children based on the AUTO_START_BIT flag.

```lua
local gate = ct:define_gate_node("gate", nil, nil, nil, nil, nil, true)
    -- children with auto_start=true are enabled on init
ct:end_column(gate)
```

### Fork (Parallel)
All children run in parallel. Fork stays active while any child is enabled.

```lua
local fork = ct:define_fork_column("parallel_tasks")
    -- child columns run concurrently
ct:end_column(fork)
```

### For Loop
Repeats children N times.

```lua
local loop = ct:define_for_column("repeat_3x", 3)
    ct:asm_log_message("iteration")
ct:end_column(loop)
```

### While Loop
Repeats while boolean function returns false.

```lua
local wh = ct:define_while_column("while_running", "CHECK_DONE")
    ct:asm_log_message("still running")
ct:end_column(wh)
```

### Local Arena
Column with a dedicated memory arena.

```lua
local arena = ct:define_local_arena("arena_col", 256)
    -- nodes can allocate from this arena
ct:end_column(arena)
```

## Leaf Nodes (asm_ functions)

### Basic
```lua
ct:asm_log_message("hello world")           -- print timestamped message
ct:asm_wait_time(5.0)                       -- wait N seconds
ct:asm_halt()                               -- halt (CFL_HALT forever)
ct:asm_reset()                              -- reset this column
ct:asm_disable()                            -- disable this node
ct:asm_terminate()                          -- terminate this column
ct:asm_terminate_system()                   -- terminate entire runtime
ct:asm_one_shot_handler("FN_NAME", {data})  -- call user oneshot on init
```

### Events
```lua
ct:asm_send_named_event(target_node, "EVENT_NAME", {data})
ct:asm_send_system_event("EVENT_ID", {data})
ct:asm_event_logger("message", {"CFL_SECOND_EVENT", "CFL_TIMER_EVENT"})
```

### Wait / Verify
```lua
ct:asm_wait_for_event("EVENT", count, reset, timeout, error_fn, event_name, error_data)
ct:asm_wait_for_bitmask({0,1}, {2,3}, timeout, error_fn, error_data)
ct:asm_verify("BOOL_FN", {}, reset, error_fn, error_data)
ct:asm_verify_timeout(5.0, reset, error_fn, error_data)
ct:asm_verify_bitmask({0,1}, {}, timeout, error_fn, error_data)
```

### Bitmask
```lua
ct:asm_set_bitmask({0, 1, 2, 3})
ct:asm_clear_bitmask({2, 3})
```

### Node Control
```lua
ct:asm_enable_nodes({node_a, node_b})
ct:asm_disable_nodes({node_c})
ct:asm_enable_watch_dog(wd_node)
ct:asm_disable_watch_dog(wd_node)
ct:asm_pat_watch_dog(wd_node)
```

### Join Link
Waits for a target node to become disabled before the column advances:

```lua
local node = ct:se_engine_link("module", "tree", "bb_field")
ct:define_join_link(node)    -- column waits here until node disables
ct:asm_log_message("node completed")
```

## State Machine

```lua
ct:define_state_machine("sm_name", "STATE_FIELD", "SM_EVENT_SYNC")
    ct:define_state("state_0", true)    -- auto_start
        -- children for state 0
    ct:end_state()
    ct:define_state("state_1", false)
        -- children for state 1
    ct:end_state()
ct:end_state_machine()
```

## Exception Handler

```lua
ct:define_exception_handler("handler")
    ct:define_try("try_block")
        -- main execution
    ct:end_try()
    ct:define_catch("catch_block", "EXCEPTION_ID")
        -- recovery
    ct:end_catch()
ct:end_exception_handler()
```

## Streaming

```lua
local port = ct:make_port("schema_hash", handler_id, event_id)
ct:asm_streaming_emit_packet("GENERATOR_FN", {}, event_col, port)
ct:asm_streaming_sink_packet("SINK_FN", {}, port)
ct:asm_streaming_filter_packet("FILTER_FN", {}, port)
ct:asm_streaming_transform_packet("TRANSFORM_FN", {}, in_port, out_port, event_col)
ct:asm_streaming_collect_packets("COLLECT_FN", {}, {port_a, port_b}, event, event_col)
```

## S-Engine Integration

### Composite (children controlled by s-engine)
```lua
local eng = ct:se_engine("module_name", "tree_name", "bb_ptr_field", {user_data})
    ct:asm_log_message("controlled by s-engine")
    ct:asm_halt()
ct:end_se_engine(eng)
```

### Leaf Link (runs tree to completion)
```lua
local node = ct:se_engine_link("module_name", "tree_name", "bb_ptr_field", {user_data}, "AUX_FN")
ct:define_join_link(node)
```

### Legacy Pipeline (se_tick)
```lua
ct:se_module_load("module_name", "USER_REGISTER_FN")
ct:se_tree_load("module_name", "tree_name", "bb_field")
ct:se_tick("bb_field")
```

## User Functions

ChainTree nodes reference functions by uppercase string names. The binary pipeline lowercases and appends type suffixes:

| DSL Name | C Symbol | Type |
|----------|----------|------|
| `CFL_COLUMN_MAIN` | `cfl_column_main_main_fn` | main |
| `CFL_COLUMN_INIT` | `cfl_column_init_one_shot_fn` | oneshot |
| `CFL_NULL` | `cfl_null_boolean_fn` | boolean |
| `MY_CUSTOM_FN` | `my_custom_fn_main_fn` | main (user) |

Register user functions in `main.c`:
```c
cfl_image_register_main(&img, "my_custom_fn_main", my_custom_fn);
cfl_image_register_one_shot(&img, "my_oneshot_fn_one_shot", my_oneshot_fn);
cfl_image_register_boolean(&img, "my_bool_fn_boolean", my_bool_fn);
```

## JSON IR Schema

See [lua_dsl/README_dsl_schema.md](chaintree/README_dsl_schema.md) for the JSON intermediate representation specification.
