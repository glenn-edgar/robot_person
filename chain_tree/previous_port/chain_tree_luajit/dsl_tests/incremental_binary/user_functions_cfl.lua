-- user_functions_cfl.lua — user functions for CFL runtime (mirrors C signatures)
--
-- CFL runtime signatures:
--   main:    fn(handle, bool_fn_idx, node_idx, event_type, event_id, event_data) -> return_code
--   boolean: fn(handle, node_idx, event_type, event_id, event_data) -> bool
--   oneshot: fn(handle, node_idx) -> nil
--
-- Node data access: common.get_node_data(handle, node_idx) -> node_dict table
-- Node state:       common.get_node_state(handle, node_idx) -> per-node mutable table

local common    = require("cfl_common")
local defs      = require("cfl_definitions")
local streaming = require("cfl_streaming")
local eq_mod    = require("cfl_event_queue")

local CFL_CONTINUE         = defs.CFL_CONTINUE
local CFL_HALT             = defs.CFL_HALT
local CFL_TERMINATE        = defs.CFL_TERMINATE
local CFL_DISABLE          = defs.CFL_DISABLE
local CFL_INIT_EVENT       = defs.CFL_INIT_EVENT
local CFL_TERMINATE_EVENT  = defs.CFL_TERMINATE_EVENT
local CFL_TIMER_EVENT      = defs.CFL_TIMER_EVENT
local CFL_RAISE_EXCEPTION_EVENT = defs.CFL_RAISE_EXCEPTION_EVENT

local M = {}

-- ============================================================================
-- FFI / Avro schema loading
-- ============================================================================
local ffi_ok, ffi = pcall(require, "ffi")
local stream_schema, drone_schema

local function load_schemas()
    if stream_schema then return end
    local ok1, s = pcall(require, "stream_test_1_ffi")
    if ok1 then stream_schema = s end
    local ok2, d = pcall(require, "drone_control_ffi")
    if ok2 then drone_schema = d end
end

-- ============================================================================
-- ONE-SHOT FUNCTIONS
-- ============================================================================

M.ACTIVATE_VALVE = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if nd and nd.state == "open" then
        print("Valve is open")
    end
end

M.WAIT_FOR_EVENT_ERROR = function(handle, node_idx)
    print(string.format("wait_for_event_error_one_shot_fn node: %d", node_idx))
end

M.VERIFY_ERROR = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    local msg = ns and ns.error_data and ns.error_data.failure_data
    print(string.format("error_message: %s", tostring(msg)))
end

M.INITIALIZE_SEQUENCE = function(handle, node_idx)
    -- no-op
end

M.DISPLAY_SEQUENCE_TILL_RESULT = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    local msg = nd and nd.column_data and nd.column_data.user_data
        and nd.column_data.user_data.message
    print(string.format("display_sequence_till_result_one_shot_fn message: %s", tostring(msg)))
    if ns then
        local st = ns.sequence_type == "pass" and 0 or 1
        local sr = ns.final_status == true and 1 or 0
        print(string.format("sequence_type: %d", st))
        print(string.format("sequence_result: %d", sr))
    end
end

M.DISPLAY_SEQUENCE_RESULT = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    if ns and ns.try_node_indexes then
        print(string.format("try_node_count: %d", #ns.try_node_indexes))
    end
end

M.DISPLAY_FAILURE_WINDOW_RESULT = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    if ns then
        print(string.format("failed_link_index: %s", tostring(ns.failed_link_index)))
    end
    local nd = common.get_node_data(handle, node_idx)
    local uplink = nd and nd.column_data and nd.column_data.user_data
        and nd.column_data.user_data.uplink_node_id
    print(string.format("uplink_node_id: %s if communicating with uplink node", tostring(uplink)))
end

M.WATCH_DOG_TIME_OUT = function(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    local reset = nd and nd.wd_reset
    local msg = nd and nd.wd_fn_data and nd.wd_fn_data.message
    print(string.format("watch_dog_time_out_one_shot_fn reset: %s", tostring(reset)))
    print(string.format("watch_dog_time_out_one_shot_fn message: %s", tostring(msg)))
end

M.EXCEPTION_LOGGING = function(handle, node_idx)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then ns = common.alloc_node_state(handle, node_idx) end

    if not ns.logging_data then
        local nd = common.get_node_data(handle, node_idx)
        ns.logging_data = nd and nd.column_data
            and nd.column_data.logging_function_data
            and nd.column_data.logging_function_data.logging_function_data
    end

    print("*********** exception_logging_one_shot_fn ***********")
    print(string.format("original_node_id: %s", tostring(ns.original_node_id)))
    print(string.format("logging_data: %s", tostring(ns.logging_data)))
    print(string.format("exception_type: %s", tostring(ns.exception_type)))
    print("*********** exception_logging_one_shot_fn ***********")
end

M.WHILE_BITMASK_FAILURE = function(handle, node_idx)
    print(string.format("--------------------> while bitmask timeout: %d", node_idx))
end

M.VERIFY_BITMASK_FAILURE = function(handle, node_idx)
    print(string.format("--------------------> verify bitmask failure: %d", node_idx))
end

M.WAIT_FOR_TEST_COMPLETE_ERROR = function(handle, node_idx)
    print(string.format("--------------------> wait for test complete error: %d", node_idx))
end

M.VERIFY_TESTS_ACTIVE_ERROR = function(handle, node_idx)
    print(string.format("--------------------> verify tests active error: %d", node_idx))
end

-- ============================================================================
-- BLACKBOARD TEST FUNCTIONS
-- ============================================================================

M.BB_INIT_FIELDS = function(handle, node_idx)
    if not handle.blackboard then handle.blackboard = {} end
    local bb = handle.blackboard
    bb.mode = 42
    bb.temperature = 98.6
    bb.error_count = 7
    if not bb.nav then bb.nav = {} end
    bb.nav.heading = 270
    bb.nav.altitude = 3500.0
    bb.nav.speed = 125.5
    bb.debug_ptr = 0xDEADBEEFCAFEBABEULL
    print("[BB_INIT] Fields initialized")
end

M.BB_VERIFY_BASIC_FIELDS = function(handle, node_idx)
    local bb = handle.blackboard or {}
    local pass, fail = 0, 0
    local function check(name, got, expected)
        if type(expected) == "number" and type(got) == "number" then
            if math.abs(got - expected) < 0.001 then pass = pass + 1
            else print(string.format("[BB_VERIFY] FAIL: %s=%s expected %s", name, tostring(got), tostring(expected))); fail = fail + 1 end
        elseif got == expected then pass = pass + 1
        else print(string.format("[BB_VERIFY] FAIL: %s=%s expected %s", name, tostring(got), tostring(expected))); fail = fail + 1 end
    end
    check("mode", bb.mode, 42)
    check("temperature", bb.temperature, 98.6)
    check("error_count", bb.error_count, 7)
    print(string.format("[BB_VERIFY_BASIC] pass=%d fail=%d", pass, fail))
end

M.BB_VERIFY_NESTED_FIELDS = function(handle, node_idx)
    local bb = handle.blackboard or {}
    local nav = bb.nav or {}
    local pass, fail = 0, 0
    local function check(name, got, expected)
        if type(expected) == "number" and type(got) == "number" then
            if math.abs(got - expected) < 0.001 then pass = pass + 1
            else print(string.format("[BB_NESTED] FAIL: %s=%s expected %s", name, tostring(got), tostring(expected))); fail = fail + 1 end
        elseif got == expected then pass = pass + 1
        else print(string.format("[BB_NESTED] FAIL: %s=%s expected %s", name, tostring(got), tostring(expected))); fail = fail + 1 end
    end
    check("nav.heading", nav.heading, 270)
    check("nav.altitude", nav.altitude, 3500.0)
    check("nav.speed", nav.speed, 125.5)
    nav.heading = 90
    check("nav.heading (after set)", nav.heading, 90)
    print(string.format("[BB_VERIFY_NESTED] pass=%d fail=%d", pass, fail))
end

M.BB_VERIFY_CONST_RECORD = function(handle, node_idx)
    local bb = handle.blackboard or {}
    local pass, fail = 0, 0
    local cal = bb.const_records and bb.const_records.calibration
    if not cal then
        print("[BB_CONST] FAIL: calibration record not found")
        return
    end
    pass = pass + 1
    local function check(name, got, expected)
        if type(expected) == "number" and type(got) == "number" then
            if math.abs(got - expected) < 0.001 then pass = pass + 1
            else print(string.format("[BB_CONST] FAIL: %s=%s expected %s", name, tostring(got), tostring(expected))); fail = fail + 1 end
        elseif got == expected then pass = pass + 1
        else print(string.format("[BB_CONST] FAIL: %s=%s expected %s", name, tostring(got), tostring(expected))); fail = fail + 1 end
    end
    check("gain", cal.gain, 1.5)
    check("offset", cal.offset, -0.25)
    check("max_value", cal.max_value, 1000)
    check("scale_x", cal.scale_x, 2.0)
    check("scale_y", cal.scale_y, 3.0)
    print(string.format("[BB_VERIFY_CONST] pass=%d fail=%d", pass, fail))
end

M.BB_VERIFY_PTR64_FIELD = function(handle, node_idx)
    local bb = handle.blackboard or {}
    local pass, fail = 0, 0
    if bb.debug_ptr == 0xDEADBEEFCAFEBABEULL then
        pass = pass + 1
    else
        print(string.format("[BB_PTR64] FAIL: debug_ptr=%s expected 0xDEADBEEFCAFEBABE", tostring(bb.debug_ptr)))
        fail = fail + 1
    end
    bb.debug_ptr = 12345
    if bb.debug_ptr == 12345 then pass = pass + 1
    else print("[BB_PTR64] FAIL: roundtrip failed"); fail = fail + 1 end
    print(string.format("[BB_VERIFY_PTR64] pass=%d fail=%d", pass, fail))
end

-- ============================================================================
-- AVRO TEST FUNCTIONS (pre-streaming, direct packet test)
-- ============================================================================

M.GENERATE_AVRO_PACKET = function(handle, node_idx)
    load_schemas()
    if not stream_schema or not ffi_ok then return end
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local pkt = stream_schema.new_packet("accelerometer_reading")
    stream_schema.packet_init(pkt, "accelerometer_reading", node_idx)
    pkt.data.x = 1.0; pkt.data.y = 2.0; pkt.data.z = 9.81
    local target = nd.event_column or handle.kb_start_index or 0
    if handle.flash_handle.original_to_final and handle.flash_handle.original_to_final[target] then
        target = handle.flash_handle.original_to_final[target]
    end
    streaming.send_streaming_event(handle, target, nd.event_id or 0, pkt)
end

M.GENERATE_CONST_AVRO_PACKET = function(handle, node_idx)
    load_schemas()
    if not stream_schema or not ffi_ok then return end
    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local const_pkt = stream_schema.const_packets and stream_schema.const_packets.default_accel_reading
    if not const_pkt then return end
    local pkt = stream_schema.new_packet("accelerometer_reading")
    ffi.copy(pkt, const_pkt, ffi.sizeof(pkt))
    local target = nd.event_column or handle.kb_start_index or 0
    if handle.flash_handle.original_to_final and handle.flash_handle.original_to_final[target] then
        target = handle.flash_handle.original_to_final[target]
    end
    streaming.send_streaming_event(handle, target, nd.event_id or 0, pkt)
end

M.AVRO_VERIFY_PACKET_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    ns.event_id = nd and nd.event_id
    ns.verified = false
end

M.AVRO_VERIFY_CONST_PACKET_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    ns.event_id = nd and nd.event_id
    ns.verified = false
end

M.AVRO_VERIFY_PACKET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_CONTINUE end

    if event_type == defs.CFL_EVENT_TYPE_STREAMING_DATA and event_id == ns.event_id then
        load_schemas()
        if stream_schema and ffi_ok and type(event_data) == "cdata" then
            local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
            if pkt_data then
                print(string.format("[AVRO_VERIFY] x=%.3f y=%.3f z=%.3f",
                    tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
                ns.verified = true
                return CFL_TERMINATE
            end
        end
    end
    return CFL_CONTINUE
end

M.AVRO_VERIFY_CONST_PACKET = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return CFL_CONTINUE end

    if event_type == defs.CFL_EVENT_TYPE_STREAMING_DATA and event_id == ns.event_id then
        load_schemas()
        if stream_schema and ffi_ok and type(event_data) == "cdata" then
            local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
            if pkt_data then
                print(string.format("[AVRO_VERIFY_CONST] x=%.3f y=%.3f z=%.3f",
                    tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
                ns.verified = true
                return CFL_TERMINATE
            end
        end
    end
    return CFL_CONTINUE
end

M.SM_EVENT_FILTERING_INIT = function(handle, node_idx)
    local ns = common.alloc_node_state(handle, node_idx)
    local nd = common.get_node_data(handle, node_idx)
    if nd and nd.event_name then
        ns.event_id = handle.flash_handle.event_strings and handle.flash_handle.event_strings[nd.event_name]
    end
end

-- ============================================================================
-- STREAMING PACKET FUNCTIONS
-- ============================================================================

-- PACKET_GENERATOR: one-shot that creates and emits an accelerometer packet
M.PACKET_GENERATOR = function(handle, node_idx)
    load_schemas()
    if not stream_schema or not ffi_ok then return end

    local nd = common.get_node_data(handle, node_idx)
    if not nd then return end
    local outport = nd.outport
    if not outport then return end

    -- Create and fill packet
    local pkt = stream_schema.new_packet("accelerometer_reading")
    stream_schema.packet_init(pkt, "accelerometer_reading", node_idx)
    pkt.data.x = math.random() * 1.0
    pkt.data.y = math.random() * 1.0
    pkt.data.z = 9.81

    -- Emit via CFL event queue
    local target = nd.event_column or handle.kb_start_index or 0
    -- Resolve original index to final if needed
    if handle.flash_handle.original_to_final and handle.flash_handle.original_to_final[target] then
        target = handle.flash_handle.original_to_final[target]
    end
    streaming.send_streaming_event(handle, target, outport.event_id, pkt)
end

-- PACKET_FILTER: boolean — pass if x <= threshold
M.PACKET_FILTER = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end
    load_schemas()
    if not stream_schema or not ffi_ok or event_data == nil then return true end
    if type(event_data) ~= "cdata" then return true end

    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then return true end

    local nd = common.get_node_data(handle, node_idx)
    local threshold = nd and nd.aux_data and nd.aux_data.x or 0.5
    if pkt_data.x > threshold then
        return false  -- block
    end
    return true  -- pass
end

-- PACKET_TAP: boolean — log packet
M.PACKET_TAP = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
        return false
    end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end

    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if pkt_data then
        local nd = common.get_node_data(handle, node_idx)
        local msg = nd and nd.aux_data and nd.aux_data.log_message or "tap"
        print(string.format("[TAP] %s: x=%.3f y=%.3f z=%.3f", msg, tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- PACKET_TRANSFORM: boolean — accumulate and average, then emit filtered packet
M.PACKET_TRANSFORM = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT then
        local ns = common.alloc_node_state(handle, node_idx)
        local nd = common.get_node_data(handle, node_idx)
        ns.sum_x, ns.sum_y, ns.sum_z = 0, 0, 0
        ns.sum_index = 0
        ns.sum_count = nd and nd.aux_data and nd.aux_data.average or 5
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end

    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end

    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then return true end

    local ns = common.get_node_state(handle, node_idx)
    if not ns then return true end

    ns.sum_x = ns.sum_x + tonumber(pkt_data.x)
    ns.sum_y = ns.sum_y + tonumber(pkt_data.y)
    ns.sum_z = ns.sum_z + tonumber(pkt_data.z)
    ns.sum_index = ns.sum_index + 1

    if ns.sum_index >= ns.sum_count then
        -- Emit averaged packet on outport
        local nd = common.get_node_data(handle, node_idx)
        if nd and nd.outport and stream_schema then
            local out_pkt = stream_schema.new_packet("accelerometer_reading_filtered")
            stream_schema.packet_init(out_pkt, "accelerometer_reading_filtered", node_idx)
            out_pkt.data.x = ns.sum_x / ns.sum_count
            out_pkt.data.y = ns.sum_y / ns.sum_count
            out_pkt.data.z = ns.sum_z / ns.sum_count

            local target = nd.output_event_column_id or handle.kb_start_index or 0
            if handle.flash_handle.original_to_final and handle.flash_handle.original_to_final[target] then
                target = handle.flash_handle.original_to_final[target]
            end
            streaming.send_streaming_event(handle, target, nd.output_event_id, out_pkt)
        end
        ns.sum_x, ns.sum_y, ns.sum_z = 0, 0, 0
        ns.sum_index = 0
    end
    return true
end

-- PACKET_SINK_A: boolean — consume raw packets
M.PACKET_SINK_A = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if pkt_data then
        print(string.format("[SINK_A] raw: x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- PACKET_SINK_B: boolean — consume filtered packets
M.PACKET_SINK_B = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading_filtered")
    if pkt_data then
        print(string.format("[SINK_B] filtered: x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- PACKET_COLLECTOR: boolean — accept/reject packet for collector
M.PACKET_COLLECTOR = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then return true end

    local ns = common.get_node_state(handle, node_idx)
    local port = event_type or 0  -- collect passes port index as event_type
    local count = ns and ns.container_count or 0
    local capacity = ns and ns.container_capacity or 3
    local x = tonumber(pkt_data.x)

    if x < 0.05 then
        print(string.format("collector: evaluating packet from port %d (x=%.3f)", port - 1, x))
        print(string.format("collector: REJECTED (x too low)"))
        return false
    end
    print(string.format("collector: evaluating packet from port %d (x=%.3f)", port - 1, x))
    print(string.format("collector: ACCEPTED (count will be %d/%d)", count + 1, capacity))
    return true
end

-- PACKET_COLLECTOR_SINK: boolean — consume collected packet container
M.PACKET_COLLECTOR_SINK = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then return false end
    load_schemas()
    local nd = common.get_node_data(handle, node_idx)
    local aux = nd and nd.aux_data or {}
    local msg = aux.sink_message or "collected packet received"

    if type(event_data) == "table" and event_data.count then
        print(string.format("collector_sink [%s]: received %d packets", msg, event_data.count))
        if stream_schema and ffi_ok then
            for i = 1, event_data.count do
                local pkt = event_data.packets[i]
                local port = event_data.port_indices[i] or 0
                if type(pkt) == "cdata" then
                    local d = stream_schema.packet_verify(pkt, "accelerometer_reading")
                    if d then
                        print(string.format("  [%d] port=%d, x=%.3f, y=%.3f, z=%.3f",
                            i-1, port-1, tonumber(d.x), tonumber(d.y), tonumber(d.z)))
                    end
                end
            end
        end
    end
    return true
end

-- PACKET_VERIFY_X_RANGE: boolean — verify x in [min_x, max_x]
M.PACKET_VERIFY_X_RANGE = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    if event_id == CFL_INIT_EVENT then
        local nd = common.get_node_data(handle, node_idx)
        local aux = nd and nd.fn_data and nd.fn_data.aux_data or {}
        ns.verify_min_x = aux.min_x or 0.0
        ns.verify_max_x = aux.max_x or 1.0
        print(string.format("verify_x_range: initialized with range [%.3f, %.3f]",
            ns.verify_min_x, ns.verify_max_x))
        return true
    end
    if event_id == CFL_TERMINATE_EVENT then return true end

    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return false end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then
        print("verify_x_range: packet decode failed")
        return false
    end

    local x = tonumber(pkt_data.x)
    if x < ns.verify_min_x or x > ns.verify_max_x then
        print(string.format("verify_x_range: FAILED - x=%.3f not in range [%.3f, %.3f] -> RESET",
            x, ns.verify_min_x, ns.verify_max_x))
        return false
    end
    print(string.format("verify_x_range: PASSED - x=%.3f in range [%.3f, %.3f]",
        x, ns.verify_min_x, ns.verify_max_x))
    return true
end

-- PACKET_VERIFIED_SINK: boolean — verify then consume
M.PACKET_VERIFIED_SINK = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if pkt_data then
        print(string.format("[VERIFIED_SINK] x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- ============================================================================
-- BOOLEAN FUNCTIONS
-- ============================================================================

M.WHILE_TEST = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then return false end

    if event_id == CFL_INIT_EVENT then
        local nd = common.get_node_data(handle, node_idx)
        ns.loop_count = nd and nd.user_data and nd.user_data.count or 0
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if (ns.current_iteration or 0) >= ns.loop_count then
        return false
    end
    return true
end

M.CATCH_ALL_EXCEPTION = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then ns = common.alloc_node_state(handle, node_idx) end

    if event_id == CFL_INIT_EVENT then
        local nd = common.get_node_data(handle, node_idx)
        ns.aux_data = nd and nd.column_data and nd.column_data.aux_data
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        print("*********** catch_all_exception_boolean_fn ***********")
        print("Raise exception event")
        print(string.format("Aux data: %s", tostring(ns.aux_data)))
        print(string.format("original node id: %s", tostring(event_data)))
        print("catch the exception")
        print("*********** catch_all_exception_boolean_fn ***********")
        return true
    end
    return false
end

M.EXCEPTION_FILTER = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then ns = common.alloc_node_state(handle, node_idx) end

    if event_id == CFL_INIT_EVENT then
        local nd = common.get_node_data(handle, node_idx)
        ns.exception_filter_data = nd and nd.column_data
            and nd.column_data.aux_function_data
            and nd.column_data.aux_function_data.exception_filter_data
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        print("*********** Exception filter event function ***********")
        print("Exception filter event function")
        print(string.format("Raise exception originating node %s %s",
            tostring(event_data), tostring(ns.exception_filter_data)))
        print(string.format("exception_type: %s", tostring(ns.exception_type)))
        print("Returning false")
        print("*********** Exception filter event function ***********")
        return false
    end
    return false
end

M.USER_SKIP_CONDITION = function(handle, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if not ns then ns = common.alloc_node_state(handle, node_idx) end

    if event_id == CFL_INIT_EVENT then
        local node = handle.flash_handle.nodes[node_idx]
        ns.parent_node_id = node and node.parent_index
        local nd = common.get_node_data(handle, node_idx)
        ns.skip_condition_message = nd and nd.column_data
            and nd.column_data.skip_condition_data
            and nd.column_data.skip_condition_data.skip_condition_data
        return false
    end
    if event_id == CFL_TERMINATE_EVENT then return false end

    -- Walk up to find exception catch parent
    local exc_id = common.find_parent_exception_node(handle, node_idx)
    local step_state = 0
    if exc_id then
        local parent_ns = common.get_node_state(handle, exc_id)
        if parent_ns then
            step_state = parent_ns.step_count or 0
        end
    end
    print("*********** Recovery step check ***********")
    print(string.format("Recovery step message: %s", tostring(ns.skip_condition_message)))
    print(string.format("Recovery step state: %d", step_state))
    print("*********** Recovery step check ***********")
    return true
end

M.DRONE_CONTROL_EXCEPTION_CATCH = function(handle, node_idx, event_type, event_id, event_data)
    if event_id == CFL_INIT_EVENT then return false end
    if event_id == CFL_TERMINATE_EVENT then return false end
    if event_id == CFL_RAISE_EXCEPTION_EVENT then
        print("*********** catch_all_exception_boolean_fn ***********")
        print("Raise exception event")
        print(string.format("original node id: %s", tostring(event_data)))
        print("raise the exception to parent node")
        print("*********** catch_all_exception_boolean_fn ***********")
        return false
    end
    return false
end

-- ============================================================================
-- MAIN FUNCTIONS
-- ============================================================================

M.SM_EVENT_FILTERING_MAIN = function(handle, bool_fn_idx, node_idx, event_type, event_id, event_data)
    local ns = common.get_node_state(handle, node_idx)
    if ns and event_id == ns.event_id then
        return CFL_CONTINUE
    end
    return CFL_CONTINUE
end

-- ============================================================================
-- DRONE CONTROL / CONTROLLED NODE FUNCTIONS
-- ============================================================================

M.UPDATE_FLY_STRAIGHT_FINAL = function(handle, node_idx) end
M.UPDATE_FLY_ARC_FINAL      = function(handle, node_idx) end
M.UPDATE_FLY_UP_FINAL       = function(handle, node_idx) end
M.UPDATE_FLY_DOWN_FINAL     = function(handle, node_idx) end

-- Client booleans: on response event return true (command complete)
local function make_on_fly_complete(fn_name)
    return function(handle, node_idx, event_type, event_id, event_data)
        if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
            return false
        end
        local ns = common.get_node_state(handle, node_idx)
        if ns and ns.response_port and event_id == ns.response_port.event_id then
            print(string.format("%s: response successful", fn_name))
            return true
        end
        return false
    end
end

M.ON_FLY_STRAIGHT_COMPLETE = make_on_fly_complete("on_fly_straight_complete_boolean_fn")
M.ON_FLY_ARC_COMPLETE      = make_on_fly_complete("on_fly_arc_complete_boolean_fn")
M.ON_FLY_UP_COMPLETE       = make_on_fly_complete("on_fly_up_complete_boolean_fn")
M.ON_FLY_DOWN_COMPLETE     = make_on_fly_complete("on_fly_down_complete_boolean_fn")

-- Server booleans: accept request
local function make_fly_monitor(name)
    return function(handle, node_idx, event_type, event_id, event_data)
        if event_id == CFL_INIT_EVENT or event_id == CFL_TERMINATE_EVENT then
            return false
        end
        return true
    end
end

M.FLY_STRAIGHT_MONITOR = make_fly_monitor("fly_straight")
M.FLY_ARC_MONITOR      = make_fly_monitor("fly_arc")
M.FLY_UP_MONITOR       = make_fly_monitor("fly_up")
M.FLY_DOWN_MONITOR     = make_fly_monitor("fly_down")

return M
