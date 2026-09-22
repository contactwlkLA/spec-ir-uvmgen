# spec-ir-uvmgen — evidence and reproduction

**Revision:** 3
**Date:** 2026-09-22
**Time:** 02:22 UTC
**Status:** Initial public documentation draft; bounded demonstration evidence, not formal proof.

## What the headline claims mean

The **8/8** result belongs to the buffer Python oracle. **Byte-identical
regeneration** belongs to the timer renderer and its saved baseline. They are
separate demonstrations, not evidence that the buffer oracle has checked a
simulated generated UVM environment.

Earlier local verification in this work session reported the results below.
This document does not bundle raw execution logs or a signed generation manifest.
The source, fixtures, and commands make the checks repeatable; expected output
below is a recognition guide, not a new execution transcript.

| Demonstration | Reported result | Evidence source |
| --- | --- | --- |
| Buffer oracle | 8/8 stories plus ordering guards pass | `material_extracted/test_oracle_traces.py` |
| Timer structural checks | 24/24 on each of two supplied JSON inputs | `uvm_platform/verify_render.py` |
| Phase A baseline comparison | Seven baseline files byte-identical | `material_extracted/phase_a_runner.py`, `generated_baseline/` |
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

## 3. Byte-identical rendering across the IR split

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

## 4. Buffer semantic-candidate validation

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

## Not demonstrated yet

- Compilation or simulation of the generated UVM.
- An integrated generated-UVM-to-Python-oracle observation path.
- Complete buffer requirement/scenario coverage or formal verification.
- Arbitrary natural-language extraction or multi-design generalization.
- Functional external agents, completed RAL/scoreboard behavior, or demonstrated
  real multi-agent coordination in the emitted skeleton.

Use [Architecture](docs/architecture.md) for ownership and integration boundaries,
and the [platform requirements](docs/extensible_uvm_platform_reqspec_v0_3.md)
for detailed goals. A requirements statement or a generated placeholder is not
execution evidence.
