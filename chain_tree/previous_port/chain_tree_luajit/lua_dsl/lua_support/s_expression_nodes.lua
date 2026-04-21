local ColumnFlow = require("lua_support.column_flow")

local SExpressionNodes = setmetatable({}, { __index = ColumnFlow })
SExpressionNodes.__index = SExpressionNodes

function SExpressionNodes.new(ctb)
    local self = ColumnFlow.new(ctb)
    return setmetatable(self, SExpressionNodes)
end

function SExpressionNodes:define_s_expression_link(module_name, tree_name, user_data, aux_function_name)
    user_data = user_data or {}
    aux_function_name = aux_function_name or "CFL_NULL"

    local column_data = {
        column_data = {
            module_name = module_name,
            tree_name = tree_name,
            user_data = user_data,
        }
    }

    return self:define_column_link(
        "CFL_S_EXPRESSION_LINK_MAIN",
        "CFL_S_EXPRESSION_LINK_INIT",
        aux_function_name,
        "CFL_S_EXPRESSION_LINK_TERM",
        column_data,
        "S_EXP_LINK_NODE"
    )
end

function SExpressionNodes:define_s_expression_node(column_name, module_name, tree_name, user_data, aux_function_name)
    user_data = user_data or {}
    aux_function_name = aux_function_name or "CFL_NULL"

    local column_data = {
        module_name = module_name,
        tree_name = tree_name,
        user_data = user_data,
    }

    return self:define_column(
        column_name,
        "CFL_S_EXPRESSION_NODE_MAIN",
        "CFL_S_EXPRESSION_NODE_INIT",
        "CFL_S_EXPRESSION_NODE_TERM",
        aux_function_name,
        column_data,
        true,          -- auto_start
        "S_EXP_NODE"   -- label
    )
end

return SExpressionNodes