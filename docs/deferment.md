# deferment.md
**Revision:** 3 (2026-08-30 21:46 PDT)
Write-only log. Append here, don't edit or delete existing entries.
Two kinds of entry — keep them distinct:
- DEFERRED: still true / still owed, just not done yet
- STRIPPED: was true under the old design, removed on a judgment call, may reconsider

---

## DEFERRED

- GR-010 — generation manifest (mock params, encodings, source/generator revisions).
  Schema (semantic_schema.py:334) already marks this as the only permitted deferral.

- Phase D — Verification Intent IR. Per CONTINUATION.md: deferred until a second
  design forces it.

- Trace-rewrite scope — six hand-written traces (LT-001/005/007/012, IT-001/002/006)
  vs. full 26-trace set from PRD §7. Decided: start with six. Full set is the
  real exit criterion, not yet scheduled.

- SVA — out of scope for now (no simulator/tools). Assertion records in the
  semantic model (AST-*) stay as unbacked names. Revisit if a PD-side or
  simulator-side path opens up.

- Revision-pin discipline — `source_prd_revision` is hard-pinned to the current
  PRD revision (v0.0e) in both semantic_schema.py (Literal) and
  validate_uvm_buffer_semantics.py (equality check). A transitional union
  ("v0.0d" | "v0.0e") existed only while the v0.0e candidate landed and was
  re-pinned before commit. Every future PRD revision row must bump the pin in
  both files as part of the same pass; until then extraction and validation
  fail loudly (intended tripwire). Never widen the pin to a union to make an
  old candidate validate — regenerate the candidate instead.

- Referee milestone coverage gap (oracle-plan v0.3 execution, 2026-08-31).
  The 8-story milestone exercises the hold threshold arm and the guarantee
  arm only in its non-firing form. Not exercised at milestone, all covered by
  the 25-scenario exit pass: the positive form of the request-side acceptance
  guarantee (hold-low + valid ⇒ accepted; exit stories LT-002/LT-013 per PRD
  :380/:390), the watchdog fire path (exit story IT-008), and the
  HoldViolationRecord emission paths (no milestone story fires one; they were
  smoke-tested once outside the harness — threshold arm, guarantee arm, and
  watchdog each fire exactly once and do not double-fire). The exit pass must
  include at least one story that fires each violation record.

- THEORY_OF_OPERATION.md Panel B pipeline diagram lags the artifact set: the
  referee stage (material_extracted/oracle_events.py, oracle.py,
  test_oracle_traces.py) is not drawn. Update at the next doc-sync pass.

- Audit discipline: ID-set scans are structurally blind to deleted concepts
  surviving in prose (description/statement/disposition fields), and
  scratch-file baselines are weaker than the VCS baseline. Future
  Phase-0-style audits must (a) grep generated artifacts for removed-concept
  vocabulary, and (b) take gate evidence from `git diff HEAD`, never from
  mid-pass copies.

---

## STRIPPED

- DUT-LC-008 (final-slot arbitration) — removed 2026-08-30. Symmetric hold +
  cushion slot makes the rule false, not just inapplicable (both sources accept
  at occupancy 14; no single-slot race exists to arbitrate). Reconsider only if
  buffer redesign reverts to asymmetric hold.

- ND-001 (final-slot arbitration nondeterminism) — removed same session, same
  reason. ND-002 (completion selection/timing) is unaffected and stays.

- agree-1 (AGREEMENTS.md) — capacity-15 rationale superseded by the symmetric-
  hold fix; the underlying numeric decision (15 vs 16, threshold vs depth)
  carries forward, but agree-1's text and its "capacity-agnostic streamer"
  framing do not.

- "Nondeterminism: ND-001 closed/bounded" line, AGREEMENTS.md — obsolete,
  tracks the entry above.

- flushed_id_set on the oracle→scoreboard channel (agree-2) — flagged as an
  ownership leak against agree-3; error_code=STALE_RESPONSE already carries
  the classification. Not yet removed from AGREEMENTS.md as of this log entry.

- prd.md (platform PRD, 2025-07-17) — deprecated 2026-08-30. Superseded by
  ../uvm_buffer_prd.md (DUT requirements) + README/FLOW (platform goals
  and state). Kept for history only; do not cite or update.
