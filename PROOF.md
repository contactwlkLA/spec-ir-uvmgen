# spec-ir-uvmgen — evidence and reproduction

Project: spec-ir-uvmgen 2.0 (SIU 2.0)

**Revision:** 3.4 (2026-09-22 15:40 PDT)
**Date:** 2026-09-22
**Time:** 22:40 UTC
**Status:** Structural milestone complete for timer and concurrent buffer; bounded demonstration evidence, not formal proof.

## What the headline claims mean

The **8/8** result belongs to the buffer Python oracle. **Byte-identical
regeneration** belongs to the timer renderer and its saved baseline. **10 content
checks over 7 emitted files** and **2 defective-copy rejections** belong to the
buffer structural renderer. They are structural and reference demonstrations, not
evidence that the buffer oracle has checked a simulated generated UVM environment.

Earlier local verification in this work session reported the results below.
This document does not bundle raw execution logs or a signed generation manifest.
The source, fixtures, and commands make the checks repeatable; expected output
below is a recognition guide, not a new execution transcript.

| Demonstration | Reported result | Evidence source |
| --- | --- | --- |
| Buffer oracle | 8/8 stories plus ordering guards pass | `material_extracted/test_oracle_traces.py` |
| Timer structural checks | 24/24 on each of two supplied JSON inputs | `uvm_platform/verify_render.py` |
| Buffer structural checks | 10 content checks over 7 emitted SV files; 2 defective copies rejected | `uvm_platform/verify_render.py` |
| Phase A baseline comparison | Seven baseline files byte-identical | `material_extracted/phase_a_runner.py`, `generated_baseline/` |
| Static contract check | Alignment matrix between PRD §5, Python oracle, and generated UVM | `docs/task_6_results.md` |
| Buffer semantic validation | GR-009 PASS | `material_extracted/validate_uvm_buffer_semantics.py`, candidate JSON, DUT PRD |

**Generated UVM has not yet been compiled or run in simulation.** No result here
establishes DUT correctness, complete requirement coverage, or formal proof.

## Reproduction setup

Run from the repository root after the [README setup](README.md#setup), using
Python 3.11 and the pinned dependencies. Do not use Python's `-O` option: the
oracle harness uses assertions for its checks. No API key, LLM, or simulator is
needed. Dependency installation may require network access; these checks do not.

The rendering commands below use a fresh POSIX temporary directory:

```bash
PROOF_DIR="$(mktemp -d)"
```

Keep this shell variable for the commands that follow. Outputs remain there for
inspection. Rendering replaces generated SV output; the Phase A runner replaces
its selected output directory. Use only disposable destinations. No baseline or
tracked generated artifact needs to be changed. Python may create ignored
bytecode caches.

## 1. Eight hand-authored buffer-oracle stories

```bash
python3 material_extracted/test_oracle_traces.py
```

The harness constructs events, invokes the reference oracle, and checks expected
results/state. Its [`build_stories()` and `FINAL_CHECKS`](material_extracted/test_oracle_traces.py)
identify exactly these eight stories:

| Trace | Selected behavior |
| --- | --- |
| LT-001 | Two requests complete out of order |
| LT-005 | Reset flushes outstanding state; IDs can be reused after release |
| LT-007 | Completed write followed by a read of the same address |
| LT-009 | Ready-low time does not advance the response-service watchdog counter |
| LT-012 | Full occupancy with same-edge completion does not create an acceptance slot |
| IT-001 | Unknown response ID is classified as an error |
| IT-002 | Duplicate completion is classified as an error |
| IT-006 | A response for a pre-reset request is classified as stale |

Expected success: a `PASS` line for every story, an ordering-guard `PASS`, and:

```text
MILESTONE MET: 8/8 stories pass
```

The guard separately checks backwards cycles, non-first edge samples, and
duplicate edge samples. The eight-story count does not include these as extra
stories. An illegal story passes when the expected error is detected.

**Limits:** these are hand-derived examples, not an exhaustive proof. LT-009
checks paused service-time accounting; do not interpret it as a complete test
of the exact watchdog-expiry boundary. Positive hold-violation emission and
watchdog-firing paths are not covered by this milestone. Broader scenario and
simulation coverage remains future work. See the
[deferment log](docs/deferment.md) for historical coverage decisions.

## 2. Timer file/content checks

```bash
python3 uvm_platform/verify_render.py \
  material_extracted/simple_timer_blueprint.json --out "$PROOF_DIR/reference"
python3 uvm_platform/verify_render.py \
  material_extracted/my_hardware_spec.extracted.json --out "$PROOF_DIR/extracted"
```

Each command validates the input, derives scopes, invokes the renderer using
the active Python interpreter, and checks the output. Expected messages include:

```text
OK — all 7 expected files present
OK — all 24 content checks passed
```

These checks are specific to the timer fixture. They inspect names, signal
widths, configuration scopes, interfaces, and stub classes. They do not compile
SystemVerilog, evaluate behavior, or constitute a generic verifier for arbitrary
designs. The two input files exercise the same fixture, not two independent DUTs.

For a fresh Markdown extraction feeding this verifier, use the
[README quickstart](README.md#quick-start-spec--ir--uvm-skeleton); the commands
above intentionally test the supplied JSON artifacts.

## 3. Buffer structural checks and defective-copy rejection

```bash
python3 uvm_platform/verify_render.py \
  material_extracted/uvm_buffer_blueprint.json --out "$PROOF_DIR/buffer"
```

The verifier validates the hand-authored buffer Blueprint, derives 5 hierarchical
scopes via `path_assembler.py`, deduplicates the reused `buffer_req_if` interface
(checking declaration compatibility), synthesizes the T3 virtual sequencer stub
(omitting register model stubs via `BUFFER_STUBS`), and checks the output.

Expected messages include:

```text
OK — all 7 expected files present
OK — all 10 content checks passed
```

The 10 content checks verify (see `BUFFER_CONTENT_CHECKS` in `verify_render.py`):
1. `buffer_req_if.sv` declares `req_id` at 8 bits (`ID_W`).
2. `buffer_rsp_if.sv` declares `rsp_rdata` at 32 bits (`DATA_W`).
3. `clk_rst_if.sv` declares `rst` (active-high reset).
4. `uvm_buffer_pkg.sv` emits the `uvm_buffer_vsequencer` stub.
5. `uvm_buffer_pkg.sv` emits `uvm_buffer_scoreboard`.
6. `uvm_buffer_pkg.sv` guards/omits `uvm_buffer_reg_block` (`BUFFER_STUBS`).
7. `uvm_buffer_env.sv` instantiates `m_req_agent_0`.
8. `uvm_buffer_env.sv` does not declare `m_regmodel`.
9. `tb_top.sv` instantiates `req0_vif` and `req1_vif` with the shared `buffer_req_if`.
10. `tb_top.sv` sets the derived scope for `m_req_agent_0` (`uvm_test_top.m_env.m_req_agent_0.*`).

The verifier also exercises two defective copies on disposable output paths:
- `config_db` target-instance mismatch (`target_instance` set to `nonexistent_component`; fails Pydantic validation).
- Shared-interface conflict (`req1_vif` signal width changed to 16; fails `check_interface_compatibility`).

**Limits:** These are structural text and schema assertions, not SystemVerilog
compilation or simulation.

## 4. Byte-identical rendering across the IR split

```bash
python3 material_extracted/phase_a_runner.py \
  material_extracted/simple_timer_blueprint.json \
  --baseline generated_baseline --out "$PROOF_DIR/phase-a"
```

The runner adapts the input, composes semantic and implementation information,
renders it, and compares each baseline file with its output using byte equality.
It prints shortened SHA-256 digests for inspection. Expected summary:

```text
PHASE A RESULT: BYTE-IDENTICAL
```

The comparison covers:

- `apb_if.sv`
- `clk_rst_if.sv`
- `irq_if.sv`
- `simple_timer_base_test.sv`
- `simple_timer_env.sv`
- `simple_timer_pkg.sv`
- `tb_top.sv`

All seven should report `identical`. Missing files or changed baseline-file bytes
fail the check. Extra candidate files produce a warning rather than failure;
the result is therefore a claim about the baseline files, not a strict
whole-directory identity check.

**Limits:** this run starts from JSON; it does not test Markdown extraction.
The saved baseline is a regression fixture, not an independent correctness
oracle. Equal generated bytes do not prove compilation, simulation, or semantic
correctness, and no broader platform/version reproducibility matrix is claimed.

## 5. Buffer semantic-candidate validation

```bash
python3 material_extracted/validate_uvm_buffer_semantics.py
```

Expected summary: `PASS: GR-009 semantic candidate validation`, with 36
requirements (31 DUT, 5 environment), 6 observations, 16 invariants, 8 decisions,
and 10 gates.

The validator checks schema and internal references, matches source ID sets
against the normative portion of [the buffer PRD](uvm_buffer_prd.md), and enforces
the v0.0e/status contract. It deliberately requires
`candidate_pending_human_approval` and `generation_ready: false`.

**Limits:** ID/reference consistency is not proof that every prose requirement
was interpreted correctly. The model is built from maintained Python extraction
tables; validation neither generates the oracle nor promotes the candidate.
GR-010, the generation manifest, remains deferred.

## 6. Static oracle-to-UVM contract check

See [docs/task_6_results.md](docs/task_6_results.md) for the complete 5-column contract
check matrix comparing PRD v0.0e Section 5, the Python reference oracle
(`oracle.py`), and the generated SystemVerilog UVM structural testbench.

Key findings recorded:
- **Interface & Topology Alignment**: 4 interfaces declared, 5 components
  instantiated, and 5 `config_db` scopes derived match PRD requirements.
- **Sole State Ownership**: Preserves OD-008; all 8 semantic state objects solely
  reside in `oracle.py`. The generated `uvm_buffer_scoreboard` holds zero state.
- **`OBS-004` Specification Meaning**: Mapped to test objection drop and final-phase
  zero-outstanding guard in UVM test phase structure.
- **`OBS-006` Three Gaps Resolved**:
  1. *Definition*: Not in PRD §5.1 table; defined in Python metronome hook.
  2. *Consumer ownership*: Python oracle samples pre-edge occupancy directly;
     UVM TLM oracle cannot sample wires directly without breaking TLM boundaries.
  3. *Producer aggregation*: Python combines dual request channels into one sample;
     UVM provides dual independent request agents with independent VIFs.
     Synchronized edge-sampling bridge deferred to simulation.
- **Summary Contract Sentence**:
  > *Oracle interface/topology alignment checked; behavioral equivalence unverified.*

## Not demonstrated yet

- Compilation or simulation of the generated UVM (no VCS, Questa, or Verilator run).
- An integrated generated-UVM-to-Python-oracle observation path.
- Complete buffer requirement/scenario coverage or formal verification.
- Arbitrary natural-language extraction or multi-design generalization.
- Functional external agents, completed RAL/scoreboard behavior, or demonstrated
  real multi-agent coordination in the emitted skeleton.

Use [Architecture](docs/architecture.md) for ownership and integration boundaries,
and the [platform requirements](docs/extensible_uvm_platform_reqspec_v0_3.md)
for detailed goals. A requirements statement or a generated placeholder is not
execution evidence.
