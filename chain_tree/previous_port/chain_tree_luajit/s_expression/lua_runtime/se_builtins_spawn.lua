-- ============================================================================
-- se_builtins_spawn.lua
-- Mirrors s_engine_builtins_spawn.h
--
-- Child tree spawning, ticking, and dictionary-driven dispatch.
-- All main functions: fn(inst, node, event_id, event_data) -> result_code
--
-- In Lua, child trees are full se_runtime instances (created with
-- se_runtime.new_instance). Tree lookup uses mod.trees_by_hash[hash].
--
-- Dictionaries are plain Lua tables stored in the blackboard.
-- Keys are hashes (numbers) or strings; values are Lua functions.
-- ============================================================================

local se_runtime = require("se_runtime")

local SE_EVENT_INIT        = se_runtime.SE_EVENT_INIT
local SE_EVENT_TERMINATE   = se_runtime.SE_EVENT_TERMINATE
local SE_EVENT_TICK        = se_runtime.SE_EVENT_TICK
local SE_PIPELINE_CONTINUE = se_runtime.SE_PIPELINE_CONTINUE
local SE_PIPELINE_DISABLE  = se_runtime.SE_PIPELINE_DISABLE
local SE_PIPELINE_TERMINATE= se_runtime.SE_PIPELINE_TERMINATE
local SE_PIPELINE_RESET    = se_runtime.SE_PIPELINE_RESET

local get_ns               = se_runtime.get_ns
local param_int            = se_runtime.param_int
local param_str            = se_runtime.param_str
local param_field_name     = se_runtime.param_field_name
local field_get            = se_runtime.field_get
local field_set            = se_runtime.field_set
local get_state            = se_runtime.get_state
local set_state            = se_runtime.set_state
local get_user_u64         = se_runtime.get_user_u64
local set_user_u64         = se_runtime.set_user_u64
local FLAG_ACTIVE = 0x01
local M = {}

-- ============================================================================
-- Internal: result_is_complete
-- Mirrors the C static helper of the same name.
-- ============================================================================
local function result_is_complete(result)
    return result ~= SE_PIPELINE_CONTINUE and result ~= SE_PIPELINE_DISABLE
end

-- ============================================================================
-- Internal: tick_with_event_queue
-- Tick a child instance then drain its internal event queue.
-- Mirrors the C tick_with_event_queue helper exactly.
-- ============================================================================
local function tick_with_event_queue(child, event_id, event_data)
    local result = se_runtime.tick_once(child, event_id, event_data)

    local event_count = se_runtime.event_count(child)
    while event_count > 0 and not result_is_complete(result) do
        local tick_type, ev_id, ev_data = se_runtime.event_pop(child)

        local saved_tick_type = child.tick_type
        child.tick_type = tick_type

        local event_result = se_runtime.tick_once(child, ev_id, ev_data)

        child.tick_type = saved_tick_type

        if result_is_complete(event_result) then
            result = event_result
            break
        end

        event_count = se_runtime.event_count(child)
    end

    return result
end

-- ============================================================================
-- Internal: resolve tree by hash
-- ============================================================================
local function resolve_tree(inst, node, param_idx)
    local p = (node.params or {})[param_idx]
    assert(p, "spawn: missing tree hash param at index " .. param_idx)
    local hash = (type(p.value) == "table") and p.value.hash or p.value
    local name = inst.mod.trees_by_hash[hash]
    assert(name, string.format("spawn: unknown tree hash 0x%08x", hash))
    return name
end

-- ============================================================================
-- SE_SPAWN_AND_TICK_TREE  (pt_m_call -- pointer slot stores child instance)
-- Creates a child tree, forwards ticks to it, and drains parent's event queue.
-- Lua tree layout:
--   params[1] = str_hash  tree name hash
--   params[2] = uint      stack_size (0 = no stack)
-- Pointer slot: .ptr holds child instance
--
-- INIT or state==0:
--   create child tree, optional stack, initial tick(0), set state=1
-- TERMINATE:
--   free child (nil slot)
-- TICK:
--   tick child with event_queue drain
--   drain parent's own event queue, forwarding each event to child
--   if result_is_complete: free child
-- ----------------------------------------------------------------------------
M.se_spawn_and_tick_tree = function(inst, node, event_id, event_data)
    assert(#(node.params or {}) >= 2,
        "se_spawn_and_tick_tree: requires [str_hash tree] [uint stack_size]")

    local slot  = inst.pointer_array[inst.pointer_base]
    local state = get_state(inst, node)

    -- INIT or first-run
    if event_id == SE_EVENT_INIT or state == 0 then
        local tree_name  = resolve_tree(inst, node, 1)
        local stack_size = param_int(node, 2)
        local child = se_runtime.new_instance(inst.mod, tree_name)

        if stack_size > 0 then
            child.stack = require("se_stack").new_stack(stack_size)
        end

        slot.ptr = child
        tick_with_event_queue(child, 0, nil)  -- initial tick, event_id=0
        set_state(inst, node, 1)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        slot.ptr = nil
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: forward event to child, then drain parent's event queue
    local child = slot.ptr
    assert(child, "se_spawn_and_tick_tree: child tree is nil")

    local result = tick_with_event_queue(child, event_id, event_data)

    -- Drain parent's own event queue and forward each event to child
    -- (mirrors the second while loop in the C implementation)
    local eq_count = se_runtime.event_count(inst)
    while eq_count > 0 and not result_is_complete(result) do
        local tick_type, ev_id, ev_data = se_runtime.event_pop(inst)
        local saved_tick_type = child.tick_type
        child.tick_type = tick_type
        result = tick_with_event_queue(child, ev_id, ev_data)
        child.tick_type = saved_tick_type
        eq_count = se_runtime.event_count(inst)
    end

    if result_is_complete(result) then
        slot.ptr = nil
    end

    return result
end

-- ============================================================================
-- SE_SPAWN_TREE  (pt_m_call)
-- Spawns a child tree; stores reference in a blackboard field.
-- The child is ticked separately via SE_TICK_TREE.
-- Lua tree layout:
--   params[1] = field_ref  blackboard PTR field to store child instance
--   params[2] = str_hash   tree name hash
--   params[3] = uint       stack_size
--
-- INIT:
--   create child, init node states, store in blackboard + user_ptr slot
-- TERMINATE:
--   terminate child, free, clear blackboard field
-- TICK:
--   SE_PIPELINE_CONTINUE (this node does not tick the child)
-- ============================================================================
M.se_spawn_tree = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        assert(#(node.params or {}) >= 3,
            "se_spawn_tree: requires [field_ref ptr] [str_hash tree] [uint stack_size]")

        local field_name = param_field_name(node, 1)
        local tree_name  = resolve_tree(inst, node, 2)
        local stack_size = param_int(node, 3)

        local child = se_runtime.new_instance(inst.mod, tree_name)

        if stack_size > 0 then
            child.stack = require("se_stack").new_stack(stack_size)
        end

        -- Cache in pointer slot for fast TERMINATE access
        inst.pointer_array[inst.pointer_base].ptr = child

        -- Store in blackboard field (by field name)
        inst.blackboard[field_name] = child

        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        local child = inst.pointer_array[inst.pointer_base].ptr
        if child then
            -- Send terminate to child tree
            se_runtime.tick_once(child, SE_EVENT_TERMINATE, nil)
            -- Clear blackboard field
            local field_name = param_field_name(node, 1)
            inst.blackboard[field_name] = nil
            inst.pointer_array[inst.pointer_base].ptr = nil
        end
        return SE_PIPELINE_CONTINUE
    end

    return SE_PIPELINE_CONTINUE
end

-- ============================================================================
-- SE_TICK_TREE  (m_call)
-- Ticks a child tree stored in a blackboard field.
-- Lua tree layout:
--   params[1] = field_ref  blackboard field holding child instance
--
-- INIT:     full reset of child tree (reset all node states + event queue)
-- TERMINATE: send terminate event to child
-- TICK:     tick child and drain child's event queue
-- ============================================================================
M.se_tick_tree = function(inst, node, event_id, event_data)
    assert(#(node.params or {}) >= 1,
        "se_tick_tree: requires [field_ref tree_ptr]")

    local field_name = param_field_name(node, 1)
    local child = inst.blackboard[field_name]
    assert(child, "se_tick_tree: child tree is nil in field: " .. tostring(field_name))

    if event_id == SE_EVENT_INIT then
        -- Full reset: mirrors s_expr_node_full_reset
        for i = 0, child.node_count - 1 do
            local ns = child.node_states[i]
            ns.flags     = FLAG_ACTIVE  -- 0x01
            ns.state     = 0
            ns.user_data = 0
        end
        se_runtime.event_clear(child)
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        se_runtime.tick_once(child, SE_EVENT_TERMINATE, nil)
        return SE_PIPELINE_CONTINUE
    end

    -- TICK: tick child + drain its event queue
    local result = se_runtime.tick_once(child, event_id, event_data)

    -- Drain the child's event queue
    while se_runtime.event_count(child) > 0 do
        local q_tick_type, q_event_id, q_event_data = se_runtime.event_pop(child)
        result = se_runtime.tick_once(child, q_event_id, q_event_data)
    end

    return result
end

-- ============================================================================
-- SE_LOAD_FUNCTION  (io_call = ONESHOT)
-- io_call compiles as an oneshot: fn(inst, node) -- no event_id arg.
-- Runs once during tree INIT. Stores a closure over the child subtree
-- into the blackboard PTR64 field so SE_EXEC_FN can invoke it later.
--
-- Lua tree layout:
--   params[1] = field_ref  (blackboard field to store into)
--   children[1] = root of the function body subtree
-- ============================================================================
M.se_load_function = function(inst, node)
    local field_name = param_field_name(node, 1)
    assert(field_name, "se_load_function: missing field_ref param")

    -- child[1] is the function body subtree root
    local child = node.children and node.children[1]
    assert(child and child.node_index,
        "se_load_function: no child subtree to load")

    -- Store the child node table (invoke_any takes a node table, not an index)
    local child_node = child

    -- Build a closure that ticks the child subtree via invoke_any.
    local fn = function(calling_inst, _exec_node, eid, edata)
        return se_runtime.invoke_any(calling_inst, child_node, eid, edata)
    end

    inst.blackboard[field_name] = fn
end

-- ============================================================================
-- SE_EXEC_FN  (m_call)
-- Executes a Lua function stored in a blackboard field.
-- Lua tree layout:
--   params[1] = field_ref  (blackboard field holding fn)
--
-- INIT:     validate that field holds a callable; cache fn in node_state
-- TERMINATE: SE_PIPELINE_CONTINUE
-- TICK:     call the function; SE_PIPELINE_DISABLE -> SE_PIPELINE_CONTINUE
-- ============================================================================
M.se_exec_fn = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local field_name = param_field_name(node, 1)
        local fn = inst.blackboard[field_name]
        assert(type(fn) == "function",
            "se_exec_fn: blackboard field is not a function: " .. tostring(field_name))
        -- Cache the function reference on node state for fast TICK access
        get_ns(inst, node.node_index).cached_fn = fn
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    local fn = get_ns(inst, node.node_index).cached_fn
    assert(fn, "se_exec_fn: nil cached function")

    local result = fn(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE

    -- C: if (result == SE_PIPELINE_DISABLE) result = SE_PIPELINE_CONTINUE
    if result == SE_PIPELINE_DISABLE then
        result = SE_PIPELINE_CONTINUE
    end

    return result
end

-- ============================================================================
-- SE_EXEC_DICT_INTERNAL  (m_call)
-- Execute an entry from inst.current_dict by hash key.
-- Lua tree layout:
--   params[1] = str_hash  key hash
--
-- In Lua, dict values are Lua functions (fn(inst, node, event_id, event_data)).
-- inst.current_dict is set by se_exec_dict_dispatch / se_exec_dict_fn_ptr on INIT.
--
-- INIT/TERM: SE_PIPELINE_CONTINUE
-- TICK:      look up key, call the function
--            SE_PIPELINE_DISABLE -> SE_PIPELINE_CONTINUE
-- ============================================================================
M.se_exec_dict_internal = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT or event_id == SE_EVENT_TERMINATE then
        return SE_PIPELINE_CONTINUE
    end

    local dict = inst.current_dict
    assert(dict, "se_exec_dict_internal: no current_dict on instance")

    local p1 = (node.params or {})[1]
    assert(p1, "se_exec_dict_internal: missing key hash param")
    local key = (type(p1.value) == "table") and p1.value.hash or p1.value

    local entry = dict[key] or dict[tostring(key)]
    assert(entry, "se_exec_dict_internal: key not found: " .. tostring(key))
    assert(type(entry) == "function",
        "se_exec_dict_internal: dict value is not a function for key: " .. tostring(key))

    local result = entry(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE

    if result == SE_PIPELINE_DISABLE then
        result = SE_PIPELINE_CONTINUE
    end

    return result
end

-- ============================================================================
-- SE_EXEC_DICT_DISPATCH  (m_call)
-- Load dict from blackboard on INIT, then dispatch by compile-time key hash.
-- Lua tree layout:
--   params[1] = field_ref  (blackboard field holding the Lua dict table)
--   params[2] = str_hash   key hash to look up
--
-- INIT:     load dict from blackboard, store in inst.current_dict
-- TERMINATE: clear inst.current_dict
-- TICK:     look up key, call the function
-- ============================================================================
M.se_exec_dict_dispatch = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local field_name = param_field_name(node, 1)
        local dict = inst.blackboard[field_name]
        assert(dict and type(dict) == "table",
            "se_exec_dict_dispatch: field is not a table: " .. tostring(field_name))
        inst.current_dict = dict
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        inst.current_dict = nil
        return SE_PIPELINE_CONTINUE
    end

    local dict = inst.current_dict
    assert(dict, "se_exec_dict_dispatch: no current_dict on instance")

    local p2 = (node.params or {})[2]
    assert(p2, "se_exec_dict_dispatch: missing key hash param")
    local key = (type(p2.value) == "table") and p2.value.hash or p2.value

    local entry = dict[key] or dict[tostring(key)]
    assert(entry, "se_exec_dict_dispatch: key not found: " .. tostring(key))
    assert(type(entry) == "function", "se_exec_dict_dispatch: entry is not callable")

    local result = entry(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE
    if result == SE_PIPELINE_DISABLE then result = SE_PIPELINE_CONTINUE end
    return result
end

-- ============================================================================
-- SE_EXEC_DICT_FN_PTR  (m_call)
-- Like se_exec_dict_dispatch but key comes from a blackboard field at runtime.
-- Lua tree layout:
--   params[1] = field_ref  (blackboard field holding the Lua dict table)
--   params[2] = field_ref  (blackboard field holding the runtime key/hash)
--
-- INIT:     load dict from blackboard
-- TERMINATE: clear inst.current_dict
-- TICK:     read key from blackboard field, look up, call the function
-- ============================================================================
M.se_exec_dict_fn_ptr = function(inst, node, event_id, event_data)
    if event_id == SE_EVENT_INIT then
        local field_name = param_field_name(node, 1)
        local dict = inst.blackboard[field_name]
        assert(dict and type(dict) == "table",
            "se_exec_dict_fn_ptr: field is not a table: " .. tostring(field_name))
        inst.current_dict = dict
        return SE_PIPELINE_CONTINUE
    end

    if event_id == SE_EVENT_TERMINATE then
        inst.current_dict = nil
        return SE_PIPELINE_CONTINUE
    end

    local dict = inst.current_dict
    assert(dict, "se_exec_dict_fn_ptr: no current_dict on instance")

    -- Key comes from a blackboard field at runtime
    local key_field = param_field_name(node, 2)
    local key = inst.blackboard[key_field]
    assert(key ~= nil,
        "se_exec_dict_fn_ptr: key field is nil: " .. tostring(key_field))

    local entry = dict[key] or dict[tostring(key)]
    assert(entry, "se_exec_dict_fn_ptr: key not found: " .. tostring(key))
    assert(type(entry) == "function", "se_exec_dict_fn_ptr: entry is not callable")

    local result = entry(inst, node, event_id, event_data) or SE_PIPELINE_CONTINUE
    if result == SE_PIPELINE_DISABLE then result = SE_PIPELINE_CONTINUE end
    return result
end

-- Module constant (used by se_tick_tree full reset)


return M