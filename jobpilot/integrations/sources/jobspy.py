"""
JobSpy adapter — scrapes LinkedIn and Indeed.

Anti-detection strategy:
  - LinkedIn: serial only, low result count, single global search (most sensitive)
  - Indeed:   limited parallel (max 2 threads), per-location, moderate count
  - Random jitter between every request (2–5 seconds)
  - Per-site circuit breaker: if blocked/429, skip remaining requests for that site
  - Small results_wanted per call to avoid deep pagination
"""
from __future__ import annotations

import random
import threading
import time
import concurrent.futures
from typing import List, Set

import pandas as pd

from ...core.config import settings
from ...core.logging import get_logger
from ...core.schemas import RawJob
from .base import JobSourceAdapter

logger = get_logger("sources.jobspy")

# Locations for Indeed (remote jobs from target countries)
_INDEED_LOCATIONS = [
    ("United States", "JobSpy-Indeed-US"),
    ("United Kingdom", "JobSpy-Indeed-UK"),
    ("Germany", "JobSpy-Indeed-DE"),
]

# India-based location exclusions
_INDIA_KEYWORDS = [
    "india", "bangalore", "bengaluru", "delhi", "mumbai",
    "hyderabad", "pune", "chennai", "kolkata", "noida", "gurgaon",
]

# Safe result cap per request to avoid deep pagination (bot trigger)
# User rule: LinkedIn freshness <= 5 days (120h); keep caps modest but usable.
_LINKEDIN_RESULTS_PER_TERM = 15
_INDEED_RESULTS_PER_TERM = 15

# Circuit breaker: track blocked sites within one run
_blocked_sites: Set[str] = set()
_blocked_lock = threading.Lock()


def _jitter(lo: float = 2.0, hi: float = 5.0) -> None:
    """Random human-like delay between requests."""
    time.sleep(random.uniform(lo, hi))


def _is_blocked(err: Exception) -> bool:
    msg = str(err).lower()
    return any(k in msg for k in ["429", "403", "captcha", "blocked", "rate limit", "too many"])


def _is_india_job(location: str) -> bool:
    loc = (location or "").lower()
    return any(city in loc for city in _INDIA_KEYWORDS)


class JobSpyAdapter(JobSourceAdapter):
    source_name = "jobspy"
    rate_limit_delay = 0.0  # We handle our own delays with jitter

    def fetch(self) -> List[RawJob]:
        from jobspy import scrape_jobs  # lazy import

        global _blocked_sites
        _blocked_sites = set()  # reset per run

        all_jobs: List[RawJob] = []

        # ── LinkedIn: serial, one at a time, global remote search ─────────────
        # LinkedIn is the most aggressive about bot detection.
        # We do NOT parallelise LinkedIn and keep result counts very low.
        if "linkedin" not in _blocked_sites:
            for term in settings.SEARCH_TERMS:
                if "linkedin" in _blocked_sites:
                    logger.warning("[JobSpy] LinkedIn blocked — skipping remaining terms")
                    break
                try:
                    _jitter(3.0, 6.0)  # longer wait before LinkedIn
                    df = scrape_jobs(
                        site_name=["linkedin"],
                        search_term=term,
                        location="Worldwide",
                        results_wanted=_LINKEDIN_RESULTS_PER_TERM,
                        hours_old=120,  # user rule: LinkedIn freshness <= 5 days
                        is_remote=True,
                    )
                    jobs = self._df_to_raw(df, "JobSpy-LinkedIn")
                    all_jobs.extend(j for j in jobs if not _is_india_job(j.location))
                    logger.info("[JobSpy] LinkedIn '%s': %d jobs", term, len(jobs))
                except Exception as exc:
                    if _is_blocked(exc):
                        with _blocked_lock:
                            _blocked_sites.add("linkedin")
                        logger.warning("[JobSpy] LinkedIn bot-detected, circuit open: %s", exc)
                    else:
                        logger.warning("[JobSpy] LinkedIn error for '%s': %s", term, exc)

        # ── Indeed: limited parallel (2 threads max), per location ────────────
        # Indeed is less aggressive than LinkedIn but still blocks heavy scraping.
        def scrape_indeed(term: str, location: str, label: str) -> List[RawJob]:
            if "indeed" in _blocked_sites:
                return []
            try:
                _jitter(2.0, 4.5)
                df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=term,
                    location=location,
                    results_wanted=_INDEED_RESULTS_PER_TERM,
                    hours_old=120,  # user rule: LinkedIn freshness <= 5 days
                    is_remote=True,
                )
                jobs = self._df_to_raw(df, label)
                return [j for j in jobs if not _is_india_job(j.location)]
            except Exception as exc:
                if _is_blocked(exc):
                    with _blocked_lock:
                        _blocked_sites.add("indeed")
                    logger.warning("[JobSpy] Indeed bot-detected, circuit open: %s", exc)
                else:
                    logger.warning("[JobSpy] Indeed error for '%s' @ %s: %s", term, location, exc)
                return []

        tasks = [
            (term, loc, label)
            for term in settings.SEARCH_TERMS
            for loc, label in _INDEED_LOCATIONS
        ]

        # max_workers=2 keeps concurrent Indeed hits low
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futures = [ex.submit(scrape_indeed, t, loc, lbl) for t, loc, lbl in tasks]
            for f in concurrent.futures.as_completed(futures):
                try:
                    all_jobs.extend(f.result())
                except Exception as exc:
                    logger.warning("[JobSpy] Indeed thread error: %s", exc)

        # De-dup by URL
        seen: set = set()
        unique: List[RawJob] = []
        for j in all_jobs:
            if j.application_url not in seen:
                seen.add(j.application_url)
                unique.append(j)

        logger.info("[JobSpy] Total unique jobs collected: %d", len(unique))
        return unique

    def _df_to_raw(self, df, source_label: str) -> List[RawJob]:
        results: List[RawJob] = []
        if df is None or df.empty:
            return results
        for _, row in df.iterrows():
            url = str(row.get("job_url", "")).strip()
            if not url or url in ("nan", ""):
                continue
            try:
                salary_raw = None
                if pd.notna(row.get("min_amount")):
                    salary_raw = f"{row.get('min_amount')} - {row.get('max_amount')} {row.get('currency', 'USD')}"
                results.append(RawJob(
                    title=str(row.get("title", "")),
                    company=str(row.get("company", "")),
                    location=str(row.get("location", "Remote")),
                    description=str(row.get("description", "")) if pd.notna(row.get("description")) else None,
                    application_url=url,
                    source=source_label,
                    salary_raw=salary_raw,
                    employment_type=str(row.get("job_type", "")) if pd.notna(row.get("job_type")) else None,
                ))
            except Exception as exc:
                self.logger.debug("Skipping malformed row: %s", exc)
        return results
