"""Working Nomads API adapter (free remote developer jobs)."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_BASE = "https://www.workingnomads.com/api/exposed_jobs/"


class WorkingNomadsAdapter(JobSourceAdapter):
    source_name = "workingnomads"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        resp = requests.get(_BASE, timeout=12, headers={"User-Agent": "Mozilla/5.0 JOBPILOT/1.0"})
        resp.raise_for_status()
        raw = resp.json()
        for j in raw[:50]:
            cat = str(j.get("category_name", "")).lower()
            if "development" not in cat and "sysadmin" not in cat:
                continue
            url = j.get("url", "").strip()
            if not url:
                continue
            jobs.append(RawJob(
                title=j.get("title", "").strip(),
                company=j.get("company_name", "").strip(),
                location=j.get("location", "Worldwide Remote").strip(),
                description=j.get("description", "") or "",
                application_url=url,
                source="WorkingNomads",
                remote_type="remote",
                posting_date=j.get("pub_date"),
                skills_raw=j.get("tags", "").split(",") if j.get("tags") else [],
            ))
        return jobs
