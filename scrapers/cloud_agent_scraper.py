"""
Cloud Job Stream Harvester & Filter Adapter.
High-throughput stream scraper for live software and AI engineering roles
with strict 24h freshness, role specialization, senior exclusions, and hardened location classification.
"""
from __future__ import annotations

import os
import re
import sys
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import httpx

# Ensure project root is in path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from freshness_engine import verify_24h_freshness, contains_dead_job_markers
from job_structurer import structure_job_object, extract_remote_regions, extract_salary_range

logger = logging.getLogger("cloud_agent_scraper")

# Strict Role Target Regex (Junior/Mid AI, Full-Stack, Python, Backend)
TARGET_ROLE_PATTERNS = [
    r"\bai\b", r"\bml\b", r"\bmachine learning\b", r"\bartificial intelligence\b",
    r"\bllm\b", r"\brag\b", r"\bgenai\b", r"\bgenerative ai\b", r"\bprompt\b",
    r"\bpython\b", r"\bfull[- ]?stack\b", r"\bbackend\b", r"\bsoftware engineer\b",
    r"\bsoftware developer\b", r"\bdeveloper\b", r"\bengineer\b", r"\bdata engineer\b",
    r"\bfrontend\b", r"\breact\b", r"\bfastapi\b", r"\bnode\b"
]

# Strict Hard Senior Exclusions (Keep profile junior/mid friendly 0-2 yrs)
SENIOR_BLOCK_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b",
    r"\bdirector\b", r"\bvp\b", r"\bvice president\b", r"\bhead of\b",
    r"\barchitect\b", r"\bmanager\b", r"\bdistinguished\b", r"\bfellow\b",
    r"\biii\b", r"\biv\b", r"\bv\b"
]

# Strict Non-Target Blocks
NON_TARGET_BLOCKS = [
    r"\bqa\b", r"\bquality assurance\b", r"\bsdet\b", r"\btest automation\b",
    r"\bmanual tester\b", r"\.net\b", r"\bc#\b", r"\bwordpress\b", r"\bphp\b",
    r"\bsales\b", r"\bmarketing\b", r"\brecruiter\b", r"\baccount executive\b",
    r"\bbusiness develop\w*\b", r"\bcustomer success\b", r"\bcustomer support\b",
    r"\bsupport engineer\b", r"\btechnical support\b", r"\bhelpdesk\b",
    r"\brater\b", r"\bevaluator\b", r"\bvideo editor\b", r"\belearning\b",
    r"\bdistribution engineer\b", r"\bservice engineer\b", r"\bit support\b",
    r"\bcounsel\b", r"\blegal\b", r"\blawyer\b", r"\bcompliance\b",
    r"\bmechanical\b", r"\bcivil\b", r"\belectrical\b", r"\bplant\b",
    r"\bproduction\b", r"\bsmt\b", r"\btechnician\b", r"\bsetter\b",
    r"\bwarehouse\b", r"\bmanufacturing\b"
]

def is_hardened_target_role(title: str) -> bool:
    """Validates that a job title is strictly software/AI/dev and NOT senior/management or non-tech."""
    t = title.lower()
    for block in NON_TARGET_BLOCKS:
        if re.search(block, t):
            return False
    for sen in SENIOR_BLOCK_PATTERNS:
        if re.search(sen, t):
            return False
    return any(re.search(pat, t) for pat in TARGET_ROLE_PATTERNS)

class CloudAgentScraper:
    BASE_URL = "https://job-agent-production-9446.up.railway.app/api/jobs"

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

    def fetch_jobs(
        self,
        keywords: Optional[List[str]] = None,
        max_hours: float = 24.0,
        limit_per_query: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Synchronously fetches and filters fresh jobs from Cloud Stream API.
        """
        if keywords is None:
            keywords = [
                "ai engineer",
                "full stack",
                "python developer",
                "machine learning",
                "backend engineer",
                "fastapi",
                "react developer"
            ]

        seen_fingerprints = set()
        seen_urls = set()
        collected_jobs: List[Dict[str, Any]] = []

        with httpx.Client(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            # 1. Fetch keyword-targeted queries
            for kw in keywords:
                try:
                    params = {
                        "q": kw,
                        "posted_since": int(max_hours),
                        "limit": limit_per_query
                    }
                    resp = client.get(self.BASE_URL, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_jobs = data.get("jobs", [])
                        for r in raw_jobs:
                            job = self._process_raw_job(r, max_hours)
                            if job and job["url"] not in seen_urls and job["fingerprint"] not in seen_fingerprints:
                                seen_urls.add(job["url"])
                                seen_fingerprints.add(job["fingerprint"])
                                collected_jobs.append(job)
                except Exception as e:
                    logger.debug(f"Error querying Cloud Stream for kw '{kw}': {e}")

            # 2. Fetch specific local Pakistan jobs
            try:
                params_pk = {
                    "location": "pakistan",
                    "posted_since": int(max_hours * 2), # allow 48h for rare local tech postings
                    "limit": limit_per_query
                }
                resp_pk = client.get(self.BASE_URL, params=params_pk)
                if resp_pk.status_code == 200:
                    data_pk = resp_pk.json()
                    for r in data_pk.get("jobs", []):
                        job = self._process_raw_job(r, max_hours * 2, is_pk_search=True)
                        if job and job["url"] not in seen_urls and job["fingerprint"] not in seen_fingerprints:
                            seen_urls.add(job["url"])
                            seen_fingerprints.add(job["fingerprint"])
                            collected_jobs.append(job)
            except Exception as e:
                logger.debug(f"Error querying Cloud Stream for location 'pakistan': {e}")

        return collected_jobs

    def _process_raw_job(self, r: Dict[str, Any], max_hours: float, is_pk_search: bool = False) -> Optional[Dict[str, Any]]:
        title = (r.get("title") or "").strip()
        if not title:
            return None

        # Hardened Role Filter
        if not is_hardened_target_role(title):
            return None

        # Check Dead Markers in description
        desc = r.get("description") or f"{title} at {r.get('company', {}).get('name', '')}"
        is_dead, _ = contains_dead_job_markers(desc)
        if is_dead:
            return None

        # Freshness Check
        # Check both posted_at and first_seen_at
        ts = r.get("posted_at") or r.get("first_seen_at")
        is_fresh, hrs_old, dt, reason = verify_24h_freshness(ts, max_hours=max_hours)
        if not is_fresh:
            # Fallback to first_seen_at if posted_at was legacy date but recently discovered
            first_seen = r.get("first_seen_at")
            if first_seen and first_seen != ts:
                is_fresh, hrs_old, dt, reason = verify_24h_freshness(first_seen, max_hours=max_hours)
                if not is_fresh:
                    return None
            else:
                return None

        # Extract URLs: prioritize canonical ATS over aggregator
        apply_url = r.get("apply_url") or ""
        canon_url = r.get("canonical_url") or ""
        final_url = canon_url or apply_url
        if not final_url:
            return None

        # If apply_url is a direct ATS link (Ashby, Lever, Greenhouse, SmartRecruiters), prioritize it
        ats_patterns = ["ashbyhq.com", "lever.co", "greenhouse.io", "smartrecruiters.com", "workable.com", "rippling.com"]
        for p in ats_patterns:
            if p in apply_url.lower():
                final_url = apply_url
                break

        # Location Parsing
        raw_locations = r.get("locations") or []
        location_str = ", ".join(raw_locations) if raw_locations else "Remote"

        # Company details
        co_obj = r.get("company") or {}
        company_name = co_obj.get("name") or "Tech Startup"
        company_slug = co_obj.get("slug") or company_name.lower().replace(" ", "")
        logo_url = co_obj.get("logo_url") or f"https://www.google.com/s2/favicons?domain={co_obj.get('domain', 'company.com')}&sz=128"

        # Structured Regions & Salary
        regions, remote_summary = extract_remote_regions(location_str, desc)
        sal_min, sal_max, sal_curr = extract_salary_range(desc)
        if not sal_min and r.get("salary_min"):
            sal_min = float(r.get("salary_min"))
        if not sal_max and r.get("salary_max"):
            sal_max = float(r.get("salary_max"))
        if not sal_curr and r.get("salary_currency"):
            sal_curr = r.get("salary_currency")

        # Fingerprint for deduplication
        fp = r.get("fingerprint") or f"{company_slug}:::{title.lower()}"

        return {
            "id": f"lo-{r.get('id', fp[:10])}",
            "title": title,
            "company": company_name,
            "company_slug": company_slug,
            "url": final_url,
            "direct_career_url": final_url,
            "location": location_str,
            "remote_regions": json.dumps(regions),
            "remote_summary": remote_summary,
            "description": desc,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_currency": sal_curr or "USD",
            "source": "cloud_agent",
            "date_posted": dt.isoformat() if dt else str(ts or ""),
            "hours_old": hrs_old,
            "is_24h_fresh": is_fresh,
            "logo_url": logo_url,
            "company_size": 100,
            "fingerprint": fp
        }

def get_cloud_agent_jobs() -> List[Dict[str, Any]]:
    """Legacy interface compatible with other scrapers."""
    scraper = CloudAgentScraper()
    return scraper.fetch_jobs(max_hours=24.0)

if __name__ == "__main__":
    print("Testing Cloud Stream Scraper & Hardened Filter Adapter...")
    scraper = CloudAgentScraper()
    jobs = scraper.fetch_jobs(max_hours=24.0, limit_per_query=20)
    print(f"\nSuccessfully harvested {len(jobs)} hardened, verified fresh jobs from Cloud Stream:")
    for j in jobs[:8]:
        print(f"\n[{j['company']}] {j['title']}")
        print(f"  URL:       {j['direct_career_url']}")
        print(f"  Location:  {j['location']}")
        print(f"  Regions:   {j['remote_regions']} ({j['remote_summary']})")
        print(f"  Freshness: {j['hours_old']:.1f}h ago | {j['date_posted']}")

# Backward compatibility aliases
LandOfferScraper = CloudAgentScraper
get_landoffer_jobs = get_cloud_agent_jobs
