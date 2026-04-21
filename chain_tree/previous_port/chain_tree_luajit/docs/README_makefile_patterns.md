# Makefile Patterns

Three Makefile variants are used across the test suite. All use GCC with `-MMD -MP` for automatic header dependency tracking.

## Variant 1: ChainTree Only (incremental_binary)

Links two libraries. No s-engine dependency.

```makefile
CORE_LIB = ../../runtime_binary/libcfl_binarycore.a
FUNC_LIB = ../../runtime_functions/libcfl_core_functions.a

$(TARGET): $(OBJS) $(FUNC_LIB) $(CORE_LIB)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(FUNC_LIB) $(CORE_LIB) -lm
```

**Link order matters:** functions before core (`$(FUNC_LIB) $(CORE_LIB) -lm`).

## Variant 2: ChainTree + S-Engine (s_test_binary, s_engine_test_2)

Links three libraries. Build order enforced by dependencies.

```makefile
CORE_LIB = ../../runtime_binary/libcfl_binarycore.a
FUNC_LIB = ../../runtime_functions/libcfl_core_functions.a
SE_LIB   = ../../s_expression/lib/libs_s_engine.a

# s_expression must build first (installs headers runtime_functions needs)
$(FUNC_LIB): $(FUNC_LIB_SOURCES) $(SE_LIB)
	$(MAKE) -C $(FUNC_LIB_DIR)

$(SE_LIB): $(SE_LIB_SOURCES)
	$(MAKE) -C $(SE_LIB_DIR)/runtime

# App objects need library headers installed first
$(BUILD_DIR)/%.o: %.c $(LOCAL_HEADERS) | $(BUILD_DIR) libs
	$(CC) $(CFLAGS) $(DEPFLAGS) -c $< -o $@

$(TARGET): $(OBJS) $(FUNC_LIB) $(CORE_LIB) $(SE_LIB)
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(FUNC_LIB) $(CORE_LIB) $(SE_LIB) -lm
```

**Build order:** s_expression → runtime_functions → runtime_binary → app.

The `libs` phony target ensures all libraries build before any `.o` compilation (headers must be installed):
```makefile
libs: $(FUNC_LIB) $(CORE_LIB) $(SE_LIB)
```

## Clean Targets

`make clean` rebuilds all libraries from scratch:

```makefile
clean:
	rm -rf $(BUILD_DIR) $(TARGET)
	$(MAKE) -C $(CORE_LIB_DIR) clean
	$(MAKE) -C $(FUNC_LIB_DIR) clean
	$(MAKE) -C $(SE_LIB_DIR)/runtime cleanall  # removes lib + installed headers
```

## Include Paths

```makefile
CFLAGS += -I. \
          -I$(SE_LOCAL_DIR) \                    # local s-engine module headers
          -I$(CORE_LIB_DIR)/include \            # runtime_binary headers
          -I$(FUNC_LIB_DIR)/include \            # runtime_functions headers
          -I$(SE_LIB_DIR)/include/s_engine       # s-engine headers (installed by build)
```

## Source Discovery

```makefile
# All .c files in current dir and s_engine/ subdir
SRCS = $(wildcard *.c) $(wildcard $(SE_LOCAL_DIR)/*.c)
OBJS = $(patsubst %.c,$(BUILD_DIR)/%.o,$(notdir $(SRCS)))
```

Separate pattern rules for root and subdir sources:
```makefile
$(BUILD_DIR)/%.o: %.c $(LOCAL_HEADERS) | $(BUILD_DIR) libs
	$(CC) $(CFLAGS) $(DEPFLAGS) -c $< -o $@

$(BUILD_DIR)/%.o: $(SE_LOCAL_DIR)/%.c $(LOCAL_HEADERS) | $(BUILD_DIR) libs
	$(CC) $(CFLAGS) $(DEPFLAGS) -c $< -o $@
```

## Creating a New Makefile

Copy from `s_engine_test_2/Makefile` and adjust:
1. Remove `SE_LIB_DIR` / `SE_LIB` if no s-engine
2. Add/remove source directories
3. Adjust `heap_size` in `main.c` if memory errors occur
