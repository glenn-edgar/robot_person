# S-Expression Engine DSL File Structure

## Lua Module Architecture

The S-Expression DSL compiler loads modules in dependency order via `s_engine_helpers.lua`:

```
s_compile.lua                      ← command-line compiler
    ├── s_expr_dsl.lua             ← core: module/record/tree/call/param APIs
    ├── s_expr_generators.lua      ← C header + binary generators
    ├── s_expr_debug.lua           ← debug output generation
    ├── s_expr_compiler.lua        ← expression compiler (C-like syntax)
    └── s_engine_helpers.lua       ← loads all helper sub-modules:
        ├── s_engine_equation.lua
        ├── se_field_validation.lua
        ├── se_result_codes.lua    ← se_return_continue(), etc.
        ├── se_predicates.lua      ← se_pred_or(), se_field_eq(), etc.
        ├── se_oneshot.lua         ← se_set_field(), se_log(), etc.
        ├── se_control_flow.lua    ← se_sequence(), se_fork(), etc.
        ├── se_timing_events.lua   ← se_tick_delay(), se_wait_event(), etc.
        ├── se_state_machine.lua   ← se_state_machine(), se_field_dispatch(), etc.
        ├── se_dictionary.lua      ← dictionary/JSON loading
        ├── se_quad_ops.lua        ← arithmetic, comparison, math
        ├── se_p_quad_ops.lua      ← predicate quad operations
        ├── se_stack_frame.lua     ← stack frame management
        ├── se_function_dict.lua   ← function dictionary, tree spawning
        └── se_chain_tree.lua      ← CFL bridge helpers (ChainTree integration)
```

## Module File Template

```lua
local mod = start_module("my_module")
use_32bit()          -- or use_64bit() for 64-bit targets
set_debug(true)      -- optional: include debug strings

-- ============================================================================
-- RECORD DEFINITIONS
-- ============================================================================

RECORD("my_blackboard")
    FIELD("counter",     "int32")
    FIELD("temperature", "float")
    FIELD("name_ptr",    "uint32")
    PTR64_FIELD("data",  "my_data_record")
END_RECORD()

RECORD("my_data_record")
    FIELD("x", "float")
    FIELD("y", "float")
END_RECORD()

-- ============================================================================
-- CONSTANT DEFINITIONS (optional)
-- ============================================================================

CONST("default_config", "my_blackboard")
    VALUE("counter", 0)
    VALUE("temperature", 20.5)
END_CONST()

-- ============================================================================
-- TREE DEFINITIONS
-- ============================================================================

start_tree("my_tree")
    use_record("my_blackboard")

    se_function_interface(function()
        se_log("tree started")
        se_i_set_field("counter", 0)

        se_fork_join(function()
            se_sequence(function()
                se_chain_flow(function()
                    se_log("step 1")
                    se_tick_delay(10)
                    se_log("step 1 done")
                    se_return_pipeline_disable()
                end)
            end)
        end)

        se_log("tree complete")
        se_return_function_terminate()
    end)

end_tree("my_tree")

-- ============================================================================
-- END MODULE
-- ============================================================================

return end_module(mod)
```

## Key Concepts

### Module
A module is a collection of records, constants, and trees compiled into a single binary. One `.lua` file = one module. The module name is used for registry lookup at runtime.

### Records
Records define typed blackboard layouts. Each tree uses one record. Fields must be `int32`, `uint32`, or `float` (minimum 4 bytes). Use `PTR64_FIELD` for pointers, `CHAR_ARRAY` for fixed strings.

### Trees
A tree is a flat parameter array evaluated by the tick-driven interpreter. Each tree has a name (hashed for lookup), a record type, and a root function (`se_function_interface`).

### Function Types
- `o_call("NAME")` — oneshot (void return, called on init/tick/term)
- `io_call("NAME")` — oneshot, init-only (skipped on tick/term)
- `m_call("NAME")` — main (returns `s_expr_result_t`)
- `pt_m_call("NAME")` — main with pointer storage (uses tree pointer slot)
- `p_call("NAME")` — predicate (returns bool)

### Composites vs Raw Calls
Helpers like `se_sequence()`, `se_fork_join()`, `se_state_machine()` generate the correct raw `m_call` patterns internally. Use helpers when available; use raw calls for user functions.

## Generated Output Files

| File | Description |
|------|-------------|
| `<base>_records.h` | C struct typedefs for all records |
| `<base>.h` | Module/tree/field hash `#define`s |
| `<base>_debug.h` | Hash-to-name debug mappings |
| `<base>_user_functions.h` | User function prototypes |
| `<base>_user_registration.c` | Generated registration (must override for ChainTree) |
| `<base>_32.bin` | Binary module for file loading |
| `<base>_bin_32.h` | Binary module as C array for ROM embedding |
| `<base>_dump_32.h` | Human-readable parameter dump |

## Directory Layout

```
s_engine/
  my_module.lua                  S-engine DSL source (hand-written)
  my_module.h                    Generated hashes
  my_module_records.h            Generated record structs
  my_module_bin_32.h             Generated binary ROM (C array)
  my_module_32.bin               Generated binary (file-loadable)
  my_module_dump_32.h            Human-readable dump
  my_module_debug.h              Debug hash mappings
  my_module_user_functions.h     Generated prototypes
  my_module_user_registration.c  Registration (manual override for ChainTree)
  user_functions.c               User C implementations (hand-written)
```

## Creating a New S-Engine Module

### Step 1: Write the DSL file
Follow the template above. Define records, constants, and trees.

### Step 2: Compile
```bash
./s_expression/s_build.sh path/to/my_module.lua path/to/output/
```

### Step 3: Override user_registration.c (ChainTree only)
The compiler generates `_user_registration.c` with all non-`SE_` functions including CFL bridge functions. For ChainTree integration, replace with a manual file that registers only true user functions.

### Step 4: Write user C functions
Implement the functions declared in `_user_functions.h`. Follow the oneshot/main/predicate signatures.

### Step 5: Build
Include `_bin_32.h` and `_records.h` in your test, link against `libs_s_engine.a`.

## Standalone vs ChainTree

| Aspect | Standalone | Inside ChainTree |
|--------|-----------|-----------------|
| Loading | `s_engine_load_from_rom()` | `cfl_se_registry_register_def()` |
| Ticking | `s_expr_node_tick(tree, event_id, NULL)` | Automatic via `se_engine`/`se_tick` |
| Allocator | User provides malloc/free | Uses `cfl_heap` via bridge |
| User functions | `_register_all()` called directly | Passed via `_with_user()` callback |
| Event ID | `SE_EVENT_TICK` (4) | `CFL_TIMER_EVENT` (4) — same value |
| User context | `s_expr_tree_set_user_ctx()` | Automatically set to `cfl_runtime_handle_t*` |
