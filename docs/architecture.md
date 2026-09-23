# spec-ir-uvmgen architecture

Project: spec-ir-uvmgen 2.0 (SIU 2.0)

**Revision:** 3.4 (2026-09-22 15:20 PDT)
**Date:** 2026-09-22
**Time:** 22:20 UTC
**Status:** Structural milestone complete for timer and concurrent buffer.

## Scope: two structural generation paths, one reference oracle, future integration

The long-term direction is specification → validated IR → generated UVM →
observations checked by an oracle. The repository does **not** yet implement
that complete connected flow. Today it demonstrates:
1. **Structural UVM generation for two designs**:
   - `simple_timer`: structured Markdown spec → validated IR → 7 SV files.
   - `uvm_buffer`: PRD-derived hand-authored Blueprint → 7 SV files (shared-interface deduplication, T3 stub synthesis).
2. **A separate buffer semantic/reference-oracle prototype** (8/8 hand-authored traces).
3. **A static contract check** ([task_6_results.md](task_6_results.md)) mapping PRD verification intent to the generated UVM skeleton.

The [platform requirement specification](extensible_uvm_platform_reqspec_v0_3.md)
is the detailed architectural reference. The [buffer PRD](../uvm_buffer_prd.md)
defines the buffer's behavior. Requirements and proposed seams must not be
confused with demonstrated implementation.

## 1. Timer: specification → IR → UVM generation

```text
my_hardware_spec.md
  → extract_blueprint.py
  → schema-validated SemanticIR/Blueprint JSON
  + ImplementationContract
  → scope assembly, stub synthesis, instance naming
  → render_blueprint.py + Jinja2 templates
  → seven SystemVerilog files
  → verify_render.py content checks
```

| Responsibility | Existing implementation |
| --- | --- |
| Parse the structured Markdown fixture | `material_extracted/extract_blueprint.py` |
| Validate extracted facts and cross-references | `material_extracted/blueprint_schema.py` |
| Separate semantic facts from implementation choices; adapt legacy input | `material_extracted/blueprint_ir_split.py` |
| Derive configuration scopes from instance structure | `material_extracted/path_assembler.py` |
| Compose the input, synthesize stubs, apply instance prefixes, emit files | `uvm_platform/render_blueprint.py` and `uvm_platform/templates/` |
| Check expected timer files and content | `uvm_platform/verify_render.py` |
| Compare IR-split rendering with the saved baseline | `material_extracted/phase_a_runner.py` and `generated_baseline/` |

Paths in this table are relative to the repository root. Both schema and adapter
code use Blueprint/SemanticIR terminology; the conceptual distinction is
**specification facts versus renderer-owned implementation choices**, not a
promise that every Python type has the same representation.

The extractor describes interfaces, signals, topology, and configuration links.
The implementation contract supplies such choices as configuration scopes,
instance-name prefixes, and the virtual-sequencer stub. The renderer emits three
interface files plus the timer package, environment, base test, and top module.

The supported demonstration uses the section/table conventions of
[the timer specification](../my_hardware_spec.md). It is not a general-purpose
natural-language interpretation service. The former LLM extraction path is
removed.

## 2. Buffer: hand-authored Blueprint → structural UVM generation

```text
uvm_buffer_prd.md (§6 topology, §3.1 concrete parameters)
  → hand-authored material_extracted/uvm_buffer_blueprint.json
  → blueprint_schema.py validation
  → path_assembler.py scope derivation (5 hierarchical scopes)
  → render_blueprint.py (interface deduplication, BUFFER_STUBS synthesis)
  → seven SystemVerilog files
  → verify_render.py content assertions (10 checks) + rejection of defective copies
```

| Responsibility | Existing implementation |
| --- | --- |
| Author buffer Blueprint from PRD topology & concrete mock parameters | `material_extracted/uvm_buffer_blueprint.json` |
| Validate extracted Blueprint schema, keys, and cross-references | `material_extracted/blueprint_schema.py` |
| Deduplicate reused interface types (`buffer_req_if`) with compatibility checks | `uvm_platform/render_blueprint.py` (`check_interface_compatibility`) |
| Control per-design stub emission (`BUFFER_STUBS`: T3 vsequencer only) | `material_extracted/blueprint_ir_split.py` & `uvm_platform/render_blueprint.py` |
| Derive hierarchical configuration scopes | `material_extracted/path_assembler.py` |
| Emit 7 SV files (`buffer_req_if`, `buffer_rsp_if`, `clk_rst_if`, pkg, env, test, `tb_top`) | `uvm_platform/render_blueprint.py` + templates |
| Check expected buffer files, scope wiring, and reject defective copies | `uvm_platform/verify_render.py` |

The buffer Blueprint maps PRD §6 topology and §3.1 concrete parameter widths
(`MAX_CAPACITY=16, ID_W=8, ADDR_W=8, DATA_W=32, OP_W=1, STATUS_W=1, DELAY_W=4`)
with mock protocol encodings (`READ=0, WRITE=1, OK=0`).

### Structural boundary

The generated buffer UVM files represent structural scaffolding only:
- Reused interface types (`buffer_req_if.sv` shared by `req0_vif` and `req1_vif`)
  are emitted once; declaration compatibility checking prevents conflicting signal
  widths or declarations.
- Register model and register adapter placeholders are guarded and omitted from
  `uvm_buffer_pkg.sv` because the buffer contains no register block; `BUFFER_STUBS`
  emits only the T3 virtual sequencer stub (`uvm_buffer_vsequencer`).
- SystemVerilog compilation with commercial simulators, dynamic simulation,
  procedural sequences, driver/monitor run phases, TLM scoreboard/oracle comparison,
  and SVA property compilation remain explicitly deferred.

## 3. Buffer: semantic candidate and Python reference oracle

```text
uvm_buffer_prd.md
  → maintained extraction tables in extract_uvm_buffer_semantics.py
  → uvm_buffer_semantic_model.candidate.json
  → semantic_schema.py + validate_uvm_buffer_semantics.py

uvm_buffer_prd.md
  → hand-written oracle_events.py + oracle.py
  ← hand-authored observation streams in test_oracle_traces.py
  → expected lifecycle results, hold violations, and diagnostics
```

The semantic builder deterministically serializes maintained Python tables. It
does not automatically interpret arbitrary PRD prose, generate the Python oracle,
or feed the timer renderer. GR-009 checks the candidate's schema, internal
references, source ID sets, and revision/status contract. A passing candidate
still has `generation_ready: false` and awaits human approval.

### Oracle ownership and event order

[`oracle.py`](../material_extracted/oracle.py) owns outstanding transactions,
occupancy, reset epoch, the service counter/watchdog, expected memory contents,
and completed/flushed ID history. These are reference-model states, not a
simulation of an implemented DUT.

The hand-authored harness calls `tick(cycle, rst, rsp_ready)` and supplies events
in this order:

1. `EdgeSample` — first event, using beginning-of-edge occupancy.
2. `ResetTransition` — reset dominates that edge.
3. `CompletedResponse` — a completion does not free a same-edge acceptance slot.
4. `AcceptedRequest`.

The ordering guard rejects backwards cycles, duplicate edge samples, and a
non-first edge sample. Event and result records are defined in
[`oracle_events.py`](../material_extracted/oracle_events.py). `OracleResult` and
`HoldViolationRecord` are verdict records; the diagnostic `reports` list is not
another verdict channel.

The eight stories test selected oracle behavior directly. They do not drive
SystemVerilog, and passing them does not validate a generated scoreboard or DUT.

## 4. Evidence boundaries

See [PROOF.md](../PROOF.md) for the authoritative public reproduction commands.

- The timer verifier checks seven expected files and 24 content patterns.
- The buffer verifier checks seven expected files and 10 content patterns, and confirms rejection of 2 defective copies.
- The Phase A runner renders a supplied timer JSON fixture and compares its
  baseline files byte-for-byte; it does not re-extract Markdown itself.
- The buffer harness checks eight selected stories plus ordering guards.
- The static contract check ([task_6_results.md](task_6_results.md)) records the
  alignment matrix between PRD §5, the Python oracle, and the generated UVM skeleton.
- GR-009 validates semantic structure/reference consistency, not full behavioral
  correctness or generation readiness.

`generated/` and `generated_baseline/` are retained timer artifacts. The baseline
is a frozen regression reference, not an independently verified implementation.
Use disposable output directories when reproducing results; never hand-edit
fixtures to make a check pass.

## 5. Future UVM → oracle integration

This is the missing connection, not an implemented stage:

```text
Future DUT + generated UVM simulation
  → request/response/reset observations
  → integration with the oracle's event contract
  → scoreboard/verdict reporting
```

No demonstrated simulator bridge currently supplies those events. Generated
`tb_top.sv` still requires DUT and clock/reset integration; external agents and
functional register-model/scoreboard behavior remain necessary. Compilation,
simulation, complete buffer coverage, and multi-design extensibility have not
been established.

Verification Intent IR, the generation manifest, and actual multi-agent
coordination remain deferred. The semantic candidate's status must not be
promoted merely because the Python checks pass.
