# Function Dictionary & External Tree Test — LuaJIT Runtime

## Overview

This test demonstrates hierarchical tree composition combined with a function dictionary pattern in the LuaJIT runtime. A parent tree (`call_tree`) spawns a child tree (`function_dictionary`) at runtime, injects a command hash into the child's blackboard, and ticks the child to execute a complete STM32F4 peripheral initialization sequence — all driven by dictionary-dispatched functions that use stack-based parameter passing.

## Purpose

This test validates three core capabilities of the external tree system:

1. **External tree lifecycle management** — how to spawn, tick, and terminate a child tree from a parent tree using `se_spawn_tree`, `se_tick_tree` (`se_builtins_spawn.lua`), and the automatic cleanup on `SE_EVENT_TERMINATE`.

2. **Cross-tree parameter passing** — how to write values into a child tree's blackboard from the parent using `se_set_external_field` (`se_builtins_oneshot.lua`) with compile-time field offsets resolved through the child's record definition. In the LuaJIT runtime, the child is a full `inst` table stored in the parent's blackboard, and `se_set_external_field` resolves the byte offset to a field name via the child's record descriptor.

3. **Shared dictionary invocation across trees** — how to call a specific dictionary entry in another tree by injecting a function hash into the child's blackboard before ticking. This means a large function dictionary only needs to exist in one tree and can be invoked by any number of other trees. Without this pattern, every tree that needs dictionary functions would have to include its own copy, wasting memory.

## Module Structure

**Module name:** `external_tree`

### Trees

| Tree | Record | Purpose |
|------|--------|---------|
| `function_dictionary` | `cpu_config_blackboard` | Contains a function dictionary with peripheral configuration routines. Executes whichever dictionary entry is named by `fn_hash`. |
| `call_tree` | `call_blackboard` | Parent tree that spawns `function_dictionary`, sets the command hash, ticks the child, and terminates. |

Both trees exist in the same `module_data` and share the same `mod` — meaning they share function registrations, time source, and module metadata. `se_runtime.new_instance(mod, "function_dictionary")` and `se_runtime.new_instance(mod, "call_tree")` create separate instances with separate blackboards and node_states.

---

## Blackboard Records

### cpu_config_blackboard

In `module_data.records`:

```lua
records["cpu_config_blackboard"] = {
    fields = {
        fn_dict           = { type = "ptr64",  default = 0 },
        fn_hash           = { type = "uint32", default = 0 },
        gpio_port         = { type = "uint32", default = 0 },
        gpio_pin          = { type = "uint32", default = 0 },
        gpio_mode         = { type = "uint32", default = 0 },
        gpio_speed        = { type = "uint32", default = 0 },
        gpio_pull         = { type = "uint32", default = 0 },
        uart_channel      = { type = "uint32", default = 0 },
        uart_baud         = { type = "uint32", default = 0 },
        uart_parity       = { type = "uint32", default = 0 },
        uart_stop_bits    = { type = "uint32", default = 0 },
        uart_flow_ctrl    = { type = "uint32", default = 0 },
        spi_channel       = { type = "uint32", default = 0 },
        spi_clock_div     = { type = "uint32", default = 0 },
        spi_mode          = { type = "uint32", default = 0 },
        spi_bit_order     = { type = "uint32", default = 0 },
        config_state      = { type = "uint32", default = 0 },
        error_code        = { type = "uint32", default = 0 },
        peripherals_ready = { type = "uint32", default = 0 },
        temp_reg_addr     = { type = "uint32", default = 0 },
        temp_reg_value    = { type = "uint32", default = 0 },
    }
}
```

After `new_instance()`, these become `inst.blackboard["fn_dict"]`, `inst.blackboard["fn_hash"]`, etc. The `fn_dict` field holds a Lua `{hash → closure}` table (not a ROM pointer), and `fn_hash` holds the FNV-1a hash of the function to execute.

### call_blackboard

```lua
records["call_blackboard"] = {
    fields = {
        tree_pointer    = { type = "ptr64",  default = 0 },
        dictionary_hash = { type = "uint32", default = 0 },
    }
}
```

In the LuaJIT runtime, `tree_pointer` holds the child's `inst` table (a full tree instance) rather than a raw pointer.

---

## Function Dictionary Entries

The `function_dictionary` tree contains a dictionary of stack-based callable functions that form a layered peripheral abstraction. Each function uses `se_call` with `frame_vars` for safe local variable management.

### Call Hierarchy

```
init_all_peripherals
├── enable_peripheral_clock  (×3: GPIOA, USART1, SPI1)
│   └── read_modify_write
│       └── write_register
├── configure_gpio_pin
│   └── read_modify_write  (×3: MODER, OSPEEDR, PUPDR)
│       └── write_register
├── configure_uart  (conditional: uart_channel != 0)
│   ├── read_modify_write  (disable USART)
│   ├── write_register     (set BRR)
│   ├── read_modify_write  (set CR1 config)
│   └── read_modify_write  (enable USART)
└── configure_spi   (conditional: spi_channel != 0)
    ├── read_modify_write  (disable SPI)
    ├── write_register     (write CR1)
    └── read_modify_write  (enable SPI)
```

### Function Details

| Function | Stack Params | Locals | Description |
|----------|-------------|--------|-------------|
| `write_register` | addr, value | — | Low-level register write |
| `read_modify_write` | addr, clear_mask, set_bits | current, inv_mask | Read-modify-write: clears bits then sets bits |
| `enable_peripheral_clock` | clock_reg_addr, peripheral_bit | — | Calls `read_modify_write` to set a clock enable bit |
| `configure_gpio_pin` | port_base, pin, mode, speed, pull | shift, mask, reg_addr, set_val | Configures MODER, OSPEEDR, and PUPDR registers |
| `configure_uart` | usart_base, baud_div, config_bits | reg_addr | Disables USART, sets baud rate and config, re-enables |
| `configure_spi` | spi_base, clock_div, mode, bit_order | cr1 | Disables SPI, builds and writes CR1, re-enables |
| `init_all_peripherals` | — | — | Top-level orchestrator that enables clocks and configures all peripherals |

### How Dictionary Functions Execute

The dictionary is built by `se_load_function_dict` (`se_builtins_dict.lua`), which pairs `dict_key` names with child subtrees:

```lua
-- At INIT time in function_dictionary tree:
-- se_load_function_dict stores:
--   inst.blackboard["fn_dict"] = {
--     [s_expr_hash("write_register")]         = closure → write_register subtree,
--     [s_expr_hash("read_modify_write")]       = closure → read_modify_write subtree,
--     [s_expr_hash("enable_peripheral_clock")] = closure → enable_peripheral_clock subtree,
--     [s_expr_hash("configure_gpio_pin")]      = closure → configure_gpio_pin subtree,
--     [s_expr_hash("configure_uart")]          = closure → configure_uart subtree,
--     [s_expr_hash("configure_spi")]           = closure → configure_spi subtree,
--     [s_expr_hash("init_all_peripherals")]    = closure → init_all_peripherals subtree,
--   }
```

Each closure wraps `se_runtime.invoke_any(inst, child_node, eid, edata)`. When `se_exec_dict_fn_ptr` ticks, it reads `inst.blackboard["fn_hash"]`, looks up `dict[fn_hash]`, and calls the closure.

Inside the function body, `se_exec_dict_internal` calls sibling dictionary entries (e.g., `write_register` from within `read_modify_write`). It uses `inst.current_dict` which was set by the parent `se_exec_dict_fn_ptr` on INIT.

### Stack-Based Parameter Passing

Dictionary functions receive parameters via the stack. Before calling `se_exec_dict_internal`, the caller pushes parameters:

```lua
-- In configure_gpio_pin, calling read_modify_write(addr, clear_mask, set_bits):
-- 1. Compute values into frame locals via quad_expr
-- 2. Push params onto stack:
--    quad_mov(local:reg_addr, stack_push)   → becomes p0 in callee
--    quad_mov(local:mask,     stack_push)   → becomes p1
--    quad_mov(local:set_val,  stack_push)   → becomes p2
-- 3. se_exec_dict_internal("read_modify_write")
--    → looks up dict[s_expr_hash("read_modify_write")]
--    → invokes the closure which enters se_call(3, 2, ...)
--    → se_stack_frame_instance pops param count, pushes frame
```

At runtime, `se_builtins_quads.lua`'s `write_int`/`write_float` handle the `"stack_push"` param type via `se_stack.push(stk, val)`, and `read_int`/`read_float` handle `"stack_local"` via `se_stack.get_local(stk, idx)`.

---

## STM32F4 Peripheral Constants

The test uses realistic STM32F4 base addresses and register offsets:

| Constant | Value | Description |
|----------|-------|-------------|
| `RCC_AHB1ENR` | `0x40023830` | AHB1 peripheral clock enable register |
| `RCC_APB2ENR` | `0x40023844` | APB2 peripheral clock enable register |
| `GPIOA_BASE` | `0x40020000` | GPIO Port A base address |
| `USART1_BASE` | `0x40011000` | USART1 base address |
| `SPI1_BASE` | `0x40013000` | SPI1 base address |

Register offsets follow the STM32F4 reference manual (e.g., MODER at +0, OSPEEDR at +8, PUPDR at +12, USART BRR at +8, USART CR1 at +12). In the LuaJIT runtime, these are integer constants in blackboard fields and quad parameters — no actual hardware access occurs (the test validates the computation and call chain, not hardware I/O).

---

## Parent Tree Flow (call_tree)

The `call_tree` demonstrates the external tree management pattern:

```
SE_FUNCTION_INTERFACE (root)
├── [pt_m_call] SE_SPAWN_TREE
│   params: [field_ref:"tree_pointer", str_hash:"function_dictionary", uint:128]
│   → se_runtime.new_instance(mod, "function_dictionary")
│   → child.stack = se_stack.new_stack(128)
│   → inst.blackboard["tree_pointer"] = child
│
├── [o_call] SE_SET_HASH_FIELD
│   params: [field_ref:"dictionary_hash", str_hash:"init_all_peripherals"]
│   → inst.blackboard["dictionary_hash"] = s_expr_hash("init_all_peripherals")
│
├── [o_call] SE_SET_EXTERNAL_FIELD
│   params: [field_ref:"dictionary_hash", field_ref:"tree_pointer", uint:offset]
│   → child = inst.blackboard["tree_pointer"]    (the child inst table)
│   → resolve offset to field name via child's record definition
│   → child.blackboard["fn_hash"] = inst.blackboard["dictionary_hash"]
│
├── [m_call] SE_TICK_TREE
│   params: [field_ref:"tree_pointer"]
│   → child = inst.blackboard["tree_pointer"]
│   → se_runtime.tick_once(child, event_id, event_data)
│   → drain child's event queue
│
├── [o_call] SE_LOG "call_tree: called"
│
└── SE_RETURN_FUNCTION_TERMINATE
```

### se_set_external_field in LuaJIT

The key cross-tree mechanism. In C, this does raw byte-offset pointer arithmetic into the child's blackboard struct. In LuaJIT, it resolves the byte offset to a field name through the child's record definition:

```lua
-- From se_builtins_oneshot.lua:
M.se_set_external_field = function(inst, node)
    local params = node.params or {}

    -- Read value from own blackboard
    local value = inst.blackboard[params[1].value]

    -- Read child tree instance from own blackboard
    local child = inst.blackboard[params[2].value]
    assert(child and type(child) == "table" and child.blackboard)

    -- Byte offset in the child's record
    local offset = params[3].value

    -- Resolve byte offset to field name using child's record definition
    local record_name = child.tree.record_name
    local record = child.mod.module_data.records[record_name]

    for _, field in ipairs(record.fields) do
        if field.offset == offset then
            child.blackboard[field.name] = value
            return
        end
    end

    error(string.format(
        "se_set_external_field: no field at offset %d in record '%s'",
        offset, record_name))
end
```

This is the LuaJIT equivalent of the C pattern where `get_field_offset("cpu_config_blackboard", "fn_hash")` provides the byte offset at compile time, and the runtime writes directly to `(uint8_t*)child->blackboard + offset`. The LuaJIT version performs a field-name lookup through the record descriptor, which is slightly less efficient but avoids all pointer arithmetic and alignment concerns.

### se_spawn_tree in LuaJIT

Creates a child tree instance from the same module and stores it in a blackboard field:

```lua
-- From se_builtins_spawn.lua:
-- On INIT:
local child = se_runtime.new_instance(inst.mod, tree_name)
if stack_size > 0 then
    child.stack = require("se_stack").new_stack(stack_size)
end
inst.pointer_array[inst.pointer_base].ptr = child   -- cache in pointer slot
inst.blackboard[field_name] = child                  -- store in blackboard
```

The child is a full `inst` table with its own `node_states`, `blackboard`, `pointer_array`, `event_queue`, and optional `stack`. It shares the parent's `mod` (function tables, module_data, time source).

### se_tick_tree in LuaJIT

Ticks the child tree and drains its event queue:

```lua
-- From se_builtins_spawn.lua:
-- On TICK:
local child = inst.blackboard[field_name]
local result = se_runtime.tick_once(child, event_id, event_data)

-- Drain child's event queue
while se_runtime.event_count(child) > 0 do
    local q_tick_type, q_event_id, q_event_data = se_runtime.event_pop(child)
    result = se_runtime.tick_once(child, q_event_id, q_event_data)
end

return result
```

---

## Key Design Patterns Demonstrated

### Stack-Based Parameter Passing
Dictionary functions receive parameters via `se_stack.lua`. Values are pushed with `stack_push` param type before calling `se_exec_dict_internal`, and the callee's `se_stack_frame_instance` pops the param count marker, validates arity, and pushes the frame. `frame_vars` provides named access to params (`stack_local(0)`, `stack_local(1)`, ...) and scratch (`stack_tos(N)`, ...).

### Frame Variable Safety
All values that survive a `stack_push` call are stored in frame locals (`stack_local`), not scratch (`stack_tos`) variables. This is critical because `se_stack.push` advances `stk.sp`, which invalidates TOS-relative offsets.

### Expression Compilation
`quad_expr` from `s_expr_compiler.lua` compiles arithmetic expressions (shifts, masks, bitwise operations) into sequences of `se_quad` nodes with opcodes like `BIT_SHL` (0x14), `BIT_AND` (0x10), `BIT_OR` (0x11), `BIT_NOT` (0x13). At runtime, `se_builtins_quads.lua` executes these via LuaJIT's `bit.*` library.

### Conditional Peripheral Configuration
`se_if_then_else` with `se_field_ne` predicates allows peripheral configuration to be skipped when the corresponding channel field is zero (e.g., `inst.blackboard["uart_channel"] ~= 0`), demonstrating runtime branching within dictionary functions.

### Cross-Tree Communication
The parent writes into the child's blackboard using `se_set_external_field`, which resolves a compile-time byte offset to a field name through the child's record descriptor. This provides a clean, typed interface between trees without requiring shared global state.

### Shared Dictionary — Single Copy, Multiple Callers
The function dictionary exists only in the `function_dictionary` tree. The `call_tree` (and any number of other parent trees) can invoke any dictionary entry by:
1. Spawning the child tree
2. Setting `fn_hash` in the child's blackboard
3. Ticking the child

This avoids duplicating dictionary functions across trees — significant on memory-constrained embedded targets where ROM is scarce.

---

## Comparison with C Implementation

| Aspect | C Runtime | LuaJIT Runtime |
|--------|-----------|----------------|
| Child tree storage | `void*` in PTR64 field | `inst` table in blackboard |
| Cross-tree field write | `(uint8_t*)child->blackboard + offset` | `child.blackboard[field_name]` via record lookup |
| Dictionary storage | ROM pointer to `s_expr_param_t[]` | `{hash → closure}` Lua table |
| Dictionary invocation | `s_expr_invoke_any(inst, params, ...)` | `closure(inst, node, eid, edata)` → `invoke_any` |
| Stack values | Typed `s_expr_param_t` (8/16 bytes) | Plain Lua numbers |
| Register writes | Actual hardware writes (on target) | Computation only (no hardware I/O in LuaJIT) |
| Field offset resolution | Direct byte offset (compile-time) | Record descriptor scan (runtime) |

---

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_builtins_spawn.lua` | `se_spawn_tree`, `se_tick_tree`, `se_exec_dict_fn_ptr`, `se_exec_dict_internal` | Tree lifecycle, dictionary dispatch |
| `se_builtins_dict.lua` | `se_load_function_dict`, `s_expr_hash` | Dictionary building, FNV-1a hashing |
| `se_builtins_oneshot.lua` | `se_log`, `se_set_field`, `se_set_hash`, `se_set_hash_field`, `se_set_external_field` | Logging, field writes, cross-tree writes |
| `se_builtins_stack.lua` | `se_frame_allocate`, `se_stack_frame_instance` | Stack frame lifecycle |
| `se_builtins_quads.lua` | `se_quad` (IADD, BIT_SHL, BIT_AND, BIT_OR, BIT_NOT, MOVE) | Register arithmetic |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_sequence_once`, `se_if_then_else`, `se_chain_flow` | Control flow |
| `se_builtins_pred.lua` | `se_field_ne` | Conditional peripheral configuration |
| `se_builtins_return_codes.lua` | `se_return_function_terminate`, `se_return_pipeline_terminate` | Termination |
| `se_stack.lua` | `new_stack`, `push`, `pop`, `push_frame`, `pop_frame`, `get_local`, `set_local` | Stack data structure |
| `se_runtime.lua` | `new_module`, `new_instance`, `tick_once`, `invoke_any`, event queue | Core engine |

## Dependencies

| DSL / Pipeline | LuaJIT Builtin | Module | Purpose |
|----------------|---------------|--------|---------|
| `se_spawn_tree` | `se_spawn_tree` | `se_builtins_spawn.lua` | Create child tree instance |
| `se_tick_tree` | `se_tick_tree` | `se_builtins_spawn.lua` | Tick child + drain event queue |
| `se_set_external_field` | `se_set_external_field` | `se_builtins_oneshot.lua` | Write value into child's blackboard |
| `se_load_function_dict` | `se_load_function_dict` | `se_builtins_dict.lua` | Build `{hash → closure}` dictionary |
| `se_exec_dict_fn_ptr` | `se_exec_dict_fn_ptr` | `se_builtins_spawn.lua` | Execute dict entry by runtime key |
| `se_exec_dict_internal` | `se_exec_dict_internal` | `se_builtins_spawn.lua` | Execute sibling dict entry via `inst.current_dict` |
| `se_call` / `frame_vars` | `se_stack_frame_instance` | `se_builtins_stack.lua` | Stack-based calling convention |
| `stack_push_ref` | `{type="stack_push"}` | `se_builtins_quads.lua` | Push values onto stack |
| `quad_expr` / `quad_mov` | `se_quad` with opcodes | `se_builtins_quads.lua` | Arithmetic and bitwise operations |
| `se_if_then_else` | `se_if_then_else` | `se_builtins_flow_control.lua` | Conditional branching |
| `se_set_hash_field` | `se_set_hash_field` | `se_builtins_oneshot.lua` | Write FNV-1a hash to field |
| `get_field_offset` | Record descriptor lookup | `se_builtins_oneshot.lua` | Compile-time → runtime field offset resolution |

## Files

| File | Description |
|------|-------------|
| `external_tree_module.lua` | Pipeline-generated `module_data` with both trees |
| `test_external_tree.lua` | LuaJIT test harness |
| `se_builtins_spawn.lua` | `se_spawn_tree`, `se_tick_tree`, `se_exec_dict_*` |
| `se_builtins_dict.lua` | `se_load_function_dict`, `s_expr_hash` |
| `se_builtins_oneshot.lua` | `se_set_external_field`, `se_set_hash_field` |
| `se_builtins_stack.lua` | `se_frame_allocate`, `se_stack_frame_instance` |
| `se_builtins_quads.lua` | `se_quad` for register arithmetic |