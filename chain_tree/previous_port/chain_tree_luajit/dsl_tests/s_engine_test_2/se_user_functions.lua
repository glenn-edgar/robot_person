-- se_user_functions.lua — SE-level user functions for s_engine_test_2
-- Ported from chain_tree_c/dsl_tests/s_engine_test_2/s_engine/user_functions.c

local se = require("se_runtime")
local defs = require("ct_definitions")

local M = {}

-- Event constants (match C defines)
local EVT_TIMER    = 0xEE01
local EVT_BUTTON   = 0xEE02
local EVT_SENSOR   = 0xEE03
local EVT_ALARM    = 0xEE04
local EVT_SHUTDOWN = 0xEE05

local CFL_TIMER_EVENT  = defs.CFL_TIMER_EVENT

-- ============================================================================
-- TEST_31: Motor/state control oneshots
-- ============================================================================

M.TEST_31_SET_MOTOR = function(inst, node)
    if #node.params < 2 then return end
    local motor_id = se.param_int(node, 1)
    local speed    = se.param_int(node, 2)
    print(string.format("TEST_31_SET_MOTOR: MOTOR[%d] = %d", motor_id, speed))
end

M.TEST_31_SET_STATE = function(inst, node)
    if #node.params < 2 then return end
    local value = se.param_int(node, 2)
    se.field_set(inst, node, 1, value)
    print(string.format("TEST_31_SET_STATE: set %d", value))
end

-- ============================================================================
-- TEST_32: I/O oneshots
-- ============================================================================

M.TEST_32_ENABLE_BUZZER = function(inst, node)
    print("BUZZER: ENABLED")
end

M.TEST_32_DISABLE_ALL_OUTPUTS = function(inst, node)
    print("OUTPUTS: ALL DISABLED")
end

M.TEST_32_TOGGLE_LED = function(inst, node)
    if #node.params < 1 then return end
    local led_id = se.param_int(node, 1)
    print(string.format("LED[%d]: TOGGLED", led_id))
end

M.TEST_32_SET_LED = function(inst, node)
    if #node.params < 2 then return end
    local led_id = se.param_int(node, 1)
    local state  = se.param_int(node, 2)
    print(string.format("LED[%d]: %s", led_id, state ~= 0 and "ON" or "OFF"))
end

M.TEST_32_SAVE_STATE = function(inst, node)
    print("STATE: SAVED")
end

M.TEST_32_NOTIFY_SYSTEM = function(inst, node)
    if #node.params < 1 then return end
    local p = node.params[1]
    local hash
    if p.type == "str_hash" then
        hash = p.value.hash or 0
    else
        hash = tonumber(p.value) or 0
    end
    print(string.format("NOTIFY: 0x%08X", hash))
end

-- ============================================================================
-- TEST_32: Main functions
-- ============================================================================

M.TEST_32_PROCESS_SCHEDULED_TASKS = function(inst, node, event_id, event_data)
    if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
        return se.SE_CONTINUE
    end
    if event_id == EVT_TIMER then
        print("SCHEDULED_TASKS: PROCESSING")
    end
    return se.SE_CONTINUE
end

M.TEST_32_RUN_BACKGROUND_TASKS = function(inst, node, event_id, event_data)
    if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
        return se.SE_CONTINUE
    end
    if event_id == defs.CFL_SECOND_EVENT then
        print("BACKGROUND_TASKS: RUNNING")
    end
    return se.SE_CONTINUE
end

M.TEST_32_CHECK_THRESHOLD = function(inst, node, event_id, event_data)
    if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
        return se.SE_CONTINUE
    end
    if #node.params < 2 then return se.SE_TERMINATE end
    if event_id == EVT_SENSOR then
        local reading = tonumber(event_data) or 0
        local threshold = se.param_int(node, 2)
        if reading > threshold then
            print(string.format("SENSOR: ABOVE THRESHOLD (%d > %d)", reading, threshold))
        end
    end
    return se.SE_CONTINUE
end

M.TEST_32_GENERATE_INTERNAL_EVENTS = function(inst, node, event_id, event_data)
    if event_id == se.SE_EVENT_INIT then
        -- Initialize tick counter via node state
        local ns = se.get_ns(inst, node.node_index)
        ns.counter = 0
        return se.SE_CONTINUE
    end
    if event_id == se.SE_EVENT_TERMINATE then
        return se.SE_CONTINUE
    end

    -- Only process on SE_EVENT_TICK (mapped from CFL_TIMER_EVENT by bridge)
    if event_id ~= se.SE_EVENT_TICK then
        return se.SE_CONTINUE
    end

    local ns = se.get_ns(inst, node.node_index)
    ns.counter = (ns.counter or 0) + 1
    local counter = ns.counter

    -- Push events to CFL event queue (not SE queue) targeting this SE engine node
    local handle = inst.user_ctx
    local target = inst.ct_node_id

    -- Every 100 ticks: timer event
    if counter % 100 == 0 then
        table.insert(handle.event_queue, { node_id = target, event_id = EVT_TIMER, event_data = 0 })
    end

    -- Every 10 ticks: button event
    if counter % 10 == 0 then
        table.insert(handle.event_queue, { node_id = target, event_id = EVT_BUTTON, event_data = 0 })
    end

    -- At counter 200: alarm
    if counter == 200 then
        print("EVENT_GEN: ALARM TRIGGERED")
        table.insert(handle.event_queue, { node_id = target, event_id = EVT_ALARM, event_data = 0 })
    end

    -- Every tick: sensor event with data = counter % 60
    table.insert(handle.event_queue, { node_id = target, event_id = EVT_SENSOR, event_data = counter % 60 })

    return se.SE_CONTINUE
end

-- ============================================================================
-- TEST_33-39: Stub oneshots (advanced tests not yet ported)
-- ============================================================================

local function noop(inst, node) end

M.TEST_33_READ_VECTOR = noop
M.TEST_33_READ_PID = noop
M.TEST_33_READ_SYSTEM = noop
M.TEST_34_ALLOC_NODE = noop
M.TEST_34_ALLOC_SENSOR = noop
M.TEST_34_READ_NODE = noop
M.TEST_34_READ_SENSOR = noop
M.TEST_34_READ_UINT32 = noop
M.TEST_34_READ_UINT16 = noop
M.TEST_34_CHECK_NULL = noop
M.TEST_34_FREE_PTR = noop
M.TEST_35_BUILD_LIST = noop
M.TEST_35_TRAVERSE_LIST = noop
M.TEST_35_FREE_LIST = noop
M.TEST_36_COPY_PTR = noop
M.TEST_36_VERIFY_SAME_PTR = noop
M.TEST_36_MODIFY_NODE_VALUE = noop
M.TEST_36_CLEAR_PTR = noop
M.TEST_37_COPY_STATIC_NETWORK = noop
M.TEST_37_VERIFY_NETWORK = noop
M.TEST_37_VERIFY_SENSORS = noop
M.TEST_37_VERIFY_DEVICE_NAME = noop
M.TEST_37_VERIFY_DEVICE_SERIAL = noop
M.TEST_37_VERIFY_DEVICE_INFO = noop
M.TEST_37_VERIFY_TOP_LEVEL = noop
M.TEST_37_DUMP_STATE = noop
M.TEST_37_VERIFY_STRING_PTR = noop
M.TEST_38_VERIFY_DEFAULTS = noop
M.TEST_38_VERIFY_TEST_PID = noop
M.TEST_39_VERIFY_GAINS = noop
M.TEST_39_VERIFY_POINTER = noop

return M
