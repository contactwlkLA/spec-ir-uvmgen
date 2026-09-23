# Buffer ↔ Blueprint Structural Integration — Task List

Source: `merge_to_buf_str_pt_plan_5.md` Rev 5 (2026-09-22 12:48 PDT).
Written: 2026-09-22 20:56 UTC. Updated: 2026-09-23 00:05 UTC. Status: All tasks 1–11 complete.

| Checkbox | # | Description |
|---|---|---|
| [x] | 1 | Confirm structural entry point — inspect schema/renderer + buffer artifacts only; supported vs external/unimplemented; check generation preconditions, no general audit |
| [x] | 2 | Make stubs per-design — `stubs_emitted` explicit in contract + callers; buffer T3-only, timer existing set; guard register classes by post-synthesis role |
| [x] | 3 | Author buffer Blueprint — map PRD topology, interface refs, config scopes, class refs, intended connections; record D1/D2, concrete widths/encodings, source revs; mark external/unimplemented honestly |
| [x] | 4 | Resolve shared interfaces — compatibility-check reused interface types, emit once each; reject conflicts, no silent overwrite/drop |
| [x] | 5 | Render + structurally check — input validation + buffer output assertions (10 checks); reject 2 defective copies on disposable outputs; timer-vs-baseline unchanged; no SV compilation |
| [x] | 6 | Static oracle-to-UVM contract check (§5) — read-only table with source locations + limits; 30–60 min timebox |
| [x] | 7 | Update README/status framing — structural milestone, finishing line, implemented/deferred boundary, resume-ready limit |
| [x] | 8 | Update architecture docs — buffer hand-authored Blueprint path + structural boundary in existing doc; no new arch document |
| [x] | 9 | Update FLOW docs — structural rendering shown; simulation/behavioral stages explicitly deferred |
| [x] | 10 | Record static-check evidence — oracle-to-UVM table + implemented / structurally-checked / deferred status in existing proof/status material |
| [x] | 11 | Refresh architecture diagram — regenerate `spec-ir-uvmgen-architecture.png` via `docs/diagrams/render_architecture.py` to show buffer Blueprint→SV path; verify caption ↔ PNG ↔ prose agree; do last, after Tasks 7–10 settle |
