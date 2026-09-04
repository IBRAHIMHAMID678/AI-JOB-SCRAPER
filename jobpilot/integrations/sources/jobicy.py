"""Jobicy API adapter (free remote tech/developer jobs)."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_BASE = "https://jobicy.com/api/v2/remote-jobs?count=50&industry=dev"


class JobicyAdapter(JobSourceAdapter):
    source_name = "jobicy"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        try:
            resp = requests.get(_BASE, timeout=12, headers={"User-Agent": "Mozilla/5.0 JOBPILOT/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                for j in data.get("jobs", []):
                    url = j.get("url", "").strip()
                    if not url:
                        continue
                    jobs.append(RawJob(
                        title=j.get("jobTitle", "").strip(),
                        company=j.get("companyName", "").strip(),
                        location=j.get("jobGeo", "Worldwide Remote").strip(),
                        description=j.get("jobDescription", "") or j.get("jobExcerpt", ""),
                        application_url=url,
                        source="Jobicy",
                        remote_type="remote",
                        salary_min=float(j.get("annualSalaryMin")) if j.get("annualSalaryMin") and str(j.get("annualSalaryMin")).isdigit() else None,
                        skills_raw=j.get("jobIndustry") if isinstance(j.get("jobIndustry"), list) else (str(j.get("jobIndustry")).split(",") if j.get("jobIndustry") else []),
                    ))
        except Exception as exc:
            self.logger.warning("Jobicy fetch error: %s", exc)
        return jobs
