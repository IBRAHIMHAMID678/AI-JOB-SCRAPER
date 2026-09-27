"""
Dead-letter queue for JOBPILOT (item 34).

Jobs dropped by swallowed exceptions mid-pipeline get a durable record here
instead of vanishing behind a log line. One JSON object per line:
  {"timestamp": ..., "job_id": ..., "stage": ..., "error": ..., "extra": {...}}

Never raises — a failing dead-letter write must not mask the original error.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def dead_letter_path() -> str:
    # jobpilot/core/dead_letter.py → repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(repo_root, "dead_letter.jsonl")


def write_dead_letter(
    job_id: Any,
    stage: str,
    error: Any,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "job_id": str(job_id) if job_id else "unknown",
        "stage": stage,
        "error": str(error)[:2000],
    }
    if extra:
        record["extra"] = extra
    try:
        with open(dead_letter_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
