#!/usr/bin/env python3
"""
phase_a_runner.py — Phase A end-to-end: load legacy Blueprint, split into
SemanticIR + ImplementationContract, feed back into the renderer, diff
output against the legacy baseline.

This is the validation. Goal: byte-identical render output, or we know the
seam is in the wrong place.

Usage:
    python phase_a_runner.py <legacy_blueprint.json> [--baseline DIR] [--out DIR]

Defaults:
    --baseline  ../generated_baseline    (saved by hand before Phase A)
    --out       ../generated_phase_a     (Phase A's render output, fresh each run)
"""
from __future__ import annotations
import argparse
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "uvm_platform"))

from blueprint_ir_split import from_legacy  # noqa: E402
from render_blueprint import render as composed_render  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("blueprint", help="Legacy Blueprint JSON")
    ap.add_argument("--baseline", default=str(HERE.parent / "generated_baseline"),
                    help="Baseline generated/ dir (pre-Phase-A render output)")
    ap.add_argument("--out", default=str(HERE.parent / "generated_phase_a"),
                    help="Phase A output dir (Phase-A render output)")
    args = ap.parse_args()

    blueprint_path = Path(args.blueprint)
    baseline_dir = Path(args.baseline)
    out_dir = Path(args.out)

    if not blueprint_path.exists():
        print(f"FAIL: legacy blueprint not found at {blueprint_path}")
        return 1
    if not baseline_dir.exists():
        print(f"FAIL: baseline dir not found at {baseline_dir}")
        return 1

    # ---- Step 1: load legacy and split ----
    print(f"[*] Loading legacy Blueprint: {blueprint_path}")
    legacy = json.loads(blueprint_path.read_text())
    print(f"    block_name={legacy['block_name']!r}, "
          f"{len(legacy['shared_assets']['interfaces'])} interfaces, "
          f"{sum(len(e['components']) for e in legacy['instances']['envs'].values())} components, "
          f"{len(legacy['config_db'])} config_db entries")

    print("[*] Splitting into SemanticIR + ImplementationContract...")
    bp = from_legacy(legacy)
    print(f"    SemanticIR: {len(bp.semantic.interfaces)} interfaces, "
          f"{len(bp.semantic.envs)} envs, "
          f"{len(bp.semantic.config_db)} config_db entries")
    print(f"    ImplementationContract: {len(bp.implementation.scopes)} scopes, "
          f"{len(bp.implementation.stubs_emitted)} stubs")

    # ---- Step 2: flatten to Pydantic, then render ----
    # from_legacy() produces a blueprint_ir_split.SemanticIR (dataclass),
    # but render() expects blueprint_schema.Blueprint (Pydantic). Convert
    # via to_renderer_dict() with validate=False (skip scope assembly),
    # strip the path_assembler-added fields, validate clean dict, then
    # let render() handle scope assembly + stubs + prefix.
    print("[*] Flattening Blueprint → Pydantic SemanticIR...")
    renderer_dict = bp.to_renderer_dict(validate=False)
    # Strip fields added by assemble_scopes() so we can re-validate
    for entry in renderer_dict.get("config_db", []):
        entry.pop("scope", None)
        entry.pop("type", None)
    for env in renderer_dict.get("instances", {}).get("envs", {}).values():
        env.pop("_path", None)
        for comp in env.get("components", {}).values():
            comp.pop("_path", None)

    from blueprint_schema import Blueprint as PydanticBlueprint
    pydantic_semantic = PydanticBlueprint.model_validate(renderer_dict)
    from blueprint_ir_split import Blueprint as ComposedBlueprint
    composed = ComposedBlueprint(
        semantic=pydantic_semantic,
        implementation=bp.implementation,
    )

    if out_dir.exists():
        shutil.rmtree(out_dir)
    print(f"[*] Rendering composed Blueprint to {out_dir}...")
    rc = composed_render(composed, out_dir)
    if rc != 0:
        print(f"FAIL: renderer returned {rc}")
        return rc

    # ---- Step 4: diff against baseline ----
    print(f"\n[*] Diffing {out_dir} against baseline {baseline_dir}...")
    return diff_dirs(baseline_dir, out_dir)


def diff_dirs(baseline: Path, candidate: Path) -> int:
    """Compare every file in baseline/ to candidate/ by sha256.

    Reports per-file: identical / diff. Exits 0 if all files match, 1 if any
    diverge, 2 on missing files.
    """
    if not candidate.exists():
        print(f"FAIL: candidate dir does not exist: {candidate}")
        return 2

    baseline_files = sorted(p.name for p in baseline.iterdir() if p.is_file())
    candidate_files = sorted(p.name for p in candidate.iterdir() if p.is_file())

    missing = set(baseline_files) - set(candidate_files)
    extra = set(candidate_files) - set(baseline_files)
    if missing:
        print(f"FAIL: missing in candidate: {sorted(missing)}")
        return 2
    if extra:
        print(f"WARN: extra in candidate (not in baseline): {sorted(extra)}")

    all_match = True
    for name in baseline_files:
        a = (baseline / name).read_bytes()
        b = (candidate / name).read_bytes()
        ha = hashlib.sha256(a).hexdigest()[:12]
        hb = hashlib.sha256(b).hexdigest()[:12]
        status = "identical" if a == b else "DIVERGES"
        print(f"  {name:35s}  baseline={ha}  phase_a={hb}  {status}")
        if a != b:
            all_match = False

    print()
    if all_match:
        print("=" * 60)
        print("PHASE A RESULT: BYTE-IDENTICAL")
        print("=" * 60)
        print("The IR split seam is in the right place. Every legacy field")
        print("classifies cleanly into SemanticIR or ImplementationContract,")
        print("and re-flattening through the new shape produces identical SV.")
        print()
        print("Decision: adopt the split. Proceed to Phase B (extractors emit")
        print("Semantic IR only) when ready.")
        return 0
    else:
        print("=" * 60)
        print("PHASE A RESULT: DIVERGENCE")
        print("=" * 60)
        print("Some file(s) differ. The classification has a bug — a field")
        print("was put in the wrong layer, or a derivation is missing.")
        print("Diff the differing file(s) to find the leak.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
