from escalada_core import apply_command, default_state, parse_timer_preset
from escalada_core.validation import ValidatedCmd


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

def test_init_route_preserves_competitor_club():
    state = default_state("sid-club")
    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 1,
            "holdsCount": 5,
            "competitors": [{"nume": "Alex", "club": "CSM", "marked": False}],
        },
    )
    assert state["competitors"][0]["nume"] == "Alex"
    assert state["competitors"][0]["club"] == "CSM"


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


def test_reset_partial_unmark_all_restarts_box_competition():
    state = default_state("sid-rp")
    old_session = state["sessionId"]
    state.update(
        {
            "initiated": True,
            "categorie": "Cat",
            "routesCount": 2,
            "holdsCounts": [10, 12],
            "routeIndex": 2,
            "holdsCount": 12,
            "timerPresetSec": 60,
            "timerState": "running",
            "started": True,
            "remaining": 12.0,
            "holdCount": 5.0,
            "lastRegisteredTime": 33.3,
            "scores": {"Alex": [1, 2]},
            "times": {"Alex": [None, 10.0]},
            "competitors": [{"nume": "Alex", "marked": True}, {"nume": "Bob", "marked": True}],
            "currentClimber": "Bob",
            "preparingClimber": "",
        }
    )

    outcome = apply_command(state, {"type": "RESET_PARTIAL", "boxId": 1, "unmarkAll": True})
    st = outcome.state

    assert st["initiated"] is False
    assert st["sessionId"] != old_session
    assert st["routeIndex"] == 1
    assert st["holdsCount"] == 10
    assert st["timerState"] == "idle"
    assert st["started"] is False
    assert st.get("remaining") == 60.0
    assert st["holdCount"] == 0.0
    assert st.get("lastRegisteredTime") is None
    assert st.get("scores") == {}
    assert st.get("times") == {}
    assert st["currentClimber"] == ""
    assert st["preparingClimber"] == ""
    assert all((isinstance(c, dict) and c.get("marked") is False) for c in st.get("competitors") or [])


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
    assert payload["type"] == "SET_TIME_CRITERION"
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
    assert state["times"]["A"][0] == 12

    outcome = apply_command(state, {"type": "RESET_BOX"})
    assert outcome.state["initiated"] is False
    assert outcome.state["competitors"] == []


def test_init_route_preserves_scores_for_next_route_and_clears_on_route_1():
    state = default_state("sid-multi")
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
    apply_command(
        state,
        {"type": "SUBMIT_SCORE", "competitor": "A", "score": 7, "registeredTime": 12.0},
    )
    assert state["scores"]["A"][0] == 7

    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 2,
            "holdsCount": 4,
            "competitors": [{"nume": "A", "marked": False}, {"nume": "B", "marked": False}],
        },
    )
    assert state["scores"]["A"][0] == 7

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
    assert state["scores"] == {}
    assert state["times"] == {}


def test_validation_accepts_submit_score_idx_alias():
    cmd = ValidatedCmd(boxId=1, type="SUBMIT_SCORE", idx=0, score=5.0)
    assert cmd.idx == 0
    assert cmd.competitor is None
    assert cmd.competitorIdx is None


def test_last_registered_time_none_or_invalid_does_not_crash():
    state = default_state("sid-lrt")
    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 1,
            "holdsCount": 3,
            "competitors": [{"nume": "A"}],
        },
    )
    apply_command(state, {"type": "REGISTER_TIME", "registeredTime": "abc"})
    outcome = apply_command(
        state, {"type": "SUBMIT_SCORE", "competitor": "A", "score": 6}
    )
    assert outcome.snapshot_required
    assert outcome.state["lastRegisteredTime"] is None
    assert outcome.state["times"] == {}


def test_register_time_preserves_float_and_ignores_none():
    state = default_state("sid-rt")
    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 1,
            "holdsCount": 3,
            "competitors": [{"nume": "A"}],
        },
    )
    apply_command(state, {"type": "REGISTER_TIME", "registeredTime": 15.5})
    assert state["lastRegisteredTime"] == 15.5
    apply_command(state, {"type": "REGISTER_TIME", "registeredTime": None})
    assert state["lastRegisteredTime"] == 15.5


def test_submit_score_accepts_idx_zero():
    state = default_state("sid-idx-0")
    apply_command(
        state,
        {
            "type": "INIT_ROUTE",
            "boxId": 1,
            "routeIndex": 1,
            "holdsCount": 4,
            "competitors": [{"nume": "A"}, {"nume": "B"}],
        },
    )
    outcome = apply_command(
        state, {"type": "SUBMIT_SCORE", "idx": 0, "score": 8, "registeredTime": 15.9}
    )
    assert outcome.state["scores"]["A"][0] == 8
    assert outcome.state["times"]["A"][0] == 15.9
    assert outcome.state["currentClimber"] == "B"
    assert outcome.state["competitors"][0]["marked"] is True


def test_submit_score_ignores_empty_idx_when_competitor_present():
    state = default_state("sid-idx-empty")
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
    outcome = apply_command(
        state,
        {
            "type": "SUBMIT_SCORE",
            "idx": None,
            "competitor": "A",
            "score": 9.1,
            "registeredTime": 11.7,
        },
    )
    assert outcome.state["scores"]["A"][0] == 9.1
    assert outcome.state["times"]["A"][0] == 11.7
    assert outcome.state["currentClimber"] == "B"
