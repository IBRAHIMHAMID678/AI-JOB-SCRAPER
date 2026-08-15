"""RemoteOK API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_TAGS = ["python", "react", "javascript", "node", "ai"]
_BASE = "https://remoteok.com/api"


class RemoteOKAdapter(JobSourceAdapter):
    source_name = "remoteok"
    rate_limit_delay = 2.0

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        for tag in _TAGS:
            try:
                resp = requests.get(
                    f"{_BASE}?tag={tag}",
                    timeout=self.timeout,
                    headers={"User-Agent": "JOBPILOT/1.0 (job-search-bot)"},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and data:
                    data = data[1:]  # first element is a meta object
                for j in (data or [])[:15]:
                    if not isinstance(j, dict):
                        continue
                    url = j.get("url", "")
                    if not url:
                        continue
                    try:
                        jobs.append(RawJob(
                            title=j.get("position", ""),
                            company=j.get("company", ""),
                            location=j.get("location", "Worldwide"),
                            description=j.get("description", ""),
                            application_url=url,
                            source="RemoteOK",
                            salary_raw=f"{j.get('salary_min', '')} - {j.get('salary_max', '')}".strip(" -") or None,
                            remote_type="remote",
                            skills_raw=j.get("tags", []) or [],
                        ))
                    except Exception:
                        pass
            except Exception as exc:
                self.logger.warning("RemoteOK error for tag '%s': %s", tag, exc)
        return jobs
