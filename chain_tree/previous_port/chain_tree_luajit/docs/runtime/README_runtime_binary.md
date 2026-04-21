# libcfl_core

Core runtime library for the **ChainTree** control flow framework — a unified architecture combining behavior trees, state machines, and sequential control flows into a single execution engine.

ChainTree targets systems spanning from 32 KB ARM Cortex-M microcontrollers to 8 GB+ servers, using a common codebase with platform-specific tuning via compile-time configuration.

## Building

```bash
make            # builds libcfl_core.a and libcfl_core.so
make clean      # removes build artifacts
```

### Cross-compiling for 32-bit ARM

```bash
make CC=arm-none-eabi-gcc CFLAGS+="-DCFL_32BIT -mcpu=cortex-m4 -mthumb"
```

The library auto-detects 64-bit platforms. Override with `-DCFL_32BIT` or `-DCFL_64BIT` for cross-compilation. This controls alignment (4 bytes on 32-bit, 8 bytes on 64-bit) and event queue data widths throughout the library.

### Installing

```bash
sudo make install               # installs to /usr/local
make install PREFIX=/opt/cfl    # custom prefix
```

## Directory Layout

```
libcfl_core/
├── include/         Public headers
├── src/             Implementation files
├── Makefile
├── LICENSE
└── README.md
```

## Architecture

The library is organized in layers. Each layer depends only on the layers below it.

```
┌─────────────────────────────────────────┐
│              cfl_runtime                │  Orchestration, test management
├─────────────────────────────────────────┤
│              cfl_engine                 │  Execution engine, node lifecycle
├──────────────┬──────────┬───────────────┤
│ cfl_event    │ cfl_timer│ cfl_heap      │  Event queues, timers,
│ _queue       │ _system  │ _arena        │  arena allocation
├──────────────┴──────────┴───────────────┤
│          cfl_heap   cfl_perm            │  Core allocators
├─────────────────────────────────────────┤
│       cfl_global_definitions            │  Platform config (32/64-bit)
└─────────────────────────────────────────┘
```

## Modules

### Platform Configuration

**cfl_global_definitions.h** — Auto-detects 32-bit vs 64-bit platforms and derives alignment constants. Single source of truth for `BLOCK_ALIGNMENT`, `ARENA_ALIGNMENT`, and `MIN_BLOCK_SIZE`.

### Memory Management

**cfl_perm** — Permanent bump allocator. Allocations never free individually; the entire pool resets at once. Used for long-lived structures (handles, lookup tables, control blocks). Supports index-based and pointer-based access.

**cfl_heap** — General-purpose heap with block headers, footer guards, corruption detection, and automatic coalescing of free blocks. Tracks allocation ownership by node ID.

**cfl_heap_arena_allocate** — Arena system built on top of the heap. Supports up to 254 concurrent arenas, each with bump allocation. Allocator 0 is permanent (from perm); allocators 1–253 are heap-backed and can be created/destroyed at runtime. Provides node-to-allocator mapping for the tree walker.

### Event System

**cfl_event_queue** — Dual-priority (high/low) ring buffer event queue. Supports typed events: unsigned, integer, float, pointer, JSON record, node ID, and streaming data. Tracks queue depth statistics.

### Timing

**cfl_timer_system** — Elapsed-time timer system for node scheduling and watchdogs. Allocates timer slots from the permanent allocator.

### Execution Engine

**cfl_engine** — Core execution engine managing node lifecycle (initialize, execute, terminate), function dispatch, and the tree walker. Maintains bitmap-based node state tracking.

**cfl_runtime** — Top-level orchestration layer. Creates and configures engine instances, manages test/knowledge-base loading, and provides the main run loop.

## Include Chain

Headers are designed so that including a higher-level header automatically provides everything below it:

```
cfl_runtime.h
  └── cfl_engine.h
        ├── cfl_perm.h ──── cfl_global_definitions.h
        ├── cfl_heap.h
        ├── cfl_heap_arena_allocate.h
        ├── cfl_event_queue.h
        └── cfl_timer_system.h
```

Most application code only needs `#include "cfl_runtime.h"`.

## License

MIT — see [LICENSE](LICENSE).

