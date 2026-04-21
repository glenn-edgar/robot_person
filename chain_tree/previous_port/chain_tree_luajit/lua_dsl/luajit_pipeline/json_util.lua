--[[
  json_util.lua - Pure-Lua JSON encoder/decoder for the ChainTree pipeline.
  
  No external dependencies. Works with LuaJIT and standard Lua 5.1+.
  
  Usage:
    local json = require("json_util")
    local tbl = json.decode(json_string)
    local str = json.encode(tbl)
--]]

local M = {}

-- =========================================================================
-- Encoder
-- =========================================================================

local encode_value  -- forward decl

local function encode_string(s)
    s = s:gsub('\\', '\\\\')
    s = s:gsub('"', '\\"')
    s = s:gsub('\n', '\\n')
    s = s:gsub('\r', '\\r')
    s = s:gsub('\t', '\\t')
    s = s:gsub('%c', function(c)
        return string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. s .. '"'
end

local function is_array(t)
    if type(t) ~= "table" then return false end
    local count = 0
    for _ in pairs(t) do count = count + 1 end
    if count == 0 then return false end
    for i = 1, count do
        if t[i] == nil then return false end
    end
    return count == #t
end

local function sorted_keys(t)
    local keys = {}
    for k in pairs(t) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    return keys
end

encode_value = function(val)
    if val == nil then return "null" end

    local vtype = type(val)
    if vtype == "boolean" then
        return val and "true" or "false"
    elseif vtype == "number" then
        if val == math.floor(val) and math.abs(val) < 2^53 then
            return string.format("%d", val)
        else
            return string.format("%.17g", val)
        end
    elseif vtype == "string" then
        return encode_string(val)
    elseif vtype == "table" then
        if next(val) == nil then return "{}" end
        if is_array(val) then
            local parts = {}
            for i = 1, #val do parts[i] = encode_value(val[i]) end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for _, k in ipairs(sorted_keys(val)) do
                parts[#parts + 1] = encode_string(tostring(k)) .. ":" .. encode_value(val[k])
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    else
        return '"<' .. vtype .. '>"'
    end
end

function M.encode(val)
    return encode_value(val)
end

-- =========================================================================
-- Decoder
-- =========================================================================

local decode_value  -- forward decl

local function skip_ws(str, pos)
    return str:match("^%s*()", pos)
end

local function decode_string(str, pos)
    -- pos should be at the opening "
    if str:byte(pos) ~= 34 then
        error("Expected '\"' at position " .. pos)
    end
    pos = pos + 1

    local parts = {}
    while pos <= #str do
        local c = str:byte(pos)
        if c == 34 then  -- closing "
            return table.concat(parts), pos + 1
        elseif c == 92 then  -- backslash
            pos = pos + 1
            local esc = str:byte(pos)
            if esc == 34 then parts[#parts + 1] = '"'
            elseif esc == 92 then parts[#parts + 1] = '\\'
            elseif esc == 47 then parts[#parts + 1] = '/'
            elseif esc == 98 then parts[#parts + 1] = '\b'
            elseif esc == 102 then parts[#parts + 1] = '\f'
            elseif esc == 110 then parts[#parts + 1] = '\n'
            elseif esc == 114 then parts[#parts + 1] = '\r'
            elseif esc == 116 then parts[#parts + 1] = '\t'
            elseif esc == 117 then -- \uXXXX
                local hex = str:sub(pos + 1, pos + 4)
                local code = tonumber(hex, 16)
                if code then
                    if code < 128 then
                        parts[#parts + 1] = string.char(code)
                    elseif code < 2048 then
                        parts[#parts + 1] = string.char(
                            192 + math.floor(code / 64),
                            128 + code % 64
                        )
                    else
                        parts[#parts + 1] = string.char(
                            224 + math.floor(code / 4096),
                            128 + math.floor(code / 64) % 64,
                            128 + code % 64
                        )
                    end
                end
                pos = pos + 4
            end
            pos = pos + 1
        else
            parts[#parts + 1] = string.char(c)
            pos = pos + 1
        end
    end
    error("Unterminated string at position " .. pos)
end

local function decode_number(str, pos)
    local num_str = str:match("^%-?%d+%.?%d*[eE]?[%+%-]?%d*", pos)
    if not num_str then
        error("Invalid number at position " .. pos)
    end
    local val = tonumber(num_str)
    if not val then
        error("Cannot parse number: " .. num_str)
    end
    return val, pos + #num_str
end

local function decode_object(str, pos)
    -- pos at {
    pos = skip_ws(str, pos + 1)
    local obj = {}

    if str:byte(pos) == 125 then  -- empty object }
        return obj, pos + 1
    end

    while true do
        pos = skip_ws(str, pos)
        if str:byte(pos) ~= 34 then
            error("Expected string key at position " .. pos)
        end
        local key
        key, pos = decode_string(str, pos)

        pos = skip_ws(str, pos)
        if str:byte(pos) ~= 58 then  -- :
            error("Expected ':' at position " .. pos)
        end
        pos = skip_ws(str, pos + 1)

        local val
        val, pos = decode_value(str, pos)
        obj[key] = val

        pos = skip_ws(str, pos)
        local c = str:byte(pos)
        if c == 125 then  -- }
            return obj, pos + 1
        elseif c == 44 then  -- ,
            pos = pos + 1
        else
            error("Expected ',' or '}' at position " .. pos)
        end
    end
end

local function decode_array(str, pos)
    -- pos at [
    pos = skip_ws(str, pos + 1)
    local arr = {}

    if str:byte(pos) == 93 then  -- empty array ]
        return arr, pos + 1
    end

    while true do
        pos = skip_ws(str, pos)
        local val
        val, pos = decode_value(str, pos)
        arr[#arr + 1] = val

        pos = skip_ws(str, pos)
        local c = str:byte(pos)
        if c == 93 then  -- ]
            return arr, pos + 1
        elseif c == 44 then  -- ,
            pos = pos + 1
        else
            error("Expected ',' or ']' at position " .. pos)
        end
    end
end

decode_value = function(str, pos)
    pos = skip_ws(str, pos)
    local c = str:byte(pos)

    if c == 34 then  -- "
        return decode_string(str, pos)
    elseif c == 123 then  -- {
        return decode_object(str, pos)
    elseif c == 91 then  -- [
        return decode_array(str, pos)
    elseif c == 116 then  -- true
        if str:sub(pos, pos + 3) == "true" then
            return true, pos + 4
        end
    elseif c == 102 then  -- false
        if str:sub(pos, pos + 4) == "false" then
            return false, pos + 5
        end
    elseif c == 110 then  -- null
        if str:sub(pos, pos + 3) == "null" then
            return nil, pos + 4
        end
    elseif c == 45 or (c >= 48 and c <= 57) then  -- - or digit
        return decode_number(str, pos)
    end

    error("Unexpected character at position " .. pos .. ": " .. string.char(c or 0))
end

function M.decode(str)
    if type(str) ~= "string" then
        error("Expected string, got " .. type(str))
    end
    local val, pos = decode_value(str, 1)
    return val
end

return M