# Copilot Instructions for Escalada 3 repos

## Architecture Overview
- **escalada-core**: Pure Python logic for climbing competitions (state transitions, validation). No external dependencies (no FastAPI, DB, etc). See [escalada-core/README.md](./README.md).
- **escalada-api**: FastAPI backend with WebSocket support, JSON persistence, and admin/backup endpoints. Integrates escalada-core as a dependency. See [escalada-api/README.md](../escalada-api/README.md).
- **escalada-ui**: React + Vite frontend for real-time competition management. See [escalada-ui/README.md](../escalada-ui/README.md).

## Developer Workflows
- **Backend (API):**
  - Install core: `poetry run pip install -e ../escalada-core`
  - Run dev server: `poetry run uvicorn escalada.main:app --reload --host 0.0.0.0 --port 8000`
  - Run tests: `poetry run pytest tests -q`
  - Format: `pre-commit run --all-files` (uses Black + isort)
- **Core:**
  - Install deps: `poetry install --with dev --no-root`
  - Run tests: `poetry run pytest -q`
- **Frontend (UI):**
  - Start dev: `npm run dev`
  - Run tests: `npm test -- --run`

## Project Conventions & Patterns
- **escalada-core** is dependency-free and pure logic. All business rules and state machines live here.
- **escalada-api** imports escalada-core for all domain logic. API endpoints are in `escalada/api/`.
- **Backups/restore**: Admin endpoints for backup/restore in API (`/api/admin/backup/*`, `/api/admin/restore`).
- **CI**: Installs escalada-core from a separate repo. If private, set `ESCALADA_CORE_TOKEN` in GitHub Actions.
- **Formatting**: Python code is auto-formatted (Black, isort) via pre-commit hooks.

## Integration Points
- **API <-> Core**: All business logic flows through escalada-core. Do not duplicate domain logic in API.
- **API <-> Storage**: JSON storage only.
- **API <-> UI**: Communicates via REST and WebSocket endpoints. See routers and main app for entrypoints.

## Examples
- Add a new competition rule: implement in escalada-core, then expose via API if needed.
- Add a new API endpoint: create in `escalada/api/routers/`, use core logic, add DB/service layer if needed.
- Add a new UI feature: integrate with API endpoints, follow React component structure in `src/components/`.

## References
- [escalada-core/README.md](./README.md)
- [escalada-api/README.md](../escalada-api/README.md)
- [escalada-ui/README.md](../escalada-ui/README.md)

---
For unclear or missing conventions, check the respective README files or ask for clarification.
