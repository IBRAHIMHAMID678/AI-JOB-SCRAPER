"""WeWorkRemotely RSS adapter."""
from __future__ import annotations

from typing import List
import xml.etree.ElementTree as ET
import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
]


class WeWorkRemotelyAdapter(JobSourceAdapter):
    source_name = "weworkremotely"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        failed_feeds = 0
        for feed_url in _FEEDS:
            try:
                resp = requests.get(feed_url, timeout=self.timeout, headers={"User-Agent": "JOBPILOT/1.0"})
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                # RSS feeds are single-page: take every item, not just [:20].
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description")
                    region_el = item.find("{https://weworkremotely.com}region")
                    if title_el is None or link_el is None:
                        continue
                    raw_title = (title_el.text or "").strip()
                    # Format: "Company: Title"
                    parts = raw_title.split(":", 1)
                    company = parts[0].strip() if len(parts) > 1 else "Unknown"
                    title = parts[1].strip() if len(parts) > 1 else raw_title
                    url = (link_el.text or "").strip()
                    if not url:
                        continue
                    jobs.append(RawJob(
                        title=title,
                        company=company,
                        location=region_el.text if region_el is not None else "Worldwide",
                        description=desc_el.text if desc_el is not None else None,
                        application_url=url,
                        source="WeWorkRemotely",
                        remote_type="remote",
                    ))
            except Exception as exc:
                failed_feeds += 1
                self.logger.error("WWR feed error (%s): %s", feed_url, exc)
        if not jobs and failed_feeds == len(_FEEDS):
            raise RuntimeError(f"WeWorkRemotely: all {len(_FEEDS)} feeds failed")
        return jobs
