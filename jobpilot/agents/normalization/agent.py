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

# Item 23: explicit negations of remote work — "This is NOT a remote position"
_REMOTE_NEGATIONS = [
    r"\bnot\s+a\s+remote\b",
    r"\bnot\s+remote\b",
    r"\bno\s+remote\b",
    r"\bnon[\s-]?remote\b",
    r"\bonsite\s+only\b",
    r"\bon[\s-]?site\s+only\b",
    r"\bin[\s-]?office\s+only\b",
    r"\bremote\s+not\s+available\b",
    r"\bno\s+wfh\b",
]
_REMOTE_NEGATIONS_COMPILED = [re.compile(p, re.IGNORECASE) for p in _REMOTE_NEGATIONS]

# Generic location tokens that don't name a physical city
_GENERIC_REMOTE_LOCATIONS = ["remote", "worldwide", "anywhere", "global", "work from anywhere", "wfh"]

_EMPLOYMENT_MAP = {
    "full_time": ["full-time", "full time", "permanent"],
    "part_time": ["part-time", "part time"],
    "contract": ["contract", "contractor", "freelance", "consulting"],
    "internship": ["intern", "internship", "co-op"],
}

_CURRENCY_MAP = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "₨": "PKR",
    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "INR": "INR", "PKR": "PKR",
    "RS": "PKR",  # "Rs.", "Rs", "RS" → Pakistani Rupee (item 28)
}


def _norm_currency(sym: Optional[str]) -> Optional[str]:
    if not sym:
        return None
    return _CURRENCY_MAP.get(sym.strip().upper().rstrip("."))


# Item 28: second number optional ('$30/hr' must parse); PKR/Rs/₨ symbols;
# period capture (/hr|/mo|/yr|per month|per annum).
_SALARY_PATTERN = re.compile(
    r"(?P<cur1>\$|€|£|₹|₨|rs\.?|pkr|usd|eur|gbp|inr)?\s*"
    r"(?P<lo>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<k1>[kK])?"
    r"(?:\s*(?:-|to|–)\s*"
    r"(?P<cur2>\$|€|£|₹|₨|rs\.?|pkr|usd|eur|gbp|inr)?\s*"
    r"(?P<hi>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?P<k2>[kK])?"
    r")?"
    r"\s*(?P<period>/\s*(?:hr|hrs|h|hour|hours|mo|mos|month|months|yr|yrs|year|years)"
    r"|per\s+(?:hour|month|year|annum)|hourly|monthly|annually|yearly)?",
    re.IGNORECASE,
)


def _norm_period(raw: Optional[str]) -> Optional[str]:
    """Normalize a captured pay period to hourly/monthly/yearly."""
    if not raw:
        return None
    p = raw.lower().replace(" ", "").replace("/", "")
    if p in ("hr", "hrs", "h", "hour", "hours", "hourly", "perhour"):
        return "hourly"
    if p in ("mo", "mos", "month", "months", "monthly", "permonth"):
        return "monthly"
    if p in ("yr", "yrs", "year", "years", "annum", "perannum", "annually", "yearly", "peryear"):
        return "yearly"
    return None


def _parse_remote_type(location: str, description: str = "") -> str:
    text = (location + " " + description).lower()
    # Item 23: negations first — "This is NOT a remote position. Office in Berlin."
    if any(p.search(text) for p in _REMOTE_NEGATIONS_COMPILED):
        return "onsite"
    if any(k in text for k in _HYBRID_KEYWORDS):
        return "hybrid"
    if any(k in text for k in _REMOTE_KEYWORDS):
        return "remote"
    if any(k in text for k in _ONSITE_KEYWORDS):
        return "onsite"
    # Item 23: default to "unknown" when the location names a physical city
    loc = (location or "").strip().lower()
    if loc and not any(k in loc for k in _GENERIC_REMOTE_LOCATIONS):
        return "unknown"
    return "remote"  # default assumption for job boards with no location signal


def _parse_employment_type(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    raw_lower = raw.lower()
    for etype, keywords in _EMPLOYMENT_MAP.items():
        if any(k in raw_lower for k in keywords):
            return etype
    return "unknown"


def _parse_salary(salary_raw: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Returns (min, max, currency). Item 28: keep the legacy 3-value shape so
    existing tests/callers keep working; use _parse_salary_period for the period."""
    if not salary_raw:
        return None, None, None
    m = _SALARY_PATTERN.search(salary_raw)
    if not m:
        return None, None, None
    try:
        g = m.groupdict()
        lo_val = float(g["lo"].replace(",", "")) * (1000 if g["k1"] else 1)
        hi_raw = g.get("hi")
        hi_val = float(hi_raw.replace(",", "")) * (1000 if g["k2"] else 1) if hi_raw else lo_val
        currency = _norm_currency(g.get("cur1")) or _norm_currency(g.get("cur2")) or "USD"
        return lo_val, hi_val, currency
    except Exception:
        return None, None, None


def _parse_salary_period(salary_raw: Optional[str]) -> Optional[str]:
    """Returns hourly/monthly/yearly/None — kept separate from _parse_salary
    (item 28) so the parser's public shape is unchanged."""
    if not salary_raw:
        return None
    m = _SALARY_PATTERN.search(salary_raw)
    if not m:
        return None
    try:
        return _norm_period(m.groupdict().get("period"))
    except Exception:
        return None


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
                # Item 34: dead-letter record instead of a bare log line
                self.logger.warning("Failed to normalize job '%s': %s", raw.title, exc)
                try:
                    from ...core.dead_letter import write_dead_letter
                    write_dead_letter(
                        raw.source_job_id or raw.title,
                        stage="normalization",
                        error=exc,
                        extra={"title": raw.title, "company": raw.company, "source": raw.source},
                    )
                except Exception:
                    pass
        self.logger.info("Normalized %d/%d jobs", len(normalized), len(raw_jobs))
        return normalized

    def _normalize(self, raw: RawJob) -> NormalizedJob:
        loc = raw.location or "Remote"
        desc = raw.description or ""
        sal_min, sal_max, currency = _parse_salary(raw.salary_raw)
        sal_period = _parse_salary_period(raw.salary_raw)

        norm_co = re.sub(r"[^a-z0-9]", "", raw.company.lower())
        norm_ti = re.sub(r"[^a-z0-9]", "", raw.title.lower())
        # Item 24: canonical ID includes location + salary + description hash, so
        # "AI Engineer @ X (remote)" and "AI Engineer @ X (onsite Islamabad)" are
        # distinct opportunities instead of permanent duplicates.
        norm_lo = re.sub(r"[^a-z0-9]", "", loc.lower())
        sal_key = f"{sal_min or 0}-{sal_max or 0}-{currency or ''}-{sal_period or ''}"
        import hashlib
        desc_hash = hashlib.sha256(desc[:2000].encode()).hexdigest()[:12]
        canon_id = hashlib.sha256(
            f"{norm_co}::{norm_ti}::{norm_lo}::{sal_key}::{desc_hash}".encode()
        ).hexdigest()[:24]

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
