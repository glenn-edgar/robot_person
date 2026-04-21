-- json_extract_test.lua
-- Comprehensive test for all dictionary extraction functions
-- Four passes:
--   Pass 1: String path extraction
--   Pass 2: Hash path extraction
--   Pass 3: Array element access via index paths
--   Pass 4: Sub-dictionary pointer storage and extraction

local mod = start_module("json_test")

-- ============================================================================
-- RECORD DEFINITION
-- ============================================================================

RECORD("extract_state")
    -- Dictionary pointers
    PTR64_FIELD("dict_string", "void")    -- String-keyed dictionary
    PTR64_FIELD("dict_hash", "void")      -- Hash-keyed dictionary
    
    -- Pass counter
    FIELD("pass_number", "uint32")
    
    -- Integer extractions
    FIELD("int_val_1", "int32")
    FIELD("int_val_2", "int32")
    FIELD("int_val_3", "int32")
    
    -- Unsigned integer extractions
    FIELD("uint_val_1", "uint32")
    FIELD("uint_val_2", "uint32")
    FIELD("uint_val_3", "uint32")
    
    -- Float extractions
    FIELD("float_val_1", "float")
    FIELD("float_val_2", "float")
    FIELD("float_val_3", "float")
    
    -- Bool extractions (stored as int)
    FIELD("bool_val_1", "uint32")
    FIELD("bool_val_2", "uint32")
    FIELD("bool_val_3", "uint32")
    
    -- Hash extractions
    FIELD("hash_val_1", "uint32")
    FIELD("hash_val_2", "uint32")
    FIELD("hash_val_3", "uint32")
    
    -- Array test fields (Pass 3)
    FIELD("arr_int_0", "int32")
    FIELD("arr_int_1", "int32")
    FIELD("arr_int_2", "int32")
    FIELD("arr_int_3", "int32")
    FIELD("arr_float_0", "float")
    FIELD("arr_float_1", "float")
    FIELD("arr_float_2", "float")
    FIELD("arr_nested_0_id", "uint32")
    FIELD("arr_nested_0_val", "float")
    FIELD("arr_nested_1_id", "uint32")
    FIELD("arr_nested_1_val", "float")
    FIELD("arr_nested_2_id", "uint32")
    FIELD("arr_nested_2_val", "float")
    
    -- Pointer test fields (Pass 4)
    PTR64_FIELD("sub_integers", "void")    -- Pointer to integers sub-dict
    PTR64_FIELD("sub_floats", "void")      -- Pointer to floats sub-dict
    PTR64_FIELD("sub_nested_0", "void")    -- Pointer to items[0] dict
    PTR64_FIELD("sub_nested_1", "void")    -- Pointer to items[1] dict
    FIELD("ptr_int_pos", "int32")
    FIELD("ptr_int_neg", "int32")
    FIELD("ptr_float_pi", "float")
    FIELD("ptr_float_neg", "float")
    FIELD("ptr_n0_id", "uint32")
    FIELD("ptr_n0_val", "float")
    FIELD("ptr_n1_id", "uint32")
    FIELD("ptr_n1_val", "float")
END_RECORD()

-- ============================================================================
-- TEST CONFIGURATION DATA
-- ============================================================================

local config = {
    -- Integers (positive, negative, zero)
    integers = {
        positive = 12345,
        negative = -9876,
        zero = 0,
        nested = {
            deep = {
                value = 42
            }
        }
    },
    
    -- Unsigned integers
    unsigned = {
        small = 100,
        medium = 50000,
        large = 0xFFFF,
        nested = {
            deep = {
                value = 255
            }
        }
    },
    
    -- Floats
    floats = {
        pi = 3.14159,
        negative = -273.15,
        zero = 0.0,
        nested = {
            deep = {
                value = 2.71828
            }
        }
    },
    
    -- Booleans (as 0/1)
    bools = {
        true_val = 1,
        false_val = 0,
        nested = {
            deep = {
                value = 1
            }
        }
    },
    
    -- Hashes (stored as strings, will be hashed)
    hashes = {
        state_idle = "idle",
        state_running = "running",
        state_error = "error",
        nested = {
            deep = {
                value = "deep_hash"
            }
        }
    },
    
    -- Arrays for Pass 3
    int_array = {10, 20, 30, 40},
    float_array = {1.5, 2.5, 3.5},
    items = {
        {id = 100, value = 10.1},
        {id = 200, value = 20.2},
        {id = 300, value = 30.3},
    },
    
    -- Mixed depth test
    level1 = {
        level2 = {
            level3 = {
                level4 = {
                    final_int = 999,
                    final_float = 1.5,
                    final_bool = 1
                }
            }
        }
    }
}

-- ============================================================================
-- TREE DEFINITION
-- ============================================================================

start_tree("json_test")
use_record("extract_state")

se_function_interface(function()

    -- ========================================================================
    -- Load both dictionary formats
    -- ========================================================================
    
    se_load_dictionary("dict_string", config)
    se_load_dictionary_hash("dict_hash", config)
    
    -- Initialize pass counter
    se_set_field("pass_number", 0)
    
    -- ========================================================================
    -- PASS 1: String path extraction (dict_string)
    -- ========================================================================
    
    se_log("=== PASS 1: String Path Extraction ===")
    se_increment_field("pass_number", 1)
    
    -- Integer extractions via string path
    se_dict_extract_int("dict_string", "integers.positive", "int_val_1")
    se_dict_extract_int("dict_string", "integers.negative", "int_val_2")
    se_dict_extract_int("dict_string", "integers.nested.deep.value", "int_val_3")
    
    -- Unsigned extractions via string path
    se_dict_extract_uint("dict_string", "unsigned.small", "uint_val_1")
    se_dict_extract_uint("dict_string", "unsigned.medium", "uint_val_2")
    se_dict_extract_uint("dict_string", "unsigned.nested.deep.value", "uint_val_3")
    
    -- Float extractions via string path
    se_dict_extract_float("dict_string", "floats.pi", "float_val_1")
    se_dict_extract_float("dict_string", "floats.negative", "float_val_2")
    se_dict_extract_float("dict_string", "floats.nested.deep.value", "float_val_3")
    
    -- Bool extractions via string path
    se_dict_extract_bool("dict_string", "bools.true_val", "bool_val_1")
    se_dict_extract_bool("dict_string", "bools.false_val", "bool_val_2")
    se_dict_extract_bool("dict_string", "bools.nested.deep.value", "bool_val_3")
    
    -- Hash extractions via string path
    se_dict_extract_hash("dict_string", "hashes.state_idle", "hash_val_1")
    se_dict_extract_hash("dict_string", "hashes.state_running", "hash_val_2")
    se_dict_extract_hash("dict_string", "hashes.nested.deep.value", "hash_val_3")
    
    -- Print Pass 1 results
    local print1 = o_call("USER_PRINT_EXTRACT_RESULTS")
        str("Pass 1 - String Paths")
        field_ref("pass_number")
        field_ref("int_val_1")
        field_ref("int_val_2")
        field_ref("int_val_3")
        field_ref("uint_val_1")
        field_ref("uint_val_2")
        field_ref("uint_val_3")
        field_ref("float_val_1")
        field_ref("float_val_2")
        field_ref("float_val_3")
        field_ref("bool_val_1")
        field_ref("bool_val_2")
        field_ref("bool_val_3")
        field_ref("hash_val_1")
        field_ref("hash_val_2")
        field_ref("hash_val_3")
    end_call(print1)
    
    -- ========================================================================
    -- Clear fields for Pass 2
    -- ========================================================================
    
    se_set_field("int_val_1", 0)
    se_set_field("int_val_2", 0)
    se_set_field("int_val_3", 0)
    se_set_field("uint_val_1", 0)
    se_set_field("uint_val_2", 0)
    se_set_field("uint_val_3", 0)
    se_set_field("float_val_1", 0)
    se_set_field("float_val_2", 0)
    se_set_field("float_val_3", 0)
    se_set_field("bool_val_1", 0)
    se_set_field("bool_val_2", 0)
    se_set_field("bool_val_3", 0)
    se_set_field("hash_val_1", 0)
    se_set_field("hash_val_2", 0)
    se_set_field("hash_val_3", 0)
    
    -- ========================================================================
    -- PASS 2: Hash path extraction (dict_hash)
    -- ========================================================================
    
    se_log("=== PASS 2: Hash Path Extraction ===")
    se_increment_field("pass_number", 1)
    
    -- Integer extractions via hash path
    se_dict_extract_int_h("dict_hash", 
        {"integers", "positive"}, 
        "int_val_1")
    se_dict_extract_int_h("dict_hash", 
        {"integers", "negative"}, 
        "int_val_2")
    se_dict_extract_int_h("dict_hash", 
        {"integers", "nested", "deep", "value"}, 
        "int_val_3")
    
    -- Unsigned extractions via hash path
    se_dict_extract_uint_h("dict_hash", 
        {"unsigned", "small"}, 
        "uint_val_1")
    se_dict_extract_uint_h("dict_hash", 
        {"unsigned", "medium"}, 
        "uint_val_2")
    se_dict_extract_uint_h("dict_hash", 
        {"unsigned", "nested", "deep", "value"}, 
        "uint_val_3")
    
    -- Float extractions via hash path
    se_dict_extract_float_h("dict_hash", 
        {"floats", "pi"}, 
        "float_val_1")
    se_dict_extract_float_h("dict_hash", 
        {"floats", "negative"}, 
        "float_val_2")
    se_dict_extract_float_h("dict_hash", 
        {"floats", "nested", "deep", "value"}, 
        "float_val_3")
    
    -- Bool extractions via hash path
    se_dict_extract_bool_h("dict_hash", 
        {"bools", "true_val"}, 
        "bool_val_1")
    se_dict_extract_bool_h("dict_hash", 
        {"bools", "false_val"}, 
        "bool_val_2")
    se_dict_extract_bool_h("dict_hash", 
        {"bools", "nested", "deep", "value"}, 
        "bool_val_3")
    
    -- Hash extractions via hash path
    se_dict_extract_hash_h("dict_hash", 
        {"hashes", "state_idle"}, 
        "hash_val_1")
    se_dict_extract_hash_h("dict_hash", 
        {"hashes", "state_running"}, 
        "hash_val_2")
    se_dict_extract_hash_h("dict_hash", 
        {"hashes", "nested", "deep", "value"}, 
        "hash_val_3")
    
    -- Print Pass 2 results
    local print2 = o_call("USER_PRINT_EXTRACT_RESULTS")
        str("Pass 2 - Hash Paths")
        field_ref("pass_number")
        field_ref("int_val_1")
        field_ref("int_val_2")
        field_ref("int_val_3")
        field_ref("uint_val_1")
        field_ref("uint_val_2")
        field_ref("uint_val_3")
        field_ref("float_val_1")
        field_ref("float_val_2")
        field_ref("float_val_3")
        field_ref("bool_val_1")
        field_ref("bool_val_2")
        field_ref("bool_val_3")
        field_ref("hash_val_1")
        field_ref("hash_val_2")
        field_ref("hash_val_3")
    end_call(print2)
    
    -- ========================================================================
    -- PASS 3: Array element access via index paths
    -- ========================================================================
    
    se_log("=== PASS 3: Array Element Access ===")
    se_increment_field("pass_number", 1)
    
    -- Integer array: int_array = {10, 20, 30, 40}
    se_dict_extract_int("dict_string", "int_array.0", "arr_int_0")
    se_dict_extract_int("dict_string", "int_array.1", "arr_int_1")
    se_dict_extract_int("dict_string", "int_array.2", "arr_int_2")
    se_dict_extract_int("dict_string", "int_array.3", "arr_int_3")
    
    -- Float array: float_array = {1.5, 2.5, 3.5}
    se_dict_extract_float("dict_string", "float_array.0", "arr_float_0")
    se_dict_extract_float("dict_string", "float_array.1", "arr_float_1")
    se_dict_extract_float("dict_string", "float_array.2", "arr_float_2")
    
    -- Array of dicts: items[n].id, items[n].value
    se_dict_extract_uint("dict_string", "items.0.id", "arr_nested_0_id")
    se_dict_extract_float("dict_string", "items.0.value", "arr_nested_0_val")
    se_dict_extract_uint("dict_string", "items.1.id", "arr_nested_1_id")
    se_dict_extract_float("dict_string", "items.1.value", "arr_nested_1_val")
    se_dict_extract_uint("dict_string", "items.2.id", "arr_nested_2_id")
    se_dict_extract_float("dict_string", "items.2.value", "arr_nested_2_val")
    
    -- Print Pass 3 results
    local print3 = o_call("USER_PRINT_ARRAY_RESULTS")
        str("Pass 3 - Array Access")
        field_ref("pass_number")
        field_ref("arr_int_0")
        field_ref("arr_int_1")
        field_ref("arr_int_2")
        field_ref("arr_int_3")
        field_ref("arr_float_0")
        field_ref("arr_float_1")
        field_ref("arr_float_2")
        field_ref("arr_nested_0_id")
        field_ref("arr_nested_0_val")
        field_ref("arr_nested_1_id")
        field_ref("arr_nested_1_val")
        field_ref("arr_nested_2_id")
        field_ref("arr_nested_2_val")
    end_call(print3)
    
 -- ========================================================================
    -- PASS 4: Sub-dictionary pointer storage and extraction
    -- Tests both string-path and hash-path pointer storage
    -- ========================================================================
    
    se_log("=== PASS 4: Pointer Storage and Extraction ===")
    se_increment_field("pass_number", 1)
    
    -- Store pointers using string paths (from dict_string)
    se_dict_store_ptr("dict_string", "integers", "sub_integers")
    se_dict_store_ptr("dict_string", "floats", "sub_floats")
    
    -- Store pointers using string paths into array elements
    se_dict_store_ptr("dict_string", "items.0", "sub_nested_0")
    se_dict_store_ptr("dict_string", "items.1", "sub_nested_1")
    
    -- Extract from sub_integers pointer using string paths
    se_dict_extract_int("sub_integers", "positive", "ptr_int_pos")
    se_dict_extract_int("sub_integers", "negative", "ptr_int_neg")
    
    -- Extract from sub_floats pointer using string paths
    se_dict_extract_float("sub_floats", "pi", "ptr_float_pi")
    se_dict_extract_float("sub_floats", "negative", "ptr_float_neg")
    
    -- Extract from array element pointers using string paths
    se_dict_extract_uint("sub_nested_0", "id", "ptr_n0_id")
    se_dict_extract_float("sub_nested_0", "value", "ptr_n0_val")
    se_dict_extract_uint("sub_nested_1", "id", "ptr_n1_id")
    se_dict_extract_float("sub_nested_1", "value", "ptr_n1_val")
    
    -- Print Pass 4 results
    local print4 = o_call("USER_PRINT_POINTER_RESULTS")
        str("Pass 4 - String Pointer Extraction")
        field_ref("pass_number")
        field_ref("ptr_int_pos")
        field_ref("ptr_int_neg")
        field_ref("ptr_float_pi")
        field_ref("ptr_float_neg")
        field_ref("ptr_n0_id")
        field_ref("ptr_n0_val")
        field_ref("ptr_n1_id")
        field_ref("ptr_n1_val")
    end_call(print4)
    
    -- ========================================================================
    -- PASS 5: Hash-path pointer storage and extraction
    -- ========================================================================
    
    se_log("=== PASS 5: Hash Pointer Storage and Extraction ===")
    se_increment_field("pass_number", 1)
    
    -- Clear pointer fields
    se_set_field("ptr_int_pos", 0)
    se_set_field("ptr_int_neg", 0)
    se_set_field("ptr_float_pi", 0)
    se_set_field("ptr_float_neg", 0)
    se_set_field("ptr_n0_id", 0)
    se_set_field("ptr_n0_val", 0)
    se_set_field("ptr_n1_id", 0)
    se_set_field("ptr_n1_val", 0)
    
    -- Store pointers using hash paths (from dict_hash)
    se_dict_store_ptr_h("dict_hash", {"integers"}, "sub_integers")
    se_dict_store_ptr_h("dict_hash", {"floats"}, "sub_floats")
    
    -- Store pointers into array elements using hash paths
    se_dict_store_ptr_h("dict_hash", {"items", "0"}, "sub_nested_0")
    se_dict_store_ptr_h("dict_hash", {"items", "1"}, "sub_nested_1")
    
    -- Extract from sub_integers pointer using hash paths
    se_dict_extract_int_h("sub_integers", {"positive"}, "ptr_int_pos")
    se_dict_extract_int_h("sub_integers", {"negative"}, "ptr_int_neg")
    
    -- Extract from sub_floats pointer using hash paths
    se_dict_extract_float_h("sub_floats", {"pi"}, "ptr_float_pi")
    se_dict_extract_float_h("sub_floats", {"negative"}, "ptr_float_neg")
    
    -- Extract from array element pointers using hash paths
    se_dict_extract_uint_h("sub_nested_0", {"id"}, "ptr_n0_id")
    se_dict_extract_float_h("sub_nested_0", {"value"}, "ptr_n0_val")
    se_dict_extract_uint_h("sub_nested_1", {"id"}, "ptr_n1_id")
    se_dict_extract_float_h("sub_nested_1", {"value"}, "ptr_n1_val")
    
    -- Print Pass 5 results
    local print5 = o_call("USER_PRINT_POINTER_RESULTS")
        str("Pass 5 - Hash Pointer Extraction")
        field_ref("pass_number")
        field_ref("ptr_int_pos")
        field_ref("ptr_int_neg")
        field_ref("ptr_float_pi")
        field_ref("ptr_float_neg")
        field_ref("ptr_n0_id")
        field_ref("ptr_n0_val")
        field_ref("ptr_n1_id")
        field_ref("ptr_n1_val")
    end_call(print5)
    -- ========================================================================
    -- Final verification (all 4 passes)
    -- ========================================================================
    
    local verify = o_call("USER_VERIFY_RESULTS")
    end_call(verify)
    
    se_return_terminate()
end)

end_tree("json_test")

return end_module(mod)