# FLOW — current state and direction

Project: spec-ir-uvmgen 2.0 (SIU 2.0)

**Revision:** 3.4 (2026-09-22 15:34 PDT)

Quick map of where we are, what each piece does, and what's next. Read this
when you've lost track (you will — there are a lot of moving parts).

## The one-sentence version

Spec facts are represented in Pydantic-validated Blueprint JSON (either extracted
deterministically or hand-authored from a PRD); the Blueprint is rendered into
deterministic UVM SystemVerilog skeletons by a Jinja2 pipeline. Dynamic simulation
and procedural sequences remain explicitly deferred.

## Where things live

```
spec-ir-uvmgen/
├── README.md            # entry point — goals, source-of-truth, layout
├── PROOF.md             # evidence, reproduction commands, limits
├── my_hardware_spec.md  # smoke-test spec (single-agent simple_timer)
├── uvm_buffer_prd.md    # authoritative concurrent buffer PRD
├── docs/                # secondary documentation
│   ├── FLOW.md                # this file — pipeline + phase status
│   ├── architecture.md        # boundaries, file roles, evidence limits
│   └── task_6_results.md      # static oracle-to-UVM contract check (§5)
├── material_extracted/  # extraction & IR layer
│   ├── blueprint_schema.py             # Pydantic models — structural validation
│   ├── blueprint_ir_split.py           # SemanticIR + ImplementationContract (per-design stubs)
│   ├── path_assembler.py               # derives uvm_config_db scopes & compatibility checks
│   ├── simple_timer_blueprint.json     # reference timer Blueprint (6 comp)
│   ├── my_hardware_spec.extracted.json # deterministic timer extractor output
│   ├── extract_blueprint.py            # deterministic regex parser for timer spec
│   ├── uvm_buffer_blueprint.json       # hand-authored buffer Blueprint (PRD §6 topology)
│   ├── oracle.py                       # buffer Python reference oracle (8/8 traces)
│   └── test_oracle_traces.py           # hand-authored buffer trace harness
├── uvm_platform/        # render layer
│   ├── render_blueprint.py    # Blueprint → SV (interface dedup, stub synthesis)
│   ├── verify_render.py       # structural verifier (timer: 24 checks; buffer: 10 checks)
│   └── templates/             # Jinja2 — one .sv.j2 per artifact type
│       ├── interface.sv.j2
│       ├── package.sv.j2
│       ├── env.sv.j2
│       ├── test.sv.j2
│       └── tb_top.sv.j2
└── generated/           # SV output (disposable, rewritten each run)
```

Three-layer split: spec (text) → extracted/IR (data) → generated (SV). The
extraction/IR layer defines what counts as a valid Blueprint; the render
layer consumes that contract.

## The data flow

```
[Timer Path]
my_hardware_spec.md
        │
        ├──► extract_blueprint.py (regex parser)
        │         │
        │         ▼
        │    Blueprint.model_validate(...)
        │         │
        └────► my_hardware_spec.extracted.json
                  │
                  ▼
             path_assembler.assemble_scopes(...)
                  │
                  ▼
             render_blueprint.py (TIMER_STUBS)
                  │
                  ▼
             generated/*.sv (7 files, 24 checks)

[Buffer Path]
uvm_buffer_prd.md (§6 topology, §3.1 concrete D1/D2 mock parameters)
        │
        ▼
   uvm_buffer_blueprint.json (hand-authored)
        │
        ▼
   Blueprint.model_validate(...)
        │
        ▼
   path_assembler.assemble_scopes(...) (5 scopes derived)
        │
        ▼
   render_blueprint.py (shared-interface dedup for buffer_req_if, BUFFER_STUBS T3-only)
        │
        ▼
   generated/*.sv (7 files, 10 content checks + 2 defective copies rejected)
```

## Phase status

| # | Phase | Status | What it proves |
|---|---|---|---|
| 0 | Cleanup & canonical home | **done** | One pipeline, one archive. No accidental two-schema confusion. |
| 1 | Renderer w/ no LLM | **done** | Blueprint → SV loop closes. 24 content checks pass. T1 addendum, T3 stub, T2 placeholders all emitted. |
| 2 | Deterministic extractor | **done** | `extract_blueprint.py my_hardware_spec.md` produces byte-identical SV to the hand-crafted reference. |
| 3 | LLM caller | **removed (deterministic-only by design)** | `query_llm.py` + prompts deleted; spec-extraction variance would make two runs undiffable. |
| 4 | Multi-agent / T3 real | much later | Only after single-agent runs clean for several iterations. |
| A | IR-split spike (Phase A) | **done** | `blueprint_ir_split.py` splits Blueprint into SemanticIR + ImplementationContract. `phase_a_runner.py` proves byte-identical render across the seam. |
| B | Extractors emit SemanticIR only | **done** | `extract_blueprint.py` no longer adds T3 vsequencer stub. Renderer synthesizes stubs from ImplementationContract. |
| C | Renderer consumes new shape | **done** | `render_blueprint.render(blueprint: ComposedBlueprint, out_dir)` synthesizes stubs from implementation, then runs PIPELINE. Legacy file-based entry still works. 24/24 on both Blueprint files. |
| D | Buffer structural integration | **done** | Hand-authored `uvm_buffer_blueprint.json` renders 7 SV files. Reused `buffer_req_if` deduplicated with compatibility checks. 10 structural content checks pass; 2 defective copies rejected. Timer baseline byte-identical. |
| E | Static oracle-to-UVM contract check | **done** | Static contract matrix (`docs/task_6_results.md`) checks alignment between PRD §5, Python reference oracle, and generated UVM interfaces/topology. |
| F | Dynamic simulation & verification | **deferred** | SV compilation (VCS/Questa/Verilator), dynamic UVM simulation, procedural sequences, driver/monitor run phases, TLM scoreboard/oracle wiring, and SVA compilation remain explicitly deferred. |
| G | Verification Intent IR | **deferred** | Multi-design semantic representation deferred until forced. |

## Key reqspec tenets and where they live in the code

| Tenet | Where enforced | Notes |
|---|---|---|
| **T1** no direct wiring | `path_assembler.py` + `tb_top.sv.j2` | Scope strings derived from instance tree, never spec-owned. The `tb_top.sv.j2` template iterates `config_db` entries — it does not receive a path string. |
| **T1 addendum** shared keys | `InterfaceAsset.key`, `ConfigDBEntry.interface_ref`, `Blueprint._config_db_entries_reference_real_things` | Cross-references go through keys. Renaming a key requires only changing the Blueprint; no string convention to drift. |
| **T2** SystemRDL/RAL | `simple_timer_reg_block` / `simple_timer_reg_adapter` in `package.sv.j2` | Placeholders only. Real model from PeakRDL deferred (reqspec §2a MVP tier). |
| **T3** virtual sequencer stub | `{{block_name}}_vsequencer` in `package.sv.j2` (timer: `simple_timer_vsequencer`; buffer: `uvm_buffer_vsequencer`) | Always emitted with stubbed `arbitrate()`. Plug-in point for multi-agent (reqspec §2a). |
| **T4** generated/human separation | `generated/` wiped each run | Human extensions live elsewhere (e.g., `generated_extensions/`, future). |
| **R1** strict confidence tags | `Confidence = Literal[...]` in `blueprint_schema.py` | Every field tagged. Missing tag = `ValidationError` at parse time. |
| **R2** triage | `verify_render.py` content checks | Coverage is currently "every field" — R2's blast-radius scoring is a future relaxation. |
| **R4** corrections go upstream | Handled by user — `simple_timer_blueprint.json` is regenerated, never hand-patched | Tooling supports it; discipline is human. |
| **R5** no silent defaults | Schema has no `default_factory` that would suppress a tag | The whole point of the new context file (replacing the old `uvm_irbridge_context.txt`) is to not tell the LLM to skip. |

## How to run things

```bash
# Deps: pydantic + jinja2 via system python3 — no venv needed

# Timer Phase 2: deterministic extraction
cd material_extracted
python3 extract_blueprint.py ../my_hardware_spec.md
# → writes ../my_hardware_spec.extracted.json

# Timer check (Blueprint + render + 24 content checks)
cd ../uvm_platform
python3 verify_render.py                                 # default: hand-crafted
python3 verify_render.py ../material_extracted/my_hardware_spec.extracted.json

# Buffer structural check (Blueprint + render + 10 content checks)
# NOTE: never point --out at ../generated (tracked timer output; wipes the
# Phase A baseline regression). Use a disposable directory.
python3 verify_render.py ../material_extracted/uvm_buffer_blueprint.json --out "$(mktemp -d)"

# Buffer Python reference oracle harness (8/8 stories)
cd ../material_extracted
python3 test_oracle_traces.py
```

## What Phase 3 was (removed)

- `material_extracted/query_llm.py` called an LLM with a prompt built from
  `Blueprint.model_json_schema()`, parsed the response, validated via
  Pydantic, ran the R2 audit, wrote `<spec>.llm.json`
- It replaced the old `uvm_irbridge_context.txt` (R5 violations) and
  `_retired/query_uvm_irbridge.py` (no validation, prose output)
- R2 audit listed every `inferred`/`unknown` field for human review
- REMOVED with prompts/llm.json: deterministic-only by design (see row 3)

The renderer synthesizes the T3 vsequencer stub regardless of whether the
input Blueprint carries it — so a stubless LLM output would pass all 24
checks through the same path as deterministic output. Both naming-discipline
divergences have been closed structurally (instance prefix, env-key
validator), so a real LLM run would test prompt compliance but would not
uncover new divergence classes.

## What the IR split (Phases A → C) buys us

The 3 LLM-vs-deterministic divergences above were all on the *implementation*
side (vsequencer stub, `m_` prefix, env key). With the IR split, the
extractor no longer makes these decisions — they're owned by
`ImplementationContract`, which the renderer reads. New divergences can
only appear on the *semantic* side, which is the side humans actually
care about (and R2 audits).

Files:
- `material_extracted/design_ir_split.md` — the spike proposal
- `material_extracted/blueprint_ir_split.py` — Pydantic models + `from_legacy()` adapter
- `material_extracted/phase_a_runner.py` — Phase A byte-identical validation

The `from_legacy()` adapter keeps legacy Blueprints working unchanged.
New extractors emit pure SemanticIR; the renderer synthesizes the T3
vsequencer stub (and T2 regmodel/reg_adapter placeholders, if missing) from
`ImplementationContract.stubs_emitted`. The reference
`simple_timer_blueprint.json` has been regenerated from the deterministic
extractor (6 components, no stub), matching what extractors produce.

## Defaults taken for Phase 2 (and why)

1. Extracted output goes to `my_hardware_spec.extracted.json` (separate
   from hand-crafted) — so we can diff
2. Parameterized for any spec with the same section structure — same
   five sections (§1 System Signals, §2 primary protocol, §3 dedicated
   outputs, §4 registers, §5 UVM Topology)
3. Semantic match aimed at byte-identical — got byte-identical in practice
   once the renderer synthesized the vsequencer stub (T3 per reqspec §2a MVP tier;
   stub ownership moved from extractor to renderer in Phase B)
