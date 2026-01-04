# Copilot instructions (escalada-core)

## What this repo is
- Pure domain logic for Escalada contests (no FastAPI/DB/WebSocket). Keep business rules here.
- Main state machine: `escalada_core/contest.py` (`default_state()`, `apply_command()`, `validate_session_and_version()`).

## Domain model & command flow
- State is a plain `dict` with keys like `sessionId`, `boxVersion`, `timerState`, `holdCount` (float; supports 0.1), `lastRegisteredTime`.
- `apply_command(state, cmd)` uses a pure transition internally (deepcopy) but **mutates the input dict** for backward compatibility; prefer consuming the returned `CommandOutcome` when adding new callers.
- Competitors are dicts with Romanian key `nume`; core normalizes via `_normalize_competitors()` and uses `marked` to track completion.

## Validation conventions
- Pydantic v2 schemas live in `escalada_core/validation.py` (`ValidatedCmd`).
- Timer presets are normalized/padded (e.g. `"5:00" → "05:00"`) in validation.
- Stale-command prevention: `sessionId` + `boxVersion` validation is implemented in core and enforced by the API.

## Dev workflow
- Tests: `poetry run pytest -q` (see `tests/test_core_contest.py`).
- Install for dev (no root): `poetry install --with dev --no-root`.
