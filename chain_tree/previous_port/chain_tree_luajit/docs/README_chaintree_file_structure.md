# ChainTree DSL File Structure

## Lua Module Architecture

The ChainTree DSL is built from a mixin-based module system. `ChainTreeMaster` combines all modules into a single class using method copying (equivalent to Python multiple inheritance):

```
chain_tree_master.lua          ← entry point, builds ChainTreeMaster
    ├── chain_tree_yaml.lua    ← core: node tree builder, JSON emitter
    ├── column_flow.lua        ← columns, forks, for/while, gate, join, links
    ├── basic_cf_links.lua     ← log, wait_time, halt, reset, terminate, events, watchdog
    ├── wait_cf_links.lua      ← wait_for_event, wait_for_bitmask, wait_time
    ├── verify_cf_links.lua    ← verify, verify_timeout, verify_bitmask
    ├── state_machine.lua      ← state machine composites
    ├── sequence_till.lua      ← sequence_til_pass, sequence_til_fail
    ├── data_flow.lua          ← set/clear bitmask
    ├── exception_handler.lua  ← try/catch/recovery/finalize, heartbeat
    ├── streaming.lua          ← packet tap/sink/filter/transform/collect
    ├── controlled_nodes.lua   ← client-controlled nodes
    ├── s_expression_nodes.lua ← legacy s-engine nodes (module_load, tree_load)
    ├── s_engine.lua           ← se_engine composite, se_engine_link leaf, se_tick
    ├── debug_yaml_dumper.lua  ← debug YAML output
    └── fnv1a.lua              ← FNV-1a hash (for function name hashing)
```

## DSL File Template

Every ChainTree DSL test file follows this structure:

```lua
-- =========================================================================
-- my_test.lua — ChainTree DSL test file
-- =========================================================================

local ChainTreeMaster = require("chain_tree_master")

-- =========================================================================
-- Test Definitions
-- =========================================================================

local function first_test(ct, kb_name)
    ct:start_test(kb_name)

    -- Define blackboard, columns, leaf nodes here

    ct:end_test()
end

local function second_test(ct, kb_name)
    ct:start_test(kb_name)
    -- ...
    ct:end_test()
end

-- =========================================================================
-- Blackboard + Header
-- =========================================================================

local function add_header(yaml_file)
    local ct = ChainTreeMaster.new(yaml_file)

    -- One blackboard per configuration (shared across all KBs)
    ct:define_blackboard("my_state")
        ct:bb_field("counter", "int32", 0)
        ct:bb_field("mode",    "int32", 0)
    ct:end_blackboard()

    return ct
end

-- =========================================================================
-- Test List (ordered — determines KB index)
-- =========================================================================

local test_list = {
    "first_test",
    "second_test",
}

local test_dict = {
    first_test  = first_test,
    second_test = second_test,
}

-- =========================================================================
-- Main (command-line entry point)
-- =========================================================================

if arg then
    if #arg ~= 1 then
        print("Usage: luajit my_test.lua <json_file>")
        os.exit(1)
    end

    local json_file = arg[1]
    local ct = add_header(json_file)

    for _, test_name in ipairs(test_list) do
        test_dict[test_name](ct, test_name)
    end

    ct:check_and_generate_yaml()
    ct:generate_debug_yaml()
    ct:display_chain_tree_function_mapping()

    local kbs = ct:list_kbs()
    print(table.concat(kbs, ", "))
    print("total nodes", ct.ctb:get_total_node_count())
end
```

## Key Concepts

### The `ct` Object
All DSL calls go through the `ct` object (a `ChainTreeMaster` instance). It maintains:
- The node tree being built
- A link number stack (tracks parent-child nesting)
- State machine, sequence, exception handler stacks
- Event string table
- Blackboard definition

### start_test / end_test
Each `start_test(name)` creates a new knowledge base (KB). The KB gets a root gate node. All nodes defined between `start_test` and `end_test` belong to this KB. The order in `test_list` determines the KB index used by `cfl_add_test_by_index()` in `main.c`.

### define_column / end_column
Creates a composite node. Children are defined between `define_column` and `end_column`. The DSL tracks nesting via an internal link stack — each `define_column` pushes, each `end_column` pops.

```lua
local outer = ct:define_column("outer", nil, nil, nil, nil, nil, true)
    ct:asm_log_message("in outer")

    local inner = ct:define_column("inner")
        ct:asm_log_message("in inner")
        ct:asm_halt()
    ct:end_column(inner)

    ct:asm_log_message("after inner")
ct:end_column(outer)
```

### auto_start
The 7th parameter to `define_column` controls whether the node is enabled on parent init:
- `true` — enabled automatically when parent initializes (AUTO_START_BIT set)
- `false` or `nil` — must be enabled explicitly (e.g., by a state machine)

### Leaf Nodes (asm_ functions)
Leaf nodes are created by `asm_*` functions. They're added as children of the current composite. Each `asm_` call creates a node with specific main/init/term/aux functions.

### define_column_link
Creates a leaf node directly (not a composite). Used for custom nodes like `se_engine_link`, `define_join_link`, etc. Returns a node ID that can be referenced by join links.

## Directory Layout for a Test

```
dsl_tests/my_test/
  my_test.lua                    ChainTree DSL source
  my_test.json                   Generated JSON IR (stage 1)
  my_test_debug.yaml             Generated debug dump (stage 1)
  chaintree_handle.ctb           Generated binary image (stage 2)
  chaintree_handle_image.h       Generated C array (stage 2)
  chaintree_handle_blackboard.h  Generated blackboard offsets (stage 2)
  main.c                         Test harness
  Makefile                       Build rules
  build/                         Object files (generated)
  main                           Compiled binary (generated)
```

### With S-Engine Module

```
dsl_tests/my_test/
  my_test.lua                    ChainTree DSL
  main.c                         Test harness
  Makefile
  s_engine/
    my_module.lua                S-engine DSL source
    my_module.h                  Generated module hashes
    my_module_bin_32.h           Generated binary ROM
    my_module_records.h          Generated record structs
    my_module_user_functions.h   Generated user function prototypes
    my_module_user_registration.c  User function registration (manual override)
    user_functions.c             User C function implementations
```

## Creating a New Test

### Step 1: Create directory and DSL file
```bash
mkdir -p dsl_tests/my_test
# Write my_test.lua following the template above
```

### Step 2: (Optional) Create s-engine module
```bash
mkdir -p dsl_tests/my_test/s_engine
# Write s_engine/my_module.lua
./s_expression/s_build.sh dsl_tests/my_test/s_engine/my_module.lua dsl_tests/my_test/s_engine/
```

### Step 3: Generate ChainTree artifacts
```bash
./s_build_json.sh dsl_tests/my_test/my_test.lua dsl_tests/my_test/
./s_build_headers_binary.sh dsl_tests/my_test/my_test.json dsl_tests/my_test/
```

### Step 4: Write main.c
Follow the cookie-cutter pattern from `s_engine_test_2/main.c`:
1. Load embedded image
2. Register functions (core + user boolean)
3. Get handle
4. Create runtime (set heap size, arena count, etc.)
5. (Optional) Create s-engine registry, register module binaries
6. Reset and select test(s)
7. Run
8. Cleanup

### Step 5: Write Makefile
Copy from `s_engine_test_2/Makefile` and adjust:
- `SE_LOCAL_DIR` if you have s-engine files
- Add user `.c` files to SRCS
- Adjust library dependencies

### Step 6: Build and run
```bash
cd dsl_tests/my_test
make clean && make
./main 0
```

## Function Name Convention

The DSL uses uppercase names. The binary pipeline generates typed registration names:

| DSL Usage | Generated Name | Lookup |
|-----------|---------------|--------|
| `main_function = "CFL_COLUMN_MAIN"` | `cfl_column_main_main` | FNV-1a hash |
| `init_function = "CFL_COLUMN_INIT"` | `cfl_column_init_one_shot` | FNV-1a hash |
| `aux_function = "CFL_COLUMN_NULL"` | `cfl_column_null_boolean` | FNV-1a hash |
| `term_function = "CFL_COLUMN_TERM"` | `cfl_column_term_one_shot` | FNV-1a hash |

User functions follow the same pattern. The function name in the DSL is lowercased and a type suffix is appended. The binary image stores the FNV-1a 32-bit hash, and the runtime resolves functions by hash at startup.

## Nesting Rules

- Composites can be nested (column inside column, fork inside column, etc.)
- Leaf nodes (`asm_*`) cannot contain children
- `start_test` / `end_test` must be balanced
- `define_column` / `end_column` must be balanced
- State machine states must be inside a state machine
- Exception try/catch must be inside an exception handler
- The blackboard is defined once before any tests, in `add_header`
