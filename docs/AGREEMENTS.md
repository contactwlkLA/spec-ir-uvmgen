# Agreements — PRD v0.0e / candidate-v0.0e-001

**Revision:** 3.1 (2026-09-21 23:57 PDT)

Source: `../uvm_buffer_prd.md` (v0.0e) + `material_extracted/uvm_buffer_semantic_model.candidate.json` (`candidate-v0.0e-001`). Private pre-publication history is intentionally omitted from this release.
Status: GR-009 PASS, `candidate_pending_human_approval` — GR-010 deferred

## agree-2 — Flush observability (OD-005), no handshake
- No oracle↔scoreboard flush handshake. One-way `observation_seq` + `reset_epoch` + `flushed_id_set` only.
- OD-005 reservation stays test-held: mutation test reserves flushed ID until stale `OBS-002` observed; SB pairs by `observation_seq` and reports.
- Rationale: keeps GR-003 / OD-008 ownership intact; avoids liveness coupling.

## agree-3 — Oracle/scoreboard ownership (OD-008)
- Keep OD-008 closed: oracle solely owns `outstanding_table`, occupancy, epoch, service_counter, watchdog, `golden_mem`, `completed_id_set`, `flushed_id_set` + expected-result production.
- Scoreboard: pair `OBS-002` ↔ oracle-result by `observation_seq`, compare, report — zero behavioral state. No duplicate table/memory.
- Don't duplicate state in SB; revisit only for multi-agent/Phase D.

## Other dispositions (no new agree ID — deferred/enhancement)
- **Symbolic params vs mock defaults**: separately recorded (`parameters` vs `mock_encodings`); mock `DELAY 1..8`, `READ=0/WRITE=1/OK=0` not normative. No reopen of OD-006.
- **Nondeterminism**: ND-002 (completion selection/timing C+D..256) deferred to behavior model.
- **Traceability**: PRD §5.5 mapping requirement→observation→checker/invariant→primary trace complete; LT/IT present.
- **Gate bookkeeping**: GR-001..008 PRD-claimed pass, GR-009 validator-proven, GR-010 `deferred_later_stage`.
- **Ownership boundary final word**: agree-2/3 provisional; hardened rule is whatever v0.0e checker/invariants (INV-001..016, CHK-*) prove.
