#!/usr/bin/env lua5.4
-- test_schema.lua
-- Example schema definition

local avro = require("avro_dsl")
avro.export_globals()

FILE("sensor_data")

INCLUDE_BRACKET("stdint.h")
INCLUDE_BRACKET("stdbool.h")
INCLUDE_BRACKET("string.h")

ENUM("sensor_type")
    VALUE("TEMPERATURE", 0)
    VALUE("HUMIDITY", 1)
    VALUE("PRESSURE", 2)
    VALUE("FLOW", 3)
END_ENUM()

ENUM("alarm_level")
    VALUE("NONE", 0)
    VALUE("WARNING", 1)
    VALUE("CRITICAL", 2)
END_ENUM()

FIXED("mac_addr", 6)
FIXED("uuid", 16)

STRING("sensor_name", 32)

RECORD("sensor_reading")
    FIELD("sensor_id", "uint16")
    FIELD("sensor_type", "sensor_type")
    FIELD("value", "float")
    FIELD("timestamp", "uint32")
END_RECORD()

RECORD("alarm_event")
    FIELD("sensor_id", "uint16")
    FIELD("level", "alarm_level")
    FIELD("value", "float")
    FIELD("threshold", "float")
    FIELD("timestamp", "uint32")
END_RECORD()

RECORD("config_update")
    FIELD("sensor_id", "uint16")
    FIELD("sample_rate_ms", "uint16")
    FIELD("threshold_low", "float")
    FIELD("threshold_high", "float")
    FIELD("enabled", "bool")
END_RECORD()

RECORD("heartbeat")
    FIELD("uptime_sec", "uint32")
    FIELD("free_heap", "uint32")
    FIELD("sensor_count", "uint8")
    FIELD("alarm_count", "uint8")
END_RECORD()

-- Generate all outputs
GENERATE_ALL("sensor_data")

