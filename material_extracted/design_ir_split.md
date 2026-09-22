# Spike — IR split for the Blueprint

**Status (updated):** **Phases A, B, C all done.** Phase D deferred per §10.
**Origin:** response to an external architectural critique of the original flow (retained in private history).
**Outcome:** Phase A validated byte-identical render; Phases B + C landed;
the T3 vsequencer divergence is now structurally impossible.
**Files:** `blueprint_ir_split.py` (Pydantic models + legacy adapter),
`phase_a_runner.py` (byte-identical validation), `render_blueprint.py`
(new `render()` entry point + `synthesize_stubs()`).

---

## 1. The problem in one sentence

The current `Blueprint` carries two kinds of facts in one shape — **what is true about the spec** (semantic) and **how the renderer will materialize it as UVM** (implementation) — and that fusion is what makes every refactor expensive and every divergence between extractors noisy.

## 2. Current state (one diagram)

```
my_hardware_spec.md
        │
        ├──[regex]──► extract_blueprint.py ─► Blueprint (Pydantic-validated)
        │                                        │
        └──[LLM]────► query_llm.py ────────────►│
                                                 ▼
                                       path_assembler.assemble_scopes()
                                                 │
                                                 ▼
                                       render_blueprint.py (Jinja2)
                                                 │
                                                 ▼
                                       generated/*.sv
```

The `Blueprint` is the single artifact that flows through this. Both extractors produce the same shape; both round-trip through the renderer; both pass the same 24 content checks. The shape carries:

| Concern | Example fields | Type of fact |
|---|---|---|
| Interfaces exist, with these signals and widths | `interfaces[].signals[].width` | Semantic (true about the spec) |
| Component topology (agents, scoreboard, etc.) | `components[].type`, `components[].role` | Semantic |
| Register definitions | `registers[].fields[]` | Semantic |
| `uvm_config_db` scope paths | derived by `path_assembler` | Implementation |
| `m_` instance-name prefix convention | applied during render | Implementation |
| T3 vsequencer stub always emitted | applied during render | Implementation |
| T2 reg_block / reg_adapter placeholders | applied during render | Implementation |
| File mapping (which .sv file owns which class) | `templates/*.sv.j2` + `PIPELINE` | Implementation |

The known 3 divergences between deterministic and LLM extractors (vsequencer missing, `m_` prefix dropped, env key uses `m_env`) are all on the **implementation side** — they're "the renderer should add this regardless of what the spec says." The current architecture can't express that distinction cleanly, so the deltas show up as if they were semantic disagreements.

## 3. Proposed state (one diagram)

```
my_hardware_spec.md
        │
        ├──[regex/LLM]──► Semantic IR (NEW — pure facts)
        │                       │
        │                       ▼
        │              [optional] Verification Intent IR (NEW — what must be proven)
        │                       │
        │                       ▼
        │              Blueprint = Semantic IR + Implementation choices
        │                       │
        │                       ▼
        │              path_assembler (unchanged)
        │                       │
        │                       ▼
        │              render_blueprint.py (unchanged)
        │                       │
        │                       ▼
        │              generated/*.sv
        │
        └──[audit only]──► Review queue (R2 — confidence-tagged fields from Semantic IR)
```

Two new artifacts, one existing one narrowed:

| Artifact | Owns | Validator | Review trigger |
|---|---|---|---|
| **Semantic IR** (new) | Interfaces, signals, registers, topology — only what the spec says or what's a stated convention | Pydantic, strict (`Literal[...]` confidence tags) | Every `inferred` / `unknown` field on a high-blast-radius area |
| **Verification Intent IR** (new, optional) | Coverage goals, protocol invariants, reset/corner-case intent | Pydantic, lighter (free-text fields OK here) | Once per spec, before any code emits |
| **Blueprint** (narrowed) | `Semantic IR + Implementation choices`: file mapping, scope derivation rules, T1/T2/T3 stubs that always apply | Pydantic, derived from Semantic IR (no field overlap with it) | n/a — mechanically constructed from the two IRs |

## 4. Field-by-field: what moves where

Concrete migration table for the current `Blueprint` shape. (Source: `material_extracted/blueprint_schema.py`.)

### Stays in Semantic IR (pure facts)

```
interfaces[].name
interfaces[].signals[].name
interfaces[].signals[].width
interfaces[].signals[].direction        (input/output/inout)
interfaces[].clock_signal
interfaces[].reset_signal
interfaces[].protocol                  (apb3/axi4/...) — explicit if stated, inferred if conventional
interfaces[].key                       (T1 addendum cross-ref key)
registers[].block_name
registers[].base_address
registers[].registers[].name
registers[].registers[].offset
registers[].registers[].fields[]
components[].class_name
components[].role                      (agent/monitor/scoreboard/sequencer/regmodel/reg_adapter/...)
components[].agent_type                (e.g. amba_apb_agent — explicit or "to be supplied")
config_db[].key                        (logical name, NOT a scope path)
config_db[].interface_ref              (T1 addendum: references interfaces[].key)
config_db[].value_kind                 (virtual_interface / int / string / ...)
```

### Moves to Blueprint / Implementation (renderer-derived, never extracted)

```
uvm_config_db scopes                  (derived by path_assembler)
m_ prefix on instance names           (renderer-applied convention)
file paths under generated/           (renderer-applied)
T3 vsequencer class + stubbed arbitrate()  (always emitted per MVP-tier tenet)
T2 reg_block + reg_adapter placeholders    (always emitted per MVP-tier tenet)
T1 no-direct-wiring (vif only)         (enforced by template, not by IR field)
```

### Goes to Verification Intent IR (new layer, mostly empty for simple_timer)

```
coverage_goals[]
protocol_invariants[]                 (e.g. "valid only when ready", "last + valid on final beat")
reset_behavior                        (free-text spec)
corner_cases[]                        (named scenarios the user wants exercised)
illegal_transitions[]
```

For `simple_timer` and any other MVP-tier single-agent design, this layer is mostly empty by design — it exists to be filled in when T3 actually runs against a second design (per MVP-tier §2a "defer until forced").

## 5. Sketch of the new schema (illustrative, not Pydantic)

```python
# Semantic IR — only what the spec says or what's a stated convention
class SemanticIR(BaseModel):
    spec_source: str                         # path or identifier of the source spec
    interfaces: list[InterfaceAsset]         # as today, but no scope paths
    registers: list[RegisterBlock]           # as today
    components: list[ComponentDecl]          # class_name, role, agent_type — no instance name
    config_db: list[ConfigDBEntry]           # key (logical), interface_ref, value_kind
    confidence: dict[str, Confidence]         # R1: every field tagged

# Verification Intent IR — new, mostly empty for MVP designs
class VerificationIntent(BaseModel):
    coverage_goals: list[str] = []
    protocol_invariants: list[str] = []
    reset_behavior: str | None = None
    corner_cases: list[str] = []
    illegal_transitions: list[str] = []

# Blueprint = Semantic IR + Implementation contract
class Blueprint(BaseModel):
    semantic: SemanticIR                     # embedded, not referenced — keeps the contract self-contained
    intent: VerificationIntent = VerificationIntent()
    implementation: ImplementationContract   # derived in a deterministic post-pass

class ImplementationContract(BaseModel):
    env_class_name: str                      # always "simple_timer_env" or whatever semantic says
    instance_prefix: Literal["m_"]           # the convention, made explicit
    file_layout: list[FileAssignment]        # which class goes in which .sv
    scopes: list[ScopeAssignment]            # output of path_assembler, NOT extracted
    stubs_emitted: list[Literal["t3_vsequencer", "t2_regmodel", "t2_reg_adapter"]]
```

Key shape change: the `Blueprint` becomes a *composition* (`semantic + intent + implementation`), not a flat union of fields. The renderer consumes `implementation`; reviewers consume `semantic`; the audit queue looks at `intent`.

## 6. Human checkpoints (where review happens)

Per cgpt doc + our R1/R2/R5 discipline, review should interrupt only at architectural boundaries, never inside a phase.

| Checkpoint | What the human sees | When |
|---|---|---|
| **C1 — Semantic IR review** | The extracted facts (`interfaces`, `registers`, `components`, `config_db`), with every `inferred`/`unknown` field highlighted | After extraction, before any intent or implementation work begins. Catches >50% of future downstream errors per the doc. |
| **C2 — Verification Intent review** | The coverage goals and invariants (often empty for MVP designs) | Optional for MVP designs. Mandatory once a second agent is introduced. |
| **C3 — Generated topology review** | The `implementation` block of the Blueprint — file layout, scope assignments, stub emissions | After path_assembler runs, before render. Mechanical but reviewable. |
| **C4 — Coverage gaps** | Output of the simulation/coverage layer | Currently out of scope; deferred per NG2. |
| **C5 — Regression approval** | Diff of regenerated SV vs. previous run, scoped to human-authored extensions only | Per T4 — only touches `generated_extensions/`, never `generated/`. |

The current `verify_render.py` content checks remain as a final mechanical gate. R2 (blast-radius review queue) gets cleaner because it now operates on the Semantic IR's confidence tags, not on a flat union.

## 7. Migration plan (if we adopt)

Three phases, each independently shippable. **Phase A is the only one required to validate the spike; the rest are optional until we commit.**

### Phase A — Spike → Adopt (this proposal lands)

- Write `blueprint_ir_split.py` (sketch): two dataclasses, `SemanticIR` and `Blueprint(semantic, implementation)`, with `Blueprint` constructor that takes a `SemanticIR` and an `ImplementationContract` and assembles them.
- Run it on `simple_timer_blueprint.json`: produce an equivalent Blueprint through the new path, prove `verify_render.py` still passes all 24 checks.
- **Decision point:** if Phase A's render output is byte-identical to today's, the split is cost-free to adopt. If anything diverges, we know exactly where the seam is and can decide.

### Phase B — Extractors emit Semantic IR

- `extract_blueprint.py` rewritten to emit `SemanticIR` only.
- `query_llm.py` rewritten to prompt for `SemanticIR` only (prompt shrinks — no implementation fields to confuse the model).
- Old Blueprints continue to work via a thin adapter: `Blueprint.from_legacy(json)` constructs the new shape by classifying each legacy field as semantic vs. implementation.

### Phase C — Renderer consumes the new shape

- `render_blueprint.py` reads `implementation` directly. The semantic fields are accessible to templates but only via `blueprint.semantic.*` — making "is this field semantic or implementation?" answerable by grep.
- `path_assembler` is unchanged; its output moves into `implementation.scopes`.

### Phase D (later) — Verification Intent IR

- Added when a second agent design forces it. Not required for any current work.

## 8. Open decisions

These need a call before Phase A can land. Bold = my recommendation.

1. **Where does the `m_` instance-name convention live?** Bold: in `ImplementationContract`, not in Semantic IR. Semantic says "the env is class `simple_timer_env`"; implementation says "the instance is `m_env`."
2. **What about the existing `simple_timer_blueprint.json` (hand-crafted)?** Bold: ship it through a `Blueprint.from_legacy()` adapter in Phase B, don't rewrite the canonical artifact by hand.
3. **Does `Blueprint` embed `SemanticIR` or reference it?** Bold: embed (self-contained artifact, easier to diff and review). Reference is cleaner if Semantic IR gets versioned independently later, but we have no evidence we need that yet.
4. **Where do R2 blast-radius scores live?** Bold: on the `SemanticIR` confidence tags, scored by a hand-authored heuristic (per reqspec §4 [OPEN]). Implementation fields are mechanical and not review-queued.
5. **Should the LLM prompt now ask for Verification Intent fields?** Bold: no, for MVP designs. They're empty by default; we add prompt coverage when a second design forces it.

## 9. Risk callouts

- **Mechanical risk:** Phase A must produce byte-identical render output. If it doesn't, the spike is invalidated — the seam is in the wrong place.
- **Convention drift risk:** the 3 known LLM-vs-deterministic divergences only go away if every extractor emits the same Semantic IR shape AND the implementation fields are mechanically derived (not extracted). If any extractor emits implementation-shaped fields, the divergences persist and we're worse off (more layers, same noise).
- **Review burden risk:** C1 review (Semantic IR) is real human time. For `simple_timer` it's a few minutes; for a real SoC spec it could be hours. R2's blast-radius scoring matters more than ever — without it, every `inferred` field on every review is a tax.
- **Schema migration risk:** `blueprint_schema.py` is the contract between extractors and renderer. Any field rename during the split breaks both sides. Mitigation: legacy adapter (Phase B) keeps the old shape working until both extractors migrate.
- **"Defer until forced" applies here too:** this is a real refactor, not a small change. If T3 multi-agent is still 6+ months out, the cost of splitting now may exceed the payoff. The Phase A spike is the right way to find out cheaply.

## 10. Recommendation

**Adopt Phase A immediately** (1-2 hours, validates the seam is in the right place). Decide on Phase B/C only after Phase A's render output is byte-identical. Defer Phase D until a second design forces it.

If Phase A's render output diverges from today's, this proposal is wrong and we shelve the IR split until after T3 (per the doc's "spec is the bottleneck, not the architecture" hedge).

### Update — phases A/B/C complete

- **Phase A** done: `phase_a_runner.py` proved byte-identical render across
  the seam (all 7 SV files match SHA256). The spike is validated.
- **Phase B** done: `extract_blueprint.py` no longer emits the T3 vsequencer
  stub; `prompt_v2.txt` rule #3 changed from "ALWAYS emit" to "DO NOT emit";
  `query_llm.py` emits SemanticIR. The T3 vsequencer divergence between
  deterministic and LLM outputs is now **structurally impossible** —
  extractors can't emit it, renderer always adds from
  `ImplementationContract.stubs_emitted`.
- **Phase C** done: `render_blueprint.render(blueprint: ComposedBlueprint, out_dir)`
  synthesizes stubs from `ImplementationContract`, then runs the PIPELINE.
  Legacy file-based `render_blueprint(path)` still works. All 24 content
  checks pass on all three Blueprints (legacy hand-crafted, deterministic
  extracted, LLM extracted).
- **Phase D** deferred: Verification Intent IR added when a second design
  forces it.

### What the IR split did NOT fix

The 2 remaining LLM-vs-deterministic divergences (`m_` prefix on instance
names, env-key choice) are naming-discipline issues, not architecture
issues. The IR split doesn't change them; they'd be closed off by
Pydantic validators (separate work).
