#!/usr/bin/env python3
"""
blueprint_ir_split.py — Phase A spike of the IR split.

Splits the legacy `Blueprint` shape into two layers:

    SemanticIR            — what is true about the spec
                             (interfaces, registers, components, config_db wire list)

    ImplementationContract — what the renderer derives (no spec facts here)
                             (uvm_config_db scopes, file layout, stub set)

    Blueprint(semantic, implementation) — composed artifact, the new "contract"
                            between extractors and renderer.

This is the cheap validation step. Goal: prove that classifying each legacy
field as semantic-vs-implementation produces a Blueprint whose render output
is byte-identical to today's. If yes, the seam is in the right place and the
refactor is cost-free to adopt.

If a field's classification is wrong, render output diverges — fix and retry.
If we can't get byte-identical after a few tries, the spike is invalidated
and we shelve the split until after T3.

No edits to existing files. The legacy Blueprint (blueprint_schema.py) and
path_assembler.py stay untouched. This module is purely additive.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from path_assembler import assemble_scopes  # noqa: E402


# ----------------------------------------------------------------------------
# Semantic IR — pure facts about the spec
# ----------------------------------------------------------------------------

@dataclass
class Signal:
    """One signal on a virtual interface. Pure spec fact."""
    name: str
    width: int
    direction: Literal["input", "output", "inout"]
    confidence: Literal["explicit", "inferred", "unknown"]


@dataclass
class InterfaceAsset:
    """A virtual interface. Pure spec fact: name, signals, widths."""
    key: str
    type: str  # e.g. "virtual apb_if"
    confidence: Literal["explicit", "inferred", "unknown"]
    signals: list[Signal]


@dataclass
class Instance:
    """One named instance in the env topology. Pure spec fact."""
    instance_name: str
    class_name: str
    role: str
    vif: str | None
    confidence: Literal["explicit", "inferred", "unknown"]
    children: dict[str, "Instance"] = field(default_factory=dict)


@dataclass
class EnvInstance:
    """The environment and its components."""
    instance_name: str
    class_name: str
    confidence: Literal["explicit", "inferred", "unknown"]
    components: dict[str, Instance]


@dataclass
class ConfigDBEntry:
    """One uvm_config_db::set() entry. Pure spec fact: who gets which asset.

    The `scope` is implementation-derived and NOT stored here.
    """
    target_instance: str
    interface_ref: str
    field_name: str
    delivery: Literal["set"]
    confidence: Literal["explicit", "inferred", "unknown"]


@dataclass
class SemanticIR:
    """The semantic layer. Everything the spec says, nothing about how it
    renders. Confidence tags preserved per R1.
    """
    spec_source: str
    block_name: str
    interfaces: dict[str, InterfaceAsset]            # shared_assets.interfaces
    envs: dict[str, EnvInstance]                     # instances.envs
    config_db: list[ConfigDBEntry]                   # config_db (without scopes)


# ----------------------------------------------------------------------------
# Implementation Contract — what the renderer derives
# ----------------------------------------------------------------------------

@dataclass
class ScopeAssignment:
    """One derived uvm_config_db scope string. Produced by path_assembler."""
    config_db_index: int   # index into SemanticIR.config_db
    scope: str             # e.g. "uvm_test_top.m_env.m_apb_agent.*"
    type: str              # e.g. "virtual apb_if" (stamped from shared asset)


@dataclass
class FileAssignment:
    """Which class lives in which generated .sv file."""
    class_name: str
    filename: str          # e.g. "apb_if.sv" or "simple_timer_pkg.sv"


@dataclass
class ImplementationContract:
    """The implementation layer. No spec facts; all derived or constant."""
    scopes: list[ScopeAssignment] = field(default_factory=list)
    file_layout: list[FileAssignment] = field(default_factory=list)
    # T2/T3 stubs always emitted per MVP-tier tenets (reqspec §2a).
    # Stored here so the seam between "spec owns" and "tool always emits" is explicit.
    stubs_emitted: list[Literal["t3_vsequencer", "t2_regmodel", "t2_reg_adapter"]] = field(
        default_factory=lambda: ["t3_vsequencer", "t2_regmodel", "t2_reg_adapter"]
    )
    # UVM naming convention: instance names of env children start with this
    # prefix (e.g. "m_" for member variables). The renderer applies this
    # prefix during rendering so extractors (deterministic and LLM) can
    # output clean names — the convention is enforced in one place.
    instance_prefix: str = "m_"


# ----------------------------------------------------------------------------
# Blueprint = composition of the two layers
# ----------------------------------------------------------------------------

@dataclass
class Blueprint:
    """The new top-level contract. Composed, not flat.

    `to_renderer_dict()` flattens back into the legacy shape so today's
    renderer can consume it. That's the bridge for Phase A: validate the
    seam by proving render output is byte-identical.
    """
    semantic: SemanticIR
    implementation: ImplementationContract

    def to_renderer_dict(self, validate: bool = True) -> dict:
        """Reconstruct the legacy Blueprint dict shape so the existing
        renderer can consume this Blueprint unchanged.

        Order matches the legacy flow (validate clean → mutate with scopes):
        1. Build clean dict from semantic (no scopes yet)
        2. Validate against the legacy Pydantic schema (proves the semantic
           classification is faithful — any miss surfaces as a schema error)
        3. Run path_assembler to derive scopes (mutates in place)
        4. Return the dirty dict for the renderer

        `validate=True` by default; set False if you're sure and want speed.
        """
        bp: dict = {
            "spec_source": self.semantic.spec_source,
            "block_name": self.semantic.block_name,
            "shared_assets": {
                "interfaces": {
                    k: {
                        "key": v.key,
                        "type": v.type,
                        "confidence": v.confidence,
                        "signals": [
                            {
                                "name": s.name,
                                "width": s.width,
                                "direction": s.direction,
                                "confidence": s.confidence,
                            }
                            for s in v.signals
                        ],
                    }
                    for k, v in self.semantic.interfaces.items()
                }
            },
            "instances": {
                "envs": {
                    ek: {
                        "instance_name": ev.instance_name,
                        "class_name": ev.class_name,
                        "confidence": ev.confidence,
                        "components": {
                            ik: _instance_to_dict(i)
                            for ik, i in ev.components.items()
                        },
                    }
                    for ek, ev in self.semantic.envs.items()
                }
            },
            "config_db": [
                {
                    "target_instance": e.target_instance,
                    "interface_ref": e.interface_ref,
                    "field_name": e.field_name,
                    "delivery": e.delivery,
                    "confidence": e.confidence,
                }
                for e in self.semantic.config_db
            ],
        }

        # Validate the clean dict FIRST (before any mutation). Legacy schema
        # is extra="forbid", so any extra field from a previous path_assembler
        # call would be rejected.
        if validate:
            from blueprint_schema import Blueprint as LegacyBlueprint
            LegacyBlueprint.model_validate(bp)

        # Path_assembler mutates in place — give it the dict, get back
        # the same dict with `scope` and `type` filled on each config_db
        # entry. We round-trip through it so the source of truth for
        # scopes stays path_assembler.py, not this module.
        assemble_scopes(bp)
        return bp


def _instance_to_dict(i: Instance) -> dict:
    return {
        "instance_name": i.instance_name,
        "class_name": i.class_name,
        "role": i.role,
        "vif": i.vif,
        "confidence": i.confidence,
        "children": {ck: _instance_to_dict(c) for ck, c in i.children.items()},
    }


# ----------------------------------------------------------------------------
# Classifier — splits a legacy Blueprint dict into SemanticIR + Implementation
# ----------------------------------------------------------------------------

def from_legacy(legacy: dict) -> Blueprint:
    """Take a legacy Blueprint dict (the shape `blueprint_schema.Blueprint`
    produces via `model_dump()`) and split it into the new Blueprint.

    Classification rules (Phase A — these are what we're validating):
      - spec_source, block_name              → SemanticIR
      - shared_assets.interfaces.*           → SemanticIR (no transformation)
      - instances.envs.*                     → SemanticIR (instance_name stays as-is)
      - config_db[].target/interface_ref/... → SemanticIR (no scope here)
      - scopes                               → ImplementationContract (derived via path_assembler)

    If any of these rules are wrong, render output diverges and we know.
    """
    semantic = SemanticIR(
        spec_source=legacy["spec_source"],
        block_name=legacy["block_name"],
        interfaces={
            k: InterfaceAsset(
                key=v["key"],
                type=v["type"],
                confidence=v["confidence"],
                signals=[
                    Signal(
                        name=s["name"],
                        width=s["width"],
                        direction=s["direction"],
                        confidence=s["confidence"],
                    )
                    for s in v["signals"]
                ],
            )
            for k, v in legacy["shared_assets"]["interfaces"].items()
        },
        envs={
            ek: EnvInstance(
                instance_name=ev["instance_name"],
                class_name=ev["class_name"],
                confidence=ev["confidence"],
                components={
                    ik: _dict_to_instance(ik, i)
                    for ik, i in ev["components"].items()
                },
            )
            for ek, ev in legacy["instances"]["envs"].items()
        },
        config_db=[
            ConfigDBEntry(
                target_instance=e["target_instance"],
                interface_ref=e["interface_ref"],
                field_name=e.get("field_name", "vif"),
                delivery=e.get("delivery", "set"),
                confidence=e["confidence"],
            )
            for e in legacy["config_db"]
        ],
    )

    # Implementation: run path_assembler on a reconstructed legacy dict to
    # get scopes. This is the *only* implementation-derived thing we're
    # pulling out of the legacy shape. Everything else is metadata about
    # the renderer that doesn't affect output today.
    bp_for_scope = {
        "spec_source": semantic.spec_source,
        "block_name": semantic.block_name,
        "shared_assets": {"interfaces": legacy["shared_assets"]["interfaces"]},
        "instances": legacy["instances"],
        "config_db": [
            {
                "target_instance": e.target_instance,
                "interface_ref": e.interface_ref,
                "field_name": e.field_name,
                "delivery": e.delivery,
                "confidence": e.confidence,
            }
            for e in semantic.config_db
        ],
    }
    assemble_scopes(bp_for_scope)

    implementation = ImplementationContract(
        scopes=[
            ScopeAssignment(
                config_db_index=i,
                scope=entry["scope"],
                type=entry["type"],
            )
            for i, entry in enumerate(bp_for_scope["config_db"])
        ],
    )

    return Blueprint(semantic=semantic, implementation=implementation)


def _dict_to_instance(name: str, d: dict) -> Instance:
    return Instance(
        instance_name=d.get("instance_name", name),
        class_name=d["class_name"],
        role=d["role"],
        vif=d.get("vif"),
        confidence=d["confidence"],
        children={
            ck: _dict_to_instance(ck, c) for ck, c in d.get("children", {}).items()
        },
    )


# ----------------------------------------------------------------------------
# CLI — emit a quick summary of the classification for inspection
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys

    if len(sys.argv) < 2:
        print("Usage: python blueprint_ir_split.py <legacy_blueprint.json>")
        sys.exit(1)

    legacy = json.loads(Path(sys.argv[1]).read_text())
    bp = from_legacy(legacy)

    print(f"SemanticIR:")
    print(f"  spec_source   = {bp.semantic.spec_source}")
    print(f"  block_name    = {bp.semantic.block_name}")
    print(f"  interfaces    = {len(bp.semantic.interfaces)} ({', '.join(bp.semantic.interfaces)})")
    print(f"  envs          = {len(bp.semantic.envs)} ({', '.join(bp.semantic.envs)})")
    for ek, ev in bp.semantic.envs.items():
        print(f"    {ek}: {len(ev.components)} components "
              f"({', '.join(ev.components)})")
    print(f"  config_db     = {len(bp.semantic.config_db)} entries")
    print()
    print(f"ImplementationContract:")
    print(f"  scopes        = {len(bp.implementation.scopes)} (derived)")
    for s in bp.implementation.scopes:
        print(f"    [{s.config_db_index}] {s.scope}  type={s.type}")
    print(f"  stubs_emitted = {bp.implementation.stubs_emitted}")
