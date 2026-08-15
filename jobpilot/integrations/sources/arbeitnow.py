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
        jobs: List[RawJob] = []
        try:
            resp = requests.get(_BASE, timeout=self.timeout, headers={"User-Agent": "JOBPILOT/1.0"})
            resp.raise_for_status()
            for j in resp.json().get("data", [])[:30]:
                url = j.get("url", "")
                if not url:
                    continue
                try:
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
                except Exception:
                    pass
        except Exception as exc:
            self.logger.warning("Arbeitnow error: %s", exc)
        return jobs
