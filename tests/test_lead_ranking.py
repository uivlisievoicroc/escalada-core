from __future__ import annotations

from dataclasses import dataclass

from escalada_core import (
    Athlete,
    LeadResult,
    TieBreakDecision,
    TieContext,
    compute_lead_ranking,
)


@dataclass
class _MapResolver:
    decisions: dict[tuple[str, tuple[str, ...], int], TieBreakDecision]

    def resolve(self, group, context: TieContext):
        key = (
            context.stage,
            tuple(sorted(a.id for a in group)),
            context.rank_start,
        )
        return self.decisions.get(key, TieBreakDecision(choice="pending"))


def _rows_by_id(result):
    return {row.athlete_id: row for row in result.rows}


def test_compute_lead_ranking_no_ties():
    athletes = [
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
    ]
    results = {
        "A": LeadResult(topped=True, hold=40, plus=False, time_seconds=90),
        "B": LeadResult(topped=False, hold=39, plus=True, time_seconds=100),
        "C": LeadResult(topped=False, hold=39, plus=False, time_seconds=80),
    }
    out = compute_lead_ranking(athletes, results, tie_break_resolver=None)
    assert out.is_resolved is True
    assert out.tie_events == ()
    assert [row.athlete_id for row in out.rows] == ["A", "B", "C"]
    assert [row.rank for row in out.rows] == [1, 2, 3]


def test_tie_outside_podium_can_stay_shared_rank():
    athletes = [
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
        Athlete(id="D", name="Dan"),
        Athlete(id="E", name="Ema"),
    ]
    results = {
        "A": LeadResult(topped=True, hold=40, plus=False, time_seconds=100),
        "B": LeadResult(topped=False, hold=39, plus=True, time_seconds=101),
        "C": LeadResult(topped=False, hold=38, plus=True, time_seconds=102),
        "D": LeadResult(topped=False, hold=30, plus=False, time_seconds=103),
        "E": LeadResult(topped=False, hold=30, plus=False, time_seconds=104),
    }
    out = compute_lead_ranking(athletes, results, tie_break_resolver=None, podium_places=3)
    by_id = _rows_by_id(out)
    assert out.is_resolved is True
    assert by_id["D"].rank == 4
    assert by_id["E"].rank == 4
    assert out.tie_events == ()


def test_two_way_podium_tie_resolved_by_previous_rounds():
    athletes = [Athlete(id="A", name="Ana"), Athlete(id="B", name="Bob")]
    results = {
        "A": LeadResult(topped=False, hold=30, plus=False, time_seconds=140),
        "B": LeadResult(topped=False, hold=30, plus=False, time_seconds=100),
    }
    resolver = _MapResolver(
        decisions={
            ("previous_rounds", ("A", "B"), 1): TieBreakDecision(
                choice="yes",
                previous_ranks_by_athlete={"A": 1, "B": 2},
            )
        }
    )
    out = compute_lead_ranking(athletes, results, tie_break_resolver=resolver)
    by_id = _rows_by_id(out)
    assert out.is_resolved is True
    assert by_id["A"].rank == 1
    assert by_id["B"].rank == 2
    assert by_id["A"].tb_prev is True


def test_three_way_podium_tie_resolved_by_full_previous_rounds_order():
    athletes = [
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
    ]
    results = {
        "A": LeadResult(topped=False, hold=30, plus=False, time_seconds=130),
        "B": LeadResult(topped=False, hold=30, plus=False, time_seconds=120),
        "C": LeadResult(topped=False, hold=30, plus=False, time_seconds=110),
    }
    resolver = _MapResolver(
        decisions={
            ("previous_rounds", ("A", "B", "C"), 1): TieBreakDecision(
                choice="yes",
                previous_ranks_by_athlete={"C": 1, "A": 2, "B": 3},
            )
        }
    )
    out = compute_lead_ranking(athletes, results, tie_break_resolver=resolver)
    assert [row.athlete_id for row in out.rows] == ["C", "A", "B"]
    assert [row.rank for row in out.rows] == [1, 2, 3]


def test_three_way_partial_previous_rounds_then_time_for_remaining_subgroup():
    athletes = [
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
    ]
    results = {
        "A": LeadResult(topped=False, hold=30, plus=False, time_seconds=105),
        "B": LeadResult(topped=False, hold=30, plus=False, time_seconds=130),
        "C": LeadResult(topped=False, hold=30, plus=False, time_seconds=150),
    }
    resolver = _MapResolver(
        decisions={
            ("previous_rounds", ("A", "B", "C"), 1): TieBreakDecision(
                choice="yes",
                previous_ranks_by_athlete={"C": 1, "A": 2, "B": 2},
            ),
            ("time", ("A", "B"), 2): TieBreakDecision(choice="yes"),
        }
    )
    out = compute_lead_ranking(athletes, results, tie_break_resolver=resolver)
    by_id = _rows_by_id(out)
    assert out.is_resolved is True
    assert [row.athlete_id for row in out.rows] == ["C", "A", "B"]
    assert [row.rank for row in out.rows] == [1, 2, 3]
    assert by_id["C"].tb_prev is True
    assert by_id["A"].tb_time is True
    assert by_id["B"].tb_time is True


def test_partial_previous_rounds_input_keeps_existing_split_and_only_new_member_pending():
    athletes = [
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
    ]
    results = {
        "A": LeadResult(topped=False, hold=30, plus=False, time_seconds=105),
        "B": LeadResult(topped=False, hold=30, plus=False, time_seconds=130),
        "C": LeadResult(topped=False, hold=30, plus=False, time_seconds=140),
    }
    resolver = _MapResolver(
        decisions={
            ("previous_rounds", ("A", "B", "C"), 1): TieBreakDecision(
                choice="yes",
                previous_ranks_by_athlete={"A": 1, "B": 2},
            )
        }
    )
    out = compute_lead_ranking(athletes, results, tie_break_resolver=resolver)
    by_id = _rows_by_id(out)
    assert by_id["A"].rank == 1
    assert by_id["B"].rank == 2
    assert by_id["C"].rank == 3
    assert out.is_resolved is False
    assert out.has_pending_podium_ties is True
    pending = [ev for ev in out.tie_events if ev.stage == "previous_rounds" and ev.status == "pending"]
    assert pending
    event = pending[0]
    assert event.requires_prev_rounds_input is True
    assert event.known_prev_ranks_by_athlete == {"A": 1, "B": 2}
    assert event.missing_prev_rounds_athlete_ids == ("C",)


def test_inconsistent_admin_input_is_reported_and_podium_remains_unresolved():
    athletes = [Athlete(id="A", name="Ana"), Athlete(id="B", name="Bob")]
    results = {
        "A": LeadResult(topped=False, hold=30, plus=False, time_seconds=90),
        "B": LeadResult(topped=False, hold=30, plus=False, time_seconds=100),
    }
    resolver = _MapResolver(
        decisions={
            ("previous_rounds", ("A", "B"), 1): TieBreakDecision(
                choice="yes",
                previous_ranks_by_athlete={"A": 1},
            )
        }
    )
    out = compute_lead_ranking(athletes, results, tie_break_resolver=resolver)
    assert out.is_resolved is False
    assert out.has_pending_podium_ties is True
    assert out.errors == ()
    assert out.rows[0].rank == 1
    assert out.rows[1].rank == 2
    pending = [ev for ev in out.tie_events if ev.stage == "previous_rounds" and ev.status == "pending"]
    assert pending
    assert pending[0].missing_prev_rounds_athlete_ids == ("B",)


def test_previous_podium_tiebreak_does_not_keep_split_below_podium():
    athletes = [
        Athlete(id="X", name="Xena"),
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
        Athlete(id="D", name="Dan"),
    ]
    results = {
        "X": LeadResult(topped=True, hold=40, plus=False, time_seconds=80),
        "A": LeadResult(topped=False, hold=30, plus=False, time_seconds=100),
        "B": LeadResult(topped=False, hold=30, plus=False, time_seconds=120),
        "C": LeadResult(topped=False, hold=35, plus=False, time_seconds=90),
        "D": LeadResult(topped=False, hold=34, plus=False, time_seconds=95),
    }

    class _AlwaysSplitResolver:
        def resolve(self, group, context: TieContext):
            if context.stage == "previous_rounds":
                return TieBreakDecision(
                    choice="yes",
                    previous_ranks_by_athlete={ath.id: idx + 1 for idx, ath in enumerate(group)},
                )
            return TieBreakDecision(choice="yes")

    out = compute_lead_ranking(athletes, results, tie_break_resolver=_AlwaysSplitResolver())
    by_id = _rows_by_id(out)
    assert by_id["A"].rank == 4
    assert by_id["B"].rank == 4


def test_only_tail_below_podium_collapses_when_group_straddles_boundary():
    athletes = [
        Athlete(id="A", name="Ana"),
        Athlete(id="B", name="Bob"),
        Athlete(id="C", name="Cara"),
        Athlete(id="D", name="Dan"),
        Athlete(id="E", name="Ema"),
    ]
    results = {
        "A": LeadResult(topped=True, hold=40, plus=False, time_seconds=80),
        "B": LeadResult(topped=True, hold=39, plus=False, time_seconds=81),
        # Tied performance group that spans ranks 3..5 after tie-break.
        "C": LeadResult(topped=False, hold=30, plus=False, time_seconds=100),
        "D": LeadResult(topped=False, hold=30, plus=False, time_seconds=110),
        "E": LeadResult(topped=False, hold=30, plus=False, time_seconds=120),
    }

    class _SplitThreeResolver:
        def resolve(self, group, context: TieContext):
            if context.stage == "previous_rounds":
                return TieBreakDecision(
                    choice="yes",
                    previous_ranks_by_athlete={"C": 1, "D": 2, "E": 3},
                )
            return TieBreakDecision(choice="yes")

    out = compute_lead_ranking(athletes, results, tie_break_resolver=_SplitThreeResolver())
    by_id = _rows_by_id(out)
    assert by_id["C"].rank == 3
    assert by_id["D"].rank == 4
    assert by_id["E"].rank == 4
