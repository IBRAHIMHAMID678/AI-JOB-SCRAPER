"""RemoteOK API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_TAGS = ["python", "react", "javascript", "node", "ai", "llm", "full-stack"]
_BASE = "https://remoteok.com/api"
_PER_TAG_CAP = 40  # RemoteOK tag endpoints return a single page; take a bigger slice


class RemoteOKAdapter(JobSourceAdapter):
    source_name = "remoteok"
    rate_limit_delay = 2.0

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        tag_errors = 0
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
                for j in (data or [])[:_PER_TAG_CAP]:
                    if not isinstance(j, dict):
                        continue
                    url = j.get("url", "")
                    if not url:
                        continue
                    jobs.append(RawJob(
                        title=j.get("position", ""),
                        company=j.get("company", ""),
                        location=j.get("location") or "Worldwide",
                        description=j.get("description", ""),
                        application_url=url,
                        source="RemoteOK",
                        salary_raw=f"{j.get('salary_min', '')} - {j.get('salary_max', '')}".strip(" -") or None,
                        remote_type="remote",
                        skills_raw=j.get("tags", []) or [],
                    ))
            except Exception as exc:
                # Loud per-tag failure; keep other tags. If every tag failed,
                # raise so get_jobs() retries the whole source with backoff.
                tag_errors += 1
                self.logger.error("RemoteOK tag '%s' failed: %s", tag, exc)
        if not jobs and tag_errors == len(_TAGS):
            raise RuntimeError(f"RemoteOK: all {len(_TAGS)} tag requests failed")
        return jobs
