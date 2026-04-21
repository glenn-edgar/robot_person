# S-Engine Bridge

`ct_se_bridge.lua` connects the S-Expression engine to the ChainTree dict runtime. It provides a module registry, CFL-specific S-Engine built-in functions, ChainTree node functions for managing S-Engine lifecycle, and result code mapping.

## Module Registry

The registry manages S-Engine module loading and lookup.

```lua
local se_bridge = require("ct_se_bridge")

-- Create registry (attaches to handle.se_registry)
local reg = se_bridge.create_registry(handle)

-- Pre-register a module definition
se_bridge.register_def(reg, "module_name", module_data_or_loader, user_fns)

-- Load module (creates se_runtime module, registers all function layers)
local mod = se_bridge.load_module(reg, "module_name")

-- Lookup / unload
local mod = se_bridge.find_module(reg, "module_name")
se_bridge.unload_module(reg, "module_name")
```

`register_def` accepts either a `module_data` table or a loader function that returns one. The `user_fns` table is merged into the S-Engine function dispatch after all builtin layers.

`load_module` merges these function layers in order:
1. `se_builtins_flow_control`
2. `se_builtins_dispatch`
3. `se_builtins_pred`
4. `se_builtins_oneshot`
5. `se_builtins_return_codes`
6. `se_builtins_delays`
7. `se_builtins_verify`
8. `se_builtins_stack`
9. `se_builtins_spawn`
10. `se_builtins_quads`
11. `se_builtins_dict`
12. CFL bridge builtins (`make_cfl_se_builtins`)
13. User functions (if provided)

## CFL S-Engine Builtins

Created by `make_cfl_se_builtins(handle)`. These S-Engine functions bridge back into the ChainTree runtime:

### Logging

| Function | Behavior |
|----------|----------|
| `CFL_LOG` | Prints `timestamp ct_node se_node msg` using handle.timestamp |

### Child control

| Function | Behavior |
|----------|----------|
| `CFL_ENABLE_CHILDREN` | Enables all children of the ChainTree node (`inst.ct_node_id`) |
| `CFL_DISABLE_CHILDREN` | Disables all children |
| `CFL_ENABLE_CHILD` | Enables child at 0-based index (param 1) |
| `CFL_DISABLE_CHILD` | Terminates child subtree at 0-based index (param 1) |

### Events

| Function | Behavior |
|----------|----------|
| `CFL_INTERNAL_EVENT` | Pushes event to ChainTree event queue: `{node_id, event_id=param1, event_data=param2}`. Skips SE init/terminate events |
| `CFL_EXCEPTION` | Raises a Lua error |

### Bitmask

| Function | Behavior |
|----------|----------|
| `CFL_SET_BITS` | Sets bits in `handle.bitmask` (all params as bit indices) |
| `CFL_CLEAR_BITS` | Clears bits in `handle.bitmask` |
| `CFL_READ_BIT` | Predicate: returns true if bit at param 1 is set |

### Composite bitmask predicates

| Function | Behavior |
|----------|----------|
| `CFL_S_BIT_OR` | True if any param bit is set |
| `CFL_S_BIT_AND` | True if all param bits are set |
| `CFL_S_BIT_NOR` | True if no param bit is set |
| `CFL_S_BIT_NAND` | True if not all param bits are set |
| `CFL_S_BIT_XOR` | True if odd number of param bits are set |

These support nested child predicates (`p_call` / `p_call_composite`) as well as direct parameter bit indices.

### Wait

| Function | Behavior |
|----------|----------|
| `CFL_WAIT_CHILD_DISABLED` | Main function: halts until ChainTree child at param 1 index is disabled, then returns SE_DISABLE |

### Stubs

`CFL_JSON_READ_*`, `CFL_COPY_CONST`, `CFL_COPY_CONST_FULL` are registered as no-ops.

## Result Code Mapping

`se_to_cfl(se_result)` maps S-Engine return codes to ChainTree return codes:

| S-Engine Result | ChainTree Result |
|----------------|-----------------|
| `SE_CONTINUE`, `SE_FUNCTION_CONTINUE`, `SE_PIPELINE_CONTINUE` | `CFL_HALT` |
| `SE_HALT`, `SE_FUNCTION_HALT`, `SE_PIPELINE_HALT` | `CFL_HALT` |
| `SE_DISABLE`, `SE_FUNCTION_DISABLE`, `SE_PIPELINE_DISABLE` | `CFL_DISABLE` |
| `SE_TERMINATE`, `SE_FUNCTION_TERMINATE`, `SE_PIPELINE_TERMINATE` | `CFL_TERMINATE` |
| `SE_RESET`, `SE_FUNCTION_RESET`, `SE_PIPELINE_RESET` | `CFL_RESET` |
| `SE_SKIP_CONTINUE`, `SE_FUNCTION_SKIP_CONTINUE`, `SE_PIPELINE_SKIP_CONTINUE` | `CFL_SKIP_CONTINUE` |

Note: SE_CONTINUE maps to CFL_HALT (SE still running = CFL hold position).

## tick_se_instance Helper

`tick_se_instance(handle, inst, cfl_event_id)` ticks an S-Engine instance:

1. Maps CFL event ID to SE event ID. `CFL_TIMER_EVENT` (4) passes through directly as `SE_EVENT_TICK` (also 4). `CFL_INIT_EVENT` and `CFL_TERMINATE_EVENT` map to SE equivalents.
2. Calls `se.tick_once(inst, se_event_id, nil)`.
3. Drains the SE event queue: pops events, ticks again for each.
4. On SE_RESET: resets all SE node flags to ACTIVE.
5. Returns `se_to_cfl(result)`.

## ChainTree Node Functions

Dict-style node functions registered as `M.one_shot`, `M.main`, `M.boolean`:

### CFL_SE_MODULE_LOAD

- **Init**: Loads module from registry, stores in node state
- **Main**: Returns `CFL_CONTINUE` (stays alive)
- **Term**: Clears node state

### CFL_SE_TREE_LOAD

- **Init**: Looks up module, creates tree instance via `se.new_instance`, stores instance in `handle.blackboard[bb_field]`. Sets `inst.ct_node_id` for bridge callbacks.
- **Main**: Returns `CFL_CONTINUE`
- **Term**: Clears blackboard field and node state

### CFL_SE_TICK

- **Init**: Retrieves tree instance from blackboard, resets it
- **Main**: Calls `tick_se_instance()` each tick, returns mapped CFL result
- **Term**: Clears node state

### CFL_SE_ENGINE (composite)

Self-contained lifecycle wrapping module load + tree load + tick:

- **Init**: Creates registry (if needed), loads module, creates tree instance, stores in blackboard. Disables all children (SE controls them).
- **Main**: Ticks SE instance. Returns mapped result.
- **Term**: Terminates all children, clears blackboard, unloads module.
