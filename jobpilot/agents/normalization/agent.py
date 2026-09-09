"""
Job Normalization Agent.
Converts RawJob (untrusted scraper output) into a canonical NormalizedJob.
All parsing is deterministic — no LLM calls needed here.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from ...core.schemas import NormalizedJob, RawJob
from ...core.security import hash_content, hash_url
from ..base import BaseAgent

_REMOTE_KEYWORDS = ["remote", "worldwide", "anywhere", "work from home", "wfh"]
_HYBRID_KEYWORDS = ["hybrid"]
_ONSITE_KEYWORDS = ["onsite", "on-site", "in-office", "office"]

_EMPLOYMENT_MAP = {
    "full_time": ["full-time", "full time", "permanent"],
    "part_time": ["part-time", "part time"],
    "contract": ["contract", "contractor", "freelance", "consulting"],
    "internship": ["intern", "internship", "co-op"],
}

_CURRENCY_MAP = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR",
    "USD": "USD", "EUR": "EUR", "GBP": "GBP",
}

_SALARY_PATTERN = re.compile(
    r"([$€£₹]?)\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([kK])?\s*(?:-|to|–)\s*([$€£₹]?)\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*([kK])?",
    re.IGNORECASE,
)


def _parse_remote_type(location: str, description: str = "") -> str:
    text = (location + " " + description).lower()
    if any(k in text for k in _REMOTE_KEYWORDS):
        if any(k in text for k in _HYBRID_KEYWORDS):
            return "hybrid"
        return "remote"
    if any(k in text for k in _HYBRID_KEYWORDS):
        return "hybrid"
    if any(k in text for k in _ONSITE_KEYWORDS):
        return "onsite"
    return "remote"  # default assumption for job boards


def _parse_employment_type(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    raw_lower = raw.lower()
    for etype, keywords in _EMPLOYMENT_MAP.items():
        if any(k in raw_lower for k in keywords):
            return etype
    return "unknown"


def _parse_salary(salary_raw: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str]]:
    if not salary_raw:
        return None, None, None
    m = _SALARY_PATTERN.search(salary_raw)
    if not m:
        return None, None, None
    try:
        sym1, lo, k1, sym2, hi, k2 = m.groups()
        lo_val = float(lo.replace(",", "")) * (1000 if k1 else 1)
        hi_val = float(hi.replace(",", "")) * (1000 if k2 else 1)
        currency = _CURRENCY_MAP.get(sym1 or sym2, "USD")
        return lo_val, hi_val, currency
    except Exception:
        return None, None, None


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw[:19], fmt)
        except ValueError:
            continue
    return None


class NormalizationAgent(BaseAgent[List[RawJob], List[NormalizedJob]]):
    name = "normalization_agent"

    def _execute(self, raw_jobs: List[RawJob]) -> List[NormalizedJob]:
        normalized: List[NormalizedJob] = []
        for raw in raw_jobs:
            try:
                n = self._normalize(raw)
                normalized.append(n)
            except Exception as exc:
                self.logger.warning("Failed to normalize job '%s': %s", raw.title, exc)
        self.logger.info("Normalized %d/%d jobs", len(normalized), len(raw_jobs))
        return normalized

    def _normalize(self, raw: RawJob) -> NormalizedJob:
        loc = raw.location or "Remote"
        desc = raw.description or ""
        sal_min, sal_max, currency = _parse_salary(raw.salary_raw)

        norm_co = re.sub(r"[^a-z0-9]", "", raw.company.lower())
        norm_ti = re.sub(r"[^a-z0-9]", "", raw.title.lower())
        import hashlib
        canon_id = hashlib.sha256(f"{norm_co}::{norm_ti}".encode()).hexdigest()[:24]

        return NormalizedJob(
            source_name=raw.source,
            source_job_id=raw.source_job_id,
            title=raw.title.strip(),
            company=raw.company.strip(),
            location=loc,
            remote_type=_parse_remote_type(loc, desc),
            employment_type=_parse_employment_type(raw.employment_type),
            salary_min=sal_min,
            salary_max=sal_max,
            currency=currency,
            salary_raw=raw.salary_raw,
            description=desc[:20000] if desc else None,
            skills_raw=list(set(raw.skills_raw)),
            posting_date=_parse_date(raw.posting_date),
            application_url=raw.application_url,
            url_hash=hash_url(raw.application_url),
            content_hash=hash_content(raw.title, raw.company, desc),
            canonical_job_id=canon_id,
        )
