# spec-ir-uvmgen 2.0

Project: spec-ir-uvmgen 2.0 (SIU 2.0)

**Revision:** 3.4 (2026-09-22 15:05 PDT)
**Status:** Structural milestone complete for timer and concurrent buffer.

A deterministic spec-to-UVM prototype for verification engineers exploring
validated intermediate representations and reproducible code generation.
The demonstrated generator converts the structured Markdown `simple_timer`
specification and the PRD-derived concurrent-buffer Blueprint into deterministic
UVM SystemVerilog skeletons. A separate concurrent-buffer prototype exercises
a Python reference oracle against hand-authored traces.

## Current validation boundary

Converts a natural-language hardware spec (`simple_timer`) and a PRD-derived
Blueprint (`uvm_buffer`) into validated intermediate representations, then
generates UVM verification environments from them. The timer IR, buffer
structural Blueprint, and the Python reference oracle are proven — 8/8 hand-authored
traces, 10 structural content checks across 7 emitted buffer files, 2 defective-copy
rejection checks, and byte-identical timer regeneration. The generated UVM has
not yet been compiled or run in simulation; behavioral equivalence and dynamic
simulation remain explicitly deferred.

The evidence below scopes these claims to the supplied fixtures and Python
checks, not formal proof or a completed hardware-verification flow.

## Architecture at a glance

![Architecture overview: timer structural generation track, buffer semantic/oracle track, and buffer structural generation track, with future UVM simulation integration marked as future](docs/diagrams/spec-ir-uvmgen-architecture.png)

Two related tracks share the spec-first methodology; they are not yet one
integrated generator/simulator/oracle pipeline:

```text
Timer:  structured spec → validated SemanticIR + implementation contract
                       → Jinja2 renderer → seven UVM SystemVerilog files

Buffer: DUT PRD → maintained semantic tables → candidate JSON → validation
        DUT PRD → Python event contracts + reference oracle
                ← eight hand-authored observation traces
        DUT PRD → hand-authored uvm_buffer_blueprint.json (PRD §6 topology + D1/D2 mock params)
                → Jinja2 renderer (interface deduplication + T3 stub)
                → seven UVM SystemVerilog files (10 structural content checks)
```

The timer extractor owns specification facts. The renderer derives instance
names, configuration scopes, and implementation stubs. The buffer oracle owns
expected lifecycle results; it is hand-written Python, not generated from the
timer IR. The buffer Blueprint derives from PRD §6 topology with concrete D1/D2
parameters, rendering deduplicated interfaces and buffer-specific stubs.
See [Architecture](docs/architecture.md) for boundaries and file roles.

## Setup

Python **3.11** is the tested version. The commands below use a POSIX shell and
start at the repository root. Python dependencies are pinned in
[requirements.txt](requirements.txt); no LLM credentials or simulator are needed
for these demonstrations.

```bash
python3 -m venv venv
. venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Quick start: spec → IR → UVM skeleton

Use a fresh temporary directory so the example does not overwrite tracked
fixtures or generated evidence:

```bash
DEMO_DIR="$(mktemp -d)"

# 1. Timer: spec → IR → UVM skeleton (7 files, 24 checks)
python3 material_extracted/extract_blueprint.py my_hardware_spec.md \
  --out "$DEMO_DIR/timer.extracted.json"
python3 uvm_platform/verify_render.py "$DEMO_DIR/timer.extracted.json" \
  --out "$DEMO_DIR/timer_uvm"

# 2. Buffer: PRD-derived Blueprint → UVM skeleton (7 files, 10 checks)
python3 uvm_platform/verify_render.py material_extracted/uvm_buffer_blueprint.json \
  --out "$DEMO_DIR/buffer_uvm"

printf 'Inspect generated files in %s/timer_uvm and %s/buffer_uvm\n' "$DEMO_DIR" "$DEMO_DIR"
```

Expected result: Blueprint validation succeeds for both designs.
- **Timer**: Emits seven SV files with **24 content checks** passing (three interfaces, package, env, test, `tb_top.sv`).
- **Buffer**: Emits seven SV files with **10 content checks** passing (deduplicated `buffer_req_if`, `buffer_rsp_if`, `clk_rst_if`, package with T3 vsequencer stub, env with dual request agents, test, `tb_top.sv`).
These are structural checks, not compilation or simulation. The timer parser expects the section/table structure of [my_hardware_spec.md](my_hardware_spec.md); arbitrary prose is not a demonstrated input format.

Output directories are disposable: rendering replaces generated SV files, and
the Phase A runner replaces its selected output directory. Do not point either
at valuable files. Temporary results remain available for inspection; Python may
also create ignored bytecode caches.

## Demonstrated results

| Check | Reported result | What it establishes |
| --- | --- | --- |
| Timer renderer | 24/24 content checks on each of two supplied Blueprint files | Expected timer files, names, scopes, and placeholders |
| Phase A IR split | Seven rendered files byte-identical to `generated_baseline/` | Fixture-level render regression across the IR split |
| Buffer renderer | 10 content checks over 7 emitted SV files; 2 defective copies rejected | Expected buffer files, shared interface deduplication (`buffer_req_if`), T3 vsequencer stub, and scope wiring |
| Buffer oracle | 8/8 hand-authored stories, plus ordering guards | Selected legal and illegal lifecycle observations produce expected Python verdicts |
| Static contract check | §5 contract check matrix ([docs/task_6_results.md](docs/task_6_results.md)) | Interface and topology alignment between PRD, Python oracle, and generated UVM |
| Buffer semantic candidate | GR-009 PASS: 36 requirements, 6 observations, 16 invariants, 8 decisions, 10 gates | Schema and reference consistency; not generation readiness |

[PROOF.md](PROOF.md) provides commands, evidence locations, expected output, and
coverage limits. The byte comparison concerns the timer fixture; the eight
stories concern the separate buffer oracle.

## Limitations and next work

- **Finishing line reached for structural integration:**
  - Both designs have validated Blueprint representations that render clean 7-file UVM structural skeletons.
  - Interface deduplication resolves shared interface types (`buffer_req_if`) while rejecting incompatible declarations.
  - Per-design stub selection (`BUFFER_STUBS` vs `TIMER_STUBS`) guards register model stubs from designs without register blocks.
  - Static contract matrix ([docs/task_6_results.md](docs/task_6_results.md)) records interface/topology alignment and documents behavioral equivalence boundaries.
- **Implemented vs. deferred boundaries:**
  - *Implemented:* Blueprint schema validation, Jinja2 template rendering, interface deduplication, configuration scope assembly, structural content assertions, and Python reference oracle.
  - *Explicitly deferred:* SystemVerilog compilation, dynamic UVM simulation, procedural test sequences, driver/monitor run phases, TLM scoreboard/oracle comparison, and SVA property compilation.
- **Resume-ready limits:**
  - Future simulation work should resume at: (1) implementing procedural driver and monitor sequences for the buffer request/response agents, (2) adding the synchronized metronome/edge-sample monitor to resolve the OBS-006 bridge gap, and (3) connecting the UVM scoreboard TLM ports to the Python reference oracle (or an equivalent SystemVerilog implementation).
- The eight oracle stories are a milestone subset, not complete DUT requirement
  coverage. Positive hold-violation and watchdog-firing coverage remains outside
  that milestone; see [PROOF.md](PROOF.md).
- The buffer semantic model remains `candidate_pending_human_approval` with
  `generation_ready: false`. Validation does not promote it.
- The LLM extraction path was removed. General arbitrary-spec extraction,
  multi-design generalization, and real multi-agent coordination are not demonstrated.
- Verification Intent IR and the generation manifest are deferred. Simulation
  and the connection between generated monitors and the Python oracle are future
  integration work, not an existing runnable command.

## Documentation and authority

- [Architecture](docs/architecture.md): implemented tracks and ownership.
- [Evidence and reproduction](PROOF.md): claims, commands, and limits.
- [Buffer structural contract check](docs/task_6_results.md) and
  [structural integration task list](docs/task-2-0.md): milestone evidence for
  the buffer Blueprint → UVM structural path.
- [Authoritative platform requirements](docs/extensible_uvm_platform_reqspec_v0_3.md):
  detailed architectural goals and open questions; Draft v0.3 is not a claim
  that all requirements are implemented.
- [Buffer DUT PRD](uvm_buffer_prd.md): authoritative buffer behavioral contract.
- [Semantic agreements](docs/AGREEMENTS.md) and [deferment log](docs/deferment.md):
  decisions and historical deferrals.
- [IR-split design note](material_extracted/design_ir_split.md),
  [FLOW](docs/FLOW.md), [CONTINUATION](docs/CONTINUATION.md), and
  [deprecated platform PRD](docs/prd.md): development history; older phase counts,
  commands, and session references are not current public quickstart guidance.

## License and attribution

[MIT License](LICENSE). spec-ir-uvmgen builds on ideas from the cited paper
[HAVEN (arXiv:2604.27643)](https://arxiv.org/abs/2604.27643); it is not a
reproduction of that project's results.
