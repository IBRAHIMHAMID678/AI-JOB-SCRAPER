"""Filter: applies Ibrahim's requirements to a normalized job dict.

Normalized job dict (from any source):
    source, id, title, company, description, url,
    apply_url (optional), apply_email (optional),
    location (str), remote (bool),
    salary_min, salary_max, salary_unit ("hourly"/"yearly", optional),
    posted_at (datetime or None), tags (list[str])

Returns: (verdict, reasons)
    verdict: "pass" | "review" | "fail"
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from requirements import (
    ROLE_KEYWORDS, SENIOR_TITLE_PATTERNS, NON_DEV_TITLE_PATTERNS,
    MAX_EXP_QUALIFY,
    LOCAL_CITIES, ACCEPTABLE_CITIES, PAKISTAN_MARKERS,
    MAX_AGE_DAYS_PORTAL, PREFERRED_AGE_DAYS, BLOCKED_ROUTE_MARKERS,
)

_EXP_PATTERNS = [
    re.compile(r"(\d+)\s*\+\s*(?:years?|yrs?)\b", re.I),
    re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)", re.I),
    re.compile(r"(\d+)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:hands-on\s+)?experience", re.I),
    re.compile(r"experience\s*[:\-]?\s*(\d+)\s*[-–+]?\s*(?:years?|yrs?)", re.I),
]
_SENIOR_RE = re.compile("|".join(re.escape(p) for p in SENIOR_TITLE_PATTERNS), re.I)
_NON_DEV_RE = re.compile(r"\b(" + "|".join(re.escape(p) for p in NON_DEV_TITLE_PATTERNS) + r")\b", re.I)
_DEV_TITLE_RE = re.compile(r"\b(engineer|developer)\b", re.I)
_JUNIOR_HINTS = re.compile(r"\b(junior|entry[- ]level|fresher|fresh graduates?|0[-–]2|1[-–]3|0[-–]3)\b", re.I)


def _exp_range(text: str):
    """Return (min_years, max_years) or None if no explicit experience stated."""
    lows, highs = [], []
    for pat in _EXP_PATTERNS:
        for m in pat.finditer(text):
            groups = [g for g in m.groups() if g is not None]
            if len(groups) == 2:
                lows.append(int(groups[0])); highs.append(int(groups[1]))
            else:
                lows.append(int(groups[0])); highs.append(int(groups[0]))
    if not lows:
        return None
    return min(lows), max(highs)


def _role_relevant(title: str, desc: str) -> bool:
    if _DEV_TITLE_RE.search(title):
        return True
    blob = f"{title} {desc}".lower()
    return any(k in blob for k in ROLE_KEYWORDS)


def _pakistan_ok(location: str, desc: str, remote: bool) -> tuple[bool, str]:
    loc = (location or "").lower()
    blob = f"{loc} {desc or ''}".lower()

    def _has_any(words: list[str]) -> bool:
        return bool(re.search(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", blob))

    if _has_any(LOCAL_CITIES):
        return True, "local (Isb/Rwp area)"
    if _has_any(["karachi"]):
        return True, "Karachi"
    if remote:
        # whole-word match only: "globally" (users) must NOT count as hiring worldwide
        if _has_any(["pakistan", "worldwide", "anywhere", "global", "remote-first", "emea"]):
            if _has_any(["pakistan"]):
                return True, "remote, Pakistan eligible"
            return False, "remote but Pakistan eligibility unverified"
        return False, "remote but Pakistan eligibility unverified"
    return False, "location out of scope"


def _route_ok(job: dict) -> tuple[bool, str]:
    blob = f"{job.get('apply_url') or ''} {job.get('description') or ''}".lower()
    for marker in BLOCKED_ROUTE_MARKERS:
        if marker in blob:
            return False, f"blocked route ({marker.strip()})"
    if job.get("apply_email"):
        return True, "direct email"
    url = (job.get("apply_url") or "").lower()
    if "docs.google.com/forms" in url:
        return True, "google form"
    if job.get("source") == "linkedin":
        # LinkedIn listings: apply path needs agent verification (Easy Apply vs external)
        return False, "linkedin route — verify apply path"
    if url:
        return True, "career page / apply link"
    return False, "no usable apply route"


def filter_job(job: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    title = job.get("title") or ""
    desc = job.get("description") or ""
    text = f"{title}\n{desc}"

    # 1. Senior-only titles
    if _SENIOR_RE.search(title):
        return "fail", [f"senior-only title: {title!r}"]

    # 1b. Non-dev titles (sales, consulting, security, mobile, ...) — never his roles
    if _NON_DEV_RE.search(title):
        return "fail", [f"non-dev role: {title!r}"]

    # 2. Role relevance
    if not _role_relevant(title, desc):
        return "fail", ["role not in target set (AI/Python/full-stack)"]

    # 3. Experience range
    exp = _exp_range(text)
    if exp:
        lo, hi = exp
        if lo >= 4 or hi > 6 and lo >= 4:
            return "fail", [f"experience {lo}-{hi} yrs exceeds 0-3 cap"]
        if hi > MAX_EXP_QUALIFY:
            return "fail", [f"experience {lo}-{hi} yrs exceeds 0-3 cap"]
        reasons.append(f"experience {lo}-{hi} yrs ok")

    # 4. Freshness
    posted = job.get("posted_at")
    if posted:
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - posted).days
        if age_days > MAX_AGE_DAYS_PORTAL:
            return "fail", [f"stale: {age_days}d old (>30d)"]
        reasons.append(f"posted {age_days}d ago")
    else:
        reasons.append("post date unknown")

    # 5. Location / remote eligibility
    # remote-but-unverified goes to manual review (I'll check the job page) instead of failing
    ok, why = _pakistan_ok(job.get("location") or "", desc, bool(job.get("remote")))
    if not ok:
        if bool(job.get("remote")) and why == "remote but Pakistan eligibility unverified":
            return "review", reasons + [f"{why} — manual check needed"]
        return "fail", [why]
    reasons.append(why)

    # 6. Apply route (LinkedIn listings without a direct route go to review)
    route_ok, route_why = _route_ok(job)
    if not route_ok:
        if job.get("source") == "linkedin":
            return "review", reasons + [route_why]
        return "fail", [route_why]
    reasons.append(f"route: {route_why}")

    # 7. Junior hints -> confidence; intern titles -> review
    if _JUNIOR_HINTS.search(text):
        reasons.append("junior-friendly")
    if re.search(r"\bintern(ship)?\b", title, re.I):
        return "review", reasons + ["intern-titled role: needs his call"]

    return "pass", reasons
