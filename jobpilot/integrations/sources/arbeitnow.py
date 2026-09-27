"""Arbeitnow API adapter (free remote job board)."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_BASE = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowAdapter(JobSourceAdapter):
    source_name = "arbeitnow"

    def fetch(self) -> List[RawJob]:
        # The API paginates via ?page=N (~325 jobs/page). Fetch up to 2 pages,
        # deduping by URL, and stop early when a page yields nothing new.
        jobs: List[RawJob] = []
        seen_urls: set = set()
        for page in range(1, 3):
            resp = requests.get(
                _BASE,
                params={"page": page},
                timeout=self.timeout,
                headers={"User-Agent": "JOBPILOT/1.0"},
            )
            resp.raise_for_status()
            page_jobs = resp.json().get("data", [])
            new_this_page = 0
            for j in page_jobs:
                url = j.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                new_this_page += 1
                jobs.append(RawJob(
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location=j.get("location", "Remote"),
                    description=j.get("description", ""),
                    application_url=url,
                    source="Arbeitnow",
                    remote_type="remote" if j.get("remote") else "onsite",
                    skills_raw=j.get("tags", []) or [],
                ))
            self.logger.info("Arbeitnow page %d: +%d new jobs", page, new_this_page)
            if new_this_page == 0:
                break
        return jobs
