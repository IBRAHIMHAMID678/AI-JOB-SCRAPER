"""
Structured logging for JOBPILOT.
Outputs JSON lines in production; human-readable in debug mode.
Every log includes a correlation_id for full request traceability.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import settings

# Thread-local correlation ID (set per request/task)
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    cid = str(uuid.uuid4())[:8]
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    return _correlation_id.get() or "--------"


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "cid": get_correlation_id(),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            entry.update(record.extra)
        return json.dumps(entry, default=str)


class _TextFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        cid = get_correlation_id()
        return f"{color}[{ts}][{cid}][{record.levelname}] {record.getMessage()}{self.RESET}"


def setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(_TextFormatter())
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# ── SSE log queue (for live dashboard streaming) ──────────────────────────────

import queue

_sse_log_queue: queue.Queue = queue.Queue(maxsize=500)
_sse_job_queue: queue.Queue = queue.Queue(maxsize=200)
_sse_pending_queue: queue.Queue = queue.Queue(maxsize=200)


def sse_log(message: str) -> None:
    """Emit a log line to the SSE dashboard stream."""
    try:
        _sse_log_queue.put_nowait(message)
    except queue.Full:
        pass  # Drop oldest not newest — non-critical


def sse_emit_job(job: Dict[str, Any]) -> None:
    try:
        _sse_job_queue.put_nowait(job)
    except queue.Full:
        pass


def sse_emit_pending(job: Dict[str, Any]) -> None:
    try:
        _sse_pending_queue.put_nowait(job)
    except queue.Full:
        pass


setup_logging()
