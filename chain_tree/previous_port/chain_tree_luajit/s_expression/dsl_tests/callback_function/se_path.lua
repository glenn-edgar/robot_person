-- ============================================================================
-- se_path.lua
-- Prepend the lua_runtime directory to package.path so that all se_runtime
-- and builtin modules can be found via require().
--
-- Usage: place this file in the same directory as your test scripts and call:
--   dofile((...):match("(.-)[^/]+$") .. "se_path.lua")
--   -- or, if arg[0] is available (luajit CLI):
--   dofile(debug.getinfo(1,"S").source:sub(2):match("(.-)[^/]+$") .. "se_path.lua")
--
-- More simply, just put this at the very top of every test file:
--   local _dir = debug.getinfo(1,"S").source:sub(2):match("(.-)[^/]+$") or "./"
--   dofile(_dir .. "se_path.lua")
--
-- The RUNTIME_REL_PATH variable below is the path from THIS file's location
-- to the lua_runtime directory.  Adjust if se_path.lua is moved.
-- ============================================================================

-- Resolve the directory that contains THIS file (se_path.lua itself).
-- debug.getinfo(1,"S").source is "@/abs/or/rel/path/to/se_path.lua"
local _src = debug.getinfo(1, "S").source
local _here = _src:sub(2):match("(.-)[^/]+$") or "./"   -- strip leading "@" and filename

-- Path from here to the lua_runtime directory.
-- Change this one constant if you move se_path.lua.
local RUNTIME_REL_PATH = "../../lua_runtime/"

local _runtime = _here .. RUNTIME_REL_PATH

-- Prepend to package.path so these take priority over system modules.
-- The semicolon-separated entries follow standard Lua path conventions.
package.path = _runtime .. "?.lua;" .. package.path

-- Also add the directory containing se_path.lua itself so that test-local
-- modules (e.g. basic_primitive_test_user_functions.lua) resolve without
-- an explicit path.
if _here ~= "" and _here ~= "./" then
    package.path = _here .. "?.lua;" .. package.path
end

