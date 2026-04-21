# ChainTree Build Pipeline

The ChainTree system uses a two-stage code generation pipeline. Stage 1 compiles a Lua DSL frontend into JSON IR. Stage 2 consumes the JSON IR and produces either C headers (for compile-time embedding) or binary images (for runtime loading). The S-Expression engine has its own separate compiler.

## Pipeline Overview

```
                         ┌─────────────────┐
                         │   Lua DSL (.lua) │
                         └────────┬────────┘
                                  │ Stage 1: s_build_json.sh
                                  ▼
                         ┌─────────────────┐
                         │   JSON IR (.json)│
                         └────────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │ Stage 2a    │ Stage 2b     │
                    ▼             ▼              │
           ┌──────────────┐ ┌──────────────┐    │
           │ C Headers    │ │ Binary Image │    │
           │ (.h + .c)    │ │ (.ctb + .h)  │    │
           └──────────────┘ └──────────────┘    │
                                                │
                    S-Expression Engine          │
                    (separate compiler)          │
                                                ▼
                         ┌─────────────────────────┐
                         │ S-Engine Binary (.bin/.h)│
                         └─────────────────────────┘
```

## Stage 1: Lua DSL to JSON IR

Compiles the ChainTree Lua DSL into a JSON intermediate representation. This is the stable contract between the frontend and all backends.

```bash
./s_build_json.sh <lua_test_file> <output_directory>
```

**Example:**
```bash
./s_build_json.sh dsl_tests/incremental_binary/incremental_build.lua dsl_tests/incremental_binary/
```

**Requires:** `luajit`

**Inputs:**
- `<lua_test_file>` — Lua DSL file (e.g., `incremental_build.lua`)

**Outputs:**
- `<basename>.json` — JSON IR (schema v1.0)
- `<basename>_debug.yaml` — Human-readable debug dump

**LUA_PATH:** Automatically set to resolve `lua_dsl/lua_support/` modules.

---

## Stage 2a: JSON to C Headers (Header-Based Runtime)

Generates matched `.h`/`.c` file pairs that compile directly into the application. Used with `runtime_h/libcfl_core.a`.

```bash
./s_build_headers_luajit.sh <input.json> <output_dir> [handle_name] [--no-support]
```

**Example:**
```bash
./s_build_headers_luajit.sh dsl_tests/incremental_build/incremental_build.json dsl_tests/incremental_build/
```

**Outputs:** 9 matched `.h`/`.c` file pairs compiled into the application.

**Options:**
- `handle_name` — base name for generated files (default: `chaintree_handle`)
- `--no-support` — skip generating support/utility headers

---

## Stage 2b: JSON to Binary Image (Binary Runtime)

Generates a single `.ctb` binary image loadable at runtime via mmap or embedded as a C array. Used with `runtime_binary/libcfl_binarycore.a`. This is the primary path for new development.

```bash
./s_build_headers_binary.sh <input.json> <output_dir> [handle_name]
```

**Example:**
```bash
./s_build_headers_binary.sh dsl_tests/incremental_binary/incremental_build.json dsl_tests/incremental_binary/
```

**Outputs:**
| File | Description |
|------|-------------|
| `{handle_name}.ctb` | Binary image — mmap-loadable at runtime |
| `{handle_name}_image.h` | C `const uint8_t[]` array — for firmware embedding |
| `{handle_name}_blackboard.h` | Blackboard field offset `#define`s |

The `.ctb` file uses magic `CTB1`, CRC32 checksums, and FNV-1a function hashing. Functions are resolved by hash at startup.

**Loading options:**
- **File loading:** `cfl_file_load("path/to/handle.ctb", &img)` — loads from filesystem via mmap
- **Embedded loading:** `cfl_embedded_load(chaintree_handle_image, SIZE, &img)` — loads from C array in ROM

Both produce an identical `cfl_image_loader_t` handle.

---

## S-Expression Engine Compiler

The S-Expression engine has its own compiler that produces binary module files. These are separate from the ChainTree pipeline — an s-engine module is loaded at runtime by ChainTree bridge nodes (`se_engine`, `se_engine_link`, `se_module_load`).

### Compile S-Engine Module

```bash
./s_expression/s_build.sh <entry_point.lua> <output_dir>
```

**Example:**
```bash
./s_expression/s_build.sh dsl_tests/s_engine_test_2/s_engine/chain_flow_dsl_tests.lua dsl_tests/s_engine_test_2/s_engine/
```

**Requires:** `luajit`

**Outputs:**
| File | Description |
|------|-------------|
| `<base>_records.h` | C struct definitions for all records |
| `<base>.h` | Module/tree/field hash `#define`s |
| `<base>_debug.h` | Debug hash-to-name mappings |
| `<base>_user_functions.h` | User function prototypes |
| `<base>_user_registration.c` | User function registration code |
| `<base>_32.bin` | Binary module — file-loadable at runtime |
| `<base>_bin_32.h` | Binary module as C `const uint8_t[]` for ROM embedding |
| `<base>_dump_32.h` | Human-readable parameter dump |

### Direct Invocation (Advanced)

```bash
# Full options
luajit s_expression/lua_dsl/s_compile.lua <input.lua> [options]

# Options:
#   --all          Generate all text outputs (.h, .c)
#   --all-bin      Generate all outputs including binary files
#   --outdir=<dir> Output directory
#   --32bit        Force 32-bit mode (default)
#   --64bit        Force 64-bit mode (16-byte params)
#   --helpers=<f>  Load helper functions
#   --dump         Print debug dump to stdout
```

### S-Engine Loading Options

Same as ChainTree — two loading paths:

- **File loading:** `s_engine_load_from_file(&engine, &alloc, "module_32.bin", ...)` — loads `.bin` from filesystem
- **ROM embedding:** `s_engine_load_from_rom(&engine, &alloc, module_bin_32, SIZE, ...)` — loads from `_bin_32.h` C array

When used inside ChainTree via `se_engine` or `se_engine_link`, the app registers module binaries before the engine starts:
```c
// ROM embedded (typical for firmware)
cfl_se_registry_register_def(reg, "module_name",
    module_bin_32, MODULE_BIN_32_SIZE);

// With user function registration callback
cfl_se_registry_register_def_with_user(reg, "module_name",
    module_bin_32, MODULE_BIN_32_SIZE,
    user_register_wrapper, NULL);
```

---

## Complete Build Example

### ChainTree with S-Engine (binary path)

```bash
# 1. Compile s-engine module
./s_expression/s_build.sh \
    dsl_tests/s_engine_test_2/s_engine/chain_flow_dsl_tests.lua \
    dsl_tests/s_engine_test_2/s_engine/

# 2. Generate ChainTree JSON IR from Lua DSL
./s_build_json.sh \
    dsl_tests/s_engine_test_2/s_engine_test_2.lua \
    dsl_tests/s_engine_test_2/

# 3. Generate ChainTree binary image
./s_build_headers_binary.sh \
    dsl_tests/s_engine_test_2/s_engine_test_2.json \
    dsl_tests/s_engine_test_2/

# 4. Build C application
cd dsl_tests/s_engine_test_2
make clean && make

# 5. Run
./main 0
```

### ChainTree Only (no S-Engine)

```bash
# 1. Generate JSON IR
./s_build_json.sh \
    dsl_tests/incremental_binary/incremental_build.lua \
    dsl_tests/incremental_binary/

# 2. Generate binary image
./s_build_headers_binary.sh \
    dsl_tests/incremental_binary/incremental_build.json \
    dsl_tests/incremental_binary/

# 3. Build and run
cd dsl_tests/incremental_binary
make clean && make && ./main
```

---

## Cross-Compilation

For 32-bit ARM targets:
```bash
make CC=arm-none-eabi-gcc CFLAGS+="-DCFL_32BIT -mcpu=cortex-m4 -mthumb"
```

For 64-bit s-engine modules:
```bash
luajit s_expression/lua_dsl/s_compile.lua module.lua --64bit --all-bin
```

---

## Pipeline Stages (Internal)

The ChainTree binary pipeline runs 6 internal stages:

| Stage | Module | Description |
|-------|--------|-------------|
| 1 | stage1_handle | Load JSON IR, extract metadata |
| 2 | stage2_node_index | Build node indices, filter metadata nodes |
| 3 | stage3_function_index | Build function indices (main, oneshot, boolean) |
| 4 | stage4_link_table | Build parent-child link tables |
| 5 | stage5_node_data | Encode node data (JSON records, string table) |
| 6 | stage6_binary | Emit `.ctb` binary image with sections (BBRD, CREC, FSTR, etc.) |

The header path uses stage6_codegen instead of stage6_binary to emit `.h`/`.c` files.
