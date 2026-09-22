"""Eight scripted referee stories (oracle-plan-v0.3 §6) -- the harness.

Fixture authoring rule (plan F1): every expected verdict below is AUTHORED --
hand-derived from the PRD v0.0e normative requirement text (§3 behavioral
contract, §4 closure decisions, §5 verification intent).  The PRD §7
trace-summary prose is orientation only.  A referee failure is therefore
treated as ambiguous until the fixture is independently re-derived from the
requirement text: wrong fixture and wrong oracle look identical, and there is
no independent arbiter at milestone.

Stories (trace ID -> milestone): LT-001, LT-005, LT-007, LT-009, LT-012,
IT-001, IT-002, IT-006.  The 17 remaining scenarios are the standing exit
criterion in deferment.md, not part of this pass.

Known milestone gap (plan F2/N2, bounded): the stories exercise the hold
threshold check and the guarantee arm in its non-firing form; the positive
guarantee case is covered at exit (PRD LT-002/LT-013).  The watchdog fire
path is likewise only exercised at exit (IT-008).

Per-cycle script convention (deterministic; mirrors oracle.py):
  1. tick(cycle, rst, rsp_ready)   2. EdgeSample   3. ResetTransition
  4. CompletedResponse             5. AcceptedRequest
Events within a cycle are listed in that order (the oracle's process() guard
enforces it -- backwards cycles, non-first EdgeSamples, and duplicate
EdgeSamples raise; see check_guard); inline CHECK items may appear
between cycles.  The harness holds events and expected verdicts only -- it
duplicates no oracle state (plan §4).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from oracle import LifecycleOracle
from oracle_events import (
    OP_READ,
    OP_WRITE,
    STATUS_OK,
    AcceptedRequest,
    CompletedResponse,
    EdgeSample,
    LifecycleError,
    ResetTransition,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def C(cycle: int, *events, rst: int = 0, ready: int = 1):
    """One rising edge: timekeeping tick, then that cycle's events in order."""
    return ("cycle", cycle, rst, ready, list(events))


def CHECK(fn, label: str):
    return ("check", fn, label)


def edge(c, h0, h1, v0=0, v1=0) -> EdgeSample:
    """OBS-006 metronome sample: per-source hold/valid (h0/h1, v0/v1)."""
    return EdgeSample(c, (bool(h0), bool(h1)), (bool(v0), bool(v1)))


def acc(c, src, tid, addr, op, wdata=0, delay=1) -> AcceptedRequest:
    """OBS-001 acceptance (mock defaults: delay 1, no write payload for reads)."""
    return AcceptedRequest(c, src, tid, addr, op, wdata, delay)


def comp(c, seq, tid, rdata=0, status=STATUS_OK) -> CompletedResponse:
    """OBS-002 completion."""
    return CompletedResponse(c, seq, tid, rdata, status)


def rst(c, asserted: bool) -> ResetTransition:
    """OBS-003 raw reset transition."""
    return ResetTransition(c, asserted)


# ---------------------------------------------------------------------------
# Authored expectation helpers (F1: derived from the requirement text)
# ---------------------------------------------------------------------------


def result_by_seq(oracle: LifecycleOracle, seq: int):
    matches = [r for r in oracle.results if r.observation_seq == seq]
    assert len(matches) == 1, f"INV-015: expected exactly one result for seq {seq}, got {len(matches)}"
    return matches[0]


def expect_legal(r, matched_id, compare: bool, exp_rdata=None, epoch=None) -> None:
    """Legal completion (DUT-LC-002 / INV-002): matched request, OK status,
    read comparison enabled exactly for reads (DUT-DATA-002)."""
    assert r.lifecycle_valid, f"expected legal completion, got {r.error_code}"
    assert r.error_code is LifecycleError.NONE
    assert r.matched_request_valid and r.matched_request.id == matched_id
    assert r.compare_read_data is compare
    assert r.expected_read_data == exp_rdata
    assert r.expected_status == STATUS_OK  # DUT-PROTO-002 / OD-007
    if epoch is not None:
        assert r.reset_epoch == epoch


def expect_invalid(r, err: LifecycleError) -> None:
    """Lifecycle-invalid completion (INV-003 / INV-006): no matched request,
    no expected payload -- the scoreboard reports identity/lifecycle failure."""
    assert not r.lifecycle_valid
    assert r.error_code is err
    assert not r.matched_request_valid and r.matched_request is None
    assert r.compare_read_data is False
    assert r.expected_read_data is None and r.expected_status is None


def expect_clean_hold(oracle: LifecycleOracle) -> None:
    assert oracle.hold_violations == [], f"unexpected INV-016 records: {oracle.hold_violations}"


# ---------------------------------------------------------------------------
# The eight stories
# ---------------------------------------------------------------------------


def lt001_fill() -> list:
    return [
        C(1, edge(1, 0, 0)),
        # DUT-LC-001: accept on valid && !hold (hold low at occupancy 0-1,
        # far below the DUT-LC-012 threshold).  DUT-PROTO-004 guarantee arm:
        # hold-low + valid => accepted same edge (satisfied below).
        C(2, edge(2, 0, 0, 1, 0), acc(2, 0, 1, 0x100, OP_WRITE, 0xA1)),
        C(3, edge(3, 0, 0, 0, 1), acc(3, 1, 2, 0x200, OP_WRITE, 0xB2)),
        # Reverse-order completion (DUT-LC-009).  ID 2 accepted c3 delay 1 =>
        # eligible c4 = 3+1 (DUT-LC-014); completes c4.
        C(4, edge(4, 0, 0), comp(4, 1, 2)),
        C(5, edge(5, 0, 0), comp(5, 2, 1)),
    ]


def lt001_final(oracle: LifecycleOracle) -> None:
    r1 = result_by_seq(oracle, 1)  # completed first: newest request (DUT-LC-009)
    expect_legal(r1, matched_id=2, compare=False)
    r2 = result_by_seq(oracle, 2)
    expect_legal(r2, matched_id=1, compare=False)
    assert oracle.occupancy == 0 and not oracle.outstanding_table  # INV-001/INV-002 closed
    assert oracle.completed_id_set == {1, 2} and oracle.flushed_id_set == set()
    assert oracle.golden_mem == {0x100: 0xA1, 0x200: 0xB2}  # DUT-DATA-001 write visibility
    expect_clean_hold(oracle)
    assert oracle.reports == []  # DUT-LIVE-001/002: no watchdog flag


def lt005_mid(oracle: LifecycleOracle) -> None:
    # Authored from DUT-RST-001 (flush), DUT-RST-004 (one epoch advance on
    # the first rst==1 edge after operational edges -- cycles 1-3 operated),
    # DUT-RST-005 (memory clear), OD-005 (flushed IDs reserved).
    assert oracle.occupancy == 0 and not oracle.outstanding_table
    assert oracle.reset_epoch == 1
    assert oracle.flushed_id_set == {1, 2}
    assert oracle.golden_mem == {}
    expect_clean_hold(oracle)


def lt005_final(oracle: LifecycleOracle) -> None:
    r1 = result_by_seq(oracle, 1)
    expect_legal(r1, matched_id=1, compare=False, epoch=1)  # completion in the new epoch
    assert oracle.occupancy == 0
    assert oracle.completed_id_set == {1}  # DUT-RST-003 reuse; PRD §5.2 history-set removal at accept
    assert oracle.flushed_id_set == {2}  # ID 2 stays reserved (OD-005)
    assert oracle.golden_mem == {0x30: 0x33}
    expect_clean_hold(oracle)
    assert oracle.reports == []


def lt007_final(oracle: LifecycleOracle) -> None:
    r1 = result_by_seq(oracle, 1)
    expect_legal(r1, matched_id=1, compare=False)
    # DUT-DATA-002: read returns the latest completed write data for the
    # address, as observed at the read completion event.
    r2 = result_by_seq(oracle, 2)
    expect_legal(r2, matched_id=2, compare=True, exp_rdata=0xCAFE)
    assert oracle.golden_mem == {0x2A: 0xCAFE}
    assert oracle.occupancy == 0 and oracle.completed_id_set == {1, 2}
    expect_clean_hold(oracle)
    assert oracle.reports == []


def lt009_final(oracle: LifecycleOracle) -> None:
    r1 = result_by_seq(oracle, 1)
    expect_legal(r1, matched_id=1, compare=False)
    # Service-enabled accounting (PRD §3.8 / DUT-LIVE-002): counter advanced
    # on cycles 1, 2, 263, 264 only -- the 260 ready-low cycles did not count.
    assert oracle.service_counter == 4
    # The acceptance-to-completion wall clock is 262 cycles (> 256); only the
    # 2 service-enabled cycles count, so INV-013 must NOT fire.
    assert oracle.reports == []
    assert oracle.occupancy == 0
    expect_clean_hold(oracle)


def lt012_fill() -> list:
    script = []
    # Fill to occupancy 14 with dual-source accepts (DUT-LC-007: both
    # accepted when >= 2 slots free).  Pre-edge occupancy stays below the
    # DUT-LC-012 threshold, so hold low is legal (the requirement mandates
    # hold only at >= 15; below it the referee must not invent a rule).
    for k, c in enumerate(range(2, 9)):
        id0, id1 = 1 + 2 * k, 2 + 2 * k
        script.append(
            C(
                c,
                edge(c, 0, 0, 1, 1),
                acc(c, 0, id0, 0x100 + id0, OP_WRITE, 0x10 + id0),
                acc(c, 1, id1, 0x100 + id1, OP_WRITE, 0x10 + id1),
            )
        )
    # Pre-edge occupancy 14 < 15 => hold low legal; both sources accepted
    # (DUT-LC-007): 14 + 2 = 16 <= depth -- the transient cushion slot of
    # DUT-LC-012's note, reachable only through this hold/accept race.
    script.append(
        C(
            9,
            edge(9, 0, 0, 1, 1),
            acc(9, 0, 15, 0x115, OP_WRITE, 0x115 + 0x10),
            acc(9, 1, 16, 0x116, OP_WRITE, 0x116 + 0x10),
        )
    )
    # Pre-edge occupancy 16 >= 15 => req_hold == 2'b11 (DUT-LC-012).  A
    # response completes on the same edge (rsp_ready high); the same-edge
    # completion frees no same-edge acceptance slot (DUT-LC-011 / OD-002),
    # so the valid request on source 0 stays held -- no acceptance event.
    script.append(C(10, edge(10, 1, 1, 1, 0), comp(10, 1, 1)))
    return script


def lt012_mid(oracle: LifecycleOracle) -> None:
    # Authored from DUT-LC-011/012: response completed, request remained
    # held, next occupancy is 15 (LT-012's expected result, in requirement
    # terms).  Threshold arm satisfied at pre-edge 16 (hold 11).
    assert oracle.occupancy == 15
    expect_clean_hold(oracle)


def lt012_final(oracle: LifecycleOracle) -> None:
    r1 = result_by_seq(oracle, 1)
    expect_legal(r1, matched_id=1, compare=False)
    assert oracle.occupancy == 15
    assert oracle.outstanding_table.keys() == set(range(2, 17))  # INV-009: occupancy == table size
    assert oracle.completed_id_set == {1}
    # Pre-edge occupancy 15 >= 15 => hold 11 sustained (DUT-LC-012).
    expect_clean_hold(oracle)
    assert oracle.reports == []


def it001_final(oracle: LifecycleOracle) -> None:
    # INV-002/INV-003: a completion for an unknown ID fails; only legal
    # completions record into the history sets, so no state changes.
    expect_invalid(result_by_seq(oracle, 1), LifecycleError.UNKNOWN_ID)
    assert oracle.occupancy == 0 and not oracle.outstanding_table
    assert oracle.completed_id_set == set()
    expect_clean_hold(oracle)


def it002_final(oracle: LifecycleOracle) -> None:
    expect_legal(result_by_seq(oracle, 1), matched_id=1, compare=False)
    # INV-003 / OD-003: duplicate completion fails.  MUT-001 reserves the ID
    # until the injected response is observed; it stays in completed_id_set.
    expect_invalid(result_by_seq(oracle, 2), LifecycleError.DUPLICATE_COMPLETION)
    assert oracle.occupancy == 0 and oracle.completed_id_set == {1}
    expect_clean_hold(oracle)


def it006_mid(oracle: LifecycleOracle) -> None:
    # DUT-RST-001/004/005 + INV-005: flush, one epoch advance, memory clear,
    # OD-005 reservation of the flushed ID.
    assert oracle.occupancy == 0 and oracle.reset_epoch == 1
    assert oracle.flushed_id_set == {1} and oracle.golden_mem == {}
    expect_clean_hold(oracle)


def it006_final(oracle: LifecycleOracle) -> None:
    # DUT-RST-002 / INV-006: a pre-reset response observed after reset
    # deassertion fails as STALE_RESPONSE (MUT-004: the flushed ID was not
    # reused before observation -- OD-005 reservation honored).
    expect_invalid(result_by_seq(oracle, 1), LifecycleError.STALE_RESPONSE)
    assert oracle.occupancy == 0
    assert oracle.flushed_id_set == {1}
    expect_clean_hold(oracle)


@dataclass
class Story:
    trace_id: str
    scenario: str  # PRD §7 summary -- orientation only (plan F1)
    fixture_basis: str  # requirement text the expectations are authored from
    script: list


def build_stories() -> list[Story]:
    return [
        Story(
            "LT-001",
            "Two accepted requests complete in reverse order",
            "DUT-LC-001/002/009/011/014, DUT-PROTO-002/004, DUT-DATA-001, INV-001/002/015, OD-007",
            lt001_fill(),
        ),
        Story(
            "LT-005",
            "Synchronous reset with outstanding transactions",
            "DUT-RST-001/002/003/004/005/006/007, DUT-LC-001/002, INV-005, OD-004/OD-005",
            [
                C(1, edge(1, 0, 0)),
                C(2, edge(2, 0, 0, 1, 0), acc(2, 0, 1, 0x10, OP_WRITE, 0x11)),
                C(3, edge(3, 0, 0, 0, 1), acc(3, 1, 2, 0x20, OP_WRITE, 0x22)),
                # Reset sampled on posedge (DUT-RST-004): reset is the only
                # transition on this edge; hold high and no handshake while
                # reset asserted (DUT-RST-006).
                C(4, edge(4, 1, 1), rst(4, True), rst=1),
                C(5, edge(5, 1, 1), rst=1),  # held: no epoch double-advance (DUT-RST-004)
                CHECK(lt005_mid, "mid-story: flush, epoch advance, memory clear, reservation"),
                C(6, edge(6, 0, 0), rst(6, False)),  # DUT-RST-007 release
                # DUT-RST-003: flushed IDs may be reused on the first
                # operational edge after release; PRD §5.2 removes the ID
                # from the history set before the new entry opens.
                C(7, edge(7, 0, 0, 1, 0), acc(7, 0, 1, 0x30, OP_WRITE, 0x33)),
                C(8, edge(8, 0, 0), comp(8, 1, 1)),
            ],
        ),
        Story(
            "LT-007",
            "Completed write followed by read of the same address",
            "DUT-DATA-001/002/004, DUT-LC-001/002/014, ENV-004, INV-008, OD-007",
            [
                C(1, edge(1, 0, 0)),
                C(2, edge(2, 0, 0, 1, 0), acc(2, 0, 1, 0x2A, OP_WRITE, 0xCAFE)),
                C(3, edge(3, 0, 0), comp(3, 1, 1)),  # write completes -> golden_mem update (DUT-DATA-001)
                # ENV-004 satisfied: the write completed in this epoch before
                # the read was issued.
                C(4, edge(4, 0, 0, 0, 1), acc(4, 1, 2, 0x2A, OP_READ)),
                C(5, edge(5, 0, 0), comp(5, 2, 2, rdata=0xCAFE)),
            ],
        ),
        Story(
            "LT-009",
            "Transaction completes at or before the 256th response-service-enabled cycle",
            "PRD §3.8 service-counter definition, DUT-LIVE-001/002, INV-013, DUT-LC-001/002",
            [
                C(1, edge(1, 0, 0)),
                C(2, edge(2, 0, 0, 1, 0), acc(2, 0, 1, 0x40, OP_WRITE, 0x44)),
                # rsp_ready low for 260 cycles (cycles 3-262): DUT-LIVE-002 --
                # ready-low cycles do not advance the watchdog.
                *[C(c, edge(c, 0, 0), ready=0) for c in range(3, 263)],
                C(263, edge(263, 0, 0)),
                C(264, edge(264, 0, 0), comp(264, 1, 1)),
            ],
        ),
        Story(
            "LT-012",
            "At full occupancy, a response completes while a request is valid on the same edge",
            "DUT-LC-005/006/007/011/012, DUT-PROTO-004, INV-004/009/016, OD-002",
            lt012_fill()
            + [
                CHECK(lt012_mid, "mid-story: response completed, request stayed held, next occupancy 15"),
                C(11, edge(11, 1, 1)),  # pre-edge 15 >= 15 => hold 11 sustained (DUT-LC-012)
            ],
        ),
        Story(
            "IT-001",
            "Completion for an unknown ID",
            "DUT-LC-002/003, INV-002/003, MUT-002, OD-003",
            [
                C(1, edge(1, 0, 0)),
                C(2, edge(2, 0, 0), comp(2, 1, 99)),
            ],
        ),
        Story(
            "IT-002",
            "Duplicate completion",
            "DUT-LC-002/003, INV-003, MUT-001, OD-003/OD-005",
            [
                C(1, edge(1, 0, 0)),
                C(2, edge(2, 0, 0, 1, 0), acc(2, 0, 1, 0x50, OP_WRITE, 0x55)),
                C(3, edge(3, 0, 0), comp(3, 1, 1)),  # legal completion
                C(4, edge(4, 0, 0), comp(4, 2, 1)),  # duplicate completion (ID reserved per MUT-001)
            ],
        ),
        Story(
            "IT-006",
            "Pre-reset response observed after reset deassertion",
            "DUT-RST-001/002/004/005/007, INV-005/006, MUT-004, OD-005",
            [
                C(1, edge(1, 0, 0)),
                C(2, edge(2, 0, 0, 1, 0), acc(2, 0, 1, 0x60, OP_WRITE, 0x66)),
                C(3, edge(3, 1, 1), rst(3, True), rst=1),
                CHECK(it006_mid, "mid-story: flush, epoch advance, reservation"),
                C(4, edge(4, 0, 0), rst(4, False)),  # DUT-RST-007 release
                # Stale response injected after release (DUT-RST-002
                # violation); ID 1 was not reused before observation (MUT-004).
                C(5, edge(5, 0, 0), comp(5, 1, 1)),
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_story(story: Story) -> None:
    oracle = LifecycleOracle()
    n_completions = 0
    for item in story.script:
        if item[0] == "cycle":
            _, cycle, rst_v, ready, events = item
            oracle.tick(cycle, rst_v, ready)
            for ev in events:
                if isinstance(ev, CompletedResponse):
                    n_completions += 1
                oracle.process(ev)
        else:
            _, fn, label = item
            try:
                fn(oracle)
            except AssertionError as exc:
                raise AssertionError(f"[{story.trace_id} {label}] {exc}") from exc
    oracle.finish()
    # INV-015: exactly one oracle result per completed-response observation.
    assert len(oracle.results) == n_completions, (
        f"[{story.trace_id}] INV-015: {n_completions} completions but "
        f"{len(oracle.results)} oracle results"
    )
    try:
        FINAL_CHECKS[story.trace_id](oracle)
    except AssertionError as exc:
        raise AssertionError(f"[{story.trace_id} final verdicts] {exc}") from exc


FINAL_CHECKS = {
    "LT-001": lt001_final,
    "LT-005": lt005_final,
    "LT-007": lt007_final,
    "LT-009": lt009_final,
    "LT-012": lt012_final,
    "IT-001": it001_final,
    "IT-002": it002_final,
    "IT-006": it006_final,
}


def check_guard() -> None:
    """Referee self-check: the intra-cycle ordering contract is enforced, not
    conventional.  A misordered stream must raise -- never silently mis-score.
    (Finding, 2026-08-31: EdgeSample position was load-bearing and
    unenforced; a completion-first fixture silently skipped the DUT-LC-012
    threshold check on exactly the completing edge that requirement names.)
    Committed negative coverage for the guard -- without it the guard is
    unproven code (same posture the HoldViolationRecord paths had)."""

    # (1) EdgeSample not the first event of its cycle -> raise.
    def not_first() -> None:
        o = LifecycleOracle()
        o.tick(1, 0, 1)
        o.process(AcceptedRequest(1, 0, 1, 0, OP_WRITE, 0, 1))
        o.process(EdgeSample(1, (False, False), (False, False)))

    _guard_raises(not_first, "first event")

    # (2) duplicate EdgeSample within one cycle -> raise.
    def duplicate() -> None:
        o = LifecycleOracle()
        o.tick(1, 0, 1)
        o.process(EdgeSample(1, (False, False), (False, False)))
        o.process(EdgeSample(1, (False, False), (False, False)))

    _guard_raises(duplicate, "first event")

    # (3) backwards cycle -> raise.
    def backwards() -> None:
        o = LifecycleOracle()
        o.tick(1, 0, 1)
        o.process(EdgeSample(1, (False, False), (False, False)))
        o.process(EdgeSample(0, (False, False), (False, False)))

    _guard_raises(backwards, "backwards")


def _guard_raises(fn, needle: str) -> None:
    try:
        fn()
    except ValueError as exc:
        assert needle in str(exc), f"guard raised with wrong reason: {exc}"
        return
    raise AssertionError(f"guard did not raise (expected: {needle})")


def main() -> int:
    stories = build_stories()
    failures = []
    for story in stories:
        try:
            run_story(story)
            print(f"{story.trace_id}: PASS")
        except (AssertionError, ValueError) as exc:
            failures.append(str(exc))
            print(f"{story.trace_id}: FAIL -- {exc}")
    try:
        check_guard()
        print("guard: PASS (backwards cycle / non-first / duplicate EdgeSample all raise)")
    except AssertionError as exc:
        failures.append(f"guard: {exc}")
        print(f"guard: FAIL -- {exc}")
    if failures:
        print(f"\nMILESTONE NOT MET: {len(stories) - len(failures)}/{len(stories)} stories pass")
        return 1
    print(f"\nMILESTONE MET: {len(stories)}/{len(stories)} stories pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
