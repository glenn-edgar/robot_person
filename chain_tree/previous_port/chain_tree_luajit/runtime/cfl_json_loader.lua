-- ============================================================================
-- cfl_json_loader.lua
-- ChainTree LuaJIT Runtime — load JSON IR into runtime Lua tables
--
-- Reads the JSON intermediate representation produced by the DSL pipeline
-- (stages 1-5) and builds a flash_handle table equivalent to the C
-- chaintree_handle_t.  No binary image needed — Lua tables are the runtime.
--
-- API:
--   local loader = require("cfl_json_loader")
--   local flash  = loader.load("my_test.json")
--   loader.register_functions(flash, builtins, user_fns)
-- ============================================================================

local M = {}

local cjson = require("cjson")
local bit   = require("bit")
local band   = bit.band

local defs = require("cfl_definitions")

-- ============================================================================
-- Helpers
-- ============================================================================

-- Read entire file
local function read_file(path)
    local f = assert(io.open(path, "r"))
    local data = f:read("*a")
    f:close()
    return data
end

-- Sort ltree names for a KB by their original index (breadth-first order)
local function sorted_ltree_pairs(ltree_to_index)
    local arr = {}
    for ltree, idx in pairs(ltree_to_index) do
        arr[#arr + 1] = { ltree = ltree, idx = idx }
    end
    table.sort(arr, function(a, b) return a.idx < b.idx end)
    return arr
end

-- Extract KB name from ltree path:  "kb.first_test.GATE_root._0" -> "first_test"
local function kb_name_from_ltree(ltree)
    local parts = {}
    for p in ltree:gmatch("[^%.]+") do parts[#parts + 1] = p end
    return parts[2]
end

-- Compute node depth from ltree path
local function depth_from_ltree(ltree, root_ltree)
    local function count_parts(s)
        local n = 0
        for _ in s:gmatch("[^%.]+") do n = n + 1 end
        return n
    end
    local root_parts = count_parts(root_ltree)
    local node_parts = count_parts(ltree)
    return math.max(0, math.floor((node_parts - root_parts) / 2))
end

-- Check if a node is a metadata-only node (filtered out)
local METADATA_LABELS = {
    virtual_functions = true, complete_functions = true,
    main_functions = true, one_shot_functions = true,
    boolean_functions = true,
}

local function is_metadata_node(node_def)
    return METADATA_LABELS[node_def.label or ""] == true
end

-- ============================================================================
-- load(json_path) -> flash_handle
--
-- Builds a table mirroring chaintree_handle_t:
--   .nodes[idx]              — 0-based node array
--   .node_count
--   .link_table[idx]         — 0-based flat link table
--   .link_table_size
--   .main_function_names[]   — 1-based array of names
--   .main_function_count
--   .one_shot_function_names[]
--   .one_shot_function_count
--   .boolean_function_names[]
--   .boolean_function_count
--   .main_functions[]        — 1-based, filled by register_functions
--   .one_shot_functions[]
--   .boolean_functions[]
--   .kb_table[]              — 1-based array of KB info
--   .kb_count
--   .event_strings{}         — name -> id
--   .bitmask_names{}         — name -> bit
--   .node_data{}             — node_id -> node_dict table
--   .bb_table                — blackboard descriptor or nil
-- ============================================================================

function M.load(json_path)
    local raw = read_file(json_path)
    local ir = cjson.decode(raw)

    assert(ir.schema_version == "1.0",
        "cfl_json_loader: unsupported schema_version: " .. tostring(ir.schema_version))

    -- ------------------------------------------------------------------
    -- Pass 1: identify KBs and their root nodes
    -- ------------------------------------------------------------------
    local kb_names_set = {}
    local kb_root_ltree = {}  -- kb_name -> root ltree path

    for ltree, _ in pairs(ir.ltree_to_index) do
        local kb = kb_name_from_ltree(ltree)
        if kb and not kb_names_set[kb] then
            kb_names_set[kb] = true
        end
    end

    -- Find root node per KB (the ltree with minimum index in that KB)
    local kb_min_idx = {}
    for ltree, idx in pairs(ir.ltree_to_index) do
        local kb = kb_name_from_ltree(ltree)
        if kb then
            if not kb_min_idx[kb] or idx < kb_min_idx[kb] then
                kb_min_idx[kb] = idx
                kb_root_ltree[kb] = ltree
            end
        end
    end

    -- ------------------------------------------------------------------
    -- Pass 2: order all non-metadata nodes by their original index
    -- ------------------------------------------------------------------
    local ordered = sorted_ltree_pairs(ir.ltree_to_index)

    -- Filter metadata nodes
    local filtered_set = {}
    local filtered_ordered = {}
    for _, entry in ipairs(ordered) do
        local node_def = ir.nodes[entry.ltree]
        if node_def and not is_metadata_node(node_def) then
            filtered_ordered[#filtered_ordered + 1] = entry
        else
            filtered_set[entry.ltree] = true
        end
    end

    -- Also filter children of metadata nodes
    local final_ordered = {}
    for _, entry in ipairs(filtered_ordered) do
        local node_def = ir.nodes[entry.ltree]
        local parent = node_def and node_def.label_dict and node_def.label_dict.parent_ltree_name
        if not (parent and filtered_set[parent]) then
            final_ordered[#final_ordered + 1] = entry
        else
            filtered_set[entry.ltree] = true
        end
    end

    -- ------------------------------------------------------------------
    -- Pass 3: assign final indices (0-based) and build node array
    -- ------------------------------------------------------------------
    local total_nodes = #final_ordered
    local ltree_to_final = {}  -- ltree -> final 0-based index
    local nodes = {}           -- 0-based array of node tables

    for i, entry in ipairs(final_ordered) do
        ltree_to_final[entry.ltree] = i - 1
    end

    -- ------------------------------------------------------------------
    -- Pass 4: collect all unique function names
    -- ------------------------------------------------------------------
    local main_names_set    = { CFL_NULL = true }
    local oneshot_names_set = { CFL_NULL = true }
    local bool_names_set    = { CFL_NULL = true }

    for _, entry in ipairs(final_ordered) do
        local nd = ir.nodes[entry.ltree]
        local ld = nd and nd.label_dict
        if ld then
            if ld.main_function_name           then main_names_set[ld.main_function_name] = true end
            if ld.initialization_function_name then oneshot_names_set[ld.initialization_function_name] = true end
            if ld.termination_function_name    then oneshot_names_set[ld.termination_function_name] = true end
            if ld.aux_function_name            then bool_names_set[ld.aux_function_name] = true end
        end
    end

    -- Merge the DSL-emitted function_registry. Functions referenced from
    -- node_dict fields (verify error_function, watchdog wd_fn, ...) are
    -- not visible from per-node label scans above, so without this merge
    -- resolve_oneshot_idx returns 0 (CFL_NULL) and handlers silently
    -- no-op. The DSL's _build_envelope unions all per-KB function sets
    -- into ir.function_registry = {main=[], one_shot=[], boolean=[]}.
    local reg = ir.function_registry
    if reg then
        for _, name in ipairs(reg.main or {})     do main_names_set[name]    = true end
        for _, name in ipairs(reg.one_shot or {}) do oneshot_names_set[name] = true end
        for _, name in ipairs(reg.boolean or {})  do bool_names_set[name]    = true end
    end

    -- Build sorted arrays (CFL_NULL always at index 0)
    local function build_fn_index(names_set)
        local arr = {}
        local idx = {}
        -- CFL_NULL first
        arr[1] = "CFL_NULL"
        idx["CFL_NULL"] = 0
        local sorted = {}
        for name in pairs(names_set) do
            if name ~= "CFL_NULL" then sorted[#sorted + 1] = name end
        end
        table.sort(sorted)
        for _, name in ipairs(sorted) do
            arr[#arr + 1] = name
            idx[name] = #arr - 1  -- 0-based
        end
        return arr, idx
    end

    local main_fn_names,    main_fn_idx    = build_fn_index(main_names_set)
    local oneshot_fn_names, oneshot_fn_idx = build_fn_index(oneshot_names_set)
    local bool_fn_names,    bool_fn_idx    = build_fn_index(bool_names_set)

    -- ------------------------------------------------------------------
    -- Pass 5: build link table and node structures
    -- ------------------------------------------------------------------
    local link_table = {}  -- 0-based flat array
    local link_pos = 0
    local node_data_map = {}  -- node_id -> node_dict table

    for i, entry in ipairs(final_ordered) do
        local node_id = i - 1
        local nd = ir.nodes[entry.ltree]
        local ld = nd.label_dict or {}
        local ndict = nd.node_dict

        -- Resolve parent
        local parent_idx = defs.CFL_NO_PARENT
        if ld.parent_ltree_name and ltree_to_final[ld.parent_ltree_name] then
            parent_idx = ltree_to_final[ld.parent_ltree_name]
        end

        -- Build children links
        local children = {}
        if ld.links then
            for _, child_ltree in ipairs(ld.links) do
                local cid = ltree_to_final[child_ltree]
                if cid then children[#children + 1] = cid end
            end
        end

        local link_start = link_pos
        local link_count = #children
        for _, cid in ipairs(children) do
            link_table[link_pos] = cid
            link_pos = link_pos + 1
        end

        -- auto_start flag
        local auto_start = ndict and ndict.auto_start or false

        -- Resolve function indices
        local main_fi    = main_fn_idx[ld.main_function_name or "CFL_NULL"] or 0
        local init_fi    = oneshot_fn_idx[ld.initialization_function_name or "CFL_NULL"] or 0
        local term_fi    = oneshot_fn_idx[ld.termination_function_name or "CFL_NULL"] or 0
        local aux_fi     = bool_fn_idx[ld.aux_function_name or "CFL_NULL"] or 0

        -- Depth
        local kb = kb_name_from_ltree(entry.ltree)
        local root = kb_root_ltree[kb] or entry.ltree
        local depth = depth_from_ltree(entry.ltree, root)

        nodes[node_id] = {
            node_index           = node_id,
            parent_index         = parent_idx,
            depth                = depth,
            link_start           = link_start,
            link_count           = link_count + (auto_start and 0x8000 or 0),
            main_function_index  = main_fi,
            init_function_index  = init_fi,
            aux_function_index   = aux_fi,
            term_function_index  = term_fi,
            -- Keep original names for debugging
            _ltree               = entry.ltree,
            _label               = nd.label,
        }

        -- Store node_dict as-is (Lua table — no binary encoding needed)
        if ndict then
            node_data_map[node_id] = ndict
        end
    end

    -- ------------------------------------------------------------------
    -- Pass 6: build KB table
    -- ------------------------------------------------------------------
    local kb_table = {}
    -- Collect KB names with their earliest node index for ordering
    local kb_info = {}
    for name in pairs(kb_names_set) do
        -- Find earliest node to determine KB order (matches C binary ordering)
        local earliest = total_nodes
        for _, entry in ipairs(final_ordered) do
            if kb_name_from_ltree(entry.ltree) == name then
                local fid = ltree_to_final[entry.ltree]
                if fid < earliest then earliest = fid end
                break  -- final_ordered is already sorted by position
            end
        end
        kb_info[#kb_info + 1] = { name = name, earliest = earliest }
    end
    table.sort(kb_info, function(a, b) return a.earliest < b.earliest end)
    local kb_names_sorted = {}
    for _, info in ipairs(kb_info) do kb_names_sorted[#kb_names_sorted + 1] = info.name end

    for _, kb_name in ipairs(kb_names_sorted) do
        -- Skip metadata KBs (function tables, event/bitmask tables)
        if kb_name:match("_functions$") or kb_name == "complete_functions_kb"
           or kb_name == "bitmask_table_kb" or kb_name == "event_string_table_kb" then
            goto continue_kb
        end

        -- Find start/end indices for this KB
        local start_idx, end_idx, max_depth = total_nodes, 0, 0
        for _, entry in ipairs(final_ordered) do
            if kb_name_from_ltree(entry.ltree) == kb_name then
                local fid = ltree_to_final[entry.ltree]
                if fid < start_idx then start_idx = fid end
                if fid > end_idx then end_idx = fid end
                local d = nodes[fid].depth
                if d > max_depth then max_depth = d end
            end
        end

        local node_count = end_idx - start_idx + 1
        local mem_factor = 10  -- default
        if ir.kb_metadata and ir.kb_metadata[kb_name] then
            mem_factor = ir.kb_metadata[kb_name].node_memory_factor or mem_factor
        end

        -- Aliases
        local aliases = {}
        if ir.kb_metadata and ir.kb_metadata[kb_name] and ir.kb_metadata[kb_name].node_aliases then
            for alias, idx in pairs(ir.kb_metadata[kb_name].node_aliases) do
                aliases[alias] = idx
            end
        end

        kb_table[#kb_table + 1] = {
            name          = kb_name,
            start_index   = start_idx,
            root_node_index = start_idx,  -- root is always the first node
            node_count    = node_count,
            max_depth     = max_depth,
            memory_factor = mem_factor,
            aliases       = aliases,
        }
        ::continue_kb::
    end

    -- ------------------------------------------------------------------
    -- Pass 7: blackboard
    -- ------------------------------------------------------------------
    local bb_table = nil
    if ir.blackboard then
        bb_table = ir.blackboard  -- keep as-is
    end

    -- ------------------------------------------------------------------
    -- Build original-index to final-index mapping
    -- ------------------------------------------------------------------
    local original_to_final = {}
    for ltree, final_idx in pairs(ltree_to_final) do
        local orig_idx = ir.ltree_to_index[ltree]
        if orig_idx then
            original_to_final[orig_idx] = final_idx
        end
    end

    -- ------------------------------------------------------------------
    -- Build flash_handle
    -- ------------------------------------------------------------------
    local flash = {
        nodes      = nodes,
        node_count = total_nodes,

        link_table      = link_table,
        link_table_size = link_pos,

        main_function_names     = main_fn_names,
        main_function_count     = #main_fn_names,
        one_shot_function_names = oneshot_fn_names,
        one_shot_function_count = #oneshot_fn_names,
        boolean_function_names  = bool_fn_names,
        boolean_function_count  = #bool_fn_names,

        -- Function pointer arrays (filled by register_functions)
        main_functions     = {},
        one_shot_functions = {},
        boolean_functions  = {},

        -- Function name -> index maps
        _main_fn_idx    = main_fn_idx,
        _oneshot_fn_idx = oneshot_fn_idx,
        _bool_fn_idx    = bool_fn_idx,

        -- State machine name -> { node_id, state_index_by_name }
        -- Populated below; lets user-function error handlers fire
        -- change_state without hardcoding ltree paths.
        sm_by_name = {},

        kb_table = kb_table,
        kb_count = #kb_table,

        event_strings = ir.event_string_table or {},
        bitmask_names = ir.bitmask_table or {},

        node_data = node_data_map,
        bb_table  = bb_table,

        -- ltree and index mappings (for join/exception node resolution)
        ltree_to_index    = ltree_to_final,
        original_to_final = original_to_final,

        -- Usage count (for arena calculation, not critical in LuaJIT)
        main_function_usage_count = nil,
    }

    -- Populate sm_by_name[sm_name] = { node_id, states = { name -> idx } }
    for _, entry in ipairs(final_ordered) do
        local nd = ir.nodes[entry.ltree]
        local ld = nd and nd.label_dict
        if ld and ld.main_function_name == "CFL_STATE_MACHINE_MAIN" then
            local sm_name = ld.sm_name
            if sm_name then
                local node_id = ltree_to_final[entry.ltree]
                local cd = nd.node_dict and nd.node_dict.column_data
                local names = cd and cd.state_names or {}
                local states = {}
                for i, n in ipairs(names) do states[n] = i - 1 end
                flash.sm_by_name[sm_name] = {
                    node_id = node_id,
                    states  = states,
                }
            end
        end
    end

    return flash
end

-- ============================================================================
-- register_functions(flash_handle, builtin_registry, user_registry)
--
-- Fills flash.main_functions[], flash.one_shot_functions[], flash.boolean_functions[]
-- by matching function names from the registries.
--
-- Each registry is a table: { FUNCTION_NAME = lua_function, ... }
-- Multiple registries can be passed; later ones override earlier.
-- ============================================================================
function M.register_functions(flash, ...)
    -- Merge all registries into one
    local merged = {}
    for _, reg in ipairs({...}) do
        if reg then
            for name, fn in pairs(reg) do
                merged[name:upper()] = fn
            end
        end
    end

    -- Map function names to Lua function references
    for i, name in ipairs(flash.main_function_names) do
        local fn = merged[name:upper()]
        flash.main_functions[i - 1] = fn  -- 0-based
    end

    for i, name in ipairs(flash.one_shot_function_names) do
        local fn = merged[name:upper()]
        flash.one_shot_functions[i - 1] = fn
    end

    for i, name in ipairs(flash.boolean_function_names) do
        local fn = merged[name:upper()]
        -- Wrap boolean functions to ensure proper Lua boolean return.
        -- In C, CFL_NULL returns 0 which is falsy. In Lua, 0 is truthy.
        -- Wrapping ensures numeric 0 and nil map to false.
        if fn then
            local raw_fn = fn
            flash.boolean_functions[i - 1] = function(handle, node_idx, event_type, event_id, event_data)
                local r = raw_fn(handle, node_idx, event_type, event_id, event_data)
                if r == 0 or r == nil then return false end
                return r and true or false
            end
        end
    end
end

-- ============================================================================
-- validate(flash_handle) -> ok, missing
-- Check that every function slot has been filled.
-- ============================================================================
function M.validate(flash)
    local missing = {}

    for i, name in ipairs(flash.main_function_names) do
        if not flash.main_functions[i - 1] then
            missing[#missing + 1] = { kind = "main", name = name }
        end
    end
    for i, name in ipairs(flash.one_shot_function_names) do
        if not flash.one_shot_functions[i - 1] then
            missing[#missing + 1] = { kind = "oneshot", name = name }
        end
    end
    for i, name in ipairs(flash.boolean_function_names) do
        if not flash.boolean_functions[i - 1] then
            missing[#missing + 1] = { kind = "boolean", name = name }
        end
    end

    return #missing == 0, missing
end

return M
