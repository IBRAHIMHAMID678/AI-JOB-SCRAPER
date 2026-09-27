"""
Base agent class for JOBPILOT.
Every agent inherits from BaseAgent, which provides:
  - structured logging with correlation IDs
  - automatic run tracking in the database
  - retry with exponential backoff
  - error handling and audit logging
  - event publishing
"""
from __future__ import annotations

import time
import traceback
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar

from ..core.config import settings
from ..core.database import db_session
from ..core.events import bus, EventType
from ..core.logging import get_logger, new_correlation_id

logger = get_logger(__name__)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class AgentError(Exception):
    """Raised by agents for expected, recoverable errors."""
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """
    Contract every JOBPILOT agent must fulfil:
      - name: unique agent identifier
      - run(input): execute the agent task and return structured output
      - _execute(input): the actual implementation
    """

    name: str = "base_agent"
    max_retries: int = 2
    retry_delay: float = 2.0

    def __init__(self) -> None:
        self.logger = get_logger(f"agents.{self.name}")
        self._run_id: Optional[str] = None

    def run(self, input_data: InputT, trigger: str = "manual") -> Optional[OutputT]:
        """
        Public entry point. Handles:
        - correlation ID
        - DB run tracking
        - retries
        - final error handling
        """
        cid = new_correlation_id()
        self._run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        attempt = 0

        self.logger.info("[%s] Starting (run=%s trigger=%s)", self.name, self._run_id, trigger)
        self._record_run_start(trigger, input_data)

        while attempt <= self.max_retries:
            try:
                result = self._execute(input_data)
                duration = (datetime.now(timezone.utc) - started_at).total_seconds()
                self.logger.info("[%s] Completed in %.2fs", self.name, duration)
                self._record_run_end(success=True, duration=duration)
                return result

            except AgentError as exc:
                if not exc.retryable or attempt >= self.max_retries:
                    self.logger.error("[%s] Failed (non-retryable): %s", self.name, exc)
                    self._record_run_end(success=False, error=str(exc))
                    bus.emit(EventType.AGENT_FAILED, {"agent": self.name, "error": str(exc), "run_id": self._run_id})
                    self._dead_letter(input_data, exc)
                    return None
                attempt += 1
                delay = self.retry_delay * (2 ** (attempt - 1))
                self.logger.warning("[%s] Retry %d/%d in %.1fs: %s", self.name, attempt, self.max_retries, delay, exc)
                time.sleep(delay)

            except Exception as exc:
                tb = traceback.format_exc()
                self.logger.error("[%s] Unexpected error: %s\n%s", self.name, exc, tb)
                self._record_run_end(success=False, error=str(exc))
                bus.emit(EventType.AGENT_FAILED, {"agent": self.name, "error": str(exc), "run_id": self._run_id})
                self._dead_letter(input_data, exc)
                return None

        return None

    def _dead_letter(self, input_data: Any, exc: Exception) -> None:
        """Item 34: durable dead-letter record for a failed agent run."""
        try:
            from ..core.dead_letter import write_dead_letter
            job_id = self._run_id
            for attr in ("source_job_id", "canonical_job_id", "id"):
                v = getattr(input_data, attr, None)
                if v:
                    job_id = str(v)
                    break
            if job_id == self._run_id and isinstance(input_data, dict):
                for k in ("source_job_id", "canonical_job_id", "id", "url"):
                    if input_data.get(k):
                        job_id = str(input_data[k])[:120]
                        break
            write_dead_letter(job_id, stage=f"agent:{self.name}", error=exc)
        except Exception:
            pass

    @abstractmethod
    def _execute(self, input_data: InputT) -> OutputT:
        """Implement agent logic here. May raise AgentError for retryable failures."""

    # ── DB tracking (non-critical — errors here must not crash the agent) ──────

    def _record_run_start(self, trigger: str, input_data: Any) -> None:
        try:
            from ..core.models import AgentRun, AgentStatus
            with db_session() as db:
                run = AgentRun(
                    id=self._run_id,
                    agent_name=self.name,
                    status=AgentStatus.RUNNING.value,
                    trigger=trigger,
                    input_summary=str(input_data)[:500],
                    started_at=datetime.now(timezone.utc),
                )
                db.add(run)
        except Exception as exc:
            self.logger.debug("Could not record run start: %s", exc)

    def _record_run_end(self, success: bool, duration: float = 0, error: str = None) -> None:
        try:
            from ..core.models import AgentRun, AgentStatus
            with db_session() as db:
                run = db.query(AgentRun).filter(AgentRun.id == self._run_id).first()
                if run:
                    run.status = AgentStatus.COMPLETED.value if success else AgentStatus.FAILED.value
                    run.completed_at = datetime.now(timezone.utc)
                    run.duration_seconds = duration
                    if error:
                        run.error_message = error[:1000]
        except Exception as exc:
            self.logger.debug("Could not record run end: %s", exc)

    def audit(self, action: str, resource_type: str = None, resource_id: str = None, details: Dict = None, severity: str = "info") -> None:
        """Write an audit log entry."""
        try:
            from ..core.models import AuditLog
            with db_session() as db:
                entry = AuditLog(
                    actor=f"agent:{self.name}",
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=details or {},
                    severity=severity,
                )
                db.add(entry)
        except Exception as exc:
            self.logger.debug("Could not write audit log: %s", exc)
