"""
Startup Job Scraper Module
Discovers startup job posts specifically needing Junior AI Engineers or Full Stack Developers.
Supports:
1. Pakistan Tech Startups (Lahore, Islamabad, Karachi, Remote Pakistan)
2. Remote Foreign Startups (US/UK/EU/Global Remote AI & Tech Startups)

Strictly filters for:
- Junior / 0-3 yrs / Associate / Entry-level roles (rejects Senior, Lead, Staff, Principal, VP)
- AI Engineer, Machine Learning, Full Stack Developer, Python, Backend, Next.js/React
- Open, compatible ATS forms (Greenhouse, Lever, Ashby, open direct forms)
- NO login walls (no Workday, Taleo) and NO OTP challenges
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import requests
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from jobpilot.core.logging import get_logger
from jobpilot.core.schemas import RawJob
from jobpilot.agents.application.router import is_form_apply_compatible

logger = get_logger("scrapers.startup")

SENIOR_PATTERN = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|director|head of|vp|architect|manager)\b",
    re.IGNORECASE,
)
ROLE_PATTERN = re.compile(
    r"\b(ai engineer|artificial intelligence|machine learning|ml engineer|llm|rag|deep learning|"
    r"full stack|full-stack|fullstack|software engineer|software developer|python developer|"
    r"backend developer|frontend developer|web developer|associate engineer|junior)\b",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# Key Foreign AI & Tech Startups using Greenhouse/Lever with open forms
FOREIGN_STARTUP_GREENHOUSE_BOARDS = [
    "anthropic", "mistral", "together", "runway", "retool",
    "cursor", "elevenlabs", "deepgram", "baseten", "cohere",
    "pinecone", "weaviate", "qdrant", "groq", "scale",
    "perplexity", "writer", "huggingface", "vercel", "canonical"
]

FOREIGN_STARTUP_LEVER_BOARDS = [
    "replit", "supabase", "modal", "resend", "railway",
    "convex", "prisma", "cal", "clerk", "fly",
    "dbtlabs", "synthesia", "docker", "palantir"
]


class StartupJobScraper:
    def __init__(self):
        self.seen_urls: Set[str] = set()

    def is_eligible_startup_role(self, title: str, description: str = "") -> bool:
        """Verifies title matches Junior AI Engineer or Full Stack Developer and avoids senior tags."""
        if not title:
            return False
        if SENIOR_PATTERN.search(title):
            return False
        if not ROLE_PATTERN.search(title):
            return False
        # If description explicitly requires 5+ years of experience, reject
        desc_lower = description.lower()
        if re.search(r"\b([4-9]|1[0-9])\+?\s*years?\s+(of\s+)?experience\b", desc_lower):
            return False
        return True

    def fetch_greenhouse_startup_jobs(
        self, board_tokens: List[str], region_tag: str = "remote_foreign_startup"
    ) -> List[RawJob]:
        """Queries public Greenhouse API for startup job listings in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        jobs: List[RawJob] = []

        def _fetch_single_gh(board: str) -> List[RawJob]:
            board_jobs = []
            url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            try:
                res = requests.get(url, headers=HEADERS, timeout=4)
                if res.status_code != 200:
                    return []
                data = res.json()
                raw_list = data.get("jobs", [])
                for item in raw_list:
                    title = str(item.get("title", "")).strip()
                    job_url = str(item.get("absolute_url", "")).strip()
                    loc = str(item.get("location", {}).get("name", "Remote")).strip()
                    desc = str(item.get("content", "")).strip()

                    if not job_url:
                        continue
                    if not self.is_eligible_startup_role(title, desc):
                        continue
                    compat, _ = is_form_apply_compatible(job_url)
                    if not compat:
                        continue

                    board_jobs.append(
                        RawJob(
                            title=title,
                            company=board.capitalize(),
                            location=loc,
                            description=desc,
                            application_url=job_url,
                            source=f"Greenhouse Startup ({board})",
                            remote_type="remote" if "remote" in loc.lower() else "on-site",
                        )
                    )
            except Exception:
                pass
            return board_jobs

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_fetch_single_gh, b) for b in board_tokens]
            for f in as_completed(futures):
                try:
                    res_jobs = f.result()
                    for rj in res_jobs:
                        if rj.application_url not in self.seen_urls:
                            self.seen_urls.add(rj.application_url)
                            jobs.append(rj)
                except Exception:
                    pass
        return jobs

    def fetch_lever_startup_jobs(
        self, company_slugs: List[str], region_tag: str = "remote_foreign_startup"
    ) -> List[RawJob]:
        """Queries public Lever API for startup job listings in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        jobs: List[RawJob] = []

        def _fetch_single_lv(comp: str) -> List[RawJob]:
            comp_jobs = []
            url = f"https://api.lever.co/v0/postings/{comp}?mode=json"
            try:
                res = requests.get(url, headers=HEADERS, timeout=4)
                if res.status_code != 200:
                    return []
                data = res.json()
                if not isinstance(data, list):
                    return []
                for item in data:
                    title = str(item.get("text", "")).strip()
                    job_url = str(item.get("hostedUrl", "")).strip()
                    loc = str(item.get("categories", {}).get("location", "Remote")).strip()
                    desc = str(item.get("descriptionPlain", "")).strip()

                    if not job_url:
                        continue
                    if not self.is_eligible_startup_role(title, desc):
                        continue
                    compat, _ = is_form_apply_compatible(job_url)
                    if not compat:
                        continue

                    comp_jobs.append(
                        RawJob(
                            title=title,
                            company=comp.capitalize(),
                            location=loc,
                            description=desc,
                            application_url=job_url,
                            source=f"Lever Startup ({comp})",
                            remote_type="remote" if "remote" in loc.lower() else "on-site",
                        )
                    )
            except Exception:
                pass
            return comp_jobs

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_fetch_single_lv, c) for c in company_slugs]
            for f in as_completed(futures):
                try:
                    res_jobs = f.result()
                    for rj in res_jobs:
                        if rj.application_url not in self.seen_urls:
                            self.seen_urls.add(rj.application_url)
                            jobs.append(rj)
                except Exception:
                    pass
        return jobs

    def search_engine_discover(self, queries: List[str], region_tag: str) -> List[RawJob]:
        """
        Uses Yahoo & search index queries to discover startup jobs on open ATS boards
        specifically in Pakistan or Remote Foreign.
        """
        jobs: List[RawJob] = []
        extracted_urls: Set[str] = set()

        for q in queries:
            url = "https://search.yahoo.com/search?p=" + urllib.parse.quote(q)
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                    ru_matches = re.findall(r"RU=([^/]+)/RK", html)
                    for ru in ru_matches:
                        unquoted = urllib.parse.unquote(ru)
                        # Direct ATS forms
                        if "boards.greenhouse.io" in unquoted or "jobs.lever.co" in unquoted or "job-boards.greenhouse.io" in unquoted:
                            clean_url = unquoted.split("?")[0].rstrip("/")
                            if clean_url not in self.seen_urls and clean_url not in extracted_urls:
                                extracted_urls.add(clean_url)
            except Exception as e:
                logger.debug("Search query failed '%s': %s", q, e)
            time.sleep(1.0)

        # Inspect found URLs
        for app_url in extracted_urls:
            try:
                parts = [p for p in app_url.split("/") if p]
                company = "Startup"
                if "greenhouse.io" in app_url and len(parts) >= 4:
                    company = parts[2].capitalize()
                elif "lever.co" in app_url and len(parts) >= 3:
                    company = parts[2].capitalize()

                r = requests.get(app_url, headers=HEADERS, timeout=6)
                if r.status_code == 200:
                    title_m = re.search(r"<title>([^<]+)</title>", r.text, re.IGNORECASE)
                    raw_title = title_m.group(1) if title_m else ""
                    clean_title = raw_title.split(" - ")[0].split(" | ")[0].strip()
                    if not clean_title or len(clean_title) > 80:
                        clean_title = "Junior Software Engineer / AI Developer"

                    if self.is_eligible_startup_role(clean_title):
                        compat, reason = is_form_apply_compatible(app_url, r.text)
                        if compat:
                            self.seen_urls.add(app_url)
                            jobs.append(
                                RawJob(
                                    title=clean_title,
                                    company=company,
                                    location="Pakistan" if region_tag == "pakistan_startup" else "Remote",
                                    description=r.text[:500],
                                    application_url=app_url,
                                    source=f"Startup Discovery ({region_tag})",
                                    remote_type="remote" if region_tag != "pakistan_startup" else "hybrid",
                                )
                            )
            except Exception:
                pass

        return jobs

    def fetch_pakistan_startup_jobs(self, limit: int = 15) -> List[RawJob]:
        """
        Discovers startup job posts for Junior AI Engineers or Full Stack Developers in Pakistan
        on open ATS forms (Greenhouse, Lever, open single-page forms).
        """
        logger.info("Searching for Junior AI / Full Stack startup jobs in Pakistan...")
        queries = [
            'site:jobs.lever.co "Pakistan" ("AI Engineer" OR "Full Stack" OR "Software Engineer")',
            'site:boards.greenhouse.io "Pakistan" ("AI Engineer" OR "Full Stack" OR "Software Engineer")',
            'site:jobs.lever.co "Islamabad" ("Software Engineer" OR "Developer" OR "Python")',
            'site:jobs.lever.co "Lahore" ("Software Engineer" OR "Full Stack" OR "AI")',
            'site:boards.greenhouse.io "Lahore" ("Software Engineer" OR "Full Stack" OR "Developer")',
            'site:boards.greenhouse.io "Islamabad" ("Software" OR "AI" OR "Python")',
            'site:jobs.lever.co "Karachi" ("Software Engineer" OR "Full Stack")',
            'site:boards.greenhouse.io "Karachi" ("Software Engineer" OR "Developer")',
        ]

        discovered = self.search_engine_discover(queries, region_tag="pakistan_startup")

        pk_boards = ["motive", "educative", "arbisoft", "bazaar", "remotebase", "sastaticket"]
        pk_gh = self.fetch_greenhouse_startup_jobs(pk_boards, region_tag="pakistan_startup")
        discovered.extend(pk_gh)

        for j in discovered:
            if "pakistan" not in j.location.lower() and "lahore" not in j.location.lower() and "islamabad" not in j.location.lower():
                j.location = f"Pakistan ({j.location})"

        logger.info("Discovered %d Pakistan startup jobs", len(discovered))
        return discovered[:limit]

    def fetch_remote_foreign_startup_jobs(self, limit: int = 15) -> List[RawJob]:
        """
        Discovers startup job posts for Junior AI Engineers or Full Stack Developers at Remote Foreign Startups
        on open ATS forms (Greenhouse, Lever).
        """
        logger.info("Searching for Junior AI / Full Stack Remote Foreign startup jobs...")
        
        gh_jobs = self.fetch_greenhouse_startup_jobs(FOREIGN_STARTUP_GREENHOUSE_BOARDS, region_tag="remote_foreign_startup")
        lv_jobs = self.fetch_lever_startup_jobs(FOREIGN_STARTUP_LEVER_BOARDS, region_tag="remote_foreign_startup")

        search_queries = [
            'site:jobs.lever.co "startup" ("Junior AI Engineer" OR "Full Stack Developer") "Remote"',
            'site:boards.greenhouse.io "startup" ("Junior AI Engineer" OR "Full Stack Developer") "Remote"',
            'site:jobs.lever.co "remote" ("AI Developer" OR "Python Developer" OR "Junior Full Stack")',
            'site:boards.greenhouse.io "remote" ("AI Engineer" OR "Full Stack Engineer" OR "Associate")',
        ]
        searched = self.search_engine_discover(search_queries, region_tag="remote_foreign_startup")

        combined = gh_jobs + lv_jobs + searched
        unique_jobs: List[RawJob] = []
        seen = set()
        for j in combined:
            if j.application_url not in seen:
                seen.add(j.application_url)
                unique_jobs.append(j)

        logger.info("Discovered %d Remote Foreign startup jobs", len(unique_jobs))
        return unique_jobs[:limit]
