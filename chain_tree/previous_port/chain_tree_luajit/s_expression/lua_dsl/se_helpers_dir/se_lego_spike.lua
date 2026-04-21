--============================================================================
-- se_lego_spike.lua
-- Lego SPIKE Prime / Pybricks leaf functions for S-Expression Engine DSL
--
-- Provides helper functions for motor control, sensor reading, drivebase
-- navigation, and IMU access. All functions communicate with the Pybricks
-- MicroPython runtime through blackboard fields.
--
-- Blackboard convention:
--   Motors:    motor_<port>_angle, motor_<port>_speed, motor_<port>_load,
--              motor_<port>_stalled, motor_<port>_done   (port = a..f)
--   Color:    color_hue, color_sat, color_val, color_id, color_reflection
--   Ultra:    ultrasonic_distance
--   Force:    force_value, force_pressed, force_touched
--   IMU:      imu_heading, imu_pitch, imu_roll, imu_ready
--   Drive:    drivebase_distance, drivebase_angle, drivebase_speed,
--              drivebase_done, drivebase_stalled
--============================================================================

-- ============================================================================
-- Stop type constants (match Pybricks Stop enum)
-- ============================================================================

SPIKE_STOP_COAST = 0
SPIKE_STOP_BRAKE = 1
SPIKE_STOP_HOLD  = 2
SPIKE_STOP_NONE  = 3

-- ============================================================================
-- Port constants
-- ============================================================================

SPIKE_PORT_A = 0
SPIKE_PORT_B = 1
SPIKE_PORT_C = 2
SPIKE_PORT_D = 3
SPIKE_PORT_E = 4
SPIKE_PORT_F = 5

-- ============================================================================
-- Register user functions (C implementation names)
-- ============================================================================

-- Predicates
register_user("SPIKE_MOTOR_STALLED")
register_user("SPIKE_MOTOR_DONE")
register_user("SPIKE_FORCE_PRESSED")
register_user("SPIKE_FORCE_TOUCHED")
register_user("SPIKE_COLOR_IS")
register_user("SPIKE_DISTANCE_LT")
register_user("SPIKE_DISTANCE_GT")
register_user("SPIKE_IMU_READY")
register_user("SPIKE_DRIVEBASE_DONE")
register_user("SPIKE_DRIVEBASE_STALLED")
register_user("SPIKE_FIELD_IN_RANGE")

-- Oneshots
register_user("SPIKE_MOTOR_RUN")
register_user("SPIKE_MOTOR_STOP")
register_user("SPIKE_MOTOR_BRAKE")
register_user("SPIKE_MOTOR_HOLD")
register_user("SPIKE_MOTOR_DC")
register_user("SPIKE_MOTOR_RESET_ANGLE")
register_user("SPIKE_COLOR_LIGHTS_ON")
register_user("SPIKE_COLOR_LIGHTS_OFF")
register_user("SPIKE_ULTRASONIC_LIGHTS_ON")
register_user("SPIKE_ULTRASONIC_LIGHTS_OFF")
register_user("SPIKE_DRIVEBASE_DRIVE")
register_user("SPIKE_DRIVEBASE_STOP")
register_user("SPIKE_DRIVEBASE_BRAKE")
register_user("SPIKE_DRIVEBASE_RESET")
register_user("SPIKE_IMU_RESET_HEADING")
register_user("SPIKE_READ_SENSORS")
register_user("SPIKE_SET_MOTOR_PID")
register_user("SPIKE_SET_MOTOR_LIMITS")

-- Fault predicates
register_user("SPIKE_BATTERY_LOW")
register_user("SPIKE_MOTOR_OVERCURRENT")
register_user("SPIKE_SENSOR_DISCONNECTED")
register_user("SPIKE_COMM_TIMEOUT")
register_user("SPIKE_MOTOR_RUNAWAY")
register_user("SPIKE_TILT_EXCEEDED")
register_user("SPIKE_BUMP_DETECTED")

-- Recovery oneshots
register_user("SPIKE_EMERGENCY_STOP")
register_user("SPIKE_SAFE_SHUTDOWN")
register_user("SPIKE_LOG_FAULT")
register_user("SPIKE_CLEAR_BUMP")

-- Main (tick-driven)
register_user("SPIKE_MOTOR_RUN_ANGLE")
register_user("SPIKE_MOTOR_RUN_TARGET")
register_user("SPIKE_MOTOR_RUN_TIME")
register_user("SPIKE_MOTOR_RUN_UNTIL_STALLED")
register_user("SPIKE_DRIVEBASE_STRAIGHT")
register_user("SPIKE_DRIVEBASE_TURN")
register_user("SPIKE_DRIVEBASE_CURVE")
register_user("SPIKE_WAIT_COLOR")
register_user("SPIKE_WAIT_DISTANCE_LT")
register_user("SPIKE_WAIT_FORCE")
register_user("SPIKE_WAIT_HEADING")

-- ============================================================================
-- BLACKBOARD DEFINITION HELPER
-- Generates the standard Lego SPIKE blackboard with all sensor/motor fields.
-- Call once per module before defining trees.
-- ============================================================================

function spike_define_blackboard()
    define_record("spike_hw")
        -- Motor A
        define_field("motor_a_angle",   "int32",  0)
        define_field("motor_a_speed",   "int32",  0)
        define_field("motor_a_load",    "int32",  0)
        define_field("motor_a_stalled", "int32",  0)
        define_field("motor_a_done",    "int32",  1)
        -- Motor B
        define_field("motor_b_angle",   "int32",  0)
        define_field("motor_b_speed",   "int32",  0)
        define_field("motor_b_load",    "int32",  0)
        define_field("motor_b_stalled", "int32",  0)
        define_field("motor_b_done",    "int32",  1)
        -- Motor C
        define_field("motor_c_angle",   "int32",  0)
        define_field("motor_c_speed",   "int32",  0)
        define_field("motor_c_load",    "int32",  0)
        define_field("motor_c_stalled", "int32",  0)
        define_field("motor_c_done",    "int32",  1)
        -- Motor D
        define_field("motor_d_angle",   "int32",  0)
        define_field("motor_d_speed",   "int32",  0)
        define_field("motor_d_load",    "int32",  0)
        define_field("motor_d_stalled", "int32",  0)
        define_field("motor_d_done",    "int32",  1)
        -- Motor E
        define_field("motor_e_angle",   "int32",  0)
        define_field("motor_e_speed",   "int32",  0)
        define_field("motor_e_load",    "int32",  0)
        define_field("motor_e_stalled", "int32",  0)
        define_field("motor_e_done",    "int32",  1)
        -- Motor F
        define_field("motor_f_angle",   "int32",  0)
        define_field("motor_f_speed",   "int32",  0)
        define_field("motor_f_load",    "int32",  0)
        define_field("motor_f_stalled", "int32",  0)
        define_field("motor_f_done",    "int32",  1)
        -- Color sensor
        define_field("color_hue",        "int32",  0)
        define_field("color_sat",        "int32",  0)
        define_field("color_val",        "int32",  0)
        define_field("color_id",         "int32",  0)
        define_field("color_reflection", "int32",  0)
        -- Ultrasonic sensor
        define_field("ultrasonic_distance", "int32", 0)
        -- Force sensor
        define_field("force_value",   "float",  0.0)
        define_field("force_pressed", "int32",  0)
        define_field("force_touched", "int32",  0)
        -- IMU
        define_field("imu_heading", "float",  0.0)
        define_field("imu_pitch",   "float",  0.0)
        define_field("imu_roll",    "float",  0.0)
        define_field("imu_ready",   "int32",  0)
        -- DriveBase
        define_field("drivebase_distance", "int32",  0)
        define_field("drivebase_angle",    "int32",  0)
        define_field("drivebase_speed",    "int32",  0)
        define_field("drivebase_done",     "int32",  1)
        define_field("drivebase_stalled",  "int32",  0)
        -- Hub / safety monitoring
        define_field("battery_voltage",    "float",  8.0)
        define_field("comm_last_tick",     "int32",  0)
        -- IMU accelerometer (mm/s^2, updated by sensor poll)
        define_field("imu_accel_x",        "float",  0.0)
        define_field("imu_accel_y",        "float",  0.0)
        define_field("imu_accel_z",        "float",  0.0)
        define_field("bump_detected",      "int32",  0)
        -- Per-port sensor connection flags
        define_field("sensor_a_connected", "int32",  1)
        define_field("sensor_b_connected", "int32",  1)
        define_field("sensor_c_connected", "int32",  1)
        define_field("sensor_d_connected", "int32",  1)
        define_field("sensor_e_connected", "int32",  1)
        define_field("sensor_f_connected", "int32",  1)
    end_record()
end

-- ============================================================================
-- PREDICATES
-- ============================================================================

-- Motor stalled check.  port_field = blackboard field for stalled flag
-- e.g. spike_motor_stalled("motor_a_stalled")
function spike_motor_stalled(stalled_field)
    return se_pred_with("SPIKE_MOTOR_STALLED", function()
        field_ref(stalled_field)
    end)
end

-- Motor command done check
function spike_motor_done(done_field)
    return se_pred_with("SPIKE_MOTOR_DONE", function()
        field_ref(done_field)
    end)
end

-- Force sensor pressed
function spike_force_pressed()
    return se_pred_with("SPIKE_FORCE_PRESSED", function()
        field_ref("force_pressed")
    end)
end

-- Force sensor touched
function spike_force_touched()
    return se_pred_with("SPIKE_FORCE_TOUCHED", function()
        field_ref("force_touched")
    end)
end

-- Color matches target (target_color is integer color enum)
function spike_color_is(target_color)
    return se_pred_with("SPIKE_COLOR_IS", function()
        field_ref("color_id")
        int(target_color)
    end)
end

-- Ultrasonic distance less than threshold (mm)
function spike_distance_lt(threshold_mm)
    return se_pred_with("SPIKE_DISTANCE_LT", function()
        field_ref("ultrasonic_distance")
        int(threshold_mm)
    end)
end

-- Ultrasonic distance greater than threshold (mm)
function spike_distance_gt(threshold_mm)
    return se_pred_with("SPIKE_DISTANCE_GT", function()
        field_ref("ultrasonic_distance")
        int(threshold_mm)
    end)
end

-- IMU calibrated and ready
function spike_imu_ready()
    return se_pred_with("SPIKE_IMU_READY", function()
        field_ref("imu_ready")
    end)
end

-- DriveBase command complete
function spike_drivebase_done()
    return se_pred_with("SPIKE_DRIVEBASE_DONE", function()
        field_ref("drivebase_done")
    end)
end

-- DriveBase stalled
function spike_drivebase_stalled()
    return se_pred_with("SPIKE_DRIVEBASE_STALLED", function()
        field_ref("drivebase_stalled")
    end)
end

-- Generic field in range [lo, hi]
function spike_field_in_range(field_name, lo, hi)
    return se_pred_with("SPIKE_FIELD_IN_RANGE", function()
        field_ref(field_name)
        int(lo)
        int(hi)
    end)
end

-- ============================================================================
-- ONESHOT FUNCTIONS (fire and forget)
-- ============================================================================

-- Start motor at constant speed (deg/s)
function spike_motor_run(port, speed)
    local c = o_call("SPIKE_MOTOR_RUN")
        int(port)
        int(speed)
    end_call(c)
end

-- Coast stop motor
function spike_motor_stop(port)
    local c = o_call("SPIKE_MOTOR_STOP")
        int(port)
    end_call(c)
end

-- Passive brake
function spike_motor_brake(port)
    local c = o_call("SPIKE_MOTOR_BRAKE")
        int(port)
    end_call(c)
end

-- Active PID hold at current angle
function spike_motor_hold(port)
    local c = o_call("SPIKE_MOTOR_HOLD")
        int(port)
    end_call(c)
end

-- Raw duty cycle (-100 to 100)
function spike_motor_dc(port, duty)
    local c = o_call("SPIKE_MOTOR_DC")
        int(port)
        int(duty)
    end_call(c)
end

-- Reset encoder angle
function spike_motor_reset_angle(port, angle)
    angle = angle or 0
    local c = o_call("SPIKE_MOTOR_RESET_ANGLE")
        int(port)
        int(angle)
    end_call(c)
end

-- Color sensor LEDs on (brightness 0-100)
function spike_color_lights_on(port, brightness)
    local c = o_call("SPIKE_COLOR_LIGHTS_ON")
        int(port)
        int(brightness)
    end_call(c)
end

-- Color sensor LEDs off
function spike_color_lights_off(port)
    local c = o_call("SPIKE_COLOR_LIGHTS_OFF")
        int(port)
    end_call(c)
end

-- Ultrasonic sensor LEDs on
function spike_ultrasonic_lights_on(port, brightness)
    local c = o_call("SPIKE_ULTRASONIC_LIGHTS_ON")
        int(port)
        int(brightness)
    end_call(c)
end

-- Ultrasonic sensor LEDs off
function spike_ultrasonic_lights_off(port)
    local c = o_call("SPIKE_ULTRASONIC_LIGHTS_OFF")
        int(port)
    end_call(c)
end

-- Continuous drive (speed mm/s, turn_rate deg/s)
function spike_drivebase_drive(speed, turn_rate)
    local c = o_call("SPIKE_DRIVEBASE_DRIVE")
        int(speed)
        int(turn_rate)
    end_call(c)
end

-- Stop drivebase (coast)
function spike_drivebase_stop()
    local c = o_call("SPIKE_DRIVEBASE_STOP")
    end_call(c)
end

-- Brake drivebase
function spike_drivebase_brake()
    local c = o_call("SPIKE_DRIVEBASE_BRAKE")
    end_call(c)
end

-- Reset drivebase odometry
function spike_drivebase_reset()
    local c = o_call("SPIKE_DRIVEBASE_RESET")
    end_call(c)
end

-- Reset IMU heading reference
function spike_imu_reset_heading(angle)
    angle = angle or 0
    local c = o_call("SPIKE_IMU_RESET_HEADING")
        int(angle)
    end_call(c)
end

-- Trigger sensor poll cycle, update all blackboard fields
function spike_read_sensors()
    local c = o_call("SPIKE_READ_SENSORS")
    end_call(c)
end

-- Configure motor PID gains
function spike_set_motor_pid(port, kp, ki, kd)
    local c = o_call("SPIKE_SET_MOTOR_PID")
        int(port)
        int(kp)
        int(ki)
        int(kd)
    end_call(c)
end

-- Configure motor control limits (speed deg/s, accel deg/s^2, torque mNm)
function spike_set_motor_limits(port, max_speed, acceleration, torque)
    local c = o_call("SPIKE_SET_MOTOR_LIMITS")
        int(port)
        int(max_speed)
        int(acceleration)
        int(torque)
    end_call(c)
end

-- ============================================================================
-- MAIN FUNCTIONS (tick-driven, return SE_HALT until done)
-- ============================================================================

-- Run motor a relative angle (deg), stop_type = SPIKE_STOP_*
function spike_motor_run_angle(port, speed, angle, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    local c = pt_m_call("SPIKE_MOTOR_RUN_ANGLE")
        int(port)
        int(speed)
        int(angle)
        int(stop_type)
    end_call(c)
end

-- Run motor to absolute target angle (deg)
function spike_motor_run_target(port, speed, target, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    local c = pt_m_call("SPIKE_MOTOR_RUN_TARGET")
        int(port)
        int(speed)
        int(target)
        int(stop_type)
    end_call(c)
end

-- Run motor for duration (ms)
function spike_motor_run_time(port, speed, time_ms, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    local c = pt_m_call("SPIKE_MOTOR_RUN_TIME")
        int(port)
        int(speed)
        int(time_ms)
        int(stop_type)
    end_call(c)
end

-- Run motor until stall detected, writes stall angle to blackboard
function spike_motor_run_until_stalled(port, speed, duty_limit)
    duty_limit = duty_limit or 100
    local c = pt_m_call("SPIKE_MOTOR_RUN_UNTIL_STALLED")
        int(port)
        int(speed)
        int(duty_limit)
    end_call(c)
end

-- Drive straight (distance_mm), stop_type = SPIKE_STOP_*
function spike_drivebase_straight(distance_mm, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    local c = pt_m_call("SPIKE_DRIVEBASE_STRAIGHT")
        int(distance_mm)
        int(stop_type)
    end_call(c)
end

-- Turn in place (angle_deg, positive = right)
function spike_drivebase_turn(angle_deg, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    local c = pt_m_call("SPIKE_DRIVEBASE_TURN")
        int(angle_deg)
        int(stop_type)
    end_call(c)
end

-- Drive arc (radius mm, angle deg)
function spike_drivebase_curve(radius, angle, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    local c = pt_m_call("SPIKE_DRIVEBASE_CURVE")
        int(radius)
        int(angle)
        int(stop_type)
    end_call(c)
end

-- Wait until color sensor matches target
function spike_wait_color(target_color)
    local c = pt_m_call("SPIKE_WAIT_COLOR")
        int(target_color)
    end_call(c)
end

-- Wait until ultrasonic distance < threshold_mm
function spike_wait_distance_lt(threshold_mm)
    local c = pt_m_call("SPIKE_WAIT_DISTANCE_LT")
        int(threshold_mm)
    end_call(c)
end

-- Wait until force sensor > threshold (Newtons)
function spike_wait_force(threshold_n)
    local c = pt_m_call("SPIKE_WAIT_FORCE")
        flt(threshold_n)
    end_call(c)
end

-- Wait until heading within tolerance of target (degrees)
function spike_wait_heading(target_deg, tolerance)
    tolerance = tolerance or 5
    local c = pt_m_call("SPIKE_WAIT_HEADING")
        int(target_deg)
        int(tolerance)
    end_call(c)
end

-- ============================================================================
-- COMPOSITE HELPERS
-- Higher-level patterns built from the leaf functions above
-- ============================================================================

-- Run motor angle then continue (sequence wrapper)
function spike_do_motor_angle(port, speed, angle, stop_type)
    se_sequence(
        function() spike_motor_run_angle(port, speed, angle, stop_type) end,
        function() se_return_continue() end
    )
end

-- Drive straight then continue
function spike_do_straight(distance_mm, stop_type)
    se_sequence(
        function() spike_drivebase_straight(distance_mm, stop_type) end,
        function() se_return_continue() end
    )
end

-- Turn then continue
function spike_do_turn(angle_deg, stop_type)
    se_sequence(
        function() spike_drivebase_turn(angle_deg, stop_type) end,
        function() se_return_continue() end
    )
end

-- Drive until object detected within distance, then stop
function spike_drive_until_close(speed, turn_rate, threshold_mm)
    se_sequence(
        function() spike_drivebase_drive(speed, turn_rate) end,
        function() spike_wait_distance_lt(threshold_mm) end,
        function() spike_drivebase_brake() end,
        function() se_return_continue() end
    )
end

-- Find mechanical endpoint: run until stalled, reset angle to 0
function spike_find_endpoint(port, speed, duty_limit)
    se_sequence(
        function() spike_motor_run_until_stalled(port, speed, duty_limit) end,
        function() spike_motor_reset_angle(port, 0) end,
        function() se_return_continue() end
    )
end

-- Poll sensors continuously in a fork (fire-and-forget polling loop)
-- Place inside a se_fork() alongside control logic
function spike_sensor_poll_loop()
    se_sequence(
        function() spike_read_sensors() end,
        function() se_tick_delay(1) end,
        function() se_return_reset() end
    )
end

-- Wait for IMU ready before proceeding
function spike_wait_imu_ready()
    se_wait(spike_imu_ready())
end

-- ============================================================================
-- FAULT PREDICATES
-- These return true when a fault condition exists.
-- Used with se_verify (which fires when predicate returns FALSE),
-- so wrap with se_pred_not() when passing to se_verify, or use the
-- spike_guarded_action helper which handles inversion automatically.
-- ============================================================================

-- Battery voltage below threshold (Volts)
function spike_battery_low(threshold_v)
    return se_pred_with("SPIKE_BATTERY_LOW", function()
        field_ref("battery_voltage")
        flt(threshold_v)
    end)
end

-- Motor load exceeds safe torque limit (mNm)
function spike_motor_overcurrent(load_field, threshold_mNm)
    return se_pred_with("SPIKE_MOTOR_OVERCURRENT", function()
        field_ref(load_field)
        int(threshold_mNm)
    end)
end

-- Sensor disconnected on port (connection flag = 0)
function spike_sensor_disconnected(connected_field)
    return se_pred_with("SPIKE_SENSOR_DISCONNECTED", function()
        field_ref(connected_field)
    end)
end

-- Communication bridge hasn't updated in max_ticks
function spike_comm_timeout(max_ticks)
    return se_pred_with("SPIKE_COMM_TIMEOUT", function()
        field_ref("comm_last_tick")
        int(max_ticks)
    end)
end

-- Motor speed exceeds safe maximum (runaway detection, deg/s)
function spike_motor_runaway(speed_field, max_speed)
    return se_pred_with("SPIKE_MOTOR_RUNAWAY", function()
        field_ref(speed_field)
        int(max_speed)
    end)
end

-- Robot tipped beyond safe angle (checks both pitch and roll, degrees)
function spike_tilt_exceeded(max_degrees)
    return se_pred_with("SPIKE_TILT_EXCEEDED", function()
        field_ref("imu_pitch")
        field_ref("imu_roll")
        int(max_degrees)
    end)
end

-- Bump detected via accelerometer spike (flag set by SPIKE_BUMP_DETECT main)
function spike_bump_detected()
    return se_pred_with("SPIKE_BUMP_DETECTED", function()
        field_ref("bump_detected")
    end)
end

-- ============================================================================
-- RECOVERY ONESHOT FUNCTIONS
-- ============================================================================

-- Emergency stop: coast-stop ALL motors on all ports immediately
function spike_emergency_stop()
    local c = o_call("SPIKE_EMERGENCY_STOP")
    end_call(c)
end

-- Safe shutdown: brake all motors, LEDs off, log
function spike_safe_shutdown()
    local c = o_call("SPIKE_SAFE_SHUTDOWN")
    end_call(c)
end

-- Log a fault with name and the blackboard field value that triggered it
function spike_log_fault(fault_name, fault_field)
    local c = o_call("SPIKE_LOG_FAULT")
        str_ptr(fault_name)
        field_ref(fault_field)
    end_call(c)
end

-- Clear the bump_detected flag after handling
function spike_clear_bump()
    local c = o_call("SPIKE_CLEAR_BUMP")
    end_call(c)
end

-- ============================================================================
-- BUMP DETECTION (main function, tick-driven)
--
-- Monitors IMU accelerometer magnitude each tick.  When the magnitude
-- exceeds the threshold (indicating a collision/bump), sets the
-- bump_detected blackboard field to 1.  Runs continuously (resets
-- after each detection so it can catch the next bump).
--
-- Place inside a se_fork() alongside your main control logic.
-- ============================================================================

register_user("SPIKE_BUMP_DETECT")

-- Continuous bump detector.  threshold is in mm/s^2
-- (gravity ~= 9810 mm/s^2, so a bump threshold of ~15000-20000 is typical)
function spike_bump_detect(threshold)
    local c = pt_m_call("SPIKE_BUMP_DETECT")
        flt(threshold)
    end_call(c)
end

-- ============================================================================
-- GUARD COMPOSITES (baby exception handlers)
--
-- These use se_function_interface + se_verify to monitor fault conditions
-- alongside a main action.  When the fault fires, the pipeline terminates
-- and the recovery oneshot executes.
--
-- se_verify fires when its predicate returns FALSE.
-- Fault predicates return TRUE when fault exists.
-- So we invert: se_verify(NOT(fault), ...) -> fires when fault is TRUE.
-- ============================================================================

-- Core guard pattern: run action_fn with a single fault monitor.
-- When fault_pred becomes true, abort action and run recovery_fn.
-- reset_on_fault: true = SE_PIPELINE_RESET, false = SE_PIPELINE_TERMINATE
function spike_guarded_action(fault_pred, recovery_fn, action_fn, reset_on_fault)
    if reset_on_fault == nil then reset_on_fault = false end

    -- Build the inverted predicate: NOT(fault) -> true when healthy
    pred_begin()
        local n = se_pred_not()
            fault_pred()
        pred_close(n)
    local healthy_pred = pred_end()

    se_function_interface(function()
        se_verify(healthy_pred, reset_on_fault, recovery_fn)
        action_fn()
    end)
end

-- Stack multiple guards on a single action.
-- guards = list of { pred = fault_pred_fn, recovery = recovery_fn }
function spike_multi_guard(guards, action_fn, reset_on_fault)
    if reset_on_fault == nil then reset_on_fault = false end

    se_function_interface(function()
        for _, guard in ipairs(guards) do
            pred_begin()
                local n = se_pred_not()
                    guard.pred()
                pred_close(n)
            local healthy = pred_end()
            se_verify(healthy, reset_on_fault, guard.recovery)
        end
        action_fn()
    end)
end

-- ============================================================================
-- PRE-BUILT GUARD PATTERNS
-- ============================================================================

-- Battery guard: abort and safe-shutdown if voltage drops below threshold
function spike_battery_guard(threshold_v, action_fn)
    spike_guarded_action(
        function() spike_battery_low(threshold_v) end,
        function()
            spike_log_fault("BATTERY_LOW", "battery_voltage")
            spike_safe_shutdown()
        end,
        action_fn
    )
end

-- Motor overcurrent guard: abort and emergency-stop if load exceeds limit
-- load_field = e.g. "motor_a_load"
function spike_stall_guard(load_field, threshold_mNm, action_fn)
    spike_guarded_action(
        function() spike_motor_overcurrent(load_field, threshold_mNm) end,
        function()
            spike_log_fault("OVERCURRENT", load_field)
            spike_emergency_stop()
        end,
        action_fn
    )
end

-- Tilt guard: abort and emergency-stop if robot tips
function spike_tilt_guard(max_degrees, action_fn)
    spike_guarded_action(
        function() spike_tilt_exceeded(max_degrees) end,
        function()
            spike_log_fault("TILT_EXCEEDED", "imu_pitch")
            spike_emergency_stop()
        end,
        action_fn
    )
end

-- Communication timeout guard: abort and safe-shutdown if bridge lost
function spike_comm_guard(max_ticks, action_fn)
    spike_guarded_action(
        function() spike_comm_timeout(max_ticks) end,
        function()
            spike_log_fault("COMM_TIMEOUT", "comm_last_tick")
            spike_safe_shutdown()
        end,
        action_fn
    )
end

-- Bump guard: abort action when bump/collision detected
function spike_bump_guard(action_fn)
    spike_guarded_action(
        function() spike_bump_detected() end,
        function()
            spike_log_fault("BUMP_DETECTED", "bump_detected")
            spike_emergency_stop()
        end,
        action_fn
    )
end

-- Full safety suite: battery + tilt + bump + comm timeout on one action
function spike_full_safety_guard(action_fn, opts)
    opts = opts or {}
    local battery_v   = opts.battery_v   or 6.5
    local max_tilt     = opts.max_tilt     or 45
    local bump_thresh  = opts.bump_thresh  or 18000
    local comm_ticks   = opts.comm_ticks   or 100

    se_fork(
        -- Bump detector runs continuously alongside everything
        function() spike_bump_detect(bump_thresh) end,
        -- Guarded main action with all monitors
        function()
            spike_multi_guard({
                { pred = function() spike_battery_low(battery_v) end,
                  recovery = function()
                      spike_log_fault("BATTERY_LOW", "battery_voltage")
                      spike_safe_shutdown()
                  end },
                { pred = function() spike_tilt_exceeded(max_tilt) end,
                  recovery = function()
                      spike_log_fault("TILT_EXCEEDED", "imu_pitch")
                      spike_emergency_stop()
                  end },
                { pred = function() spike_bump_detected() end,
                  recovery = function()
                      spike_log_fault("BUMP_DETECTED", "bump_detected")
                      spike_emergency_stop()
                  end },
                { pred = function() spike_comm_timeout(comm_ticks) end,
                  recovery = function()
                      spike_log_fault("COMM_TIMEOUT", "comm_last_tick")
                      spike_safe_shutdown()
                  end },
            }, action_fn)
        end
    )
end

-- Safe drive: drivebase straight with full safety suite
function spike_safe_straight(distance_mm, stop_type, opts)
    spike_full_safety_guard(function()
        spike_drivebase_straight(distance_mm, stop_type)
    end, opts)
end

-- Safe turn: drivebase turn with full safety suite
function spike_safe_turn(angle_deg, stop_type, opts)
    spike_full_safety_guard(function()
        spike_drivebase_turn(angle_deg, stop_type)
    end, opts)
end

-- Safe motor: run motor angle with overcurrent + bump guard
function spike_safe_motor_angle(port, speed, angle, load_field, max_load, stop_type)
    stop_type = stop_type or SPIKE_STOP_HOLD
    spike_multi_guard({
        { pred = function() spike_motor_overcurrent(load_field, max_load) end,
          recovery = function()
              spike_log_fault("OVERCURRENT", load_field)
              spike_emergency_stop()
          end },
        { pred = function() spike_bump_detected() end,
          recovery = function()
              spike_log_fault("BUMP_DETECTED", "bump_detected")
              spike_emergency_stop()
          end },
    }, function()
        spike_motor_run_angle(port, speed, angle, stop_type)
    end)
end

print("SPIKE Prime S-Expression helpers loaded (with safety monitors)")
