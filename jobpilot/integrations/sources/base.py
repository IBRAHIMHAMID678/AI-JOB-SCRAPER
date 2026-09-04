"""
Base class for all job source adapters.
Each source is a plugin that implements fetch() and returns List[RawJob].
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import List, Optional

from ...core.config import settings
from ...core.logging import get_logger
from ...core.schemas import RawJob
from ...core.security import sanitize_url, detect_prompt_injection


class JobSourceAdapter(ABC):
    """
    Contract for all job source plugins.

    Subclasses must implement:
      - source_name: str
      - fetch() -> List[RawJob]
    """

    source_name: str = "unknown"
    rate_limit_delay: float = 0.5
    max_retries: int = 1
    timeout: int = 10

    def __init__(self) -> None:
        self.logger = get_logger(f"sources.{self.source_name}")
        self._last_request_time: float = 0.0

    def get_jobs(self) -> List[RawJob]:
        """
        Public entry point with rate limiting, retries, and validation.
        """
        self._throttle()
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                raw_jobs = self.fetch()
                validated = self._validate_and_clean(raw_jobs)
                self.logger.info("[%s] Fetched %d valid jobs", self.source_name, len(validated))
                return validated
            except Exception as exc:
                last_error = exc
                self.logger.warning("[%s] Attempt %d/%d failed: %s", self.source_name, attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)

        self.logger.error("[%s] All retries exhausted: %s", self.source_name, last_error)
        return []

    @abstractmethod
    def fetch(self) -> List[RawJob]:
        """Fetch raw jobs from the source. May raise on failure."""

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _validate_and_clean(self, jobs: List[RawJob]) -> List[RawJob]:
        """
        Filter out jobs with invalid URLs and scan for prompt injection.
        This protects the system from malicious job listings.
        """
        clean: List[RawJob] = []
        for job in jobs:
            # URL safety check
            safe_url = sanitize_url(job.application_url)
            if not safe_url:
                self.logger.debug("Dropped job with unsafe URL: %s", job.application_url[:100])
                continue

            # Prompt injection scan on description
            if job.description:
                suspicious, pattern = detect_prompt_injection(job.description)
                if suspicious:
                    self.logger.warning(
                        "[SECURITY] Prompt injection attempt in job '%s' at '%s': matched '%s'",
                        job.title, job.company, pattern
                    )
                    # We keep the job but flag it — the description will be sanitized before LLM use
                    job.extra["_injection_flagged"] = True
                    job.extra["_injection_pattern"] = pattern

            clean.append(job)
        return clean
