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
    
    # TIMER_SYNC
    remaining: Optional[float]


# Type alias for backwards compatibility with existing Dict[str, Any] usage
StateDict = ContestState
CmdDict = CommandPayload
