# CODEX PROMPT — Escalada (core + api + ui) Hardening Plan

Ești Codex CLI și ai acces la 3 repo‑uri surori (CWD este `escalada-core`):
- `escalada-core` (logică pură: mașină de stări + validare)
- `../escalada-api` (FastAPI + WebSocket + persistă starea în `data/boxes/*.json`)
- `../escalada-ui` (React/Vite; trimite comenzi la `/api/cmd`, folosește WS pentru updates)

**Obiectiv**
- Elimină instabilitățile cunoscute în fluxul de concurs (comenzi ignorate din cauza `sessionId/boxVersion`, WS handshake noisy, persist/clear comportament controlabil, hardening de securitate/config), păstrând compatibilitatea și schimbările cât mai mici.

**Non‑goals (respectă strict)**
- Nu implementa task-ul separat `PROGRESS_SCORE` (cel “în coadă”).
- Ignoră problema “cleanup backend boxes”.
- Nu schimba `/#/rankings` să citească din localStorage (rămâne din backend).
- Nu adăuga refactorizări mari / nu schimba API contracts fără motiv.

---

## 1) escalada-core (core correctness)

**Țintă:** `escalada_core/contest.py`, `escalada_core/validation.py`, `tests/test_core_contest.py`

- `REGISTER_TIME`: coercion defensiv pentru `registeredTime/lastRegisteredTime` (acceptă `None`, numere, string numeric; respinge valori invalide fără crash).
- `SUBMIT_SCORE`: suport pentru selectarea competitorului prin:
  - `idx` (0‑based) și alias `competitorIdx`
  - sau `competitor` (nume)
  - fără a pierde `0` (idx=0 trebuie să rămână valid)
  - validare bounds (idx în intervalul `competitors`)
  - când primești idx/competitorIdx valid, rezolvă numele competitorului din `competitors[idx]` și normalizează payload.
- `validation`: `SUBMIT_SCORE` trebuie să accepte `competitor` **sau** `idx` **sau** `competitorIdx` (și să nu respingă `idx=0`).
- Teste: adaugă/actualizează teste pentru `idx=0`, `lastRegisteredTime=None/invalid`, și cazuri “empty string / None” care nu trebuie să spargă flow‑ul.

**Comandă test (core):** `poetry run pytest -q tests/test_core_contest.py`

---

## 2) escalada-api (transport + securitate + opțiuni de operare)

**Țintă:** `../escalada-api/escalada/api/live.py`, `../escalada-api/escalada/api/save_ranking.py`, `../escalada-api/escalada/auth/service.py`, `../escalada-api/escalada/main.py`, `../escalada-api/RUNBOOK_CONCURS.md`

- `/api/cmd`: asigură propagarea câmpului `idx` până în `ValidatedCmd` (dacă modelul legacy `Cmd` îl pierde, adaugă `idx: int | None` acolo).
- Persist/reset operare: suportă reset automat la pornire controlat prin env (ex. `RESET_BOXES_ON_START=1`) care șterge `data/boxes/*.json` înainte de preload (util pentru demo/test; *nu* default pentru concurs).
- Securitate:
  - avertizează la startup dacă `JWT_SECRET` rămâne default (`dev-secret-change-me`) și documentează în `.env`/RUNBOOK.
  - CORS: documentează cum se setează `ALLOWED_ORIGINS`/`ALLOWED_ORIGIN_REGEX` pentru IP‑urile folosite în sală (fără a relaxa inutil în cod).
- Path traversal: sanitize pentru `payload.categorie` în `save_ranking` astfel încât să nu poată ieși din `escalada/clasamente` (păstrează diacritice/spații dacă se poate; blochează `..`, `/`, `\\` sau “escape via resolve”).

**Comenzi test (api):**
- `cd ../escalada-api && poetry run pip install -e ../escalada-core`
- `cd ../escalada-api && poetry run pytest -q`

---

## 3) escalada-ui (reziliență comenzi + WS stability)

**Țintă:** `../escalada-ui/src/utilis/contestActions.js`, `../escalada-ui/src/components/ControlPanel.tsx`, `../escalada-ui/src/components/ContestPage.tsx`

- Pentru comenzi critice (minim `START_TIMER`, `STOP_TIMER`, `RESUME_TIMER`):
  - dacă backend răspunde `{"status":"ignored"}`, fă resync (ex. `GET /api/state/{boxId}`), actualizează `sessionId`/`boxVersion` și retry o singură dată.
  - dacă tot e ignorat, arată o eroare clară și revino la un state safe (nu lăsa UI blocată/optimistică).
- `INIT_ROUTE`: nu trimite `sessionId` (comanda e special‑case în API; evită “stale_session” după restart).
- WebSocket cleanup (ControlPanel): evită `ws.close()` când socketul e `CONNECTING` (reduce warnings “closed before established”); aliniază comportamentul cu pattern‑ul deja folosit în ContestPage/hook (detach handlers, “defer close” dacă e nevoie).

**Comenzi test (ui):**
- `cd ../escalada-ui && npm run test -- --run`

---

## 4) Smoke test manual (după implementare)

1. Pornește API + UI.
2. Inițializează un concurs, pornește timerul, apasă `+1 hold` de câteva ori, `stop time`, `submit score`.
3. Repornește API (fără UI) și verifică:
   - comenzi din tab-uri vechi: nu blochează UI; se resync/arată mesaj clar
   - WS: fără spam de erori “closed before established” la navigare
4. (Opțional demo) pornește API cu `RESET_BOXES_ON_START=1` și verifică că `/#/rankings` pornește curat.

---

## Output așteptat de la Codex

- Patch-uri minimale în repo-urile relevante.
- Teste rulate (sau instrucțiuni clare dacă nu pot fi rulate).
- Un rezumat scurt: ce fișiere au fost schimbate + cum verifici.

<!--
LEGACY PLAN (păstrat doar ca referință; nu urma secțiunile de mai jos)

# Escalada Application Implementation Plan

**Audit Date:** 18 ianuarie 2026  
**Status:** Ready for Implementation  
**Scope:** escalada-core, escalada-api, escalada-ui

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Phase 1: Critical Fixes (P1)](#phase-1-critical-fixes-p1)
3. [Phase 2: Robustness Improvements (P2)](#phase-2-robustness-improvements-p2)
4. [Phase 3: Quality & UX Enhancements (P3)](#phase-3-quality--ux-enhancements-p3)
5. [Testing & Validation](#testing--validation)
6. [Deployment Strategy](#deployment-strategy)

---

## Executive Summary

The Escalada application has a **sound architecture** with clean separation of concerns (domain logic, API, UI) but suffers from **three critical state-transition bugs** that affect:
- Score marking (falsy values coerced to defaults)
- Competitor indexing (zero index lost in conditional logic)
- Time registration (defensive coercion missing)

**Total Implementation Effort:** ~12-14 hours  
**Risk Level:** Low (isolated fixes, high test coverage possible)  
**Priority:** All P1 items must complete before next contest event.

---

## Phase 1: Critical Fixes (P1)

### P1.1: Fix `holdCount=0` Bug in Core State Machine

**Problem:**  
In [`escalada_core/contest.py`](escalada_core/contest.py#L236-L240), the `PROGRESS_UPDATE` command uses:
```python
"holdCount": cmd.get("holdCount") or 1
```
This coerces `holdCount=0` (valid state: no holds registered yet) to `1`, corrupting scoring.

**Solution:**  
Create a `_coerce_optional_int()` helper to distinguish `None` (missing) from `0` (valid).

**Implementation:**

1. Add helper function to `escalada_core/contest.py`:
```python
def _coerce_optional_int(value, default=None):
    """Coerce optional int; preserve 0, reject None/invalid."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value) if isinstance(value, float) else value
    raise ValueError(f"Invalid int value: {value}")
```

2. Replace all `or` fallbacks in state transitions:
   - Line 236-240: `PROGRESS_UPDATE` → use `_coerce_optional_int()`
   - Line 249-256: `REGISTER_TIME` → use helper for `lastRegisteredTime`
   - Line 271-285: `SUBMIT_SCORE` → use helper for `idx`

3. Add test cases:
   - `test_progress_update_with_zero_holds()`
   - `test_progress_update_preserves_zero_not_one()`

**Acceptance Criteria:**
- ✅ `holdCount=0` does not become `1`
- ✅ All transitions preserve falsy values correctly
- ✅ Tests pass for edge cases (0, None, negative values)
- ✅ No regression in existing command flows

**Effort:** 1 hour  
**Owner:** escalada-core  

---

### P1.2: Fix `idx=0` Parsing in `SUBMIT_SCORE`

**Problem:**  
Line 271-285 uses `cmd.get("idx") or fallback_idx`, losing index 0 (first competitor).

**Solution:**  
Use the new `_coerce_optional_int()` helper to validate idx correctly.

**Implementation:**

1. Replace conditional in `SUBMIT_SCORE`:
```python
# Before:
idx = cmd.get("idx") or 0  # BUG: 0 becomes fallback

# After:
idx = _coerce_optional_int(cmd.get("idx"), default=0)
```

2. Add validation for idx bounds:
```python
if idx < 0 or idx >= len(competitors):
    raise ValueError(f"Invalid idx {idx} for {len(competitors)} competitors")
```

3. Add test cases:
   - `test_submit_score_with_idx_zero()`
   - `test_submit_score_marks_first_competitor()`
   - `test_submit_score_idx_out_of_bounds()`

**Acceptance Criteria:**
- ✅ First competitor (`idx=0`) can be marked correctly
- ✅ All idx values 0..n work without loss
- ✅ Invalid idx raises proper error
- ✅ Backward compatibility maintained

**Effort:** 1 hour  
**Owner:** escalada-core  

---

### P1.3: Add Defensive `lastRegisteredTime` Coercion

**Problem:**  
`REGISTER_TIME` command has no defensive coercion for `None`/invalid values.

**Solution:**  
Validate and normalize time strings to `HH:MM:SS` format before storing.

**Implementation:**

1. Create `_normalize_time()` helper:
```python
def _normalize_time(time_str):
    """Normalize time to HH:MM:SS; handle 'H:MM' and 'HH:MM' variants."""
    if time_str is None:
        return None
    if not isinstance(time_str, str):
        raise ValueError(f"Invalid time type: {type(time_str)}")
    
    parts = time_str.split(":")
    if len(parts) == 2:  # H:MM or HH:MM
        h, m = parts
        s = "00"
    elif len(parts) == 3:  # HH:MM:SS
        h, m, s = parts
    else:
        raise ValueError(f"Invalid time format: {time_str}")
    
    h, m, s = int(h), int(m), int(s)
    return f"{h:02d}:{m:02d}:{s:02d}"
```

2. Update `REGISTER_TIME` command handler:
```python
"lastRegisteredTime": _normalize_time(cmd.get("lastRegisteredTime"))
```

3. Add validation in `validation.py`:
   - Regex: `^([0-2][0-9]|[0-9]):[0-5][0-9](:[0-5][0-9])?$`
   - Pydantic v2 validator

4. Add test cases:
   - `test_register_time_normalizes_padding()`
   - `test_register_time_none_value()`
   - `test_register_time_invalid_format_raises()`

**Acceptance Criteria:**
- ✅ Time values normalized to `HH:MM:SS`
- ✅ `None` values handled without error
- ✅ Invalid formats raise with clear message
- ✅ Validation applied consistently across API + core

**Effort:** 1 hour  
**Owner:** escalada-core, escalada-api  

---

## Phase 2: Robustness Improvements (P2)

### P2.1: Verify Rate Limit Enforcement in API

**Problem:**  
Rate limiting enforcement in [`escalada/rate_limit.py`](escalada/rate_limit.py) is unclear; potential DOS vectors.

**Solution:**  
Audit + document rate limit thresholds; add stress tests.

**Implementation:**

1. Review `rate_limit.py`:
   - Verify per-IP limits (e.g., 100 req/min)
   - Verify per-boxId limits (e.g., 50 cmd/min)
   - Verify global WS connection limits

2. Add unit tests in `tests/test_rate_limit.py`:
   - `test_rate_limit_per_ip_exceeded()`
   - `test_rate_limit_per_box_exceeded()`
   - `test_rate_limit_burst_handling()`

3. Document thresholds in [`escalada/main.py`](escalada/main.py):
```python
# Rate limit configuration
RATE_LIMIT_PER_IP = 100  # requests/minute
RATE_LIMIT_PER_BOX = 50  # commands/minute
RATE_LIMIT_WS = 10       # concurrent connections/box
```

4. Add monitoring logs:
   - Log when limit is exceeded
   - Include client IP, boxId, reason

**Acceptance Criteria:**
- ✅ All rate limits documented with thresholds
- ✅ Unit tests cover normal + exceeded scenarios
- ✅ No concurrent request race conditions
- ✅ Stress test passes (1000 req/sec for 10s)

**Effort:** 2 hours  
**Owner:** escalada-api  

---

### P2.2: Strengthen Stale-Tab Prevention in UI

**Problem:**  
ControlPanel doesn't explicitly validate `sessionId` + `boxVersion` before sending commands; weak error recovery.

**Solution:**  
Add explicit session validation + improved error handling for ignored commands.

**Implementation:**

1. Update `src/components/ControlPanel.tsx`:
```javascript
const sendCommand = async (cmd) => {
    // Validate session before sending
    const response = await fetch(`/api/state/${boxId}`);
    const { sessionId: currentSession, boxVersion: currentVersion } = await response.json();
    
    if (sessionId !== currentSession || boxVersion !== currentVersion) {
        // Stale tab detected
        setError("Session expired. Reload page.");
        return;
    }
    
    // Send command with current session info
    cmd.sessionId = currentSession;
    cmd.boxVersion = currentVersion;
    const result = await http.post("/api/cmd", cmd);
    
    if (result.status === "ignored") {
        setError("Command ignored (stale state). Refreshing...");
        // Auto-refresh state from server
        location.reload();
    }
};
```

2. Add error UI component `src/components/StaleTabAlert.tsx`:
```typescript
export const StaleTabAlert = ({ message, onDismiss }) => (
    <div className="alert alert-warning">
        {message}
        <button onClick={onDismiss}>Dismiss</button>
    </div>
);
```

3. Add tests in `src/__tests__/ControlPanel.test.jsx`:
   - `test_stale_tab_detected_shows_alert()`
   - `test_command_ignored_triggers_reload()`
   - `test_session_mismatch_prevents_send()`

4. Update `src/utilis/useAppState.tsx` BroadcastChannel sync:
   - Broadcast `sessionId` + `boxVersion` updates
   - Auto-refresh on mismatch

**Acceptance Criteria:**
- ✅ Stale tabs are detected before command send
- ✅ Ignored commands show clear error message
- ✅ User can manually refresh or auto-refresh
- ✅ Cross-tab sync prevents race conditions
- ✅ Tests pass for all stale scenarios

**Effort:** 2 hours  
**Owner:** escalada-ui  

---

### P2.3: Verify State Mutation Handling in API

**Problem:**  
`apply_command()` mutates input dict for backward compatibility; risk of concurrent request bugs.

**Solution:**  
Document mutation behavior; consume `CommandOutcome` consistently.

**Implementation:**

1. Update [`escalada/api/live.py`](escalada/api/live.py#L227-L240):
```python
# Before:
apply_command(state, cmd)  # Mutates state, also returns CommandOutcome

# After:
outcome = apply_command(state, cmd)  # Explicitly use returned outcome
# state is mutated as side-effect (for backward compat)
# but we prefer the outcome
```

2. Add comment in core:
```python
# NOTE: apply_command() mutates the input state dict AND returns CommandOutcome.
# The mutation is for backward compatibility; new callers should use CommandOutcome.
def apply_command(state: dict, cmd: dict) -> CommandOutcome:
    ...
```

3. Add concurrency tests in `tests/test_concurrent_commands.py`:
   - `test_concurrent_same_box_commands()`
   - `test_concurrent_different_boxes()`
   - `test_state_lock_prevents_corruption()`

4. Verify state locks in `escalada/api/live.py`:
```python
async with state_locks[boxId]:
    # Critical section: state mutation
    outcome = apply_command(state, validated_cmd)
```

**Acceptance Criteria:**
- ✅ No race conditions under 100 concurrent requests/box
- ✅ State locks prevent corruption
- ✅ Documentation clarifies mutation semantics
- ✅ Concurrent tests pass

**Effort:** 2 hours  
**Owner:** escalada-api  

---

## Phase 3: Quality & UX Enhancements (P3)

### P3.1: Complete TypeScript Interfaces

**Problem:**  
[`src/types/index.ts`](src/types/index.ts) has incomplete interface definitions; weak type safety.

**Solution:**  
Add complete, exported TypeScript types matching API contracts.

**Implementation:**

1. Expand `src/types/index.ts`:
```typescript
// State types
export interface BoxState {
    boxId: string;
    sessionId: string;
    boxVersion: number;
    timerState: "stopped" | "running" | "paused";
    holdCount: number;
    lastRegisteredTime: string | null;
    competitors: Competitor[];
}

export interface Competitor {
    nume: string;
    marked: boolean;
    score: number | null;
}

// Command types
export interface ProgressUpdateCmd {
    type: "PROGRESS_UPDATE";
    holdCount: number;
}

export interface RegisterTimeCmd {
    type: "REGISTER_TIME";
    lastRegisteredTime: string;
}

// API response types
export interface CommandOutcome {
    status: "success" | "ignored" | "error";
    state?: BoxState;
    error?: string;
}
```

2. Use types in components:
```typescript
// src/components/ControlPanel.tsx
const sendCommand = async (cmd: ProgressUpdateCmd) => { ... }

// src/components/ContestPage.tsx
const [state, setState] = useState<BoxState | null>(null);
```

3. Add tests for type coverage:
   - `test_types_match_api_contracts()`
   - `test_component_type_errors_caught()`

**Acceptance Criteria:**
- ✅ All API types defined in `index.ts`
- ✅ Components use proper types (no `any`)
- ✅ TypeScript strict mode passes
- ✅ No type errors in build

**Effort:** 1 hour  
**Owner:** escalada-ui  

---

### P3.2: Add Client-Side Timer Preset Validation

**Problem:**  
Timer presets (e.g., "5:00") are validated server-side; client should validate before send.

**Solution:**  
Add client-side validation + normalization for timer presets.

**Implementation:**

1. Create `src/utilis/timerValidator.ts`:
```typescript
export const normalizeTimerPreset = (input: string): string => {
    const parts = input.split(":");
    if (parts.length !== 2 && parts.length !== 3) {
        throw new Error("Invalid time format. Use HH:MM or HH:MM:SS");
    }
    
    const [h, m, s = "00"] = parts;
    const hours = parseInt(h).toString().padStart(2, "0");
    const mins = parseInt(m).toString().padStart(2, "0");
    const secs = parseInt(s).toString().padStart(2, "0");
    
    return `${hours}:${mins}:${secs}`;
};

export const validateTimerPreset = (preset: string): boolean => {
    const regex = /^([0-2][0-9]|[0-9]):[0-5][0-9](:[0-5][0-9])?$/;
    return regex.test(preset);
};
```

2. Update timer input in ControlPanel:
```typescript
const handleTimerInput = (input: string) => {
    try {
        const normalized = normalizeTimerPreset(input);
        setTimerDisplay(normalized);
    } catch (e) {
        setError(e.message);
    }
};
```

3. Add tests in `src/__tests__/timerValidator.test.js`:
   - `test_normalize_5_00_to_05_00_00()`
   - `test_invalid_format_throws()`
   - `test_validate_preset_accepts_valid()`

**Acceptance Criteria:**
- ✅ Client validates before server (UX improvement)
- ✅ Presets normalized to `HH:MM:SS` format
- ✅ Clear error messages for invalid input
- ✅ Tests pass for all timer formats

**Effort:** 1 hour  
**Owner:** escalada-ui  

---

### P3.3: Add E2E Tests for Cross-Tab Sync

**Problem:**  
No E2E tests verify BroadcastChannel sync across tabs for state updates.

**Solution:**  
Add Playwright E2E tests for multi-tab scenario.

**Implementation:**

1. Create `e2e/cross-tab-sync.spec.ts`:
```typescript
test("state updates sync across tabs", async ({ browser }) => {
    const context = await browser.newContext();
    const page1 = await context.newPage();
    const page2 = await context.newPage();
    
    // Navigate both to same box
    await page1.goto("http://localhost:5173/contest/box-1");
    await page2.goto("http://localhost:5173/contest/box-1");
    
    // Update in page1
    await page1.click("[data-testid=progress-btn]");
    
    // Verify page2 receives update via BroadcastChannel
    await page2.waitForFunction(() => {
        const state = JSON.parse(localStorage.getItem("escalada-state"));
        return state?.holdCount === 1;
    });
});

test("stale tab prevented by sessionId check", async ({ browser }) => {
    const context = await browser.newContext();
    const page1 = await context.newPage();
    const page2 = await context.newPage();
    
    // Set up page1 with session
    await page1.goto("http://localhost:5173/control");
    const session1 = await page1.evaluate(() => sessionStorage.getItem("sessionId"));
    
    // Change session in API (simulate stale)
    await fetch("/api/box/1/reset", { method: "POST" });
    
    // Try command from page1 (stale)
    const result = await page1.evaluate(async () => {
        const resp = await fetch("/api/cmd", { method: "POST", body: JSON.stringify({ ... }) });
        return resp.json();
    });
    
    expect(result.status).toBe("ignored");
});
```

2. Run tests: `npx playwright test e2e/cross-tab-sync.spec.ts`

**Acceptance Criteria:**
- ✅ Cross-tab state sync tested
- ✅ Stale-tab prevention verified
- ✅ All scenarios pass (local dev + CI)
- ✅ Tests are maintainable and fast

**Effort:** 3 hours  
**Owner:** escalada-ui  

---

## Testing & Validation

### Unit Test Coverage

| Repo | File | Current | Target | New Tests |
|------|------|---------|--------|-----------|
| core | `test_core_contest.py` | ~60% | 95% | P1 edge cases (0, None, invalid) |
| api | `tests/test_*.py` | ~50% | 85% | Rate limit, concurrency, stale-tab |
| ui | `src/__tests__/` | ~40% | 75% | Types, timer validation, sync |

### Test Execution Plan

```bash
# Phase 1 validation (after P1 fixes)
cd escalada-core && poetry run pytest -q --cov=escalada_core

# Phase 2 validation
cd escalada-api && poetry run pytest -q --cov=escalada

# Phase 3 validation
cd escalada-ui && npm run test -- --run
npx playwright test --reporter=list
```

### Acceptance Criteria (All Phases)

- ✅ All P1 tests pass (unit + integration)
- ✅ All P2 stress tests pass (100+ concurrent)
- ✅ All P3 E2E tests pass (multi-tab scenarios)
- ✅ No regressions in existing tests
- ✅ Code review + sign-off from team

---

## Deployment Strategy

### Pre-Deployment Checklist

- [ ] **escalada-core**: All P1 fixes merged + tests pass
- [ ] **escalada-api**: Rate limit verified, concurrency tests pass
- [ ] **escalada-ui**: Stale-tab detection deployed, E2E tests pass
- [ ] **Integration test**: Full contest flow (timer → register → score → complete)
- [ ] **Staging deployment**: 24h smoke test with team
- [ ] **Documentation**: Update [RUNBOOK_CONCURS.md](../escalada-api/RUNBOOK_CONCURS.md)

### Rollout Plan

1. **Day 1 (Mon):** Deploy escalada-core P1 fixes
2. **Day 2 (Tue):** Deploy escalada-api P2 fixes
3. **Day 3 (Wed):** Deploy escalada-ui P2+P3 fixes
4. **Day 4-5 (Thu-Fri):** Staging validation + team testing
5. **Day 6 (Next Mon):** Production deployment (post-backup)

### Rollback Plan

If critical issues detected in production:
1. Rollback to last stable backup: `escalada/api/backup.py` → `restore_from_backup()`
2. Revert UI to previous version (static files)
3. Notify team + conduct incident review

---

## Success Metrics

| Metric | Target | Validation |
|--------|--------|-----------|
| **P1 Bugs Fixed** | 3/3 | Unit tests pass; no falsy value loss |
| **Rate Limit DOS** | 0 events | Stress test + monitoring logs |
| **Stale-Tab Incidents** | 0 events | E2E tests; cross-tab sync verified |
| **Command Success Rate** | 99.9% | API logs over 48h post-deploy |
| **Test Coverage** | 85%+ | Code coverage report |
| **Zero Data Corruption** | Verified | State audit + audit logs review |

---

## Timeline

| Phase | Tasks | Duration | Target Date |
|-------|-------|----------|-------------|
| **P1** | 3 core fixes | 3 hours | 18-19 Jan |
| **P2** | Rate limit + stale-tab + concurrency | 6 hours | 20-21 Jan |
| **P3** | Types + validation + E2E tests | 5 hours | 22-23 Jan |
| **Testing** | Full integration + staging | 8 hours | 24-27 Jan |
| **Deployment** | Production rollout | 2 hours | 28 Jan |

**Total: 24 hours of implementation + testing**

---

## References

- [escalada-core Copilot Instructions](escalada_core/../.github/copilot-instructions.md)
- [escalada-api Copilot Instructions](../escalada-api/.github/copilot-instructions.md)
- [escalada-ui Copilot Instructions](../escalada-ui/.github/copilot-instructions.md)
- [RUNBOOK_CONCURS.md](../escalada-api/RUNBOOK_CONCURS.md)

---

**Status:** Ready for implementation  
**Approved By:** [Team Lead]  
**Last Updated:** 18 ianuarie 2026
-->
