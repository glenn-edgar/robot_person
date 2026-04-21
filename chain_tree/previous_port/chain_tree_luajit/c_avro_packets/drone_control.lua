require("avro_dsl").export_globals()

--------------------------------------------------------------------------------
-- FILE DECLARATION
--------------------------------------------------------------------------------
FILE("drone_control")

INCLUDE_BRACKET("stdint.h")
INCLUDE_BRACKET("stdbool.h")
INCLUDE_BRACKET("string.h")
INCLUDE_STRING("avro_common.h")

--------------------------------------------------------------------------------
-- COMMON STRUCTURES
--------------------------------------------------------------------------------
--[[
STRUCT("packet_header")
    FIELD("device_id", "uint16")
    FIELD("seq", "uint16")
    FIELD("timestamp", "double")
END_STRUCT()
]]--
POINTER("finalize_data")

--------------------------------------------------------------------------------
-- FLY STRAIGHT (handler_id: 0, 1)
--------------------------------------------------------------------------------
RECORD("fly_straight_request")          -- handler_id 0
    FIELD("distance", "float")
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("heading", "float")
    FIELD("finalize", "finalize_data")
END_RECORD()

RECORD("fly_straight_response")        
    FIELD("distance", "float")
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("heading", "float")
    FIELD("success", "bool")
    FIELD("error_code", "int32")
END_RECORD()

--------------------------------------------------------------------------------
-- FLY ARC (handler_id: 2, 3)
--------------------------------------------------------------------------------
RECORD("fly_arc_request")               -- handler_id 2
    FIELD("distance", "float")
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("heading", "float")
    FIELD("finalize", "finalize_data")
END_RECORD()

RECORD("fly_arc_response")        
    FIELD("distance", "float")
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("heading", "float")
    FIELD("success", "bool")
    FIELD("error_code", "int32")
END_RECORD()

--------------------------------------------------------------------------------
-- FLY UP (handler_id: 4, 5)
--------------------------------------------------------------------------------
RECORD("fly_up_request")                -- handler_id 4
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("finalize", "finalize_data")
END_RECORD()

RECORD("fly_up_response")              
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("success", "bool")
    FIELD("error_code", "int32")
END_RECORD()

--------------------------------------------------------------------------------
-- FLY DOWN (handler_id: 6, 7)
--------------------------------------------------------------------------------
RECORD("fly_down_request")              -- handler_id 6
    FIELD("final_altitude", "float")
    FIELD("final_speed", "float")
    FIELD("finalize", "finalize_data")
END_RECORD()

RECORD("fly_down_response")     
    FIELD("final_altitude", "float")        -- handler_id 7
    FIELD("final_speed", "float")
    FIELD("success", "bool")
    FIELD("error_code", "int32")
END_RECORD()

-------------------------------------------------------------------------------
-- GENERATE OUTPUT
--------------------------------------------------------------------------------
GENERATE()

