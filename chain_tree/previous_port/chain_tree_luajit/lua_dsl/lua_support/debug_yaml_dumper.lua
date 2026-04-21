--[[
    debug_yaml_dumper.lua - Human-readable YAML debug output for ChainTree structures.

    Recursively serializes nested Lua tables to YAML format.
    Not a full YAML spec implementation — designed for readability
    of ChainTree's JSON-like data (strings, numbers, booleans,
    nested tables with string keys, arrays).

    Usage:
        local dumper = require("lua_support.debug_yaml_dumper")
        dumper.dump_to_file(data, "debug_output.yaml")
        local yaml_str = dumper.to_yaml(data)
]]

local M = {}

-- ---------------------------------------------------------------------------
-- Internal: detect if a table is array-like (consecutive integer keys 1..N)
-- ---------------------------------------------------------------------------
local function is_array(t)
    if type(t) ~= "table" then return false end
    local n = #t
    if n == 0 then
        -- Check if truly empty or has non-integer keys
        for _ in pairs(t) do
            return false
        end
        return true  -- empty table treated as empty mapping
    end
    local count = 0
    for _ in pairs(t) do
        count = count + 1
    end
    return count == n
end

-- ---------------------------------------------------------------------------
-- Internal: sort keys for deterministic output
-- ---------------------------------------------------------------------------
local function sorted_keys(t)
    local keys = {}
    for k, _ in pairs(t) do
        keys[#keys + 1] = k
    end
    table.sort(keys, function(a, b)
        -- numbers before strings, then lexicographic
        local ta, tb = type(a), type(b)
        if ta ~= tb then return ta < tb end
        return a < b
    end)
    return keys
end

-- ---------------------------------------------------------------------------
-- Internal: escape a YAML scalar if needed
-- ---------------------------------------------------------------------------
local function escape_scalar(v)
    local s = tostring(v)
    -- Quote if it contains characters that could confuse a YAML parser
    if s == ""
       or s:match("^[%s]")
       or s:match("[%s]$")
       or s:match("[:#{}&*!|>'\"%@`,%[%]{}]")
       or s:match("^%-%-")
       or s:match("^true$") or s:match("^false$")
       or s:match("^null$") or s:match("^~$")
       or tonumber(s)
    then
        -- Use double-quoted form, escaping internal quotes and backslashes
        s = s:gsub("\\", "\\\\"):gsub('"', '\\"')
        return '"' .. s .. '"'
    end
    return s
end

-- ---------------------------------------------------------------------------
-- Internal: recursive serializer
-- ---------------------------------------------------------------------------
local function serialize(buf, value, indent, inline_depth)
    local prefix = string.rep("  ", indent)

    if type(value) == "table" then
        if is_array(value) then
            if #value == 0 then
                buf[#buf + 1] = " []\n"
                return
            end
            buf[#buf + 1] = "\n"
            for i = 1, #value do
                buf[#buf + 1] = prefix .. "- "
                if type(value[i]) == "table" then
                    -- For nested table in array, serialize inline or indented
                    if is_array(value[i]) or next(value[i]) == nil then
                        serialize(buf, value[i], indent + 1, inline_depth + 1)
                    else
                        buf[#buf + 1] = "\n"
                        local keys = sorted_keys(value[i])
                        for _, k in ipairs(keys) do
                            buf[#buf + 1] = prefix .. "  " .. escape_scalar(k) .. ":"
                            serialize(buf, value[i][k], indent + 2, inline_depth + 1)
                        end
                    end
                else
                    buf[#buf + 1] = escape_scalar(value[i]) .. "\n"
                end
            end
        else
            -- Mapping
            local keys = sorted_keys(value)
            if #keys == 0 then
                buf[#buf + 1] = " {}\n"
                return
            end
            buf[#buf + 1] = "\n"
            for _, k in ipairs(keys) do
                buf[#buf + 1] = prefix .. escape_scalar(k) .. ":"
                serialize(buf, value[k], indent + 1, inline_depth + 1)
            end
        end
    elseif type(value) == "boolean" then
        buf[#buf + 1] = " " .. (value and "true" or "false") .. "\n"
    elseif value == nil then
        buf[#buf + 1] = " null\n"
    else
        buf[#buf + 1] = " " .. escape_scalar(value) .. "\n"
    end
end

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

--- Convert a Lua table to a YAML-formatted string.
--- @param data table   The data to serialize
--- @return string       YAML text
function M.to_yaml(data)
    local buf = { "# ChainTree Debug YAML Output\n" }
    buf[#buf + 1] = "# Generated: " .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. "\n"
    buf[#buf + 1] = "---\n"

    if type(data) == "table" then
        if is_array(data) then
            for i = 1, #data do
                buf[#buf + 1] = "- "
                if type(data[i]) == "table" then
                    serialize(buf, data[i], 1, 0)
                else
                    buf[#buf + 1] = escape_scalar(data[i]) .. "\n"
                end
            end
        else
            local keys = sorted_keys(data)
            for _, k in ipairs(keys) do
                buf[#buf + 1] = escape_scalar(k) .. ":"
                serialize(buf, data[k], 1, 0)
            end
        end
    else
        buf[#buf + 1] = tostring(data) .. "\n"
    end

    return table.concat(buf)
end

--- Write a Lua table to a YAML file.
--- @param data        table   The data to serialize
--- @param filepath    string  Output file path
function M.dump_to_file(data, filepath)
    local yaml_str = M.to_yaml(data)
    local fh, err = io.open(filepath, "w")
    if not fh then
        error(string.format("debug_yaml_dumper: cannot open '%s': %s", filepath, err))
    end
    fh:write(yaml_str)
    fh:close()
    print(string.format("[debug_yaml_dumper] Wrote %d bytes to %s",
                         #yaml_str, filepath))
end

--- Dump a Lua table to YAML on stdout (convenience for REPL use).
--- @param data table
function M.dump(data)
    io.write(M.to_yaml(data))
end

return M
