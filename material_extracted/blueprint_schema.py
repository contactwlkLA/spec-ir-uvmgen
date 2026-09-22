#!/usr/bin/env python3
"""
blueprint_schema.py — Pydantic models for the UVM Blueprint.

Single source of truth for the Blueprint shape, used by:
  - The LLM extraction prompt (via Blueprint.model_json_schema())
  - The validator (Blueprint.model_validate)
  - The renderer / path assembler (typed attribute access, not raw dicts)

R1 (confidence-tag enforcement) is implemented as Literal types in the models.
Any value not in the allowed set raises ValidationError at parse time.

R2 (triage by blast radius) is a *future* relaxation: every required field
here is "strict." To loosen later, change a field from required to optional
and add a default + confidence tag. Don't change the Literal set.
"""
from __future__ import annotations
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict


# ----------------------------------------------------------------------------
# Enums and literals (the strict sets — R1 enforcement)
# ----------------------------------------------------------------------------

# R1: every confidence tag must be one of these three. Anything else is rejected.
Confidence = Literal["explicit", "inferred", "unknown"]

# Roles an instance can play in the env. Extending this list is a schema break.
InstanceRole = Literal[
    "env",
    "active_agent",
    "passive_agent",
    "vsequencer",        # T3 stub
    "regmodel",
    "reg_adapter",
    "reg_predictor",
    "scoreboard",
    "bfm",               # T5 hook
]

# How an asset is delivered to its target. Only `set` is supported; explicit
# values keep the renderer from having to infer delivery semantics.
DeliveryKind = Literal["set"]

# Signal directions on a virtual interface. `inout` is included for completeness
# but most agent-facing interfaces use only input/output.
SignalDirection = Literal["input", "output", "inout"]


# ----------------------------------------------------------------------------
# Signals
# ----------------------------------------------------------------------------

class Signal(BaseModel):
    """One signal on a virtual interface. Width in bits; direction is one
    of input/output/inout. Confidence-tagged per R1.
    """
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Signal name, e.g. 'paddr'")
    width: int = Field(default=1, ge=1, description="Bit width (default 1)")
    direction: SignalDirection
    confidence: Confidence


# ----------------------------------------------------------------------------
# Shared asset dictionary
# ----------------------------------------------------------------------------

class InterfaceAsset(BaseModel):
    """A virtual interface handle that lives in `top` and gets propagated
    via uvm_config_db. `key` is the shared-asset key used in interface_ref
    pointers elsewhere in the Blueprint.

    Per T1 addendum: `key` is the only way to refer to this interface. No
    string conventions; every reference must use this key.

    `signals` declares the SV signals inside the interface body. Without
    these the renderer cannot emit a complete interface declaration.
    """
    model_config = ConfigDict(extra="forbid")
    key: str = Field(..., description="Shared-asset key, e.g. 'apb_ctrl_vif'")
    type: str = Field(..., description="Virtual interface type, e.g. 'virtual apb_if'")
    confidence: Confidence
    signals: list[Signal] = Field(
        default_factory=list,
        description="Signals declared inside this interface body",
    )

    @model_validator(mode="after")
    def _key_must_end_in_vif(self) -> "InterfaceAsset":
        """Convention: shared-asset keys for virtual interfaces end in `_vif`.
        Catches typos like `apb_ctrl` vs `apb_ctrl_vif` early.
        """
        if not self.key.endswith("_vif"):
            raise ValueError(
                f"interface key '{self.key}' should end in '_vif' "
                f"(convention for shared-asset virtual interface keys)"
            )
        return self


class SharedAssets(BaseModel):
    """The shared-asset dictionary. Everything in here is referenced by `key`
    from elsewhere in the Blueprint. No duplication of the asset itself.
    """
    model_config = ConfigDict(extra="forbid")
    interfaces: dict[str, InterfaceAsset] = Field(
        default_factory=dict,
        description="Map of shared-asset key → InterfaceAsset",
    )


# ----------------------------------------------------------------------------
# Instance tree
# ----------------------------------------------------------------------------

class Instance(BaseModel):
    """One named instance in the env. `instance_name` is the local handle;
    `class_name` is the SystemVerilog class to instantiate. `role` tells the
    renderer how to treat it (active vs passive agent, vsequencer, etc.).

    `children` holds sub-instances where structure is hierarchical (e.g. an
    agent can contain its own sub-instances). Most flat env-level
    components (scoreboard, predictor) use `parent_role` instead.
    """
    model_config = ConfigDict(extra="forbid")
    instance_name: str = Field(..., description="Local handle, must be unique in the env")
    class_name: str = Field(..., description="SystemVerilog class to instantiate")
    role: InstanceRole
    vif: Optional[str] = Field(
        default=None,
        description="Shared-asset key of the vif this instance receives (if any)",
    )
    confidence: Confidence
    children: dict[str, "Instance"] = Field(
        default_factory=dict,
        description="Named sub-instances (instance_name → Instance)",
    )

    @model_validator(mode="after")
    def _vif_required_for_agents(self) -> "Instance":
        """Every agent must have a vif; everything else is optional."""
        if self.role in ("active_agent", "passive_agent") and not self.vif:
            raise ValueError(
                f"agent '{self.instance_name}' (role={self.role}) "
                f"must declare a 'vif' (shared-asset key)"
            )
        return self


class EnvInstance(BaseModel):
    """The environment. Holds all top-level env children as a flat map of
    instance_name → Instance. Flat, not hierarchical — the path assembler
    computes the hierarchy from the env's parent scope.
    """
    model_config = ConfigDict(extra="forbid")
    instance_name: str = Field(default="m_env", description="Default convention is m_env")
    class_name: str
    components: dict[str, Instance] = Field(
        default_factory=dict,
        description="Flat map of instance_name → Instance, all children of this env",
    )
    confidence: Confidence = Field(
        ...,
        description="R1: confidence that the env's class and instance_name "
                    "are faithfully extracted from the spec",
    )


class InstancesBlock(BaseModel):
    """Top-level container for all instances. Currently just envs; the
    `test` entry is reserved for future use (right now the test name is
    fixed at `uvm_test_top` by UVM convention).
    """
    model_config = ConfigDict(extra="forbid")
    envs: dict[str, EnvInstance] = Field(
        default_factory=dict,
        description="Map of env_name → EnvInstance",
    )

    @model_validator(mode="after")
    def _env_key_matches_class_name(self) -> "InstancesBlock":
        """Enforce that every env dict key equals its EnvInstance.class_name.

        This prevents a naming divergence between the deterministic extractor
        (which uses class_name as the key) and the LLM extractor (which might
        use instance_name instead). Both pass the type checker without this
        rule because dict keys are just strings.
        """
        for key, env in self.envs.items():
            if key != env.class_name:
                raise ValueError(
                    f"env key {key!r} does not match EnvInstance.class_name "
                    f"{env.class_name!r}. The dict key must equal class_name "
                    f"to keep env lookup consistent across extractors."
                )
        return self


# ----------------------------------------------------------------------------
# Config DB entries (the wire list)
# ----------------------------------------------------------------------------

class ConfigDBEntry(BaseModel):
    """One `uvm_config_db::set()` call in the generated env.

    Per T1 (and the addendum on shared keys): the entry names a target
    instance by name and points to a shared asset by `interface_ref`. The
    renderer derives the `scope` path; the entry does NOT carry one.
    """
    model_config = ConfigDict(extra="forbid")
    target_instance: str = Field(
        ...,
        description="Instance name that will uvm_config_db::get() this asset",
    )
    interface_ref: str = Field(
        ...,
        description="Shared-asset key of the interface being delivered",
    )
    field_name: str = Field(
        default="vif",
        description="Field name used in both set() and get(); default is 'vif'",
    )
    delivery: DeliveryKind = Field(
        default="set",
        description="Delivery mechanism; only 'set' supported in v1",
    )
    confidence: Confidence


# ----------------------------------------------------------------------------
# Top-level Blueprint
# ----------------------------------------------------------------------------

class Blueprint(BaseModel):
    """The whole thing. What the LLM emits, what the renderer consumes.

    The model is the contract: the prompt derives from this, the validator
    enforces this, the renderer reads this.
    """
    model_config = ConfigDict(extra="forbid")
    spec_source: str = Field(
        ...,
        description="Path or identifier of the spec this Blueprint was extracted from",
    )
    block_name: str = Field(
        ...,
        description="Prefix used for generated files and classes, e.g. 'simple_timer'. "
                    "Explicit (not derived) so the spec can name the block whatever it likes.",
    )
    shared_assets: SharedAssets
    instances: InstancesBlock
    config_db: list[ConfigDBEntry] = Field(
        default_factory=list,
        description="One entry per uvm_config_db::set() call to generate",
    )

    @model_validator(mode="after")
    def _config_db_entries_reference_real_things(self) -> "Blueprint":
        """Cross-reference resolution: every config_db entry's target_instance
        must exist somewhere in the env tree, and its interface_ref must
        exist in shared_assets.interfaces. This is the T1 addendum made
        structural.
        """
        # Collect every declared instance_name across all envs
        declared: set[str] = set()
        for env in self.instances.envs.values():
            declared.add(env.instance_name)
            for inst in env.components.values():
                declared.add(inst.instance_name)
                # Walk children too
                declared.update(inst.children.keys())

        interface_keys = set(self.shared_assets.interfaces.keys())

        for i, entry in enumerate(self.config_db):
            if entry.target_instance not in declared:
                raise ValueError(
                    f"config_db[{i}]: target_instance '{entry.target_instance}' "
                    f"is not declared anywhere in instances.envs.*.components. "
                    f"Declared: {sorted(declared)}"
                )
            if entry.interface_ref not in interface_keys:
                raise ValueError(
                    f"config_db[{i}]: interface_ref '{entry.interface_ref}' "
                    f"is not in shared_assets.interfaces. "
                    f"Declared: {sorted(interface_keys)}"
                )

        return self


# ----------------------------------------------------------------------------
# CLI: emit the JSON Schema for use in the LLM prompt
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    import json, sys
    schema = Blueprint.model_json_schema()
    if len(sys.argv) > 1 and sys.argv[1] == "--schema":
        print(json.dumps(schema, indent=2))
    else:
        print("Usage: python blueprint_schema.py --schema   # emit JSON Schema")
        print("       python blueprint_schema.py             # show summary")
        print()
        print("Blueprint has these top-level fields:")
        for name, field in Blueprint.model_fields.items():
            print(f"  - {name}: {field.annotation}")
