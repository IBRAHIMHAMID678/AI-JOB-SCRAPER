"""Remotive API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_CATEGORIES = ["software-dev", "data", "devops-sysadmin"]
_BASE = "https://remotive.com/api/remote-jobs"


class RemotiveAdapter(JobSourceAdapter):
    source_name = "remotive"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        for cat in _CATEGORIES:
            try:
                resp = requests.get(_BASE, params={"category": cat, "limit": 20}, timeout=self.timeout)
                resp.raise_for_status()
                for j in resp.json().get("jobs", []):
                    url = j.get("url", "")
                    if not url:
                        continue
                    try:
                        jobs.append(RawJob(
                            title=j.get("title", ""),
                            company=j.get("company_name", ""),
                            location=j.get("candidate_required_location", "Worldwide"),
                            description=j.get("description", ""),
                            application_url=url,
                            source="Remotive",
                            salary_raw=j.get("salary", None),
                            remote_type="remote",
                            skills_raw=j.get("tags", []) or [],
                        ))
                    except Exception:
                        pass
            except Exception as exc:
                self.logger.warning("Remotive error for category '%s': %s", cat, exc)
        return jobs
