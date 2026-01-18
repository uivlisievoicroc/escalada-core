"""Core contest state transitions (pure, no FastAPI/DB)."""
from __future__ import annotations

import math
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
        "preparingClimber": "",
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


def _coerce_optional_time(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
            if not math.isfinite(parsed):
                return None
            return parsed
        except ValueError:
            return None
    return None


def _coerce_idx(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped, 10)
        except ValueError:
            return None
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
            club = None
            if comp.get("club") not in (None, ""):
                club_candidate = InputSanitizer.sanitize_string(
                    comp.get("club") if isinstance(comp.get("club"), str) else str(comp.get("club")),
                    255,
                )
                if club_candidate:
                    club = club_candidate
            marked_val = comp.get("marked", False)
            if isinstance(marked_val, bool):
                marked_bool = marked_val
            elif isinstance(marked_val, (int, float)):
                marked_bool = bool(int(marked_val))
            elif isinstance(marked_val, str):
                lowered = marked_val.strip().lower()
                if lowered in {"1", "true", "yes", "y", "on"}:
                    marked_bool = True
                elif lowered in {"0", "false", "no", "n", "off", ""}:
                    marked_bool = False
                else:
                    marked_bool = False
            else:
                marked_bool = False
            entry: dict[str, Any] = {"nume": safe_name, "marked": marked_bool}
            if club is not None:
                entry["club"] = club
            normalized.append(entry)
        except Exception:
            continue
    return normalized


def _compute_preparing_climber(competitors: List[dict], current_climber: str) -> str:
    """
    Match ContestPage behavior: "preparing" is the next competitor after the active climber,
    based on the competitors order. We optionally skip already-marked competitors.
    """
    if not competitors or not current_climber:
        return ""
    current_idx = None
    for i, comp in enumerate(competitors):
        if isinstance(comp, dict) and comp.get("nume") == current_climber:
            current_idx = i
            break
    if current_idx is None:
        return ""
    for comp in competitors[current_idx + 1 :]:
        if not isinstance(comp, dict):
            continue
        name = comp.get("nume")
        if not isinstance(name, str) or not name.strip():
            continue
        if comp.get("marked"):
            continue
        return name
    return ""


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
        incoming_route_index = cmd.get("routeIndex") or 1
        new_state["holdsCount"] = cmd.get("holdsCount") or 0
        new_state["routeIndex"] = incoming_route_index
        if cmd.get("routesCount") is not None:
            new_state["routesCount"] = cmd.get("routesCount")
        if cmd.get("holdsCounts") is not None:
            new_state["holdsCounts"] = cmd.get("holdsCounts")

        competitors = _normalize_competitors(cmd.get("competitors"))
        new_state["competitors"] = competitors
        new_state["currentClimber"] = competitors[0]["nume"] if competitors else ""
        new_state["preparingClimber"] = (
            competitors[1]["nume"] if len(competitors) > 1 else ""
        )

        new_state["started"] = False
        new_state["timerState"] = "idle"
        new_state["holdCount"] = 0.0
        new_state["lastRegisteredTime"] = None
        new_state["remaining"] = None
        # Clear previous contest results only when starting a fresh contest in this box.
        # For multi-route contests, INIT_ROUTE for routeIndex > 1 must preserve prior route scores/times.
        if incoming_route_index == 1:
            new_state["scores"] = {}
            new_state["times"] = {}
        else:
            if not isinstance(new_state.get("scores"), dict):
                new_state["scores"] = {}
            if not isinstance(new_state.get("times"), dict):
                new_state["times"] = {}

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
        if "registeredTime" in cmd:
            candidate = _coerce_optional_time(cmd.get("registeredTime"))
            if candidate is not None:
                new_state["lastRegisteredTime"] = candidate
        snapshot_required = True

    elif ctype == "TIMER_SYNC":
        new_state["remaining"] = cmd.get("remaining")

    elif ctype == "SUBMIT_SCORE":
        raw_time = cmd.get("registeredTime")
        if raw_time is None:
            raw_time = new_state.get("lastRegisteredTime")
        effective_time = _coerce_optional_time(raw_time)
        payload["registeredTime"] = effective_time

        competitors = new_state.get("competitors") or []
        idx = None
        if "idx" in cmd:
            raw_idx = cmd.get("idx")
            if raw_idx not in (None, ""):
                idx = _coerce_idx(raw_idx)
                if idx is None:
                    raise ValueError("SUBMIT_SCORE idx must be an int or numeric string")
        elif "competitorIdx" in cmd:
            raw_idx = cmd.get("competitorIdx")
            if raw_idx not in (None, ""):
                idx = _coerce_idx(raw_idx)
                if idx is None:
                    raise ValueError(
                        "SUBMIT_SCORE competitorIdx must be an int or numeric string"
                    )

        competitor_name = cmd.get("competitor")
        if idx is not None:
            if idx < 0 or idx >= len(competitors):
                raise ValueError("SUBMIT_SCORE idx out of range")
            comp = competitors[idx]
            if not isinstance(comp, dict):
                raise ValueError("SUBMIT_SCORE idx refers to invalid competitor")
            resolved_name = comp.get("nume")
            if not isinstance(resolved_name, str) or not resolved_name.strip():
                raise ValueError("SUBMIT_SCORE idx refers to invalid competitor")
            competitor_name = resolved_name
            payload["competitor"] = competitor_name

        active_name = new_state.get("currentClimber") or ""
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

        if competitors:
            for comp in competitors:
                if not isinstance(comp, dict):
                    continue
                if comp.get("nume") == competitor_name:
                    comp["marked"] = True
                    break
            # Advance only when we submit the active climber (matches ContestPage behavior).
            if competitor_name and competitor_name == active_name:
                next_active = _compute_preparing_climber(competitors, active_name)
                new_state["currentClimber"] = next_active
            new_state["preparingClimber"] = _compute_preparing_climber(
                competitors, new_state.get("currentClimber") or ""
            )
        snapshot_required = True

    elif ctype == "SET_TIME_CRITERION":
        if cmd.get("timeCriterionEnabled") is not None:
            new_state["timeCriterionEnabled"] = bool(cmd.get("timeCriterionEnabled"))
        snapshot_required = True

    elif ctype == "RESET_BOX":
        import uuid

        new_state["initiated"] = False
        new_state["currentClimber"] = ""
        new_state["preparingClimber"] = ""
        new_state["started"] = False
        new_state["timerState"] = "idle"
        new_state["holdCount"] = 0.0
        new_state["lastRegisteredTime"] = None
        new_state["remaining"] = None
        new_state["scores"] = {}
        new_state["times"] = {}
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
