"""Core contest state transitions (pure, no FastAPI/DB)."""
from __future__ import annotations

from copy import deepcopy
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
        "routesCount": 1,
        "holdsCounts": [],
        "competitors": [],
        "categorie": "",
        "lastRegisteredTime": None,
        "remaining": None,
        "timerPreset": None,
        "timerPresetSec": None,
        "timeCriterionEnabled": False,
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


def _apply_transition(state: Dict[str, Any], cmd: Dict[str, Any]) -> CommandOutcome:
    """
    Pure transition: works on a copy of the provided state and returns new state + payload.
    """
    # Work on a copy to keep transitions pure and deterministic for the same input.
    new_state: Dict[str, Any] = deepcopy(state)
    ctype = cmd.get("type")
    snapshot_required = False
    payload = dict(cmd)

    if ctype == "INIT_ROUTE":
        new_state["boxVersion"] = new_state.get("boxVersion", 0) + 1
        payload["sessionId"] = new_state.get("sessionId")
        new_state["initiated"] = True
        new_state["holdsCount"] = cmd.get("holdsCount") or 0
        new_state["routeIndex"] = cmd.get("routeIndex") or 1
        if cmd.get("routesCount") is not None:
            new_state["routesCount"] = cmd.get("routesCount")
        if cmd.get("holdsCounts") is not None:
            new_state["holdsCounts"] = cmd.get("holdsCounts")

        competitors = _normalize_competitors(cmd.get("competitors"))
        new_state["competitors"] = competitors
        new_state["currentClimber"] = competitors[0]["nume"] if competitors else ""

        new_state["started"] = False
        new_state["timerState"] = "idle"
        new_state["holdCount"] = 0.0
        new_state["lastRegisteredTime"] = None
        new_state["remaining"] = None

        if cmd.get("categorie"):
            new_state["categorie"] = cmd["categorie"]
        if cmd.get("timerPreset"):
            new_state["timerPreset"] = cmd["timerPreset"]
            new_state["timerPresetSec"] = parse_timer_preset(cmd.get("timerPreset"))

        snapshot_required = True

    elif ctype == "START_TIMER":
        new_state["started"] = True
        new_state["timerState"] = "running"
        new_state["lastRegisteredTime"] = None
        new_state["remaining"] = None
        snapshot_required = True

    elif ctype == "STOP_TIMER":
        new_state["started"] = False
        new_state["timerState"] = "paused"
        snapshot_required = True

    elif ctype == "RESUME_TIMER":
        new_state["started"] = True
        new_state["timerState"] = "running"
        new_state["lastRegisteredTime"] = None
        snapshot_required = True

    elif ctype == "PROGRESS_UPDATE":
        delta = cmd.get("delta") or 1
        new_count = (
            (int(new_state.get("holdCount", 0)) + 1)
            if delta == 1
            else round(new_state.get("holdCount", 0) + delta, 1)
        )
        if new_count < 0:
            new_count = 0.0
        max_holds = new_state.get("holdsCount") or 0
        if isinstance(max_holds, int) and max_holds > 0 and new_count > max_holds:
            new_count = float(max_holds)
        new_state["holdCount"] = new_count
        snapshot_required = True

    elif ctype == "REGISTER_TIME":
        if cmd.get("registeredTime") is not None:
            new_state["lastRegisteredTime"] = cmd.get("registeredTime")
        snapshot_required = True

    elif ctype == "TIMER_SYNC":
        new_state["remaining"] = cmd.get("remaining")

    elif ctype == "SUBMIT_SCORE":
        effective_time = cmd.get("registeredTime")
        if effective_time is None:
            effective_time = new_state.get("lastRegisteredTime")
        payload["registeredTime"] = effective_time

        competitor_name = cmd.get("competitor")
        route_idx = max((new_state.get("routeIndex") or 1) - 1, 0)
        if competitor_name:
            scores = new_state.get("scores") or {}
            times = new_state.get("times") or {}
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
            new_state["scores"] = scores
            new_state["times"] = times

        new_state["started"] = False
        new_state["timerState"] = "idle"
        new_state["holdCount"] = 0.0
        new_state["lastRegisteredTime"] = effective_time
        new_state["remaining"] = None

        competitors = new_state.get("competitors") or []
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
            new_state["currentClimber"] = next_comp
        snapshot_required = True

    elif ctype == "SET_TIME_CRITERION":
        if cmd.get("timeCriterionEnabled") is not None:
            new_state["timeCriterionEnabled"] = bool(cmd.get("timeCriterionEnabled"))
        snapshot_required = True

    elif ctype == "RESET_BOX":
        import uuid

        new_state["initiated"] = False
        new_state["currentClimber"] = ""
        new_state["started"] = False
        new_state["timerState"] = "idle"
        new_state["holdCount"] = 0.0
        new_state["lastRegisteredTime"] = None
        new_state["remaining"] = None
        new_state["routesCount"] = 1
        new_state["holdsCounts"] = []
        new_state["competitors"] = []
        new_state["categorie"] = ""
        new_state["timerPreset"] = None
        new_state["timerPresetSec"] = None
        new_state["sessionId"] = str(uuid.uuid4())
        snapshot_required = True

    return CommandOutcome(
        state=new_state, cmd_payload=payload, snapshot_required=snapshot_required
    )


def apply_command(state: Dict[str, Any], cmd: Dict[str, Any]) -> CommandOutcome:
    """
    Apply a contest command to in-memory state.
    Returns updated state + command payload for echo.
    """
    outcome = _apply_transition(state, cmd)

    # Preserve backward compatibility for callers that expect in-place mutation.
    state.clear()
    state.update(outcome.state)

    return outcome


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
    current_value: bool, enabled: bool | None, box_id: int | None = None
) -> Tuple[bool, Dict[str, Any]]:
    """Pure helper to compute new time criterion flag and payload."""
    new_value = bool(enabled)
    payload = {
        "type": "SET_TIME_CRITERION",
        "timeCriterionEnabled": new_value,
    }
    if box_id is not None:
        payload["boxId"] = box_id
    return new_value, payload
