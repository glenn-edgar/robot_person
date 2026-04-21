-- ============================================================================
-- cfl_timer.lua
-- ChainTree LuaJIT Runtime — timer system generating periodic events
-- Mirrors cfl_timer_system.c
-- ============================================================================

local M = {}

local defs = require("cfl_definitions")

function M.create(delta_time)
    local now = os.time()
    local t = os.date("*t", now)
    return {
        delta_time  = delta_time or 0.1,
        timestamp   = 0.0,
        -- Previous time fields for change detection
        prev_sec    = t.sec,
        prev_min    = t.min,
        prev_hour   = t.hour,
        prev_day    = t.day,
        prev_wday   = t.wday,
        prev_yday   = t.yday,
    }
end

function M.tick(timer)
    timer.timestamp = timer.timestamp + timer.delta_time

    local now = os.time()
    local t = os.date("*t", now)
    local mask = 0

    if t.sec  ~= timer.prev_sec  then mask = mask + defs.CFL_CHANGED_SECOND end
    if t.min  ~= timer.prev_min  then mask = mask + defs.CFL_CHANGED_MINUTE end
    if t.hour ~= timer.prev_hour then mask = mask + defs.CFL_CHANGED_HOUR   end
    if t.day  ~= timer.prev_day  then mask = mask + defs.CFL_CHANGED_DAY    end
    if t.wday ~= timer.prev_wday then mask = mask + defs.CFL_CHANGED_DOW    end
    if t.yday ~= timer.prev_yday then mask = mask + defs.CFL_CHANGED_DOY    end

    timer.prev_sec  = t.sec
    timer.prev_min  = t.min
    timer.prev_hour = t.hour
    timer.prev_day  = t.day
    timer.prev_wday = t.wday
    timer.prev_yday = t.yday

    return { changed_mask = mask, timestamp = timer.timestamp }
end

function M.get_timestamp(timer)
    return timer.timestamp
end

function M.wait(timer, seconds)
    -- In LuaJIT we don't actually sleep; the caller controls the tick loop.
    -- This is a no-op placeholder for compatibility.
end

return M
