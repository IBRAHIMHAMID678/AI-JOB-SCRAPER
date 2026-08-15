"""NoDesk / Python.org RSS adapter."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List

import requests

from ...core.schemas import RawJob
from .base import JobSourceAdapter

_FEEDS = [
    {"name": "Python.org Jobs", "url": "https://www.python.org/jobs/feed/rss/"},
    {"name": "NoDesk Jobs",     "url": "https://nodesk.co/index.xml"},
]

_TECH_KEYWORDS = [
    "ai", "python", "full stack", "react", "next", "node", "software",
    "developer", "engineer", "frontend", "backend", "web", "fastapi", "django",
]


class NodeDeskAdapter(JobSourceAdapter):
    source_name = "nodesk"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        seen_urls: set = set()

        for feed in _FEEDS:
            try:
                resp = requests.get(feed["url"], timeout=self.timeout)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                items = root.findall("./channel/item")

                for item in items:
                    title_elem = item.find("title")
                    link_elem  = item.find("link")
                    desc_elem  = item.find("description")

                    raw_title = title_elem.text if title_elem is not None else ""
                    job_url   = link_elem.text  if link_elem  is not None else ""
                    raw_desc  = desc_elem.text  if desc_elem  is not None else ""

                    if not job_url or job_url in seen_urls:
                        continue

                    # Parse "Title at Company" or "Company - Title"
                    company = "Remote Tech Employer"
                    title   = raw_title
                    if " at " in raw_title:
                        parts   = raw_title.split(" at ", 1)
                        title   = parts[0].strip()
                        company = parts[1].strip()
                    elif " - " in raw_title:
                        parts   = raw_title.split(" - ", 1)
                        company = parts[0].strip()
                        title   = parts[1].strip()

                    # Only keep tech-relevant listings
                    if not any(kw in title.lower() for kw in _TECH_KEYWORDS):
                        continue

                    # Best-effort salary extraction
                    pay_match = re.search(
                        r'\$\d{2,3}(?:,\d{3})*(?:\s*-\s*\$\d{2,3}(?:,\d{3})*)?'
                        r'(?:\s*/\s*hr|\s*per hour|\s*/\s*year|\s*/\s*yr)?',
                        raw_desc,
                        re.IGNORECASE,
                    )
                    salary_raw = pay_match.group(0) if pay_match else None

                    try:
                        jobs.append(RawJob(
                            title=title,
                            company=company,
                            location="Worldwide Remote",
                            description=raw_desc or "No description available",
                            application_url=job_url,
                            source=feed["name"],
                            salary_raw=salary_raw,
                            remote_type="remote",
                        ))
                        seen_urls.add(job_url)
                    except Exception:
                        pass

            except Exception as exc:
                self.logger.warning(
                    "NodeDesk feed error for '%s' (%s): %s",
                    feed["name"], feed["url"], exc,
                )

        return jobs
