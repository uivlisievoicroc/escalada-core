# Lead Ranking (Single Engine)

## Source of truth
- Ranking is computed only by `compute_lead_ranking(...)` in `/Users/silviucorciovei/Soft_Escalada/repos/escalada-core/escalada_core/lead_ranking.py`.
- API adapts contest state to Lead results and reuses this engine for live snapshots, public snapshots, save ranking, and official export.
- UI no longer recalculates ranking; it only renders `leadRankingRows` + `leadTieEvents` from snapshot data and sends tie-break commands.

## Lead comparator
- `topped=True` always beats `topped=False`.
- For non-tops: higher `hold` wins.
- At equal hold: `plus=True` wins over `plus=False`.
- Equal on all three fields means a performance tie.

## Tie-break workflow
- Stage 1: `previous_rounds` decision.
- Stage 2 (only for unresolved subgroup): `time`.
- Podium ties (positions `1..3`) cannot stay tied.
- Non-podium ties can remain tied unless admin explicitly resolves.
- Multi-way ties are supported; previous-rounds can partially split a group, then time resolves only remaining subgroup(s).

## Command inputs
- Previous-rounds resolution command accepts:
  - `prevRoundsTiebreakDecision: "yes" | "no"`
  - `prevRoundsTiebreakFingerprint: string`
  - `prevRoundsTiebreakRanksByName: { [name]: positive_int }`
- Legacy `prevRoundsTiebreakOrder` is still accepted and adapted for backward compatibility.

## Validation
- `prevRoundsTiebreakRanksByName` must contain all tie members exactly once with integer ranks `> 0`.
- For time tie-break, all subgroup athletes must have valid `time_seconds`.
- Invalid/inconsistent decisions are surfaced explicitly (`error` tie event and API validation errors), without silent fallback ranking.
