from escalada_core import apply_command, default_state, parse_timer_preset


def test_default_state_has_session_and_defaults():
    state = default_state()
    assert state["sessionId"]
    assert state["holdCount"] == 0.0
    assert state["timerState"] == "idle"
    assert state["boxVersion"] == 0


def test_parse_timer_preset_handles_valid_and_invalid():
    assert parse_timer_preset("05:30") == 330
    assert parse_timer_preset("00:00") == 0
    assert parse_timer_preset(None) is None
    assert parse_timer_preset("invalid") is None


def test_init_route_sets_competitors_and_timer():
    state = default_state("session-1")
    outcome = apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 2,
            "holdsCount": 5,
            "competitors": [{"nume": "Alex", "marked": False}, {"nume": "Bob"}],
            "timerPreset": "05:00",
            "categorie": "Youth",
        },
    )
    assert outcome.snapshot_required
    assert outcome.state["initiated"] is True
    assert outcome.state["routeIndex"] == 2
    assert outcome.state["holdsCount"] == 5
    assert outcome.state["currentClimber"] == "Alex"
    assert outcome.state["timerPresetSec"] == 300
    assert outcome.cmd_payload["sessionId"] == state["sessionId"]


def test_progress_update_respects_bounds():
    state = default_state("sid-1")
    state["holdsCount"] = 3
    outcome = apply_command(state, {"type": "PROGRESS_UPDATE", "delta": 5})
    assert outcome.snapshot_required
    assert outcome.state["holdCount"] == 3.0  # capped
    outcome = apply_command(state, {"type": "PROGRESS_UPDATE", "delta": -10})
    assert outcome.state["holdCount"] == 0.0  # floored


def test_submit_score_marks_competitor_and_resets_timer():
    state = default_state("sid-2")
    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "competitors": [{"nume": "Alice"}],
            "routeIndex": 1,
            "holdsCount": 4,
        },
    )
    outcome = apply_command(
        state,
        {
            "type": "SUBMIT_SCORE",
            "competitor": "Alice",
            "score": 7.5,
            "registeredTime": 12.3,
        },
    )
    assert outcome.snapshot_required
    assert outcome.state["scores"]["Alice"][0] == 7.5
    assert outcome.state["times"]["Alice"][0] == 12.3
    assert outcome.state["timerState"] == "idle"
    assert outcome.state["holdCount"] == 0.0
    assert outcome.state["currentClimber"] == ""


def test_reset_box_generates_new_session_and_clears_state():
    state = default_state("sid-3")
    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "competitors": [{"nume": "A"}],
            "routeIndex": 1,
            "holdsCount": 2,
        },
    )
    old_session = state["sessionId"]
    outcome = apply_command(state, {"type": "RESET_BOX"})
    assert outcome.snapshot_required
    assert outcome.state["sessionId"] != old_session
    assert outcome.state["initiated"] is False
    assert outcome.state["competitors"] == []
    assert outcome.state["timerPreset"] is None


def test_validation_checks_session_and_version():
    from escalada_core import validate_session_and_version

    state = default_state("sid-4")
    state["boxVersion"] = 2
    missing = validate_session_and_version(state, {"type": "START_TIMER"}, require_session=True)
    assert missing is not None and missing.status_code == 400

    stale_session = validate_session_and_version(
        state, {"type": "START_TIMER", "sessionId": "other"}, require_session=True
    )
    assert stale_session is not None and stale_session.kind == "stale_session"

    stale_version = validate_session_and_version(
        state,
        {"type": "START_TIMER", "sessionId": "sid-4", "boxVersion": 1},
        require_session=True,
    )
    assert stale_version is not None and stale_version.kind == "stale_version"

    ok = validate_session_and_version(
        state,
        {"type": "START_TIMER", "sessionId": "sid-4", "boxVersion": 3},
        require_session=True,
    )
    assert ok is None


def test_toggle_time_criterion_returns_payload():
    from escalada_core import toggle_time_criterion

    new_value, payload = toggle_time_criterion(False, True)
    assert new_value is True
    assert payload["type"] == "TIME_CRITERION"
    assert payload["timeCriterionEnabled"] is True


def test_full_contest_flow_sequence():
    """Simulate INIT -> START -> PROGRESS -> SUBMIT -> RESET in pure core."""
    state = default_state("sid-flow")

    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 1,
            "holdsCount": 3,
            "competitors": [{"nume": "A"}, {"nume": "B"}],
        },
    )
    assert state["initiated"] and state["currentClimber"] == "A"

    apply_command(state, {"type": "START_TIMER"})
    apply_command(state, {"type": "PROGRESS_UPDATE", "delta": 1})
    apply_command(
        state,
        {"type": "SUBMIT_SCORE", "competitor": "A", "score": 7, "registeredTime": 12.0},
    )
    assert state["started"] is False
    assert state["currentClimber"] == "B"
    assert state["scores"]["A"][0] == 7
    assert state["times"]["A"][0] == 12.0

    outcome = apply_command(state, {"type": "RESET_BOX"})
    assert outcome.state["initiated"] is False
    assert outcome.state["competitors"] == []
