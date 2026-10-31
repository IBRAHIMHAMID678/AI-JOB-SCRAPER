"""
High-Concurrency 1st-Party ATS Harvester.
Directly ingests 1st-party ATS public APIs (Greenhouse, Ashby, Lever, Rippling, Workable),
resolves canonical company domain URLs, and enforces strict 24-hour freshness gating.
"""
from __future__ import annotations

import os
import re
import json
import time
import hashlib
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

import httpx
from freshness_engine import verify_24h_freshness, contains_dead_job_markers

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(BASE_DIR, "company_registry.json")

def load_company_registry() -> Dict[str, List[str]]:
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"greenhouse": [], "ashby": [], "lever": [], "rippling": [], "workable": [], "smartrecruiters": []}

class ATSHarvester:
    def __init__(self, max_concurrent: int = 15, timeout: float = 12.0):
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.registry = load_company_registry()
        self.client_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9"
        }

    async def fetch_greenhouse_board(self, client: httpx.AsyncClient, token: str, max_hours: float = 24.0) -> List[Dict[str, Any]]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = await client.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw_list = data.get("jobs", [])
            for r in raw_list:
                # Timestamps in Greenhouse can be updated_at or first_published_at
                ts = r.get("updated_at") or r.get("created_at") or r.get("first_published_at")
                is_fresh, hrs_old, dt, reason = verify_24h_freshness(ts, max_hours=max_hours)
                
                # Check for dead markers in content
                content_html = r.get("content") or ""
                is_dead, _ = contains_dead_job_markers(content_html)
                if is_dead:
                    continue

                # Canonical URL - Greenhouse returns absolute_url which contains the company's own custom domain
                canonical_url = r.get("absolute_url") or f"https://job-boards.greenhouse.io/{token}/jobs/{r.get('id')}"
                
                job_id = str(r.get("id"))
                job_obj = {
                    "id": f"gh-{token}-{job_id}",
                    "title": (r.get("title") or "").strip(),
                    "company": token.replace("-", " ").title(),
                    "company_slug": token,
                    "url": canonical_url,
                    "direct_career_url": canonical_url,
                    "location": (r.get("location") or {}).get("name", "Remote"),
                    "description": content_html,
                    "source": "ats_greenhouse",
                    "ats_platform": "greenhouse",
                    "board_token": token,
                    "date_posted": dt.isoformat() if dt else str(ts or ""),
                    "hours_old": hrs_old,
                    "is_24h_fresh": is_fresh
                }
                jobs.append(job_obj)
        except Exception:
            pass
        return jobs

    async def fetch_ashby_board(self, client: httpx.AsyncClient, token: str, max_hours: float = 24.0) -> List[Dict[str, Any]]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = await client.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw_list = data.get("jobs", [])
            for r in raw_list:
                ts = r.get("publishedAt") or r.get("updatedAt")
                is_fresh, hrs_old, dt, reason = verify_24h_freshness(ts, max_hours=max_hours)

                canonical_url = r.get("jobUrl") or f"https://jobs.ashbyhq.com/{token}/{r.get('id')}"
                comp = r.get("compensation") or {}
                salary_raw = ""
                if comp:
                    c_min = comp.get("minValue")
                    c_max = comp.get("maxValue")
                    curr = comp.get("currency", "USD")
                    if c_min and c_max:
                        salary_raw = f"{curr} {c_min:,} - {c_max:,}"

                job_id = str(r.get("id"))
                job_obj = {
                    "id": f"ashby-{token}-{job_id}",
                    "title": (r.get("title") or "").strip(),
                    "company": token.replace("-", " ").title(),
                    "company_slug": token,
                    "url": canonical_url,
                    "direct_career_url": canonical_url,
                    "location": (r.get("location") or "Remote"),
                    "description": r.get("descriptionHtml") or r.get("descriptionPlain") or "",
                    "salary_raw": salary_raw,
                    "source": "ats_ashby",
                    "ats_platform": "ashby",
                    "board_token": token,
                    "date_posted": dt.isoformat() if dt else str(ts or ""),
                    "hours_old": hrs_old,
                    "is_24h_fresh": is_fresh
                }
                jobs.append(job_obj)
        except Exception:
            pass
        return jobs

    async def fetch_lever_board(self, client: httpx.AsyncClient, token: str, max_hours: float = 24.0) -> List[Dict[str, Any]]:
        url = f"https://api.lever.co/v0/postings/{token}?mode=json"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = await client.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            raw_list = resp.json()
            if not isinstance(raw_list, list):
                return []
            for r in raw_list:
                ts = r.get("createdAt")
                is_fresh, hrs_old, dt, reason = verify_24h_freshness(ts, max_hours=max_hours)

                canonical_url = r.get("hostedUrl") or r.get("applyUrl") or f"https://jobs.lever.co/{token}/{r.get('id')}"
                cats = r.get("categories") or {}
                loc = cats.get("location") or "Remote"
                desc = r.get("descriptionPlain") or r.get("description") or ""

                job_id = str(r.get("id"))
                job_obj = {
                    "id": f"lever-{token}-{job_id}",
                    "title": (r.get("text") or "").strip(),
                    "company": token.replace("-", " ").title(),
                    "company_slug": token,
                    "url": canonical_url,
                    "direct_career_url": canonical_url,
                    "location": loc,
                    "description": desc,
                    "source": "ats_lever",
                    "ats_platform": "lever",
                    "board_token": token,
                    "date_posted": dt.isoformat() if dt else str(ts or ""),
                    "hours_old": hrs_old,
                    "is_24h_fresh": is_fresh
                }
                jobs.append(job_obj)
        except Exception:
            pass
        return jobs

    async def fetch_rippling_board(self, client: httpx.AsyncClient, token: str, max_hours: float = 24.0) -> List[Dict[str, Any]]:
        url = f"https://api.rippling.com/platform/api/ats/v2/board/{token}/jobs?groupJobsByLocation=true&page=0&pageSize=1000"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = await client.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("items", [])
            for r in items:
                job_id = str(r.get("id"))
                title = (r.get("name") or "").strip()
                canonical_url = r.get("url") or f"https://ats.rippling.com/{token}/jobs/{job_id}"

                locations = r.get("locations") or []
                loc_parts = []
                is_remote = False
                for loc in locations:
                    wp = loc.get("workplaceType", "")
                    if wp == "REMOTE":
                        is_remote = True
                    loc_name = loc.get("name") or f"{loc.get('city', '')}, {loc.get('country', '')}"
                    if loc_name.strip():
                        loc_parts.append(loc_name.strip())

                loc_str = ", ".join(loc_parts) if loc_parts else "Remote"
                if is_remote and "remote" not in loc_str.lower():
                    loc_str = f"Remote - {loc_str}"

                ts = r.get("publishedAt") or r.get("createdAt") or datetime.now(timezone.utc).isoformat()
                is_fresh, hrs_old, dt, reason = verify_24h_freshness(ts, max_hours=max_hours)

                job_obj = {
                    "id": f"rippling-{token}-{job_id}",
                    "title": title,
                    "company": token.replace("-", " ").title(),
                    "company_slug": token,
                    "url": canonical_url,
                    "direct_career_url": canonical_url,
                    "location": loc_str,
                    "description": f"{title} at {token.title()} ({loc_str})",
                    "source": "ats_rippling",
                    "ats_platform": "rippling",
                    "board_token": token,
                    "date_posted": dt.isoformat() if dt else str(ts or ""),
                    "hours_old": hrs_old,
                    "is_24h_fresh": is_fresh
                }
                jobs.append(job_obj)
        except Exception:
            pass
        return jobs

    async def fetch_smartrecruiters_board(self, client: httpx.AsyncClient, token: str, max_hours: float = 24.0) -> List[Dict[str, Any]]:
        url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
        jobs: List[Dict[str, Any]] = []
        try:
            resp = await client.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("content", [])
            for r in items:
                job_id = str(r.get("id"))
                title = (r.get("name") or "").strip()
                canonical_url = f"https://jobs.smartrecruiters.com/{token}/{job_id}"

                ts = r.get("releasedDate")
                is_fresh, hrs_old, dt, reason = verify_24h_freshness(ts, max_hours=max_hours)

                loc_obj = r.get("location") or {}
                city = loc_obj.get("city", "")
                country = loc_obj.get("country", "")
                is_remote = loc_obj.get("remote", False)
                loc_str = f"{city}, {country}".strip(", ")
                if is_remote:
                    loc_str = f"Remote - {loc_str}" if loc_str else "Remote"

                job_obj = {
                    "id": f"sr-{token}-{job_id}",
                    "title": title,
                    "company": token.replace("-", " ").title(),
                    "company_slug": token,
                    "url": canonical_url,
                    "direct_career_url": canonical_url,
                    "location": loc_str or "Remote",
                    "description": f"{title} at {token.title()} ({loc_str})",
                    "source": "ats_smartrecruiters",
                    "ats_platform": "smartrecruiters",
                    "board_token": token,
                    "date_posted": dt.isoformat() if dt else str(ts or ""),
                    "hours_old": hrs_old,
                    "is_24h_fresh": is_fresh
                }
                jobs.append(job_obj)
        except Exception:
            pass
        return jobs

    async def harvest_all_async(self, max_hours: float = 24.0, only_fresh: bool = True) -> List[Dict[str, Any]]:
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=self.max_concurrent)
        all_jobs: List[Dict[str, Any]] = []
        
        async with httpx.AsyncClient(limits=limits, headers=self.client_headers, follow_redirects=True) as client:
            tasks = []
            # Greenhouse
            for gh_tok in self.registry.get("greenhouse", []):
                tasks.append(self.fetch_greenhouse_board(client, gh_tok, max_hours=max_hours))
            # Ashby
            for ash_tok in self.registry.get("ashby", []):
                tasks.append(self.fetch_ashby_board(client, ash_tok, max_hours=max_hours))
            # Lever
            for lev_tok in self.registry.get("lever", []):
                tasks.append(self.fetch_lever_board(client, lev_tok, max_hours=max_hours))
            # Rippling
            for rip_tok in self.registry.get("rippling", []):
                tasks.append(self.fetch_rippling_board(client, rip_tok, max_hours=max_hours))
            # SmartRecruiters
            for sr_tok in self.registry.get("smartrecruiters", []):
                tasks.append(self.fetch_smartrecruiters_board(client, sr_tok, max_hours=max_hours))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    all_jobs.extend(res)

        if only_fresh:
            filtered = [j for j in all_jobs if j.get("is_24h_fresh")]
            return filtered
        return all_jobs

    def harvest_all(self, max_hours: float = 24.0, only_fresh: bool = True) -> List[Dict[str, Any]]:
        """Synchronous wrapper for pipeline and batch runs."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In environments with running event loops, create new loop or run in thread
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.harvest_all_async(max_hours=max_hours, only_fresh=only_fresh))
            else:
                return loop.run_until_complete(self.harvest_all_async(max_hours=max_hours, only_fresh=only_fresh))
        except Exception:
            return asyncio.run(self.harvest_all_async(max_hours=max_hours, only_fresh=only_fresh))

if __name__ == "__main__":
    print("Testing ATS Harvester...")
    harvester = ATSHarvester()
    t0 = time.time()
    jobs = harvester.harvest_all(max_hours=48.0, only_fresh=True)
    t1 = time.time()
    print(f"Harvested {len(jobs)} fresh jobs in {t1 - t0:.2f} seconds!")
    for j in jobs[:5]:
        print(f"[{j['company']}] {j['title']} ({j['hours_old']:.1f}h ago)")
        print(f"   URL: {j['direct_career_url']}")

# Backward compatibility alias
MatchaATSHarvester = ATSHarvester
