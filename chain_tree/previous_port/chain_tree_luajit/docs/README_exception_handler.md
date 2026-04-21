# Exception Handler Patterns

ChainTree provides structured exception handling with try/catch/recovery/finalize phases and optional heartbeat monitoring.

## Basic Exception Handler

```lua
ct:define_exception_handler("handler_name")

    ct:define_main_column("main_block")
        -- Normal execution
        ct:asm_log_message("main running")
        ct:asm_wait_time(5.0)
        ct:asm_log_message("main complete")
    ct:end_main_column()

    ct:define_recovery_column("recovery_block")
        -- Recovery after exception
        ct:asm_log_message("recovering")
        ct:asm_wait_time(1.0)
    ct:end_recovery_column()

    ct:define_finalize_column("finalize_block")
        -- Always runs (like finally)
        ct:asm_log_message("finalizing")
    ct:end_finalize_column()

    ct:define_exception_catch("catch_block", "MY_EXCEPTION")
        -- Catch specific exception
        ct:asm_log_message("caught MY_EXCEPTION")
    ct:end_exception_catch()

ct:end_exception_handler()
```

## Execution Flow

```
Normal:     main → finalize → done
Exception:  main → catch → recovery → finalize → done
```

1. **Main** executes until complete or exception raised
2. **Catch** fires if exception matches (by exception ID)
3. **Recovery** runs after catch to restore state
4. **Finalize** always runs (cleanup, resource release)

## Raising Exceptions

From within the main block or any child:

```lua
ct:asm_raise_exception("MY_EXCEPTION", { reason = "sensor_timeout" })
```

From C user functions:
```c
// Set exception step (identifies which phase raised it)
cfl_set_exception_step_one_shot_fn(handle, node_index);

// Raise the exception
cfl_raise_exception_one_shot_fn(handle, node_index);
```

## Exception Catch-All

Catches any exception not matched by specific catch blocks:

```lua
ct:define_exception_catch_all("catch_all")
    ct:asm_log_message("unexpected exception caught")
ct:end_exception_catch_all()
```

## Heartbeat Monitoring

Adds a watchdog that raises an exception if the main block doesn't send heartbeat events within a timeout:

```lua
ct:define_exception_handler("monitored_handler")

    ct:define_main_column("main_block")
        ct:asm_turn_heartbeat_on(5.0)     -- 5 second timeout
        ct:asm_log_message("working...")

        -- Must call periodically to prevent timeout:
        ct:asm_heartbeat_event()

        ct:asm_wait_time(2.0)
        ct:asm_heartbeat_event()           -- reset watchdog

        ct:asm_turn_heartbeat_off()
        ct:asm_log_message("done")
    ct:end_main_column()

    ct:define_recovery_column("recovery")
        ct:asm_log_message("heartbeat timeout — recovering")
    ct:end_recovery_column()

    ct:define_finalize_column("finalize")
        ct:asm_log_message("cleanup")
    ct:end_finalize_column()

ct:end_exception_handler()
```

If no `heartbeat_event()` arrives within the timeout, the handler automatically raises an exception and transitions to recovery.

## Nested Exception Handlers

Exception handlers can be nested inside columns:

```lua
local col = ct:define_column("outer", nil, nil, nil, nil, nil, true)

    ct:define_exception_handler("inner_handler")
        ct:define_main_column("risky_operation")
            ct:asm_log_message("attempting risky operation")
            -- if this raises, inner handler catches it
        ct:end_main_column()
        ct:define_recovery_column("inner_recovery")
            ct:asm_log_message("inner recovery")
        ct:end_recovery_column()
    ct:end_exception_handler()

    ct:asm_log_message("after inner handler")
    ct:asm_terminate_system()

ct:end_column(col)
```

## Test Reference

- **Test 13 (seventeenth_test)**: Basic exception handler with try/catch/recovery/finalize
- **Test 14 (eighteenth_test)**: Exception handler with heartbeat monitoring

See [README_incremental_binary.md](README_incremental_binary.md) for the full test list.
