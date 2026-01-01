"""
Input validation schemas using Pydantic v2
Validates all command types and API inputs
"""

import logging
import re
from typing import Dict, List, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ==================== VALIDATOR FUNCTIONS ====================


class ValidatedCmd(BaseModel):
    """Enhanced Cmd model with comprehensive validation"""

    # Accept -1 as sentinel for global commands (e.g., SET_TIME_CRITERION)
    boxId: int = Field(
        ..., ge=-1, le=9999, description="Box ID (-1 for global, 0-9999 for boxes)"
    )
    type: str = Field(..., min_length=1, max_length=50, description="Command type")

    # Generic optional fields with validation
    delta: Optional[float] = Field(
        None, ge=-10.0, le=10.0, description="Progress delta (-10 to +10)"
    )
    score: Optional[float] = Field(None, ge=0.0, le=100.0, description="Score (0-100)")
    competitor: Optional[str] = Field(
        None, min_length=1, max_length=255, description="Competitor name"
    )
    registeredTime: Optional[float] = Field(
        None, ge=0, le=3600, description="Registered time (0-3600 seconds)"
    )

    # INIT_ROUTE fields
    routeIndex: Optional[int] = Field(
        None, gt=0, le=999, description="Route index (1-999)"
    )
    holdsCount: Optional[int] = Field(
        None, ge=0, le=100, description="Hold count (0-100)"
    )
    competitors: Optional[List[Dict]] = Field(None, description="Competitors list")
    categorie: Optional[str] = Field(None, max_length=100, description="Category name")
    timerPreset: Optional[str] = Field(
        None, max_length=20, description="Timer preset (e.g., '05:00')"
    )

    # Timer sync
    remaining: Optional[float] = Field(
        None, ge=0, le=9999, description="Remaining seconds"
    )

    # Time criterion
    timeCriterionEnabled: Optional[bool] = None

    # STATE_SNAPSHOT fields (for REQUEST_STATE response)
    initiated: Optional[bool] = None
    holdsCount_snap: Optional[int] = Field(None, alias="holdsCount", ge=0, le=100)
    currentClimber: Optional[str] = Field(None, max_length=255)
    started: Optional[bool] = None
    timerState: Optional[str] = Field(None, description="'idle', 'running', 'paused'")
    holdCount: Optional[float] = Field(None, ge=0, le=10000)
    registeredTime_snap: Optional[float] = Field(None, ge=0)
    timerPreset_snap: Optional[str] = Field(None, max_length=20)
    timerPresetSec: Optional[int] = Field(None, ge=0, le=9999)

    # For SUBMIT_SCORE (competitor index)
    competitorIdx: Optional[int] = Field(None, ge=0, le=1000)

    # Session token to prevent state bleed between box deletions
    sessionId: Optional[str] = Field(
        None, min_length=1, max_length=64, description="Box session token"
    )

    # Box version for stale command detection (prevents commands from old browser tabs)
    boxVersion: Optional[int] = Field(
        None, ge=0, le=99999, description="Box version for stale command detection"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Validate command type is one of allowed types"""
        allowed_types = {
            "START_TIMER",
            "STOP_TIMER",
            "RESUME_TIMER",
            "PROGRESS_UPDATE",
            "REQUEST_ACTIVE_COMPETITOR",
            "SUBMIT_SCORE",
            "INIT_ROUTE",
            "REQUEST_STATE",
            "SET_TIME_CRITERION",
            "REGISTER_TIME",
            "TIMER_SYNC",
            "ACTIVE_CLIMBER",
            "RESET_BOX",
        }
        if v not in allowed_types:
            raise ValueError(f"type must be one of {allowed_types}, got {v}")
        return v

    @field_validator("competitor")
    @classmethod
    def validate_competitor_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate competitor name is safe"""
        if v is None:
            return v

        # Remove leading/trailing whitespace
        v = v.strip()

        # Check for malicious patterns (SQL injection, XSS)
        dangerous_patterns = [
            "--",
            "/*",
            "*/",
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "SELECT",
            "<script",
            "</script",
            "javascript:",
            "onerror=",
            "onclick=",
            "onload=",
            "<iframe",
            "<object",
            "<embed",
            "eval(",
            "alert(",
        ]

        v_upper = v.upper()
        for pattern in dangerous_patterns:
            if pattern.upper() in v_upper:
                raise ValueError(
                    f"competitor contains potentially dangerous pattern: {pattern}"
                )

        # Block SQL injection with quotes (but allow apostrophes in names like O'Connor)
        if "'" in v and ("OR" in v_upper or "AND" in v_upper or "=" in v):
            raise ValueError("competitor contains potential SQL injection pattern")

        # Block HTML tags
        if "<" in v and ">" in v:
            raise ValueError("competitor contains HTML tags")

        if len(v) == 0:
            raise ValueError("competitor name cannot be empty")

        return v

    @field_validator("categorie")
    @classmethod
    def validate_categorie(cls, v: Optional[str]) -> Optional[str]:
        """Validate category name"""
        if v is None:
            return v
        v = v.strip()
        if len(v) == 0:
            raise ValueError("categorie cannot be empty")
        return v

    @field_validator("timerPreset")
    @classmethod
    def validate_timer_preset(cls, v: Optional[str]) -> Optional[str]:
        """Validate timer preset format (MM:SS) and normalize to zero-padded format"""
        if v is None:
            return v

        v = v.strip()
        if not isinstance(v, str):
            raise ValueError("timerPreset must be string")

        # Expected format: MM:SS
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("timerPreset must be MM:SS format")

        try:
            mins = int(parts[0])
            secs = int(parts[1])

            if mins < 0 or mins > 99:
                raise ValueError("minutes must be 0-99")
            if secs < 0 or secs > 59:
                raise ValueError("seconds must be 0-59")

            # TASK 2.2: Auto-pad single-digit minutes (5:00 → 05:00)
            # This prevents frontend/backend mismatch where frontend sends "5:00"
            normalized = f"{mins:02d}:{secs:02d}"

            logger.debug(f"Normalized timerPreset: {v} → {normalized}")
            return normalized

        except (ValueError, IndexError):
            raise ValueError("timerPreset must be MM:SS format with valid numbers")

    @field_validator("competitors")
    @classmethod
    def validate_competitors_list(cls, v: Optional[List[Dict]]) -> Optional[List[Dict]]:
        """Validate competitors list format"""
        if v is None:
            return v

        if not isinstance(v, list):
            raise ValueError("competitors must be a list")

        if len(v) == 0:
            return v

        if len(v) > 500:
            raise ValueError("competitors cannot exceed 500 entries")

        for i, competitor in enumerate(v):
            if not isinstance(competitor, dict):
                raise ValueError(f"competitor {i} must be a dict")

            if "nume" not in competitor:
                raise ValueError(f'competitor {i} missing "nume" field')

            if not isinstance(competitor["nume"], str):
                raise ValueError(f'competitor {i} "nume" must be string')

            name = competitor["nume"].strip()
            if len(name) == 0:
                raise ValueError(f'competitor {i} "nume" cannot be empty')

            # Validate name safety
            dangerous_patterns = ["--", "/*", "<script", "javascript:", "onerror="]
            for pattern in dangerous_patterns:
                if pattern.upper() in name.upper():
                    raise ValueError(
                        f'competitor {i} "nume" contains dangerous pattern: {pattern}'
                    )

        return v

    @model_validator(mode="after")
    def validate_command_fields(self) -> Self:
        """Validate required fields based on command type"""
        cmd_type = self.type

        # Commands that require specific fields
        if cmd_type == "INIT_ROUTE":
            if self.routeIndex is None:
                raise ValueError("INIT_ROUTE requires routeIndex")
            if self.holdsCount is None:
                raise ValueError("INIT_ROUTE requires holdsCount")

        elif cmd_type == "PROGRESS_UPDATE":
            if self.delta is None:
                raise ValueError("PROGRESS_UPDATE requires delta")

        elif cmd_type == "SUBMIT_SCORE":
            if self.competitor is None and self.competitorIdx is None:
                raise ValueError("SUBMIT_SCORE requires competitor or competitorIdx")

        elif cmd_type == "REGISTER_TIME":
            if self.registeredTime is None and self.time is None:
                # allow time alias mapping at API layer
                raise ValueError("REGISTER_TIME requires registeredTime")

        elif cmd_type == "TIMER_SYNC":
            if self.remaining is None:
                raise ValueError("TIMER_SYNC requires remaining")

        elif cmd_type == "SET_TIME_CRITERION":
            if self.timeCriterionEnabled is None:
                raise ValueError("SET_TIME_CRITERION requires timeCriterionEnabled")

        return self

    # legacy alias for registeredTime
    time: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class RateLimitConfig:
    """Rate limiting configuration per command type"""

    # Max requests per minute for each command type
    PER_COMMAND_LIMITS = {
        "START_TIMER": 30,
        "STOP_TIMER": 30,
        "RESUME_TIMER": 30,
        "PROGRESS_UPDATE": 120,  # Frequent updates
        "REQUEST_ACTIVE_COMPETITOR": 30,
        "SUBMIT_SCORE": 60,
        "INIT_ROUTE": 10,
        "REQUEST_STATE": 30,
        "SET_TIME_CRITERION": 10,
        "REGISTER_TIME": 30,
        "TIMER_SYNC": 60,
    }


class InputSanitizer:
    """Utility class for input sanitization"""

    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        """Sanitize string input"""
        if not isinstance(value, str):
            return str(value)[:max_length]

        # Strip whitespace
        value = value.strip()

        # Limit length
        value = value[:max_length]

        # Remove null bytes
        value = value.replace("\0", "")

        return value

    @staticmethod
    def sanitize_competitor_name(name: str) -> str:
        """Sanitize competitor name for display - preserve Romanian diacritics"""
        name = InputSanitizer.sanitize_string(name, 255)

        # Remove dangerous characters but preserve letters (including diacritics), numbers, spaces, dashes, apostrophes
        # Allow Unicode letters (includes Romanian ș, ț, ă, â, î, etc.)
        # Remove only control characters, SQL/XSS special chars
        dangerous_chars = r'[<>{}[\]\\|;()&$`"\*\x00-\x1f\x7f]'
        name = re.sub(dangerous_chars, "", name)

        return name.strip()

    @staticmethod
    def sanitize_category(category: str) -> str:
        """Sanitize category name"""
        return InputSanitizer.sanitize_string(category, 100)

    @staticmethod
    def validate_and_sanitize_cmd(cmd_dict: dict) -> ValidatedCmd:
        """
        Validate and sanitize command dictionary

        Returns:
            ValidatedCmd: Validated command object

        Raises:
            ValueError: If validation fails
        """
        try:
            return ValidatedCmd(**cmd_dict)
        except Exception as e:
            logger.warning(f"Command validation failed: {e}")
            raise ValueError(f"Invalid command: {str(e)}")


# ==================== EXPORT ====================

__all__ = [
    "ValidatedCmd",
    "RateLimitConfig",
    "InputSanitizer",
]
