-- ============================================================================
-- se_chain_tree.lua — ChainTree bridge function helpers for S-Engine DSL
--
-- These wrap the CFL_* oneshot/predicate functions registered via
-- cfl_se_get_oneshot_table() and cfl_se_get_pred_table().
-- ============================================================================

-- ============================================================================
-- Child control (oneshot)
-- ============================================================================

function cfl_enable_children()
    local c = o_call("CFL_ENABLE_CHILDREN")
    end_call(c)
end

function cfl_disable_children()
    local c = o_call("CFL_DISABLE_CHILDREN")
    end_call(c)
end

function cfl_i_disable_children()
    local c = io_call("CFL_DISABLE_CHILDREN")
    end_call(c)
end

function cfl_enable_child(index)
    local c = o_call("CFL_ENABLE_CHILD")
        int(index)
    end_call(c)
end

function cfl_disable_child(index)
    local c = o_call("CFL_DISABLE_CHILD")
        int(index)
    end_call(c)
end

-- ============================================================================
-- Internal event (oneshot)
-- ============================================================================

function cfl_internal_event(event_id_val, event_data_val)
    local c = o_call("CFL_INTERNAL_EVENT")
        int(event_id_val)
        int(event_data_val)
    end_call(c)
end

-- ============================================================================
-- Bitmask predicates
-- ============================================================================

function cfl_s_bit_or_start()
    return p_call("CFL_S_BIT_OR")
end

function cfl_s_bit_and_start()
    return p_call("CFL_S_BIT_AND")
end

function cfl_s_bit_nor_start()
    return p_call("CFL_S_BIT_NOR")
end

function cfl_s_bit_nand_start()
    return p_call("CFL_S_BIT_NAND")
end

function cfl_s_bit_xor_start()
    return p_call("CFL_S_BIT_XOR")
end

function cfl_bit_entry(...)
    for _, bit_index in ipairs({...}) do
        int(bit_index)
    end
end

-- ============================================================================
-- JSON reads (oneshot) — read from ChainTree node JSON into blackboard
-- field_name: blackboard field path (supports nested: "sensors.temperature")
-- json_path:  JSON path in node data (e.g. "node_dict.column_data.user_data.x")
-- ============================================================================

function cfl_json_read_int(field_name, json_path)
    local c = o_call("CFL_JSON_READ_INT")
        nested_field_ref(field_name)
        str_ptr(json_path)
    end_call(c)
end

function cfl_json_read_uint(field_name, json_path)
    local c = o_call("CFL_JSON_READ_UINT")
        nested_field_ref(field_name)
        str_ptr(json_path)
    end_call(c)
end

function cfl_json_read_float(field_name, json_path)
    local c = o_call("CFL_JSON_READ_FLOAT")
        nested_field_ref(field_name)
        str_ptr(json_path)
    end_call(c)
end

function cfl_json_read_bool(field_name, json_path)
    local c = o_call("CFL_JSON_READ_BOOL")
        nested_field_ref(field_name)
        str_ptr(json_path)
    end_call(c)
end

function cfl_json_read_string_buf(field_name, json_path)
    local c = o_call("CFL_JSON_READ_STRING_BUF")
        nested_field_ref(field_name)
        str_ptr(json_path)
    end_call(c)
end

function cfl_json_read_string_ptr(field_name, json_path)
    local c = o_call("CFL_JSON_READ_STRING_PTR")
        nested_field_ref(field_name)
        str_ptr(json_path)
    end_call(c)
end

-- ============================================================================
-- Constant record copy (oneshot)
-- ============================================================================

function cfl_copy_const(field_name, const_name)
    local c = o_call("CFL_COPY_CONST")
        field_ref(field_name)
        const_ref(const_name)
    end_call(c)
end

function cfl_copy_const_full(const_name)
    local c = o_call("CFL_COPY_CONST_FULL")
        const_ref(const_name)
    end_call(c)
end

-- ============================================================================
-- Set/clear bitmask bits (oneshot)
-- ============================================================================

function cfl_set_bits(...)
    local c = o_call("CFL_SET_BITS")
        for _, bit_index in ipairs({...}) do
            int(bit_index)
        end
    end_call(c)
end

function cfl_clear_bits(...)
    local c = o_call("CFL_CLEAR_BITS")
        for _, bit_index in ipairs({...}) do
            int(bit_index)
        end
    end_call(c)
end
