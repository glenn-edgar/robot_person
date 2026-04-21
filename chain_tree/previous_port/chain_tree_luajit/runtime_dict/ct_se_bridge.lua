-- ============================================================================
-- ct_se_bridge.lua
-- Dict-based ChainTree Runtime — S-Expression Engine bridge
--
-- Ported from runtime/cfl_se_bridge.lua to dict-based runtime conventions.
--
-- Provides:
--   1. Module registry (create_registry, register_def, load_module,
--      find_module, unload_module)
--   2. ChainTree node functions (CFL_SE_MODULE_LOAD, CFL_SE_TREE_LOAD,
--      CFL_SE_TICK, CFL_SE_ENGINE init/main/term)
--   3. CFL-specific S-Engine builtins (CFL_LOG, CFL_ENABLE/DISABLE_CHILDREN,
--      CFL_SET/CLEAR_BITS, CFL_READ_BIT, CFL_S_BIT_*, CFL_WAIT_CHILD_DISABLED)
--
-- Dict-style conventions:
--   - node_id = node.label_dict.ltree_name (ltree string)
--   - node data via node.node_dict.field (direct table access)
--   - node state via common.alloc_node_state(handle, node_id) with ltree key
--   - blackboard: handle.blackboard[field_name]
--   - bitmask: handle.bitmask (integer, no shadow bitmask)
--   - timestamp: handle.timestamp
--   - event queue: table.insert(handle.event_queue, {...})
--
-- Function signatures:
--   Main:     fn(handle, bool_fn, node, event_id, event_data) -> return_code
--   One-shot: fn(handle, node) -> nil
--   Boolean:  fn(handle, node, event_id, event_data) -> boolean
-- ============================================================================

local M = {}

local bit  = require("bit")
local band, bor, bnot = bit.band, bit.bor, bit.bnot

local defs   = require("ct_definitions")
local common = require("ct_common")

-- Lazy-load to avoid circular requires
local engine
local function get_engine()
    if not engine then engine = require("ct_engine") end
    return engine
end

local se_runtime
local function get_se_runtime()
    if not se_runtime then se_runtime = require("se_runtime") end
    return se_runtime
end

-- Local aliases for frequently used constants
local CFL_CONTINUE         = defs.CFL_CONTINUE
local CFL_HALT             = defs.CFL_HALT
local CFL_TERMINATE        = defs.CFL_TERMINATE
local CFL_RESET            = defs.CFL_RESET
local CFL_DISABLE          = defs.CFL_DISABLE
local CFL_SKIP_CONTINUE    = defs.CFL_SKIP_CONTINUE
local CFL_TERMINATE_SYSTEM = defs.CFL_TERMINATE_SYSTEM
local CFL_TIMER_EVENT      = defs.CFL_TIMER_EVENT
local CFL_INIT_EVENT       = defs.CFL_INIT_EVENT
local CFL_TERMINATE_EVENT  = defs.CFL_TERMINATE_EVENT

-- Helper: get node_id (ltree string) from node table
local function nid(node)
    return node.label_dict.ltree_name
end

-- ============================================================================
-- MODULE REGISTRY
-- ============================================================================

function M.create_registry(handle)
    local reg = {
        defs    = {},   -- name -> { module_data_loader = fn, user_fns = table }
        loaded  = {},   -- name -> se_runtime mod object
        handle  = handle,
    }
    handle.se_registry = reg
    return reg
end

-- Pre-register a module definition (module_data table or loader function)
function M.register_def(reg, name, module_data_or_loader, user_fns)
    if type(module_data_or_loader) == "function" then
        reg.defs[name] = { loader = module_data_or_loader, user_fns = user_fns }
    else
        reg.defs[name] = { module_data = module_data_or_loader, user_fns = user_fns }
    end
end

-- Load a module: create se_runtime.new_module, register all builtins + CFL fns
function M.load_module(reg, name)
    if reg.loaded[name] then return reg.loaded[name] end

    local def = reg.defs[name]
    assert(def, "ct_se_bridge: module '" .. name .. "' not pre-registered")

    local se = get_se_runtime()
    local module_data = def.module_data
    if def.loader then
        module_data = def.loader()
    end
    assert(module_data, "ct_se_bridge: no module_data for '" .. name .. "'")

    -- Merge all builtin layers
    local fns = se.merge_fns(
        require("se_builtins_flow_control"),
        require("se_builtins_dispatch"),
        require("se_builtins_pred"),
        require("se_builtins_oneshot"),
        require("se_builtins_return_codes"),
        require("se_builtins_delays"),
        require("se_builtins_verify"),
        require("se_builtins_stack"),
        require("se_builtins_spawn"),
        require("se_builtins_quads"),
        require("se_builtins_dict"),
        M.make_cfl_se_builtins(reg.handle)  -- CFL bridge layer
    )

    -- Add user functions if any
    if def.user_fns then
        fns = se.merge_fns(fns, def.user_fns)
    end

    local mod = se.new_module(module_data, fns)
    reg.loaded[name] = mod
    return mod
end

function M.find_module(reg, name)
    return reg.loaded[name]
end

function M.unload_module(reg, name)
    reg.loaded[name] = nil
end

-- ============================================================================
-- CFL-SPECIFIC S-ENGINE BUILTINS
-- Creates a function table keyed by function name, suitable for
-- se_runtime.register_fns(). Captures the ChainTree handle for bridge calls.
-- ============================================================================

function M.make_cfl_se_builtins(handle)
    local se = get_se_runtime()
    local fns = {}

    -- CFL_LOG: print timestamp + node + message
    fns.CFL_LOG = function(inst, node)
        local msg = node.params[1] and node.params[1].value or ""
        -- Resolve string from string_table if it's an index
        if type(msg) == "number" then
            msg = inst.mod.module_data.string_table[msg + 1] or tostring(msg)
        end
        print(string.format("++++ timestamp %f ct_node %s se_node %d msg: %s",
            handle.timestamp, tostring(inst.ct_node_id), node.node_index, tostring(msg)))
    end

    -- CFL_ENABLE_CHILDREN / CFL_DISABLE_CHILDREN
    fns.CFL_ENABLE_CHILDREN = function(inst, node)
        local ct_node = inst.ct_node_id
        if ct_node then common.enable_children(handle, ct_node) end
    end

    fns.CFL_DISABLE_CHILDREN = function(inst, node)
        local ct_node = inst.ct_node_id
        if ct_node then common.disable_children(handle, ct_node) end
    end

    -- CFL_ENABLE_CHILD / CFL_DISABLE_CHILD
    fns.CFL_ENABLE_CHILD = function(inst, node)
        local ct_node = inst.ct_node_id
        local child_idx = se.param_int(node, 1)
        if ct_node then common.enable_child(handle, ct_node, child_idx) end
    end

    fns.CFL_DISABLE_CHILD = function(inst, node)
        local ct_node = inst.ct_node_id
        if not ct_node then return end
        local child_idx = se.param_int(node, 1)
        local children = common.get_children(handle.nodes[ct_node])
        local child_id = children[child_idx + 1]
        if child_id then
            get_engine().terminate_node_tree(handle, child_id)
        end
    end

    -- CFL_INTERNAL_EVENT
    fns.CFL_INTERNAL_EVENT = function(inst, node, event_id, event_data)
        -- Only fire on tick, skip init/terminate
        if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
            return
        end
        local ev_type = se.param_int(node, 1)
        local ev_data = se.param_int(node, 2)
        table.insert(handle.event_queue, {
            node_id  = inst.ct_node_id,
            event_id = ev_type,
            event_data = ev_data,
        })
    end

    -- CFL_EXCEPTION
    fns.CFL_EXCEPTION = function(inst, node)
        error("CFL_EXCEPTION: " .. tostring(node.params[1] and node.params[1].value))
    end

    -- CFL_SET_BITS / CFL_CLEAR_BITS (use handle.bitmask, no shadow)
    fns.CFL_SET_BITS = function(inst, node)
        for i, p in ipairs(node.params) do
            local b = tonumber(p.value) or 0
            if b >= 0 and b < 64 then
                handle.bitmask = bor(handle.bitmask or 0, bit.lshift(1, b))
            end
        end
    end

    fns.CFL_CLEAR_BITS = function(inst, node)
        for i, p in ipairs(node.params) do
            local b = tonumber(p.value) or 0
            if b >= 0 and b < 64 then
                handle.bitmask = band(handle.bitmask or 0, bnot(bit.lshift(1, b)))
            end
        end
    end

    -- CFL_READ_BIT (predicate)
    fns.CFL_READ_BIT = function(inst, node)
        local b = se.param_int(node, 1)
        return band(handle.bitmask or 0, bit.lshift(1, b)) ~= 0
    end

    -- CFL_S_BIT_OR / AND / NOR / NAND / XOR (composite predicates)
    local function bit_compound(inst, node, event_id, event_data, combine)
        if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
            return true
        end
        local result = combine == "and"  -- start true for AND, false for OR
        for _, child in ipairs(node.children or {}) do
            local val
            if child.call_type == "p_call" or child.call_type == "p_call_composite" then
                local pred_fn = inst.mod.pred_fns[child.func_index]
                if pred_fn then
                    val = pred_fn(inst, child, event_id, event_data)
                else
                    val = false
                end
            else
                -- Leaf int param: read bit from bitmask
                local b = child.params and child.params[1] and tonumber(child.params[1].value) or 0
                val = band(handle.bitmask or 0, bit.lshift(1, b)) ~= 0
            end
            if combine == "or" then
                result = result or val
            elseif combine == "and" then
                result = result and val
            end
        end
        -- For compound preds, iterate through params as bit indices
        for _, p in ipairs(node.params or {}) do
            if p.type == "int" or p.type == "uint" then
                local b = tonumber(p.value) or 0
                local val = band(handle.bitmask or 0, bit.lshift(1, b)) ~= 0
                if combine == "or" then
                    result = result or val
                elseif combine == "and" then
                    result = result and val
                end
            end
        end
        return result
    end

    fns.CFL_S_BIT_OR  = function(inst, node, eid, ed) return bit_compound(inst, node, eid, ed, "or") end
    fns.CFL_S_BIT_AND = function(inst, node, eid, ed) return bit_compound(inst, node, eid, ed, "and") end
    fns.CFL_S_BIT_NOR = function(inst, node, eid, ed) return not bit_compound(inst, node, eid, ed, "or") end
    fns.CFL_S_BIT_NAND= function(inst, node, eid, ed) return not bit_compound(inst, node, eid, ed, "and") end
    fns.CFL_S_BIT_XOR = function(inst, node, eid, ed)
        if eid == se.SE_EVENT_INIT or eid == se.SE_EVENT_TERMINATE then return true end
        local count = 0
        for _, p in ipairs(node.params or {}) do
            if p.type == "int" or p.type == "uint" then
                local b = tonumber(p.value) or 0
                if band(handle.bitmask or 0, bit.lshift(1, b)) ~= 0 then count = count + 1 end
            end
        end
        return (count % 2) == 1
    end

    -- CFL_WAIT_CHILD_DISABLED (main function in SE context)
    fns.CFL_WAIT_CHILD_DISABLED = function(inst, node, event_id, event_data)
        if event_id == se.SE_EVENT_INIT or event_id == se.SE_EVENT_TERMINATE then
            return se.SE_PIPELINE_CONTINUE
        end
        local child_idx = se.param_int(node, 1)
        local ct_node = inst.ct_node_id
        if ct_node then
            local children = common.get_children(handle.nodes[ct_node])
            local child_id = children[child_idx + 1]
            if child_id and get_engine().node_is_enabled(handle, child_id) then
                return se.SE_FUNCTION_HALT
            end
        end
        return se.SE_DISABLE
    end

    -- CFL_JSON_READ_* / CFL_COPY_* are no-ops (stubs)
    fns.CFL_JSON_READ_INT        = function(inst, node) end
    fns.CFL_JSON_READ_UINT       = function(inst, node) end
    fns.CFL_JSON_READ_FLOAT      = function(inst, node) end
    fns.CFL_JSON_READ_BOOL       = function(inst, node) end
    fns.CFL_JSON_READ_STRING_PTR = function(inst, node) end
    fns.CFL_JSON_READ_STRING_BUF = function(inst, node) end
    fns.CFL_COPY_CONST           = function(inst, node) end
    fns.CFL_COPY_CONST_FULL      = function(inst, node) end

    return fns
end

-- ============================================================================
-- RESULT CODE MAPPING
-- ============================================================================

-- Map SE result codes to CFL result codes
local function se_to_cfl(se_result)
    local se = get_se_runtime()
    if se_result == se.SE_CONTINUE or se_result == se.SE_FUNCTION_CONTINUE
       or se_result == se.SE_PIPELINE_CONTINUE then
        return CFL_HALT  -- SE continuing = CFL halt (hold position in tree)
    elseif se_result == se.SE_HALT or se_result == se.SE_FUNCTION_HALT
           or se_result == se.SE_PIPELINE_HALT then
        return CFL_HALT
    elseif se_result == se.SE_DISABLE or se_result == se.SE_FUNCTION_DISABLE
           or se_result == se.SE_PIPELINE_DISABLE then
        return CFL_DISABLE
    elseif se_result == se.SE_TERMINATE or se_result == se.SE_FUNCTION_TERMINATE
           or se_result == se.SE_PIPELINE_TERMINATE then
        return CFL_TERMINATE
    elseif se_result == se.SE_RESET or se_result == se.SE_FUNCTION_RESET
           or se_result == se.SE_PIPELINE_RESET then
        return CFL_RESET
    elseif se_result == se.SE_SKIP_CONTINUE or se_result == se.SE_FUNCTION_SKIP_CONTINUE
           or se_result == se.SE_PIPELINE_SKIP_CONTINUE then
        return CFL_SKIP_CONTINUE
    end
    return CFL_CONTINUE
end

-- ============================================================================
-- TICK HELPER
-- ============================================================================

-- Tick an S-Engine instance, drain its event queue, return CFL result
local function tick_se_instance(handle, inst, cfl_event_id)
    local se = get_se_runtime()

    -- Map CFL events to SE events
    -- CFL_TIMER_EVENT → SE_EVENT_TICK, other CFL events pass through as-is
    local se_event_id = cfl_event_id
    if cfl_event_id == CFL_TIMER_EVENT then
        se_event_id = se.SE_EVENT_TICK
    elseif cfl_event_id == CFL_INIT_EVENT then
        se_event_id = se.SE_EVENT_INIT
    elseif cfl_event_id == CFL_TERMINATE_EVENT then
        se_event_id = se.SE_EVENT_TERMINATE
    end

    -- Main tick
    local result = se.tick_once(inst, se_event_id, nil)

    -- Drain SE event queue
    while se.event_count(inst) > 0 do
        local tick_type, ev_id, ev_data = se.event_pop(inst)
        local saved = inst.tick_type
        inst.tick_type = tick_type
        result = se.tick_once(inst, ev_id, ev_data)
        inst.tick_type = saved
    end

    -- Reset if needed
    if result == se.SE_FUNCTION_RESET or result == se.SE_PIPELINE_RESET then
        for i = 0, inst.node_count - 1 do
            inst.node_states[i].flags = bor(
                band(inst.node_states[i].flags, 0xF0), 0x01)  -- keep user, set ACTIVE
        end
    end

    return se_to_cfl(result)
end

-- ============================================================================
-- CHAINTREE NODE FUNCTIONS
-- Dict-style: one_shot fn(handle, node), main fn(handle, bool_fn, node, event_id, event_data)
-- ============================================================================

M.one_shot = {}
M.main = {}
M.boolean = {}

-- ---------- CFL_SE_MODULE_LOAD ----------

M.one_shot.CFL_SE_MODULE_LOAD_INIT = function(handle, node)
    local node_id = nid(node)
    local ns = common.alloc_node_state(handle, node_id)
    local module_name = node.node_dict.module_name

    ns.module_name = module_name

    local reg = handle.se_registry
    assert(reg, "CFL_SE_MODULE_LOAD_INIT: no se_registry on handle")

    ns.se_mod = M.load_module(reg, module_name)
end

M.main.CFL_SE_MODULE_LOAD_MAIN = function(handle, bool_fn, node, event_id, event_data)
    return CFL_CONTINUE  -- stay alive; term runs when parent column terminates
end

M.one_shot.CFL_SE_MODULE_LOAD_TERM = function(handle, node)
    local node_id = nid(node)
    handle.node_state[node_id] = nil
end

-- ---------- CFL_SE_TREE_LOAD ----------

M.one_shot.CFL_SE_TREE_LOAD_INIT = function(handle, node)
    local node_id = nid(node)
    local ns = common.alloc_node_state(handle, node_id)
    local se = get_se_runtime()

    local module_name = node.node_dict.module_name
    local tree_name   = node.node_dict.tree_name
    local bb_field    = node.node_dict.bb_field_name

    local reg = handle.se_registry
    assert(reg, "CFL_SE_TREE_LOAD_INIT: no se_registry")

    local mod = M.find_module(reg, module_name)
    assert(mod, "CFL_SE_TREE_LOAD_INIT: module '" .. module_name .. "' not loaded")

    local inst = se.new_instance(mod, tree_name)
    inst.ct_node_id = node_id  -- link back to ChainTree node (ltree string)
    inst.user_ctx = handle     -- CFL handle for bridge/user functions

    ns.se_inst = inst
    ns.bb_field = bb_field

    -- Store instance in blackboard
    if bb_field then
        handle.blackboard[bb_field] = inst
    end
end

M.main.CFL_SE_TREE_LOAD_MAIN = function(handle, bool_fn, node, event_id, event_data)
    return CFL_CONTINUE  -- stay alive; term runs when parent column terminates
end

M.one_shot.CFL_SE_TREE_LOAD_TERM = function(handle, node)
    local node_id = nid(node)
    local ns = common.get_node_state(handle, node_id)
    if ns and ns.bb_field then
        handle.blackboard[ns.bb_field] = nil
    end
    handle.node_state[node_id] = nil
end

-- ---------- CFL_SE_TICK ----------

M.one_shot.CFL_SE_TICK_INIT = function(handle, node)
    local node_id = nid(node)
    local ns = common.alloc_node_state(handle, node_id)
    local bb_field = node.node_dict.tree_bb_field

    ns.bb_field = bb_field

    -- Retrieve SE instance from blackboard
    if bb_field then
        ns.se_inst = handle.blackboard[bb_field]
    end
    if ns.se_inst then
        ns.se_inst.ct_node_id = node_id
        ns.se_inst.user_ctx = handle
    end
end

M.main.CFL_SE_TICK_MAIN = function(handle, bool_fn, node, event_id, event_data)
    if event_id ~= CFL_TIMER_EVENT then
        return CFL_HALT
    end

    local node_id = nid(node)
    local ns = common.get_node_state(handle, node_id)
    if not ns or not ns.se_inst then
        return CFL_DISABLE
    end

    return tick_se_instance(handle, ns.se_inst, event_id)
end

M.one_shot.CFL_SE_TICK_TERM = function(handle, node)
    local node_id = nid(node)
    handle.node_state[node_id] = nil
end

-- ---------- CFL_SE_ENGINE (composite: module_load + tree_load + tick) ----------

M.one_shot.CFL_SE_ENGINE_INIT = function(handle, node)
    local node_id = nid(node)
    local ns = common.alloc_node_state(handle, node_id)
    local se = get_se_runtime()

    -- Read from column_data (composite) or direct node_dict fields
    local nd = node.node_dict
    local cd = nd.column_data
    local module_name = (cd and cd.module_name) or nd.module_name
    local tree_name   = (cd and cd.tree_name)   or nd.tree_name
    local bb_field    = (cd and cd.tree_bb_field) or nd.tree_bb_field

    local reg = handle.se_registry
    assert(reg, "CFL_SE_ENGINE_INIT: no se_registry")

    -- Load module if not already loaded
    local mod = M.find_module(reg, module_name) or M.load_module(reg, module_name)
    local inst = se.new_instance(mod, tree_name)
    inst.ct_node_id = node_id
    inst.user_ctx = handle

    ns.module_name = module_name
    ns.se_inst = inst
    ns.bb_field = bb_field
    ns.owns_module = not M.find_module(reg, module_name)

    if bb_field then
        handle.blackboard[bb_field] = inst
    end
end

-- SE_ENGINE is a composite (column with children controlled by SE tree).
-- Ticks the SE tree on every CFL event (timer, second, minute, etc.) so the
-- SE tree can react to all event types. Returns CFL_CONTINUE so the walker
-- visits enabled children after the SE tick.
M.main.CFL_SE_ENGINE_MAIN = function(handle, bool_fn, node, event_id, event_data)
    local node_id = nid(node)
    local ns = common.get_node_state(handle, node_id)
    if not ns or not ns.se_inst then
        return CFL_DISABLE
    end

    local result = tick_se_instance(handle, ns.se_inst, event_id)
    if result == CFL_HALT then
        return CFL_CONTINUE
    end
    -- SE tree done: map TERMINATE to DISABLE so se_engine_link
    -- disables cleanly without killing the parent column
    if result == CFL_TERMINATE then
        return CFL_DISABLE
    end
    return result
end

M.one_shot.CFL_SE_ENGINE_TERM = function(handle, node)
    local node_id = nid(node)
    local ns = common.get_node_state(handle, node_id)
    if ns then
        if ns.bb_field then
            handle.blackboard[ns.bb_field] = nil
        end
        if ns.owns_module and ns.module_name then
            local reg = handle.se_registry
            if reg then M.unload_module(reg, ns.module_name) end
        end
    end
    handle.node_state[node_id] = nil
end

return M
