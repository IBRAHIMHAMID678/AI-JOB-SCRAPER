"""The Muse API adapter."""
from __future__ import annotations

from typing import List
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_BASE = "https://www.themuse.com/api/public/jobs"
_CATEGORIES = ["Software Engineer", "Data Science", "IT", "Engineering"]


class TheMuseAdapter(JobSourceAdapter):
    source_name = "themuse"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        for cat in _CATEGORIES[:2]:
            try:
                resp = requests.get(
                    _BASE,
                    params={"category": cat, "level": "Entry Level", "page": 1, "api_key": ""},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                for j in resp.json().get("results", [])[:15]:
                    refs = j.get("refs", {})
                    url = refs.get("landing_page", "")
                    if not url:
                        continue
                    locs = j.get("locations", [])
                    location = locs[0].get("name", "Remote") if locs else "Remote"
                    try:
                        jobs.append(RawJob(
                            title=j.get("name", ""),
                            company=j.get("company", {}).get("name", "") if isinstance(j.get("company"), dict) else "",
                            location=location,
                            application_url=url,
                            source="TheMuse",
                            remote_type="remote" if "remote" in location.lower() else "unknown",
                        ))
                    except Exception:
                        pass
            except Exception as exc:
                self.logger.warning("TheMuse error for '%s': %s", cat, exc)
        return jobs
