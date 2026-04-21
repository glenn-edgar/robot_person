-- ============================================================================
-- cfl_event_queue.lua
-- ChainTree LuaJIT Runtime — dual-priority event queue
-- Mirrors cfl_event_queue.c ring buffer design
-- ============================================================================

local M = {}

local defs = require("cfl_definitions")

-- ============================================================================
-- Ring buffer (circular queue using modular arithmetic)
-- ============================================================================
local function ring_create(capacity)
    -- Round up to power of 2 (minimum 2)
    local cap = 2
    while cap < capacity do cap = cap * 2 end
    return {
        events   = {},
        head     = 0,
        tail     = 0,
        capacity = cap,
        mask     = cap - 1,
    }
end

local function ring_is_empty(ring)
    return ring.head == ring.tail
end

local function ring_is_full(ring)
    return ((ring.head + 1) % ring.capacity) == ring.tail
end

local function ring_count(ring)
    return (ring.head - ring.tail) % ring.capacity
end

local function ring_push(ring, event)
    assert(not ring_is_full(ring), "cfl_event_queue: ring full")
    ring.events[ring.head] = event
    ring.head = (ring.head + 1) % ring.capacity
end

local function ring_pop(ring)
    assert(not ring_is_empty(ring), "cfl_event_queue: ring empty")
    local event = ring.events[ring.tail]
    ring.events[ring.tail] = nil
    ring.tail = (ring.tail + 1) % ring.capacity
    return event
end

local function ring_peek(ring)
    assert(not ring_is_empty(ring), "cfl_event_queue: ring empty on peek")
    return ring.events[ring.tail]
end

local function ring_clear(ring)
    ring.head = 0
    ring.tail = 0
    -- let GC collect event tables
    for k in pairs(ring.events) do ring.events[k] = nil end
end

-- ============================================================================
-- Public API
-- ============================================================================

function M.create(high_size, low_size)
    return {
        high = ring_create(high_size or 8),
        low  = ring_create(low_size or 64),
        max_total_depth = 0,
        max_high_depth  = 0,
    }
end

function M.send(queue, priority, node_id, event_type, event_id, data)
    local event = {
        node_id    = node_id,
        event_type = event_type or defs.CFL_EVENT_TYPE_NULL,
        event_id   = event_id,
        data       = data,
    }

    local ring
    if priority == defs.CFL_EVENT_PRIORITY_HIGH then
        ring = queue.high
    else
        ring = queue.low
    end

    ring_push(ring, event)

    -- Update stats
    local hc = ring_count(queue.high)
    if hc > queue.max_high_depth then queue.max_high_depth = hc end
    local tc = hc + ring_count(queue.low)
    if tc > queue.max_total_depth then queue.max_total_depth = tc end
end

function M.pop(queue)
    if not ring_is_empty(queue.high) then
        return ring_pop(queue.high)
    end
    if not ring_is_empty(queue.low) then
        return ring_pop(queue.low)
    end
    return nil
end

function M.peek(queue)
    if not ring_is_empty(queue.high) then
        return ring_peek(queue.high)
    end
    if not ring_is_empty(queue.low) then
        return ring_peek(queue.low)
    end
    return nil
end

function M.clear(queue)
    ring_clear(queue.high)
    ring_clear(queue.low)
end

function M.total_count(queue)
    return ring_count(queue.high) + ring_count(queue.low)
end

function M.high_count(queue)
    return ring_count(queue.high)
end

function M.low_count(queue)
    return ring_count(queue.low)
end

-- Typed send helpers
function M.send_null(queue, priority, node_id, event_id)
    M.send(queue, priority, node_id, defs.CFL_EVENT_TYPE_NULL, event_id, nil)
end

function M.send_integer(queue, priority, node_id, event_id, value)
    M.send(queue, priority, node_id, defs.CFL_EVENT_TYPE_INT, event_id, value)
end

function M.send_float(queue, priority, node_id, event_id, value)
    M.send(queue, priority, node_id, defs.CFL_EVENT_TYPE_FLOAT, event_id, value)
end

function M.send_node_id(queue, priority, node_id, event_id, target_node)
    M.send(queue, priority, node_id, defs.CFL_EVENT_TYPE_NODE_ID, event_id, target_node)
end

return M
