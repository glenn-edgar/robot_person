require("avro_dsl").export_globals()

FILE("stream_test_1")
INCLUDE_BRACKET("stdint.h")
INCLUDE_BRACKET("stdbool.h")
INCLUDE_BRACKET("string.h")
INCLUDE_STRING("avro_common.h")

RECORD("accelerometer_reading")
    FIELD("x", "float")
    FIELD("y", "float")
    FIELD("z", "float")
END_RECORD()

RECORD("accelerometer_reading_filtered")
    FIELD("x", "float")
    FIELD("y", "float")
    FIELD("z", "float")
END_RECORD()

--GENERATE()

CONST_PACKET("accelerometer_reading", "default_accel_reading", 0)
    SET("x", 0.0)
    SET("y", 0.0)
    SET("z", 9.81)
END_CONST_PACKET()

GENERATE_ALL()