-- ============================================================================
-- cfl_definitions.lua
-- ChainTree LuaJIT Runtime — constants, return codes, event types
-- Mirrors cfl_engine.h, cfl_event_queue.h, CT_Tree_Walker.h
-- ============================================================================

local M = {}

local bit = require("bit")
local band, bor, bnot = bit.band, bit.bor, bit.bnot

-- ============================================================================
-- Main function return codes (cfl_engine.h)
-- ============================================================================
M.CFL_CONTINUE         = 0
M.CFL_HALT             = 1
M.CFL_TERMINATE        = 2
M.CFL_RESET            = 3
M.CFL_DISABLE          = 4
M.CFL_SKIP_CONTINUE    = 5
M.CFL_TERMINATE_SYSTEM = 6

-- ============================================================================
-- Tree walker return codes (CT_Tree_Walker.h)
-- ============================================================================
M.CT_CONTINUE       = 0
M.CT_SKIP_CHILDREN  = 1
M.CT_STOP_BRANCH    = 2
M.CT_STOP_SIBLINGS  = 3
M.CT_STOP_LEVEL     = 4
M.CT_STOP_ALL       = 5

-- ============================================================================
-- Engine event IDs (cfl_engine.h)
-- ============================================================================
M.CFL_INIT_EVENT                     = 0
M.CFL_TERMINATE_EVENT                = 1
M.CFL_START_TESTS                    = 2
M.CFL_TERMINATE_TESTS                = 3
M.CFL_TIMER_EVENT                    = 4
M.CFL_SECOND_EVENT                   = 5
M.CFL_MINUTE_EVENT                   = 6
M.CFL_HOUR_EVENT                     = 7
M.CFL_DAY_EVENT                      = 8
M.CFL_WEEK_EVENT                     = 9
M.CFL_MONTH_EVENT                    = 10
M.CFL_YEAR_EVENT                     = 11
M.CFL_RAISE_EXCEPTION_EVENT         = 12
M.CFL_TURN_HEARTBEAT_ON_EVENT       = 13
M.CFL_TURN_HEARTBEAT_OFF_EVENT      = 14
M.CFL_HEARTBEAT_EVENT               = 15
M.CFL_SET_EXCEPTION_STEP_EVENT      = 16
M.CFL_CHANGE_STATE_EVENT            = 17
M.CFL_RESET_STATE_MACHINE_EVENT     = 18
M.CFL_TERMINATE_STATE_MACHINE_EVENT = 19

M.CFL_TERMINATE_SYSTEM_EVENT = 0xFFFF
M.CFL_STOP_START_TESTS_EVENT = 0xFFF0

-- ============================================================================
-- Event types (cfl_event_queue.h)
-- ============================================================================
M.CFL_EVENT_TYPE_PTR                        = 0
M.CFL_EVENT_TYPE_INT                        = 1
M.CFL_EVENT_TYPE_UINT                       = 2
M.CFL_EVENT_TYPE_FLOAT                      = 3
M.CFL_EVENT_TYPE_NODE_ID                    = 4
M.CFL_EVENT_TYPE_JSON_RECORD                = 5
M.CFL_EVENT_TYPE_STREAMING_DATA             = 6
M.CFL_EVENT_TYPE_STREAMING_COLLECTED_PACKETS = 7
M.CFL_EVENT_TYPE_NULL                       = 8

-- ============================================================================
-- Event priorities
-- ============================================================================
M.CFL_EVENT_PRIORITY_LOW  = 0
M.CFL_EVENT_PRIORITY_HIGH = 1

-- ============================================================================
-- Node flag bits (CT_Tree_Walker.h user flags)
-- Stored in handle.flags[node_index] as integer bitmask
-- ============================================================================
M.CT_FLAG_VISITED    = 0x01   -- walker visited flag (engine-managed)
M.CT_FLAG_USER0      = 0x10
M.CT_FLAG_USER1      = 0x20   -- mark for termination
M.CT_FLAG_USER2      = 0x40   -- node initialized
M.CT_FLAG_USER3      = 0x80   -- node enabled
M.CT_FLAG_USER_MASK  = 0xF0   -- all user flag bits

-- ============================================================================
-- Link count mask (bit 15 is auto_start flag in C)
-- ============================================================================
M.CFL_LINK_COUNT_MASK = 0x7FFF
M.CFL_AUTO_START_BIT  = 0x8000

-- ============================================================================
-- Timer changed_mask bits
-- ============================================================================
M.CFL_CHANGED_SECOND = 0x01
M.CFL_CHANGED_MINUTE = 0x02
M.CFL_CHANGED_HOUR   = 0x04
M.CFL_CHANGED_DAY    = 0x08
M.CFL_CHANGED_DOW    = 0x10
M.CFL_CHANGED_DOY    = 0x20

-- ============================================================================
-- Null parent sentinel
-- ============================================================================
M.CFL_NO_PARENT = 0xFFFF

-- ============================================================================
-- Exception catch stages (cfl_exception_support.h)
-- ============================================================================
M.CFL_EXCEPTION_MAIN_LINK     = 1   -- 1-based Lua index into catch_links
M.CFL_EXCEPTION_RECOVERY_LINK = 2
M.CFL_EXCEPTION_FINALIZE_LINK = 3

-- Exception types (for logging)
M.CFL_EXCEPTION_RAISED            = 1
M.CFL_EXCEPTION_HEARTBEAT_TIMEOUT = 2

return M
