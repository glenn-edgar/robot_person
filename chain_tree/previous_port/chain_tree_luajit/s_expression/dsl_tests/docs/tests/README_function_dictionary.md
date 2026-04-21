# Function Dictionary Test — STM32F4 Peripheral Configuration (LuaJIT Runtime)

## Overview

This test demonstrates the **Function Dictionary** feature of the S-Expression Engine in the LuaJIT runtime. A function dictionary is a collection of named, one-tick stack-based functions that can call each other internally to produce complex results. In this test, a small set of primitive I/O functions — `write_register` and `read_modify_write` — are composed into higher-level peripheral configuration routines that set up GPIO, UART, and SPI on a simulated STM32F4 microcontroller.

The key insight is that instead of writing many individual user-defined Lua functions for each peripheral register operation, only a single Lua callback (`write_register`) is needed. All the register address computation, bit manipulation, and sequencing logic lives in the dictionary as S-Expression tree nodes, using `quad_expr`-generated `se_quad` nodes for arithmetic and bitwise operations executed by `se_builtins_quads.lua`.

## Dictionary Architecture

The dictionary is structured as a hierarchy of reusable functions, each stored as a closure in a `{hash → closure}` Lua table:

```
init_all_peripherals          (top-level orchestrator)
  ├── enable_peripheral_clock   (clock setup, called 3x)
  │     └── read_modify_write     (bit manipulation)
  │           └── write_register    (user-defined Lua function)
  ├── configure_gpio_pin        (GPIO register config)
  │     └── read_modify_write (x3: MODER, OSPEEDR, PUPDR)
  ├── configure_uart            (USART setup)
  │     ├── read_modify_write (x3: disable, config, enable)
  │     └── write_register    (x1: BRR baud rate)
  └── configure_spi             (SPI setup)
        ├── read_modify_write (x2: disable, enable)
        └── write_register    (x1: CR1 config)
```

### Dictionary Functions

| Function | Stack Params | Description |
|----------|-------------|-------------|
| `write_register` | addr, value | User-defined Lua function that performs the register write |
| `read_modify_write` | addr, clear_mask, set_bits | Clears bits then sets bits via internal calls to `write_register` |
| `enable_peripheral_clock` | clk_reg, periph_bit | Enables a peripheral clock via RCC register |
| `configure_gpio_pin` | port_base, pin, mode, speed, pull | Configures a GPIO pin's mode, speed, and pull-up/down |
| `configure_uart` | usart_base, baud_div, config_bits | Disables USART, sets baud rate, configures, re-enables |
| `configure_spi` | spi_base, clk_div, mode, bit_order | Disables SPI, builds CR1 register, writes config, re-enables |
| `init_all_peripherals` | (none) | Top-level: enables clocks, configures all peripherals |

## Dictionary Loading

The dictionary is built at tree INIT time by `se_load_function_dict` (`se_builtins_dict.lua`). It pairs `dict_key` names from `node.params` with child subtrees from `node.children`:

```lua
-- se_load_function_dict builds:
inst.blackboard["fn_dict"] = {
    [s_expr_hash("write_register")]         = function(inst, node, eid, edata)
        return se_runtime.invoke_any(inst, write_register_subtree, eid, edata)
    end,
    [s_expr_hash("read_modify_write")]       = function(inst, node, eid, edata)
        return se_runtime.invoke_any(inst, read_modify_write_subtree, eid, edata)
    end,
    [s_expr_hash("enable_peripheral_clock")] = function(...) ... end,
    [s_expr_hash("configure_gpio_pin")]      = function(...) ... end,
    [s_expr_hash("configure_uart")]          = function(...) ... end,
    [s_expr_hash("configure_spi")]           = function(...) ... end,
    [s_expr_hash("init_all_peripherals")]    = function(...) ... end,
}
```

Each closure captures its child node table by reference. The dictionary persists in the blackboard for the lifetime of the tree instance and can be called from anywhere in the program.

## Calling Dictionary Functions

There are three ways to call dictionary functions, all implemented in `se_builtins_spawn.lua`:

### 1. Direct Call by Name (`se_exec_dict_dispatch`)

```
SE_EXEC_DICT_DISPATCH
  params: [field_ref:"fn_dict", str_hash:{hash=H, str="init_all_peripherals"}]
```

Used from the main program to invoke a dictionary function by a name known at pipeline compile time. The function name is hashed at compile time and stored as a `str_hash` param. On INIT, the builtin reads the dictionary from the blackboard and stores it in `inst.current_dict`. On TICK, it looks up `dict[hash]` and calls the closure.

**Runtime behavior** (from `se_builtins_spawn.lua`):

```lua
M.se_exec_dict_dispatch = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local dict = inst.blackboard[param_field_name(node, 1)]
        inst.current_dict = dict
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: look up key hash, call the closure
    local key = (type(p2.value) == "table") and p2.value.hash or p2.value
    local entry = dict[key]
    local result = entry(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE

    -- DISABLE → CONTINUE: keep the dispatch node alive
    if result == SE_PIPELINE_DISABLE then result = SE_PIPELINE_CONTINUE end
    return result
end
```

### 2. Indirect Call via Hash Field (`se_exec_dict_fn_ptr`)

```
SE_SET_HASH_FIELD
  params: [field_ref:"fn_hash", str_hash:{hash=H, str="init_all_peripherals"}]
  → inst.blackboard["fn_hash"] = s_expr_hash("init_all_peripherals")

SE_EXEC_DICT_FN_PTR
  params: [field_ref:"fn_dict", field_ref:"fn_hash"]
```

This two-step approach stores a function name hash into a blackboard field (`fn_hash`), then `se_exec_dict_fn_ptr` reads the hash from that field at runtime and dispatches the corresponding dictionary function.

While the example above uses a compile-time constant, the hash field can be set by any source at runtime:

- **An external tree** writing via `se_set_external_field` (the cross-tree calling pattern)
- **A user-defined Lua function** setting the field based on sensor input or protocol messages
- **A state machine** selecting different dictionary functions based on runtime conditions
- **An event handler** dispatching different operations based on event type

**Runtime behavior** (from `se_builtins_spawn.lua`):

```lua
M.se_exec_dict_fn_ptr = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local dict = inst.blackboard[param_field_name(node, 1)]
        inst.current_dict = dict
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: read key from blackboard field at runtime
    local key = inst.blackboard[param_field_name(node, 2)]
    local entry = dict[key]
    local result = entry(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE
    if result == SE_PIPELINE_DISABLE then result = SE_PIPELINE_CONTINUE end
    return result
end
```

### 3. Internal Call (`se_exec_dict_internal`)

```
-- Push params onto stack first:
SE_QUAD MOVE(local:addr, null, stack_push)
SE_QUAD MOVE(local:value, null, stack_push)

SE_EXEC_DICT_INTERNAL
  params: [str_hash:{hash=H, str="write_register"}]
```

Inside a dictionary function, `se_exec_dict_internal` calls another function within the same dictionary. It uses `inst.current_dict` which was set by the parent `se_exec_dict_dispatch` or `se_exec_dict_fn_ptr` on INIT. Parameters are pushed onto the stack using `se_quad` MOVE nodes with `{type="stack_push"}` as the destination. The called function receives these as its stack frame parameters via `se_stack_frame_instance`.

**Runtime behavior** (from `se_builtins_spawn.lua`):

```lua
M.se_exec_dict_internal = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT or event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    local dict = inst.current_dict
    local key = (type(p1.value) == "table") and p1.value.hash or p1.value
    local entry = dict[key]
    local result = entry(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE
    if result == SE_PIPELINE_DISABLE then result = SE_PIPELINE_CONTINUE end
    return result
end
```

## The User Function: write_register

The only user-defined Lua function in this test. It reads two parameters from the stack frame — the register address and the value to write — and prints them:

```lua
local function write_register(inst, node)
    local stk = inst.stack
    assert(stk, "write_register: no stack on instance")

    local se_stack = require("se_stack")
    local address = se_stack.get_local(stk, 0) or 0
    local value   = se_stack.get_local(stk, 1) or 0

    print(string.format("write_register: addr=0x%08X value=0x%08X", address, value))
end
```

In the LuaJIT runtime, stack entries are plain Lua numbers (not typed `s_expr_param_t` structs). `se_stack.get_local(stk, 0)` returns the first parameter directly.

In a production system targeting actual hardware via LuaJIT FFI, this function would perform a memory-mapped register write. All the address computation and bit manipulation is handled by the dictionary functions' `se_quad` nodes, so this single Lua function serves every register write in the entire peripheral configuration sequence.

## Main Program Flow

The tree structure exercises both dictionary calling methods:

```
SE_FUNCTION_INTERFACE (root)
├── [o_call] SE_SET_FIELD uart_channel = 1
├── [o_call] SE_SET_FIELD uart_baud = 0x0683
├── [o_call] SE_SET_FIELD uart_parity = 0
├── ... (GPIO, SPI field initialization)
│
├── [o_call] SE_LOAD_FUNCTION_DICT → inst.blackboard["fn_dict"] = {hash→closure}
│
├── [m_call] SE_EXEC_DICT_DISPATCH("fn_dict", "init_all_peripherals")
│   → Direct call: compile-time hash lookup in dict
│   → Executes full peripheral init sequence
│
├── [o_call] SE_LOG "--- Configuration Results ---"
├── [o_call] SE_LOG_INT "config_state 0x%08X"
├── ... (log other blackboard fields)
│
├── [o_call] SE_SET_HASH_FIELD("fn_hash", "init_all_peripherals")
│   → inst.blackboard["fn_hash"] = s_expr_hash("init_all_peripherals")
│
├── [m_call] SE_EXEC_DICT_FN_PTR("fn_dict", "fn_hash")
│   → Indirect call: reads hash from blackboard["fn_hash"] at runtime
│   → Executes same sequence again (identical results)
│
└── SE_RETURN_FUNCTION_TERMINATE
```

Steps 3 and 5 both invoke `init_all_peripherals`, but through different mechanisms. The direct call uses a compile-time constant hash embedded in `params[2]`. The indirect call reads the hash from `inst.blackboard["fn_hash"]` — the same field that an external tree or user Lua function would write to in a production system. Both paths produce identical results, confirming that the two calling conventions are interchangeable.

## Control Flow Within the Dictionary

The dictionary supports the full range of S-Expression control flow constructs. This test demonstrates:

- **`se_if_then_else`** (`se_builtins_flow_control.lua`) — used in `init_all_peripherals` to conditionally configure UART and SPI. If `inst.blackboard["uart_channel"] ~= 0`, UART is configured; otherwise skipped. The predicate is `se_field_ne` (`se_builtins_pred.lua`).
- **`se_sequence_once`** — ensures the initialization sequence runs exactly once per tick.
- **`se_set_field` / `se_field_ne`** — blackboard fields store configuration state and drive conditional logic.

## Expression Compiler Usage

The dictionary functions use `quad_expr` (`s_expr_compiler.lua`) to compile C-like expressions into `se_quad` nodes at pipeline time:

```lua
quad_expr("shift = pin * 2", cv, {"t0"})()
quad_expr("mask = 3 << shift", cv, {"t0"})()
quad_expr("set_val = mode << shift", cv, {"t0"})()
quad_expr("reg_addr = port_base + 8", cv, {"t0"})()
```

These compile to `se_quad` nodes with opcodes like `IMUL` (0x02), `BIT_SHL` (0x14), and `IADD` (0x00). At runtime, `exec_quad` in `se_builtins_quads.lua` dispatches on the opcode and reads/writes via `se_stack.get_local` / `se_stack.set_local` for `stack_local` params.

The `frame_vars` function defines named locals and scratch variables with stack frame offsets:

```lua
local cv = frame_vars(
    {"port_base:int", "pin:int", "mode:int", "speed:int", "pull:int",
     "shift:int", "mask:int", "reg_addr:int", "set_val:int"},
    {"t0:int", "t1:int"}
)
```

The `:int` annotations drive the compiler's type inference, ensuring integer opcodes (IADD, BIT_SHL, etc.) are selected rather than float opcodes.

**Important constraint:** Values that will be read after a `stack_push` call must be stored in frame locals (`stack_local`), not scratch (`stack_tos`) variables. The `se_stack.push` call advances `stk.sp`, which invalidates TOS-relative offsets.

## Test Results Explained

The test runs to completion in a single tick, producing 13 register writes (executed twice — once via direct call, once via indirect hash call):

### Clock Enables (RCC)

| Register | Value | Description |
|----------|-------|-------------|
| `0x40023830` (AHB1ENR) | `0x00000001` | Enable GPIOA clock (bit 0) |
| `0x40023844` (APB2ENR) | `0x00000010` | Enable USART1 clock (bit 4) |
| `0x40023844` (APB2ENR) | `0x00001000` | Enable SPI1 clock (bit 12) |

### GPIO PA5 Configuration

Pin 5 uses bit positions 10–11 (shift = pin × 2 = 10), with a 2-bit mask of `0xC00`. Computed by `quad_expr("shift = pin * 2")` → IMUL, `quad_expr("mask = 3 << shift")` → BIT_SHL:

| Register | Value | Description |
|----------|-------|-------------|
| `0x40020000` (MODER) | `0x00000800` | Alt-function mode (2 << 10) |
| `0x40020008` (OSPEEDR) | `0x00000800` | High speed (2 << 10) |
| `0x4002000C` (PUPDR) | `0x00000000` | No pull-up/pull-down (0 << 10) |

### USART1 Configuration

| Register | Value | Description |
|----------|-------|-------------|
| `0x4001100C` (CR1) | `0x00000000` | Disable USART (clear UE bit 13) |
| `0x40011008` (BRR) | `0x00000683` | Baud rate divisor for 115200 @ 16MHz |
| `0x4001100C` (CR1) | `0x0000200C` | Set UE, TE, RE (enable with TX+RX) |
| `0x4001100C` (CR1) | `0x00002000` | Enable USART (set UE bit 13) |

### SPI1 Configuration

SPI1 CR1 is at base address `0x40013000` (offset 0). Clock divider 2 maps to bits 5:3 = `0x10`. Computed by `quad_expr("cr1 = clk_div << 3")` → BIT_SHL:

| Register | Value | Description |
|----------|-------|-------------|
| `0x40013000` (CR1) | `0x00000000` | Disable SPI (clear SPE bit 6) |
| `0x40013000` (CR1) | `0x00000010` | CR1 = clk_div(2)<<3 \| mode(0) \| bit_order(0)<<7 |
| `0x40013000` (CR1) | `0x00000040` | Enable SPI (set SPE bit 6) |

### Final Blackboard State

After configuration completes:

```lua
inst.blackboard["config_state"]      -- 4 (CONFIG_DONE)
inst.blackboard["peripherals_ready"] -- 1 (all peripherals initialized)
inst.blackboard["error_code"]        -- 0 (no errors)
```

## Dictionary Calling Methods Summary

| Method | Builtin | Module | Hash Source | Use Case |
|--------|---------|--------|-------------|----------|
| Direct | `se_exec_dict_dispatch` | `se_builtins_spawn.lua` | Compile-time `str_hash` param | Known function, called from main program |
| Indirect | `se_exec_dict_fn_ptr` | `se_builtins_spawn.lua` | Blackboard field (runtime) | Variable dispatch, external tree calls, event-driven selection |
| Internal | `se_exec_dict_internal` | `se_builtins_spawn.lua` | Compile-time `str_hash` param | Dictionary function calling another dictionary function |

The indirect method is the key enabler for cross-tree dictionary invocation. A parent tree can write any function hash into the child's `fn_hash` field via `se_set_external_field`, then tick the child to execute that function. The child tree's dictionary serves as a shared library of functions callable by any tree in the system.

## Comparison with C Implementation

| Aspect | C Runtime | LuaJIT Runtime |
|--------|-----------|----------------|
| Dictionary storage | ROM pointer to flat `s_expr_param_t[]` array | `{hash → closure}` Lua table in blackboard |
| Dictionary building | Pointer assignment (zero allocation) | `se_load_function_dict` builds closures (one-time GC allocation) |
| Function invocation | `s_expr_invoke_any(inst, params, ...)` on param array | `closure(inst, node, eid, edata)` → `invoke_any(inst, child_node, ...)` |
| `write_register` signature | `fn(inst, params, count, event_type, event_id, event_data)` | `fn(inst, node)` |
| Stack parameter access | `s_expr_stack_get_local(stack, 0)->uint_val` | `se_stack.get_local(stk, 0)` (plain Lua number) |
| Register arithmetic | `se_quad` with typed `s_expr_param_t` values | `se_quad` with plain Lua numbers via `bit.*` library |
| Hardware I/O | Actual memory-mapped writes (on target) | Print simulation (or FFI for real hardware) |
| `inst.current_dict` | Points into ROM param array | References the Lua `{hash → closure}` table |

## Runtime Modules Exercised

| Module | Functions | Role |
|--------|-----------|------|
| `se_builtins_dict.lua` | `se_load_function_dict`, `s_expr_hash` | Build `{hash → closure}` dictionary |
| `se_builtins_spawn.lua` | `se_exec_dict_dispatch`, `se_exec_dict_fn_ptr`, `se_exec_dict_internal` | Dictionary dispatch (all three methods) |
| `se_builtins_stack.lua` | `se_frame_allocate`, `se_stack_frame_instance` | Stack frame lifecycle for dictionary functions |
| `se_builtins_quads.lua` | `se_quad` (IADD, IMUL, BIT_SHL, BIT_AND, BIT_OR, BIT_NOT, MOVE) | Register arithmetic |
| `se_builtins_flow_control.lua` | `se_function_interface`, `se_sequence_once`, `se_if_then_else`, `se_chain_flow` | Control flow |
| `se_builtins_pred.lua` | `se_field_ne` | Conditional peripheral configuration |
| `se_builtins_oneshot.lua` | `se_log`, `se_log_int`, `se_set_field`, `se_set_hash_field` | Logging, field writes |
| `se_builtins_return_codes.lua` | `se_return_function_terminate`, `se_return_pipeline_terminate` | Termination |
| `se_stack.lua` | `new_stack`, `push`, `pop`, `push_frame`, `pop_frame`, `get_local`, `set_local` | Stack data structure |
| `se_runtime.lua` | `new_module`, `new_instance`, `tick_once`, `invoke_any` | Core engine |

## Test Harness

```lua
local se_runtime = require("se_runtime")
local se_stack   = require("se_stack")
local module_data = require("function_dictionary_test_module")

local fns = se_runtime.merge_fns(
    require("se_builtins_flow_control"),
    require("se_builtins_pred"),
    require("se_builtins_oneshot"),
    require("se_builtins_delays"),
    require("se_builtins_dispatch"),
    require("se_builtins_return_codes"),
    require("se_builtins_stack"),
    require("se_builtins_quads"),
    require("se_builtins_dict"),
    require("se_builtins_spawn"),
    -- User-defined:
    {
        write_register = function(inst, node)
            local stk = inst.stack
            local addr  = se_stack.get_local(stk, 0) or 0
            local value = se_stack.get_local(stk, 1) or 0
            print(string.format("write_register: addr=0x%08X value=0x%08X", addr, value))
        end,
    }
)

local mod = se_runtime.new_module(module_data, fns)
local inst = se_runtime.new_instance(mod, "function_dictionary")
inst.stack = se_stack.new_stack(256)

local result = se_runtime.tick_once(inst)

-- Verify
assert(inst.blackboard["config_state"] == 4,
    "Expected config_state=4, got " .. tostring(inst.blackboard["config_state"]))
assert(inst.blackboard["peripherals_ready"] == 1,
    "Expected peripherals_ready=1, got " .. tostring(inst.blackboard["peripherals_ready"]))
assert(inst.blackboard["error_code"] == 0,
    "Expected error_code=0, got " .. tostring(inst.blackboard["error_code"]))

print(string.format("Result: %s",
    result == se_runtime.SE_FUNCTION_TERMINATE and "FUNCTION_TERMINATE" or tostring(result)))
print("✅ PASSED")
```

## Key Design Pattern

This test illustrates a powerful pattern for embedded systems: **a minimal set of user-defined Lua primitives composed through a dictionary of S-Expression functions**. The dictionary can be loaded once and called throughout the tree's lifetime. By moving register-level logic into the dictionary, the user code stays small (one `write_register` function), while the configuration logic remains flexible, readable, and modifiable without changing user code.

In the LuaJIT runtime, the dictionary is a live `{hash → closure}` table that can be inspected, extended, or replaced at runtime — offering more flexibility than the C version's ROM-resident param arrays while maintaining identical execution semantics.

## Files

| File | Description |
|------|-------------|
| `function_dictionary_test_module.lua` | Pipeline-generated `module_data` Lua table |
| `test_function_dictionary.lua` | LuaJIT test harness |
| `se_builtins_dict.lua` | `se_load_function_dict`, `s_expr_hash` |
| `se_builtins_spawn.lua` | `se_exec_dict_dispatch`, `se_exec_dict_fn_ptr`, `se_exec_dict_internal` |
| `se_builtins_stack.lua` | `se_frame_allocate`, `se_stack_frame_instance` |
| `se_builtins_quads.lua` | `se_quad` for register arithmetic |