"""Event and record dataclasses for the deterministic lifecycle referee.

Plain data, no behavior (oracle-plan-v0.3 §3).  Field names mirror the
committed semantic model (candidate-v0.0e-001,
``uvm_buffer_semantic_model.candidate.json``) and the PRD v0.0e contracts:

===========  =====================================================
Dataclass    Committed contract
===========  =====================================================
AcceptedRequest    OBS-001  (request accepted)
CompletedResponse  OBS-002  (response completed)
ResetTransition    OBS-003  (reset transition)
ProtocolViolation  OBS-005  (protocol violation)
EdgeSample         OBS-006  (edge sample)
===========  =====================================================

``EdgeSample`` carries only monitor-observable inputs (cycle, req_hold,
req_valid).  Occupancy is the oracle's own book, computed internally from the
event stream; it is never an input (oracle-plan-v0.3 §2d/§3/§4).

The referee emits exactly two verdict record kinds, both declared in the
committed schema:

- ``OracleResult``        -- ORACLE-RESULT-001, field set per PRD §5.1.2
                             (Oracle-Result Contract).
- ``HoldViolationRecord`` -- HOLD-VIOLATION-001, field set per the committed
                             hold-violation contract (INV-016 failures).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Mock encodings (committed model ``mock_encodings``; PRD §3.1).  They belong
# to the mock implementation contract and are not semantic rules.
OP_READ = 0
OP_WRITE = 1
STATUS_OK = 0

# Watchdog bound (committed model parameter WATCHDOG_CYCLES; PRD §3.8).
WATCHDOG_CYCLES = 256

# Hold threshold (DUT-LC-012): at pre-edge occupancy 15 or more,
# req_hold[1:0] == 2'b11.  Depth is 16; occupancy 16 is the transient cushion
# slot reachable only in the hold/accept race.
HOLD_THRESHOLD = 15


class LifecycleError(Enum):
    """Oracle-result lifecycle disposition (PRD §5.1.2 ``error_code``)."""

    NONE = "NONE"
    UNKNOWN_ID = "UNKNOWN_ID"
    DUPLICATE_COMPLETION = "DUPLICATE_COMPLETION"
    STALE_RESPONSE = "STALE_RESPONSE"


# ---------------------------------------------------------------------------
# Input events (monitor-observable facts only; PRD §5.1)
# ---------------------------------------------------------------------------


@dataclass
class AcceptedRequest:
    """OBS-001 -- a request was accepted on source ``source`` this edge."""

    cycle: int
    source: int  # 0 or 1
    id: int
    addr: int
    operation: int  # OP_READ or OP_WRITE
    write_data: int
    requested_delay: int


@dataclass
class CompletedResponse:
    """OBS-002 -- a response handshake completed this edge."""

    cycle: int
    observation_seq: int  # unique monotonic key assigned by the response monitor
    id: int
    read_data: int
    status: int


@dataclass
class ResetTransition:
    """OBS-003 -- raw reset transition published by the reset monitor.

    ``reset_state`` is True on assertion, False on deassertion.  The monitor
    owns no epoch or lifecycle state (COMP-RESET-MONITOR).
    """

    cycle: int
    reset_state: bool


@dataclass
class ProtocolViolation:
    """OBS-005 -- a wire rule break reported by the monitor/checker layer.

    Lifecycle classification of completions is the oracle's job; this event is
    carried in the stream for completeness of the observation contract.
    """

    cycle: int
    violation_channel: str  # REQ0 / REQ1 / RSP / RESET / TEST
    violated_rule: str  # stable requirement or invariant ID
    id_valid: bool
    id: int = 0


@dataclass
class EdgeSample:
    """OBS-006 -- the metronome: fired every cycle.

    Per-source sampled ``req_hold`` / ``req_valid`` at the rising edge.
    Index 0 = source 0, index 1 = source 1.  No occupancy field: occupancy is
    oracle-internal book (oracle-plan-v0.3 §2d).
    """

    cycle: int
    req_hold: tuple[bool, bool]
    req_valid: tuple[bool, bool]


# ---------------------------------------------------------------------------
# Emitted verdict records
# ---------------------------------------------------------------------------


@dataclass
class OracleResult:
    """ORACLE-RESULT-001 -- one per CompletedResponse, including
    lifecycle-invalid responses (INV-015).  Field set per PRD §5.1.2."""

    observation_seq: int
    reset_epoch: int
    service_counter: int
    lifecycle_valid: bool
    error_code: LifecycleError
    matched_request_valid: bool
    matched_request: AcceptedRequest | None
    compare_read_data: bool
    expected_read_data: int | None
    expected_status: int | None


@dataclass
class HoldViolationRecord:
    """HOLD-VIOLATION-001 -- one per INV-016 failure.  Distinct type, never an
    OracleResult.  ``pre_edge_occupancy`` is the oracle's own stamp for
    diagnosability (producer: oracle), not an observed input."""

    cycle: int
    source: int
    req_hold: tuple[bool, bool]
    pre_edge_occupancy: int
    violated_rule: str  # DUT-LC-012 (threshold arm) or DUT-PROTO-004 (guarantee arm)
