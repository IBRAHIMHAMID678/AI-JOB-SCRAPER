"""
Internal event bus for JOBPILOT agent coordination.
Agents publish events; other agents subscribe to relevant ones.
Uses an in-process pub/sub with queue-based delivery.
Swap for Redis pub/sub in a multi-process deployment.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .logging import get_logger

logger = get_logger(__name__)

# ── Event types ───────────────────────────────────────────────────────────────

class EventType:
    JOB_DISCOVERED = "JOB_DISCOVERED"
    JOB_NORMALIZED = "JOB_NORMALIZED"
    JOB_DEDUPLICATED = "JOB_DEDUPLICATED"
    JOB_ANALYZED = "JOB_ANALYZED"
    JOB_MATCHED = "JOB_MATCHED"
    JOB_REJECTED = "JOB_REJECTED"
    RESUME_REQUESTED = "RESUME_REQUESTED"
    RESUME_GENERATED = "RESUME_GENERATED"
    COVER_LETTER_REQUESTED = "COVER_LETTER_REQUESTED"
    COVER_LETTER_GENERATED = "COVER_LETTER_GENERATED"
    APPLICATION_READY = "APPLICATION_READY"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPLICATION_APPROVED = "APPLICATION_APPROVED"
    APPLICATION_REJECTED = "APPLICATION_REJECTED"
    APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
    APPLICATION_CONFIRMED = "APPLICATION_CONFIRMED"
    EMAIL_RECEIVED = "EMAIL_RECEIVED"
    INTERVIEW_DETECTED = "INTERVIEW_DETECTED"
    FOLLOWUP_DUE = "FOLLOWUP_DUE"
    AGENT_FAILED = "AGENT_FAILED"
    PIPELINE_STARTED = "PIPELINE_STARTED"
    PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
    NOTIFICATION_SENT = "NOTIFICATION_SENT"


@dataclass
class Event:
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ── Event bus ─────────────────────────────────────────────────────────────────

class EventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[Event] = queue.Queue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        self._queue.put_nowait(event)

    def emit(self, event_type: str, payload: Dict[str, Any] = None, correlation_id: str = None) -> None:
        self.publish(Event(type=event_type, payload=payload or {}, correlation_id=correlation_id))

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._dispatch_loop, daemon=True, name="event-bus")
        self._worker_thread.start()
        logger.info("Event bus started")

    def stop(self) -> None:
        self._running = False
        self._queue.put_nowait(None)  # sentinel
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = self._queue.get(timeout=1)
                if event is None:
                    break
                self._dispatch(event)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error("Event dispatch error: %s", exc)

    def _dispatch(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.type, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.error("Handler %s failed for event %s: %s", handler.__name__, event.type, exc)


bus = EventBus()
