# CODEX PROMPT: Fix tranziții în `escalada-core/escalada_core/contest.py`

## Context
Repo `escalada-core` conține logica pură a concursului (mașina de stări). În `escalada_core/contest.py`, tranzițiile sunt aplicate în `_apply_transition(...)` și expuse prin `apply_command(...)`.

Acest task cere fixuri strict în core (fără FastAPI/UI).

## Obiective
1) `PROGRESS_SCORE`: să nu mai transforme `0` în `1` (bug tipic: fallback cu `or`).
2) `lastRegisteredTime`: tratează defensiv cazul când e `None` sau invalid (string non-numeric, NaN, etc.) fără crash.
3) `SUBMIT_SCORE` cu `idx`: definește contractul și implementează-l clar:
   - fie accepți `idx` corect (și validezi strict),
   - fie respingi explicit (eroare clară / outcome consistent cu proiectul).

## Constrângeri
- Nu schimba semantica `holdCount` (float cu zecimi) — doar bug-ul de coercion `0 → 1`.
- Respectă stilul existent: `state` este `dict`, tranziții pure intern, rezultat/outcome conform pattern-ului curent.
- Nu introduce dependențe noi.

## Pași de implementare

### 1) Elimină fallback-uri de tip “truthy” care strică `0`
În `contest.py`, caută și înlocuiește pattern-uri de tip:
- `x = state.get("holdCount") or 1`
- `idx = cmd.get("idx") or 1`
- `last = state.get("lastRegisteredTime") or ...`

Înlocuiește cu verificări explicite:
- `if x is None: x = default`

Nu folosi `or` când `0` este valoare validă.

### 2) `lastRegisteredTime`: helper de coerciție + utilizare
Adaugă un helper local în `contest.py` (fără dependențe) care:
- primește `None` → returnează `None`
- primește `int` → returnează `int`
- primește `float` finit → returnează `int(value)`
- primește string numeric → parsează la `int`
- altfel → returnează `None`

Apoi, oriunde se compară/folosește `lastRegisteredTime`, convertește prin helper și:
- dacă rezultatul e `None`, evită comparații/actualizări care ar crăpa.

### 3) `SUBMIT_SCORE` cu `idx`: contract recomandat (acceptă și validează)
**Recomandare:** acceptă `idx` ca index competitor **0-based** și validează strict:
- dacă `idx` este prezent:
  - trebuie să fie `int` (sau string numeric convertibil) și `0 <= idx < len(competitors)`;
  - `idx=0` trebuie să rămână 0 (nu folosi fallback cu `or`).
- dacă `idx` nu este prezent:
  - păstrează comportamentul existent (competitorul curent / următorul nemarcat etc.).
- dacă `idx` este invalid:
  - ridică `ValueError` clar (sau folosește mecanismul de erori deja folosit în proiect) — fără no-op distructiv.

### 4) [Coada] `PROGRESS_SCORE`: calcul robust + clamp minim (implementare separata)
- Citește `holdCount` defensiv:
  - dacă lipsește sau e `None` → tratează ca `0.0`;
  - dacă e non-numeric → normalizează la `0.0` sau aruncă eroare (dar consistent cu restul proiectului).
- Aplică delta/step conform logicii existente (nu schimba step-ul, nu schimba UX).
- Dacă există decrement, clamp minim la `0.0` (nu impune minim `1`).

## Criteria de acceptare
1) `holdCount=0.0` + `PROGRESS_SCORE` nu devine `1` doar fiindcă e falsy.
2) `lastRegisteredTime=None` sau `"abc"` nu produce excepții; starea rămâne consistentă.
3) `SUBMIT_SCORE` cu `idx=0` acționează pe competitorul 0 (sau e respins explicit, dacă alegi varianta de respingere), dar nu se transformă în `idx=1`.
4) Actualizează/adaugă teste pentru cele 3 cazuri.

## Teste (minime și țintite)
Adaugă/actualizează în `tests/test_core_contest.py`:
- `test_progress_score_does_not_coerce_zero_to_one`
- `test_last_registered_time_none_or_invalid_does_not_crash`
- `test_submit_score_accepts_idx_zero` (sau `...rejects_idx...` dacă respingi contractul)

## Note de implementare (schelet orientativ)
- Adaugă un helper (ex. `_coerce_optional_int`) în `contest.py`.
- În `PROGRESS_SCORE`, înlocuiește orice fallback bazat pe truthiness cu verificări explicite.
- În `SUBMIT_SCORE`, parsează `idx` fără a-l altera când este `0`.
