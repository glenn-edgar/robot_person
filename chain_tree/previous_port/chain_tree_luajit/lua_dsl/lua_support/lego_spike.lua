--============================================================================
-- ct_lego_spike.lua
-- Lego SPIKE Prime / Pybricks leaf functions for ChainTree DSL
--
-- Mixin module for ChainTreeMaster.  Provides asm_* methods for motor
-- control, sensor reading, drivebase navigation, and IMU access.
--
-- All functions produce ChainTree column-link nodes whose C callbacks
-- communicate with the Pybricks MicroPython runtime through the shared
-- blackboard (cfl_blackboard).
--
-- Usage:
--   local ct = ChainTreeMaster.new("output.json")
--   ct:start_test("my_robot")
--   local col = ct:define_column("drive_col", nil, nil, nil, nil, nil, true)
--       ct:asm_spike_motor_run_angle(SPIKE_PORT_A, 500, 360, SPIKE_STOP_HOLD)
--       ct:asm_spike_drivebase_straight(500, SPIKE_STOP_HOLD)
--       ct:asm_terminate()
--   ct:end_column(col)
--   ct:end_test()
--============================================================================

local ColumnFlow = require("lua_support.column_flow")

local LegoSpike = setmetatable({}, { __index = ColumnFlow })
LegoSpike.__index = LegoSpike

function LegoSpike.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, LegoSpike)
end

-- ============================================================================
-- Constants
-- ============================================================================

SPIKE_PORT_A = 0
SPIKE_PORT_B = 1
SPIKE_PORT_C = 2
SPIKE_PORT_D = 3
SPIKE_PORT_E = 4
SPIKE_PORT_F = 5

SPIKE_STOP_COAST = 0
SPIKE_STOP_BRAKE = 1
SPIKE_STOP_HOLD  = 2
SPIKE_STOP_NONE  = 3

-- ============================================================================
-- BLACKBOARD DEFINITION
-- Call once from your test definition to set up the standard SPIKE blackboard.
--
-- ct:define_spike_blackboard()
-- ============================================================================

function LegoSpike:define_spike_blackboard()
    local bb = self.ctb

    bb:define_blackboard("spike_hw")
        -- Motor A
        bb:bb_field("motor_a_angle",   "int32",  0)
        bb:bb_field("motor_a_speed",   "int32",  0)
        bb:bb_field("motor_a_load",    "int32",  0)
        bb:bb_field("motor_a_stalled", "int32",  0)
        bb:bb_field("motor_a_done",    "int32",  1)
        -- Motor B
        bb:bb_field("motor_b_angle",   "int32",  0)
        bb:bb_field("motor_b_speed",   "int32",  0)
        bb:bb_field("motor_b_load",    "int32",  0)
        bb:bb_field("motor_b_stalled", "int32",  0)
        bb:bb_field("motor_b_done",    "int32",  1)
        -- Motor C
        bb:bb_field("motor_c_angle",   "int32",  0)
        bb:bb_field("motor_c_speed",   "int32",  0)
        bb:bb_field("motor_c_load",    "int32",  0)
        bb:bb_field("motor_c_stalled", "int32",  0)
        bb:bb_field("motor_c_done",    "int32",  1)
        -- Motor D
        bb:bb_field("motor_d_angle",   "int32",  0)
        bb:bb_field("motor_d_speed",   "int32",  0)
        bb:bb_field("motor_d_load",    "int32",  0)
        bb:bb_field("motor_d_stalled", "int32",  0)
        bb:bb_field("motor_d_done",    "int32",  1)
        -- Motor E
        bb:bb_field("motor_e_angle",   "int32",  0)
        bb:bb_field("motor_e_speed",   "int32",  0)
        bb:bb_field("motor_e_load",    "int32",  0)
        bb:bb_field("motor_e_stalled", "int32",  0)
        bb:bb_field("motor_e_done",    "int32",  1)
        -- Motor F
        bb:bb_field("motor_f_angle",   "int32",  0)
        bb:bb_field("motor_f_speed",   "int32",  0)
        bb:bb_field("motor_f_load",    "int32",  0)
        bb:bb_field("motor_f_stalled", "int32",  0)
        bb:bb_field("motor_f_done",    "int32",  1)
        -- Color sensor
        bb:bb_field("color_hue",        "int32",  0)
        bb:bb_field("color_sat",        "int32",  0)
        bb:bb_field("color_val",        "int32",  0)
        bb:bb_field("color_id",         "int32",  0)
        bb:bb_field("color_reflection", "int32",  0)
        -- Ultrasonic sensor
        bb:bb_field("ultrasonic_distance", "int32", 0)
        -- Force sensor
        bb:bb_field("force_value",   "float",  0.0)
        bb:bb_field("force_pressed", "int32",  0)
        bb:bb_field("force_touched", "int32",  0)
        -- IMU
        bb:bb_field("imu_heading", "float",  0.0)
        bb:bb_field("imu_pitch",   "float",  0.0)
        bb:bb_field("imu_roll",    "float",  0.0)
        bb:bb_field("imu_ready",   "int32",  0)
        -- DriveBase
        bb:bb_field("drivebase_distance", "int32",  0)
        bb:bb_field("drivebase_angle",    "int32",  0)
        bb:bb_field("drivebase_speed",    "int32",  0)
        bb:bb_field("drivebase_done",     "int32",  1)
        bb:bb_field("drivebase_stalled",  "int32",  0)
        -- Hub / safety monitoring
        bb:bb_field("battery_voltage",    "float",  8.0)
        bb:bb_field("comm_last_tick",     "int32",  0)
        -- IMU accelerometer (mm/s^2, updated by sensor poll)
        bb:bb_field("imu_accel_x",        "float",  0.0)
        bb:bb_field("imu_accel_y",        "float",  0.0)
        bb:bb_field("imu_accel_z",        "float",  0.0)
        bb:bb_field("bump_detected",      "int32",  0)
        -- Per-port sensor connection flags
        bb:bb_field("sensor_a_connected", "int32",  1)
        bb:bb_field("sensor_b_connected", "int32",  1)
        bb:bb_field("sensor_c_connected", "int32",  1)
        bb:bb_field("sensor_d_connected", "int32",  1)
        bb:bb_field("sensor_e_connected", "int32",  1)
        bb:bb_field("sensor_f_connected", "int32",  1)
    bb:end_blackboard()
end

-- ============================================================================
-- MOTOR ONE-SHOT OPERATIONS
-- These produce column-link nodes with CFL_DISABLE main function
-- (execute once then disable).  Parameters go in column_data.
-- ============================================================================

-- Start motor at constant speed (deg/s).  Non-blocking.
function LegoSpike:asm_spike_motor_run(port, speed)
    self:asm_one_shot_handler("SPIKE_MOTOR_RUN",
        { port = port, speed = speed })
end

-- Coast stop motor
function LegoSpike:asm_spike_motor_stop(port)
    self:asm_one_shot_handler("SPIKE_MOTOR_STOP",
        { port = port })
end

-- Passive brake
function LegoSpike:asm_spike_motor_brake(port)
    self:asm_one_shot_handler("SPIKE_MOTOR_BRAKE",
        { port = port })
end

-- Active PID hold at current position
function LegoSpike:asm_spike_motor_hold(port)
    self:asm_one_shot_handler("SPIKE_MOTOR_HOLD",
        { port = port })
end

-- Raw duty cycle (-100 to 100%)
function LegoSpike:asm_spike_motor_dc(port, duty)
    self:asm_one_shot_handler("SPIKE_MOTOR_DC",
        { port = port, duty = duty })
end

-- Reset encoder angle
function LegoSpike:asm_spike_motor_reset_angle(port, angle)
    angle = angle or 0
    self:asm_one_shot_handler("SPIKE_MOTOR_RESET_ANGLE",
        { port = port, angle = angle })
end

-- ============================================================================
-- MOTOR MAIN FUNCTIONS (blocking — HALT until done)
-- These produce column-link nodes with a main function that returns
-- CFL_CONTINUE (HALT) each tick until the motion completes, then CFL_DISABLE.
-- ============================================================================

-- Run motor a relative angle (deg)
function LegoSpike:asm_spike_motor_run_angle(port, speed, angle, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    self:define_column_link(
        "SPIKE_MOTOR_RUN_ANGLE",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { port = port, speed = speed, angle = angle, stop_type = stop_type },
        "SPIKE_MOTOR"
    )
end

-- Run motor to absolute target angle (deg)
function LegoSpike:asm_spike_motor_run_target(port, speed, target, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    self:define_column_link(
        "SPIKE_MOTOR_RUN_TARGET",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { port = port, speed = speed, target = target, stop_type = stop_type },
        "SPIKE_MOTOR"
    )
end

-- Run motor for duration (ms)
function LegoSpike:asm_spike_motor_run_time(port, speed, time_ms, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    self:define_column_link(
        "SPIKE_MOTOR_RUN_TIME",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { port = port, speed = speed, time_ms = time_ms, stop_type = stop_type },
        "SPIKE_MOTOR"
    )
end

-- Run motor until stall detected.  Writes stall angle into blackboard.
function LegoSpike:asm_spike_motor_run_until_stalled(port, speed, duty_limit)
    duty_limit = duty_limit or 100
    self:define_column_link(
        "SPIKE_MOTOR_RUN_UNTIL_STALLED",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { port = port, speed = speed, duty_limit = duty_limit },
        "SPIKE_MOTOR"
    )
end

-- ============================================================================
-- SENSOR ONE-SHOT OPERATIONS
-- ============================================================================

-- Trigger full sensor poll cycle, update all blackboard fields
function LegoSpike:asm_spike_read_sensors()
    self:asm_one_shot_handler("SPIKE_READ_SENSORS", {})
end

-- Color sensor LEDs on (brightness 0-100)
function LegoSpike:asm_spike_color_lights_on(port, brightness)
    self:asm_one_shot_handler("SPIKE_COLOR_LIGHTS_ON",
        { port = port, brightness = brightness })
end

-- Color sensor LEDs off
function LegoSpike:asm_spike_color_lights_off(port)
    self:asm_one_shot_handler("SPIKE_COLOR_LIGHTS_OFF",
        { port = port })
end

-- Ultrasonic sensor LEDs on
function LegoSpike:asm_spike_ultrasonic_lights_on(port, brightness)
    self:asm_one_shot_handler("SPIKE_ULTRASONIC_LIGHTS_ON",
        { port = port, brightness = brightness })
end

-- Ultrasonic sensor LEDs off
function LegoSpike:asm_spike_ultrasonic_lights_off(port)
    self:asm_one_shot_handler("SPIKE_ULTRASONIC_LIGHTS_OFF",
        { port = port })
end

-- ============================================================================
-- IMU ONE-SHOT OPERATIONS
-- ============================================================================

-- Reset IMU heading reference
function LegoSpike:asm_spike_imu_reset_heading(angle)
    angle = angle or 0
    self:asm_one_shot_handler("SPIKE_IMU_RESET_HEADING",
        { angle = angle })
end

-- ============================================================================
-- MOTOR PID CONFIGURATION
-- ============================================================================

-- Configure motor PID gains (kp, ki, kd in uNm/deg units)
function LegoSpike:asm_spike_set_motor_pid(port, kp, ki, kd)
    self:asm_one_shot_handler("SPIKE_SET_MOTOR_PID",
        { port = port, kp = kp, ki = ki, kd = kd })
end

-- Configure motor control limits (speed deg/s, accel deg/s^2, torque mNm)
function LegoSpike:asm_spike_set_motor_limits(port, max_speed, acceleration, torque)
    self:asm_one_shot_handler("SPIKE_SET_MOTOR_LIMITS",
        { port = port, max_speed = max_speed, acceleration = acceleration, torque = torque })
end

-- ============================================================================
-- DRIVEBASE MAIN FUNCTIONS (blocking — HALT until done)
-- ============================================================================

-- Drive straight (distance_mm, positive = forward)
function LegoSpike:asm_spike_drivebase_straight(distance_mm, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    self:define_column_link(
        "SPIKE_DRIVEBASE_STRAIGHT",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { distance_mm = distance_mm, stop_type = stop_type },
        "SPIKE_DRIVE"
    )
end

-- Turn in place (angle_deg, positive = right)
function LegoSpike:asm_spike_drivebase_turn(angle_deg, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    self:define_column_link(
        "SPIKE_DRIVEBASE_TURN",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { angle_deg = angle_deg, stop_type = stop_type },
        "SPIKE_DRIVE"
    )
end

-- Drive arc (radius mm, angle deg)
function LegoSpike:asm_spike_drivebase_curve(radius, angle, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    self:define_column_link(
        "SPIKE_DRIVEBASE_CURVE",
        "CFL_NULL", "CFL_NULL", "CFL_NULL",
        { radius = radius, angle = angle, stop_type = stop_type },
        "SPIKE_DRIVE"
    )
end

-- ============================================================================
-- DRIVEBASE ONE-SHOT OPERATIONS
-- ============================================================================

-- Continuous drive (speed mm/s, turn_rate deg/s).  Non-blocking.
function LegoSpike:asm_spike_drivebase_drive(speed, turn_rate)
    self:asm_one_shot_handler("SPIKE_DRIVEBASE_DRIVE",
        { speed = speed, turn_rate = turn_rate })
end

-- Stop drivebase (coast)
function LegoSpike:asm_spike_drivebase_stop()
    self:asm_one_shot_handler("SPIKE_DRIVEBASE_STOP", {})
end

-- Brake drivebase
function LegoSpike:asm_spike_drivebase_brake()
    self:asm_one_shot_handler("SPIKE_DRIVEBASE_BRAKE", {})
end

-- Reset drivebase odometry (zero distance and angle)
function LegoSpike:asm_spike_drivebase_reset()
    self:asm_one_shot_handler("SPIKE_DRIVEBASE_RESET", {})
end

-- ============================================================================
-- BOOLEAN FUNCTIONS (for use as aux_function in column definitions)
-- These are boolean function names that can be passed to define_column.
-- ============================================================================

-- Boolean function names (registered as C callbacks)
SPIKE_BOOL_MOTOR_STALLED     = "SPIKE_MOTOR_STALLED_BOOL"
SPIKE_BOOL_MOTOR_DONE        = "SPIKE_MOTOR_DONE_BOOL"
SPIKE_BOOL_FORCE_PRESSED     = "SPIKE_FORCE_PRESSED_BOOL"
SPIKE_BOOL_FORCE_TOUCHED     = "SPIKE_FORCE_TOUCHED_BOOL"
SPIKE_BOOL_COLOR_MATCH       = "SPIKE_COLOR_MATCH_BOOL"
SPIKE_BOOL_DISTANCE_LT       = "SPIKE_DISTANCE_LT_BOOL"
SPIKE_BOOL_IMU_READY         = "SPIKE_IMU_READY_BOOL"
SPIKE_BOOL_DRIVEBASE_DONE    = "SPIKE_DRIVEBASE_DONE_BOOL"
SPIKE_BOOL_DRIVEBASE_STALLED = "SPIKE_DRIVEBASE_STALLED_BOOL"

-- Fault detection boolean functions (for exception_catch aux_function)
SPIKE_BOOL_BATTERY_LOW        = "SPIKE_BATTERY_LOW_BOOL"
SPIKE_BOOL_MOTOR_OVERCURRENT  = "SPIKE_MOTOR_OVERCURRENT_BOOL"
SPIKE_BOOL_TILT_EXCEEDED      = "SPIKE_TILT_EXCEEDED_BOOL"
SPIKE_BOOL_COMM_TIMEOUT       = "SPIKE_COMM_TIMEOUT_BOOL"
SPIKE_BOOL_SENSOR_DISCONNECTED = "SPIKE_SENSOR_DISCONNECTED_BOOL"
SPIKE_BOOL_BUMP_DETECTED      = "SPIKE_BUMP_DETECTED_BOOL"
SPIKE_BOOL_MOTOR_RUNAWAY      = "SPIKE_MOTOR_RUNAWAY_BOOL"

-- ============================================================================
-- COMPOSITE HELPERS
-- Higher-level patterns built from the leaf methods above
-- ============================================================================

-- Run motor angle and wait for completion in a single column sequence
function LegoSpike:asm_spike_do_motor_angle(port, speed, angle, stop_type)
    self:asm_spike_motor_run_angle(port, speed, angle, stop_type)
end

-- Drive straight and wait
function LegoSpike:asm_spike_do_straight(distance_mm, stop_type)
    self:asm_spike_drivebase_straight(distance_mm, stop_type)
end

-- Turn and wait
function LegoSpike:asm_spike_do_turn(angle_deg, stop_type)
    self:asm_spike_drivebase_turn(angle_deg, stop_type)
end

-- Find mechanical endpoint: run until stalled, reset angle to 0
function LegoSpike:asm_spike_find_endpoint(port, speed, duty_limit)
    self:asm_spike_motor_run_until_stalled(port, speed, duty_limit)
    self:asm_spike_motor_reset_angle(port, 0)
end

-- Square drive pattern (forward, turn 90, repeat 4 times)
function LegoSpike:asm_spike_drive_square(side_mm, speed_turn)
    speed_turn = speed_turn or 90
    for i = 1, 4 do
        self:asm_spike_drivebase_straight(side_mm, SPIKE_STOP_HOLD)
        self:asm_spike_drivebase_turn(speed_turn, SPIKE_STOP_HOLD)
    end
end

-- ============================================================================
-- RECOVERY ONE-SHOT OPERATIONS
-- ============================================================================

-- Emergency stop: coast-stop ALL motors on all ports immediately
function LegoSpike:asm_spike_emergency_stop()
    self:asm_one_shot_handler("SPIKE_EMERGENCY_STOP", {})
end

-- Safe shutdown: brake all motors, LEDs off, log
function LegoSpike:asm_spike_safe_shutdown()
    self:asm_one_shot_handler("SPIKE_SAFE_SHUTDOWN", {})
end

-- Log a fault with name and value
function LegoSpike:asm_spike_log_fault(fault_name, fault_data)
    fault_data = fault_data or {}
    self:asm_one_shot_handler("SPIKE_LOG_FAULT",
        { fault_name = fault_name, fault_data = fault_data })
end

-- Clear the bump_detected blackboard flag after handling
function LegoSpike:asm_spike_clear_bump()
    self:asm_one_shot_handler("SPIKE_CLEAR_BUMP", {})
end

-- ============================================================================
-- GUARD COLUMNS (baby exception handlers)
--
-- These use the ChainTree exception_catch pattern:
--   exception_catch container
--     main column    -> normal behavior (aborted on fault)
--     recovery column -> safety actions (runs after abort)
--     finalize column -> cleanup / logging (runs last)
--
-- The aux_function on the exception_catch is a boolean that monitors
-- for the fault condition each tick.  When it returns true, the
-- exception_catch terminates the main column and activates recovery.
-- ============================================================================

-- Battery guard: wraps a column builder function with low-battery protection.
-- column_builder_fn receives (self) and should call asm_* methods to build
-- the main behavior column contents.
function LegoSpike:define_spike_battery_guard(name, threshold_v, column_builder_fn)
    local catch = self:define_exception_catch(
        name,
        SPIKE_BOOL_BATTERY_LOW,
        { threshold_v = threshold_v },
        "SPIKE_LOG_FAULT",
        { fault_name = "BATTERY_LOW" },
        true
    )

    local main_col = self:define_main_exception_column(
        name .. "_main", nil, nil, nil, nil, {}, true)
        column_builder_fn(self)
    self:end_main_exception_column(main_col)

    local recovery_col = self:define_recovery_column(
        name .. "_recovery", 3, "CFL_NULL", {})
        self:asm_spike_log_fault("BATTERY_LOW", { field = "battery_voltage" })
        self:asm_spike_safe_shutdown()
        self:asm_terminate()
    self:end_recovery_column(recovery_col)

    local finalize_col = self:define_finalize_column(
        name .. "_finalize", nil, nil, nil, nil, {}, true)
        self:asm_log_message("Battery guard finalized")
        self:asm_terminate()
    self:end_finalize_column(finalize_col)

    self:exception_catch_end(catch)
    return catch
end

-- Motor overcurrent guard
function LegoSpike:define_spike_stall_guard(name, aux_data, column_builder_fn)
    local catch = self:define_exception_catch(
        name,
        SPIKE_BOOL_MOTOR_OVERCURRENT,
        aux_data,
        "SPIKE_LOG_FAULT",
        { fault_name = "OVERCURRENT" },
        true
    )

    local main_col = self:define_main_exception_column(
        name .. "_main", nil, nil, nil, nil, {}, true)
        column_builder_fn(self)
    self:end_main_exception_column(main_col)

    local recovery_col = self:define_recovery_column(
        name .. "_recovery", 3, "CFL_NULL", {})
        self:asm_spike_log_fault("OVERCURRENT", aux_data)
        self:asm_spike_emergency_stop()
        self:asm_terminate()
    self:end_recovery_column(recovery_col)

    local finalize_col = self:define_finalize_column(
        name .. "_finalize", nil, nil, nil, nil, {}, true)
        self:asm_log_message("Stall guard finalized")
        self:asm_terminate()
    self:end_finalize_column(finalize_col)

    self:exception_catch_end(catch)
    return catch
end

-- Tilt guard: abort and emergency-stop if robot tips beyond max_degrees
function LegoSpike:define_spike_tilt_guard(name, max_degrees, column_builder_fn)
    local catch = self:define_exception_catch(
        name,
        SPIKE_BOOL_TILT_EXCEEDED,
        { max_degrees = max_degrees },
        "SPIKE_LOG_FAULT",
        { fault_name = "TILT_EXCEEDED" },
        true
    )

    local main_col = self:define_main_exception_column(
        name .. "_main", nil, nil, nil, nil, {}, true)
        column_builder_fn(self)
    self:end_main_exception_column(main_col)

    local recovery_col = self:define_recovery_column(
        name .. "_recovery", 3, "CFL_NULL", {})
        self:asm_spike_log_fault("TILT_EXCEEDED", { field = "imu_pitch" })
        self:asm_spike_emergency_stop()
        self:asm_terminate()
    self:end_recovery_column(recovery_col)

    local finalize_col = self:define_finalize_column(
        name .. "_finalize", nil, nil, nil, nil, {}, true)
        self:asm_log_message("Tilt guard finalized")
        self:asm_terminate()
    self:end_finalize_column(finalize_col)

    self:exception_catch_end(catch)
    return catch
end

-- Bump guard: abort when IMU accelerometer detects collision
function LegoSpike:define_spike_bump_guard(name, column_builder_fn)
    local catch = self:define_exception_catch(
        name,
        SPIKE_BOOL_BUMP_DETECTED,
        {},
        "SPIKE_LOG_FAULT",
        { fault_name = "BUMP_DETECTED" },
        true
    )

    local main_col = self:define_main_exception_column(
        name .. "_main", nil, nil, nil, nil, {}, true)
        column_builder_fn(self)
    self:end_main_exception_column(main_col)

    local recovery_col = self:define_recovery_column(
        name .. "_recovery", 4, "CFL_NULL", {})
        self:asm_spike_log_fault("BUMP_DETECTED", { field = "bump_detected" })
        self:asm_spike_emergency_stop()
        self:asm_spike_clear_bump()
        self:asm_terminate()
    self:end_recovery_column(recovery_col)

    local finalize_col = self:define_finalize_column(
        name .. "_finalize", nil, nil, nil, nil, {}, true)
        self:asm_log_message("Bump guard finalized")
        self:asm_terminate()
    self:end_finalize_column(finalize_col)

    self:exception_catch_end(catch)
    return catch
end

-- Communication timeout guard
function LegoSpike:define_spike_comm_guard(name, max_ticks, column_builder_fn)
    local catch = self:define_exception_catch(
        name,
        SPIKE_BOOL_COMM_TIMEOUT,
        { max_ticks = max_ticks },
        "SPIKE_LOG_FAULT",
        { fault_name = "COMM_TIMEOUT" },
        true
    )

    local main_col = self:define_main_exception_column(
        name .. "_main", nil, nil, nil, nil, {}, true)
        column_builder_fn(self)
    self:end_main_exception_column(main_col)

    local recovery_col = self:define_recovery_column(
        name .. "_recovery", 3, "CFL_NULL", {})
        self:asm_spike_log_fault("COMM_TIMEOUT", { field = "comm_last_tick" })
        self:asm_spike_safe_shutdown()
        self:asm_terminate()
    self:end_recovery_column(recovery_col)

    local finalize_col = self:define_finalize_column(
        name .. "_finalize", nil, nil, nil, nil, {}, true)
        self:asm_log_message("Comm guard finalized")
        self:asm_terminate()
    self:end_finalize_column(finalize_col)

    self:exception_catch_end(catch)
    return catch
end

return LegoSpike
