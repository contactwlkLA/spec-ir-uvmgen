#!/usr/bin/env python3
"""
extract_blueprint.py — deterministic spec → SemanticIR extractor.

Parses a hardware spec markdown file by section and emits a Pydantic-validated
SemanticIR JSON. No LLM. Run on a spec whose structure follows the simple_timer
template (## 1. System Signals, ## 2. <protocol>, ## 3. Dedicated Outputs,
## 4. Registers, ## 5. UVM Verification Topology).

Per the IR-split architecture (see design_ir_split.md), this extractor emits
SEMANTIC IR ONLY — facts the spec states. Implementation-derived stubs (T3
vsequencer per reqspec §2a MVP tier) are filled by the renderer from
`ImplementationContract.stubs_emitted`, not by the extractor. This eliminates
the LLM-vs-deterministic divergence on whether the vsequencer stub is present.

The renderer (render_blueprint.py) takes the SemanticIR + a Blueprint wrapper
and produces byte-identical SV either way — the stub synthesis is mechanical
and always reaches the same output.

Usage:
    python extract_blueprint.py <spec.md> [--out OUTPUT.json]

Default OUTPUT is `<spec>.extracted.json` next to the input.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

# Extraction layer — same dir.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from blueprint_schema import Blueprint  # noqa: E402


# ----------------------------------------------------------------------------
# Section helpers
# ----------------------------------------------------------------------------

SECTION_RE = re.compile(r"^##\s+(\d+)\.\s+(.+)$", re.MULTILINE)
BLOCK_NAME_RE = re.compile(r"^#\s+Block:\s+(\w+)", re.MULTILINE)
SIGNAL_RE = re.compile(
    r"^\*\s+`(\w+)`:\s+(\d+)-bit\s+(input|output|inout)\.\s+(.+)$"
)


def split_sections(text: str) -> dict[int, str]:
    """Return {section_number: section_body}. Body excludes the `## N.` header."""
    sections: dict[int, str] = {}
    matches = list(SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        num = int(m.group(1))
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[num] = text[body_start:body_end]
    return sections


def extract_signals(section_text: str) -> list[dict]:
    """Parse `* `name`: width-bit direction. description` bullets."""
    sigs: list[dict] = []
    for line in section_text.split("\n"):
        line = line.strip()
        m = SIGNAL_RE.match(line)
        if not m:
            continue
        sigs.append({
            "name": m.group(1),
            "width": int(m.group(2)),
            "direction": m.group(3),
            "confidence": "explicit",
        })
    return sigs


def strip_iface_suffix(name: str) -> str:
    """Strip common suffixes to guess the interface type stem.
    `apb_ctrl` → `apb` (then `+ _if` → `apb_if`)
    `irq_out` → `irq`
    """
    for suffix in ("_ctrl", "_out", "_in", "_io"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def guess_iface_type(name: str) -> str:
    """`apb_ctrl` → `apb_if`. The renderer strips `virtual ` prefix later."""
    return f"{strip_iface_suffix(name)}_if"


def normalize_instance_name(spec_name: str) -> str:
    """UVM convention: instance names of env children start with `m_`.
    `regmodel` → `m_regmodel`; `m_apb_agent` → `m_apb_agent` (unchanged).
    """
    return spec_name if spec_name.startswith("m_") else f"m_{spec_name}"


def target_from_scope(scope: str) -> str:
    """`uvm_test_top.m_env.*` → `m_env`. Strips `uvm_test_top.` prefix and trailing `.*`."""
    s = scope.rstrip(".*")
    parts = s.split(".")
    return parts[-1] if len(parts) > 1 else s


# ----------------------------------------------------------------------------
# Component / vif mapping
# ----------------------------------------------------------------------------

# Hardcoded map from class_name → vif key. Derived in spirit from the spec's
# Config DB Mappings section, but the regex-based extract_config_db pulls this
# directly when possible. Kept here as a fallback for specs that omit explicit
# config_db mappings.
COMPONENT_VIF_HINT = {
    "amba_apb_agent": "apb_ctrl_vif",
    "irq_monitor_agent": "irq_out_vif",
}


# ----------------------------------------------------------------------------
# Section extractors
# ----------------------------------------------------------------------------

def extract_block_name(text: str) -> str:
    m = BLOCK_NAME_RE.search(text)
    if not m:
        raise ValueError("spec has no `# Block: <name>` header")
    return m.group(1)


def extract_interfaces(sections: dict[int, str]) -> dict[str, dict]:
    """One interface per spec section. §1=clk_rst, §2=primary protocol,
    §3=dedicated output(s). Key naming: `<spec-name>_vif`.
    """
    interfaces: dict[str, dict] = {}

    # §1: System Signals → clk_rst_vif. Hardcoded by convention.
    if 1 in sections:
        sigs = extract_signals(sections[1])
        if sigs:
            interfaces["clk_rst_vif"] = {
                "key": "clk_rst_vif",
                "type": "virtual clk_rst_if",
                "confidence": "explicit",
                "signals": sigs,
            }

    # §2: primary protocol interface. Spec says "interface named `<name>`".
    if 2 in sections:
        m = re.search(r"interface named `(\w+)`", sections[2])
        if m:
            iface_name = m.group(1)  # e.g. "apb_ctrl"
            sigs = extract_signals(sections[2])
            interfaces[f"{iface_name}_vif"] = {
                "key": f"{iface_name}_vif",
                "type": f"virtual {guess_iface_type(iface_name)}",
                "confidence": "explicit",
                "signals": sigs,
            }

    # §3: dedicated outputs. One signal per bullet → one interface per bullet.
    if 3 in sections:
        sigs = extract_signals(sections[3])
        for sig in sigs:
            key = f"{sig['name']}_vif"
            interfaces[key] = {
                "key": key,
                "type": f"virtual {guess_iface_type(sig['name'])}",
                "confidence": "explicit",
                "signals": [sig],
            }

    return interfaces


def extract_env(sections: dict[int, str], block_name: str) -> dict:
    """Parse §5 for env class, instance name, and component list."""
    section = sections.get(5)
    if not section:
        raise ValueError("spec has no §5 — cannot determine env topology")

    # Env class: "Named `simple_timer_env`."
    env_class_m = re.search(r"Named `(\w+_env)`", section)
    if not env_class_m:
        raise ValueError("§5: cannot find env class declaration (e.g. 'Named `simple_timer_env`')")
    env_class = env_class_m.group(1)

    # Env instance: "instantiate `simple_timer_env` as `m_env`"
    env_inst_m = re.search(r"as `(\w+)`", section)
    env_inst = env_inst_m.group(1) if env_inst_m else "m_env"

    components = extract_components(section, block_name)

    return {
        "instance_name": env_inst,
        "class_name": env_class,
        "confidence": "explicit",
        "components": components,
    }


def extract_components(section_text: str, block_name: str) -> dict[str, dict]:
    """Each component line: '<Role> named `inst` of type `Class>`.

    Per the IR-split architecture, this emits ONLY spec-stated components.
    Implementation-derived stubs (T3 vsequencer) are NOT added here — they're
    filled by the renderer from ImplementationContract.stubs_emitted.
    """
    component_patterns = [
        (r"An active agent named `(\w+)` of type `(\w+)`\.", "active_agent"),
        (r"A passive agent named `(\w+)` of type `(\w+)`\.", "passive_agent"),
        (r"A Register Block named `(\w+)` of type `(\w+)`\.", "regmodel"),
        (r"A Register Adapter named `(\w+)` of type `(\w+)`\.", "reg_adapter"),
        (r"A Register Predictor named `(\w+)` of type `(\w+)`\.", "reg_predictor"),
        (r"A Scoreboard named `(\w+)` of type `(\w+)`\.", "scoreboard"),
    ]

    components: dict[str, dict] = {}
    for line in section_text.split("\n"):
        line = line.strip()
        for pat, role in component_patterns:
            m = re.search(pat, line)
            if not m:
                continue
            spec_name = m.group(1)
            class_name = m.group(2)
            inst_name = normalize_instance_name(spec_name)
            vif = COMPONENT_VIF_HINT.get(class_name)
            components[inst_name] = {
                "instance_name": inst_name,
                "class_name": class_name,
                "role": role,
                "vif": vif,
                "confidence": "explicit",
                "children": {},
            }
            break

    return components


def extract_config_db(section_text: str) -> list[dict]:
    """Parse `Map `<if_ref>` (type `<type>`) to scope `<scope>` under the field name `<field>`."""
    config_db: list[dict] = []
    pat = (
        r"Map `(\w+)` \(type `([^`]+)`\) to scope `([^`]+)` "
        r"under the field name `(\w+)`"
    )
    for line in section_text.split("\n"):
        line = line.strip()
        if not line.startswith("- Map"):
            continue
        m = re.search(pat, line)
        if not m:
            continue
        config_db.append({
            "target_instance": target_from_scope(m.group(3)),
            "interface_ref": m.group(1),
            "field_name": m.group(4),
            "delivery": "set",
            "confidence": "explicit",
        })
    return config_db


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def extract(spec_path: Path) -> dict:
    """Parse the spec, build a Blueprint dict, validate via Pydantic, return dict."""
    text = spec_path.read_text()
    sections = split_sections(text)
    if not sections:
        raise ValueError(f"no `## N.` sections found in {spec_path}")

    block_name = extract_block_name(text)
    interfaces = extract_interfaces(sections)
    env = extract_env(sections, block_name)
    config_db = extract_config_db(sections.get(5, ""))

    blueprint_dict = {
        "spec_source": spec_path.name,  # filename only, matching the hand-crafted Blueprint convention
        "block_name": block_name,
        "shared_assets": {"interfaces": interfaces},
        "instances": {"envs": {env["class_name"]: env}},
        "config_db": config_db,
    }

    # Validate via Pydantic — R1 strict enforcement happens here.
    # If anything's wrong, raises ValidationError with field path.
    bp = Blueprint.model_validate(blueprint_dict)
    return bp.model_dump()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("spec", help="Path to hardware spec markdown file")
    ap.add_argument("--out", help="Output Blueprint JSON (default: <spec>.extracted.json)")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"Error: spec not found at {spec_path}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else spec_path.with_suffix(".extracted.json")

    print(f"[*] Parsing spec: {spec_path}")
    try:
        blueprint_dict = extract(spec_path)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    # Write JSON (use model_dump_json via Pydantic for canonical ordering).
    import json
    out_path.write_text(json.dumps(blueprint_dict, indent=2))
    print(f"[*] Wrote {out_path}")
    print(f"    {len(blueprint_dict['shared_assets']['interfaces'])} interfaces, "
          f"{sum(len(e['components']) for e in blueprint_dict['instances']['envs'].values())} components, "
          f"{len(blueprint_dict['config_db'])} config_db entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
