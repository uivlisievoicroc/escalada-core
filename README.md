# Escalada Core

`escalada-core` conține logica pură a concursurilor Escalada: mașina de state pentru comenzi (INIT_ROUTE/PROGRESS_UPDATE/SUBMIT_SCORE), validare cu Pydantic și utilitare pentru preset-urile de timp. Nu depinde de FastAPI, WebSocket sau SQLAlchemy; toate integrările se fac din repos-ul `escalada-api`.

## Cerințe
- Python 3.11+
- Poetry 2.x

## Instalare și dezvoltare
```bash
poetry install --with dev --no-root
poetry run pytest -q
```

## Exemplu rapid
```python
from escalada_core import apply_command, default_state

state = default_state("session-1")
apply_command(
    state,
    {"type": "INIT_ROUTE", "boxId": 1, "routeIndex": 1, "holdsCount": 4, "competitors": [{"nume": "A"}]},
)
apply_command(state, {"type": "START_TIMER"})
apply_command(state, {"type": "PROGRESS_UPDATE", "delta": 2})
```

## Notițe
- Păstrează logica de business aici; API/UI doar orchestrează.
- Rulează testele înainte de publish sau înainte de a tăia un release în `escalada-api`.
