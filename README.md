# Escalada Core

Pachetul `escalada-core` conține logica pură (CORE) pentru Escalada:
- tranziții de state pentru comenzi (ex. INIT_ROUTE/PROGRESS_UPDATE/SUBMIT_SCORE)
- validare input (Pydantic)

Nu depinde de FastAPI, WebSocket sau SQLAlchemy.

## Dev

```bash
poetry install
poetry run pytest -q
```
