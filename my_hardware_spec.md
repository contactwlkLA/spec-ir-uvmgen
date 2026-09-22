# Block: simple_timer

The `simple_timer` is a basic peripheral that counts down from a pre-configured value and asserts an interrupt when it reaches zero.

## 1. System Signals
The module operates on a single clock domain and has an asynchronous reset.
* `clk`: 1-bit input. System clock (posedge).
* `rst_n`: 1-bit input. Active-low asynchronous reset.

## 2. APB Register Interface
The programming and control interface is a standard APB3 slave interface named `apb_ctrl`.
* `psel`: 1-bit input. Select line.
* `penable`: 1-bit input. Enable strobe.
* `pwrite`: 1-bit input. Read/write control.
* `paddr`: 8-bit input. Register address.
* `pwdata`: 32-bit input. Write data.
* `prdata`: 32-bit output. Read data.
* `pready`: 1-bit output. Ready flag.

## 3. Dedicated Outputs
* `irq_out`: 1-bit output. Active-high interrupt request asserted when the timer hits zero.

## 4. Registers
* `TIMER_CTRL` at offset `0x00` (32-bit, Read-Write, Reset: 0x00000000):
  - Bit 0: Enable (1 = start timer, 0 = pause timer)
  - Bit 1: Int_Enable (1 = allow IRQ assertion on zero)
* `TIMER_VAL` at offset `0x04` (32-bit, Read-Write, Reset: 0x00000000):
  - Holds the current countdown value.

## 5. UVM Verification Topology (Structural Specification)
The verification environment must adhere to the following structural requirements:

* **UVM Agent Classes**:
  - The APB agent must be of class type `amba_apb_agent`.
  - The Interrupt agent must be of class type `irq_monitor_agent`.

* **UVM Environment**: Named `simple_timer_env`. It must structurally instantiate:
  - An active agent named `m_apb_agent` of type `amba_apb_agent`.
  - A passive agent named `m_irq_agent` of type `irq_monitor_agent`.
  - A Register Block named `regmodel` of type `simple_timer_reg_block`.
  - A Register Adapter named `m_reg_adapter` of type `simple_timer_reg_adapter`.
  - A Register Predictor named `m_reg_predictor` of type `uvm_reg_predictor`.
  - A Scoreboard named `m_scoreboard` of type `simple_timer_scoreboard`.

* **UVM Base Test**: Named `simple_timer_base_test`. It must instantiate `simple_timer_env` as `m_env`.

* **Configuration Database (Config DB) Mappings**:
  - Map `clk_rst_vif` (type `virtual clk_rst_if`) to scope `uvm_test_top.m_env.*` under the field name `vif`.
  - Map `apb_ctrl_vif` (type `virtual apb_if`) to scope `uvm_test_top.m_env.m_apb_agent.*` under the field name `vif`.
  - Map `irq_out_vif` (type `virtual irq_if`) to scope `uvm_test_top.m_env.m_irq_agent.*` under the field name `vif`.
