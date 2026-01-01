"""Core contest state transitions (pure, no FastAPI/DB)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .validation import InputSanitizer


@dataclass
class CommandOutcome:
    """Result of applying a core command."""

    state: Dict[str, Any]
    cmd_payload: Dict[str, Any]
    snapshot_required: bool


@dataclass
class ValidationError:
    """Represents a non-transport validation failure (pure core)."""

    kind: str
    message: str | None = None
    status_code: int | None = None


def default_state(session_id: str | None = None) -> Dict[str, Any]:
    import uuid

    return {
        "initiated": False,
        "holdsCount": 0,
        "currentClimber": "",
        "started": False,
        "timerState": "idle",
        "holdCount": 0.0,
        "routeIndex": 1,
        "competitors": [],
        "categorie": "",
        "lastRegisteredTime": None,
        "remaining": None,
        "timerPreset": None,
        "timerPresetSec": None,
        "sessionId": session_id or str(uuid.uuid4()),
        "boxVersion": 0,
    }


def parse_timer_preset(preset: str | None) -> int | None:
    if not preset:
        return None
    try:
        minutes, seconds = (preset or "").split(":")
        return int(minutes or 0) * 60 + int(seconds or 0)
    except Exception:
        return None


def _normalize_competitors(competitors: List[dict] | None) -> List[dict]:
    normalized: List[dict] = []
    if not competitors:
        return normalized

    for comp in competitors:
        try:
            if not isinstance(comp, dict):
                continue
            name = comp.get("nume")
            if not isinstance(name, str):
                continue
            safe_name = InputSanitizer.sanitize_competitor_name(name)
            if not safe_name:
                continue
            marked_val = comp.get("marked", False)
            marked_bool = (
                bool(marked_val) if isinstance(marked_val, (bool, int, str)) else False
            )
            normalized.append({"nume": safe_name, "marked": marked_bool})
        except Exception:
            continue
    return normalized


def apply_command(state: Dict[str, Any], cmd: Dict[str, Any]) -> CommandOutcome:
    """
    Apply a contest command to in-memory state (pure core, no I/O).
    Returns updated state + command payload for echo.
    """

    ctype = cmd.get("type")
    snapshot_required = False
    payload = dict(cmd)

    if ctype == "INIT_ROUTE":
        state["boxVersion"] = state.get("boxVersion", 0) + 1
        payload["sessionId"] = state.get("sessionId")
        state["initiated"] = True
        state["holdsCount"] = cmd.get("holdsCount") or 0
        state["routeIndex"] = cmd.get("routeIndex") or 1

        competitors = _normalize_competitors(cmd.get("competitors"))
        state["competitors"] = competitors
        state["currentClimber"] = competitors[0]["nume"] if competitors else ""

        state["started"] = False
        state["timerState"] = "idle"
        state["holdCount"] = 0.0
        state["lastRegisteredTime"] = None
        state["remaining"] = None

        if cmd.get("categorie"):
            state["categorie"] = cmd["categorie"]
        if cmd.get("timerPreset"):
            state["timerPreset"] = cmd["timerPreset"]
            state["timerPresetSec"] = parse_timer_preset(cmd.get("timerPreset"))

        snapshot_required = True

    elif ctype == "START_TIMER":
        state["started"] = True
        state["timerState"] = "running"
        state["lastRegisteredTime"] = None
        state["remaining"] = None
        snapshot_required = True

    elif ctype == "STOP_TIMER":
        state["started"] = False
        state["timerState"] = "paused"
        snapshot_required = True

    elif ctype == "RESUME_TIMER":
        state["started"] = True
        state["timerState"] = "running"
        state["lastRegisteredTime"] = None
        snapshot_required = True

    elif ctype == "PROGRESS_UPDATE":
        delta = cmd.get("delta") or 1
        new_count = (
            (int(state.get("holdCount", 0)) + 1)
            if delta == 1
            else round(state.get("holdCount", 0) + delta, 1)
        )
        if new_count < 0:
            new_count = 0.0
        max_holds = state.get("holdsCount") or 0
        if isinstance(max_holds, int) and max_holds > 0 and new_count > max_holds:
            new_count = float(max_holds)
        state["holdCount"] = new_count
        snapshot_required = True

    elif ctype == "REGISTER_TIME":
        if cmd.get("registeredTime") is not None:
            state["lastRegisteredTime"] = cmd.get("registeredTime")
        snapshot_required = True

    elif ctype == "TIMER_SYNC":
        state["remaining"] = cmd.get("remaining")

    elif ctype == "SUBMIT_SCORE":
        effective_time = cmd.get("registeredTime")
        if effective_time is None:
            effective_time = state.get("lastRegisteredTime")
        payload["registeredTime"] = effective_time

        competitor_name = cmd.get("competitor")
        route_idx = max((state.get("routeIndex") or 1) - 1, 0)
        if competitor_name:
            scores = state.get("scores") or {}
            times = state.get("times") or {}
            if cmd.get("score") is not None:
                arr = scores.get(competitor_name) or []
                while len(arr) <= route_idx:
                    arr.append(None)
                arr[route_idx] = cmd.get("score")
                scores[competitor_name] = arr
            if effective_time is not None:
                tarr = times.get(competitor_name) or []
                while len(tarr) <= route_idx:
                    tarr.append(None)
                tarr[route_idx] = effective_time
                times[competitor_name] = tarr
            state["scores"] = scores
            state["times"] = times

        state["started"] = False
        state["timerState"] = "idle"
        state["holdCount"] = 0.0
        state["lastRegisteredTime"] = effective_time
        state["remaining"] = None

        competitors = state.get("competitors") or []
        if competitors:
            for comp in competitors:
                if not isinstance(comp, dict):
                    continue
                if comp.get("nume") == competitor_name:
                    comp["marked"] = True
                    break
            next_comp = next(
                (
                    c.get("nume")
                    for c in competitors
                    if isinstance(c, dict) and not c.get("marked")
                ),
                "",
            )
            state["currentClimber"] = next_comp
        snapshot_required = True

    elif ctype == "RESET_BOX":
        import uuid

        state["initiated"] = False
        state["currentClimber"] = ""
        state["started"] = False
        state["timerState"] = "idle"
        state["holdCount"] = 0.0
        state["lastRegisteredTime"] = None
        state["remaining"] = None
        state["competitors"] = []
        state["categorie"] = ""
        state["timerPreset"] = None
        state["timerPresetSec"] = None
        state["sessionId"] = str(uuid.uuid4())
        snapshot_required = True

    return CommandOutcome(state=state, cmd_payload=payload, snapshot_required=snapshot_required)


def validate_session_and_version(
    state: Dict[str, Any],
    cmd: Dict[str, Any],
    *,
    require_session: bool = True,
) -> ValidationError | None:
    """
    Pure validation for sessionId and boxVersion against current state.
    Returns ValidationError if rejected, otherwise None.
    """
    current_session = state.get("sessionId")
    incoming_session = cmd.get("sessionId")

    if require_session and not incoming_session:
        return ValidationError(
            kind="missing_session",
            message="sessionId required for all commands except INIT_ROUTE",
            status_code=400,
        )

    if incoming_session and current_session and incoming_session != current_session:
        return ValidationError(kind="stale_session")

    incoming_version = cmd.get("boxVersion")
    current_version = state.get("boxVersion", 0)
    if incoming_version is not None and incoming_version < current_version:
        return ValidationError(kind="stale_version")

    return None


def toggle_time_criterion(
    current_value: bool, enabled: bool | None
) -> Tuple[bool, Dict[str, Any]]:
    """Pure helper to compute new time criterion flag and payload."""
    new_value = bool(enabled)
    payload = {
        "type": "TIME_CRITERION",
        "timeCriterionEnabled": new_value,
    }
    return new_value, payload
