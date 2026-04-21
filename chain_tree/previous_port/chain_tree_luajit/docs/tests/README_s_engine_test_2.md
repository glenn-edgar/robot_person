# S-Engine Advanced Integration Tests (Dict Runtime)

Advanced S-Expression engine integration tests. 3 tests covering bitmask-driven data flow, state machines with child columns, and command/event dispatch patterns.

## Location

```
dsl_tests/s_engine_test_2/
  s_engine_test_2.lua         -- DSL test definitions
  s_engine_test_2.json        -- Generated JSON IR
  test_se2_dict.lua           -- Dict runtime test harness
  se_user_functions.lua       -- SE-level user functions
```

The `chain_flow_dsl_tests` S-Engine module is compiled separately and loaded at runtime. It provides the `s_expression_test_2` tree used by these tests.

## Running Tests

```bash
cd chain_tree_luajit

# By name
luajit dsl_tests/s_engine_test_2/test_se2_dict.lua twenty_ninth_test

# By index
luajit dsl_tests/s_engine_test_2/test_se2_dict.lua 0
```

## Test Index

| Index | Name | Coverage |
|-------|------|----------|
| 0 | twenty_ninth_test | Bitmask-driven data flow with two se_engine composites |
| 1 | thirty_test | State machine with S-Engine-controlled child columns |
| 2 | thirty_one_test | Command/event dispatch with custom SE user functions |

## Test Details

### twenty_ninth_test

Uses `se_engine` composite nodes. Two S-Engine trees (df_a, df_b) each control ChainTree children via `CFL_ENABLE_CHILD` / `CFL_DISABLE_CHILDREN`. The SE trees use `CFL_SET_BITS` / `CFL_CLEAR_BITS` to manipulate the ChainTree bitmask, and children include `asm_event_logger` nodes that display `CFL_SECOND_EVENT` events matching data flow mask conditions.

DSL pattern:

```lua
local eng = ct:se_engine("chain_flow_dsl_tests", "s_expression_test_2",
                         "se_tree_a_ptr", {})
    ct:asm_log_message("s expression column df_a is active")
    ct:asm_event_logger("displaying data flow mask events", {"CFL_SECOND_EVENT"})
    ct:asm_halt()
ct:end_se_engine(eng)
```

### thirty_test

S-Engine drives a state machine pattern where each state is a ChainTree child column. The SE tree transitions between states by enabling/disabling children.

### thirty_one_test

Tests custom SE user functions for command dispatch. Uses `TEST_31_SET_MOTOR`, `TEST_31_SET_STATE` oneshots and `TEST_32_*` main/oneshot functions for sensor processing, LED control, background tasks, and internal event generation.

## SE User Functions

Defined in `se_user_functions.lua`:

### TEST_31 functions (motor/state control)

| Function | Type | Behavior |
|----------|------|----------|
| `TEST_31_SET_MOTOR` | oneshot | Reads motor_id and speed from params, prints |
| `TEST_31_SET_STATE` | oneshot | Writes value to instance field via `se.field_set` |

### TEST_32 functions (I/O and events)

| Function | Type | Behavior |
|----------|------|----------|
| `TEST_32_ENABLE_BUZZER` | oneshot | Prints buzzer enabled |
| `TEST_32_DISABLE_ALL_OUTPUTS` | oneshot | Prints all outputs disabled |
| `TEST_32_TOGGLE_LED` | oneshot | Reads LED ID from param, prints toggle |
| `TEST_32_SET_LED` | oneshot | Reads LED ID and state from params |
| `TEST_32_SAVE_STATE` | oneshot | Prints state saved |
| `TEST_32_NOTIFY_SYSTEM` | oneshot | Reads hash param, prints notification |
| `TEST_32_PROCESS_SCHEDULED_TASKS` | main | On EVT_TIMER: prints processing |
| `TEST_32_RUN_BACKGROUND_TASKS` | main | On CFL_SECOND_EVENT: prints running |
| `TEST_32_CHECK_THRESHOLD` | main | On EVT_SENSOR: compares reading to threshold param |
| `TEST_32_GENERATE_INTERNAL_EVENTS` | main | Counts ticks, pushes EVT_TIMER/EVT_BUTTON/EVT_SENSOR/EVT_ALARM/EVT_SHUTDOWN at intervals |

### Event constants

```lua
EVT_TIMER    = 0xEE01
EVT_BUTTON   = 0xEE02
EVT_SENSOR   = 0xEE03
EVT_ALARM    = 0xEE04
EVT_SHUTDOWN = 0xEE05
```

## Test Harness Structure

`test_se2_dict.lua` follows the same pattern as other dict test harnesses but additionally:

1. Requires `ct_se_bridge` and `se_runtime`
2. Creates an SE registry on the handle
3. Registers the `chain_flow_dsl_tests` module with `se_user_functions` as the user function table
4. The module data is loaded from the compiled S-Engine module (separate compilation step)
