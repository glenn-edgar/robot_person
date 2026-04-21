# Cross-Compilation Guide

ChainTree targets platforms from 32KB ARM Cortex-M microcontrollers to 8GB+ servers. This guide covers cross-compilation setup and platform considerations.

## ARM Cortex-M (Bare Metal)

### Basic Cross-Compilation

```bash
make CC=arm-none-eabi-gcc CFLAGS+="-DCFL_32BIT -mcpu=cortex-m4 -mthumb"
```

### Typical CFLAGS for Cortex-M4

```bash
CFLAGS = -mcpu=cortex-m4 \
         -mthumb \
         -mfloat-abi=hard \
         -mfpu=fpv4-sp-d16 \
         -DCFL_32BIT \
         -Os \
         -ffunction-sections \
         -fdata-sections \
         -Wall -Wextra -std=c11
```

### Linker Flags

```bash
LDFLAGS = -Wl,--gc-sections \
          -T linker_script.ld \
          --specs=nosys.specs \
          --specs=nano.specs
```

`--gc-sections` removes unused functions — important since ChainTree registers all built-in functions but a typical application uses a subset.

### Memory Layout Example (STM32F4, 192KB RAM)

```
Flash (1MB):
  0x08000000  Vector table + startup
  0x08001000  Application code
  0x080A0000  ChainTree binary image (.ctb embedded as const array)
  0x080C0000  S-Engine module binary (const array)

RAM (192KB):
  0x20000000  Stack (4KB)
  0x20001000  perm_buffer (32KB) — permanent allocator
  0x20009000  Heap (8KB) — general + arenas
  0x2000B000  BSS/data
```

### Minimal Configuration

For 32KB RAM targets:

```c
params->perm_buffer_size = 8192;       // 8KB permanent
params->heap_size = 2048;              // 2KB heap
params->allocator_0_size = 32;         // 32-byte arenas
params->event_queue_high_priority_size = 4;
params->event_queue_low_priority_size = 8;
```

## 32-Bit vs 64-Bit

### Platform Auto-Detection

ChainTree auto-detects the platform width from `sizeof(void*)`. Override with:

```bash
-DCFL_32BIT    # Force 32-bit mode
-DCFL_64BIT    # Force 64-bit mode
```

### What Changes

| Aspect | 32-bit | 64-bit |
|--------|--------|--------|
| Pointer size | 4 bytes | 8 bytes |
| Alignment | 4 bytes | 8 bytes |
| Event queue entry | 8 bytes | 16 bytes |
| Blackboard uint64 field | 8 bytes | 8 bytes (same) |
| `cfl_int_t` | `int32_t` | `int64_t` |
| `cfl_size_t` | `uint32_t` | `uint64_t` |

### S-Engine 32-Bit vs 64-Bit

```bash
# 32-bit module (default, 8-byte params)
luajit s_compile.lua module.lua --all-bin --32bit

# 64-bit module (16-byte params)
luajit s_compile.lua module.lua --all-bin --64bit
```

Controlled by `MODULE_IS_64BIT` define (default 0):

| Aspect | 32-bit | 64-bit |
|--------|--------|--------|
| `s_expr_param_t` size | 8 bytes | 16 bytes |
| Hash width | FNV-1a 32-bit | FNV-1a 64-bit |
| `ct_int_t` | `int32_t` | `int64_t` |
| `ct_float_t` | `float` | `double` |
| Binary suffix | `_32.bin`, `_bin_32.h` | `_64.bin`, `_bin_64.h` |

**Important:** The s-engine binary format must match the target. A 32-bit binary cannot load on a 64-bit runtime.

## Linux / macOS / Windows (Host)

Default build uses the system compiler:

```bash
make                    # uses cc (usually gcc or clang)
make CC=clang           # explicit clang
make CC=gcc-13          # specific GCC version
```

### Debug Build

```bash
make CFLAGS="-Wall -Wextra -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L"
```

### Sanitizers

```bash
make CFLAGS="-Wall -Wextra -O0 -g -std=c11 -fsanitize=address,undefined"
```

## Dependencies

ChainTree has minimal dependencies:

| Dependency | Required By | Notes |
|-----------|-------------|-------|
| `libc` | Everything | Standard C library |
| `libm` | Math operations | `-lm` link flag |
| `luajit` | DSL compilation only | Not needed at runtime |
| `libfnv1a.so` | Binary image generation only | In `lua_dsl/binary_image/` |

The runtime libraries (`libcfl_binarycore.a`, `libcfl_core_functions.a`, `libs_s_engine.a`) are fully static with no external dependencies beyond libc and libm.
