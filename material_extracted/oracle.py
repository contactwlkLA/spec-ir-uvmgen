"""LifecycleOracle -- the single scorekeeper (oracle-plan-v0.3 §4/§5).

Ordinary deterministic Python: no model, no prompts, no inference.  The
oracle is the sole owner of every semantic state object (COMP-ORACLE /
agree-3 / OD-008) and the only producer of expected results:

===============  ======================================================
State object     Meaning
===============  ======================================================
outstanding_table  id -> AcceptedRequest (STATE-OUTSTANDING)
occupancy          outstanding count, kept == table size (INV-009)
reset_epoch        advanced per DUT-RST-004 (STATE-EPOCH)
service_counter    response-service-enabled cycle count (PRD §3.8)
watchdog           id -> service-counter value at acceptance
golden_mem         addr -> latest completed write data (STATE-GOLDEN-MEM)
completed_id_set   verification-only ID history
flushed_id_set     verification-only ID history (OD-005 reservation)
===============  ======================================================

Timekeeping mirrors PRD §5.2: the harness gives the oracle a read-only
per-cycle view of ``rst`` and ``rsp_ready`` (:meth:`LifecycleOracle.tick`)
solely to advance the service counter and watchdog.  Transaction identity
and payload enter only through monitor observations (:meth:`process`).

Emitted verdicts are exactly the two committed record kinds: ``OracleResult``
(lifecycle) and ``HoldViolationRecord`` (INV-016).  The ``reports`` list is a
diagnostic log (duplicate accepted IDs, unwritten reads, watchdog flags) --
it is not a verdict record kind and not semantic state.

Per-cycle processing convention (deterministic, documented, and enforced by
process()'s ordering guard -- a backwards cycle, a non-first EdgeSample, or a
duplicate EdgeSample raises):
  1. tick(cycle, rst, rsp_ready)  -- timekeeping only
  2. EdgeSample                   -- beginning-of-edge: threshold arm sees
     pre-edge occupancy; guarantee arm defers to cycle end
  3. ResetTransition              -- reset dominates (DUT-PROTO-003)
  4. CompletedResponse            -- same-edge completion frees no same-edge
     acceptance slot (DUT-LC-011/OD-002)
  5. AcceptedRequest
"""
from __future__ import annotations

from oracle_events import (
    WATCHDOG_CYCLES,
    HOLD_THRESHOLD,
    STATUS_OK,
    OP_WRITE,
    AcceptedRequest,
    CompletedResponse,
    EdgeSample,
    HoldViolationRecord,
    LifecycleError,
    OracleResult,
    ResetTransition,
)


class LifecycleOracle:
    def __init__(self) -> None:
        # The eight semantic state objects -- all of it, exactly once.
        self.outstanding_table: dict[int, AcceptedRequest] = {}
        self.occupancy: int = 0
        self.reset_epoch: int = 0
        self.service_counter: int = 0
        self.watchdog: dict[int, int] = {}  # id -> service counter at acceptance
        self.golden_mem: dict[int, int] = {}
        self.completed_id_set: set[int] = set()
        self.flushed_id_set: set[int] = set()

        # Emitted verdicts (the only two record kinds).
        self.results: list[OracleResult] = []
        self.hold_violations: list[HoldViolationRecord] = []

        # Diagnostic log -- not verdict records, not semantic state.
        self.reports: list[str] = []

        # Bookkeeping (not semantic state): deferred DUT-PROTO-004 guarantee
        # checks, per-cycle acceptances, DUT-RST-004 epoch-advance condition,
        # and stream-cycle tracking (the latter backs the ordering guard).
        self._pending_guarantees: list[tuple[int, int, tuple[bool, bool], int]] = []
        self._accepts_by_cycle: dict[int, set[int]] = {}
        self._operated_since_assertion: bool = False
        self._last_cycle: int = 0
        self._events_in_cycle: int = 0

    # ------------------------------------------------------------------
    # Timekeeping (read-only rst/rsp_ready view; PRD §5.2, §3.8)
    # ------------------------------------------------------------------

    def _advance_cycle(self, cycle: int) -> None:
        """Cycle-advance bookkeeping shared by tick() and process(): resolve
        guarantee checks left open by earlier cycles, then open the new cycle."""
        self._flush_guarantees(before_cycle=cycle)
        self._last_cycle = cycle
        self._events_in_cycle = 0

    def tick(self, cycle: int, rst: int, rsp_ready: int) -> None:
        """Advance service counter and watchdog once per rising edge.

        Increments only when ``rst == 0 && rsp_ready == 1`` (PRD §3.8);
        cycles with reset or ready low do not advance the watchdog
        (DUT-LIVE-002).  Never touches epoch, table, or memory: on a reset
        edge reset is the only state transition (DUT-RST-004) and the flush
        itself arrives via the reset monitor's OBS-003 event.
        """
        if cycle > self._last_cycle:
            self._advance_cycle(cycle)
        if rst == 0:
            self._operated_since_assertion = True
        if rst == 0 and rsp_ready == 1:
            self.service_counter += 1
            # Watchdog: flag when a transaction is still outstanding at the
            # start of the (256+1)-th service-enabled cycle after acceptance
            # -- i.e. it did not complete "within 256 response-service-enabled
            # cycles after acceptance" (DUT-LIVE-002 / INV-013).  The ==
            # condition fires exactly once per offending entry.
            for tid, accepted_service in self.watchdog.items():
                if self.service_counter - accepted_service == WATCHDOG_CYCLES + 1:
                    self.reports.append(
                        f"cycle {cycle}: watchdog -- ID {tid} exceeded "
                        f"{WATCHDOG_CYCLES} response-service-enabled cycles "
                        f"(INV-013 / DUT-LIVE-002)"
                    )

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    def process(self, event) -> None:
        if event.cycle < self._last_cycle:
            raise ValueError(
                f"backwards event stream: {type(event).__name__} at cycle "
                f"{event.cycle} precedes last processed cycle {self._last_cycle}"
            )
        if event.cycle > self._last_cycle:
            self._advance_cycle(event.cycle)
        if isinstance(event, EdgeSample) and self._events_in_cycle:
            raise ValueError(
                f"cycle {event.cycle}: EdgeSample must be the first event of "
                f"its cycle (metronome contract; the beginning-of-edge "
                f"occupancy read requires it) -- {self._events_in_cycle} "
                f"event(s) already processed this cycle"
            )
        self._events_in_cycle += 1
        if isinstance(event, EdgeSample):
            self._on_edge_sample(event)
        elif isinstance(event, ResetTransition):
            self._on_reset(event)
        elif isinstance(event, CompletedResponse):
            self._on_completion(event)
        elif isinstance(event, AcceptedRequest):
            self._on_accept(event)
        elif isinstance(event, ProtocolViolation):
            pass  # wire-rule reporting belongs to the monitor/checker layer
        else:
            raise TypeError(f"unknown event type: {type(event).__name__}")

    def finish(self) -> None:
        """Resolve guarantee checks still open at end of stream."""
        self._flush_guarantees(before_cycle=None)

    # ------------------------------------------------------------------
    # Job 4 -- Hold (DUT-LC-012 threshold arm + DUT-PROTO-004 guarantee arm)
    # ------------------------------------------------------------------

    def _on_edge_sample(self, ev: EdgeSample) -> None:
        # EdgeSample is processed first within its cycle -- enforced by the
        # process() ordering guard, not by convention -- so self.occupancy
        # here is the beginning-of-edge (pre-edge) occupancy (DUT-LC-011/OD-002).
        pre_edge = self.occupancy
        # Threshold arm: pre-edge occupancy >= 15 => req_hold[1:0] == 2'b11
        # (DUT-LC-012 / INV-016).  One-directional by requirement text: the
        # PRD nowhere forbids conservative holding below the threshold, so
        # the referee must not invent the reverse rule.
        if pre_edge >= HOLD_THRESHOLD:
            for p in (0, 1):
                if not ev.req_hold[p]:
                    self.hold_violations.append(
                        HoldViolationRecord(
                            cycle=ev.cycle,
                            source=p,
                            req_hold=ev.req_hold,
                            pre_edge_occupancy=pre_edge,
                            violated_rule="DUT-LC-012",
                        )
                    )
        # Guarantee arm (deferred): hold low + valid high => the request is
        # accepted at that same edge (DUT-PROTO-004 / INV-016).  Acceptance
        # events for this cycle arrive after this sample, so the check
        # resolves when the first later-cycle event (or finish()) arrives.
        for p in (0, 1):
            if not ev.req_hold[p] and ev.req_valid[p]:
                self._pending_guarantees.append(
                    (ev.cycle, p, ev.req_hold, pre_edge)
                )

    def _flush_guarantees(self, before_cycle: int | None) -> None:
        remaining: list[tuple[int, int, tuple[bool, bool], int]] = []
        for cycle, source, req_hold, pre_edge in self._pending_guarantees:
            due = before_cycle is None or cycle < before_cycle
            if due:
                if source not in self._accepts_by_cycle.get(cycle, ()):
                    self.hold_violations.append(
                        HoldViolationRecord(
                            cycle=cycle,
                            source=source,
                            req_hold=req_hold,
                            pre_edge_occupancy=pre_edge,
                            violated_rule="DUT-PROTO-004",
                        )
                    )
            else:
                remaining.append((cycle, source, req_hold, pre_edge))
        self._pending_guarantees = remaining
        if before_cycle is not None:
            for cycle in [c for c in self._accepts_by_cycle if c < before_cycle]:
                del self._accepts_by_cycle[cycle]

    # ------------------------------------------------------------------
    # Job 1 -- Reset (DUT-RST-001/003/004/005; INV-005; OD-004/OD-005)
    # ------------------------------------------------------------------

    def _on_reset(self, ev: ResetTransition) -> None:
        if not ev.reset_state:
            return  # deassertion: operation resumes on the first rst==0 edge (DUT-RST-007); no oracle state change
        # Flush outstanding IDs into the verification-only history
        # (DUT-RST-001; OD-005: a stale-response mutation reserves its flushed
        # ID until the injected response is observed).
        self.flushed_id_set.update(self.outstanding_table.keys())
        self.outstanding_table.clear()
        self.watchdog.clear()  # reset cancels watchdog state (DUT-LIVE-002)
        self.occupancy = 0
        # Reset clears the golden memory (DUT-RST-005); an address is
        # unwritten again in the new epoch.
        self.golden_mem.clear()
        # Epoch advances only on the first edge sampling rst==1 after an
        # operational edge (DUT-RST-004).
        if self._operated_since_assertion:
            self.reset_epoch += 1
        self._operated_since_assertion = False

    # ------------------------------------------------------------------
    # Job 2 -- Accept (DUT-LC-001; INV-001; ENV-003; PRD §5.2)
    # ------------------------------------------------------------------

    def _on_accept(self, ev: AcceptedRequest) -> None:
        # A hold-low + valid acceptance satisfies the deferred guarantee arm.
        self._accepts_by_cycle.setdefault(ev.cycle, set()).add(ev.source)
        if ev.id in self.outstanding_table:
            # ENV-003: an accepted duplicate ID is an illegal-stimulus
            # failure reported by the lifecycle oracle; DUT behavior after
            # the violation is unspecified, so no second entry is opened.
            # Full duplicate-accept handling enters with IT-004 (exit pass).
            self.reports.append(
                f"cycle {ev.cycle}: duplicate accepted ID {ev.id} on source "
                f"{ev.source} (ENV-003 illegal stimulus); behavior unspecified"
            )
            return
        # Legal ID reuse: remove the ID from the applicable history set
        # before creating the new outstanding entry (PRD §5.2).
        self.completed_id_set.discard(ev.id)
        self.flushed_id_set.discard(ev.id)
        self.outstanding_table[ev.id] = ev
        self.watchdog[ev.id] = self.service_counter
        self.occupancy += 1

    # ------------------------------------------------------------------
    # Job 3 -- Complete (DUT-LC-002/003; DUT-DATA-001/002; DUT-RST-002;
    #            INV-002/003/006/015; OD-003/OD-005/OD-007)
    # ------------------------------------------------------------------

    def _on_completion(self, ev: CompletedResponse) -> None:
        if ev.id in self.outstanding_table:
            result = self._complete_legal(ev)
        elif ev.id in self.flushed_id_set:
            # Stale pre-reset response observed after reset deassertion
            # (DUT-RST-002 / INV-006 / IT-006).  OD-005: the flushed ID stays
            # reserved in flushed_id_set (a later legal reuse removes it at
            # accept time).
            result = self._invalid_result(ev, LifecycleError.STALE_RESPONSE)
        elif ev.id in self.completed_id_set:
            # Duplicate completion (DUT-LC-003 / INV-003 / IT-002).  MUT-001
            # reserves the ID until the injected response is observed; the ID
            # stays in completed_id_set by construction.
            result = self._invalid_result(ev, LifecycleError.DUPLICATE_COMPLETION)
        else:
            # Unknown-ID completion (INV-002 / INV-003 / IT-001).  Only legal
            # completions record into the history sets; no state changes.
            result = self._invalid_result(ev, LifecycleError.UNKNOWN_ID)
        self.results.append(result)

    def _complete_legal(self, ev: CompletedResponse) -> OracleResult:
        entry = self.outstanding_table.pop(ev.id)
        del self.watchdog[ev.id]
        self.occupancy -= 1
        self.completed_id_set.add(ev.id)
        compare_read_data = entry.operation != OP_WRITE
        expected_read_data: int | None = None
        if compare_read_data:
            if entry.addr in self.golden_mem:
                expected_read_data = self.golden_mem[entry.addr]
            else:
                # Read to an address with no earlier completed write in this
                # epoch (ENV-004 / DUT-DATA-004 illegal stimulus).  Reported;
                # not exercised by the milestone stories.
                self.reports.append(
                    f"cycle {ev.cycle}: read of unwritten address "
                    f"{entry.addr} (ENV-004 illegal stimulus)"
                )
        if not compare_read_data:
            # Write visibility updates the associative memory when the write
            # completes (DUT-DATA-001).
            self.golden_mem[entry.addr] = entry.write_data
        return OracleResult(
            observation_seq=ev.observation_seq,
            reset_epoch=self.reset_epoch,
            service_counter=self.service_counter,
            lifecycle_valid=True,
            error_code=LifecycleError.NONE,
            matched_request_valid=True,
            matched_request=entry,
            compare_read_data=compare_read_data,
            expected_read_data=expected_read_data,
            expected_status=STATUS_OK,  # DUT-PROTO-002 / OD-007
        )

    def _invalid_result(self, ev: CompletedResponse, error: LifecycleError) -> OracleResult:
        return OracleResult(
            observation_seq=ev.observation_seq,
            reset_epoch=self.reset_epoch,
            service_counter=self.service_counter,
            lifecycle_valid=False,
            error_code=error,
            matched_request_valid=False,
            matched_request=None,
            compare_read_data=False,
            expected_read_data=None,
            expected_status=None,
        )
