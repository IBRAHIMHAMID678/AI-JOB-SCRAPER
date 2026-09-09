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
        # Check DB for already-seen URL hashes and canonical IDs
        hashes_res = self._load_existing_hashes()
        if isinstance(hashes_res, tuple) and len(hashes_res) == 2:
            seen_url_hashes, seen_canon_ids = hashes_res
        else:
            seen_url_hashes, seen_canon_ids = (hashes_res, set())

        unique_url_hashes: Set[str] = set(seen_url_hashes)
        unique_canon_ids: Set[str] = set(seen_canon_ids)
        unique_content_hashes: Set[str] = set()
        unique_title_company: Set[Tuple[str, str]] = set()
        unique_jobs: List[NormalizedJob] = []
        duplicate_count = 0

        for job in jobs:
            # Signal 0: Canonical Job ID (Cross-source identity match)
            if job.canonical_job_id and job.canonical_job_id in unique_canon_ids:
                duplicate_count += 1
                self.logger.debug("Duplicate canonical job ID: %s (%s at %s)", job.canonical_job_id, job.title, job.company)
                continue

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

            if job.canonical_job_id:
                unique_canon_ids.add(job.canonical_job_id)
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

    def _load_existing_hashes(self) -> Tuple[Set[str], Set[str]]:
        """Load URL hashes and canonical IDs of already-processed jobs from the database."""
        try:
            from ...core.database import db_session
            from ...core.models import Job
            with db_session() as db:
                rows = db.query(Job.url_hash, Job.canonical_job_id).all()
                url_hashes = {r[0] for r in rows if r[0]}
                canon_ids = {r[1] for r in rows if len(r) > 1 and r[1]}
                return url_hashes, canon_ids
        except Exception as exc:
            self.logger.warning("Could not load existing hashes: %s", exc)
            return set(), set()
