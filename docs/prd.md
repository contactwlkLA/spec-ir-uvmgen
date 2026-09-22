# PRD — UVM Platform (Extensible Spec-to-UVM)

> **DEPRECATED** (2026-08-30) — superseded by `../uvm_buffer_prd.md`
> (authoritative DUT requirements) and `../README.md` / `FLOW.md` (platform
> goals and state). Kept for history only. Do not update or cite.

**Status:** DEPRECATED — see banner above
**Date:** 2025-07-17
**Revision:** 3.0 (2026-08-30 21:46 PDT)
**Source of truth for technical reqs:** `extensible_uvm_platform_reqspec_v0_3.md`
**Source of truth for pipeline state:** `FLOW.md`

## 1. Problem

HAVEN ([arXiv:2604.27643](https://arxiv.org/abs/2604.27643)) shows LLM-based UVM generation works when LLMs
are bounded to structured extraction and code emission is delegated to
deterministic renderers. But HAVEN's renderer targets direct signal
wiring — appropriate for single-IP scopes, but structurally caps output
at that scale.

This platform keeps HAVEN's core insight (LLM-extracts, renderer-emits)
and asks: what if the renderer targets UVM-native extensibility primitives
(`uvm_config_db`, virtual sequencer, RAL, factory overrides) instead of
direct wiring?

## 2. Target users

- **Primary:** the author of this platform (PoC self-use).
- **Secondary:** anyone inheriting this codebase for a real verification
  project.

This is a PoC. No external users yet.

## 3. Goals

(Carried from reqspec §1 — restated here as product framing.)

- **G1.** Generated environments must compose into a larger env without
  regeneration or hand-editing.
- **G2.** Design-specific behavior that can't be derived from the spec
  must be represented as a typed, compile-enforced gap, never silent.
- **G3.** Human review effort should scale with blast radius, not
  artifact size.
- **G4.** Regeneration must not destroy human-authored extensions.

## 4. PoC scope (current)

- One design: `simple_timer` (single-agent, APB3 slave + IRQ monitor).
- No LLM in the loop yet — Phase 2 closes the deterministic-extraction
  gap; Phase 3 brings the LLM in.
- No multi-agent coordination — deferred per user's call to focus on
  smooth single-agent first.
- SV output is generated but not yet compilable against a real simulator
  — vendor classes (`amba_apb_agent`, `irq_monitor_agent`) are referenced
  but not emitted.

## 5. Non-goals

- **NG1.** Fully autonomous generation of design-specific coordination
  logic. (Per reqspec NG1.)
- **NG2.** DSL/functional coverage completeness. (Per reqspec NG2.)
- **NG3.** Production-grade UVM compliance — Phase 1 emits skeletons,
  not finished testbenches.
- **NG4.** Multi-agent coordination or SoC-level composition —
  deferred until single-agent runs clean.

## 6. Success criteria

| #   | Criterion | How to check | Status |
|-----|-----------|--------------|--------|
| SC1 | Blueprint validates under strict R1 (Pydantic `Literal` confidence tags) | `verify_simple_timer.py` | done |
| SC2 | `uvm_config_db` scopes derived mechanically, not spec-owned | `verify_render.py` content checks | done |
| SC3 | Renderer emits all expected SV files with correct names, signals, scopes | `verify_render.py` (24 checks) | done |
| SC4 | T3 virtual sequencer stub emitted with `virtual arbitrate()` | content check on `simple_timer_pkg.sv` | done |
| SC5 | T2 regmodel placeholders present | content check | done |
| SC6 | IRQ signal is `irq_out` (substring-match bug from old renderer structurally impossible) | content check on `irq_if.sv` | done |
| SC7 | Deterministic extractor produces a Blueprint whose rendered SV is byte-identical to the hand-crafted reference | Phase 2 | done |
| SC8 | LLM extraction passes R1 strict validation | Phase 3 | code ready, not exercised |
| SC9 | LLM-extracted Blueprint matches deterministic extractor (modulo semantic differences) | Phase 3 | structurally enforced (divergences closed by IR split + prefix + env-key validator) — not yet demonstrated by a run |
| SC10 | T2 real register model from SystemRDL | Phase 4 | much later |
| SC11 | IR-split seam produces byte-identical render (Phase A) | `phase_a_runner.py` | done |
| SC12 | Extractors emit SemanticIR only; renderer synthesizes impl stubs (Phase B+C) | `verify_render.py` on extracted.json | done |

## 7. Tenets (cross-reference)

All technical tenets (T1–T5) and requirements (R1–R5) live in the reqspec.
This PRD does not duplicate them.

Currently implemented in code:
- **T1** no direct wiring → `material_extracted/path_assembler.py`
- **T1 addendum** shared keys → `InterfaceAsset.key` cross-ref validator
- **T2** SystemRDL → placeholder only (`simple_timer_reg_block` etc.)
- **T3** virtual sequencer stub → `simple_timer_vsequencer` in `package.sv.j2`
- **T4** generated/human separation → `generated/` wiped each run
- **R1** strict confidence tags → `Confidence = Literal[...]`
- **R2** triage → currently "every field" (blast-radius scoring is a
  future relaxation, reqspec §4 [OPEN])
- **R4** corrections upstream → tooling supports; discipline is human
- **R5** no silent defaults → enforced by schema design

## 8. Phase plan

- **Phase 0** done — cleanup & canonical home
- **Phase 1** done — renderer with no LLM
- **Phase 2** done — deterministic extractor (byte-identical SV output vs hand-crafted reference)
- **Phase 3** removed — LLM extractor deleted (deterministic-only by design)
- **Phase A** done — IR-split spike validated (byte-identical render across seam)
- **Phase B** done — extractors emit SemanticIR only (T3 stub removed from extractor + LLM prompt)
- **Phase C** done — renderer consumes composed Blueprint; synthesizes T2/T3 stubs from `ImplementationContract.stubs_emitted`
- **Phase D** deferred — Verification Intent IR (until second design forces it)
- **Phase 4** later — multi-agent / T3 real / T2 real
- **Phase 5** later — real simulator bring-up

## 9. Open questions

- Blast-radius scoring for R2 (reqspec §4 [OPEN])
- Granularity of Stage 1' input spec (reqspec §5 [OPEN])
- T2 wrapper/RAL API compatibility (reqspec §5 [OPEN])
- Naming convention for `block_name` — explicit field vs derived from spec
- Path-strictness: should `tb_top.sv.j2` reject Blueprints missing
  required fields, or assume defaults?
- **Resolved** — T3 vsequencer stub: owned by renderer (`ImplementationContract.stubs_emitted`),
  not extracted. Architecture eliminates the divergence.
- **Resolved** — extractors emit SemanticIR only, not implementation
  stubs (former LLM branch since removed with Phase 3).
- **Resolved** — `m_` instance-name prefix: now owned by
  `ImplementationContract.instance_prefix` and enforced by
  `render_blueprint._ensure_instance_prefix()` at render time.
  The deterministic extractor's `normalize_instance_name()` is no
  longer the sole enforcement point; the renderer applies the `m_`
  prefix idempotently to any instance name that doesn't already carry it.
- **Resolved** — env-key convention: `InstancesBlock` in
  `blueprint_schema.py` now has a `@model_validator` that rejects
  Blueprints where an env dict key doesn't match its `class_name`.
  Both extractors must use `class_name` as the key.
