"""Unit tests for application state machine."""
import pytest
from jobpilot.core.state_machine import (
    can_transition,
    validate_transition,
    StateMachineError,
    TRANSITIONS,
    TERMINAL_STATES,
    INITIAL_STATE,
)


class TestStateMachine:
    def test_initial_state(self):
        assert INITIAL_STATE == "DISCOVERED"

    def test_valid_transition_discovered_to_analyzing(self):
        assert can_transition("DISCOVERED", "ANALYZING")

    def test_valid_transition_submitted_to_interview(self):
        assert can_transition("CONFIRMED", "INTERVIEW")

    def test_invalid_transition_rejected_to_anything(self):
        assert not can_transition("REJECTED", "MATCHED")
        assert not can_transition("REJECTED", "ANALYZING")
        assert not can_transition("REJECTED", "INTERVIEW")

    def test_terminal_states_have_no_outgoing(self):
        for state in TERMINAL_STATES:
            assert TRANSITIONS.get(state, set()) == set(), f"{state} should be terminal"

    def test_validate_raises_on_invalid(self):
        with pytest.raises(StateMachineError):
            validate_transition("REJECTED", "MATCHED")

    def test_validate_raises_backward_transition(self):
        with pytest.raises(StateMachineError):
            validate_transition("SUBMITTED", "DISCOVERED")

    def test_validate_passes_valid(self):
        validate_transition("DISCOVERED", "ANALYZING")  # should not raise

    def test_full_happy_path(self):
        """Walk through the complete happy path without errors."""
        path = [
            "DISCOVERED", "ANALYZING", "MATCHED", "SHORTLISTED",
            "RESUME_GENERATED", "COVER_LETTER_GENERATED", "READY_FOR_REVIEW",
            "APPROVED", "APPLICATION_STARTED", "SUBMITTED", "CONFIRMED",
            "INTERVIEW", "OFFER",
        ]
        for i in range(len(path) - 1):
            assert can_transition(path[i], path[i+1]), f"Expected {path[i]}→{path[i+1]} to be valid"

    def test_rejection_from_any_early_state(self):
        rejectable = ["DISCOVERED", "ANALYZING", "MATCHED", "SHORTLISTED", "READY_FOR_REVIEW"]
        for state in rejectable:
            assert can_transition(state, "REJECTED"), f"Should be able to reject from {state}"
