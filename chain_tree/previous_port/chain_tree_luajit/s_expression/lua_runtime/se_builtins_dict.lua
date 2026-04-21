-- ============================================================================
-- se_builtins_dict.lua
-- Mirrors se_load_dictionary.c / s_engine_builtins_dict.h
--
-- The dict IS the inline param array: dict_start / dict_key / value /
-- end_dict_key / dict_end tokens stored directly in node.params.
-- se_load_dictionary parses those tokens into a plain Lua table.
--
-- String-path dicts: keys are dict_key strings.
-- Hash-path dicts:   keys are dict_key_hash numbers (precomputed by pipeline).
-- Arrays:            0-based numeric keys ONLY; hash-path navigation falls
--                    back to string/numeric when hash lookup fails.
-- ============================================================================

local se_runtime = require("se_runtime")
local param_str        = se_runtime.param_str
local param_field_name = se_runtime.param_field_name

local M = {}

-- ============================================================================
-- FNV-1a 32-bit hash
-- IMPORTANT: decompose prime 16777619 = 2^24 + 403 to avoid float64 overflow.
--   h * 16777619 = (h << 24) + h * 403
--   h * 403 : max |h| <= 2^31 → |h*403| <= 403*2^31 ≈ 8.6e11 < 2^53  (exact)
--   bit.lshift(h,24) : 32-bit shift, always safe
-- ============================================================================
local function s_expr_hash(str)
    local h = 2166136261   -- FNV offset basis (becomes signed via bit ops)
    for i = 1, #str do
        h = bit.bxor(h, str:byte(i))
        -- h * 16777619 mod 2^32
        h = bit.tobit(bit.lshift(h, 24) + h * 403)
    end
    if h < 0 then h = h + 4294967296 end
    return h
end
M.s_expr_hash = s_expr_hash

-- ============================================================================
-- Param-array parser
-- ============================================================================

local parse_dict, parse_array   -- forward declarations for mutual recursion

local function parse_scalar(p)
    local t = p.type
    if t == "int" or t == "uint" or t == "float" then
        return p.value
    elseif t == "str_idx" or t == "str_ptr" then
        local s = p.value
        -- Precompute hash; used by se_dict_extract_hash / se_dict_extract_hash_h
        return { str = s, hash = s_expr_hash(s) }
    end
    return nil
end

parse_dict = function(params, start_i)
    -- params[start_i].type == "dict_start"
    local result = {}
    local i = start_i + 1
    while i <= #params do
        local p = params[i]
        if not p then break end
        local t = p.type

        if t == "dict_end" then
            return result, i + 1

        elseif t == "dict_key" or t == "dict_key_hash" then
            local key = p.value   -- string name OR numeric hash
            i = i + 1
            local vp = params[i]
            if not vp then break end

            local val
            if vp.type == "dict_start" then
                val, i = parse_dict(params, i)
            elseif vp.type == "array_start" then
                val, i = parse_array(params, i)
            else
                val = parse_scalar(vp)
                i = i + 1
            end

            if params[i] and params[i].type == "end_dict_key" then
                i = i + 1
            end

            result[key] = val
        else
            i = i + 1
        end
    end
    return result, i
end

parse_array = function(params, start_i)
    -- params[start_i].type == "array_start"
    -- Store elements at 0-based NUMERIC keys only.
    -- Hash-path navigation handles the string/"0" fallback itself.
    local result = {}
    local idx = 0
    local i = start_i + 1
    while i <= #params do
        local p = params[i]
        if not p then break end
        local t = p.type

        if t == "array_end" then
            return result, i + 1

        else
            local val
            if t == "dict_start" then
                val, i = parse_dict(params, i)
            elseif t == "array_start" then
                val, i = parse_array(params, i)
            else
                val = parse_scalar(p)
                i = i + 1
            end

            if val ~= nil then
                result[idx] = val
                idx = idx + 1
            end
        end
    end
    return result, i
end

-- ============================================================================
-- Navigation helpers
-- ============================================================================

local function as_number(v)
    if type(v) == "table" and v.str then return tonumber(v.str) or 0 end
    return tonumber(v) or 0
end

local function as_hash(v)
    if type(v) == "table" and v.hash then return v.hash end
    if type(v) == "string" then return s_expr_hash(v) end
    return math.floor(tonumber(v) or 0)
end

-- Dot-path navigation: "integers.positive", "int_array.0", "items.0.id"
local function navigate_str_path(dict, path)
    local cur = dict
    for key in path:gmatch("[^%.]+") do
        if type(cur) ~= "table" then return nil end
        local v = cur[key]
        if v == nil then
            local n = tonumber(key)
            if n then v = cur[n] end   -- 0-based numeric fallback for arrays
        end
        cur = v
    end
    return cur
end

-- Collect path as {hash, str} pairs from node.params[start..end] (1-based).
-- str_hash params embed {hash=N, str=S}; dict_key_hash params are plain numbers.
local function collect_path_items(node, start_idx, end_idx)
    local items = {}
    local params = node.params or {}
    for i = start_idx, end_idx do
        local p = params[i]
        if not p then break end
        if type(p.value) == "table" then
            -- str_hash: value = {hash=N, str=S}
            items[#items + 1] = { hash = p.value.hash, str = p.value.str }
        else
            -- dict_key_hash: plain number
            items[#items + 1] = { hash = p.value, str = nil }
        end
    end
    return items
end

-- Hash-path navigation.
-- For each path item, try hash key first; if that fails and we have the
-- original string, fall back to string key then numeric index.
-- This handles arrays (stored at 0-based numeric keys) reached via hash path
-- where the pipeline emits hash("0"), hash("1"), etc.
local function navigate_hash_path(dict, path_items)
    local cur = dict
    for _, item in ipairs(path_items) do
        if type(cur) ~= "table" then return nil end
        local v = cur[item.hash]
        if v == nil and item.str then
            v = cur[item.str]                  -- plain string key fallback
            if v == nil then
                local n = tonumber(item.str)
                if n then v = cur[n] end       -- numeric index fallback ("0"→0)
            end
        end
        cur = v
    end
    return cur
end

-- Find the last field_ref param index in node.params (1-based)
local function last_field_idx(node)
    local params = node.params or {}
    for i = #params, 1, -1 do
        local t = params[i].type
        if t == "field_ref" or t == "nested_field_ref" then return i end
    end
    return nil
end

-- Retrieve a dict table from a blackboard PTR field
local function bb_dict(inst, node, param_idx)
    local fname = param_field_name(node, param_idx)
    local d = inst.blackboard[fname]
    assert(d and type(d) == "table",
        "se_dict: blackboard field '" .. tostring(fname) ..
        "' is not a dict table (got " .. type(d) .. ")")
    return d
end

-- ============================================================================
-- SE_LOAD_DICTIONARY / SE_LOAD_DICTIONARY_HASH
-- params[1] = field_ref (dest blackboard field)
-- params[2] = dict_start (inline token stream through matching dict_end)
-- ============================================================================
local function load_dict_impl(inst, node)
    local params = node.params or {}
    assert(#params >= 2, "se_load_dictionary: need >= 2 params")
    local fname = param_field_name(node, 1)
    local p2 = params[2]
    assert(p2 and p2.type == "dict_start",
        "se_load_dictionary: params[2] must be dict_start, got: " ..
        tostring(p2 and p2.type))
    local dict = parse_dict(params, 2)
    inst.blackboard[fname] = dict
end

M.se_load_dictionary      = load_dict_impl
M.se_load_dictionary_hash = load_dict_impl

-- ============================================================================
-- String-path extraction
-- params[1]=field_ref (source dict), params[2]=str_idx (path), params[3]=field_ref (dest)
-- ============================================================================

M.se_dict_extract_int = function(inst, node)
    local d = bb_dict(inst, node, 1)
    local v = navigate_str_path(d, param_str(node, 2))
    inst.blackboard[param_field_name(node, 3)] =
        v ~= nil and math.floor(as_number(v)) or 0
end

M.se_dict_extract_uint = function(inst, node)
    local d = bb_dict(inst, node, 1)
    local v = navigate_str_path(d, param_str(node, 2))
    inst.blackboard[param_field_name(node, 3)] =
        v ~= nil and math.floor(math.abs(as_number(v))) or 0
end

M.se_dict_extract_float = function(inst, node)
    local d = bb_dict(inst, node, 1)
    local v = navigate_str_path(d, param_str(node, 2))
    inst.blackboard[param_field_name(node, 3)] =
        v ~= nil and (as_number(v) + 0.0) or 0.0
end

M.se_dict_extract_bool = function(inst, node)
    local d = bb_dict(inst, node, 1)
    local v = navigate_str_path(d, param_str(node, 2))
    local n = v ~= nil and as_number(v) or 0
    inst.blackboard[param_field_name(node, 3)] = (n ~= 0) and 1 or 0
end

M.se_dict_extract_hash = function(inst, node)
    local d = bb_dict(inst, node, 1)
    local v = navigate_str_path(d, param_str(node, 2))
    inst.blackboard[param_field_name(node, 3)] =
        v ~= nil and as_hash(v) or 0
end

-- ============================================================================
-- Hash-path extraction
-- params[1]=field_ref (source), params[2..N-1]=str_hash, params[N]=field_ref (dest)
-- ============================================================================

local function hash_extract(inst, node, conv)
    local d    = bb_dict(inst, node, 1)
    local dest = last_field_idx(node)
    assert(dest and dest > 2,
        "se_dict_extract_h: missing hash path or dest field")
    local path = collect_path_items(node, 2, dest - 1)
    local v    = navigate_hash_path(d, path)
    inst.blackboard[param_field_name(node, dest)] = conv(v)
end

M.se_dict_extract_int_h = function(inst, node)
    hash_extract(inst, node, function(v)
        return v ~= nil and math.floor(as_number(v)) or 0 end)
end

M.se_dict_extract_uint_h = function(inst, node)
    hash_extract(inst, node, function(v)
        return v ~= nil and math.floor(math.abs(as_number(v))) or 0 end)
end

M.se_dict_extract_float_h = function(inst, node)
    hash_extract(inst, node, function(v)
        return v ~= nil and (as_number(v) + 0.0) or 0.0 end)
end

M.se_dict_extract_bool_h = function(inst, node)
    hash_extract(inst, node, function(v)
        local n = v ~= nil and as_number(v) or 0
        return (n ~= 0) and 1 or 0
    end)
end

M.se_dict_extract_hash_h = function(inst, node)
    hash_extract(inst, node, function(v)
        return v ~= nil and as_hash(v) or 0 end)
end

-- ============================================================================
-- SE_DICT_STORE_PTR
-- params[1]=field_ref (source dict), params[2]=str_idx (path), params[3]=field_ref (dest)
-- ============================================================================

M.se_dict_store_ptr = function(inst, node)
    local d   = bb_dict(inst, node, 1)
    local sub = navigate_str_path(d, param_str(node, 2))
    inst.blackboard[param_field_name(node, 3)] =
        (type(sub) == "table") and sub or nil
end

-- ============================================================================
-- SE_DICT_STORE_PTR_H
-- params[1]=field_ref (source), params[2..N-1]=str_hash, params[N]=field_ref (dest)
-- ============================================================================

M.se_dict_store_ptr_h = function(inst, node)
    local d    = bb_dict(inst, node, 1)
    local dest = last_field_idx(node)
    assert(dest and dest > 2,
        "se_dict_store_ptr_h: missing hash path or dest field")
    local path = collect_path_items(node, 2, dest - 1)
    local sub  = navigate_hash_path(d, path)
    inst.blackboard[param_field_name(node, dest)] =
        (type(sub) == "table") and sub or nil
end


-- ============================================================================
-- SE_LOAD_FUNCTION_DICT  (oneshot)
-- Builds a function dictionary from inline dict_key params + child subtrees.
-- Each dict_key names a function; the corresponding child subtree IS the body.
-- Result: blackboard[field] = { [hash] = closure, ... }
--
-- params[1] = field_ref (dest blackboard field)
-- params[2] = dict_start
-- params[3] = dict_key "write_register"     → children[1]
-- params[4] = end_dict_key
-- params[5] = dict_key "read_modify_write"  → children[2]
-- ...
-- params[N] = dict_end
-- ============================================================================
M.se_load_function_dict = function(inst, node)
    local params   = node.params or {}
    local children = node.children or {}
    assert(#params >= 2, "se_load_function_dict: need >= 2 params")

    local fname = param_field_name(node, 1)

    -- Collect dict_key names in order; each pairs with the next child
    local keys = {}
    for i = 1, #params do
        if params[i].type == "dict_key" then
            keys[#keys + 1] = params[i].value
        end
    end

    assert(#keys == #children,
        string.format("se_load_function_dict: %d keys but %d children",
            #keys, #children))

    -- Build the dictionary: hash(key_name) -> closure over child subtree
    local dict = {}
    for i = 1, #keys do
        local key_name   = keys[i]
        local key_hash   = s_expr_hash(key_name)
        local child_node = children[i]

        -- Closure captures child_node; invoke_any handles full lifecycle
        dict[key_hash] = function(calling_inst, exec_node, eid, edata)
            return se_runtime.invoke_any(calling_inst, child_node, eid, edata)
        end
    end

    inst.blackboard[fname] = dict
end
return M