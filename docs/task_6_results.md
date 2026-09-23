# Task 6 Results: Static Oracle-to-UVM Contract Check (§5)

Project: spec-ir-uvmgen 2.0 (SIU 2.0)
Revision: 0 (New evidence note)
Date: 2026-09-22
Time: 21:55 UTC (14:55 PDT)
Source Document: `uvm_buffer_prd.md` (v0.0e)
Task Reference: `docs/task-2-0.md` Task 6 (plan: `merge_to_buf_str_pt_plan_5.md` Rev 5, §4)

---

> **Oracle interface/topology alignment checked; behavioral equivalence unverified.**

---

## Executive Summary & Evidence Boundary

This document records the static contract check comparing the normative verification intent in **PRD v0.0e Section 5** (`uvm_buffer_prd.md`), the **Python Reference Oracle** (`material_extracted/oracle.py`, `oracle_events.py`), and the **generated SystemVerilog UVM structural testbench** (`material_extracted/uvm_buffer_blueprint.json`, `uvm_platform/verify_render.py`).

### Evidence Framing
- **Python Reference Oracle**: Proven across 8/8 hand-authored trace stories (`test_oracle_traces.py`) plus metronome ordering guards.
- **Structural SystemVerilog Generation**: Blueprint schema validation, emission of 7 SV files, 10 structural content checks across the 7 files, 2 defective-copy rejection checks, and timer baseline non-regression are implemented in `uvm_platform/verify_render.py`. Committed execution logs and status doc synchronization belong to Tasks 7–10.
- **Behavioral Simulation**: UVM runtime phase execution, dynamic TLM port connections, procedural driver/monitor sequences, and SVA compilation remain deferred (`[DEF-SIM]`).

---

## Static Contract Check Matrix

Verdicts use the Plan §5 standard enum:
- **`Match`**: Structural types, signals, or responsibilities align completely between PRD, Python oracle, and Blueprint/UVM skeleton.
- **`Mismatch`**: Architectural divergence, semantic gap, or structural incompatibility identified.
- **`Not implemented`**: Defined in PRD/Python but behavioral SystemVerilog implementation is deferred to simulation stages.
- **`Not checked`**: Outside the current structural milestone timebox.

### 1. Observations Contract (§5.1, §5.1.1, §5.1.2)

| Contract item | Python evidence | Blueprint/UVM evidence | Result | Limitation/action |
|:---|:---|:---|:---:|:---|
| **`OBS-001`** (Accepted request) | `AcceptedRequest` (`oracle_events.py:64-74`) | `buffer_req_if.sv`: `req_valid, req_hold, req_id[7:0], req_addr[7:0], req_op, req_wdata[31:0], req_delay[3:0]` | **Match** | Structural signals match PRD widths; sampling logic in monitor is deferred (`[DEF-SIM]`). |
| **`OBS-002`** (Completed response) | `CompletedResponse` (`oracle_events.py:77-86`) | `buffer_rsp_if.sv`: `rsp_valid, rsp_ready, rsp_id[7:0], rsp_rdata[31:0], rsp_status` | **Match** | Structural signals match PRD widths; monitor `observation_seq` tagging is deferred (`[DEF-SIM]`). |
| **`OBS-003`** (Reset transition) | `ResetTransition` (`oracle_events.py:88-97`) | `clk_rst_if.sv`: `clk, rst` (1-bit active-high synchronous) | **Match** | Raw transition wire declared; reset monitor component instantiated in env (`m_reset_monitor`). |
| **`OBS-004`** (Termination request) | Harness `FINAL_CHECKS` (`test_oracle_traces.py:490-502`) checks `occupancy == 0` | `uvm_buffer_base_test.sv`: UVM test phase structure | **Not implemented** | **Establish specification meaning**: PRD §5.1 lists `OBS-004` as a termination request event (`cycle, outstanding_count, reset_epoch`). In Python it is checked at harness finish; in UVM it maps to test objection drop and final-phase zero-outstanding guard (`[DEF-SIM]`). |
| **`OBS-005`** (Protocol violation) | `ProtocolViolation` (`oracle_events.py:100-113`) | Interface declarations in `buffer_req_if`, `buffer_rsp_if` | **Not implemented** | SV SVA protocol assertion compilation deferred per `docs/deferment.md`. |
| **`OBS-006`** (Metronome edge sample) | `EdgeSample` (`oracle_events.py:115-127`), consumed by `_on_edge_sample` (`oracle.py:166-196`) | Interfaces instantiated in `tb_top.sv` (`req0_vif`, `req1_vif`) | **Mismatch** | **Three reported gaps resolved**: (1) *Definition gap*: OBS-006 is not in PRD §5.1 table, but defined in Python as metronome hook. (2) *Consumer ownership gap*: Python oracle reads pre-edge occupancy directly; UVM TLM oracle cannot sample wires directly without breaking transaction-level separation. (3) *Producer aggregation gap*: Python combines `req_hold[1:0]` and `req_valid[1:0]` into one sample; UVM has two independent request agents (`m_req_agent_0`, `m_req_agent_1`) with independent VIFs. Defer synchronized edge-sampling bridge to simulation stage. |
| **`OracleResult`** (`ORACLE-RESULT-001`) | `OracleResult` (`oracle_events.py:134-149`), produced by `_complete_legal` / `_invalid_result` (`oracle.py:292-340`) | Package placeholder in `uvm_buffer_pkg.sv` | **Not implemented** | Complete expected-result calculation proven in Python reference; SV UVM oracle class implementation deferred. |
| **`HoldViolationRecord`** (`HOLD-VIOLATION-001`) | `HoldViolationRecord` (`oracle_events.py:151-161`), emitted in `_on_edge_sample` (`oracle.py:178`) and `_flush_guarantees` (`oracle.py:204`) | SVA assertion hooks | **Not implemented** | Proven in Python reference model; SystemVerilog SVA property emission deferred. |

---

### 2. Checker & Component Responsibilities (§5.2)

| Contract item | Python evidence | Blueprint/UVM evidence | Result | Limitation/action |
|:---|:---|:---|:---:|:---|
| **Request Agents 0 & 1** | Scripted request generation in `test_oracle_traces.py` | `uvm_buffer_env.sv`: instantiates `m_req_agent_0` and `m_req_agent_1` (`buffer_req_agent`) with derived scopes | **Match** | Structural instances and VIF links match; agent driver/sequencer logic is external/vendor (`[DEF-SIM]`). |
| **Response Monitor** | Scripted response generation in `test_oracle_traces.py` | `uvm_buffer_env.sv`: instantiates `m_rsp_agent` (`buffer_rsp_agent`) with scope `uvm_test_top.m_env.m_rsp_agent.*` | **Match** | Structural monitor agent instance and VIF link match; procedural monitor sequence is deferred (`[DEF-SIM]`). |
| **Reset Monitor** | Scripted reset transitions in `test_oracle_traces.py` | `uvm_buffer_env.sv`: instantiates `m_reset_monitor` (`buffer_reset_monitor_agent`) with scope `uvm_test_top.m_env.m_reset_monitor.*` | **Match** | Structural reset monitor instance and VIF link match; procedural sampling is deferred (`[DEF-SIM]`). |
| **Lifecycle Oracle** | `LifecycleOracle` (`oracle.py`) solely owns all 8 state objects | Python reference proven (8/8 traces); omitted from package stubs | **Match** | OD-008 strictly preserved: oracle solely owns semantic state. SV oracle component deferred to simulation. |
| **Scoreboard** | Assertions in `test_oracle_traces.py` pair expected/actual | `uvm_buffer_pkg.sv`: emits `uvm_buffer_scoreboard`; instantiated in `uvm_buffer_env.sv` | **Match** | Scoreboard placeholder exists structurally; owns zero semantic state (OD-008). Dynamic TLM comparison deferred. |
| **Base Test** | Harness trace runner (`build_stories()`) | `uvm_buffer_base_test.sv`: base test class emitted | **Match** | Base test instantiates `uvm_buffer_env`; procedural test sequences deferred. |

---

### 3. Normative Invariants (§5.3)

| Contract item | Python evidence | Blueprint/UVM evidence | Result | Limitation/action |
|:---|:---|:---|:---:|:---|
| **`INV-001`** (Accepted entry) | `_on_accept` (`oracle.py:263`: `self.outstanding_table[ev.id] = ev`) | `buffer_req_if.sv` request handshake signals | **Match** | Structural interface supports handshake; oracle book proven in Python. |
| **`INV-002`** (Completed match) | `_complete_legal` (`oracle.py:293`: `self.outstanding_table.pop(ev.id)`) | `buffer_rsp_if.sv` response handshake signals | **Match** | Structural interface supports handshake; lookup proven in Python. |
| **`INV-003`** (Duplicate/unknown fail) | `_on_completion` (`oracle.py:281-289`, `IT-001`, `IT-002`) | `buffer_rsp_if.sv`: `rsp_id` width (8 bits) | **Match** | Verified on illegal traces in Python; response ID width declared in SV. |
| **`INV-004`** (Capacity 0..16) | `_on_accept` / `_complete_legal` (`oracle.py:265, 295`, `LT-012`) | Blueprint `spec_source` D1 concrete constraints (`MAX_CAPACITY=16`) | **Match** | Capacity bounded in Python oracle; parameter documented in Blueprint. |
| **`INV-005`** (Reset flushes state) | `_on_reset` (`oracle.py:229-239`, `LT-005`) | `clk_rst_if.sv`: synchronous `rst` | **Match** | Proven on `LT-005`; synchronous reset signal declared in SV. |
| **`INV-006`** (Stale pre-reset fail) | `_on_completion` (`oracle.py:275-280`, `IT-006`) | `buffer_rsp_if.sv` status signal | **Match** | Proven on `IT-006` using `flushed_id_set` reservation; SV interface declared. |
| **`INV-007`** (Termination zero-outstanding) | Harness `FINAL_CHECKS` (`test_oracle_traces.py:490-502`) | `uvm_buffer_base_test.sv` phase structure | **Not implemented** | Enforced in Python harness; UVM phase check deferred to simulation. |
| **`INV-008`** (Read data visibility) | `_complete_legal` (`oracle.py:301, 313`, `LT-007`, `LT-008`) | Payload data width (32-bit `DATA_W`) in `buffer_req_if`, `buffer_rsp_if` | **Match** | Proven on `LT-007/008` in Python; data bus widths declared in SV. |
| **`INV-009`** (Occupancy book equality) | `_on_accept` / `_complete_legal` (`oracle.py:265, 295`) | N/A (oracle-internal book) | **Match** | Internal invariant of reference oracle; no SV wire counterpart needed. |
| **`INV-010`** (Request hold stability) | Stimulus check (`LT-010`) | `buffer_req_if.sv` wire declarations | **Not implemented** | Protocol stability checked in Python harness; SVA assertions deferred (`[DEF-SIM]`). |
| **`INV-011`** (Response stall stability) | Stimulus check (`LT-011`) | `buffer_rsp_if.sv` wire declarations | **Not implemented** | Protocol stability checked in Python harness; SVA assertions deferred (`[DEF-SIM]`). |
| **`INV-012`** (Legal completion status OK) | `_complete_legal` (`oracle.py:324`: `expected_status=STATUS_OK`) | `buffer_rsp_if.sv`: `rsp_status` (1-bit `STATUS_W`) | **Match** | Proven in Python; `STATUS_W` width declared in SV interface. |
| **`INV-013`** (256-cycle service bound) | `tick` (`oracle.py:117-123`, `LT-009`, `IT-008`) | Blueprint `spec_source` D1/D2 parameter record | **Match** | Watchdog service counter proven in Python; parameter documented in Blueprint. |
| **`INV-014`** (No handshake in reset) | `tick` / `_on_reset` (`oracle.py:108-109, 223-241`) | Interface signals in `clk_rst_if`, `buffer_req_if`, `buffer_rsp_if` | **Match** | Protocol invariant checked in Python; interface wires declared in SV. |
| **`INV-015`** (1:1 response pairing) | `_on_completion` (`oracle.py:290`: `self.results.append(result)`) | `uvm_buffer_pkg.sv`: `uvm_buffer_scoreboard` placeholder | **Match** | Proven in Python; scoreboard skeleton instantiated in UVM env. |
| **`INV-016`** (Hold threshold & guarantee) | `_on_edge_sample` (`oracle.py:175-186`) and `_flush_guarantees` (`oracle.py:202-211`) | Shared `buffer_req_if.sv` dual instances (`req0_vif`, `req1_vif`) | **Match** | Threshold arm proven on `LT-012` in Python; guarantee arm non-firing proven; dual request interfaces declared in SV. |

---

### 4. Failure & Mutation Contract (§5.4)

| Contract item | Python evidence | Blueprint/UVM evidence | Result | Limitation/action |
|:---|:---|:---|:---:|:---|
| **Duplicate completion** | Verified in `oracle.py:281` (`IT-002`) | `buffer_rsp_if.sv` response ID width declared | **Match** | Proven in Python oracle; response interface declared in SV. |
| **Unknown completion** | Verified in `oracle.py:286` (`IT-001`) | `buffer_rsp_if.sv` response ID width declared | **Match** | Proven in Python oracle; response interface declared in SV. |
| **Stale response after reset** | Verified in `oracle.py:275` (`IT-006`) | `clk_rst_if.sv` synchronous reset declared | **Match** | Proven in Python oracle; reset interface declared in SV. |
| **Watchdog expiration** | Bound verified in `oracle.py:117` (`LT-009`) | Watchdog parameter recorded in Blueprint D1/D2 | **Match** | Milestone checks bound; positive watchdog firing (`IT-008`) reserved for 25-scenario exit pass. |
| **Same-edge hold race** | Verified in `oracle.py:175` (`LT-012`) | Dual request interfaces in `tb_top.sv` | **Match** | Proven on `LT-012` (occupancy 16 cushion slot observed). |
| **Corrupted response data** | Deferred to dynamic scoreboard | Data bus declared in `buffer_rsp_if.sv` | **Not implemented** | Deferred to UVM simulation stage (`[DEF-SIM]`). |
| **Premature objection drop** | Verified in `test_oracle_traces.py` (`IT-007`) | Test phase structure in `uvm_buffer_base_test.sv` | **Not implemented** | Deferred to UVM simulation stage (`[DEF-SIM]`). |

---

## 5. Summary & Hand-Off Boundary

1. **Alignment Established**:
   - Schema and topology contracts align completely: 4 interfaces declared, 5 components instantiated, and 5 config_db scopes derived.
   - All 8 semantic state objects strictly reside in the reference oracle (`oracle.py`); the scoreboard placeholder carries zero state, preserving OD-008.
   - Dual request agents share `buffer_req_if` without collision; register classes are cleanly guarded and omitted.
2. **Behavioral Boundary Maintained**:
   - Python reference oracle is proven on 8/8 milestone traces plus ordering guards.
   - SystemVerilog artifacts provide structural scaffolding only.
   - Compilation with VCS/Xcelium/Verilator, procedural driver/monitor code, and dynamic TLM communication remain deferred.
