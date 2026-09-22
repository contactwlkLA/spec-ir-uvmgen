# Continuation — pick up here in a new session

**Revision:** 3.1 (2026-09-21 23:57 PDT)
**Status:** Historical development handoff — superseded by README and docs/architecture.md for current guidance.

---

## State

All phases done. Two naming-discipline divergences closed structurally.
`simple_timer_blueprint.json` regenerated from extractor (6 components, no T3 stub).
All 24/24 content checks pass on all three Blueprints.

## What was built

### IR split (Phases A → C)

Blueprint split into `SemanticIR` + `ImplementationContract`:
- `blueprint_ir_split.py` — SemanticIR + ImplementationContract dataclasses + legacy adapter
- `phase_a_runner.py` — Phase A: byte-identical render validation
- `extract_blueprint.py` — Phase 2: emits SemanticIR, no T3 vsequencer stub
- Phase 3 LLM caller removed (deterministic-only by design)
- `render_blueprint.py` — Phase C: `render(blueprint, out_dir)` + `synthesize_stubs()`

**Phase C verified:** `extracted.json` (6 components, no stub) → `verify_render.py` → 24/24 pass. Synthesis proven by output, not inferred from architecture.

### LLM path status — removed

Phase 3 (`query_llm.py`, prompts, `my_hardware_spec.llm.json`) removed:
deterministic-only by design — spec-extraction variance would make two
runs undiffable. The three documented LLM-vs-deterministic divergences
remain structurally prevented by the renderer architecture:
- **T3 vsequencer stub** — IR split: extractors never emit it, renderer always synthesizes it
- **`m_` prefix** — `ImplementationContract.instance_prefix`: renderer applies it
- **Env key** — `InstancesBlock` Pydantic validator: rejects mismatched keys

### Audit closed

Four stale artifacts found and fixed:
1. `verify_render.py` banner — referenced retired `query_uvm_irbridge.py`
2. FLOW.md Phase 3 prose — theoretical divergences, not measured
3. FLOW.md phase-status table row C — credited non-LLM pass as evidence
4. "Stale" label on `llm.json` — implied a real-but-old run existed; it was a mislabeled copy (file since removed with Phase 3)

### Naming validators closed (2025-07-24)

Two naming-discipline divergences that were previously prompt-disciplined
are now enforced structurally:

1. **Env-key validator** — `InstancesBlock` in `blueprint_schema.py` now
   rejects Blueprints where an env dict key doesn't match its `class_name`.
   The extractor uses `class_name` as the key (former LLM branch removed).

2. **`m_` prefix → `ImplementationContract.instance_prefix`** — the UVM
   `m_` convention is now enforced by the renderer. A new function
   `_ensure_instance_prefix()` in `render_blueprint.py` walks the Blueprint
   dict before scope assembly and applies the prefix (`m_`) to any instance
   name that doesn't already carry it. Idempotent — already-prefixed names
   are unchanged. The prefix is stored in `ImplementationContract.instance_prefix`.
   See `ImplementationContract` in `blueprint_ir_split.py`.

3. **`simple_timer_blueprint.json` regenerated** — was a hand-crafted legacy
   file with 7 components (including T3 vsequencer stub). Now regenerated
   from `extract_blueprint.py` against `my_hardware_spec.md` → 6 components,
   no stub. The renderer synthesizes the vsequencer from
   `ImplementationContract.stubs_emitted` just like any other Blueprint.

4. **`phase_a_runner.py` updated** — now goes through the composed `render()`
   path (stub synthesis + prefix + scope assembly + pipeline) instead of
   calling raw pipeline steps. `render_blueprint_for_dict()` removed.

The `from_legacy()` adapter remains for any future hand-crafted Blueprints.

### What's verified (stdout-confirmed)

| Check | Result |
|---|---|
| Phase A byte-identical render | 7/7 files SHA256 match baseline ✓ |
| Deterministic-extracted (6 comp, no stub) → 24/24 | ✓ |
| `my_hardware_spec.llm.json` (copy of deterministic) → 24/24 | ✓ (historical; file removed with Phase 3) |
| Regenerated reference (6 comp, no stub) → 24/24 | ✓ |

---

## Remaining decisions

1. **Phase D** — Verification Intent IR deferred until a second design forces it

---

## Quick orientation

```
spec-ir-uvmgen/
├── docs/CONTINUATION.md         ← this file
├── README.md                  ← high-level + IR-split section
├── docs/FLOW.md               ← pipeline state, phase table
├── my_hardware_spec.md        ← canonical smoke-test design
├── sessions2-backup.bundle    ← git bundle (gitignored)
├── material_extracted/
│   ├── blueprint_schema.py    ← Pydantic contract (+ env-key validator)
│   ├── blueprint_ir_split.py  ← SemanticIR + ImplementationContract (+ instance_prefix)
│   ├── extract_blueprint.py   ← Phase 2: emits SemanticIR (no T3 stub)
│   ├── (Phase 3 LLM caller removed — deterministic-only by design)
│   ├── path_assembler.py      ← scope derivation (unchanged)
│   ├── phase_a_runner.py      ← Phase A byte-identical validation
│   ├── design_ir_split.md     ← spike proposal (marked "done")
│   ├── simple_timer_blueprint.json         ← regenerated from extractor (6 comp)
│   └── my_hardware_spec.extracted.json     ← deterministic output (6 comp)
└── uvm_platform/
    ├── render_blueprint.py    ← Phase C: render() + synthesize_stubs() + _ensure_instance_prefix()
    ├── verify_render.py        ← 24 content checks
    └── templates/*.sv.j2
```

---

## Smoke tests

```bash
# deps: pydantic + jinja2 via system python3 — no venv needed
cd spec-ir-uvmgen

# Phase A: byte-identical render across IR-split seam
python3 material_extracted/phase_a_runner.py material_extracted/simple_timer_blueprint.json

# Two Blueprints: hand-crafted and deterministic-extracted
python3 uvm_platform/verify_render.py material_extracted/simple_timer_blueprint.json --out generated
python3 uvm_platform/verify_render.py material_extracted/my_hardware_spec.extracted.json --out generated

# (Former third Blueprint `my_hardware_spec.llm.json` removed with Phase 3)
```

---

## On context depth

When you exit and re-enter:
- **Fresh session:** I start with zero memory. Type `/session` to see the current session file.
- **Resume:** `pi -c` or `/resume` loads the full JSONL. I see everything.
- **Reduce context:** `/compact [instructions]` — summarizes older messages, keeps ~20k recent tokens. Attach as CompactionEntry. Reduces what I carry without losing the gist.
- **Name the session:** `/name <description>` — session name stored in JSONL metadata, shows in `/resume` and `pi -r`.

**The JSONL is the ground truth.** Everything else (`CONTINUATION.md`, git commits, bundle) is derivative. Resume the session or re-read this file to reorient.

Historical note: this document predates publication; private pre-publication
history is intentionally omitted from this release.
