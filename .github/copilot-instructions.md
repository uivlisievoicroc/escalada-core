# Copilot instructions (escalada-core)

## What this repo is
- Pure domain logic for Escalada contests (no FastAPI/DB/WebSocket). Keep business rules here.
- Main state machine: `escalada_core/contest.py` (`default_state()`, `apply_command()`, `validate_session_and_version()`).

## Domain model & command flow
- State is a plain `dict` with keys like `sessionId`, `boxVersion`, `timerState`, `holdCount` (float; supports 0.1), `lastRegisteredTime`.
- `apply_command(state, cmd)` uses a pure transition internally (deepcopy) but **mutates the input dict** for backward compatibility; prefer consuming the returned `CommandOutcome` when adding new callers.
- `CommandOutcome` has `state` (updated dict), `cmd_payload` (enriched command), `snapshot_required` (bool for persistence).
- Competitors are dicts with Romanian key `nume`; core normalizes via `_normalize_competitors()` and uses `marked` to track completion. Preserves `club` field if present.

## Validation conventions
- Pydantic v2 schemas live in `escalada_core/validation.py` (`ValidatedCmd`).
- Fields have strict bounds: `delta` (-10 to +10), `score` (0-100), `registeredTime` (0-3600), `holdsCount` (0-100).
- Timer presets are normalized/padded (e.g. `"5:00" → "05:00"`) in validation using `normalize_timer_preset()`.
- Competitor names are sanitized with `InputSanitizer.sanitize_competitor_name()` (max 255 chars, strips control chars).
- Stale-command prevention: `sessionId` + `boxVersion` validation via `validate_session_and_version()` (returns `ValidationError` on mismatch).

## State transitions
- `INIT_ROUTE`: sets `initiated=True`, `currentClimber`, `holdsCount`, normalizes competitors, increments `boxVersion`.
- `PROGRESS_UPDATE`: adjusts `holdCount` (clamped 0 to `holdsCount`), supports half-holds (0.5).
- `SUBMIT_SCORE`: marks competitor as done, resets timer, advances to next competitor or route end.
- `START_TIMER/STOP_TIMER/RESUME_TIMER`: manage `timerState` (idle/running/paused), capture `lastRegisteredTime`.
- Timer countdown: `remaining` calculated from `timerPresetSec - elapsed`; negative when overtime.

## Dev workflow
- Install without root package: `poetry install --with dev --no-root` (avoids package conflicts when used as editable dep).
- Tests: `poetry run pytest -q` (see `tests/test_core_contest.py` for state machine examples).
- Depends on `pydantic>=2.0` only; no FastAPI/DB libs.
