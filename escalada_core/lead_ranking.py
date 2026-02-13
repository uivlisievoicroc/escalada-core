"""Lead finals ranking engine (IFSC-style comparator + manual tie-break workflow).

Single source of truth for Lead ranking across API/UI/export:
- Comparator: Top > non-Top; then hold; then plus.
- Podium ties (1..podium_places) require explicit resolution workflow.
- Non-podium ties can stay shared unless explicitly broken.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from dataclasses import replace
from typing import Literal, Protocol, Sequence


TieStage = Literal["previous_rounds", "time"]
TieChoice = Literal["yes", "no", "pending"]


@dataclass(frozen=True)
class Athlete:
    id: str
    name: str


@dataclass(frozen=True)
class LeadResult:
    topped: bool
    hold: int
    plus: bool = False
    time_seconds: float | None = None


@dataclass(frozen=True)
class TieContext:
    round_name: str
    stage: TieStage
    rank_start: int
    rank_end: int
    affects_podium: bool
    fingerprint: str
    athletes: tuple[Athlete, ...]
    performance: LeadResult
    lineage_key: str | None = None


@dataclass(frozen=True)
class TieBreakDecision:
    # yes/no/pending for the current stage.
    choice: TieChoice
    # Required for stage=previous_rounds when choice=yes.
    previous_ranks_by_athlete: dict[str, int] | None = None


class TieBreakResolver(Protocol):
    def resolve(self, group: Sequence[Athlete], context: TieContext) -> TieBreakDecision | None:
        ...


@dataclass(frozen=True)
class RankingRow:
    athlete_id: str
    athlete_name: str
    rank: int
    topped: bool
    hold: int
    plus: bool
    time_seconds: float | None
    tb_prev: bool
    tb_time: bool
    score_hint: float


@dataclass(frozen=True)
class TieEvent:
    fingerprint: str
    stage: TieStage
    rank_start: int
    rank_end: int
    affects_podium: bool
    members: tuple[RankingRow, ...]
    status: Literal["pending", "resolved", "error"]
    detail: str | None = None
    lineage_key: str | None = None
    known_prev_ranks_by_athlete: dict[str, int] | None = None
    missing_prev_rounds_athlete_ids: tuple[str, ...] | None = None
    requires_prev_rounds_input: bool = False


@dataclass(frozen=True)
class RankingResult:
    rows: tuple[RankingRow, ...]
    tie_events: tuple[TieEvent, ...]
    is_resolved: bool
    has_pending_podium_ties: bool
    errors: tuple[str, ...]


@dataclass
class _ResolvedItem:
    athlete: Athlete
    result: LeadResult
    tb_prev: bool = False
    tb_time: bool = False


@dataclass
class _TieChunk:
    items: list[_ResolvedItem]


def _result_sort_key(result: LeadResult) -> tuple[int, int, int]:
    return (
        1 if result.topped else 0,
        int(result.hold),
        1 if (result.plus and not result.topped) else 0,
    )


def _score_hint(result: LeadResult) -> float:
    # UI helper: keep a numeric value that matches current hold+plus display conventions.
    if result.topped:
        return float(result.hold)
    return float(result.hold) + (0.1 if result.plus else 0.0)


def _stable_athlete_sort_key(item: _ResolvedItem) -> tuple[str, str]:
    return (item.athlete.name.lower(), item.athlete.id)


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"tb3:{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"


def _build_tie_fingerprint(
    *,
    round_name: str,
    stage: TieStage,
    rank_start: int,
    rank_end: int,
    affects_podium: bool,
    members: Sequence[_ResolvedItem],
) -> str:
    payload = {
        "round": round_name,
        "stage": stage,
        "rank_start": rank_start,
        "rank_end": rank_end,
        "affects_podium": affects_podium,
        "members": sorted(
            [
                {
                    "id": item.athlete.id,
                    "name": item.athlete.name,
                    "topped": bool(item.result.topped),
                    "hold": int(item.result.hold),
                    "plus": bool(item.result.plus),
                    "time": item.result.time_seconds,
                }
                for item in members
            ],
            key=lambda it: (str(it["name"]).lower(), str(it["id"])),
        ),
    }
    return _fingerprint(payload)


def _build_lineage_key(*, round_name: str, result: LeadResult) -> str:
    payload = {
        "round": round_name,
        "context": "overall",
        "performance": {
            "topped": bool(result.topped),
            "hold": int(result.hold),
            "plus": bool(result.plus and not result.topped),
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"tb-lineage:{hashlib.sha1(raw.encode('utf-8')).hexdigest()}"


def _default_pending_decision() -> TieBreakDecision:
    return TieBreakDecision(choice="pending", previous_ranks_by_athlete=None)


def _resolve_with_fallback(
    resolver: TieBreakResolver | None,
    group: Sequence[_ResolvedItem],
    context: TieContext,
) -> TieBreakDecision:
    if resolver is None:
        return _default_pending_decision()
    try:
        decision = resolver.resolve([item.athlete for item in group], context)
    except Exception:
        return _default_pending_decision()
    if decision is None:
        return _default_pending_decision()
    if decision.choice not in {"yes", "no", "pending"}:
        return _default_pending_decision()
    return decision


def _validate_previous_ranks(
    members: Sequence[_ResolvedItem],
    ranks_by_athlete: dict[str, int] | None,
) -> tuple[bool, str | None]:
    if not isinstance(ranks_by_athlete, dict) or not ranks_by_athlete:
        return False, "missing_previous_rounds_ranks"
    expected_ids = {item.athlete.id for item in members}
    for athlete_id, rank_val in ranks_by_athlete.items():
        if athlete_id not in expected_ids:
            return False, f"invalid_previous_rounds_rank_member:{athlete_id}"
        if not isinstance(rank_val, int) or isinstance(rank_val, bool) or rank_val <= 0:
            return False, f"invalid_previous_rounds_rank:{athlete_id}"
    return True, None


def _to_ranking_row(item: _ResolvedItem, rank: int) -> RankingRow:
    return RankingRow(
        athlete_id=item.athlete.id,
        athlete_name=item.athlete.name,
        rank=rank,
        topped=bool(item.result.topped),
        hold=int(item.result.hold),
        plus=bool(item.result.plus),
        time_seconds=item.result.time_seconds,
        tb_prev=bool(item.tb_prev),
        tb_time=bool(item.tb_time),
        score_hint=_score_hint(item.result),
    )


def _items_equal_time(a: _ResolvedItem, b: _ResolvedItem) -> bool:
    return a.result.time_seconds == b.result.time_seconds


def _partition_by_prev_ranks(
    members: Sequence[_ResolvedItem],
    ranks_by_athlete: dict[str, int],
) -> list[list[_ResolvedItem]]:
    grouped: dict[int, list[_ResolvedItem]] = {}
    for item in members:
        rank_val = ranks_by_athlete[item.athlete.id]
        grouped.setdefault(rank_val, []).append(item)
    partitions: list[list[_ResolvedItem]] = []
    for rank_val in sorted(grouped.keys()):
        # Keep deterministic member ordering inside same previous-round rank.
        partitions.append(sorted(grouped[rank_val], key=_stable_athlete_sort_key))
    return partitions


def _partition_by_time(members: Sequence[_ResolvedItem]) -> list[list[_ResolvedItem]]:
    ordered = sorted(
        members,
        key=lambda item: (
            float(item.result.time_seconds or math.inf),
            item.athlete.name.lower(),
            item.athlete.id,
        ),
    )
    partitions: list[list[_ResolvedItem]] = []
    i = 0
    while i < len(ordered):
        current = ordered[i]
        chunk = [current]
        j = i + 1
        while j < len(ordered) and _items_equal_time(ordered[j], current):
            chunk.append(ordered[j])
            j += 1
        partitions.append(chunk)
        i = j
    return partitions


def _resolve_time_stage(
    *,
    members: Sequence[_ResolvedItem],
    rank_start: int,
    podium_places: int,
    round_name: str,
    resolver: TieBreakResolver | None,
    tie_events: list[TieEvent],
    errors: list[str],
) -> tuple[list[_TieChunk], bool]:
    affects_podium = rank_start <= podium_places
    rank_end = rank_start + len(members) - 1
    fp = _build_tie_fingerprint(
        round_name=round_name,
        stage="time",
        rank_start=rank_start,
        rank_end=rank_end,
        affects_podium=affects_podium,
        members=members,
    )
    ctx = TieContext(
        round_name=round_name,
        stage="time",
        rank_start=rank_start,
        rank_end=rank_end,
        affects_podium=affects_podium,
        fingerprint=fp,
        athletes=tuple(item.athlete for item in members),
        performance=members[0].result,
    )
    decision = _resolve_with_fallback(resolver, members, ctx)
    if decision.choice == "pending":
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="time",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=affects_podium,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="pending",
                detail="time_tiebreak_pending",
            )
        )
        return [_TieChunk(items=list(members))], not affects_podium

    if decision.choice == "no":
        if affects_podium:
            errors.append(f"podium_time_tiebreak_keep_tied_not_allowed:{fp}")
            tie_events.append(
                TieEvent(
                    fingerprint=fp,
                    stage="time",
                    rank_start=rank_start,
                    rank_end=rank_end,
                    affects_podium=True,
                    members=tuple(_to_ranking_row(item, rank_start) for item in members),
                    status="error",
                    detail="podium_keep_tied_not_allowed",
                )
            )
            return [_TieChunk(items=list(members))], False
        return [_TieChunk(items=list(members))], True

    # decision.choice == "yes"
    missing_times = [
        item.athlete.id
        for item in members
        if item.result.time_seconds is None or not math.isfinite(float(item.result.time_seconds))
    ]
    if missing_times:
        errors.append(f"time_tiebreak_missing_times:{fp}")
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="time",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=affects_podium,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="error",
                detail="missing_time_seconds",
            )
        )
        return [_TieChunk(items=list(members))], False if affects_podium else True

    partitions = _partition_by_time(members)
    # Mark all athletes touched by time tiebreak attempt.
    for part in partitions:
        for item in part:
            item.tb_time = True
    has_unresolved = any(len(part) > 1 for part in partitions)
    if has_unresolved and affects_podium:
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="time",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=True,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="error",
                detail="identical_time_keeps_podium_tie",
            )
        )
    chunks = [_TieChunk(items=list(part)) for part in partitions]
    return chunks, not (has_unresolved and affects_podium)


def _resolve_group(
    *,
    members: Sequence[_ResolvedItem],
    rank_start: int,
    podium_places: int,
    round_name: str,
    resolver: TieBreakResolver | None,
    tie_events: list[TieEvent],
    errors: list[str],
) -> tuple[list[_TieChunk], bool]:
    affects_podium = rank_start <= podium_places
    if not affects_podium:
        # Outside podium we keep shared ranks by default.
        return [_TieChunk(items=list(members))], True
    rank_end = rank_start + len(members) - 1
    fp = _build_tie_fingerprint(
        round_name=round_name,
        stage="previous_rounds",
        rank_start=rank_start,
        rank_end=rank_end,
        affects_podium=affects_podium,
        members=members,
    )
    lineage_key = _build_lineage_key(round_name=round_name, result=members[0].result)
    ctx = TieContext(
        round_name=round_name,
        stage="previous_rounds",
        rank_start=rank_start,
        rank_end=rank_end,
        affects_podium=affects_podium,
        fingerprint=fp,
        lineage_key=lineage_key,
        athletes=tuple(item.athlete for item in members),
        performance=members[0].result,
    )
    decision = _resolve_with_fallback(resolver, members, ctx)

    if decision.choice == "pending":
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="previous_rounds",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=affects_podium,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="pending",
                detail="previous_rounds_pending",
                lineage_key=lineage_key,
                known_prev_ranks_by_athlete={},
                missing_prev_rounds_athlete_ids=tuple(sorted(item.athlete.id for item in members)),
                requires_prev_rounds_input=True,
            )
        )
        return [_TieChunk(items=list(members))], not affects_podium

    if decision.choice == "no":
        return _resolve_time_stage(
            members=members,
            rank_start=rank_start,
            podium_places=podium_places,
            round_name=round_name,
            resolver=resolver,
            tie_events=tie_events,
            errors=errors,
        )

    # decision.choice == "yes"
    ok, reason = _validate_previous_ranks(members, decision.previous_ranks_by_athlete)
    if not ok:
        errors.append(f"invalid_previous_rounds_decision:{fp}:{reason}")
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="previous_rounds",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=affects_podium,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="error",
                detail=reason,
                lineage_key=lineage_key,
                known_prev_ranks_by_athlete={},
                missing_prev_rounds_athlete_ids=tuple(sorted(item.athlete.id for item in members)),
                requires_prev_rounds_input=True,
            )
        )
        return [_TieChunk(items=list(members))], False if affects_podium else True

    ranks_by_athlete = decision.previous_ranks_by_athlete or {}
    known_members: list[_ResolvedItem] = []
    missing_members: list[_ResolvedItem] = []
    for item in members:
        if item.athlete.id in ranks_by_athlete:
            known_members.append(item)
        else:
            missing_members.append(item)
    if not known_members:
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="previous_rounds",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=affects_podium,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="pending",
                detail="previous_rounds_missing_members",
                lineage_key=lineage_key,
                known_prev_ranks_by_athlete={},
                missing_prev_rounds_athlete_ids=tuple(
                    sorted(item.athlete.id for item in missing_members)
                ),
                requires_prev_rounds_input=True,
            )
        )
        return [_TieChunk(items=list(members))], False

    partitions = _partition_by_prev_ranks(known_members, ranks_by_athlete)
    chunks: list[_TieChunk] = []
    all_resolved = True
    consumed = 0
    for part_idx, part in enumerate(partitions):
        part_rank_start = rank_start + consumed
        consumed += len(part)
        if len(part) == 1:
            # Keep badge semantics simple and deterministic: only the best prev-ranked
            # athlete in the tie group gets TB Prev.
            if part_idx == 0:
                part[0].tb_prev = True
            chunks.append(_TieChunk(items=list(part)))
            continue
        time_chunks, resolved = _resolve_time_stage(
            members=part,
            rank_start=part_rank_start,
            podium_places=podium_places,
            round_name=round_name,
            resolver=resolver,
            tie_events=tie_events,
            errors=errors,
        )
        chunks.extend(time_chunks)
        all_resolved = all_resolved and resolved
    if missing_members:
        missing_members_sorted = sorted(missing_members, key=_stable_athlete_sort_key)
        chunks.append(_TieChunk(items=list(missing_members_sorted)))
        tie_events.append(
            TieEvent(
                fingerprint=fp,
                stage="previous_rounds",
                rank_start=rank_start,
                rank_end=rank_end,
                affects_podium=affects_podium,
                members=tuple(_to_ranking_row(item, rank_start) for item in members),
                status="pending",
                detail="previous_rounds_missing_members",
                lineage_key=lineage_key,
                known_prev_ranks_by_athlete={
                    item.athlete.id: int(ranks_by_athlete[item.athlete.id])
                    for item in known_members
                },
                missing_prev_rounds_athlete_ids=tuple(
                    sorted(item.athlete.id for item in missing_members_sorted)
                ),
                requires_prev_rounds_input=True,
            )
        )
        return chunks, False
    return chunks, all_resolved


def compute_lead_ranking(
    athletes: Sequence[Athlete],
    results: dict[str, LeadResult],
    tie_break_resolver: TieBreakResolver | None,
    podium_places: int = 3,
    *,
    round_name: str = "Final",
) -> RankingResult:
    """
    Compute final Lead ranking with explicit tie-break workflow support.

    Args:
      athletes: ordered athlete list.
      results: mapping athlete_id -> LeadResult.
      tie_break_resolver: resolver used for manual previous-round/time decisions.
      podium_places: podium threshold (default 3).
      round_name: used in fingerprints/context.
    """
    podium_places = max(1, int(podium_places or 3))
    resolved_items: list[_ResolvedItem] = []
    for athlete in athletes:
        if athlete.id not in results:
            continue
        resolved_items.append(_ResolvedItem(athlete=athlete, result=results[athlete.id]))

    # Base ordering by Lead performance comparator + stable name/id fallback.
    resolved_items.sort(
        key=lambda item: (
            -_result_sort_key(item.result)[0],
            -_result_sort_key(item.result)[1],
            -_result_sort_key(item.result)[2],
            item.athlete.name.lower(),
            item.athlete.id,
        )
    )

    # Build base tie groups by identical performance.
    tie_events: list[TieEvent] = []
    errors: list[str] = []
    final_chunks: list[_TieChunk] = []
    i = 0
    while i < len(resolved_items):
        current = resolved_items[i]
        current_key = _result_sort_key(current.result)
        j = i + 1
        while j < len(resolved_items) and _result_sort_key(resolved_items[j].result) == current_key:
            j += 1
        group = resolved_items[i:j]
        rank_start = len([x for ch in final_chunks for x in ch.items]) + 1
        if len(group) <= 1:
            final_chunks.append(_TieChunk(items=list(group)))
        else:
            chunks, _ = _resolve_group(
                members=group,
                rank_start=rank_start,
                podium_places=podium_places,
                round_name=round_name,
                resolver=tie_break_resolver,
                tie_events=tie_events,
                errors=errors,
            )
            final_chunks.extend(chunks)
        i = j

    rows: list[RankingRow] = []
    pos = 1
    has_pending_podium = False
    for chunk in final_chunks:
        rank = pos
        for item in sorted(chunk.items, key=_stable_athlete_sort_key):
            rows.append(_to_ranking_row(item, rank))
        if len(chunk.items) > 1 and rank <= podium_places:
            has_pending_podium = True
        pos += len(chunk.items)

    # Preserve final order by rank then deterministic athlete sort.
    rows.sort(key=lambda row: (row.rank, row.athlete_name.lower(), row.athlete_id))

    # Safety: keep tie-break impact constrained to podium only.
    # - If a full performance group falls below podium: collapse all to shared rank.
    # - If a group straddles podium boundary (e.g. ranks 3,4,5): keep podium part, collapse only tail > podium.
    by_perf = sorted(
        rows,
        key=lambda row: (
            -int(bool(row.topped)),
            -int(row.hold),
            -int(bool(row.plus and not row.topped)),
            row.athlete_name.lower(),
            row.athlete_id,
        ),
    )
    collapsed: dict[str, int] = {}
    i = 0
    while i < len(by_perf):
        current = by_perf[i]
        key = (
            int(bool(current.topped)),
            int(current.hold),
            int(bool(current.plus and not current.topped)),
        )
        j = i + 1
        while j < len(by_perf):
            other = by_perf[j]
            other_key = (
                int(bool(other.topped)),
                int(other.hold),
                int(bool(other.plus and not other.topped)),
            )
            if other_key != key:
                break
            j += 1
        group = by_perf[i:j]
        if len(group) > 1:
            min_rank = min(r.rank for r in group)
            max_rank = max(r.rank for r in group)
            if min_rank > podium_places:
                for r in group:
                    collapsed[r.athlete_id] = min_rank
            elif max_rank > podium_places:
                tail = [r for r in group if r.rank > podium_places]
                if tail:
                    shared_tail_rank = min(r.rank for r in tail)
                    for r in tail:
                        collapsed[r.athlete_id] = shared_tail_rank
        i = j
    if collapsed:
        rows = [
            replace(row, rank=collapsed.get(row.athlete_id, row.rank))
            for row in rows
        ]
        rows.sort(key=lambda row: (row.rank, row.athlete_name.lower(), row.athlete_id))

    # Pending/error podium events also mark unresolved status.
    for event in tie_events:
        if event.affects_podium and event.status in {"pending", "error"}:
            has_pending_podium = True
            break

    return RankingResult(
        rows=tuple(rows),
        tie_events=tuple(tie_events),
        is_resolved=not has_pending_podium,
        has_pending_podium_ties=has_pending_podium,
        errors=tuple(errors),
    )
