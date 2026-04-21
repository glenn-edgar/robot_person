# ChainTree Runtime API

## Runtime Lifecycle

```c
// 1. Load binary image
cfl_image_loader_t img;
cfl_embedded_load(image_data, image_size, &img);  // from C array
cfl_file_load("path.ctb", &img);                  // from file

// 2. Register functions
cfl_register_all_functions(&img);                  // built-in + CFL bridge
cfl_image_register_boolean(&img, "name", fn);      // user boolean
cfl_image_register_main(&img, "name", fn);         // user main
cfl_image_register_one_shot(&img, "name", fn);     // user oneshot
int missing = cfl_image_validate(&img);            // check all resolved

// 3. Get handle
const cfl_chaintree_handle_t *handle = cfl_image_get_handle(&img);

// 4. Create runtime
cfl_runtime_create_params_t *params = cfl_runtime_create_params_create();
params->perm = &perm;
params->perm_buffer = perm_buffer;
params->perm_buffer_size = sizeof(perm_buffer);
params->heap_size = 8192;                          // adjust per test
params->max_allocator_count = cfl_calculate_arrena_number(handle);
params->total_node_count = handle->node_count;
params->allocator_0_size = 128;
params->event_queue_high_priority_size = 8;
params->event_queue_low_priority_size = 64;
params->delta_time = 0.1;

cfl_runtime_handle_t *rt = cfl_runtime_create(&perm, params, handle);
cfl_runtime_create_params_destroy(params);

// 5. (Optional) S-Engine registry
cfl_se_module_registry_t *reg = cfl_se_registry_create(rt);
cfl_set_app_extensions(rt, reg);
cfl_se_registry_register_def(reg, "module", bin, size);

// 6. Reset and run
cfl_runtime_reset(rt);
cfl_add_test_by_index(rt, 0);
bool result = cfl_runtime_run(rt);

// 7. Cleanup
cfl_se_registry_destroy(reg);
cfl_set_app_extensions(rt, NULL);
cfl_image_free(&img);
```

## Runtime Parameters

| Parameter | Description | Typical Value |
|-----------|-------------|---------------|
| `perm_buffer_size` | Permanent allocator size | `0xFFFF` (64KB) |
| `heap_size` | General heap size | 8192–32768 |
| `max_allocator_count` | Per-node arenas | `cfl_calculate_arrena_number()` |
| `total_node_count` | From handle | `handle->node_count` |
| `allocator_0_size` | Default arena size | 50–128 bytes |
| `event_queue_high_priority_size` | High-priority event slots | 8 |
| `event_queue_low_priority_size` | Low-priority event slots | 64 |
| `delta_time` | Seconds per tick | 0.1 |

### Sizing Guidelines

- **heap_size**: Base ~2KB for runtime structures. Add ~500 bytes per s-engine module loaded, ~200 bytes per tree instance. For test_32 with 7 sequential trees: 32KB.
- **allocator_0_size**: Largest per-node state struct. Most nodes need 0–50 bytes. S-engine bridge nodes need ~128 bytes.
- **event_queue**: High-priority for system events, low-priority for user events. Size = max concurrent queued events.

## Runtime Handle

The `cfl_runtime_handle_t` provides access to all runtime state:

```c
cfl_runtime_handle_t *rt;
rt->flash_handle      // const node/function data (ROM)
rt->heap              // general heap
rt->arena_system      // per-node arenas
rt->timer_handle      // wall-clock timer
rt->event_queue       // event queue
rt->blackboard        // mutable shared blackboard
rt->blackboard_size   // blackboard size in bytes
rt->bb_desc           // blackboard field descriptors
rt->flags             // per-node flags array
rt->bitmask           // 64-bit event bitmask
rt->event_data_ptr    // current event being processed
```

## Key Functions

### Heap
```c
void *cfl_heap_malloc_pointer(cfl_heap_t *heap, uint16_t size);
void cfl_heap_free_pointer(cfl_heap_t *heap, void *ptr);
int cfl_heap_used_bytes(cfl_heap_t *heap);
int cfl_heap_free_bytes(cfl_heap_t *heap);
```

### Arena
```c
bool cfl_allocate_state(cfl_runtime_handle_t *rt, uint16_t node_index);
void *cfl_smart_arena_alloc(cfl_runtime_handle_t *rt, uint16_t node, uint16_t size);
void *cfl_heap_arena_get_node_ptr(cfl_heap_arena_system_t *sys, uint16_t node);
```

### Node Control
```c
void cfl_enable_node(cfl_runtime_handle_t *rt, unsigned node_index);
void cfl_enable_all_nodes(cfl_runtime_handle_t *rt, uint16_t parent);
void cfl_enable_all_children(cfl_runtime_handle_t *rt, uint16_t parent);
void cfl_disable_all_children(cfl_runtime_handle_t *rt, uint16_t parent);
void cfl_enable_child(cfl_runtime_handle_t *rt, uint16_t parent, uint16_t child_index);
void cfl_disable_child(cfl_runtime_handle_t *rt, uint16_t parent, uint16_t child_index);
void cfl_terminate_node_tree(cfl_runtime_handle_t *rt, unsigned node_id);
bool cfl_engine_node_is_enabled(cfl_runtime_handle_t *rt, unsigned node_index);
bool cfl_child_is_enabled(cfl_runtime_handle_t *rt, uint16_t parent, uint16_t child_index);
```

### Events
```c
bool cfl_send_integer_event(CFL_EVENT_QUEUE_T *queue, unsigned priority,
                            unsigned node_id, unsigned event_id, cfl_int_t value);
```

### Timer
```c
double cfl_timer_get_timestamp(cfl_timer_handle_t *timer);
```

### JSON Node Data
```c
json_decoder_init_from_runtime(rt, node_index);
json_extract_string_runtime(rt, "node_dict.message", &str);
json_extract_int32_runtime(rt, "node_dict.value", &val);
```

### App Extensions
```c
void cfl_set_app_extensions(cfl_runtime_handle_t *rt, void *ext);
void *cfl_get_app_extensions(cfl_runtime_handle_t *rt);
```
