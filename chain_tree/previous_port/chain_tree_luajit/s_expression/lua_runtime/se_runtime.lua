-- ============================================================================
-- se_runtime.lua
-- LuaJIT S-Expression Engine Runtime
--
-- Mirrors C s_engine_eval.c / s_engine_node.c / s_engine_module.c behavior.
-- Operates on the module_data TREE structure directly (no flat param stream).
--
-- Execution model:
--   External caller owns the tick loop.
--   se_runtime.tick() runs one main tick then drains the internal event queue.
--   Builtins signature: fn(inst, node, event_id, event_data)
--     - For main (m_call/pt_m_call): called on INIT, TICK, TERMINATE events.
--     - For oneshot (o_call/io_call):  fn(inst, node)  -- no event, no return
--     - For pred (p_call/p_call_composite): fn(inst, node) -> bool
--
-- API:
--   local se_runtime = require("se_runtime")
--   local mod  = se_runtime.new_module(module_data, user_fns)
--   local inst = se_runtime.new_instance(mod, "tree_name")
--   local result = se_runtime.tick(inst)
--   -- caller owns the tick loop, drain loop, and completion predicates
-- ============================================================================

local M = {}

local bit = require("bit")
local band, bor, bnot, bxor, lshift, rshift =
    bit.band, bit.bor, bit.bnot, bit.bxor, bit.lshift, bit.rshift

-- ============================================================================
-- Result codes  (s_engine_types.h)
-- ============================================================================
M.SE_CONTINUE               = 0
M.SE_HALT                   = 1
M.SE_TERMINATE              = 2
M.SE_RESET                  = 3
M.SE_DISABLE                = 4
M.SE_SKIP_CONTINUE          = 5

M.SE_FUNCTION_CONTINUE      = 6
M.SE_FUNCTION_HALT          = 7
M.SE_FUNCTION_TERMINATE     = 8
M.SE_FUNCTION_RESET         = 9
M.SE_FUNCTION_DISABLE       = 10
M.SE_FUNCTION_SKIP_CONTINUE = 11

M.SE_PIPELINE_CONTINUE      = 12
M.SE_PIPELINE_HALT          = 13
M.SE_PIPELINE_TERMINATE     = 14
M.SE_PIPELINE_RESET         = 15
M.SE_PIPELINE_DISABLE       = 16
M.SE_PIPELINE_SKIP_CONTINUE = 17

-- Special event IDs
M.SE_EVENT_TICK      = 0xffff
M.SE_EVENT_INIT      = 0xfffe
M.SE_EVENT_TERMINATE = 0xfffd

-- ============================================================================
-- Node state flags  (s_engine_types.h)
-- ============================================================================
local FLAG_ACTIVE      = 0x01
local FLAG_INITIALIZED = 0x02
local FLAG_EVER_INIT   = 0x04
local FLAG_ERROR       = 0x08
local FLAGS_SYSTEM     = 0x0F
local FLAGS_USER       = 0xF0

-- ============================================================================
-- Event queue size
-- ============================================================================
local EVENT_QUEUE_SIZE = 16

-- ============================================================================
-- Convenience locals for result codes used inside the runtime
-- ============================================================================
local SE_PIPELINE_CONTINUE      = M.SE_PIPELINE_CONTINUE
local SE_PIPELINE_HALT          = M.SE_PIPELINE_HALT
local SE_PIPELINE_DISABLE       = M.SE_PIPELINE_DISABLE
local SE_PIPELINE_TERMINATE     = M.SE_PIPELINE_TERMINATE
local SE_PIPELINE_RESET         = M.SE_PIPELINE_RESET
local SE_PIPELINE_SKIP_CONTINUE = M.SE_PIPELINE_SKIP_CONTINUE
local SE_FUNCTION_DISABLE       = M.SE_FUNCTION_DISABLE
local SE_FUNCTION_HALT          = M.SE_FUNCTION_HALT
local SE_FUNCTION_TERMINATE     = M.SE_FUNCTION_TERMINATE
local SE_FUNCTION_CONTINUE      = M.SE_FUNCTION_CONTINUE
local SE_EVENT_INIT             = M.SE_EVENT_INIT
local SE_EVENT_TERMINATE        = M.SE_EVENT_TERMINATE
local SE_EVENT_TICK             = M.SE_EVENT_TICK


-- ============================================================================
-- Node state helpers
-- ============================================================================
local function get_ns(inst, node_index)
    return inst.node_states[node_index]
end

-- ============================================================================
-- Event queue (circular buffer, mirrors s_engine_event_queue.c)
-- ============================================================================
local function eq_init(inst)
    inst.event_queue       = {}
    inst.event_queue_head  = 0
    inst.event_queue_count = 0
end

local function eq_count(inst)
    return inst.event_queue_count
end

local function eq_push(inst, tick_type, event_id, event_data)
    assert(inst.event_queue_count < EVENT_QUEUE_SIZE,
        "se_runtime: event_queue full")
    local tail = (inst.event_queue_head + inst.event_queue_count) % EVENT_QUEUE_SIZE
    inst.event_queue[tail] = { tick_type=tick_type, event_id=event_id, event_data=event_data }
    inst.event_queue_count = inst.event_queue_count + 1
end

local function eq_pop(inst)
    assert(inst.event_queue_count > 0, "se_runtime: event_queue empty")
    local e = inst.event_queue[inst.event_queue_head]
    inst.event_queue_head  = (inst.event_queue_head + 1) % EVENT_QUEUE_SIZE
    inst.event_queue_count = inst.event_queue_count - 1
    return e.tick_type, e.event_id, e.event_data
end

local function eq_clear(inst)
    inst.event_queue_head  = 0
    inst.event_queue_count = 0
end

-- Public queue API (for builtins and external callers)
function M.event_push(inst, tick_type, event_id, event_data)
    eq_push(inst, tick_type, event_id, event_data)
end
function M.event_count(inst)  return eq_count(inst)  end
function M.event_pop(inst)    return eq_pop(inst)     end
function M.event_clear(inst)  return eq_clear(inst)   end

-- ============================================================================
-- DFS annotation: assign node_index (0-based pre-order) and func_index
-- ============================================================================
local function annotate_node(node, counter, module_data)
    -- Assign sequential DFS pre-order index
    node.node_index = counter[1]
    counter[1] = counter[1] + 1

    -- Resolve func_index from call_type
    local ct = node.call_type
    local fname = node.func_name
    if ct == "o_call" or ct == "io_call" then
        for i, name in ipairs(module_data.oneshot_funcs) do
            if name == fname then node.func_index = i-1; break end
        end
        assert(node.func_index ~= nil,
            "annotate: unknown oneshot function: " .. tostring(fname))
    elseif ct == "m_call" or ct == "pt_m_call" then
        for i, name in ipairs(module_data.main_funcs) do
            if name == fname then node.func_index = i-1; break end
        end
        assert(node.func_index ~= nil,
            "annotate: unknown main function: " .. tostring(fname))
    elseif ct == "p_call" or ct == "p_call_composite" then
        for i, name in ipairs(module_data.pred_funcs) do
            if name == fname then node.func_index = i-1; break end
        end
        assert(node.func_index ~= nil,
            "annotate: unknown pred function: " .. tostring(fname))
    else
        error("annotate: unknown call_type: " .. tostring(ct))
    end

    -- Recurse into children
    for _, child in ipairs(node.children or {}) do
        annotate_node(child, counter, module_data)
    end
end

-- ============================================================================
-- new_module: build structure and annotate trees.
-- Does NOT assert on missing functions -- registration is separate.
-- Pass an optional initial fns table as a convenience; more can be added
-- later via register_fns().  Call validate_module() before new_instance().
-- ============================================================================
function M.new_module(module_data, initial_fns)
    local mod = {
        module_data = module_data,
        oneshot_fns = {},   -- [0-based index] -> fn,  nil = not yet registered
        main_fns    = {},
        pred_fns    = {},
        -- name->index maps for register_fns lookups
        _oneshot_idx = {},  -- name_upper -> 0-based index
        _main_idx    = {},
        _pred_idx    = {},
    }

    -- Build name->index maps from module_data function lists
    for i, name in ipairs(module_data.oneshot_funcs or {}) do
        mod._oneshot_idx[name:upper()] = i - 1
    end
    for i, name in ipairs(module_data.main_funcs or {}) do
        mod._main_idx[name:upper()] = i - 1
    end
    for i, name in ipairs(module_data.pred_funcs or {}) do
        mod._pred_idx[name:upper()] = i - 1
    end

    -- Annotate every tree (node_index, func_index assignment)
    for _, tree_name in ipairs(module_data.tree_order) do
        local tree = module_data.trees[tree_name]
        local counter = {0}
        for _, root in ipairs(tree.nodes) do
            annotate_node(root, counter, module_data)
        end
    end

    -- Build hash index for tree lookup (se_spawn_tree / se_spawn_and_tick_tree)
    mod.trees_by_hash = {}
    for _, tree_name in ipairs(module_data.tree_order) do
        local tree = module_data.trees[tree_name]
        if tree.name_hash then
            mod.trees_by_hash[tree.name_hash] = tree_name
        end
    end

    -- Default time function (can be replaced by caller)
    mod.get_time = M.default_get_time

    -- Register any functions supplied at construction time
    if initial_fns then
        M.register_fns(mod, initial_fns)
    end

    return mod
end

-- ============================================================================
-- register_fns: add (or overwrite) functions on an existing mod.
-- Can be called multiple times before validate_module / new_instance.
-- fns: table of { func_name = fn, ... } -- same format as merge_fns output.
-- Unknown names (not referenced by this module) are silently ignored;
-- they may belong to a different module loaded in the same session.
-- ============================================================================
function M.register_fns(mod, fns)
    for raw_name, fn in pairs(fns) do
        local uname = raw_name:upper()
        local idx

        idx = mod._oneshot_idx[uname]
        if idx ~= nil then mod.oneshot_fns[idx] = fn end

        idx = mod._main_idx[uname]
        if idx ~= nil then mod.main_fns[idx] = fn end

        idx = mod._pred_idx[uname]
        if idx ~= nil then mod.pred_fns[idx] = fn end
    end
end

-- ============================================================================
-- validate_module: check that every function required by the module has been
-- registered.  Returns two values:
--   ok      bool   -- true if all functions are present
--   missing table  -- list of { name=, kind= } for every gap (empty if ok)
-- Call this after all register_fns() calls, before new_instance().
-- ============================================================================
function M.validate_module(mod)
    local missing = {}
    local md = mod.module_data

    for i, name in ipairs(md.oneshot_funcs or {}) do
        if not mod.oneshot_fns[i-1] then
            missing[#missing+1] = { name=name, kind="oneshot" }
        end
    end
    for i, name in ipairs(md.main_funcs or {}) do
        if not mod.main_fns[i-1] then
            missing[#missing+1] = { name=name, kind="main" }
        end
    end
    for i, name in ipairs(md.pred_funcs or {}) do
        if not mod.pred_fns[i-1] then
            missing[#missing+1] = { name=name, kind="pred" }
        end
    end

    return (#missing == 0), missing
end

-- ============================================================================
-- new_instance: allocate node_states, blackboard, event queue.
-- Calls validate_module() first; errors with the full missing-function list
-- so the caller sees every gap at once rather than one assert at a time.
-- ============================================================================
function M.new_instance(mod, tree_name)
    local ok, missing = M.validate_module(mod)
    if not ok then
        local lines = { "new_instance: unregistered functions:" }
        for _, m in ipairs(missing) do
            lines[#lines+1] = string.format("  [%s] %s", m.kind, m.name)
        end
        error(table.concat(lines, "\n"))
    end

    local module_data = mod.module_data
    local tree = module_data.trees[tree_name]
    assert(tree, "new_instance: unknown tree: " .. tostring(tree_name))

    local inst = {
        mod                = mod,
        tree               = tree,
        node_states        = {},
        node_count         = tree.node_count,
        pointer_array      = {},
        slot_flags         = {},
        pointer_count      = tree.pointer_count or 0,
        blackboard         = {},
        current_node_index = 0,
        current_event_id   = 0,
        current_event_data = nil,
        in_pointer_call    = false,
        pointer_base       = 0,
        stack              = nil,
        tick_type          = 0,
        user_ctx           = nil,   -- application-defined; set after new_instance()
    }

    -- Initialize all node states: ACTIVE flag set, state=0, user_data=0
    for i = 0, tree.node_count - 1 do
        inst.node_states[i] = { flags=FLAG_ACTIVE, state=0, user_data=0 }
    end

    -- Initialize pointer array
    for i = 0, inst.pointer_count - 1 do
        inst.pointer_array[i] = { ptr=nil, u64=0, i64=0, f64=0.0 }
    end

    -- Initialize blackboard from record descriptor if present
    if tree.record_name then
        local rec = module_data.records and module_data.records[tree.record_name]
        if rec and rec.fields then
            for field_name, field_def in pairs(rec.fields) do
                local dv = field_def.default
                if type(dv) == "string" then dv = tonumber(dv) or dv end
                inst.blackboard[field_name] = (dv ~= nil) and dv or 0
            end
        end
    end

    eq_init(inst)

    return inst
end

-- ============================================================================
-- Core invocation  (mirrors s_engine_eval.c)
-- ============================================================================

-- Forward declaration for mutual recursion
local invoke_main, invoke_oneshot, invoke_pred, invoke_any

-- invoke_main: full INIT/TICK/TERMINATE lifecycle (m_call, pt_m_call)
invoke_main = function(inst, node, event_id, event_data)
    local ns = get_ns(inst, node.node_index)

    -- Inactive nodes are transparent
    if band(ns.flags, FLAG_ACTIVE) == 0 then
        return SE_PIPELINE_CONTINUE
    end

    local fn = inst.mod.main_fns[node.func_index]
    assert(fn, "invoke_main: no function for: " .. tostring(node.func_name))

    -- Save/restore pointer context for pt_m_call
    local saved_pb  = inst.pointer_base
    local saved_ipc = inst.in_pointer_call
    if node.call_type == "pt_m_call" then
        inst.in_pointer_call = true
        inst.pointer_base    = node.pointer_index or 0
    end

    -- INIT on first activation
    if band(ns.flags, FLAG_INITIALIZED) == 0 then
        ns.flags = bor(ns.flags, FLAG_INITIALIZED)
        inst.current_node_index = node.node_index
        fn(inst, node, SE_EVENT_INIT, nil)
    end

    -- TICK (or whichever event_id was passed)
    inst.current_node_index = node.node_index
    local result = fn(inst, node, event_id, event_data)
    result = result or SE_PIPELINE_CONTINUE

    -- Deactivate node on PIPELINE_DISABLE (normal completion).
    -- TERMINATE/RESET propagate upward intact; the node stays active
    -- so chain_flow can keep returning the result each tick.
    if result == SE_PIPELINE_DISABLE then
        inst.current_node_index = node.node_index
        fn(inst, node, SE_EVENT_TERMINATE, nil)
        ns.flags = band(ns.flags, bnot(FLAG_ACTIVE))
    end

    inst.pointer_base    = saved_pb
    inst.in_pointer_call = saved_ipc

    return result
end

-- invoke_oneshot: fire-once semantics (o_call, io_call)
invoke_oneshot = function(inst, node)
    local ns = get_ns(inst, node.node_index)
    -- io_call / SURVIVES_RESET uses EVER_INIT; o_call uses INITIALIZED
    local survives = (node.call_type == "io_call")
    local check    = survives and FLAG_EVER_INIT or FLAG_INITIALIZED
    if band(ns.flags, check) ~= 0 then
        return   -- already fired
    end
    ns.flags = bor(ns.flags, check)
    local fn = inst.mod.oneshot_fns[node.func_index]
    assert(fn, "invoke_oneshot: no function for: " .. tostring(node.func_name))
    inst.current_node_index = node.node_index
    fn(inst, node)
end

-- invoke_pred: pure bool evaluation, no state mutation
invoke_pred = function(inst, node)
    local fn = inst.mod.pred_fns[node.func_index]
    assert(fn, "invoke_pred: no function for: " .. tostring(node.func_name))
    inst.current_node_index = node.node_index
    return fn(inst, node) and true or false
end

-- invoke_any: dispatch by call_type; pred returns pipeline codes
invoke_any = function(inst, node, event_id, event_data)
    local ct = node.call_type
    if ct == "m_call" or ct == "pt_m_call" then
        return invoke_main(inst, node, event_id, event_data)
    elseif ct == "o_call" or ct == "io_call" then
        invoke_oneshot(inst, node)
        return SE_PIPELINE_CONTINUE
    elseif ct == "p_call" or ct == "p_call_composite" then
        return invoke_pred(inst, node) and SE_PIPELINE_CONTINUE or SE_PIPELINE_HALT
    end
    error("invoke_any: unknown call_type: " .. tostring(ct))
end

-- Expose for builtins and external harness
M.invoke_any  = invoke_any
M.invoke_pred = invoke_pred

-- ============================================================================
-- Child helpers  (mirrors s_engine_node.c)
-- All child indices are 0-based (matching C convention externally);
-- Lua table access is +1 internally.
-- ============================================================================

-- Count callable children
local function child_count(node)
    return #(node.children or {})
end

-- Invoke child at 0-based logical index
local function child_invoke(inst, node, idx, event_id, event_data)
    local child = (node.children or {})[idx + 1]
    assert(child, "child_invoke: bad index " .. idx)
    return invoke_any(inst, child, event_id, event_data)
end

-- Terminate a single child (only MAIN if INITIALIZED)
local function child_terminate(inst, node, idx)
    local child = (node.children or {})[idx + 1]
    if not child then return end
    local ct = child.call_type
    if ct == "m_call" or ct == "pt_m_call" then
        local ns = get_ns(inst, child.node_index)
        if band(ns.flags, FLAG_INITIALIZED) ~= 0 then
            local fn = inst.mod.main_fns[child.func_index]
            inst.current_node_index = child.node_index
            fn(inst, child, SE_EVENT_TERMINATE, nil)
            -- Clear all system flags, preserve user bits, reset state
            ns.flags    = band(ns.flags, FLAGS_USER)
            ns.state    = 0
            ns.user_data = 0
        end
    end
end

-- Reset a child: set ACTIVE only, clear state/user_data (preserve user flags).
-- FLAG_EVER_INIT is NOT pre-set here; it is set by invoke_oneshot when the
-- function actually fires. Pre-setting it would cause io_call nodes (which
-- use FLAG_EVER_INIT as their "already fired" guard) to be silently skipped.
local function child_reset(inst, node, idx)
    local child = (node.children or {})[idx + 1]
    if not child then return end
    local ns = get_ns(inst, child.node_index)
    ns.flags    = bor(band(ns.flags, FLAGS_USER), FLAG_ACTIVE)
    ns.state    = 0
    ns.user_data = 0
end

-- Recursively reset a subtree
local function reset_recursive(inst, node)
    local ns = get_ns(inst, node.node_index)
    ns.flags    = bor(band(ns.flags, FLAGS_USER), FLAG_ACTIVE, FLAG_EVER_INIT)
    ns.state    = 0
    ns.user_data = 0
    for _, child in ipairs(node.children or {}) do
        reset_recursive(inst, child)
    end
end

local function child_reset_recursive(inst, node, idx)
    local child = (node.children or {})[idx + 1]
    if child then reset_recursive(inst, child) end
end

-- Terminate all children (reverse order), then reset all callables
local function children_terminate_all(inst, node)
    local children = node.children or {}
    -- Terminate in reverse order
    for i = #children, 1, -1 do
        child_terminate(inst, node, i - 1)
    end
    -- Reset all
    for i = 1, #children do
        local ns = get_ns(inst, children[i].node_index)
        ns.flags    = bor(band(ns.flags, FLAGS_USER), FLAG_ACTIVE, FLAG_EVER_INIT)
        ns.state    = 0
        ns.user_data = 0
    end
end

-- Reset all children (no terminate)
local function children_reset_all(inst, node)
    for _, child in ipairs(node.children or {}) do
        local ns = get_ns(inst, child.node_index)
        ns.flags    = bor(band(ns.flags, FLAGS_USER), FLAG_ACTIVE, FLAG_EVER_INIT)
        ns.state    = 0
        ns.user_data = 0
    end
end

-- Invoke child as pred (returns bool)
local function child_invoke_pred(inst, node, idx)
    local child = (node.children or {})[idx + 1]
    assert(child, "child_invoke_pred: bad index " .. idx)
    return invoke_pred(inst, child)
end

-- Invoke child as oneshot (fire-once semantics)
local function child_invoke_oneshot(inst, node, idx)
    local child = (node.children or {})[idx + 1]
    assert(child, "child_invoke_oneshot: bad index " .. idx)
    invoke_oneshot(inst, child)
end

-- Expose child helpers for builtin use
M.child_count            = child_count
M.child_invoke           = child_invoke
M.child_invoke_pred      = child_invoke_pred
M.child_invoke_oneshot   = child_invoke_oneshot
M.child_terminate        = child_terminate
M.child_reset            = child_reset
M.child_reset_recursive  = child_reset_recursive
M.children_terminate_all = children_terminate_all
M.children_reset_all     = children_reset_all
M.get_ns                 = get_ns
M.invoke_oneshot         = invoke_oneshot

-- ============================================================================
-- Parameter accessors  (for use inside builtins)
-- node.params is a 1-based Lua array of {type, value, order} tables
-- ============================================================================

-- Get raw param entry
local function param(node, i)
    return node.params[i]
end

-- Integer param (int or uint)
local function param_int(node, i)
    local p = node.params[i]
    assert(p, "param_int: nil param at " .. i)
    local v = p.value
    if type(v) == "string" then return math.floor(tonumber(v) or 0) end
    return v
end

-- Float param
local function param_float(node, i)
    local v = node.params[i].value
    if type(v) == "string" then return tonumber(v) or 0.0 end
    return v
end

-- String param (str_idx carries the string itself, str_hash carries {hash, str})
local function param_str(node, i)
    local p = node.params[i]
    if p.type == "str_hash" then return p.value.str end
    return p.value
end

-- Field name (field_ref, nested_field_ref)
local function param_field_name(node, i)
    return node.params[i].value
end

-- Read a blackboard field.
-- Coerces string values to numbers so arithmetic predicates always get
-- the right type regardless of how the blackboard was initialised from JSON.
local function field_get(inst, node, i)
    local v = inst.blackboard[node.params[i].value]
    if type(v) == "string" then
        local n = tonumber(v)
        if n ~= nil then return n end
    end
    return v
end

-- Write a blackboard field
local function field_set(inst, node, i, value)
    inst.blackboard[node.params[i].value] = value
end

-- Result code param (type="result")
local function param_result(node, i)
    return node.params[i].value
end

-- Expose param helpers
M.param           = param
M.param_int       = param_int
M.param_float     = param_float
M.param_str       = param_str
M.param_field_name= param_field_name
M.field_get       = field_get
M.field_set       = field_set
M.param_result    = param_result

-- ============================================================================
-- tick_once: the ONLY tick entry point.  Mirrors s_expr_node_tick() in C.
-- Does NOT drain the event queue.  Does NOT define completion semantics.
-- The caller owns the event queue drain loop and all result-code predicates.
-- ============================================================================
function M.tick_once(inst, event_id, event_data)
    event_id = event_id or SE_EVENT_TICK

    local tree = inst.tree
    local root = tree.nodes[1]
    assert(root, "tick_once: tree has no root node")

    -- Check root ACTIVE (root disabled = tree is dead)
    local root_ns = get_ns(inst, root.node_index)
    if band(root_ns.flags, FLAG_ACTIVE) == 0 then
        return M.SE_FUNCTION_TERMINATE
    end

    -- Store event context on inst (builtins may read these)
    inst.current_event_id   = event_id
    inst.current_event_data = event_data
    inst.tick_type          = event_id

    -- Reset stack top if a stack is present
    if inst.stack then inst.stack.top = 0 end

    return invoke_main(inst, root, event_id, event_data)
end



-- ============================================================================
-- merge_fns: utility to merge multiple builtin tables into one
-- Usage:
--   local fns = se_runtime.merge_fns(
--       require("se_builtins_flow_control"),
--       require("se_builtins_pred"),
--       require("se_builtins_oneshot"),
--       require("se_builtins_return_codes"),
--       { my_custom_fn = function(inst, node, event_id, event_data) ... end }
--   )
--   local mod = se_runtime.new_module(module_data, fns)
-- ============================================================================
function M.merge_fns(...)
    local out = {}
    for _, t in ipairs({...}) do
        for k, v in pairs(t) do out[k] = v end
    end
    return out
end


-- ============================================================================
-- Extended node-state accessors
-- Used by delay/verify/spawn builtins for per-node 64-bit storage.
-- Stored directly in node_states[i] as extra Lua fields.
-- ============================================================================
function M.get_u64(inst, node)
    return inst.pointer_array[inst.pointer_base].u64 or 0
end
function M.set_u64(inst, node, v)
    inst.pointer_array[inst.pointer_base].u64 = v
end
function M.get_f64(inst, node)
    return inst.pointer_array[inst.pointer_base].f64 or 0.0
end
function M.set_f64(inst, node, v)
    inst.pointer_array[inst.pointer_base].f64 = v
end
-- user_u64 / user_f64: per-node extended state (separate from pointer slot)
function M.get_user_u64(inst, node)
    return (get_ns(inst, node.node_index).user_u64 or 0)
end
function M.set_user_u64(inst, node, v)
    get_ns(inst, node.node_index).user_u64 = v
end
function M.get_user_f64(inst, node)
    return (get_ns(inst, node.node_index).user_f64 or 0.0)
end
function M.set_user_f64(inst, node, v)
    get_ns(inst, node.node_index).user_f64 = v
end
function M.get_state(inst, node)
    return get_ns(inst, node.node_index).state
end
function M.set_state(inst, node, v)
    get_ns(inst, node.node_index).state = v
end

-- Default time function (override via mod.get_time = fn)
M.default_get_time = os.clock

return M