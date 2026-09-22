#!/usr/bin/env python3
"""Build and validate the candidate semantic extraction for PRD v0.0d.

The tables below are a mechanical, reviewable extraction of the PRD.  This
stage emits only semantic JSON; it does not emit a behavior model or SV.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from semantic_schema import SemanticModel


def req(id, kind, topic, statement, verification_status=None, rationale=None):
    d = {"id": id, "kind": kind, "topic": topic, "statement": statement}
    if verification_status is not None:
        d["verification_status"] = verification_status
    if rationale is not None:
        d["rationale"] = rationale
    return d

def obs_field(id, producer, model_type, meaning):
    return {"id": id, "producer": producer, "model_type": model_type, "meaning": meaning}

def observation(id, event, fields):
    return {"id": id, "event": event, "required_field_ids": fields}

def checker(id, mechanism, responsibility, observations=(), invariants=(), assertions=()):
    return {"id": id, "mechanism": mechanism, "responsibility": responsibility,
            "observation_ids": list(observations), "invariant_ids": list(invariants),
            "assertion_ids": list(assertions)}

def inv(id, rule, requirements=(), observations=(), decisions=(), checkers=()):
    return {"id": id, "rule": rule, "requirement_ids": list(requirements),
            "observation_ids": list(observations), "decision_ids": list(decisions),
            "checker_ids": list(checkers)}

def trace(id, kind, scenario, expected, requirements=(), observations=(), invariants=()):
    return {"id": id, "kind": kind, "scenario": scenario, "expected_result": expected,
            "requirement_ids": list(requirements), "observation_ids": list(observations),
            "invariant_ids": list(invariants)}


def build() -> dict:
    parameters = [
        ("MAX_CAPACITY", "Fixed prototype requirement", 16, "Maximum outstanding transactions"),
        ("ID_W", "2**ID_W >= MAX_CAPACITY", 8, "Transaction-ID namespace width"),
        ("ADDR_W", "ADDR_W >= 1", 8, "Address width"),
        ("DATA_W", "DATA_W >= 1", 32, "Read/write payload width"),
        ("OP_W", "Must encode READ and WRITE", 1, "Operation width"),
        ("STATUS_W", "Must encode OK", 1, "Response-status width"),
        ("DELAY_W", "Must encode MAX_COMPLETION_DELAY", 4, "Eligibility-delay width"),
        ("MIN_COMPLETION_DELAY", ">= 1", 1, "Minimum legal request delay"),
        ("MAX_COMPLETION_DELAY", ">= MIN_COMPLETION_DELAY", 8, "Maximum legal request delay"),
        ("WATCHDOG_CYCLES", "Fixed at 256 for v0.0d", 256, "Response-service-enabled liveness bound"),
    ]
    data = {
        "schema_name": "uvm_buffer_semantic_model", "schema_version": "1.0",
        "model_revision": "candidate-v0.0e-001", "source_document": "uvm_buffer_prd.md",
        "source_prd_revision": "v0.0e",
        "extraction_status": "candidate_pending_human_approval", "generation_ready": False,
        "parameters": [{"name": n, "kind": "symbolic_parameter", "symbolic": True,
                        "structural_constraint": c, "mock_default": d,
                        "mock_default_label": "mock_default", "meaning": m}
                       for n, c, d, m in parameters],
        "mock_encodings": [
            {"name": "READ", "value": 0, "mock_default_label": "mock_encoding", "meaning": "Mock operation encoding"},
            {"name": "WRITE", "value": 1, "mock_default_label": "mock_encoding", "meaning": "Mock operation encoding"},
            {"name": "OK", "value": 0, "mock_default_label": "mock_encoding", "meaning": "Mock legal response-status encoding"},
        ],
        "interfaces": [
            {"id": "IF-CLK-RST", "kind": "clock_reset", "purpose": "Single rising-edge clock and active-high synchronous reset", "signals": [
                {"name": "clk", "direction": "input", "width_constraint": "1", "meaning": "All acceptance, completion, and reset changes occur on posedge", "producer": "environment"},
                {"name": "rst", "direction": "input", "width_constraint": "1", "meaning": "Synchronous reset with priority over handshakes", "producer": "environment"}]},
            {"id": "IF-REQ", "kind": "request", "purpose": "Two independent request sources with active-high hold backpressure", "signals": [
                {"name": "req_valid[p]", "direction": "input", "width_constraint": "1 for p in {0,1}", "meaning": "Request present", "producer": "request source"},
                {"name": "req_hold[p]", "direction": "output", "width_constraint": "1 for p in {0,1}", "meaning": "DUT prevents acceptance while high", "producer": "DUT"},
                {"name": "req_id[p]", "direction": "input", "width_constraint": "ID_W", "meaning": "Transaction identity", "producer": "request source"},
                {"name": "req_addr[p]", "direction": "input", "width_constraint": "ADDR_W", "meaning": "Transaction address", "producer": "request source"},
                {"name": "req_op[p]", "direction": "input", "width_constraint": "OP_W", "meaning": "READ or WRITE", "producer": "request source"},
                {"name": "req_wdata[p]", "direction": "input", "width_constraint": "DATA_W", "meaning": "Write payload; ignored for reads", "producer": "request source"},
                {"name": "req_delay[p]", "direction": "input", "width_constraint": "DELAY_W", "meaning": "Edges after acceptance before eligibility", "producer": "request source"}]},
            {"id": "IF-RSP", "kind": "response", "purpose": "One-response-at-a-time valid/ready completion channel", "signals": [
                {"name": "rsp_valid", "direction": "output", "width_constraint": "1", "meaning": "Response present", "producer": "DUT"},
                {"name": "rsp_ready", "direction": "input", "width_constraint": "1", "meaning": "Environment accepts response", "producer": "environment"},
                {"name": "rsp_id", "direction": "output", "width_constraint": "ID_W", "meaning": "Completed request identity", "producer": "DUT"},
                {"name": "rsp_rdata", "direction": "output", "width_constraint": "DATA_W", "meaning": "Read payload; ignored for writes", "producer": "DUT"},
                {"name": "rsp_status", "direction": "output", "width_constraint": "STATUS_W", "meaning": "OK for legal completion", "producer": "DUT"}]},
        ],
        "requirements": requirements(),
        "semantic_decisions": [
            {"id": "OD-001", "topic": "Completion watchdog", "status": "closed", "disposition": "256 response-service-enabled cycles"},
            {"id": "OD-002", "topic": "Same-edge capacity", "status": "closed", "disposition": "Pre-edge occupancy controls hold; completion does not free a same-edge slot"},
            {"id": "OD-003", "topic": "Duplicate request ID", "status": "closed", "disposition": "Environment obligation; accepted violation is reported and subsequent DUT behavior is unspecified"},
            {"id": "OD-004", "topic": "Reset", "status": "closed", "disposition": "One clock; active-high synchronous reset dominates handshakes and clears behavioral state; flushed-ID history may persist for classification"},
            {"id": "OD-005", "topic": "Stale-response observability", "status": "closed", "disposition": "A stale-response mutation reserves its flushed ID until the injected response is observed"},
            {"id": "OD-006", "topic": "Completion delay", "status": "closed", "disposition": "Per-request eligibility delay is symbolic and bounded; mock defaults are 1 through 8"},
            {"id": "OD-007", "topic": "Response status", "status": "closed", "disposition": "Legal responses use OK; mock encoding is zero and no DUT error response is modeled"},
            {"id": "OD-008", "topic": "Oracle/scoreboard ownership", "status": "closed", "disposition": "Oracle solely owns semantic state and expected results; scoreboard pairs actual and expected records by observation_seq and reports comparisons"},
        ],
        "permitted_nondeterminism": [
{"id": "ND-002", "topic": "Completion selection and timing", "permitted_behavior": "Any eligible transaction may be selected and completion order/timing remain flexible", "bounded_by": ["DUT-LC-009", "DUT-LC-014", "DUT-LC-015", "DUT-LIVE-002"], "requirement_ids": ["DUT-LC-015"]},
        ],
        "observation_fields": observation_fields(),
        "observations": observations(),
        "oracle_result": {"id": "ORACLE-RESULT-001", "purpose": "One expected-result record for every completed-response observation, including lifecycle-invalid responses", "fields": [f for f in observation_fields() if f["id"] in {"status", "reset_state", "reset_epoch", "service_counter", "outstanding_count", "violation_channel", "violated_rule", "id_valid", "matched_request", "compare_read_data", "expected_read_data", "expected_status"}] + [
            {"id": "matched_request", "producer": "oracle", "model_type": "OBS-001 record", "meaning": "Accepted request when available"},
            {"id": "compare_read_data", "producer": "oracle", "model_type": "bit", "meaning": "Enables read-data comparison"},
            {"id": "expected_read_data", "producer": "oracle", "model_type": "bit [DATA_W-1:0]", "meaning": "Expected completed-read payload"},
            {"id": "expected_status", "producer": "oracle", "model_type": "bit [STATUS_W-1:0]", "meaning": "Expected response status"}],
            "publishes_for_observation_id": "OBS-002", "pairing_key": "observation_seq"},
        "hold_violation": {"id": "HOLD-VIOLATION-001", "purpose": "One hold-violation record for every INV-016 failure: hold state inconsistent with pre-edge occupancy, or acceptance while hold is low", "fields": [f for f in observation_fields() if f["id"] in {"cycle", "source", "req_hold", "pre_edge_occupancy", "violated_rule"}], "publishes_for_observation_id": "OBS-006"},
        "state_objects": state_objects(), "component_ownership": components(),
        "checkers": checkers(), "assertions": assertions(), "invariants": invariants(), "mutations": mutations(),
        "legal_traces": legal_traces(), "illegal_traces": illegal_traces(),
        "traceability": traceability(), "generation_gates": gates(),
    }
    return data


def requirements():
    r = [
        req("ENV-001", "environment_assumption", "request stability", "Source holds request fields stable while req_valid[p] && req_hold[p]."),
        req("ENV-002", "environment_assumption", "delay range", "Stimulus uses req_delay from MIN_COMPLETION_DELAY through MAX_COMPLETION_DELAY inclusive."),
        req("ENV-003", "environment_assumption", "ID uniqueness", "Stimulus does not present an already-outstanding ID or the same new ID on both sources; accepted violation is reported and DUT behavior is unspecified."),
        req("ENV-004", "environment_assumption", "read precondition", "Stimulus does not issue a read without an earlier completed write in the current reset epoch."),
        req("ENV-005", "environment_assumption", "depth-blind stimulus", "Stimulus obeys req_hold[p] only; it must not track, model, or condition on occupancy.", verification_status="unchecked_by_design", rationale="No interface-observable signal distinguishes compliant from non-compliant stimulus."),
        req("DUT-PROTO-001", "dut_guarantee", "response stability", "While rsp_valid && !rsp_ready, response valid and payload fields remain stable until completion or reset."),
        req("DUT-PROTO-002", "dut_guarantee", "response status", "Every legal completed transaction has status OK; other encodings are reserved and illegal."),
        req("DUT-PROTO-003", "dut_guarantee", "reset priority", "Reset overrides request acceptance and response completion."),
        req("DUT-PROTO-004", "dut_guarantee", "hold guarantee", "When req_hold[p] is low at a rising clock edge and req_valid[p] is high, the request on source p is accepted at that edge, unconditionally and independent of the state of the other source."),
    ]
    lc = [
        ("DUT-LC-001", "Request acceptance", "Accept on a rising edge when req_valid[p] && !req_hold[p]."), ("DUT-LC-002", "Response completion", "Complete on a rising edge when rsp_valid && rsp_ready."), ("DUT-LC-003", "Identity scope", "req_id is globally unique while outstanding; duplicate avoidance is an environment obligation."), ("DUT-LC-004", "ID reuse", "Reuse an ID only after prior completion or reset flush."), ("DUT-LC-005", "Capacity", "Maximum outstanding is 16 and occupancy_next = occupancy + accepted - completed."), ("DUT-LC-006", "Backpressure", "Do not accept when acceptance would exceed capacity."), ("DUT-LC-007", "Simultaneous acceptance", "Accept both sources when both valid and at least two slots are free."), ("DUT-LC-009", "Completion order", "Transactions may complete out of acceptance order."), ("DUT-LC-010", "Response rate", "Single response channel completes at most one per cycle; consecutive completions are permitted."), ("DUT-LC-011", "Pre-edge capacity", "Hold uses beginning-of-edge occupancy; same-edge completion does not free a slot."), ("DUT-LC-012", "Full backpressure", "When pre-edge occupancy is 15 or more, req_hold[1:0] == 2'b11, including an edge on which a response completes. Depth remains 16; occupancy 16 is a transient cushion slot reachable only in the hold/accept race."), ("DUT-LC-013", "Single acceptance", "With a free slot and exactly one valid source, accept it."), ("DUT-LC-014", "Eligibility", "Accepted edge C with delay D may complete no earlier than C+D, within symbolic bounds."), ("DUT-LC-015", "Completion selection", "When multiple transactions are eligible and no response is held, any eligible transaction may be selected."),
    ]
    r += [req(i, "dut_guarantee", t, s) for i, t, s in lc]
    r += [req("DUT-DATA-001", "dut_guarantee", "Write visibility", "Write updates associative memory when the write completes."), req("DUT-DATA-002", "dut_guarantee", "Read value", "Read returns latest completed write data at read completion."), req("DUT-DATA-003", "dut_guarantee", "Same-address ordering", "Visibility follows completion order, not acceptance order."), req("DUT-DATA-004", "dut_guarantee", "Unwritten reads", "Prototype stimulus excludes reads without an earlier completed write in the current epoch.")]
    r += [req("DUT-RST-001", "dut_guarantee", "Outstanding reset", "First reset edge flushes outstanding, clears occupancy, cancels eligibility/watchdog, and advances epoch once."), req("DUT-RST-002", "dut_guarantee", "Stale responses", "Pre-reset response is not presented or accepted after reset release."), req("DUT-RST-003", "dut_guarantee", "ID reuse after reset", "Flushed IDs may be reused on first operational edge after release."), req("DUT-RST-004", "dut_guarantee", "Reset sampling", "Synchronous reset is sampled on posedge; reset-only transition and one epoch advance on assertion."), req("DUT-RST-005", "dut_guarantee", "Memory reset", "Reset clears DUT associative memory and oracle golden memory."), req("DUT-RST-006", "dut_guarantee", "Reset channel", "No handshake on sampled reset edge; while held, holds are high and rsp_valid is low."), req("DUT-RST-007", "dut_guarantee", "Reset release", "Operation resumes on first rising edge with rst low.")]
    r += [req("DUT-LIVE-001", "dut_guarantee", "Progress", "Every accepted transaction completes while reset is inactive and response service remains enabled."), req("DUT-LIVE-002", "dut_guarantee", "Bound", "Complete within 256 response-service-enabled cycles; reset or rsp_ready low does not advance watchdog.")]
    return r


def observation_fields():
    return [
        obs_field("cycle", "monitor or test", "longint unsigned", "Rising-edge count in simulation"), obs_field("observation_seq", "response monitor", "longint unsigned", "Unique monotonic key for each completed response"), obs_field("source", "request monitor", "bit", "Request source 0 or 1"), obs_field("id", "sampled interface", "bit [ID_W-1:0]", "Transaction ID"), obs_field("addr", "sampled interface", "bit [ADDR_W-1:0]", "Transaction address"), obs_field("operation", "sampled interface", "bit [OP_W-1:0]", "READ or WRITE"), obs_field("write_data", "sampled interface", "bit [DATA_W-1:0]", "Accepted write payload"), obs_field("requested_delay", "sampled interface", "bit [DELAY_W-1:0]", "Accepted eligibility delay"), obs_field("read_data", "sampled interface", "bit [DATA_W-1:0]", "Completed read payload"), obs_field("status", "sampled interface", "bit [STATUS_W-1:0]", "Completed response status"), obs_field("reset_state", "reset monitor", "bit", "Sampled reset state"), obs_field("reset_epoch", "oracle", "int unsigned", "Epoch advanced per reset assertion"), obs_field("service_counter", "oracle", "longint unsigned", "Response-service-enabled cycle count"), obs_field("outstanding_count", "oracle", "int unsigned [0:MAX_CAPACITY]", "Current outstanding count"), obs_field("violation_channel", "protocol checker", "enum REQ0/REQ1/RSP/RESET/TEST", "Violation domain"), obs_field("violated_rule", "protocol checker", "string", "Stable requirement or invariant ID"), obs_field("id_valid", "protocol checker", "bit", "Whether violation has relevant ID"), obs_field("matched_request", "oracle", "OBS-001 record", "Accepted request when available"), obs_field("compare_read_data", "oracle", "bit", "Enables read-data comparison"), obs_field("expected_read_data", "oracle", "bit [DATA_W-1:0]", "Expected completed-read payload"), obs_field("expected_status", "oracle", "bit [STATUS_W-1:0]", "Expected response status"), obs_field("req_hold", "request monitor", "bit [1:0]", "Sampled req_hold per source at the rising edge"), obs_field("req_valid", "request monitor", "bit [1:0]", "Sampled req_valid per source at the rising edge"), obs_field("pre_edge_occupancy", "oracle", "int unsigned [0:MAX_CAPACITY]", "Beginning-of-edge outstanding count for the sampled edge")]


def observations():
    f = observation_fields()
    names = {x["id"] for x in f}
    return [observation("OBS-001", "Request accepted", ["cycle", "source", "id", "addr", "operation", "write_data", "requested_delay"]), observation("OBS-002", "Response completed", ["observation_seq", "cycle", "id", "read_data", "status"]), observation("OBS-003", "Reset transition", ["cycle", "reset_state"]), observation("OBS-004", "Test termination request", ["cycle", "outstanding_count", "reset_epoch"]), observation("OBS-005", "Protocol violation", ["cycle", "violation_channel", "violated_rule", "id_valid", "id"]), observation("OBS-006", "Edge sample: per-source req_hold and req_valid sampled at each rising edge; beginning-of-edge occupancy is the oracle's own book and is never an observed input", ["cycle", "req_hold", "req_valid"])]


def state_objects():
    descriptions = [("STATE-OUTSTANDING", "Outstanding request associative table"), ("STATE-OCCUPANCY", "Occupancy"), ("STATE-EPOCH", "Reset epoch"), ("STATE-SERVICE", "Response-service counter"), ("STATE-WATCHDOG", "Per-request watchdog state"), ("STATE-GOLDEN-MEM", "Golden associative memory"), ("STATE-ID-HISTORY", "Verification-only completed and flushed ID history")]
    return [{"id": i, "owner_component_id": "COMP-ORACLE", "semantic_or_verification_only": "verification_only" if i == "STATE-ID-HISTORY" else "semantic", "description": d} for i, d in descriptions]


def components():
    return [{"id": "COMP-ORACLE", "responsibility": "Sole owner of lifecycle semantic state, verification-only ID history, expected-result production, and timekeeping from read-only clk/rst/rsp_ready", "authoritative_state_ids": ["STATE-OUTSTANDING", "STATE-OCCUPANCY", "STATE-EPOCH", "STATE-SERVICE", "STATE-WATCHDOG", "STATE-GOLDEN-MEM", "STATE-ID-HISTORY"], "consumes_observation_ids": ["OBS-001", "OBS-002", "OBS-003"], "produces_contract_ids": ["ORACLE-RESULT-001"], "pairs_by": None}, {"id": "COMP-SCOREBOARD", "responsibility": "Buffer and pair actual response and oracle result by observation_seq; compare and report without duplicate semantic state", "authoritative_state_ids": [], "consumes_observation_ids": ["OBS-002"], "produces_contract_ids": [], "pairs_by": "observation_seq"}, {"id": "COMP-REQ-MONITORS", "responsibility": "Publish request accepted observations and protocol facts for both sources", "authoritative_state_ids": [], "consumes_observation_ids": [], "produces_contract_ids": [], "pairs_by": None}, {"id": "COMP-RSP-MONITOR", "responsibility": "Publish response completion observations with monotonically increasing observation_seq", "authoritative_state_ids": [], "consumes_observation_ids": [], "produces_contract_ids": [], "pairs_by": "observation_seq"}, {"id": "COMP-RESET-MONITOR", "responsibility": "Publish raw reset transitions and own no epoch or lifecycle state", "authoritative_state_ids": [], "consumes_observation_ids": [], "produces_contract_ids": [], "pairs_by": None}, {"id": "COMP-TEST", "responsibility": "Own objections, stimulus, drain policy, and zero-outstanding termination guard", "authoritative_state_ids": [], "consumes_observation_ids": ["OBS-004"], "produces_contract_ids": [], "pairs_by": None}]


def assertions():
    return [{"id": "AST-REQ-HOLD", "rule": "Request fields are stable while req_valid && req_hold", "requirement_ids": ["ENV-001"]}, {"id": "AST-RSP-STALL", "rule": "Response fields are stable while rsp_valid && !rsp_ready", "requirement_ids": ["DUT-PROTO-001"]}, {"id": "AST-CAPACITY", "rule": "Occupancy and acceptance obey capacity and pre-edge rules", "requirement_ids": ["DUT-LC-005", "DUT-LC-006", "DUT-LC-011"]}, {"id": "AST-WATCHDOG", "rule": "No transaction exceeds the response-service-enabled bound", "requirement_ids": ["DUT-LIVE-002"]}]


def checkers():
    return [checker("CHK-PROTOCOL", "monitor and assertions", "Request hold and response stall stability plus reset handshake rules", ["OBS-001", "OBS-002", "OBS-003", "OBS-005"], ["INV-010", "INV-011", "INV-014"], ["AST-REQ-HOLD", "AST-RSP-STALL"]), checker("CHK-LIFECYCLE", "associative oracle", "Accepted and completed lifecycle matching", ["OBS-001", "OBS-002"], ["INV-001", "INV-002", "INV-003", "INV-006"]), checker("CHK-CAPACITY", "oracle invariant and assertion", "Capacity, occupancy, and hold accounting", ["OBS-001", "OBS-002", "OBS-006"], ["INV-004", "INV-009", "INV-016"], ["AST-CAPACITY"]), checker("CHK-DATA", "lifecycle oracle", "Expected identity, data, status, and completion-order visibility", ["OBS-001", "OBS-002"], ["INV-008", "INV-012"], []), checker("CHK-LIVENESS", "watchdog and assertion", "Bounded completion and termination", ["OBS-001", "OBS-002", "OBS-003", "OBS-004"], ["INV-007", "INV-013", "INV-015"], ["AST-WATCHDOG"])]


def invariants():
    return [inv("INV-001", "Every accepted transaction creates exactly one outstanding entry", ["DUT-LC-001"], ["OBS-001"], [], ["CHK-LIFECYCLE"]), inv("INV-002", "Every completed response matches one outstanding transaction", ["DUT-LC-002"], ["OBS-002"], [], ["CHK-LIFECYCLE"]), inv("INV-003", "Duplicate and unknown completions fail", ["DUT-LC-003"], ["OBS-002", "OBS-005"], ["OD-003"], ["CHK-LIFECYCLE"]), inv("INV-004", "Occupancy remains between zero and 16", ["DUT-LC-005", "DUT-LC-006"], ["OBS-001", "OBS-002"], [], ["CHK-CAPACITY"]), inv("INV-005", "Reset removes all outstanding entries and advances epoch", ["DUT-RST-001", "DUT-RST-004"], ["OBS-003"], ["OD-004"], ["CHK-LIFECYCLE"]), inv("INV-006", "A stale pre-reset response fails after reset deassertion", ["DUT-RST-002"], ["OBS-002", "OBS-003"], ["OD-005"], ["CHK-LIFECYCLE"]), inv("INV-007", "Normal termination requires zero outstanding", [], ["OBS-004"], [], ["CHK-LIVENESS"]), inv("INV-008", "Read response data follows data requirements", ["DUT-DATA-001", "DUT-DATA-002", "DUT-DATA-003", "DUT-DATA-004"], ["OBS-001", "OBS-002"], [], ["CHK-DATA"]), inv("INV-009", "Occupancy equals outstanding table size after every edge", ["DUT-LC-005", "DUT-LC-011"], ["OBS-001", "OBS-002"], ["OD-002"], ["CHK-CAPACITY"]), inv("INV-010", "Request fields remain stable while valid and held", ["ENV-001"], ["OBS-001", "OBS-005"], [], ["CHK-PROTOCOL"]), inv("INV-011", "Response fields remain stable while valid and not ready", ["DUT-PROTO-001"], ["OBS-002", "OBS-005"], [], ["CHK-PROTOCOL"]), inv("INV-012", "Every legal completed response has OK status", ["DUT-PROTO-002"], ["OBS-002"], ["OD-007"], ["CHK-DATA"]), inv("INV-013", "No outstanding transaction exceeds 256 service-enabled cycles", ["DUT-LIVE-001", "DUT-LIVE-002"], ["OBS-001", "OBS-002", "OBS-003"], ["OD-001"], ["CHK-LIVENESS"]), inv("INV-014", "No request or response handshake occurs while reset asserted", ["DUT-PROTO-003", "DUT-RST-006"], ["OBS-003", "OBS-005"], ["OD-004"], ["CHK-PROTOCOL"]), inv("INV-015", "Every response observation yields exactly one oracle result and one paired comparison", [], ["OBS-002"], ["OD-008"], ["CHK-LIVENESS"]), inv("INV-016", "Hold reflects pre-edge occupancy against the 15 threshold; hold-low implies acceptance", ["DUT-PROTO-004"], ["OBS-006"], [], ["CHK-CAPACITY"])]


def mutations():
    return [{"id": "MUT-001", "fault": "duplicate completion", "expected_detection": "Lifecycle oracle reports duplicate completion", "trace_ids": ["IT-002"], "reserved_id_until_observed": True}, {"id": "MUT-002", "fault": "unknown completion", "expected_detection": "Lifecycle oracle reports unknown ID", "trace_ids": ["IT-001"], "reserved_id_until_observed": False}, {"id": "MUT-003", "fault": "corrupted response data", "expected_detection": "Scoreboard reports payload mismatch", "trace_ids": ["IT-005"], "reserved_id_until_observed": False}, {"id": "MUT-004", "fault": "stale response after reset", "expected_detection": "Oracle reports stale response", "trace_ids": ["IT-006"], "reserved_id_until_observed": True}, {"id": "MUT-005", "fault": "response payload changed while stalled", "expected_detection": "Protocol checker reports stall instability", "trace_ids": ["IT-010"], "reserved_id_until_observed": False}, {"id": "MUT-006", "fault": "watchdog expiration", "expected_detection": "Watchdog reports liveness failure", "trace_ids": ["IT-008"], "reserved_id_until_observed": False}]


def legal_traces():
    return [trace("LT-001", "legal", "Two accepted requests complete in reverse order", "Pass", ["DUT-LC-001", "DUT-LC-002", "DUT-LC-009"], ["OBS-001", "OBS-002"], ["INV-001", "INV-002"]), trace("LT-002", "legal", "Both sources accept in one cycle while req_hold is low on both", "Pass", ["DUT-LC-007"], ["OBS-001"], ["INV-004"]), trace("LT-004", "legal", "ID reuse after completion", "Pass", ["DUT-LC-004"], ["OBS-001", "OBS-002"], ["INV-001"]), trace("LT-005", "legal", "Synchronous reset with outstanding transactions", "Outstanding and memory state flush; IDs reusable after release", ["DUT-RST-001", "DUT-RST-003"], ["OBS-001", "OBS-002", "OBS-003"], ["INV-005", "INV-006"]), trace("LT-006", "legal", "Minimum and maximum delays become eligible independently and complete out of order", "Pass", ["DUT-LC-009", "DUT-LC-014", "DUT-LC-015"], ["OBS-001", "OBS-002"], ["INV-013"]), trace("LT-007", "legal", "Completed write followed by same-address read", "Read returns completed write data", ["DUT-DATA-001", "DUT-DATA-002"], ["OBS-001", "OBS-002"], ["INV-008"]), trace("LT-008", "legal", "Same-address completion differs from acceptance order", "Visibility follows completion order", ["DUT-DATA-003"], ["OBS-001", "OBS-002"], ["INV-008"]), trace("LT-009", "legal", "Transaction completes by 256th service-enabled cycle", "Pass", ["DUT-LIVE-001", "DUT-LIVE-002"], ["OBS-001", "OBS-002"], ["INV-013"]), trace("LT-010", "legal", "Request stable over held cycles", "Pass", ["ENV-001"], ["OBS-001"], ["INV-010"]), trace("LT-011", "legal", "Response stable while ready is low then completes", "Pass", ["DUT-PROTO-001", "DUT-LC-002"], ["OBS-002"], ["INV-011"]), trace("LT-012", "legal", "Full occupancy and same-edge response", "Response completes; request stays held; next occupancy 15", ["DUT-LC-011", "DUT-LC-012", "DUT-PROTO-004"], ["OBS-001", "OBS-002"], ["INV-004", "INV-009"]), trace("LT-013", "legal", "Exactly one source valid while req_hold[p] is low", "Valid request accepted", ["DUT-LC-013"], ["OBS-001"], ["INV-001"]), trace("LT-014", "legal", "Responses complete on consecutive edges", "Pass", ["DUT-LC-010"], ["OBS-002"], ["INV-002"])]


def illegal_traces():
    return [trace("IT-001", "illegal", "Completion for unknown ID", "Fail", ["DUT-LC-002"], ["OBS-002", "OBS-005"], ["INV-002", "INV-003"]), trace("IT-002", "illegal", "Duplicate completion", "Fail", ["DUT-LC-002", "DUT-LC-003"], ["OBS-002", "OBS-005"], ["INV-002", "INV-003"]), trace("IT-003", "illegal", "Acceptance beyond capacity", "Fail", ["DUT-LC-005", "DUT-LC-006"], ["OBS-001"], ["INV-004"]), trace("IT-004", "illegal", "ID reuse while outstanding", "Fail", ["DUT-LC-003", "DUT-LC-004"], ["OBS-001", "OBS-005"], ["INV-003"]), trace("IT-005", "illegal", "Response payload mismatch", "Fail", ["DUT-DATA-002"], ["OBS-002"], ["INV-008"]), trace("IT-006", "illegal", "Pre-reset response after reset deassertion", "Fail", ["DUT-RST-002"], ["OBS-002", "OBS-003"], ["INV-006"]), trace("IT-007", "illegal", "Termination with outstanding transactions", "Fail", [], ["OBS-004"], ["INV-007"]), trace("IT-008", "illegal", "Outstanding transaction exceeds 256 service-enabled cycles", "Fail", ["DUT-LIVE-002"], ["OBS-001", "OBS-002"], ["INV-013"]), trace("IT-009", "illegal", "Request fields change while held", "Illegal stimulus failure", ["ENV-001"], ["OBS-001", "OBS-005"], ["INV-010"]), trace("IT-010", "illegal", "Response fields change while stalled", "Fail", ["DUT-PROTO-001"], ["OBS-002", "OBS-005"], ["INV-011"]), trace("IT-011", "illegal", "Delay outside configured range", "Illegal stimulus failure", ["ENV-002"], ["OBS-005"], ["INV-013"]), trace("IT-012", "illegal", "Legal completion reports non-OK status", "Fail", ["DUT-PROTO-002"], ["OBS-002"], ["INV-012"])]


def traceability():
    groups = [(["DUT-LC-001", "DUT-LC-002"], ["OBS-001", "OBS-002"], ["CHK-LIFECYCLE"], ["INV-001", "INV-002"], ["LT-001"]), (["ENV-001"], ["OBS-001", "OBS-005"], ["CHK-PROTOCOL"], ["INV-010"], ["LT-010", "IT-009"]), (["ENV-002"], ["OBS-005"], ["CHK-LIVENESS"], ["INV-013"], ["IT-011"]), (["ENV-003"], ["OBS-001", "OBS-005"], ["CHK-LIFECYCLE"], ["INV-003"], ["IT-004"]), (["ENV-004"], ["OBS-001", "OBS-002"], ["CHK-DATA"], ["INV-008"], ["LT-007"]), (["DUT-PROTO-001"], ["OBS-002", "OBS-005"], ["CHK-PROTOCOL"], ["INV-011"], ["LT-011", "IT-010"]), (["DUT-PROTO-002"], ["OBS-002"], ["CHK-DATA"], ["INV-012"], ["IT-012"]), (["DUT-PROTO-003"], ["OBS-003", "OBS-005"], ["CHK-PROTOCOL"], ["INV-014"], ["LT-005"]), (["DUT-LC-003", "DUT-LC-004"], ["OBS-001", "OBS-002", "OBS-005"], ["CHK-LIFECYCLE"], ["INV-001", "INV-003"], ["LT-004", "IT-004"]), (["DUT-LC-005", "DUT-LC-006", "DUT-LC-007", "DUT-LC-011", "DUT-LC-012", "DUT-LC-013"], ["OBS-001", "OBS-002"], ["CHK-CAPACITY"], ["INV-004", "INV-009"], ["LT-002", "LT-012", "LT-013", "IT-003"]), (["DUT-PROTO-004"], ["OBS-006"], ["CHK-CAPACITY"], ["INV-016"], ["LT-012"]), (["ENV-005"], ["OBS-001"], [], [], []), (["DUT-LC-009", "DUT-LC-010", "DUT-LC-014", "DUT-LC-015"], ["OBS-001", "OBS-002"], ["CHK-LIFECYCLE"], ["INV-001", "INV-002"], ["LT-001", "LT-006", "LT-014"]), (["DUT-DATA-001", "DUT-DATA-002", "DUT-DATA-003", "DUT-DATA-004"], ["OBS-001", "OBS-002"], ["CHK-DATA"], ["INV-008"], ["LT-007", "LT-008", "IT-005"]), (["DUT-RST-001", "DUT-RST-004", "DUT-RST-005", "DUT-RST-006", "DUT-RST-007"], ["OBS-003", "OBS-005"], ["CHK-PROTOCOL"], ["INV-005", "INV-014"], ["LT-005"]), (["DUT-RST-002", "DUT-RST-003"], ["OBS-001", "OBS-002", "OBS-003"], ["CHK-LIFECYCLE"], ["INV-005", "INV-006"], ["LT-005", "IT-006"]), (["DUT-LIVE-001", "DUT-LIVE-002"], ["OBS-001", "OBS-002", "OBS-003"], ["CHK-LIVENESS"], ["INV-013"], ["LT-009", "IT-008"])]
    return [{"requirement_ids": a, "observation_ids": b, "checker_ids": c, "invariant_ids": d, "assertion_ids": [], "primary_trace_ids": e} for a, b, c, d, e in groups] + [{"requirement_ids": ["DUT-LC-002"], "observation_ids": ["OBS-002"], "checker_ids": ["CHK-LIVENESS"], "invariant_ids": ["INV-015"], "assertion_ids": [], "primary_trace_ids": ["LT-001", "IT-001"]}]


def gates():
    return [{"id": "GR-001", "condition": "Signals and transaction fields have direction, width/model type, producer, and meaning", "status": "satisfied_by_validator", "requirement_ids": ["DUT-PROTO-001"], "observation_ids": ["OBS-001", "OBS-002"], "invariant_ids": [], "decision_ids": []}, {"id": "GR-002", "condition": "Every semantic state transition has an observable trigger and state effect", "status": "satisfied_by_prd", "requirement_ids": ["DUT-LC-001", "DUT-LC-002", "DUT-RST-001"], "observation_ids": ["OBS-001", "OBS-002", "OBS-003"], "invariant_ids": ["INV-001", "INV-005"], "decision_ids": []}, {"id": "GR-003", "condition": "Each component has one responsibility and authoritative state has one owner", "status": "satisfied_by_validator", "requirement_ids": [], "observation_ids": [], "invariant_ids": [], "decision_ids": ["OD-008"]}, {"id": "GR-004", "condition": "Simultaneous-edge behavior is deterministic or explicitly nondeterministic (v0.0e: all simultaneous-edge behavior is deterministic; final-slot arbitration removed with the symmetric-hold rework)", "status": "satisfied_by_prd", "requirement_ids": ["DUT-LC-015"], "observation_ids": ["OBS-001", "OBS-002"], "invariant_ids": [], "decision_ids": ["OD-002"]}, {"id": "GR-005", "condition": "Assumptions, guarantees, mock defaults, and verification-only constraints remain distinct", "status": "satisfied_by_validator", "requirement_ids": ["ENV-001", "DUT-PROTO-001"], "observation_ids": [], "invariant_ids": [], "decision_ids": []}, {"id": "GR-006", "condition": "Every normative requirement maps to observation and checker/invariant/assertion", "status": "satisfied_by_validator", "requirement_ids": [], "observation_ids": [], "invariant_ids": [], "decision_ids": []}, {"id": "GR-007", "condition": "Existing requirement IDs remain stable", "status": "satisfied_by_prd", "requirement_ids": [], "observation_ids": [], "invariant_ids": [], "decision_ids": []}, {"id": "GR-008", "condition": "No blocking semantic-closure decision remains open", "status": "satisfied_by_validator", "requirement_ids": [], "observation_ids": [], "invariant_ids": [], "decision_ids": ["OD-001", "OD-008"]}, {"id": "GR-009", "condition": "Candidate semantic model validates against schema with no unresolved references", "status": "satisfied_by_validator", "requirement_ids": [], "observation_ids": [], "invariant_ids": [], "decision_ids": []}, {"id": "GR-010", "condition": "Later generation manifest records mock parameters, encodings, source, and generator revision", "status": "deferred_later_stage", "requirement_ids": [], "observation_ids": [], "invariant_ids": [], "decision_ids": []}]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("uvm_buffer_semantic_model.candidate.json"))
    args = ap.parse_args()
    model = SemanticModel.model_validate(build())
    args.out.write_text(model.model_dump_json(indent=2) + "\n")
    print(f"OK: candidate semantic model validates; wrote {args.out}")
    print(f"    requirements={len(model.requirements)} observations={len(model.observations)} "
          f"invariants={len(model.invariants)} legal_traces={len(model.legal_traces)} "
          f"illegal_traces={len(model.illegal_traces)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
