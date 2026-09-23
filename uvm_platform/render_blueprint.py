#!/usr/bin/env python3
"""
render_blueprint.py — render a Blueprint into UVM SystemVerilog files.

Phase C of the IR split (see design_ir_split.md): the renderer now consumes
the composed Blueprint shape — SemanticIR + ImplementationContract — instead
of a flat dict. The boundary is clean: a Blueprint object goes in, SV comes
out. The renderer synthesizes implementation-derived stubs (T3 vsequencer)
from ImplementationContract.stubs_emitted before running the pipeline.

Reads the Pydantic-validated SemanticIR (legacy Blueprints with stubs baked
in continue to work via the legacy adapter in blueprint_ir_split.py), runs
path_assembler to derive config_db scopes, then walks the PIPELINE list
calling one render function per artifact type. Each render function takes
the Blueprint dict, a Jinja2 environment, and an output directory, and
writes its SV file(s) there.

Extensibility: add a new artifact type by appending to PIPELINE, writing
a template in templates/<name>.sv.j2, and writing a render function. No
other code needs to change.

Usage:
    python render_blueprint.py <blueprint.json> [--out OUTDIR]

Default OUTDIR is ../generated (sibling of uvm_platform/).
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# Extraction layer (sibling) provides the schema and scope-assembler.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "material_extracted"))
from blueprint_schema import Blueprint as SemanticIR  # noqa: E402
from blueprint_ir_split import (  # noqa: E402
    Blueprint as ComposedBlueprint,
    ImplementationContract,
    TIMER_STUBS,
    BUFFER_STUBS,
)
from path_assembler import assemble_scopes  # noqa: E402


TEMPLATES_DIR = HERE / "templates"
DEFAULT_OUTDIR = HERE.parent / "generated"


# ---------------------------------------------------------------------------
# Jinja env setup
# ---------------------------------------------------------------------------

def make_jinja_env() -> Environment:
    """Jinja env with sensible defaults for SV emission."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,  # blow up on undefined variables, don't silently render empty
    )
    return env


# ---------------------------------------------------------------------------
# Stub synthesis — ImplementationContract → SemanticIR additions
# ---------------------------------------------------------------------------

# Mapping from stub name (as appears in ImplementationContract.stubs_emitted)
# to the (role, class_name_template, default_instance_name) tuple that the
# renderer synthesizes when the semantic Blueprint doesn't already declare
# one. `class_name_template` is formatted with the block_name from SemanticIR.
STUB_DEFINITIONS = {
    "t3_vsequencer": {
        "role": "vsequencer",
        "class_name_template": "{block_name}_vsequencer",
        "instance_name": "m_vsequencer",
    },
    "t2_regmodel": {
        "role": "regmodel",
        "class_name_template": "{block_name}_reg_block",
        "instance_name": "m_regmodel",
    },
    "t2_reg_adapter": {
        "role": "reg_adapter",
        "class_name_template": "{block_name}_reg_adapter",
        "instance_name": "m_reg_adapter",
    },
}


def synthesize_stubs(semantic: SemanticIR, implementation: ImplementationContract) -> SemanticIR:
    """Return a NEW SemanticIR with implementation-derived stubs added to the
    env's components. The original is untouched.

    Per the IR-split architecture: implementation-derived stubs (T3 vsequencer,
    T2 regmodel/reg_adapter placeholders) are NEVER extracted from the spec —
    they're declared in ImplementationContract.stubs_emitted and filled by the
    renderer. If the spec happens to mention them (a hand-crafted Blueprint
    might), we don't duplicate.

    `confidence: inferred` is preserved on synthesized stubs so the R2 audit
    can flag them for review.
    """
    # Deep-copy the Pydantic model so we don't mutate the caller's object.
    sem = semantic.model_copy(deep=True)

    # Find the env (currently always exactly one). If zero, nothing to do.
    envs = sem.instances.envs
    if not envs:
        return sem
    env = next(iter(envs.values()))
    components = env.components

    block_name = sem.block_name
    for stub_name in implementation.stubs_emitted:
        spec = STUB_DEFINITIONS.get(stub_name)
        if spec is None:
            # Unknown stub name — skip with warning. The Literal type in
            # ImplementationContract should make this unreachable.
            print(f"  WARN: unknown stub '{stub_name}' in implementation.stubs_emitted")
            continue
        inst_name = spec["instance_name"]
        if inst_name in components:
            # Already declared in semantic — don't duplicate.
            continue
        # Synthesize as a proper Instance object so Pydantic invariants
        # hold (e.g., role is a Literal type, no extra fields allowed).
        # Confidence is "inferred" because the stub is reqspec-mandated,
        # not spec-stated — R2 audit will surface it for review.
        from blueprint_schema import Instance
        components[inst_name] = Instance(
            instance_name=inst_name,
            class_name=spec["class_name_template"].format(block_name=block_name),
            role=spec["role"],
            vif=None,
            confidence="inferred",
            children={},
        )

    return sem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_instance_prefix(bp_dict: dict, prefix: str) -> None:
    """Ensure every instance name in the Blueprint dict starts with `prefix`.

    UVM convention uses `m_` for member-variable instance names.  The
    deterministic extractor already applies it, but the LLM may forget.
    Rather than relying on prompt discipline, the renderer enforces the
    convention here — idempotently (names already starting with the prefix
    are left unchanged).

    Mutates bp_dict in place. Covers:
      - envs.*.instance_name
      - envs.*.components.* (dict key + instance_name, recursively)
      - config_db[].target_instance
    """
    def _prefix(name: str) -> str:
        return name if name.startswith(prefix) else f"{prefix}{name}"

    for env in bp_dict.get("instances", {}).get("envs", {}).values():
        env["instance_name"] = _prefix(env["instance_name"])
        _walk_components(env.get("components", {}), _prefix)

    for entry in bp_dict.get("config_db", []):
        entry["target_instance"] = _prefix(entry["target_instance"])


def _walk_components(components: dict, prefix_fn) -> None:
    """Walk a flat or nested component dict, renaming keys and values."""
    for name in list(components.keys()):
        comp = components.pop(name)
        new_name = prefix_fn(name)
        comp["instance_name"] = prefix_fn(comp["instance_name"])
        comp["children"] = comp.get("children", {})
        if comp["children"]:
            _walk_components(comp["children"], prefix_fn)
        components[new_name] = comp


def _type_to_iface_filename(iface_type: str) -> str:
    """Map `virtual apb_if` → `apb_if.sv`. Strip `virtual ` prefix."""
    bare = re.sub(r"^virtual\s+", "", iface_type).strip()
    return f"{bare}.sv"


def _bare_type(iface_type: str) -> str:
    """Strip `virtual ` prefix from a Blueprint `type` field."""
    return re.sub(r"^virtual\s+", "", iface_type).strip()


def _block_to_filename(block_name: str, class_name: str) -> str:
    """Map a class to its filename. If the class name already starts with
    the block_name prefix, don't double it.
    """
    if class_name == block_name or class_name.startswith(f"{block_name}_"):
        return f"{class_name}.sv"
    return f"{block_name}_{class_name}.sv"


def _class_to_filename(class_name: str) -> str:
    """Map a class name to its filename (UVM convention)."""
    return f"{class_name}.sv"


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    try:
        display = path.relative_to(HERE.parent)
    except ValueError:
        display = path  # out_dir outside the project tree
    print(f"  wrote {display}")


# ---------------------------------------------------------------------------
# Render functions — one per artifact type. Each takes the Blueprint dict,
# the Jinja env, and the output directory, and writes its SV file(s).
# ---------------------------------------------------------------------------

def check_interface_compatibility(interfaces: dict[str, dict]) -> dict[str, dict]:
    """Check that interface assets reusing the same interface type have compatible
    signal declarations.

    Returns a dict mapping bare_type -> canonical iface dict (one per unique type).
    Raises ValueError on any conflict between assets sharing a type.
    """
    by_type: dict[str, tuple[str, dict, list[tuple[str, int, str]]]] = {}
    canonical_ifaces: dict[str, dict] = {}

    for key, iface in interfaces.items():
        type_bare = _bare_type(iface["type"])
        signals = [
            (s["name"], s.get("width", 1), s["direction"])
            for s in iface.get("signals", [])
        ]
        if type_bare not in by_type:
            by_type[type_bare] = (key, iface, signals)
            canonical_ifaces[type_bare] = {**iface, "type_bare": type_bare}
        else:
            first_key, first_iface, first_signals = by_type[type_bare]
            if signals != first_signals:
                first_sig_map = {s[0]: s for s in first_signals}
                curr_sig_map = {s[0]: s for s in signals}
                diffs = []
                missing_in_curr = set(first_sig_map) - set(curr_sig_map)
                if missing_in_curr:
                    diffs.append(f"missing signals in '{key}': {sorted(missing_in_curr)}")
                extra_in_curr = set(curr_sig_map) - set(first_sig_map)
                if extra_in_curr:
                    diffs.append(f"extra signals in '{key}': {sorted(extra_in_curr)}")
                for name in set(first_sig_map) & set(curr_sig_map):
                    if first_sig_map[name] != curr_sig_map[name]:
                        diffs.append(
                            f"signal '{name}' mismatch: '{first_key}' has {first_sig_map[name][1:]}, "
                            f"'{key}' has {curr_sig_map[name][1:]}"
                        )
                diff_msg = "; ".join(diffs) if diffs else "signal ordering or definition difference"
                raise ValueError(
                    f"Interface type conflict for '{type_bare}': declarations in '{first_key}' "
                    f"and '{key}' differ: {diff_msg}"
                )

    return canonical_ifaces


def render_interfaces(bp: dict, env: Environment, out_dir: Path) -> list[Path]:
    """One SV file per unique Blueprint interface type.

    Reused interface types (e.g. multiple agents sharing the same virtual
    interface definition) are compatibility-checked; conflicting declarations
    raise ValueError. Each unique interface type is emitted exactly once.
    """
    interfaces = bp["shared_assets"]["interfaces"]
    canonical_ifaces = check_interface_compatibility(interfaces)

    paths = []
    template = env.get_template("interface.sv.j2")
    for type_bare, iface in canonical_ifaces.items():
        out_file = out_dir / _type_to_iface_filename(iface["type"])
        rendered = template.render(
            spec_source=bp["spec_source"],
            block_name=bp["block_name"],
            iface=iface,
        )
        _write(out_file, rendered)
        paths.append(out_file)
    return paths


def render_package(bp: dict, env: Environment, out_dir: Path) -> list[Path]:
    """The placeholder-classes package (vsequencer, reg_block, reg_adapter, scoreboard)."""
    template = env.get_template("package.sv.j2")

    # Guard register classes by post-synthesis role
    roles = {
        c.get("role")
        for env_inst in bp.get("instances", {}).get("envs", {}).values()
        for c in env_inst.get("components", {}).values()
    }
    has_regmodel = "regmodel" in roles
    has_reg_adapter = "reg_adapter" in roles

    # Collect vendor class names — classes the renderer does NOT generate,
    # listed in the package header for visibility.
    external_classes = sorted({
        c["class_name"]
        for env_inst in bp["instances"]["envs"].values()
        for c in env_inst["components"].values()
        if c.get("role") in ("active_agent", "passive_agent", "reg_predictor", "bfm")
        or c["class_name"] in ("amba_apb_agent", "irq_monitor_agent", "uvm_reg_predictor")
    })

    rendered = template.render(
        spec_source=bp["spec_source"],
        block_name=bp["block_name"],
        external_classes=external_classes,
        has_regmodel=has_regmodel,
        has_reg_adapter=has_reg_adapter,
    )
    out_file = out_dir / _block_to_filename(bp["block_name"], "pkg")  # simple_timer_pkg.sv
    _write(out_file, rendered)
    return [out_file]


def render_env(bp: dict, env: Environment, out_dir: Path) -> list[Path]:
    """The environment class. One env per Blueprint env (currently always 1)."""
    template = env.get_template("env.sv.j2")
    paths = []
    for env_key, env_inst in bp["instances"]["envs"].items():
        rendered = template.render(
            spec_source=bp["spec_source"],
            block_name=bp["block_name"],
            env=env_inst,
        )
        # File name: block + env_class_name → simple_timer_env.sv
        out_file = out_dir / _block_to_filename(bp["block_name"], env_inst["class_name"])
        _write(out_file, rendered)
        paths.append(out_file)
    return paths


def render_test(bp: dict, env: Environment, out_dir: Path) -> list[Path]:
    """The base test class. One per Blueprint env."""
    template = env.get_template("test.sv.j2")
    paths = []
    for env_inst in bp["instances"]["envs"].values():
        test_class = f"{bp['block_name']}_base_test"
        rendered = template.render(
            spec_source=bp["spec_source"],
            block_name=bp["block_name"],
            env=env_inst,
            test={
                "class_name": test_class,
                "env_instance_name": env_inst["instance_name"],
            },
        )
        out_file = out_dir / _block_to_filename(bp["block_name"], "base_test")
        _write(out_file, rendered)
        paths.append(out_file)
    return paths


def render_tb_top(bp: dict, env: Environment, out_dir: Path) -> list[Path]:
    """The testbench top module. One per Blueprint."""
    template = env.get_template("tb_top.sv.j2")
    test_class = f"{bp['block_name']}_base_test"
    interfaces = [
        {**i, "type_bare": _bare_type(i["type"])}
        for i in bp["shared_assets"]["interfaces"].values()
    ]
    config_db = [
        {**e, "type_bare": _bare_type(e["type"])}
        for e in bp["config_db"]
    ]
    rendered = template.render(
        spec_source=bp["spec_source"],
        block_name=bp["block_name"],
        interfaces=interfaces,
        config_db=config_db,
        test={"class_name": test_class},
    )
    out_file = out_dir / "tb_top.sv"
    _write(out_file, rendered)
    return [out_file]


# ---------------------------------------------------------------------------
# Pipeline — order matters: interfaces before tb_top (uses them),
# package before env/test (imported by them).
# ---------------------------------------------------------------------------

PIPELINE: list[Callable[[dict, Environment, Path], list[Path]]] = [
    render_interfaces,
    render_package,
    render_env,
    render_test,
    render_tb_top,
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def render(blueprint: ComposedBlueprint, out_dir: Path) -> int:
    """Render the composed Blueprint (semantic + implementation) into SV.

    Steps:
      1. Synthesize implementation-derived stubs (T3 vsequencer, T2
         regmodel/reg_adapter) into the semantic component list. Spec-already-
         declared versions are preserved unchanged.
      2. Build the legacy dict shape the path_assembler and templates expect.
      3. Run path_assembler to derive config_db scopes.
      4. Wipe output dir and run the PIPELINE.

    Returns 0 on success, non-zero on error.
    """
    semantic = blueprint.semantic
    implementation = blueprint.implementation

    print(f"[*] Blueprint: semantic={semantic.block_name!r}, "
          f"{len(semantic.shared_assets.interfaces)} interfaces, "
          f"{sum(len(e.components) for e in semantic.instances.envs.values())} semantic components")
    print(f"    ImplementationContract: {len(implementation.scopes)} scopes, "
          f"stubs={implementation.stubs_emitted}")

    # Step 1: synthesize stubs into a deep copy of semantic
    print("[*] Synthesizing implementation stubs into semantic...")
    semantic_with_stubs = synthesize_stubs(semantic, implementation)
    n_stubbed = sum(
        len(e.components) for e in semantic_with_stubs.instances.envs.values()
    ) - sum(
        len(e.components) for e in semantic.instances.envs.values()
    )
    if n_stubbed:
        print(f"    Added {n_stubbed} stub component(s)")
    else:
        print(f"    No stubs needed (already declared in semantic)")

    # Step 2: build the dict shape for path_assembler and templates
    bp_dict = semantic_with_stubs.model_dump()

    # Step 2.5: ensure all instance names carry the UVM `m_` prefix.
    # The prefix is owned by ImplementationContract so extractors (deterministic
    # and LLM) can output clean names — the convention is enforced here.
    print(f"[*] Applying instance prefix {implementation.instance_prefix!r}...")
    _ensure_instance_prefix(bp_dict, implementation.instance_prefix)

    # Step 3: assemble scopes
    print("[*] Assembling config_db scopes (T1)...")
    assemble_scopes(bp_dict)

    # Step 4: wipe out_dir, run pipeline
    if out_dir.exists():
        for f in out_dir.iterdir():
            if f.is_file():
                f.unlink()
        print(f"[*] Wiped {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[*] Running render pipeline...")
    env = make_jinja_env()
    all_paths = []
    for step in PIPELINE:
        print(f"  -> {step.__name__}")
        all_paths.extend(step(bp_dict, env, out_dir))

    print(f"\n[SUCCESS] Wrote {len(all_paths)} files to {out_dir}")
    return 0


def render_blueprint(
    blueprint_path: Path,
    out_dir: Path,
    stubs_emitted: list[str] | None = None,
) -> int:
    """Legacy file-based entry point. Load JSON, validate, wrap in a composed
    Blueprint with explicit ImplementationContract, delegate to render().

    For legacy Blueprints that already include T3 vsequencer / T2 stubs in
    semantic, the synthesize_stubs step is a no-op (won't duplicate).
    """
    print(f"[*] Loading Blueprint: {blueprint_path}")
    raw = json.loads(blueprint_path.read_text())

    print("[*] Validating against Pydantic schema (SemanticIR)...")
    try:
        semantic = SemanticIR.model_validate(raw)
    except Exception as e:
        print(f"FAIL: schema validation:\n{e}")
        return 1
    print(f"    OK — block_name={semantic.block_name!r}, "
          f"{len(semantic.shared_assets.interfaces)} interfaces, "
          f"{sum(len(e.components) for e in semantic.instances.envs.values())} components, "
          f"{len(semantic.config_db)} config_db entries")

    if stubs_emitted is None:
        stubs_emitted = (
            list(BUFFER_STUBS)
            if "buffer" in semantic.block_name
            else list(TIMER_STUBS)
        )

    # Wrap in composed Blueprint. ImplementationContract has explicit stubs_emitted;
    # path_assembler will fill scopes during render().
    composed = ComposedBlueprint(
        semantic=semantic,
        implementation=ImplementationContract(stubs_emitted=stubs_emitted),
    )
    return render(composed, out_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("blueprint", help="Path to Blueprint JSON file")
    ap.add_argument("--out", default=str(DEFAULT_OUTDIR), help="Output directory")
    args = ap.parse_args()

    blueprint_path = Path(args.blueprint)
    if not blueprint_path.exists():
        print(f"Error: Blueprint not found at {blueprint_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    return render_blueprint(blueprint_path, out_dir)


if __name__ == "__main__":
    sys.exit(main())
