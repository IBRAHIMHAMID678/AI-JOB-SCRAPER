"""
Formal application state machine for JOBPILOT.
Every state transition is validated and logged.
Invalid transitions raise StateMachineError.
"""
from __future__ import annotations

from typing import Dict, Optional, Set

from .logging import get_logger

logger = get_logger(__name__)


class StateMachineError(Exception):
    pass


# ── Valid transitions ─────────────────────────────────────────────────────────
# Maps each state to the set of states it can transition INTO.

TRANSITIONS: Dict[str, Set[str]] = {
    "DISCOVERED": {"ANALYZING", "REJECTED"},
    "ANALYZING": {"MATCHED", "REJECTED"},
    "MATCHED": {"SHORTLISTED", "REJECTED"},
    "REJECTED": set(),  # terminal
    "SHORTLISTED": {"RESUME_GENERATED", "REJECTED"},
    "RESUME_GENERATED": {"COVER_LETTER_GENERATED", "REJECTED"},
    "COVER_LETTER_GENERATED": {"READY_FOR_REVIEW"},
    "READY_FOR_REVIEW": {"APPROVED", "REJECTED"},
    "APPROVED": {"APPLICATION_STARTED", "REJECTED"},
    "APPLICATION_STARTED": {"SUBMITTED", "REJECTED"},
    "SUBMITTED": {"CONFIRMED", "REJECTED", "FOLLOW_UP"},
    "CONFIRMED": {"FOLLOW_UP", "INTERVIEW", "OFFER", "REJECTED", "OFFER_REJECTED"},
    "FOLLOW_UP": {"INTERVIEW", "OFFER", "REJECTED", "OFFER_REJECTED"},
    "INTERVIEW": {"OFFER", "REJECTED", "OFFER_REJECTED"},
    "OFFER": {"CONFIRMED", "OFFER_REJECTED", "WITHDRAWN"},
    "OFFER_REJECTED": set(),  # terminal
    "WITHDRAWN": set(),  # terminal
}

TERMINAL_STATES = {"REJECTED", "WITHDRAWN", "OFFER_REJECTED"}
INITIAL_STATE = "DISCOVERED"


def can_transition(from_state: str, to_state: str) -> bool:
    allowed = TRANSITIONS.get(from_state, set())
    return to_state in allowed


def validate_transition(from_state: str, to_state: str) -> None:
    if not can_transition(from_state, to_state):
        allowed = sorted(TRANSITIONS.get(from_state, set()))
        raise StateMachineError(
            f"Invalid transition: {from_state} → {to_state}. "
            f"Allowed from {from_state}: {allowed}"
        )


def transition(application, to_state: str, actor: str = "system", note: Optional[str] = None):
    """
    Transition an Application ORM object to a new state.
    Records an ApplicationEvent and commits via the caller's session.
    """
    from .models import ApplicationEvent, ApplicationStatus

    from_state = application.status
    validate_transition(from_state, to_state)

    application.status = to_state
    event = ApplicationEvent(
        application_id=application.id,
        from_status=from_state,
        to_status=to_state,
        actor=actor,
        note=note,
    )
    logger.info("Application %s: %s → %s (by %s)", application.id, from_state, to_state, actor)
    return event
