#!/usr/bin/env python3
"""
path_assembler.py — derives uvm_config_db scope strings from a Blueprint's
instance tree. The single source of truth for paths lives here, not in
the spec or in the LLM extraction.

Per T1 (spec §2 addendum): no string-convention linking. Every config_db
entry's `scope` field is computed by walking the instance tree, not by
the LLM inventing a path string.

Usage:
    from path_assembler import assemble_scopes, validate_blueprint

    blueprint = json.load(open("blueprint.json"))
    assemble_scopes(blueprint)        # mutates in place, fills `scope` on every config_db entry
    validate_blueprint(blueprint)     # raises on any unresolved interface_ref or duplicate name
"""
from __future__ import annotations
import json
from typing import Any


# ----------------------------------------------------------------------------
# Tree helpers
# ----------------------------------------------------------------------------

def _index_instances(blueprint: dict) -> dict[str, dict]:
    """Build a flat index: instance_name -> instance node, walking the whole tree.

    An "instance" is any node in the spec with an `instance_name` field:
    env, agent, vsequencer, regmodel, scoreboard, predictor, adapter, etc.
    """
    index: dict[str, dict] = {}

    def walk(node: Any, parent_path: str) -> None:
        if isinstance(node, dict):
            name = node.get("instance_name")
            if name:
                if name in index:
                    raise ValueError(
                        f"duplicate instance_name '{name}' "
                        f"(first seen at {index[name].get('_path')}, "
                        f"again at {parent_path})"
                    )
                node["_path"] = f"{parent_path}.{name}" if parent_path else name
                index[name] = node
                parent_path = node["_path"]
            for v in node.values():
                walk(v, parent_path)
        elif isinstance(node, list):
            for item in node:
                walk(item, parent_path)

    walk(blueprint, "")
    return index


def _env_path(blueprint: dict, env_name: str) -> str:
    """Compute the full UVM path to an env: <test_name>.<env_instance_name>.

    The test name is the standard UVM convention `uvm_test_top`; this is
    fixed by the simulator, not by the spec. The env's instance name is
    the *only* spec-owned fact here.
    """
    env = blueprint["instances"]["envs"].get(env_name)
    if not env:
        raise KeyError(f"env '{env_name}' not declared in blueprint.instances.envs")
    return f"uvm_test_top.{env['instance_name']}"


# ----------------------------------------------------------------------------
# Scope assembly (the only place scope strings are produced)
# ----------------------------------------------------------------------------

def assemble_scopes(blueprint: dict) -> dict:
    """Mutate blueprint in place: for every config_db entry, set `scope` to the
    derived path. Returns the blueprint for chaining.

    The LLM never sees this code and never has the opportunity to invent
    a scope string. It only declares which `instance_name` receives which
    `interface_ref`; we turn that into a path here.
    """
    instances = _index_instances(blueprint)

    # Map each interface_ref to the interface type it points at.
    interfaces = blueprint.get("shared_assets", {}).get("interfaces", {})
    if_ref_to_type = {k: v["type"] for k, v in interfaces.items()}

    for entry in blueprint.get("config_db", []):
        if_ref = entry.get("interface_ref")
        if not if_ref:
            raise ValueError(
                f"config_db entry missing 'interface_ref': {entry}. "
                f"Per T1, every config_db entry must reference a shared asset by key."
            )
        if if_ref not in if_ref_to_type:
            raise ValueError(
                f"config_db entry's interface_ref '{if_ref}' does not resolve "
                f"to any declared interface in shared_assets.interfaces. "
                f"Known: {list(if_ref_to_type)}"
            )

        target_instance = entry.get("target_instance")
        if not target_instance:
            raise ValueError(
                f"config_db entry missing 'target_instance': {entry}. "
                f"Spec must name the receiver instance; path is derived from it."
            )
        if target_instance not in instances:
            raise ValueError(
                f"config_db entry's target_instance '{target_instance}' "
                f"is not a declared instance in the blueprint. "
                f"Known instances: {list(instances)}"
            )

        # The actual derivation: <test_root>.<env>.<target_instance>
        # For env-level entries (target = env itself), this becomes <test>.<env>.*
        target_node = instances[target_instance]
        # An instance is the env itself iff its instance_name matches the
        # env's instance_name. We look that up from the envs block.
        env_owner = _find_parent_env(blueprint, target_instance)
        is_env_itself = env_owner is None  # envs don't have a parent env

        if is_env_itself:
            # Receiver is the env itself: scope is the env's full path + ".*"
            # so all children inherit the asset.
            entry["scope"] = f"uvm_test_top.{target_node['instance_name']}.*"
        else:
            # Receiver is a child of some env: scope = <env>.<child>.*
            env_full = _env_path(blueprint, env_owner)
            entry["scope"] = f"{env_full}.{target_instance}.*"

        # Stamp the type from the shared asset so the renderer doesn't have to
        # look it up again.
        entry["type"] = if_ref_to_type[if_ref]
        # Field name stays spec-owned (it's a naming decision, not a derivation).
        # If absent, default to "vif" — caller is responsible for noting the
        # defaulted value; Pydantic's default is "vif" so this branch is hit
        # only when a hand-crafted Blueprint omitted it.
        entry.setdefault("field_name", "vif")

    return blueprint


def _find_parent_env(blueprint: dict, instance_name: str) -> str | None:
    """Walk the envs to find which env contains this instance.

    Matches the Blueprint shape: envs[name].components is a dict[str, Instance].
    """
    for env_name, env_node in blueprint.get("instances", {}).get("envs", {}).items():
        components = env_node.get("components", {})
        if instance_name in components:
            return env_name
    return None


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------

def validate_blueprint(blueprint: dict) -> list[str]:
    """Return a list of issues found. Empty list = clean.

    Checks (independent of scope assembly):
      - Every config_db entry has a resolvable interface_ref
      - No duplicate instance_name across the whole tree
      - Every asset key declared in shared_assets is actually referenced
        somewhere (or explicitly marked unused) — catches typos on the asset side
    """
    issues: list[str] = []

    # 1. Resolve index first — surfaces duplicate names.
    try:
        instances = _index_instances(blueprint)
    except ValueError as e:
        issues.append(str(e))
        return issues  # can't continue without a clean index

    # 2. Check interface_ref resolution
    interfaces = blueprint.get("shared_assets", {}).get("interfaces", {})
    for i, entry in enumerate(blueprint.get("config_db", [])):
        if_ref = entry.get("interface_ref")
        if not if_ref:
            issues.append(f"config_db[{i}]: missing interface_ref")
            continue
        if if_ref not in interfaces:
            issues.append(
                f"config_db[{i}]: interface_ref '{if_ref}' "
                f"not in shared_assets.interfaces"
            )
        target = entry.get("target_instance")
        if target and target not in instances:
            issues.append(
                f"config_db[{i}]: target_instance '{target}' "
                f"not declared in any instance tree"
            )

    # 3. Unused assets (typo detector)
    referenced_assets: set[str] = set()
    for entry in blueprint.get("config_db", []):
        if entry.get("interface_ref"):
            referenced_assets.add(entry["interface_ref"])
    for asset_key in interfaces:
        if asset_key not in referenced_assets:
            issues.append(
                f"warning: interface '{asset_key}' declared in shared_assets "
                f"but never referenced by any config_db entry"
            )

    # 4. Shared interface compatibility check
    by_type: dict[str, tuple[str, list[tuple[str, int, str]]]] = {}
    for key, iface in interfaces.items():
        bare = iface.get("type", "").replace("virtual ", "").strip()
        signals = [
            (s["name"], s.get("width", 1), s["direction"])
            for s in iface.get("signals", [])
        ]
        if bare not in by_type:
            by_type[bare] = (key, signals)
        else:
            first_key, first_signals = by_type[bare]
            if signals != first_signals:
                issues.append(
                    f"interface type conflict for '{bare}': '{first_key}' and '{key}' "
                    f"declare incompatible signals"
                )

    return issues


# ----------------------------------------------------------------------------
# CLI for ad-hoc testing
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Assemble + validate a Blueprint")
    ap.add_argument("blueprint", help="Path to Blueprint JSON file")
    ap.add_argument("--out", help="Write assembled blueprint here (default: stdout)")
    args = ap.parse_args()

    with open(args.blueprint) as f:
        bp = json.load(f)

    issues = validate_blueprint(bp)
    if issues:
        print("VALIDATION ISSUES:", file=sys.stderr)
        for line in issues:
            print(f"  - {line}", file=sys.stderr)
        sys.exit(1)

    assemble_scopes(bp)

    out = json.dumps(bp, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
    else:
        print(out)
