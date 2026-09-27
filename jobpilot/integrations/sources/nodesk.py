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


def _repair_xml(content: bytes) -> bytes:
    """Best-effort repair for feeds with unescaped '&' (e.g. nodesk.co/index.xml)."""
    text = content.decode("utf-8", errors="replace")
    # Escape bare '&' that is not part of a valid entity reference.
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", text)
    return text.encode("utf-8")


def _parse_feed(content: bytes, feed_url: str, logger) -> ET.Element:
    """Parse an RSS feed robustly: strict parse first, repaired fallback second."""
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        logger.warning("Strict XML parse failed for %s (%s); trying repaired parse", feed_url, exc)
        return ET.fromstring(_repair_xml(content))  # raises if still broken


def _split_title_company(raw_title: str) -> tuple[str, str]:
    """
    Split an RSS item title into (title, company).
    Real formats: Python.org uses "Title, Company" (e.g. 'Django Developer,
    The Developer Society'). Do NOT swap on " - " — titles like
    "Senior Backend Engineer - Remote" are not "Company - Title".
    """
    title = (raw_title or "").strip()
    company = "Remote Tech Employer"
    if ", " in title:
        # "Title, Company" — split on the LAST comma so titles containing
        # commas (e.g. "Engineer, Backend, Acme") keep working.
        title_part, company_part = title.rsplit(", ", 1)
        if title_part.strip() and company_part.strip():
            title, company = title_part.strip(), company_part.strip()
    elif " at " in title:
        parts = title.split(" at ", 1)
        title, company = parts[0].strip(), parts[1].strip() or company
    return title, company


class NodeDeskAdapter(JobSourceAdapter):
    source_name = "nodesk"

    def fetch(self) -> List[RawJob]:
        jobs: List[RawJob] = []
        seen_urls: set = set()
        failed_feeds = 0

        for feed in _FEEDS:
            try:
                resp = requests.get(feed["url"], timeout=self.timeout)
                resp.raise_for_status()
                root = _parse_feed(resp.content, feed["url"], self.logger)
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

                    title, company = _split_title_company(raw_title)

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

            except Exception as exc:
                # Loud per-feed failure; keep the other feed. If every feed
                # failed, raise so get_jobs() retries the source with backoff.
                failed_feeds += 1
                self.logger.error(
                    "NodeDesk feed error for '%s' (%s): %s",
                    feed["name"], feed["url"], exc,
                )

        if not jobs and failed_feeds == len(_FEEDS):
            raise RuntimeError(f"NodeDesk: all {len(_FEEDS)} feeds failed")
        return jobs
