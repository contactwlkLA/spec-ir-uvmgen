#!/usr/bin/env python3
"""Pydantic schema for the PRD v0.0d candidate semantic model.

This is deliberately separate from ``blueprint_schema.py``.  The Blueprint
schema describes renderer inputs; this schema describes extracted behavioral
semantics and verification intent.  It contains no UVM or SystemVerilog
implementation artifact.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SemanticBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


Status = Literal["candidate", "pending_human_approval", "validated", "deferred"]
RuleKind = Literal["environment_assumption", "dut_guarantee"]
VerificationStatus = Literal["checked", "unchecked_by_design"]
ParameterKind = Literal["symbolic_parameter"]
InterfaceKind = Literal["clock_reset", "request", "response"]
SignalDirection = Literal["input", "output"]
DecisionStatus = Literal["closed", "open"]
TraceKind = Literal["legal", "illegal"]
GateStatus = Literal["satisfied_by_prd", "satisfied_by_validator", "deferred_later_stage"]


class Parameter(SemanticBase):
    name: str
    kind: ParameterKind
    symbolic: Literal[True] = True
    structural_constraint: str
    mock_default: Any | None = None
    mock_default_label: Literal["mock_default"] = "mock_default"
    meaning: str


class MockEncoding(SemanticBase):
    name: str
    value: int
    mock_default_label: Literal["mock_encoding"] = "mock_encoding"
    meaning: str


class InterfaceSignal(SemanticBase):
    name: str
    direction: SignalDirection
    width_constraint: str
    meaning: str
    producer: str


class InterfaceContract(SemanticBase):
    id: str
    kind: InterfaceKind
    purpose: str
    signals: list[InterfaceSignal] = Field(min_length=1)


class Requirement(SemanticBase):
    id: str
    kind: RuleKind
    topic: str
    statement: str
    verification_status: VerificationStatus = "checked"
    rationale: str = ""

    @model_validator(mode="after")
    def _unchecked_requires_rationale(self) -> "Requirement":
        if self.verification_status == "unchecked_by_design" and not self.rationale.strip():
            raise ValueError(f"requirement {self.id}: unchecked_by_design requires a non-empty rationale")
        return self


class SemanticDecision(SemanticBase):
    id: str
    topic: str
    status: DecisionStatus
    disposition: str


class NondeterminismRule(SemanticBase):
    id: str
    topic: str
    permitted_behavior: str
    bounded_by: list[str] = Field(min_length=1)
    requirement_ids: list[str] = Field(min_length=1)


class ObservationField(SemanticBase):
    id: str
    producer: str
    model_type: str
    meaning: str


class ObservationContract(SemanticBase):
    id: str
    event: str
    required_field_ids: list[str] = Field(min_length=1)


class OracleResultContract(SemanticBase):
    id: str
    purpose: str
    fields: list[ObservationField] = Field(min_length=1)
    publishes_for_observation_id: str
    pairing_key: str


class HoldViolationContract(SemanticBase):
    id: str
    purpose: str
    fields: list[ObservationField] = Field(min_length=1)
    publishes_for_observation_id: str


class StateObject(SemanticBase):
    id: str
    owner_component_id: str
    semantic_or_verification_only: Literal["semantic", "verification_only"]
    description: str


class ComponentOwnership(SemanticBase):
    id: str
    responsibility: str
    authoritative_state_ids: list[str] = Field(default_factory=list)
    consumes_observation_ids: list[str] = Field(default_factory=list)
    produces_contract_ids: list[str] = Field(default_factory=list)
    pairs_by: str | None = None


class Assertion(SemanticBase):
    id: str
    rule: str
    requirement_ids: list[str] = Field(default_factory=list)


class Checker(SemanticBase):
    id: str
    mechanism: str
    responsibility: str
    observation_ids: list[str] = Field(default_factory=list)
    invariant_ids: list[str] = Field(default_factory=list)
    assertion_ids: list[str] = Field(default_factory=list)


class Invariant(SemanticBase):
    id: str
    rule: str
    requirement_ids: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    checker_ids: list[str] = Field(default_factory=list)


class Mutation(SemanticBase):
    id: str
    fault: str
    expected_detection: str
    trace_ids: list[str] = Field(min_length=1)
    reserved_id_until_observed: bool = False


class Trace(SemanticBase):
    id: str
    kind: TraceKind
    scenario: str
    expected_result: str
    requirement_ids: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    invariant_ids: list[str] = Field(default_factory=list)


class TraceabilityRow(SemanticBase):
    requirement_ids: list[str] = Field(min_length=1)
    observation_ids: list[str] = Field(min_length=1)
    # checker_ids/primary_trace_ids may be empty only on rows whose
    # requirement_ids are all verification_status="unchecked_by_design"
    # (non-empty) — enforced by the model validator below.
    checker_ids: list[str] = Field(default_factory=list)
    invariant_ids: list[str] = Field(default_factory=list)
    assertion_ids: list[str] = Field(default_factory=list)
    primary_trace_ids: list[str] = Field(default_factory=list)


class GenerationGate(SemanticBase):
    id: str
    condition: str
    status: GateStatus
    requirement_ids: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    invariant_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)


class SemanticModel(SemanticBase):
    """Candidate semantic extraction for one PRD revision.

    The post-validation checks are intentionally domain-specific: references
    are not just strings, and traceability must cover every extracted rule.
    """

    schema_name: Literal["uvm_buffer_semantic_model"]
    schema_version: str
    model_revision: str
    source_document: str
    source_prd_revision: Literal["v0.0e"]
    extraction_status: Literal["candidate_pending_human_approval"]
    generation_ready: Literal[False] = False
    parameters: list[Parameter] = Field(min_length=1)
    mock_encodings: list[MockEncoding] = Field(min_length=1)
    interfaces: list[InterfaceContract] = Field(min_length=1)
    requirements: list[Requirement] = Field(min_length=1)
    semantic_decisions: list[SemanticDecision] = Field(min_length=1)
    permitted_nondeterminism: list[NondeterminismRule] = Field(min_length=1)
    observation_fields: list[ObservationField] = Field(min_length=1)
    observations: list[ObservationContract] = Field(min_length=1)
    oracle_result: OracleResultContract
    hold_violation: HoldViolationContract
    state_objects: list[StateObject] = Field(min_length=1)
    component_ownership: list[ComponentOwnership] = Field(min_length=1)
    checkers: list[Checker] = Field(min_length=1)
    assertions: list[Assertion] = Field(min_length=1)
    invariants: list[Invariant] = Field(min_length=1)
    mutations: list[Mutation] = Field(min_length=1)
    legal_traces: list[Trace] = Field(min_length=1)
    illegal_traces: list[Trace] = Field(min_length=1)
    traceability: list[TraceabilityRow] = Field(min_length=1)
    generation_gates: list[GenerationGate] = Field(min_length=1)

    @staticmethod
    def _unique(items: list[Any], label: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in items:
            item_id = item.id
            if item_id in result:
                raise ValueError(f"duplicate {label} ID: {item_id}")
            result[item_id] = item
        return result

    @staticmethod
    def _check_refs(refs: list[str], known: set[str], label: str) -> None:
        missing = sorted(set(refs) - known)
        if missing:
            raise ValueError(f"unresolved {label} reference(s): {missing}")

    @model_validator(mode="after")
    def _validate_references_and_coverage(self) -> "SemanticModel":
        req = self._unique(self.requirements, "requirement")
        decisions = self._unique(self.semantic_decisions, "decision")
        obs = self._unique(self.observations, "observation")
        fields = self._unique(self.observation_fields, "observation field")
        states = self._unique(self.state_objects, "state object")
        components = self._unique(self.component_ownership, "component")
        checkers = self._unique(self.checkers, "checker")
        assertions = self._unique(self.assertions, "assertion")
        invariants = self._unique(self.invariants, "invariant")
        legal = self._unique(self.legal_traces, "legal trace")
        illegal = self._unique(self.illegal_traces, "illegal trace")
        gates = self._unique(self.generation_gates, "generation gate")
        all_traces = legal | illegal
        all_trace_ids = set(all_traces)
        requirement_ids = set(req)
        decision_ids = set(decisions)
        observation_ids = set(obs)
        field_ids = set(fields)
        state_ids = set(states)
        component_ids = set(components)
        checker_ids = set(checkers)
        assertion_ids = set(assertions)
        invariant_ids = set(invariants)
        gate_ids = set(gates)

        expected_gates = {f"GR-{i:03d}" for i in range(1, 11)}
        if gate_ids != expected_gates:
            raise ValueError(f"generation gates must be exactly GR-001..GR-010, got {sorted(gate_ids)}")

        for interface in self.interfaces:
            signal_names = [signal.name for signal in interface.signals]
            if len(signal_names) != len(set(signal_names)):
                raise ValueError(f"duplicate signal name in interface {interface.id}")
        for observation in self.observations:
            self._check_refs(observation.required_field_ids, field_ids, f"observation {observation.id} field")
        self._check_refs(self.oracle_result.publishes_for_observation_id.split(), observation_ids, "oracle observation")
        self._check_refs([self.oracle_result.pairing_key], field_ids, "oracle pairing field")
        for result_field in self.oracle_result.fields:
            if result_field.id not in field_ids:
                raise ValueError(f"oracle result field {result_field.id!r} is not in observation_fields")
        self._check_refs([self.hold_violation.publishes_for_observation_id], observation_ids, "hold-violation observation")
        for violation_field in self.hold_violation.fields:
            if violation_field.id not in field_ids:
                raise ValueError(f"hold-violation field {violation_field.id!r} is not in observation_fields")

        for rule in self.permitted_nondeterminism:
            self._check_refs(rule.requirement_ids, requirement_ids, f"nondeterminism {rule.id} requirement")
            self._check_refs(rule.bounded_by, requirement_ids | decision_ids | invariant_ids, f"nondeterminism {rule.id} bound")
        for state in self.state_objects:
            self._check_refs([state.owner_component_id], component_ids, f"state {state.id} owner")
        for component in self.component_ownership:
            self._check_refs(component.authoritative_state_ids, state_ids, f"component {component.id} state")
            self._check_refs(component.consumes_observation_ids, observation_ids, f"component {component.id} observation")
            self._check_refs(component.produces_contract_ids, {"ORACLE-RESULT-001"}, f"component {component.id} contract")
        for checker in self.checkers:
            self._check_refs(checker.observation_ids, observation_ids, f"checker {checker.id} observation")
            self._check_refs(checker.invariant_ids, invariant_ids, f"checker {checker.id} invariant")
            self._check_refs(checker.assertion_ids, assertion_ids, f"checker {checker.id} assertion")
        for assertion in self.assertions:
            self._check_refs(assertion.requirement_ids, requirement_ids, f"assertion {assertion.id} requirement")
        for invariant in self.invariants:
            self._check_refs(invariant.requirement_ids, requirement_ids, f"invariant {invariant.id} requirement")
            self._check_refs(invariant.observation_ids, observation_ids, f"invariant {invariant.id} observation")
            self._check_refs(invariant.decision_ids, decision_ids, f"invariant {invariant.id} decision")
            self._check_refs(invariant.checker_ids, checker_ids, f"invariant {invariant.id} checker")
        for mutation in self.mutations:
            self._check_refs(mutation.trace_ids, all_trace_ids, f"mutation {mutation.id} trace")
        for trace in all_traces.values():
            self._check_refs(trace.requirement_ids, requirement_ids, f"trace {trace.id} requirement")
            self._check_refs(trace.observation_ids, observation_ids, f"trace {trace.id} observation")
            self._check_refs(trace.invariant_ids, invariant_ids, f"trace {trace.id} invariant")
        for row in self.traceability:
            self._check_refs(row.requirement_ids, requirement_ids, "traceability requirement")
            self._check_refs(row.observation_ids, observation_ids, "traceability observation")
            self._check_refs(row.checker_ids, checker_ids, "traceability checker")
            self._check_refs(row.invariant_ids, invariant_ids, "traceability invariant")
            self._check_refs(row.assertion_ids, assertion_ids, "traceability assertion")
            self._check_refs(row.primary_trace_ids, all_trace_ids, "traceability trace")
        for gate in self.generation_gates:
            self._check_refs(gate.requirement_ids, requirement_ids, f"gate {gate.id} requirement")
            self._check_refs(gate.observation_ids, observation_ids, f"gate {gate.id} observation")
            self._check_refs(gate.invariant_ids, invariant_ids, f"gate {gate.id} invariant")
            self._check_refs(gate.decision_ids, decision_ids, f"gate {gate.id} decision")

        covered = {rid for row in self.traceability for rid in row.requirement_ids}
        if covered != requirement_ids:
            raise ValueError(f"requirement traceability mismatch; missing={sorted(requirement_ids-covered)}, extra={sorted(covered-requirement_ids)}")

        # Every normative DUT rule must have an observation and at least one
        # checker/invariant/assertion route.  Environment assumptions are also
        # required to remain traceable, but are not silently promoted to DUT
        # guarantees.
        for row in self.traceability:
            if not row.observation_ids:
                raise ValueError("each traceability row needs observations")
            if not (row.checker_ids or row.invariant_ids or row.assertion_ids):
                unchecked = bool(row.requirement_ids) and all(
                    req[rid].verification_status == "unchecked_by_design"
                    for rid in row.requirement_ids
                )
                if not unchecked:
                    raise ValueError("each traceability row needs observations and a checker/invariant/assertion")
        dut_ids = {rid for rid, rule in req.items() if rule.kind == "dut_guarantee"}
        for rid in dut_ids:
            if req[rid].verification_status == "unchecked_by_design":
                continue
            rows = [row for row in self.traceability if rid in row.requirement_ids]
            if not rows or not any(row.checker_ids or row.invariant_ids or row.assertion_ids for row in rows):
                raise ValueError(f"normative DUT requirement {rid} lacks checker/invariant/assertion mapping")

        if any(decision.status != "closed" for decision in self.semantic_decisions):
            raise ValueError("all semantic-closure decisions must be closed")
        if any(gate.status == "deferred_later_stage" for gate in self.generation_gates if gate.id != "GR-010"):
            raise ValueError("only GR-010 may be deferred to the later generation-manifest stage")
        if self.generation_ready:
            raise ValueError("candidate extraction must not claim generation readiness")
        return self


if __name__ == "__main__":
    import json
    print(json.dumps(SemanticModel.model_json_schema(), indent=2))
