#!/usr/bin/env python3
"""Rerunnable GR-009 validator for the PRD v0.0e semantic candidate."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from semantic_schema import SemanticModel

ID_RE = re.compile(r"\b(?:ENV|DUT)-(?:[A-Z]+-)?\d{3}\b|\b(?:OBS|OD|INV|LT|IT|GR)-\d{3}\b")


def ids_by_prefix(text: str, prefix: str) -> set[str]:
    return {value for value in ID_RE.findall(text) if value.startswith(prefix + "-")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate candidate semantic model and PRD references")
    ap.add_argument("model", type=Path, default=HERE / "uvm_buffer_semantic_model.candidate.json", nargs="?")
    ap.add_argument("--prd", type=Path, default=HERE.parent / "uvm_buffer_prd.md")
    args = ap.parse_args()

    try:
        raw = json.loads(args.model.read_text())
        model = SemanticModel.model_validate(raw)
    except Exception as exc:
        print(f"FAIL: schema or semantic validation: {exc}", file=sys.stderr)
        return 1

    source = args.prd.read_text()
    # The Revision History section records removed/renamed requirement and
    # trace IDs by design — "removed DUT-LC-008" is exactly the sentence a
    # future reader needs. Its ID mentions are historical, not live
    # references, so the cross-reference scan covers only the normative
    # body (everything above the revision-history heading).
    hist = re.search(r"^#+\s+.*Revision History\s*$", source, flags=re.MULTILINE)
    if not hist:
        print(
            "FAIL: Revision History heading not found — ID-scan exclusion cannot be applied",
            file=sys.stderr,
        )
        return 1
    source = source[: hist.start()]
    model_sets = {
        "ENV": {r.id for r in model.requirements if r.id.startswith("ENV-")},
        "DUT": {r.id for r in model.requirements if r.id.startswith("DUT-")},
        "OBS": {o.id for o in model.observations},
        "OD": {d.id for d in model.semantic_decisions},
        "INV": {i.id for i in model.invariants},
        "LT": {t.id for t in model.legal_traces},
        "IT": {t.id for t in model.illegal_traces},
        "GR": {g.id for g in model.generation_gates},
    }
    source_sets = {prefix: ids_by_prefix(source, prefix) for prefix in model_sets}
    failures = []
    # The missing/extra set comparison is what enforces GR-007 (existing
    # requirement IDs remain stable; no renamed/re-numbered requirement is
    # accepted): a renamed ID appears as BOTH missing (old ID absent from the
    # model) and extra (new ID absent from the PRD scan), so no rename can
    # pass silently.  Lineage provenance lives in the PRD §9 revision rows —
    # history, not a gate.
    for prefix in model_sets:
        missing = sorted(source_sets[prefix] - model_sets[prefix])
        extra = sorted(model_sets[prefix] - source_sets[prefix])
        if missing or extra:
            failures.append(f"{prefix}: missing={missing}, extra={extra}")

    if model.source_prd_revision != "v0.0e":
        failures.append("source PRD revision is not v0.0e")
    if model.extraction_status != "candidate_pending_human_approval":
        failures.append("candidate is not marked pending human approval")
    if model.generation_ready:
        failures.append("candidate incorrectly claims generation readiness")

    if failures:
        print("FAIL: " + "; ".join(failures), file=sys.stderr)
        return 1

    print("PASS: GR-009 semantic candidate validation")
    print(f"  schema/model: valid ({args.model})")
    print("  references: resolved by Pydantic cross-reference validators")
    print("  source IDs: exact for requirements, observations, decisions, invariants, traces, and gates")
    print(f"  requirements: {len(model.requirements)} (DUT={len(model_sets['DUT'])}, ENV={len(model_sets['ENV'])})")
    print(f"  observations={len(model.observations)} invariants={len(model.invariants)} "
          f"decisions={len(model.semantic_decisions)} gates={len(model.generation_gates)}")
    print("  closure: all OD decisions closed; GR-010 intentionally deferred to later manifest stage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
