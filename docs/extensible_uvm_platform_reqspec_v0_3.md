# Requirement Spec: Extensible Spec-to-UVM Verification Platform
**Status:** Draft v0.3 — pre-gap-review
**Lineage:** Inspired by HAVEN (arXiv:2604.27643) — not a duplication of it; this platform explores an adjacent architectural question HAVEN's own scope didn't target.
**Not yet resolved / explicitly open:** marked `[OPEN]` throughout

**Changelog from v0.2:**
- T1: added cross-reference requirement (shared key, not string convention) — root cause of a real naming bug found in implementation audit
- Added R5: extraction-guidance instructions must not suppress confidence tagging for gaps the renderer doesn't actually resolve
- Added §7: session audit log for traceability, kept separate from the requirements themselves

**Changelog from v0.1:**
- Reframed lineage from "response to HAVEN's gaps" to "inspired by HAVEN" throughout §0/§6
- Removed unverified I2C claim (HAVEN's stated protocol scope is Direct/Wishbone/AXI4-Lite; I2C does not appear in it) — T3 now stands on architectural reasoning alone
- Added R4: requirement-arbitration rule (spec corrections route through source only, never through intermediate data)

---

## 0. Problem Statement

HAVEN demonstrates that LLM-based UVM generation works when LLMs are restricted to structured extraction and all code emission is delegated to deterministic renderers. This platform takes that core insight as a starting point and asks a related but separate question: what changes if the renderer targets UVM's native extensibility primitives (`uvm_config_db`, virtual sequencer, RAL/`uvm_reg`, factory overrides) instead of direct signal binding and address-literal sequences?

Direct wiring — a reasonable choice for HAVEN's own single-IP scope — structurally limits:
- environment composition into larger (SoC-level, multi-IP) testbenches
- multi-agent coordination (no virtual-sequencer-equivalent exists to coordinate multiple agents when direct wiring is the connectivity model)
- reuse of a generated env component outside the exact context it was generated for

This spec defines requirements for a platform that keeps the LLM-extracts/renderer-emits insight but targets **UVM-native extensibility primitives** as the renderer's output, not ad hoc wiring.

---

## 1. Goals / Non-Goals

**Goals**
- G1. Generated environments must be composable into a larger env without regenerating or hand-editing the composed component.
- G2. Design-specific behavior that cannot be determined from the spec must be represented as a typed, compile-enforced gap (not a silent omission or a comment).
- G3. Human review effort should scale with risk/blast-radius of a decision, not with total artifact size.
- G4. Regeneration of the env (e.g., spec changed) must not silently destroy human-authored extensions.

**Non-Goals (for this version)**
- NG1. Fully autonomous generation of design-specific coordination/arbitration *logic*. (Per prior discussion: this is design-dependent and likely requires a human author for the logic itself, not just review of it.)
- NG2. Solving DSL/functional coverage completeness — treated as a downstream, secondary concern (already addressed reasonably well in HAVEN v1's Stage 2 approach; not re-litigated here).

---

## 2. Core Architectural Tenets

### T1 — No direct signal/address wiring anywhere in generated output
All DUT-to-env connectivity goes through `uvm_config_db`-propagated virtual interface handles. All register access goes through a generated RAL model (`uvm_reg_block`), never raw address literals in sequence code.

**Rationale:** direct wiring is what caps a single-IP-scoped generator at that scale and produces address-literal sequences that can't survive a register map change without full regeneration.

**Addendum:** cross-references between schema entries (e.g., a config_db entry's associated interface, a component's virtual interface handle) must be represented as an explicit shared key in the Blueprint schema — never reconstructed by string convention (deriving one field's expected value by concatenating another field's name). String-convention linking silently breaks the moment the two sides are extracted independently and drift, which is exactly the kind of fragile implicit connectivity T1 exists to eliminate.

### T2 — Register model is derived, not hand-rolled JSON
The register/field extraction target is **SystemRDL** (or IP-XACT), not a custom Blueprint JSON schema. RAL classes are generated via existing deterministic tooling (e.g., PeakRDL) from the SystemRDL, not by a bespoke CodeGen path.

**Rationale:** solved problem, existing tooling, and SystemRDL is human-readable/diffable — gives a review checkpoint for free instead of requiring reviewers to learn a custom schema.

### T3 — Multi-agent coordination is a factory-overridable virtual hook, not an omitted feature
When the extracted topology implies >1 agent, the renderer always emits a virtual-sequencer base class with the arbitration/coordination point as a `virtual` (or pure `virtual`) method with an empty/default body. Design-specific coordination logic is supplied via a derived class registered through `set_type_override_by_type`, never by editing the generated base class.

**Rationale:** makes "unknown behavior" a type-system fact (compile fails until resolved) rather than a comment an LLM or human can silently skip. This is standard UVM practice for multi-agent coordination independent of any specific empirical example — see `[OPEN]` note in §5 on the removed I2C claim.

### T4 — Two-directional protection boundary
A direct-wiring generator's "protected set" is naturally one-directional: generated code protected from LLM edits. This platform requires the inverse guarantee too: **human-authored derived classes/overrides must be immune to regeneration** of their corresponding base class. Concretely: generated and human-authored code live in physically separate files/directories; regeneration only ever touches the generated-file set.

**Rationale:** without this, every spec update risks clobbering hand-written coordination logic, which defeats the purpose of the factory-override pattern in T3.

### T5 — Same generalization applies to peripheral/BFM behavior
BFMs and register-level side-effect behavior (`uvm_reg_cbs` callbacks for write side-effects, custom predict logic) follow the same factory-override pattern as T3, not template-baked behavior.

**Rationale:** consistency — same mechanism, same reasoning, applied everywhere "design-specific but not spec-derivable" behavior can occur, not just at the sequencer layer.

---

## 2a. MVP Tier — Stub the Seam, Defer the Machinery

Building all of T1–T5 before running a single design through the pipeline is backwards — validation only comes from actually running designs through it. The MVP tier keeps the *interface shape* of each tenet (cheap, mostly boilerplate) while deferring the *implementation* behind it (expensive, design-dependent) until a design actually forces it.

| Tenet | MVP: stub now | Deferred until forced |
|---|---|---|
| T1 | Route vif through `uvm_config_db::set/get` from the start — no cost difference vs. direct binding, so there's no reason to defer this one at all | — (T1 is effectively free; do it in MVP) |
| T2 | Thin accessor wrapper (`reg_write(addr, val)`) that sequences call instead of raw address literals; address-literal behavior underneath is unchanged for now | Real SystemRDL → PeakRDL → `uvm_reg` generation. Swapping the wrapper's internals later doesn't touch sequence call sites. |
| T3 | Generate the virtual sequencer class even for a single-agent design, with `arbitrate()` as a stubbed no-op virtual method, factory-registered | Actual coordination/arbitration logic — written only when a second agent is introduced |
| T5 | Factory-registrable hook classes (BFM behavior, reg callbacks) with empty bodies | Design-specific side-effect logic |

**Rationale:** this makes a second, genuinely multi-agent design a *plug-in* (fill the stubbed hook) rather than a *rewrite* (restructure the env to add a hook that was never there). The cost of stubbing is boilerplate; the cost of not stubbing is retrofitting T3/T4's file-layout discipline onto an env that was never built expecting it.

**Known limitation of this tier:** stubbing `arbitrate()` doesn't validate that the factory-override pattern actually holds up under real multi-agent load — that only gets proven once a second design exercises it. MVP tier de-risks *retrofit cost*, not *design correctness* of T3 itself.

**Sequencing implication:** first design (e.g. 4x4 NN engine, single bus interface) runs through the MVP tier only — T1 live, T2/T3/T5 stubbed-but-present. Second design (ideally one with a genuine second agent — e.g. DMA/weight-load as a separate interface bolted onto the NN engine) is what actually exercises T3/T5's deferred logic and validates whether the seam holds.

---

## 3. Pipeline Structure (Staged)

### Stage 1' — Structural Skeleton Generation
**Input:** design spec (granularity TBD — see §5 [OPEN])
**Output:** compiles-and-connects env skeleton: vif/config_db wiring, RAL model (via SystemRDL→PeakRDL), virtual sequencer base class(es) with stubbed hooks, TLM analysis port connections, agent topology.
**Explicitly excludes:** protocol/sequence behavior.
**Human checkpoint:** **mandatory**, gated on confidence tagging (§4). This is the expensive-to-fix-later layer; review happens before Stage 2' begins.

### Stage 2' — Behavior Fill
**Input:** Stage 1' skeleton (frozen/reviewed) + spec
**Output:** protocol-level sequence behavior, following HAVEN's DSL-mediated approach (retained as-is — already solves the "LLM shouldn't write SV" problem well at this layer).
**Human checkpoint:** optional/triaged, same as HAVEN's iterative coverage-gap loop.

**Rationale for the split:** the boundary sits at *composability* (structure) vs. *protocol correctness* (behavior). Keeps expensive human review scoped to the part that's structurally expensive to unwind later.

---

## 4. Blueprint Extraction Review

### R1 — Confidence/provenance tagging on every extracted structural decision
Every field in the Stage 1' extraction output carries a tag: `explicit` (spec states it directly), `inferred` (derived from convention/pattern), or `unknown` (no basis in spec, default assumed).

### R2 — Review triage, not blanket review
Human review queue is populated by `(confidence, blast_radius)` — e.g., `inferred` or `unknown` tags on topology/RAL/sequencer-arbitration fields (high blast radius) are always queued; `inferred` tags on e.g. a coverage bin boundary (low blast radius) are not.

### R3 — No silent single-agent default
If agent-coordination behavior is `unknown`, the platform does not omit the virtual sequencer — it generates the T3 stub and flags it, forcing an explicit decision rather than an absent one.

### R4 — Requirement corrections route through the source spec only
When human review determines the *spec itself* is wrong, ambiguous, or incomplete — not just that extraction confidence was low — the correction is made by editing the source spec document (or the context/schema prompt), never by directly editing the Blueprint JSON or any downstream generated artifact. This holds regardless of whether the root cause is a genuinely incorrect requirement or a faithful extraction of an ambiguous spec: either way, the fix flows upstream and the Blueprint is regenerated, never hand-patched.

**Rationale:** extends T4's protection boundary one layer earlier in the pipeline. The Blueprint must remain a pure, reproducible function of (spec, context prompt) at all times — hand-patching it breaks that invariant silently and irreversibly on the next regeneration. Distinct from R1: R1 tags extraction *fidelity* (does the Blueprint faithfully reflect what the spec says); R4 governs *correctness of the spec itself* — a different failure mode that shares R2's review checkpoint but requires a different corrective action.

### R5 — Extraction-guidance instructions must not suppress confidence tagging
Instructions given to the extraction step (system/context prompt) must never tell the LLM to treat a class of structural gap as automatically resolved, or to skip flagging it, unless the deterministic renderer actually resolves that gap. If the renderer's coverage changes, the extraction-guidance instructions update in lockstep — a claim that something is "automatically handled" is a structural fact that has to stay true, not a standing assumption.

**Rationale:** found during implementation audit — a context prompt instructed the LLM not to flag missing TLM connections as gaps, on the assumption the renderer wired them automatically, when the renderer never did. This silently defeated R1's tagging guarantee for exactly the class of gap most worth catching.

**[OPEN]** — exact blast-radius scoring function is undefined; likely needs to start as a hand-authored heuristic (topology/RAL/sequencer = high; coverage bins/enum sweep ranges = low) rather than learned.

---

## 5. Open Items

- **[OPEN] Granularity of Stage 1' input spec.** Unresolved whether spec granularity should be fixed (e.g., always datasheet-level) or itself a tunable/staged parameter. Flagged for next round.
- **[OPEN] Coordination-logic authorship split.** Per prior discussion, this is inherently design-dependent; not resolvable at the framework-requirements level. Framework's job (T3/T4) is to make the *seam* clean, not to decide who writes the logic.
- **[OPEN] Blast-radius scoring for R2/R4.** No proposed algorithm yet, only the qualitative examples above.
- **[OPEN] SystemRDL/IP-XACT extraction accuracy.** Not yet assessed how reliably an LLM can produce valid SystemRDL from unstructured spec text vs. a simpler flat JSON Blueprint — may need its own eval before T2 is treated as low-risk.
- **[OPEN] Scope of "extensible" for v1 of this platform.** Multi-IP SoC-level composition is the stated motivation, but no requirement above has been validated against an actual multi-IP integration exercise — everything is currently justified by architectural reasoning, not a benchmark.
- **[OPEN] T3's motivating example.** v0.1 cited HAVEN's I2C results as evidence of an unexplained coordination-related coverage ceiling. That claim could not be verified — HAVEN's stated protocol scope is Direct, Wishbone, and AXI4-Lite; I2C does not appear in it. Removed pending either a genuine example (from HAVEN's full results or elsewhere) or an explicit acknowledgment that T3 is justified on architectural grounds alone, with no empirical anchor yet.
- **[OPEN] Stage 1' exit criterion.** "Compiles-and-connects" was an adequate bar when connectivity errors were compile-time errors under direct wiring. Under T1, a mismatched `config_db` `set()`/`get()` key or type parameter compiles cleanly and fails at elaboration or run-time instead. Whether Stage 1's checker needs a bounded elaboration-phase run (rather than compile-only) to catch this class of error is unresolved.
- **[OPEN] G4/T4 base-class signature drift.** File separation prevents regeneration from overwriting a human-authored override, but doesn't prevent regeneration from changing the *base class's* virtual method signature underneath it (e.g., a renamed parameter on `arbitrate()`), which can silently break or change the meaning of the derived override. Not yet addressed.
- **[OPEN] T2 wrapper/RAL API compatibility.** The MVP-tier `reg_write(addr, val)` wrapper is only a drop-in replacement when the real RAL model lands if its call signature already matches `uvm_reg`/`uvm_reg_field`'s calling convention (status output, access path, blocking semantics). Not yet pinned down.

---

## 6. Traceability

| Requirement | Origin |
|---|---|
| T1 | Direct signal/address wiring → non-extensible, single-IP ceiling |
| T2 | Custom Blueprint JSON for registers, address literals in sequences |
| T3 | No virtual sequencer concept for multi-agent coordination |
| T4 | One-directional protection is insufficient once human-authored overrides exist |
| T5 | BFM behavior needs to be overridable, not template-baked |
| Stage 1'/2' split | Boundary placed at structure vs. behavior, not component-exists vs. stimulus-exists |
| R1–R3 | Extraction errors need a confidence-tagged, triaged correction path |
| R4 | Added during this platform's own pre-gap-review — not sourced from HAVEN; closes a correction-path gap R1–R3 alone left open |
| R5 | Added after implementation audit — closes a gap where extraction guidance silently overrode R1's tagging guarantee |

---

## 7. Session Audit Log

Kept separate from §0–§6 on purpose: this is a trace of *why* things changed, not a requirement itself. Useful for picking this back up later without re-reading the full discussion.

**gem35_pkg audit** (Gemini 3.5 implementation attempt, reviewed against T1–T5/R1–R4):
- Naming bug found and root-caused → promoted to the T1 addendum above.
- Telemetry-suppression contradiction found → promoted to R5 above.
- Register model (T2) not implemented in gem35_pkg, not even at MVP-stub level — compile-blocking on the package's own example spec. Not promoted to a new requirement; T2 already covers it. Tracked as an implementation gap, deprioritized for now (see priority note below).
- Virtual sequencer (T3) not generated despite the audited spec having two agents (one active, one passive). Same situation — already covered by T3, tracked as an implementation gap rather than a new requirement.

**Explicitly held, not added to the spec:**
- Port-ambiguity hard-refusal rule (spec2json refuses to generate any JSON if port names/polarity/types are ambiguous, rather than tagging and continuing). This was the original design intent behind R1's tagging. A strict version of it is in tension with a stated preference for seeing an early skeleton and shaping it iteratively, rather than requiring a correct-on-first-attempt run. Held pending that tension being resolved one way or the other — not rejected, just not written in yet.

**Current priority** (informational, not a requirement): getting the generated topology shape correct and internally consistent takes precedence over making it compile right now — no simulator is set up yet. T2 completion and `connect_phase` generation (the compile-blocking gap above) are parked until that changes.
