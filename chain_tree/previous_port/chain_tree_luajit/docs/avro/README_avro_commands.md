## Macro Command Reference

The following macros facilitate the generation of C headers, binary schemas, and packet initializers.

| Macro | Output File | Description |
|-------|-------------|-------------|
| `GENERATE()` | `<n>.h` | Generates C headers containing structs, wire types, packet APIs, and hash constants. |
| `GENERATE_BINARY()` | `<n>.bin` | Creates a binary schema blob for file-based operations. |
| `GENERATE_BINARY_HEADER()` | `<n>_bin.h` | Creates an embeddable `const uint8_t[]` of the binary schema blob. |
| `GENERATE_CONST_PACKETS()` | `<n>_bin.h` | Generates C struct initializers (`static const _packet_t`). |
| `GENERATE_CONST_PACKETS_BINARY()` | `<n>_bin.h` | Generates raw `uint8_t[]` blobs with associated cast macros. |
| `GENERATE_ALL()` | All of the above | A convenience wrapper that calls `GENERATE()`, `GENERATE_BINARY()`, and `GENERATE_BINARY_HEADER()`. |