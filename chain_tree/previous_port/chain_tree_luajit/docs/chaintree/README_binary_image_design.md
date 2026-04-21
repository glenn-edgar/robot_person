# ChainTree Binary Image Format Specification

**Version:** 1.0 Draft  
**Date:** February 2026  
**Status:** Design  

## 1. Overview

The ChainTree Binary Image format replaces the current 9 matched .h/.c file pairs with a single flat binary image. The image is directly memory-mappable with no pointer relocation required. All internal references use byte offsets from the image base.

Functions are referenced by FNV-1a 32-bit hash. The runtime registers function implementations against their hash at startup. Node structures reference functions by 16-bit index into sorted hash tables, where the array position implicitly defines the slot index.

### 1.1 Design Goals

- **Zero-copy load**: mmap the file, cast to header, begin execution.
- **No generated C code**: Eliminates all .h/.c codegen. The pipeline produces one binary artifact.
- **Runtime function binding**: Functions are registered by name at startup; the runtime resolves names to FNV-1a hashes and performs binary search to find the slot.
- **Cross-platform**: Fixed-size fields, explicit alignment, little-endian byte order.
- **Deterministic**: Identical input JSON always produces identical binary output (sorted hash tables, stable section ordering).

### 1.2 Pipeline Change

```
Before:  JSON IR  →  [Python|LuaJIT]  →  9x .h/.c pairs  →  compiler  →  binary
After:   JSON IR  →  [Python|LuaJIT]  →  .ctb image file  →  runtime loads directly
```

## 2. File Structure

```
┌──────────────────────────────────────────────┐  offset 0
│  File Header (64 bytes, fixed)               │
├──────────────────────────────────────────────┤  64
│  Section Directory (N × 16 bytes)            │
├──────────────────────────────────────────────┤
│  [padding to 8-byte alignment]               │
├──────────────────────────────────────────────┤
│  Section 0: Node Array                       │
├──────────────────────────────────────────────┤
│  Section 1: Link Table                       │
├──────────────────────────────────────────────┤
│  Section 2: Main Function Hash Table         │
├──────────────────────────────────────────────┤
│  Section 3: One-Shot Function Hash Table     │
├──────────────────────────────────────────────┤
│  Section 4: Boolean Function Hash Table      │
├──────────────────────────────────────────────┤
│  Section 5: Function Name Strings            │
├──────────────────────────────────────────────┤
│  Section 6: JSON Records                     │
├──────────────────────────────────────────────┤
│  Section 7: JSON Record Controls             │
├──────────────────────────────────────────────┤
│  Section 8: JSON String Data                 │
├──────────────────────────────────────────────┤
│  Section 9: Event String Table               │
├──────────────────────────────────────────────┤
│  Section 10: Bitmask Table                   │
├──────────────────────────────────────────────┤
│  Section 11: KB Info Table                   │
├──────────────────────────────────────────────┤
│  Section 12: KB Alias Table                  │
├──────────────────────────────────────────────┤
│  Section 13: General String Pool             │
├──────────────────────────────────────────────┤
│  Section 14: Blackboard Record (optional)    │
├──────────────────────────────────────────────┤
│  Section 15: Constant Records (optional)     │
└──────────────────────────────────────────────┘
```

All sections are aligned to 4-byte boundaries. Padding bytes between sections are zero-filled.

## 3. File Header

64 bytes, fixed layout. All multi-byte fields are little-endian.

```
Offset  Size  Field                Description
──────  ────  ───────────────────  ────────────────────────────────────
0       4     magic                0x43544231  ("CTB1")
4       2     version_major        1
6       2     version_minor        0
8       4     flags                Bit 0: has_node_data
                                   Bit 1: has_events
                                   Bit 2: has_bitmasks
                                   Bits 3-31: reserved (0)
12      4     total_image_size     Total file size in bytes
16      4     checksum             CRC32 of entire file with this field set to 0
20      2     section_count        Number of entries in section directory
22      2     node_count           Total node array entries (including gaps)
24      2     node_active_count    Operational nodes (excluding filtered gaps)
26      2     link_table_size      Number of uint16_t entries in link table
28      2     main_func_count      Entries in main function hash table
30      2     one_shot_func_count  Entries in one-shot function hash table
32      2     boolean_func_count   Entries in boolean function hash table
34      2     event_count          Number of event strings
36      2     bitmask_count        Number of bitmask definitions
38      2     kb_count             Number of knowledge bases
40      2     json_records_count   Number of JSON record entries
42      2     json_controls_count  Number of JSON record controls
44      4     json_strings_size    Size of JSON string data in bytes
48      16    reserved             Zero-filled, future use
```

### 3.1 Magic Number

`CTB1` = ChainTree Binary, format version 1. Read as uint32_t little-endian: `0x43544231`. The magic encodes the format family in the first 3 bytes and the major version in the 4th byte, allowing future format revisions (`CTB2`, etc.) to be detected without parsing further.

### 3.2 Checksum

CRC32 (ISO 3309 / zlib) computed over the entire file contents with the checksum field itself set to zero during computation. This validates image integrity after transfer or storage.

### 3.3 Flags

```
Bit 0  has_node_data    1 if JSON records/controls/strings sections are present
Bit 1  has_events       1 if event string table section is present
Bit 2  has_bitmasks     1 if bitmask table section is present
```

Absent sections have zero size in the section directory. The flags provide fast capability checks without scanning the directory.

## 4. Section Directory

Immediately follows the file header. Each entry is 16 bytes:

```
Offset  Size  Field          Description
──────  ────  ────────────   ──────────────────────────
0       4     section_type   Section type identifier
4       4     offset         Byte offset from image base
8       4     size           Section size in bytes
12      2     entry_count    Number of entries in section
14      2     entry_size     Size of each entry in bytes (0 if variable)
```

### 4.1 Section Type Identifiers

```
Type   Value    Section
─────  ──────   ──────────────────────────
NODE   0x0001   Node array
LINK   0x0002   Link table
MFHT   0x0003   Main function hash table
OSHT   0x0004   One-shot function hash table
BFHT   0x0005   Boolean function hash table
FSTR   0x0006   Function name strings
JREC   0x0007   JSON records
JCTL   0x0008   JSON record controls
JSTR   0x0009   JSON string data
EVNT   0x000A   Event string table
BMSK   0x000B   Bitmask table
KBIN   0x000C   KB info table
KBAL   0x000D   KB alias table
GSTR   0x000E   General string pool
MUSG   0x000F   Main function usage count
BBRD   0x0010   Blackboard record descriptor
CREC   0x0011   Constant records
```

## 5. Section Formats

### 5.1 Node Array (NODE, 0x0001)

Each entry is 20 bytes, identical to the existing `chaintree_node_t`:

```
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       2     uint16    node_index
2       2     uint16    parent_index           (0xFFFF = no parent)
4       2     uint16    depth
6       2     uint16    link_start
8       2     uint16    link_count             (bits 0-14: count, bit 15: auto_start)
10      2     uint16    main_function_index    (index into main hash table)
12      2     uint16    init_function_index    (index into one-shot hash table)
14      2     uint16    aux_function_index     (index into boolean hash table)
16      2     uint16    term_function_index    (index into one-shot hash table)
18      2     uint16    node_data_id           (index into JSON controls, 0xFFFF = none)
```

The array preserves original indices from the JSON IR. Filtered/gap entries have `parent_index = 0xFFFF` and all function indices set to 0 (CFL_NULL slot).

### 5.2 Link Table (LINK, 0x0002)

Flat array of `uint16_t` child node indices. Nodes reference into this table via `link_start` and `link_count`. No per-entry structure, just packed uint16_t values.

### 5.3 Function Hash Tables (MFHT/OSHT/BFHT, 0x0003-0x0005)

Each table is a sorted array of `uint32_t` FNV-1a hashes. The array position is the function slot index.

```
Entry size: 4 bytes
Layout:     uint32_t fnv1a_hash

Sorted in ascending order by hash value.
```

**Index 0 is always CFL_NULL** (hash of "CFL_NULL") in all three tables.

The runtime allocates a function pointer array of the same size as the hash table. Registration maps: `fnv1a(name)` → binary search → position = slot → `function_pointers[slot] = fn_ptr`.

**Collision handling:** At image generation time, if two function names within the same hash table produce the same FNV-1a hash, the pipeline raises an exception. The user must rename one function. At the scale of typical ChainTree configurations (tens to low hundreds of functions per table), FNV-1a collision probability is negligible.

### 5.4 Function Name Strings (FSTR, 0x0006)

Packed, null-terminated function name strings. Used for diagnostics and runtime error reporting. Each hash table entry's name is stored in the order corresponding to its slot position.

```
Layout:
  [main_func_0_name \0] [main_func_1_name \0] ... [main_func_N \0]
  [one_shot_func_0_name \0] ... [one_shot_func_N \0]
  [boolean_func_0_name \0] ... [boolean_func_N \0]
```

The runtime can use this section to verify registrations and produce meaningful error messages ("unregistered function: my_handler") by walking the string pool in slot order.

### 5.5 JSON Records (JREC, 0x0007)

Each entry is 8 bytes:

```
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    object_type            (json_type_t enum: 0-6)
4       4     uint32    value                  (interpretation depends on type)
```

Value interpretation by type:

```
Type              Value field
────────────────  ─────────────────────
JSON_TYPE_STRING  string_offset into JSON string data section
JSON_TYPE_INT32   int32 value (reinterpreted)
JSON_TYPE_FLOAT32 float32 value (reinterpreted)
JSON_TYPE_NULL    0
JSON_TYPE_BOOL    0 or 1
JSON_TYPE_ARRAY   element count
JSON_TYPE_OBJECT  key-value pair count × 2
```

### 5.6 JSON Record Controls (JCTL, 0x0008)

Each entry is 8 bytes:

```
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    start_position         (index into JSON records array)
4       4     uint32    num_records            (number of records for this node)
```

Node's `node_data_id` indexes into this array.

### 5.7 JSON String Data (JSTR, 0x0009)

Packed null-terminated strings referenced by offset from JSON record string_offset values. Raw byte data, no per-entry structure.

### 5.8 Event String Table (EVNT, 0x000A)

Array of string offsets into the general string pool:

```
Entry size: 4 bytes
Layout:     uint32_t string_pool_offset
```

Ordered by event index. `event_strings[i]` = offset into general string pool for event name `i`.

### 5.9 Bitmask Table (BMSK, 0x000B)

Array of bitmask definitions, sorted by bit position:

```
Entry size: 8 bytes
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    string_pool_offset     (name in general string pool)
4       1     uint8     bit_position           (0-31)
5       3     uint8[3]  reserved               (zero-filled)
```

### 5.10 KB Info Table (KBIN, 0x000C)

Array of knowledge base descriptors:

```
Entry size: 24 bytes
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    name_offset            (in general string pool)
4       2     uint16    root_node_index
6       2     uint16    start_index
8       2     uint16    node_count
10      2     uint16    max_depth
12      2     uint16    memory_factor
14      2     uint16    alias_start            (index into KB alias table)
16      2     uint16    alias_count
18      6     uint8[6]  reserved               (zero-filled)
```

### 5.11 KB Alias Table (KBAL, 0x000D)

Array of node alias entries:

```
Entry size: 8 bytes
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    name_offset            (alias name in general string pool)
4       2     uint16    node_index
6       2     uint16    reserved               (zero)
```

KB info entries reference contiguous ranges within this table via `alias_start` and `alias_count`.

### 5.12 General String Pool (GSTR, 0x000E)

Packed null-terminated strings. Referenced by offset from event table, bitmask table, KB info, and KB alias sections. Deduplicated — identical strings share the same offset.

### 5.13 Blackboard Record (BBRD, 0x0010)

Defines a single mutable blackboard shared across all knowledge bases. The section contains a header, field descriptors, and a defaults blob. Optional — absent if no blackboard is defined in the DSL.

```
Header (12 bytes):
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    name_hash              FNV-1a hash of record name
4       2     uint16    total_size             Blackboard allocation size in bytes
6       2     uint16    field_count            Number of field descriptors
8       4     uint32    defaults_offset        Byte offset from section start to defaults blob
```

Followed by field descriptors (8 bytes each):

```
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    name_hash              FNV-1a hash of field name
4       2     uint16    offset                 Byte offset into blackboard buffer
6       2     uint16    size                   Field size in bytes
```

Followed by padding to 4-byte alignment, then the defaults blob (`total_size` bytes). The defaults blob contains typed values at their field offsets — the runtime copies this into the allocated blackboard at startup. Zero-filled bytes represent default value 0.

Supported field types and sizes:

```
DSL type   C type      Size   Alignment
─────────  ──────────  ────   ─────────
int32      int32_t     4      4
uint32     uint32_t    4      4
uint16     uint16_t    2      2
float      float       4      4
uint64     uint64_t    8      8
```

Fields are laid out with natural alignment. The total size is padded to 4-byte alignment.

At runtime, `cfl_image_loader.c` parses this section into a `cfl_bb_record_t` and attaches it to `handle.bb_table`. The runtime allocates the blackboard buffer from the permanent allocator and copies the defaults blob. Node functions access fields via compile-time offset macros (`CFL_BB_FIELD(handle, offset, type)`) or dynamic hash lookup (`cfl_bb_field_by_hash()`).

### 5.14 Constant Records (CREC, 0x0011)

An array of read-only named records. Optional — absent if no constant records are defined in the DSL. Multiple constant records are supported; duplicate names are not allowed.

The section is structured as a directory followed by the field descriptors and data blobs for each record, laid out sequentially.

Directory (8 bytes per record):

```
Offset  Size  Type      Field
──────  ────  ────────  ──────────────────────
0       4     uint32    name_hash              FNV-1a hash of record name
4       2     uint16    total_size             Data size in bytes
6       2     uint16    field_count            Number of field descriptors
```

The `entry_count` field in the section directory gives the number of records.

After the directory, for each record in order:

1. **Field descriptors** (8 bytes each, same format as BBRD field descriptors)
2. **Data blob** (`total_size` bytes, contains typed constant values at field offsets)

At runtime, the image loader parses these into a `cfl_bb_const_record_t` array and attaches it to `handle.bb_table`. The data pointers reference directly into the image memory (zero-copy). User code looks up records by hash (`cfl_bb_const_find()`) and reads fields via offset macros (`CFL_BB_CONST_FIELD(data_ptr, offset, type)`) or hash lookup (`cfl_bb_const_field_by_hash()`).

### 5.15 DSL Definition

The blackboard and constant records are defined in the Lua DSL frontend:

```lua
-- Mutable blackboard (one per configuration)
ct:define_blackboard("system_state")
    ct:bb_field("mode",        "int32",  0)       -- default 0
    ct:bb_field("temperature", "float",  20.0)    -- default 20.0
    ct:bb_field("debug_ptr",   "uint64", 0)
ct:end_blackboard()

-- Read-only constant records (any number, unique names)
ct:define_const_record("calibration")
    ct:const_field("gain",   "float",  1.5)
    ct:const_field("offset", "float", -0.25)
    ct:const_field("max",    "int32",  1000)
ct:end_const_record()
```

These calls can appear anywhere in the Lua file. The data flows through the JSON IR (`"blackboard"` top-level key) into stage 6, which emits the BBRD and CREC binary sections. The pipeline also emits a `{handle_name}_blackboard.h` file containing only `#define` offset constants — no runtime data, no generated C code.

## 6. Alignment and Padding

- Each section starts at a 4-byte aligned offset.
- Zero-fill padding bytes are inserted between sections as needed.
- The section directory offset and size fields reflect actual data, excluding trailing padding.

## 7. Runtime API

### 7.1 Loading

```c
typedef struct {
    const void *image_base;        /* mmap'd or loaded pointer */
    uint32_t    image_size;

    /* Parsed from header */
    const chaintree_node_t *nodes;
    uint16_t node_count;
    const uint16_t *link_table;

    /* Hash tables (point into image) */
    const uint32_t *main_hashes;
    const uint32_t *one_shot_hashes;
    const uint32_t *boolean_hashes;

    /* Function pointer arrays (allocated at runtime) */
    main_function_t     *main_functions;
    one_shot_function_t *one_shot_functions;
    boolean_function_t  *boolean_functions;

    /* Function name strings (for diagnostics) */
    const char *func_name_strings;

    /* Node data (point into image) */
    const json_record_t    *json_records;
    const record_control_t *json_controls;
    const char             *json_strings;

    /* String-based tables */
    const char *general_string_pool;
    /* ... event, bitmask, kb pointers */
} ct_runtime_t;
```

### 7.2 Initialization

```c
ct_runtime_t *ct_load(const void *image, uint32_t size);
```

1. Validate magic (`CTB1`), version, checksum.
2. Parse section directory.
3. Set all const pointers directly into image memory (zero copy).
4. Allocate three function pointer arrays, initialized to NULL.
5. Return handle.

### 7.3 Function Registration

```c
int ct_register_main(ct_runtime_t *rt, const char *name, main_function_t fn);
int ct_register_one_shot(ct_runtime_t *rt, const char *name, one_shot_function_t fn);
int ct_register_boolean(ct_runtime_t *rt, const char *name, boolean_function_t fn);
```

Each registration call:

1. Compute `hash = fnv1a_32(name)`.
2. Binary search the sorted hash table for `hash`.
3. If not found, return error (function not referenced by any node).
4. `function_pointers[position] = fn`.
5. Return the slot index.

### 7.4 Validation

```c
int ct_validate(const ct_runtime_t *rt);
```

After all registrations, walk the function pointer arrays. Any NULL slot (except index 0 = CFL_NULL) that is referenced by at least one node indicates an unregistered function. The runtime can use the function name strings section to report which functions are missing.

### 7.5 Function Name Lookup

The function name strings section stores names in slot order (main functions first, then one-shot, then boolean). To find the name for slot `i` in the main function table, walk `i` null terminators from the start of the main function name region.

For efficient reverse lookup (name → slot), the registration function already performs binary search and can cache results.

## 8. FNV-1a Hash

### 8.1 Algorithm

FNV-1a 32-bit as specified by Fowler-Noll-Vo:

```
hash = 2166136261  (FNV offset basis)
for each byte in input:
    hash = hash XOR byte
    hash = hash × 16777619  (FNV prime)
return hash as uint32_t
```

### 8.2 C Reference Implementation

```c
#include <stdint.h>

uint32_t fnv1a_32(const char *str) {
    uint32_t hash = 2166136261u;
    while (*str) {
        hash ^= (uint8_t)*str++;
        hash *= 16777619u;
    }
    return hash;
}
```

### 8.3 LuaJIT Usage

LuaJIT calls the C shared library via FFI to avoid 32-bit multiplication precision issues:

```lua
local ffi = require("ffi")
ffi.cdef[[ uint32_t fnv1a_32(const char *str); ]]
local fnv1a_lib = ffi.load("fnv1a")

local function fnv1a(str)
    return tonumber(fnv1a_lib.fnv1a_32(str))
end
```

### 8.4 Collision Policy

At image generation time, if two function names within the same hash table produce identical FNV-1a hashes, the pipeline raises a fatal error with both names. The user resolves the collision by renaming one function. Given typical table sizes (< 500 entries), the probability of any collision is approximately 1 in 35,000 per table (birthday problem: n²/2×2³²).

## 9. Image Generation Pipeline

The binary image generator replaces stage 6 (C codegen) in the existing pipeline. Stages 1-5 remain unchanged.

```
Stage 1: Load JSON          (unchanged)
Stage 2: Build node indices (unchanged)
Stage 3: Build function indices (unchanged)
Stage 4: Build link tables  (unchanged)
Stage 5: Encode node data   (unchanged)
Stage 6: Emit binary image  (NEW - replaces C codegen)
```

### 9.1 Stage 6 Binary Emission Steps

1. **Compute FNV-1a hashes** for all function names in each of the three tables.
2. **Check for collisions** within each table. Abort on collision.
3. **Sort** each hash table by hash value. Record the mapping from original index to sorted position.
4. **Remap** all node function indices from original ordering to sorted-table positions.
5. **Build general string pool** — deduplicate all event names, bitmask names, KB names, alias names.
6. **Build blackboard sections** — if a blackboard is defined in the JSON IR, compute field layouts with natural alignment, hash field names with FNV-1a, write typed defaults blob. Build CREC section for any constant records.
7. **Compute section sizes and offsets** with 4-byte alignment padding.
8. **Write header** with all counts, offsets, and flags.
9. **Write section directory.**
10. **Write each section** in order, with inter-section padding.
11. **Compute CRC32** over entire image (checksum field zeroed) and patch the header.
12. **Emit blackboard offset header** — `{handle_name}_blackboard.h` with `#define` offset constants only (no runtime data, no generated C code).

### 9.2 Output Formats

The pipeline produces:

- **`.ctb` raw binary**: Direct binary file for mmap/load at runtime.
- **`_image.h` C array**: `const uint8_t chaintree_image[] = { 0x43, 0x54, ... };` for embedding in firmware where filesystem access is unavailable.
- **`_blackboard.h` offset header** (if blackboard is defined): `#define BB_MODE_OFFSET 0`, `#define CONST_CALIBRATION_GAIN_OFFSET 0`, etc. Compile-time constants only — the runtime data is in the `.ctb` image.

## 10. Migration Path

The existing C codegen backend (stage 6) remains available. Both backends consume identical stage 1-5 output.

```
                    ┌──  stage6_codegen  ──→  9x .h/.c pairs
JSON IR → stages 1-5 ┤
                    └──  stage6_binary   ──→  .ctb / .h image
```

The runtime API (`ct_load`, `ct_register_*`) ships as a small C library (~200 lines) that replaces the current compiled-in handle initialization.

## 11. Size Comparison (Estimated)

For a typical configuration with 50 nodes, 20 main functions, 10 one-shot, 5 boolean:

```
Component              .h/.c (approx)    Binary image
─────────────────────  ────────────────   ────────────
Node array             2,000 bytes C      1,000 bytes (50 × 20)
Link table             200 bytes C        200 bytes
Function hash tables   n/a                140 bytes (35 × 4)
Function names         600 bytes C        400 bytes
JSON records           1,500 bytes C      800 bytes
String data            500 bytes C        500 bytes
KB info                400 bytes C        200 bytes
Overhead (header etc)  3,000 bytes C      200 bytes
─────────────────────  ────────────────   ────────────
Total                  ~8,200 bytes       ~3,440 bytes
```

The binary image is roughly 40-50% the size of the compiled C, plus it eliminates compile time entirely.