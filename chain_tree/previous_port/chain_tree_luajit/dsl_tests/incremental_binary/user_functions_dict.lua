-- user_functions_dict.lua — user functions for dict-based runtime
-- Ported from user_functions.lua (C-record style) to dict style

local common = require("ct_common")
local defs   = require("ct_definitions")

local M = { main = {}, one_shot = {}, boolean = {} }

-- ============================================================================
-- ONE-SHOT FUNCTIONS
-- ============================================================================

M.one_shot.ACTIVATE_VALVE = function(handle, node)
    local state = node.node_dict and node.node_dict.state
    if state == "open" then
        print("Valve is open")
    end
end

M.one_shot.WAIT_FOR_EVENT_ERROR = function(handle, node)
    local node_id = node.label_dict.ltree_name
    print(string.format("wait_for_event_error_one_shot_fn node: %s", node_id))
end

M.one_shot.VERIFY_ERROR = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    local msg = ns and ns.error_data and ns.error_data.failure_data
    print(string.format("error_message: %s", tostring(msg)))
end

M.one_shot.INITIALIZE_SEQUENCE = function(handle, node)
    -- no-op
end

M.one_shot.DISPLAY_SEQUENCE_TILL_RESULT = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    local msg = node.node_dict and node.node_dict.column_data
        and node.node_dict.column_data.user_data
        and node.node_dict.column_data.user_data.message
    print(string.format("display_sequence_till_result_one_shot_fn message: %s", tostring(msg)))
    if ns then
        local st = ns.sequence_type == "pass" and 0 or 1
        local sr = ns.final_status == true and 1 or 0
        print(string.format("sequence_type: %d", st))
        print(string.format("sequence_result: %d", sr))
        -- Print per-child results
        if ns.sequence_results then
            for idx, result in pairs(ns.sequence_results) do
                local children = node.label_dict.links or {}
                local child_id = children[idx + 1]
                local child_num = child_id and handle.ltree_to_index and handle.ltree_to_index[child_id] or "?"
                -- Find the mark node inside this child
                if child_id and handle.nodes[child_id] then
                    local child_links = handle.nodes[child_id].label_dict.links or {}
                    for _, leaf_id in ipairs(child_links) do
                        local leaf = handle.nodes[leaf_id]
                        if leaf and leaf.label_dict.initialization_function_name == "CFL_MARK_SEQUENCE" then
                            local mark_num = handle.ltree_to_index and handle.ltree_to_index[leaf_id] or "?"
                            local r = result and 1 or 0
                            print(string.format("node_index: [%s] sequence_result: %d", tostring(mark_num), r))
                            break
                        end
                    end
                end
            end
        end
    end
end

M.one_shot.DISPLAY_SEQUENCE_RESULT = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if ns and ns.try_node_indexes then
        print(string.format("try_node_count: %d", #ns.try_node_indexes))
        for i, tid in ipairs(ns.try_node_indexes) do
            print(string.format("try_node_indexes[%d]: %s", i-1, tostring(tid)))
        end
    end
end

M.one_shot.DISPLAY_FAILURE_WINDOW_RESULT = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if ns then
        print(string.format("failed_link_index: %s", tostring(ns.failed_link_index)))
    end
    local uplink = node.node_dict and node.node_dict.column_data
        and node.node_dict.column_data.user_data
        and node.node_dict.column_data.user_data.uplink_node_id
    print(string.format("uplink_node_id: %s if communicating with uplink node", tostring(uplink)))
end

M.one_shot.WATCH_DOG_TIME_OUT = function(handle, node)
    local nd = node.node_dict or {}
    local reset = nd.wd_reset
    local msg = nd.wd_fn_data and nd.wd_fn_data.message
    print(string.format("watch_dog_time_out_one_shot_fn reset: %s", tostring(reset)))
    print(string.format("watch_dog_time_out_one_shot_fn message: %s", tostring(msg)))
end

M.one_shot.EXCEPTION_LOGGING = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then ns = common.alloc_node_state(handle, node_id) end

    if not ns.logging_data then
        local nd = node.node_dict or {}
        ns.logging_data = nd.column_data
            and nd.column_data.logging_function_data
            and nd.column_data.logging_function_data.logging_function_data
    end

    print("*********** exception_logging_one_shot_fn ***********")
    print(string.format("original_node_id: %s", tostring(ns.original_node_id)))
    print(string.format("logging_data: %s", tostring(ns.logging_data)))
    print(string.format("exception_type: %s", tostring(ns.exception_type)))
    print("*********** exception_logging_one_shot_fn ***********")
end

M.one_shot.WHILE_BITMASK_FAILURE = function(handle, node)
    print(string.format("--------------------> while bitmask timeout: %s", node.label_dict.ltree_name))
end

M.one_shot.VERIFY_BITMASK_FAILURE = function(handle, node)
    print(string.format("--------------------> verify bitmask failure: %s", node.label_dict.ltree_name))
end

M.one_shot.WAIT_FOR_TEST_COMPLETE_ERROR = function(handle, node)
    print(string.format("--------------------> wait for test complete error: %s", node.label_dict.ltree_name))
end

M.one_shot.VERIFY_TESTS_ACTIVE_ERROR = function(handle, node)
    print(string.format("--------------------> verify tests active error: %s", node.label_dict.ltree_name))
end

-- ============================================================================
-- BOOLEAN FUNCTIONS
-- ============================================================================

M.boolean.WHILE_TEST = function(handle, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then return false end

    if event_id == defs.CFL_INIT_EVENT then
        ns.loop_count = node.node_dict and node.node_dict.user_data
            and node.node_dict.user_data.count or 0
        return false
    end
    if event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    if (ns.current_iteration or 0) >= ns.loop_count then
        return false
    end
    return true
end

M.boolean.CATCH_ALL_EXCEPTION = function(handle, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then ns = common.alloc_node_state(handle, node_id) end

    if event_id == defs.CFL_INIT_EVENT then
        local nd = node.node_dict or {}
        ns.aux_data = nd.column_data and nd.column_data.aux_data
        return false
    end
    if event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    if event_id == defs.CFL_RAISE_EXCEPTION_EVENT then
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

M.boolean.EXCEPTION_FILTER = function(handle, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then ns = common.alloc_node_state(handle, node_id) end

    if event_id == defs.CFL_INIT_EVENT then
        local nd = node.node_dict or {}
        ns.exception_filter_data = nd.column_data
            and nd.column_data.aux_function_data
            and nd.column_data.aux_function_data.exception_filter_data
        return false
    end
    if event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    if event_id == defs.CFL_RAISE_EXCEPTION_EVENT then
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

M.boolean.USER_SKIP_CONDITION = function(handle, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then ns = common.alloc_node_state(handle, node_id) end

    if event_id == defs.CFL_INIT_EVENT then
        ns.parent_node_id = common.get_parent_id(node)
        local nd = node.node_dict or {}
        ns.skip_condition_message = nd.column_data
            and nd.column_data.skip_condition_data
            and nd.column_data.skip_condition_data.skip_condition_data
        return false
    end
    if event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    -- Read step_count from parent exception catch node
    local recovery_ns = common.get_node_state(handle, node_id)
    local parent_exception_id = nil
    -- Walk up from recovery node to find exception catch
    local pid = common.get_parent_id(node)
    while pid and handle.nodes[pid] do
        local p = handle.nodes[pid]
        local mfn = p.label_dict.main_function_name
        if mfn == "CFL_EXCEPTION_CATCH_MAIN" or mfn == "CFL_EXCEPTION_CATCH_ALL_MAIN" then
            parent_exception_id = pid
            break
        end
        pid = common.get_parent_id(p)
    end
    local step_state = 0
    if parent_exception_id then
        local parent_ns = common.get_node_state(handle, parent_exception_id)
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

M.boolean.DRONE_CONTROL_EXCEPTION_CATCH = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT then return false end
    if event_id == defs.CFL_TERMINATE_EVENT then return false end
    if event_id == defs.CFL_RAISE_EXCEPTION_EVENT then
        print("*********** catch_all_exception_boolean_fn ***********")
        print("Raise exception event")
        print(string.format("original node id: %s", tostring(event_data)))
        -- In dict runtime, event_data is an ltree string
        if event_data and handle.nodes[event_data] then
            local src = handle.nodes[event_data]
            local nd = src.node_dict or {}
            print(string.format("Exception ID: %s", tostring(nd.exception_id)))
            if nd.exception_data then
                for k, v in pairs(nd.exception_data) do
                    print(string.format("  %s: %s", tostring(k), tostring(v)))
                end
            end
        end
        print("raise the exception to parent node")
        print("*********** catch_all_exception_boolean_fn ***********")
        return false
    end
    return false
end

-- ============================================================================
-- MAIN FUNCTIONS
-- ============================================================================

M.main.SM_EVENT_FILTERING_MAIN = function(handle, bool_fn, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if ns and event_id == ns.event_id then
        return defs.CFL_CONTINUE
    end
    return defs.CFL_CONTINUE
end

-- ============================================================================
-- BLACKBOARD TEST FUNCTIONS
-- ============================================================================

M.one_shot.BB_INIT_FIELDS = function(handle, node)
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

M.one_shot.BB_VERIFY_BASIC_FIELDS = function(handle, node)
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

M.one_shot.BB_VERIFY_NESTED_FIELDS = function(handle, node)
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

M.one_shot.BB_VERIFY_CONST_RECORD = function(handle, node)
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

M.one_shot.BB_VERIFY_PTR64_FIELD = function(handle, node)
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
-- STREAMING PACKET FUNCTIONS (using FFI)
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

-- GENERATE_AVRO_PACKET: one-shot that creates a test packet and sends as event
M.one_shot.GENERATE_AVRO_PACKET = function(handle, node)
    load_schemas()
    if not stream_schema or not ffi_ok then return end
    local nd = node.node_dict or {}
    local pkt = stream_schema.new_packet("accelerometer_reading")
    stream_schema.packet_init(pkt, "accelerometer_reading", 0)
    pkt.data.x = 1.0; pkt.data.y = 2.0; pkt.data.z = 9.81
    -- Send to self column via event
    local target = nd.node_index
    if type(target) == "number" then
        -- resolve via idx_to_ltree if still integer
        target = handle.idx_to_ltree and handle.idx_to_ltree[target]
    end
    if target then
        table.insert(handle.event_queue, {
            node_id = target,
            event_id = nd.event_id,
            event_type = "streaming_data",
            event_data = pkt,
        })
    end
end

-- GENERATE_CONST_AVRO_PACKET: one-shot that sends a const packet as event
M.one_shot.GENERATE_CONST_AVRO_PACKET = function(handle, node)
    load_schemas()
    if not stream_schema or not ffi_ok then return end
    local nd = node.node_dict or {}
    local const_pkt = stream_schema.const_packets and stream_schema.const_packets.default_accel_reading
    if not const_pkt then return end
    -- Copy const packet to mutable
    local pkt = stream_schema.new_packet("accelerometer_reading")
    ffi.copy(pkt, const_pkt, ffi.sizeof(pkt))
    local target = nd.node_index
    if type(target) == "number" then
        target = handle.idx_to_ltree and handle.idx_to_ltree[target]
    end
    if target then
        table.insert(handle.event_queue, {
            node_id = target,
            event_id = nd.event_id,
            event_type = "streaming_data",
            event_data = pkt,
        })
    end
end

-- AVRO_VERIFY_PACKET_INIT: init for avro verify node
M.one_shot.AVRO_VERIFY_PACKET_INIT = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.alloc_node_state(handle, node_id)
    ns.event_id = node.node_dict and node.node_dict.event_id
    ns.verified = false
end

-- AVRO_VERIFY_CONST_PACKET_INIT: same
M.one_shot.AVRO_VERIFY_CONST_PACKET_INIT = function(handle, node)
    local node_id = node.label_dict.ltree_name
    local ns = common.alloc_node_state(handle, node_id)
    ns.event_id = node.node_dict and node.node_dict.event_id
    ns.verified = false
end

-- AVRO_VERIFY_PACKET: main fn that waits for packet event and verifies
M.main.AVRO_VERIFY_PACKET = function(handle, bool_fn, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then return defs.CFL_CONTINUE end

    if handle.current_event_type == "streaming_data" and event_id == ns.event_id then
        load_schemas()
        if stream_schema and ffi_ok and type(event_data) == "cdata" then
            local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
            if pkt_data then
                print(string.format("[AVRO_VERIFY] x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
                ns.verified = true
                return defs.CFL_TERMINATE
            end
        end
    end
    return defs.CFL_CONTINUE
end

-- AVRO_VERIFY_CONST_PACKET: same but for const packets
M.main.AVRO_VERIFY_CONST_PACKET = function(handle, bool_fn, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then return defs.CFL_CONTINUE end

    if handle.current_event_type == "streaming_data" and event_id == ns.event_id then
        load_schemas()
        if stream_schema and ffi_ok and type(event_data) == "cdata" then
            local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
            if pkt_data then
                print(string.format("[AVRO_VERIFY_CONST] x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
                ns.verified = true
                return defs.CFL_TERMINATE
            end
        end
    end
    return defs.CFL_CONTINUE
end

-- PACKET_GENERATOR: one-shot that creates and emits a packet
M.one_shot.PACKET_GENERATOR = function(handle, node)
    load_schemas()
    if not stream_schema or not ffi_ok then return end

    local nd = node.node_dict or {}
    local outport = nd.outport
    if not outport then return end

    -- Create and fill packet
    local pkt = stream_schema.new_packet("accelerometer_reading")
    stream_schema.packet_init(pkt, "accelerometer_reading", 0)
    pkt.data.x = math.random() * 1.0
    pkt.data.y = math.random() * 1.0
    pkt.data.z = 9.81

    -- Emit via event queue
    table.insert(handle.event_queue, {
        node_id = nd.event_column,
        event_id = outport.event_id,
        event_type = "streaming_data",
        event_data = pkt,
    })
end

-- PACKET_FILTER: boolean that checks packet fields
M.boolean.PACKET_FILTER = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    load_schemas()
    if not stream_schema or not ffi_ok or event_data == nil then return true end
    if type(event_data) ~= "cdata" then return true end

    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then return true end

    -- Filter: pass if x <= threshold
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    local threshold = node.node_dict and node.node_dict.aux_data and node.node_dict.aux_data.x or 0.5
    if pkt_data.x > threshold then
        return false  -- block
    end
    return true  -- pass
end

-- PACKET_TAP: boolean that logs packet
M.boolean.PACKET_TAP = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then
        return false
    end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end

    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if pkt_data then
        local msg = node.node_dict and node.node_dict.aux_data and node.node_dict.aux_data.log_message or "tap"
        print(string.format("[TAP] %s: x=%.3f y=%.3f z=%.3f", msg, tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- PACKET_TRANSFORM: accumulate and average
M.boolean.PACKET_TRANSFORM = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT then
        local node_id = node.label_dict.ltree_name
        local ns = common.alloc_node_state(handle, node_id)
        ns.sum_x, ns.sum_y, ns.sum_z = 0, 0, 0
        ns.sum_index = 0
        ns.sum_count = node.node_dict and node.node_dict.aux_data and node.node_dict.aux_data.average or 5
        return false
    end
    if event_id == defs.CFL_TERMINATE_EVENT then return false end

    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end

    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then return true end

    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then return true end

    ns.sum_x = ns.sum_x + tonumber(pkt_data.x)
    ns.sum_y = ns.sum_y + tonumber(pkt_data.y)
    ns.sum_z = ns.sum_z + tonumber(pkt_data.z)
    ns.sum_index = ns.sum_index + 1

    if ns.sum_index >= ns.sum_count then
        -- Emit averaged packet
        local out_ns = common.get_node_state(handle, node_id)
        local nd = node.node_dict or {}
        if nd.outport and stream_schema then
            local out_pkt = stream_schema.new_packet("accelerometer_reading_filtered")
            stream_schema.packet_init(out_pkt, "accelerometer_reading_filtered", 0)
            out_pkt.data.x = ns.sum_x / ns.sum_count
            out_pkt.data.y = ns.sum_y / ns.sum_count
            out_pkt.data.z = ns.sum_z / ns.sum_count

            table.insert(handle.event_queue, {
                node_id = nd.output_event_column_id,
                event_id = nd.output_event_id,
                event_type = "streaming_data",
                event_data = out_pkt,
            })
        end
        ns.sum_x, ns.sum_y, ns.sum_z = 0, 0, 0
        ns.sum_index = 0
    end
    return true
end

-- PACKET_SINK_A: consume raw packets
M.boolean.PACKET_SINK_A = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if pkt_data then
        print(string.format("[SINK_A] raw: x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- PACKET_SINK_B: consume filtered packets
M.boolean.PACKET_SINK_B = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading_filtered")
    if pkt_data then
        print(string.format("[SINK_B] filtered: x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- PACKET_COLLECTOR: accept packet into collector
M.boolean.PACKET_COLLECTOR = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if not pkt_data then return true end
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    local port = (ns and ns.current_port_index or 1) - 1  -- 0-based for display
    local count = ns and ns.container_count or 0
    local capacity = ns and ns.container_capacity or 3
    local x = tonumber(pkt_data.x)
    if x < 0.05 then
        print(string.format("collector: evaluating packet from port %d (x=%.3f)", port, x))
        print(string.format("collector: REJECTED (x too low)"))
        return false
    end
    print(string.format("collector: evaluating packet from port %d (x=%.3f)", port, x))
    print(string.format("collector: ACCEPTED (count will be %d/%d)", count + 1, capacity))
    return true
end

-- PACKET_COLLECTOR_SINK: consume collected packet container
M.boolean.PACKET_COLLECTOR_SINK = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then return false end
    load_schemas()
    local nd = node.node_dict and node.node_dict.aux_data or {}
    local msg = nd.sink_message or "collected packet received"
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

-- PACKET_VERIFY_X_RANGE: verify packet x is within [min_x, max_x]
M.boolean.PACKET_VERIFY_X_RANGE = function(handle, node, event_id, event_data)
    local node_id = node.label_dict.ltree_name
    local ns = common.get_node_state(handle, node_id)
    if not ns then return false end

    if event_id == defs.CFL_INIT_EVENT then
        -- Read limits from fn_data.aux_data (set by CFL_VERIFY_INIT)
        local aux = ns.fn_data and ns.fn_data.aux_data or {}
        ns.verify_min_x = aux.min_x or 0.0
        ns.verify_max_x = aux.max_x or 1.0
        print(string.format("verify_x_range: initialized with range [%.3f, %.3f]",
            ns.verify_min_x, ns.verify_max_x))
        return true
    end

    if event_id == defs.CFL_TERMINATE_EVENT then
        return true
    end

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

-- PACKET_VERIFIED_SINK: verify packet fields then consume
M.boolean.PACKET_VERIFIED_SINK = function(handle, node, event_id, event_data)
    if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then return false end
    load_schemas()
    if not stream_schema or not ffi_ok or type(event_data) ~= "cdata" then return true end
    local pkt_data = stream_schema.packet_verify(event_data, "accelerometer_reading")
    if pkt_data then
        print(string.format("[VERIFIED_SINK] x=%.3f y=%.3f z=%.3f", tonumber(pkt_data.x), tonumber(pkt_data.y), tonumber(pkt_data.z)))
    end
    return true
end

-- ============================================================================
-- DRONE CONTROL / CONTROLLED NODE STUBS (no-ops)
-- ============================================================================

-- UPDATE_FLY_*_FINAL: finalization one-shots (no-ops in C reference)
M.one_shot.UPDATE_FLY_STRAIGHT_FINAL = function(handle, node) end
M.one_shot.UPDATE_FLY_ARC_FINAL      = function(handle, node) end
M.one_shot.UPDATE_FLY_UP_FINAL       = function(handle, node) end
M.one_shot.UPDATE_FLY_DOWN_FINAL     = function(handle, node) end

-- ON_FLY_*_COMPLETE: client booleans
-- On INIT: set up request packet data from node_dict.aux_data
-- On response event: return true (command complete)
local function make_on_fly_complete(fn_name)
    return function(handle, node, event_id, event_data)
        local node_id = node.label_dict.ltree_name
        local ns = common.get_node_state(handle, node_id)
        if not ns then return false end

        if event_id == defs.CFL_INIT_EVENT then
            return false
        end
        if event_id == defs.CFL_TERMINATE_EVENT then
            return false
        end

        -- Response received — check if this is our response event
        if ns.response_port and event_id == ns.response_port.event_id then
            print(string.format("%s: response successful", fn_name))
            return true
        end

        return false
    end
end

M.boolean.ON_FLY_STRAIGHT_COMPLETE = make_on_fly_complete("on_fly_straight_complete_boolean_fn")
M.boolean.ON_FLY_ARC_COMPLETE      = make_on_fly_complete("on_fly_arc_complete_boolean_fn")
M.boolean.ON_FLY_UP_COMPLETE       = make_on_fly_complete("on_fly_up_complete_boolean_fn")
M.boolean.ON_FLY_DOWN_COMPLETE     = make_on_fly_complete("on_fly_down_complete_boolean_fn")

-- fly_*_monitor: server booleans
-- On request event: return true (accept request) — no print in C reference
local function make_fly_monitor(name)
    return function(handle, node, event_id, event_data)
        if event_id == defs.CFL_INIT_EVENT or event_id == defs.CFL_TERMINATE_EVENT then
            return false
        end
        return true
    end
end

M.boolean.fly_straight_monitor = make_fly_monitor("fly_straight")
M.boolean.fly_arc_monitor      = make_fly_monitor("fly_arc")
M.boolean.fly_up_monitor       = make_fly_monitor("fly_up")
M.boolean.fly_down_monitor     = make_fly_monitor("fly_down")

return M
