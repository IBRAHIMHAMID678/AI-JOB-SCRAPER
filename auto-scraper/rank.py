"""Rank: score filtered jobs so the best fits surface first."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from requirements import ROLE_KEYWORDS, PAY_TARGET_MIN, PAY_TARGET_MAX, PREFERRED_AGE_DAYS, PRIORITY_SOURCES

_STACK_BONUS = ["rag", "llm", "langchain", "fastapi", "python", "pytorch",
                "transformer", "vector", "embedding", "agent", "openai", "ollama"]


def score(job: dict, reasons: list[str]) -> tuple[float, list[str]]:
    s = 0.0
    notes: list[str] = []
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    blob = f"{title} {desc}"

    # Role title strength
    if re.search(r"\bai\b.*\bengineer\b|\bengineer\b.*\bai\b", title):
        s += 5; notes.append("AI Engineer title")
    elif "python" in title:
        s += 4; notes.append("Python title")
    elif "full" in title and "stack" in title:
        s += 3; notes.append("Full-stack title")

    # Stack keyword hits
    hits = sum(1 for k in _STACK_BONUS if k in blob)
    s += min(hits, 6); notes.append(f"{hits} stack hits")

    # Freshness (prefer <=14d)
    posted = job.get("posted_at")
    if posted:
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - posted).days
        if age <= PREFERRED_AGE_DAYS:
            s += 3; notes.append(f"{age}d old")
        elif age <= 30:
            s += 1

    # Location: local > Pakistan-remote > unverified remote
    loc = " ".join(reasons).lower()
    if "local" in loc:
        s += 4; notes.append("local Isb/Rwp")
    elif "karachi" in loc:
        s += 2; notes.append("Karachi")
    elif "pakistan eligible" in loc:
        s += 3; notes.append("remote, PK eligible")

    # Pay: hourly in $10-40 band, or yearly equivalent (~$20k-80k)
    smin, smax, unit = job.get("salary_min"), job.get("salary_max"), job.get("salary_unit")
    if smin or smax:
        lo = (smin or smax)
        if unit == "yearly":
            lo_hr = lo / 2080
        else:
            lo_hr = lo
        if PAY_TARGET_MIN <= lo_hr <= PAY_TARGET_MAX:
            s += 2; notes.append("pay in band")
        elif lo_hr > PAY_TARGET_MAX:
            s += 1; notes.append("pay above band")
        elif lo_hr < 5:
            s -= 2; notes.append("pay very low")

    # Direct email route is the smoothest apply path
    if job.get("apply_email"):
        s += 2; notes.append("email apply")

    # Priority sources: listings here fill or die fastest (churn analysis
    # 2026-10-07) — surface them first so he can apply before they're gone
    if (job.get("source") or "").lower() in PRIORITY_SOURCES:
        s += 4; notes.append("PRIORITY source (fast-moving)")

    return s, notes
