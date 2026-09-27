"""Unit tests for deduplication agent."""
import pytest
from jobpilot.core.schemas import NormalizedJob
from jobpilot.core.security import hash_url, hash_content


def make_job(**kwargs) -> NormalizedJob:
    defaults = dict(
        source_name="test",
        title="Python Developer",
        company="ACME Corp",
        application_url="https://example.com/jobs/123",
        url_hash=hash_url(kwargs.get("application_url", "https://example.com/jobs/123")),
        content_hash=hash_content(
            kwargs.get("title", "Python Developer"),
            kwargs.get("company", "ACME Corp"),
            kwargs.get("description", ""),
        ),
    )
    defaults.update(kwargs)
    return NormalizedJob(**defaults)


class TestDeduplication:
    def test_same_url_is_duplicate(self):
        from jobpilot.agents.deduplication.agent import DeduplicationAgent
        j1 = make_job(application_url="https://jobs.com/1")
        j2 = make_job(application_url="https://jobs.com/1")  # same URL
        agent = DeduplicationAgent()
        # Patch _load_existing_hashes to return empty set for unit test
        agent._load_existing_hashes = lambda: set()
        result = agent._execute([j1, j2])
        assert len(result) == 1

    def test_different_urls_both_kept(self):
        from jobpilot.agents.deduplication.agent import DeduplicationAgent
        j1 = make_job(application_url="https://jobs.com/1", url_hash=hash_url("https://jobs.com/1"))
        j2 = make_job(application_url="https://jobs.com/2", url_hash=hash_url("https://jobs.com/2"),
                      company="Other Corp",
                      content_hash=hash_content("Python Developer", "Other Corp"))
        agent = DeduplicationAgent()
        agent._load_existing_hashes = lambda: set()
        result = agent._execute([j1, j2])
        assert len(result) == 2

    def test_already_in_db_is_skipped(self):
        from jobpilot.agents.deduplication.agent import DeduplicationAgent
        url = "https://jobs.com/already-seen"
        j = make_job(application_url=url, url_hash=hash_url(url))
        agent = DeduplicationAgent()
        agent._load_existing_hashes = lambda: {hash_url(url)}
        result = agent._execute([j])
        assert len(result) == 0

    def test_near_duplicate_title_company(self):
        from jobpilot.agents.deduplication.agent import DeduplicationAgent
        j1 = make_job(title="Senior Python Developer", company="ACME Corp",
                      application_url="https://jobs.com/1", url_hash=hash_url("https://jobs.com/1"))
        j2 = make_job(title="Junior Python Developer", company="ACME Corp",
                      application_url="https://jobs.com/2", url_hash=hash_url("https://jobs.com/2"))
        agent = DeduplicationAgent()
        agent._load_existing_hashes = lambda: set()
        # Item 24 fix: seniority is retained in the fuzzy key — Senior and
        # Junior roles at the same company are different opportunities.
        result = agent._execute([j1, j2])
        assert len(result) == 2

    def test_seniority_abbreviations_still_dedup(self):
        from jobpilot.agents.deduplication.agent import DeduplicationAgent, _normalize_title
        assert _normalize_title("Sr. Python Developer") == _normalize_title("Senior Python Developer")
        j1 = make_job(title="Sr. Python Developer", company="ACME Corp",
                      application_url="https://jobs.com/1", url_hash=hash_url("https://jobs.com/1"))
        j2 = make_job(title="Senior Python Developer", company="ACME Corp",
                      application_url="https://jobs.com/2", url_hash=hash_url("https://jobs.com/2"))
        agent = DeduplicationAgent()
        agent._load_existing_hashes = lambda: set()
        result = agent._execute([j1, j2])
        assert len(result) == 1

    def test_same_title_different_location_kept(self):
        from jobpilot.agents.deduplication.agent import DeduplicationAgent
        j1 = make_job(title="AI Engineer", company="ACME Corp", location="Remote",
                      description="remote role", application_url="https://jobs.com/1",
                      url_hash=hash_url("https://jobs.com/1"))
        j2 = make_job(title="AI Engineer", company="ACME Corp", location="Islamabad",
                      description="onsite role", application_url="https://jobs.com/2",
                      url_hash=hash_url("https://jobs.com/2"))
        agent = DeduplicationAgent()
        agent._load_existing_hashes = lambda: set()
        # Item 24 fix: location is part of the fuzzy key — remote vs onsite
        # Islamabad postings of the same title are distinct opportunities.
        result = agent._execute([j1, j2])
        assert len(result) == 2
