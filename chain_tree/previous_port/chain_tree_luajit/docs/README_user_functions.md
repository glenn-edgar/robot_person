# User Function Interfaces

Both ChainTree and S-Expression engines support user-defined C functions registered at startup. This document covers the function signatures, registration patterns, and naming conventions for both engines.

## ChainTree User Functions

ChainTree has three function types, each with a fixed C signature.

### Main Functions
Called every tick while the node is enabled. Returns a CFL result code.

```c
unsigned my_main_fn(
    void *handle,                    // cfl_runtime_handle_t*
    unsigned bool_function_index,    // index of associated boolean
    unsigned node_index,             // this node's index
    unsigned event_type,             // event type flags
    unsigned event_id,               // event identifier
    void *event_data                 // event payload (may be NULL)
);
```

Return codes: `CFL_CONTINUE`, `CFL_HALT`, `CFL_DISABLE`, `CFL_RESET`, `CFL_TERMINATE`, `CFL_SKIP_CONTINUE`, `CFL_TERMINATE_SYSTEM`

### One-Shot Functions
Called once on node init or term. No return value.

```c
void my_oneshot_fn(
    void *handle,          // cfl_runtime_handle_t*
    uint16_t node_index    // this node's index
);
```

### Boolean Functions
Called by composite nodes (columns, state machines) to make decisions.

```c
bool my_boolean_fn(
    void *handle,              // cfl_runtime_handle_t*
    unsigned node_index,       // parent node's index
    unsigned event_type,       // event type flags
    unsigned event_id,         // event identifier
    void *event_data           // event payload
);
```

### Registration

Functions are registered by their **typed name** — the DSL name lowercased with a type suffix:

| DSL Name | Registration Name | Type |
|----------|------------------|------|
| `MY_CUSTOM_MAIN` | `my_custom_main_main` | main |
| `MY_INIT_FN` | `my_init_fn_one_shot` | oneshot |
| `MY_CHECK` | `my_check_boolean` | boolean |

```c
// In main.c:
cfl_register_all_functions(&img);  // register all built-in functions

// Register user functions
cfl_image_register_main(&img, "my_custom_main_main", my_custom_main_fn);
cfl_image_register_one_shot(&img, "my_init_fn_one_shot", my_init_fn);
cfl_image_register_boolean(&img, "my_check_boolean", my_check_fn);

// Validate — fails if any DSL-referenced function is missing
int missing = cfl_image_validate(&img);
```

### Accessing Runtime State

```c
void my_oneshot(void *handle, uint16_t node_index) {
    cfl_runtime_handle_t *rt = (cfl_runtime_handle_t *)handle;

    // Access blackboard
    int32_t *mode = CFL_BB_FIELD(rt, OFFSET_MODE, int32_t);

    // Access node data from JSON
    json_decoder_init_from_runtime(rt, node_index);
    const char *msg;
    json_extract_string_runtime(rt, "node_dict.message", &msg);

    // Access heap arena
    void *data = cfl_heap_arena_get_node_ptr(rt->arena_system, node_index);

    // Access timer
    double now = cfl_timer_get_timestamp(rt->timer_handle);

    // Send event
    cfl_send_integer_event(rt->event_queue, CFL_EVENT_PRIORITY_LOW,
                           node_index, 0xEE01, 0);
}
```

---

## S-Expression Engine User Functions

The S-Expression engine has three function types with a unified parameter-passing signature.

### Oneshot Functions
Called during INIT, TERMINATE, and each TICK. Check `event_type` to filter.

```c
void my_oneshot(
    s_expr_tree_instance_t *inst,    // tree instance
    const s_expr_param_t *params,    // parameter array
    uint16_t param_count,            // number of parameters
    s_expr_event_type_t event_type,  // SE_EVENT_INIT, SE_EVENT_TICK, SE_EVENT_TERMINATE
    uint16_t event_id,               // event identifier (4 = timer tick)
    void *event_data                 // event payload
);
```

### Main Functions
Same signature but returns a result code.

```c
s_expr_result_t my_main(
    s_expr_tree_instance_t *inst,
    const s_expr_param_t *params,
    uint16_t param_count,
    s_expr_event_type_t event_type,
    uint16_t event_id,
    void *event_data
);
```

### Predicate Functions
Same signature but returns bool.

```c
bool my_pred(
    s_expr_tree_instance_t *inst,
    const s_expr_param_t *params,
    uint16_t param_count,
    s_expr_event_type_t event_type,
    uint16_t event_id,
    void *event_data
);
```

### Reading Parameters

Parameters are typed via `params[i].type & S_EXPR_OPCODE_MASK`:

```c
// Check type
uint8_t op = s_expr_param_opcode(&params[0]);

// Read values
int32_t  ival = (int32_t)s_expr_param_int(&params[i]);
uint32_t uval = (uint32_t)s_expr_param_uint(&params[i]);
float    fval = s_expr_param_float(&params[i]);
uint32_t hash = (uint32_t)s_expr_param_str_hash(&params[i]);

// Read string (from string table)
const char *str = s_expr_get_string(inst, &params[i]);

// Read field reference (pointer into blackboard)
int32_t *field = S_EXPR_GET_FIELD(inst, &params[i], int32_t);
```

Parameter types: `S_EXPR_PARAM_INT`, `S_EXPR_PARAM_UINT`, `S_EXPR_PARAM_FLOAT`, `S_EXPR_PARAM_FIELD`, `S_EXPR_PARAM_STR_IDX`, `S_EXPR_PARAM_STR_HASH`, `S_EXPR_PARAM_CONST_REF`

### Accessing Tree State

```c
void *bb = s_expr_tree_get_blackboard(inst);           // blackboard pointer
uint16_t bb_size = s_expr_tree_get_blackboard_size(inst);
void *ctx = s_expr_tree_get_user_ctx(inst);            // user context (cfl_runtime_handle_t*)
uint32_t node_id = inst->ct_node_id;                   // ChainTree node index

// Lookup field by name (runtime, slower)
void *field = s_expr_blackboard_get_field_by_string(inst, "field_name");

// Per-instance storage
s_expr_set_u64(inst, value);          // store uint64
uint64_t v = s_expr_get_u64(inst);    // retrieve uint64
```

### Registration

S-Engine functions are registered via hash tables. The DSL compiler generates hashes from function names.

**Standalone (no ChainTree):**
```c
// In _user_registration.c (generated, or manual):
static s_expr_fn_entry_t oneshot_entries[] = {
    { 0xCA568877, (void*)my_oneshot },
};
static const s_expr_fn_table_t oneshot_table = {
    .entries = oneshot_entries, .count = 1
};

void my_module_register_all(s_expr_module_t *module) {
    s_expr_module_register_oneshot(module, &oneshot_table);
}
```

**Inside ChainTree (via se_engine):**
```c
// In main.c — register module with user function callback:
static void user_register(s_expr_module_t *mod, void *ctx) {
    (void)ctx;
    my_module_register_all(mod);
}

cfl_se_registry_register_def_with_user(reg, "my_module",
    my_module_bin_32, MY_MODULE_BIN_32_SIZE,
    user_register, NULL);
```

### CFL Bridge Functions

When s-engine trees run inside ChainTree, they can access ChainTree features via pre-registered bridge functions. These are **not** user functions — they're registered automatically via `cfl_se_get_oneshot_table()`, `cfl_se_get_pred_table()`, and `cfl_se_get_main_table()`.

| Bridge Function | Type | Purpose |
|----------------|------|---------|
| `CFL_ENABLE_CHILDREN` | oneshot | Enable all ChainTree children |
| `CFL_DISABLE_CHILDREN` | oneshot | Disable all ChainTree children |
| `CFL_ENABLE_CHILD` | oneshot | Enable child by index |
| `CFL_DISABLE_CHILD` | oneshot | Disable child by index |
| `CFL_INTERNAL_EVENT` | oneshot | Post event to ChainTree queue |
| `CFL_LOG` | oneshot | Log with timestamp |
| `CFL_JSON_READ_*` | oneshot | Read JSON node data into blackboard |
| `CFL_COPY_CONST` | oneshot | Copy constant to field |
| `CFL_COPY_CONST_FULL` | oneshot | Copy constant to entire blackboard |
| `CFL_SET_BITS` / `CFL_CLEAR_BITS` | oneshot | Set/clear bitmask bits |
| `CFL_S_BIT_OR/AND/NOR/NAND/XOR` | predicate | Bitmask boolean predicates |
| `CFL_READ_BIT` | predicate | Read single bitmask bit |
| `CFL_WAIT_CHILD_DISABLED` | main | Wait until ChainTree child disables |

**Important:** The s-engine compiler treats CFL bridge functions as "user" functions in the generated `_user_registration.c`. When using ChainTree integration, you must manually override this file to exclude bridge functions (they're already in the bridge tables).

For complete user function documentation, see [s_expression/dsl_tests/docs/README_user_defined_functions.md](s_expression/README_user_defined_functions.md).
