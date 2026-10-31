"""
Fresh Entry-Level Job Harvester and Live Verification Engine.
Specifically targets entry-level and junior roles (<= 2 years experience, fresh graduates)
across:
1. Twin Cities local tech ecosystem (Islamabad & Rawalpindi, Pakistan) - onsite/hybrid/remote.
2. International remote roles strictly open to worldwide applicants (no US/EU region lock).

Filters:
- Titles: AI Engineer, AI/ML, Machine Learning, Full Stack, AI Prompt Engineer, Python Developer.
- Senior Hard Exclusions: Strips senior, sr, lead, staff, principal, director, vp, architect, manager.
- Freshness: Posted within the last 24 hours.
- Live HTTP & Dead-Marker Verification.
"""

from __future__ import annotations

import os
import sys
import re
import json
import logging
import unicodedata
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import httpx

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "auto-scraper"))

logger = logging.getLogger("fresh_entry_scraper")

# Target entry-level software/AI keywords
ROLE_KEYWORDS = [
    "ai engineer", "machine learning", "ml engineer", "ai/ml",
    "prompt engineer", "ai prompt", "prompt engineering",
    "python developer", "python engineer", "python backend",
    "full stack", "fullstack", "software engineer", "software developer"
]

# Strict Senior Hard Exclusions
SENIOR_BLOCKS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b",
    r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bhead of\b",
    r"\barchitect\b", r"\bmanager\b", r"\bdistinguished\b", r"\bfellow\b",
    r"\biii\b", r"\biv\b", r"\bv\b"
]

# Non-Dev / Non-Technical exclusions
NON_DEV_BLOCKS = [
    r"\bqa\b", r"\bquality assurance\b", r"\bsdet\b", r"\btest automation\b",
    r"\bmanual tester\b", r"\bsales\b", r"\bmarketing\b", r"\brecruiter\b",
    r"\baccount executive\b", r"\bcustomer support\b", r"\btechnical support\b",
    r"\bhelpdesk\b", r"\bcontent writer\b", r"\bcopywriter\b", r"\bgraphic designer\b",
    r"\bvideo editor\b", r"\blegal\b", r"\blawyer\b", r"\bcompliance\b"
]

# Pakistan & Twin Cities markers (Islamabad / Rawalpindi)
TWIN_CITIES_KEYWORDS = ["islamabad", "rawalpindi", "isb", "rwp"]

# US / North America / Europe only restrictions (geographically locked)
RESTRICTED_LOCATIONS = [
    r"\b(us|usa)\s*(-only|only)\b",
    r"\b(us|usa)\s+(citizens?|citizenship|residents?|residency)\b",
    r"\b(must\s+reside\s+in\s+the\s+us|must\s+be\s+located\s+in\s+the\s+us)\b",
    r"\b(north\s+america\s+only|us/canada\s+only|eu\s+only|uk\s+only)\b",
    r"\bremote[\s,\-–(]*us\b",
    r"\bremote[\s,\-–(]*usa\b",
    r"\b(us|usa)\s+only\b",
    r"\bcanada\s+only\b",
    r"\beurope\s+only\b",
    r"\blatam\b",
    r"\buk\s+only\b"
]

# Worldwide Remote markers
WORLDWIDE_INDICATORS = [
    "worldwide", "anywhere", "global", "everywhere", "work from anywhere",
    "any country", "hire anywhere", "all countries", "fully distributed",
    "international", "remote worldwide"
]

# Experience requirement regex patterns
HIGH_EXP_PATTERNS = [
    r"(\d+)\s*\+\s*(?:years?|yrs?)",
    r"(?:minimum|at\s+least|requires?)\s*(\d+)\s*(?:years?|yrs?)",
    r"(\d+)\s*[-–]\s*\d+\s*(?:years?|yrs?)"
]

DEAD_JOB_MARKERS = [
    "this job has expired",
    "position closed",
    "no longer accepting applications",
    "job posting has ended",
    "job is no longer available",
    "page not found",
    "404 not found",
    "this position has been filled",
    "opening is closed",
    "the role you are looking for has been filled",
    "applications are now closed"
]


def normalize_text(text: Optional[str]) -> str:
    """Strips diacritics/macrons (e.g. Islamābād -> Islamabad) and normalizes whitespace."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("utf-8")
    return ascii_text.strip()


def matches_target_role(title: str) -> bool:
    """Validates that title matches target roles and is free of senior or non-dev keywords."""
    t = normalize_text(title).lower()
    for block in NON_DEV_BLOCKS:
        if re.search(block, t):
            return False
    for sen in SENIOR_BLOCKS:
        if re.search(sen, t):
            return False
    return any(rk in t for rk in ROLE_KEYWORDS)


def is_entry_level_experience(text: str) -> Tuple[bool, str]:
    """Ensures max required experience is <= 2 years. Strips roles requiring 3+ years."""
    t = normalize_text(text).lower()
    for pat in HIGH_EXP_PATTERNS:
        matches = re.findall(pat, t)
        for m in matches:
            try:
                y = int(m) if isinstance(m, str) else int(m[0])
                if y >= 3:
                    return False, f"Requires {y}+ years experience"
            except (ValueError, TypeError, IndexError):
                pass
    return True, "Entry level / junior friendly (<= 2 yrs)"


def classify_location(location: str, description: str = "") -> Tuple[str, bool]:
    """
    Categorizes job location into:
    1. 'Twin Cities (Islamabad/Rawalpindi)'
    2. 'Worldwide Remote'
    3. 'Ineligible'
    """
    loc_clean = normalize_text(location).lower()
    desc_clean = normalize_text(description).lower()
    combined = f"{loc_clean} {desc_clean}"

    # 1. Twin Cities Local Check
    for kw in TWIN_CITIES_KEYWORDS:
        if kw in loc_clean:
            return "Twin Cities (Islamabad/Rawalpindi)", True

    # 2. Check region restrictions
    for block in RESTRICTED_LOCATIONS:
        if re.search(block, loc_clean):
            if not any(w in combined for w in WORLDWIDE_INDICATORS):
                return "Ineligible (Geographically Restricted)", False

    # 3. Explicit Worldwide Remote Check
    for w in WORLDWIDE_INDICATORS:
        if w in loc_clean:
            return "Worldwide Remote", True

    # 4. General Remote Check
    if "remote" in loc_clean and not any(re.search(b, loc_clean) for b in RESTRICTED_LOCATIONS):
        if any(re.search(b, desc_clean) for b in RESTRICTED_LOCATIONS):
            return "Ineligible (Restricted in Description)", False
        if any(w in desc_clean for w in WORLDWIDE_INDICATORS):
            return "Worldwide Remote", True
        return "Worldwide Remote (General)", True

    return "Ineligible (Non-Target Location)", False


def verify_live_url(url: str, timeout: float = 8.0) -> Tuple[bool, str]:
    """Performs HTTP probe to check that posting is live and not expired."""
    if not url or not url.startswith("http"):
        return False, "Invalid URL format"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            if resp.status_code in (200, 301, 302):
                body = resp.text.lower()
                for marker in DEAD_JOB_MARKERS:
                    if marker in body:
                        return False, f"Expired posting ({marker})"
                return True, "Active (HTTP 200)"
            elif resp.status_code in (401, 403):
                return True, f"Active (Protected endpoint HTTP {resp.status_code})"
            else:
                return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Unreachable ({e})"


class FreshEntryJobFinder:
    """Orchestrates multi-source scraping and live verification for entry-level tech roles."""

    def __init__(self, hours_old: float = 24.0):
        self.hours_old = hours_old

    def harvest(self) -> Dict[str, List[Dict[str, Any]]]:
        candidates: List[Dict[str, Any]] = []

        # 1. LandOffer API
        try:
            from scrapers.landoffer_scraper import LandOfferScraper
            scraper = LandOfferScraper()
            lo_jobs = scraper.fetch_jobs(
                keywords=[
                    "ai engineer", "machine learning", "prompt engineer",
                    "python developer", "full stack", "backend python"
                ],
                max_hours=self.hours_old
            )
            for j in lo_jobs:
                candidates.append({
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "location": j.get("location", ""),
                    "url": j.get("application_url") or j.get("url", ""),
                    "description": j.get("description", ""),
                    "remote_regions": j.get("remote_regions", []),
                    "source": "LandOffer"
                })
        except Exception as e:
            logger.warning(f"LandOffer scrape error: {e}")

        # 2. Himalayas (Worldwide)
        try:
            from scrapers.himalayas_scraper import get_himalayas_jobs
            him_jobs = get_himalayas_jobs()
            for j in him_jobs:
                candidates.append(j)
        except Exception as e:
            logger.warning(f"Himalayas scrape error: {e}")

        # 3. Remotive
        try:
            from scrapers.remotive_scraper import get_remotive_jobs
            rem_jobs = get_remotive_jobs()
            for j in rem_jobs:
                candidates.append(j)
        except Exception as e:
            logger.warning(f"Remotive scrape error: {e}")

        # 4. RemoteOK
        try:
            from scrapers.remoteok_scraper import get_remoteok_jobs
            rok_jobs = get_remoteok_jobs()
            for j in rok_jobs:
                candidates.append(j)
        except Exception as e:
            logger.warning(f"RemoteOK scrape error: {e}")

        # 5. JobSpy for Twin Cities (Islamabad / Rawalpindi)
        try:
            from jobspy import scrape_jobs
            search_terms = [
                "AI Engineer", "Machine Learning", "Python Developer",
                "Full Stack Developer", "Prompt Engineer"
            ]
            for q in search_terms:
                for loc in ["Islamabad, Pakistan", "Rawalpindi, Pakistan"]:
                    try:
                        df = scrape_jobs(
                            site_name=["linkedin"],
                            search_term=q,
                            location=loc,
                            results_wanted=5,
                            hours_old=int(self.hours_old)
                        )
                        if df is not None and not df.empty:
                            for _, row in df.iterrows():
                                candidates.append({
                                    "title": str(row.get("title", "")),
                                    "company": str(row.get("company", "")),
                                    "location": str(row.get("location", loc)),
                                    "url": str(row.get("job_url", "")),
                                    "description": (
                                        str(row.get("description", ""))
                                        if str(row.get("description", "")) != "nan"
                                        else ""
                                    ),
                                    "source": f"LinkedIn ({loc.split(',')[0]})"
                                })
                    except Exception as loc_err:
                        logger.debug(f"JobSpy scrape error for {q} in {loc}: {loc_err}")
        except Exception as e:
            logger.warning(f"JobSpy scrape error: {e}")

        # Deduplicate candidates by URL
        seen_urls = set()
        unique_candidates = []
        for c in candidates:
            u = (c.get("url") or "").strip()
            if not u or u in seen_urls:
                continue
            seen_urls.add(u)
            unique_candidates.append(c)

        # Filter & Verify
        verified_twin_cities: List[Dict[str, Any]] = []
        verified_worldwide: List[Dict[str, Any]] = []

        for c in unique_candidates:
            title = c.get("title", "")
            company = c.get("company", "")
            location = c.get("location", "")
            desc = c.get("description", "")
            url = c.get("url", "")

            # 1. Title verification
            if not matches_target_role(title):
                continue

            # 2. Experience bounds (<= 2 years)
            is_entry, exp_msg = is_entry_level_experience(f"{title} {desc}")
            if not is_entry:
                continue

            # 3. Location classification
            remote_regions = c.get("remote_regions", [])
            if remote_regions and "US" in remote_regions and len(remote_regions) == 1:
                continue

            loc_category, is_eligible_loc = classify_location(location, desc)
            if not is_eligible_loc:
                if any("worldwide" in str(r).lower() or "anywhere" in str(r).lower() for r in remote_regions):
                    loc_category = "Worldwide Remote"
                else:
                    continue

            # 4. Live URL probe
            is_live, live_msg = verify_live_url(url)
            if not is_live:
                continue

            record = {
                "title": title,
                "company": company,
                "location": location,
                "category": loc_category,
                "url": url,
                "experience_rating": exp_msg,
                "verification_status": live_msg,
                "source": c.get("source", "Harvester"),
                "snippet": desc[:250].replace("\n", " ") if desc else ""
            }

            if "Twin Cities" in loc_category:
                verified_twin_cities.append(record)
            else:
                verified_worldwide.append(record)

        return {
            "twin_cities": verified_twin_cities,
            "worldwide_remote": verified_worldwide
        }
