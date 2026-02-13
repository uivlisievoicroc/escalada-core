"""Type definitions for contest state and commands."""
from __future__ import annotations

from typing import Any, List, Optional, TypedDict


class Competitor(TypedDict, total=False):
    """A competitor entry in the competitors list."""
    nume: str
    club: Optional[str]
    marked: bool


class ContestState(TypedDict, total=False):
    """
    TypedDict representing the contest box state.
    
    All fields are optional (total=False) for backwards compatibility,
    but in practice most will be present after initialization.
    """
    # Session management
    sessionId: str
    boxVersion: int
    
    # Initialization state
    initiated: bool
    categorie: str
    
    # Route configuration
    routeIndex: int
    routesCount: int
    holdsCount: int  # Max holds for current route
    holdsCounts: List[int]  # Max holds per route
    
    # Timer state
    timerState: str  # 'idle' | 'running' | 'paused' | 'stopped'
    timerPreset: Optional[str]  # e.g., "05:00"
    timerPresetSec: Optional[int]  # e.g., 300
    remaining: Optional[float]  # Seconds remaining
    timerRemainingSec: Optional[float]  # Server-side remaining (authoritative)
    timerEndsAtMs: Optional[int]  # Epoch ms when timer reaches 0
    started: bool
    
    # Current climber progress
    holdCount: float  # Current hold (supports 0.1 increments)
    currentClimber: str
    preparingClimber: str
    lastRegisteredTime: Optional[float]
    
    # Competitors list
    competitors: List[Competitor]
    
    # Time criterion (for ranking tiebreaks)
    timeCriterionEnabled: bool
    # Last user preference for top-3 time tiebreak ("yes" | "no"), if any.
    timeTiebreakPreference: Optional[str]
    # Fingerprint of the currently resolved eligible-tie event.
    timeTiebreakResolvedFingerprint: Optional[str]
    # Decision applied to the resolved fingerprint ("yes" | "no").
    timeTiebreakResolvedDecision: Optional[str]
    # Per-event decisions keyed by tie fingerprint ("tb3:...": "yes" | "no").
    timeTiebreakDecisions: dict[str, str]
    # Last user preference for previous-rounds tiebreak ("yes" | "no"), if any.
    prevRoundsTiebreakPreference: Optional[str]
    # Fingerprint of the currently resolved previous-rounds eligible-tie event.
    prevRoundsTiebreakResolvedFingerprint: Optional[str]
    # Decision applied to the resolved fingerprint ("yes" | "no").
    prevRoundsTiebreakResolvedDecision: Optional[str]
    # Per-event previous-rounds decisions keyed by tie fingerprint ("tb3:...": "yes" | "no").
    prevRoundsTiebreakDecisions: dict[str, str]
    # Manual winner/order keyed by tie fingerprint; used when previous-rounds decision is "yes".
    prevRoundsTiebreakOrders: dict[str, list[str]]
    # Manual previous-rounds rank map keyed by tie fingerprint.
    # Example: {"tb3:...": {"A": 1, "B": 2, "C": 2}}
    prevRoundsTiebreakRanks: dict[str, dict[str, int]]
    # Stable previous-rounds ranks keyed by logical tie lineage (route+performance).
    prevRoundsTiebreakLineageRanks: dict[str, dict[str, int]]


class CommandPayload(TypedDict, total=False):
    """
    TypedDict for command payloads sent to apply_command().
    
    Fields vary by command type.
    """
    # Common
    type: str
    boxId: int
    sessionId: Optional[str]
    boxVersion: Optional[int]
    actionId: Optional[str]
    
    # PROGRESS_UPDATE
    delta: Optional[float]
    
    # SUBMIT_SCORE
    score: Optional[float]
    competitor: Optional[str]
    competitorIdx: Optional[int]
    idx: Optional[int]
    registeredTime: Optional[float]
    
    # INIT_ROUTE
    routeIndex: Optional[int]
    holdsCount: Optional[int]
    routesCount: Optional[int]
    holdsCounts: Optional[List[int]]
    competitors: Optional[List[dict]]
    categorie: Optional[str]
    timerPreset: Optional[str]
    
    # SET_TIME_CRITERION
    timeCriterionEnabled: Optional[bool]
    # SET_TIME_TIEBREAK_DECISION
    timeTiebreakDecision: Optional[str]
    timeTiebreakFingerprint: Optional[str]
    # SET_PREV_ROUNDS_TIEBREAK_DECISION
    prevRoundsTiebreakDecision: Optional[str]
    prevRoundsTiebreakFingerprint: Optional[str]
    prevRoundsTiebreakLineageKey: Optional[str]
    prevRoundsTiebreakOrder: Optional[List[str]]
    prevRoundsTiebreakRanksByName: Optional[dict[str, int]]
    
    # TIMER_SYNC
    remaining: Optional[float]


# Type alias for backwards compatibility with existing Dict[str, Any] usage
StateDict = ContestState
CmdDict = CommandPayload
