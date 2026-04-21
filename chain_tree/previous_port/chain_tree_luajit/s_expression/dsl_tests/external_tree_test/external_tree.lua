-- function_dictionary_test.lua
-- Test for function dictionary with quad_expr/quad_multi expressions
-- Uses realistic STM32F4 peripheral base addresses
--
-- IMPORTANT: All values that will be read after a stack_push_ref() must be
-- stored in frame locals, NOT scratch (TOS) variables. stack_push advances
-- sp which can invalidate scratch-relative offsets.

local mod = start_module("external_tree")

-- ============================================================================
-- RECORD: cpu_config_blackboard
-- ============================================================================

RECORD("cpu_config_blackboard")
    PTR64_FIELD("fn_dict","void")
    FIELD("fn_hash", "uint32")
    -- GPIO configuration state
    FIELD("gpio_port", "uint32")
    FIELD("gpio_pin", "uint32")
    FIELD("gpio_mode", "uint32")
    FIELD("gpio_speed", "uint32")
    FIELD("gpio_pull", "uint32")
    
    -- UART configuration state
    FIELD("uart_channel", "uint32")
    FIELD("uart_baud", "uint32")
    FIELD("uart_parity", "uint32")
    FIELD("uart_stop_bits", "uint32")
    FIELD("uart_flow_ctrl", "uint32")
    
    -- SPI configuration state
    FIELD("spi_channel", "uint32")
    FIELD("spi_clock_div", "uint32")
    FIELD("spi_mode", "uint32")
    FIELD("spi_bit_order", "uint32")
    
    -- Status fields
    FIELD("config_state", "uint32")
    FIELD("error_code", "uint32")
    FIELD("peripherals_ready", "uint32")
    
    -- Scratch/temp
    FIELD("temp_reg_addr", "uint32")
    FIELD("temp_reg_value", "uint32")
END_RECORD()



-- ============================================================================
-- CONSTANTS
-- ============================================================================

-- GPIO modes
GPIO_MODE_INPUT   = 0x00
GPIO_MODE_OUTPUT  = 0x01
GPIO_MODE_ALT_FN  = 0x02
GPIO_MODE_ANALOG  = 0x03

-- GPIO speed
GPIO_SPEED_LOW    = 0x00
GPIO_SPEED_MED    = 0x01
GPIO_SPEED_HIGH   = 0x02
GPIO_SPEED_VHIGH  = 0x03

-- GPIO pull
GPIO_PULL_NONE    = 0x00
GPIO_PULL_UP      = 0x01
GPIO_PULL_DOWN    = 0x02

-- UART parity
UART_PARITY_NONE  = 0x00
UART_PARITY_EVEN  = 0x01
UART_PARITY_ODD   = 0x02

-- SPI modes
SPI_MODE_0        = 0x00
SPI_MODE_1        = 0x01
SPI_MODE_2        = 0x02
SPI_MODE_3        = 0x03

-- SPI bit order
SPI_MSB_FIRST     = 0x00
SPI_LSB_FIRST     = 0x01

-- Config states
CONFIG_IDLE       = 0
CONFIG_GPIO       = 1
CONFIG_UART       = 2
CONFIG_SPI        = 3
CONFIG_DONE       = 4
CONFIG_ERROR_STATE = 5

-- ============================================================================
-- STM32F4 Peripheral Base Addresses (decimal for expression compiler)
-- ============================================================================

-- RCC (Reset and Clock Control)
RCC_AHB1ENR       = 1073887280  -- 0x40023830  AHB1 peripheral clock enable
RCC_APB1ENR       = 1073887296  -- 0x40023840  APB1 peripheral clock enable
RCC_APB2ENR       = 1073887300  -- 0x40023844  APB2 peripheral clock enable

-- GPIO Port A
GPIOA_BASE        = 1073872896  -- 0x40020000

-- USART1 (on APB2)
USART1_BASE       = 1073811456  -- 0x40011000

-- SPI1 (on APB2)
SPI1_BASE         = 1073819648  -- 0x40013000

-- Clock enable bits
CLK_GPIOA_BIT     = 1           -- AHB1ENR bit 0
CLK_USART1_BIT    = 16          -- APB2ENR bit 4  (0x10)
CLK_SPI1_BIT      = 4096        -- APB2ENR bit 12 (0x1000)

-- Control bits
UE_BIT            = 8192        -- USART CR1 bit 13 (0x2000) - USART Enable
TE_BIT            = 8           -- USART CR1 bit 3  - Transmitter Enable
RE_BIT            = 4           -- USART CR1 bit 2  - Receiver Enable
UART_ENABLE_BITS  = 8204        -- UE | TE | RE = 0x200C

SPE_BIT           = 64          -- SPI CR1 bit 6 (0x40) - SPI Enable

-- ============================================================================
-- TREE DEFINITION
-- ============================================================================

start_tree("function_dictionary")
use_record("cpu_config_blackboard")


local input_dictionary = {
    -- ================================================================
    -- write_register: Low-level register write
    -- Stack params: [addr, value]
    -- ================================================================
    {"write_register", function()
        se_call(2, 0, 0, {}, {
            function()
                local cv = frame_vars({"addr", "value"}, {})
                local c = o_call("write_register")
                end_call(c)
            end
        })
    end},
    
    -- ================================================================
    -- read_modify_write: Read register, apply mask, set bits, write back
    -- Stack params: [addr, clear_mask, set_bits]
    --
    -- All intermediates stored in locals to avoid scratch/push conflicts.
    -- Locals: addr(0), clear_mask(1), set_bits(2), current(3), inv_mask(4)
    -- ================================================================
    {"read_modify_write", function()
        se_call(3, 2, 0, {}, {
            function()
                local cv = frame_vars(
                    {"addr", "clear_mask", "set_bits", "current", "inv_mask"},
                    {}
                )
                -- current = 0 (simulates register read from reset)
                quad_mov(uint_val(0), cv.current)()
                -- inv_mask = ~clear_mask
                quad_not(cv.clear_mask, cv.inv_mask)()
                -- current = current & inv_mask
                quad_and(cv.current, cv.inv_mask, cv.current)()
                -- current = current | set_bits
                quad_or(cv.current, cv.set_bits, cv.current)()
                -- Push addr, current and call write_register
                quad_mov(cv.addr, stack_push_ref())()
                quad_mov(cv.current, stack_push_ref())()
                se_exec_dict_internal("write_register")
            end
        })
    end},
    
    -- ================================================================
    -- enable_peripheral_clock: Enable clock for a peripheral
    -- Stack params: [clock_reg_addr, peripheral_bit]
    -- ================================================================
    {"enable_peripheral_clock", function()
        se_call(2, 0, 0, {}, {
            function()
                local cv = frame_vars({"clk_reg", "periph_bit"}, {})
                -- Push [clk_reg, 0, periph_bit] for read_modify_write
                quad_mov(cv.clk_reg, stack_push_ref())()
                quad_mov(uint_val(0), stack_push_ref())()
                quad_mov(cv.periph_bit, stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
            end
        })
    end},
    
    -- ================================================================
    -- configure_gpio_pin: Full GPIO pin configuration
    -- Stack params: [port_base, pin, mode, speed, pull]
    --
    -- All computed values stored in locals before pushing.
    -- Locals: port_base(0), pin(1), mode(2), speed(3), pull(4),
    --         shift(5), mask(6), reg_addr(7), set_val(8)
    -- ================================================================
    {"configure_gpio_pin", function()
        se_call(5, 4, 1, {}, {
            function()
                local cv = frame_vars(
                    {"port_base", "pin", "mode", "speed", "pull",
                     "shift", "mask", "reg_addr", "set_val"},
                    {"t0"}
                )
                -- Compute bit positions
                quad_expr("shift = pin * 2", cv, {"t0"})()
                quad_expr("mask = 3 << shift", cv, {"t0"})()
                
                -- MODER register: port_base + 0
                quad_expr("set_val = mode << shift", cv, {"t0"})()
                quad_mov(cv.port_base, stack_push_ref())()
                quad_mov(cv.mask, stack_push_ref())()
                quad_mov(cv.set_val, stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
                
                -- OSPEEDR register: port_base + 8
                quad_expr("reg_addr = port_base + 8", cv, {"t0"})()
                quad_expr("set_val = speed << shift", cv, {"t0"})()
                quad_mov(cv.reg_addr, stack_push_ref())()
                quad_mov(cv.mask, stack_push_ref())()
                quad_mov(cv.set_val, stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
                
                -- PUPDR register: port_base + 12
                quad_expr("reg_addr = port_base + 12", cv, {"t0"})()
                quad_expr("set_val = pull << shift", cv, {"t0"})()
                quad_mov(cv.reg_addr, stack_push_ref())()
                quad_mov(cv.mask, stack_push_ref())()
                quad_mov(cv.set_val, stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
            end
        })
    end},
    
    -- ================================================================
    -- configure_uart: Full UART channel setup
    -- Stack params: [usart_base, baud_div, config_bits]
    --
    -- Locals: usart_base(0), baud_div(1), config_bits(2), reg_addr(3)
    -- ================================================================
    {"configure_uart", function()
        se_call(3, 1, 1, {}, {
            function()
                local cv = frame_vars(
                    {"usart_base", "baud_div", "config_bits", "reg_addr"},
                    {"t0"}
                )
                -- Compute CR1 address once, reuse
                quad_expr("reg_addr = usart_base + 12", cv, {"t0"})()
                
                -- Disable USART: clear UE bit in CR1
                quad_mov(cv.reg_addr, stack_push_ref())()
                quad_mov(uint_val(UE_BIT), stack_push_ref())()
                quad_mov(uint_val(0), stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
                
                -- Set baud rate: BRR = base + 8
                quad_expr("reg_addr = usart_base + 8", cv, {"t0"})()
                quad_mov(cv.reg_addr, stack_push_ref())()
                quad_mov(cv.baud_div, stack_push_ref())()
                se_exec_dict_internal("write_register")
                
                -- Set config in CR1
                quad_expr("reg_addr = usart_base + 12", cv, {"t0"})()
                quad_mov(cv.reg_addr, stack_push_ref())()
                quad_mov(uint_val(0), stack_push_ref())()
                quad_mov(cv.config_bits, stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
                
                -- Enable USART: set UE bit in CR1
                quad_mov(cv.reg_addr, stack_push_ref())()
                quad_mov(uint_val(0), stack_push_ref())()
                quad_mov(uint_val(UE_BIT), stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
            end
        })
    end},
    
    -- ================================================================
    -- configure_spi: Full SPI channel setup
    -- Stack params: [spi_base, clock_div, mode, bit_order]
    --
    -- Locals: spi_base(0), clk_div(1), mode(2), bit_order(3), cr1(4)
    -- ================================================================
    {"configure_spi", function()
        se_call(4, 1, 1, {}, {
            function()
                local cv = frame_vars(
                    {"spi_base", "clk_div", "mode", "bit_order", "cr1"},
                    {"t0"}
                )
                -- Disable SPI: clear SPE (bit 6) in CR1 (base + 0)
                quad_mov(cv.spi_base, stack_push_ref())()
                quad_mov(uint_val(SPE_BIT), stack_push_ref())()
                quad_mov(uint_val(0), stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
                
                -- Build CR1: clock_div<<3 | mode | bit_order<<7
                quad_expr("cr1 = clk_div << 3", cv, {"t0"})()
                quad_expr("cr1 = cr1 | mode", cv, {"t0"})()
                quad_expr("t0 = bit_order << 7", cv, {})()
                quad_expr("cr1 = cr1 | t0", cv, {})()
                
                -- Write CR1 (base + 0)
                quad_mov(cv.spi_base, stack_push_ref())()
                quad_mov(cv.cr1, stack_push_ref())()
                se_exec_dict_internal("write_register")
                
                -- Enable SPI: set SPE in CR1
                quad_mov(cv.spi_base, stack_push_ref())()
                quad_mov(uint_val(0), stack_push_ref())()
                quad_mov(uint_val(SPE_BIT), stack_push_ref())()
                se_exec_dict_internal("read_modify_write")
            end
        })
    end},
    
    -- ================================================================
    -- init_all_peripherals: Top-level init that calls sub-configs
    -- ================================================================
    {"init_all_peripherals", function()
        se_sequence_once(function()
            se_log("init_all_peripherals")
            
            -- Enable GPIOA clock (AHB1ENR, bit 0)
            se_push_stack(function() uint(RCC_AHB1ENR) end)
            se_push_stack(function() uint(CLK_GPIOA_BIT) end)
            se_exec_dict_internal("enable_peripheral_clock")
            
            -- Enable USART1 clock (APB2ENR, bit 4)
            se_push_stack(function() uint(RCC_APB2ENR) end)
            se_push_stack(function() uint(CLK_USART1_BIT) end)
            se_exec_dict_internal("enable_peripheral_clock")
            
            -- Enable SPI1 clock (APB2ENR, bit 12)
            se_push_stack(function() uint(RCC_APB2ENR) end)
            se_push_stack(function() uint(CLK_SPI1_BIT) end)
            se_exec_dict_internal("enable_peripheral_clock")
            
            -- Configure GPIO: PA5 as alt-function, high speed, no pull
            se_push_stack(function() uint(GPIOA_BASE) end)
            se_push_stack(function() uint(5) end)
            se_push_stack(function() uint(GPIO_MODE_ALT_FN) end)
            se_push_stack(function() uint(GPIO_SPEED_HIGH) end)
            se_push_stack(function() uint(GPIO_PULL_NONE) end)
            se_exec_dict_internal("configure_gpio_pin")
            
            -- Configure USART1 if enabled
            se_if_then_else(
                se_field_ne("uart_channel", 0),
                function()
                    se_sequence_once(function()
                        se_push_stack(function() uint(USART1_BASE) end)
                        se_push_stack(function() field_ref("uart_baud") end)
                        se_push_stack(function() uint(UART_ENABLE_BITS) end)
                        se_exec_dict_internal("configure_uart")
                        se_log("UART configured")
                    end)
                end,
                function()
                    se_log("UART skipped - channel not set")
                end
            )
            
            -- Configure SPI1 if enabled
            se_if_then_else(
                se_field_ne("spi_channel", 0),
                function()
                    se_sequence_once(function()
                        se_push_stack(function() uint(SPI1_BASE) end)
                        se_push_stack(function() field_ref("spi_clock_div") end)
                        se_push_stack(function() field_ref("spi_mode") end)
                        se_push_stack(function() field_ref("spi_bit_order") end)
                        se_exec_dict_internal("configure_spi")
                        se_log("SPI configured")
                    end)
                end,
                function()
                    se_log("SPI skipped - channel not set")
                end
            )
            
            se_set_field("peripherals_ready", 1)
            se_set_field("config_state", CONFIG_DONE)
        end)
    end},
}

-- ============================================================================
-- MAIN PROGRAM
-- ============================================================================

se_function_interface(function()
    
    -- Initialize register configuration values
    se_i_set_field("uart_channel", 1)
    se_i_set_field("uart_baud", 0x0683)
    se_i_set_field("uart_parity", UART_PARITY_NONE)
    se_i_set_field("uart_stop_bits", 1)
    se_i_set_field("uart_flow_ctrl", 0)
    
    se_i_set_field("spi_channel", 1)
    se_i_set_field("spi_clock_div", 2)
    se_i_set_field("spi_mode", SPI_MODE_0)
    se_i_set_field("spi_bit_order", SPI_MSB_FIRST)
    
    se_i_set_field("gpio_port", 0x40020000)
    se_i_set_field("gpio_pin", 5)
    se_i_set_field("gpio_mode", GPIO_MODE_ALT_FN)
    se_i_set_field("gpio_speed", GPIO_SPEED_HIGH)
    se_i_set_field("gpio_pull", GPIO_PULL_NONE)
    
    se_i_set_field("config_state", CONFIG_IDLE)
    se_i_set_field("error_code", 0)
    se_i_set_field("peripherals_ready", 0)

    -- Load dictionary and execute
    se_load_function_dict("fn_dict", input_dictionary)
    
    se_exec_dict_fn_ptr("fn_dict", "fn_hash")
   
    se_return_function_terminate()
end)

end_tree("function_dictionary")

RECORD("call_blackboard")
    PTR64_FIELD("tree_pointer","void")
    FIELD("dictionary_hash", "uint32")
END_RECORD()

start_tree("call_tree")
use_record("call_blackboard")

se_function_interface(function()
    se_spawn_tree("tree_pointer",'function_dictionary',128)
    se_set_hash_field("dictionary_hash", "init_all_peripherals")
    dictionary_offset, dictionary_size = get_field_offset("cpu_config_blackboard", "fn_hash")
    
    se_set_external_field("dictionary_hash", "tree_pointer", dictionary_offset)
    se_tick_tree("tree_pointer")
    se_log("call_tree: called")
    se_return_function_terminate()
end)
end_tree("call_tree")
return end_module(mod)