"""
Deduplication Agent.
Detects duplicate jobs across sources using multiple signals:
  1. URL hash (exact match)
  2. Content hash (title + company + description snippet)
  3. Title similarity + same company (fuzzy)
Prevents duplicate applications to the same role.
"""
from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

from ...core.schemas import NormalizedJob
from ..base import BaseAgent


def _normalize_title(title: str) -> str:
    """Strip common variations to find near-duplicate titles."""
    t = title.lower().strip()
    t = re.sub(r"\b(senior|sr|junior|jr|lead|staff|principal)\b", "", t)
    t = re.sub(r"\b(i|ii|iii|iv|v)\b", "", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _company_key(company: str) -> str:
    c = company.lower().strip()
    c = re.sub(r"\b(inc|llc|ltd|corp|co|group|technologies|tech)\b", "", c)
    return re.sub(r"\s+", " ", c).strip()


class DeduplicationAgent(BaseAgent[List[NormalizedJob], List[NormalizedJob]]):
    name = "deduplication_agent"

    def _execute(self, jobs: List[NormalizedJob]) -> List[NormalizedJob]:
        # Check DB for already-seen URL hashes
        seen_url_hashes = self._load_existing_hashes()

        unique_url_hashes: Set[str] = set(seen_url_hashes)
        unique_content_hashes: Set[str] = set()
        unique_title_company: Set[Tuple[str, str]] = set()
        unique_jobs: List[NormalizedJob] = []
        duplicate_count = 0

        for job in jobs:
            # Signal 1: URL hash
            if job.url_hash in unique_url_hashes:
                duplicate_count += 1
                self.logger.debug("Duplicate URL: %s", job.application_url[:60])
                continue

            # Signal 2: Content hash (title + company + desc snippet)
            if job.content_hash and job.content_hash in unique_content_hashes:
                duplicate_count += 1
                self.logger.debug("Duplicate content: %s at %s", job.title, job.company)
                continue

            # Signal 3: Fuzzy title + company match
            title_key = _normalize_title(job.title)
            company_key = _company_key(job.company)
            tk = (title_key, company_key)
            if tk in unique_title_company:
                duplicate_count += 1
                self.logger.debug("Near-duplicate: %s at %s", job.title, job.company)
                continue

            unique_url_hashes.add(job.url_hash)
            if job.content_hash:
                unique_content_hashes.add(job.content_hash)
            unique_title_company.add(tk)
            unique_jobs.append(job)

        self.logger.info(
            "Deduplication: %d input → %d unique (%d duplicates removed)",
            len(jobs), len(unique_jobs), duplicate_count,
        )
        return unique_jobs

    def _load_existing_hashes(self) -> Set[str]:
        """Load URL hashes of already-processed jobs from the database."""
        try:
            from ...core.database import db_session
            from ...core.models import Job
            with db_session() as db:
                rows = db.query(Job.url_hash).all()
                return {r[0] for r in rows if r[0]}
        except Exception as exc:
            self.logger.warning("Could not load existing hashes: %s", exc)
            return set()
