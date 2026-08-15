"""Unit tests for normalization agent."""
import pytest
from jobpilot.core.schemas import RawJob
from jobpilot.agents.normalization.agent import (
    _parse_remote_type, _parse_employment_type, _parse_salary, NormalizationAgent,
)


class TestRemoteTypeParsing:
    def test_remote_keyword(self):
        assert _parse_remote_type("Remote", "") == "remote"

    def test_worldwide(self):
        assert _parse_remote_type("Worldwide", "") == "remote"

    def test_hybrid(self):
        assert _parse_remote_type("London, UK (Hybrid)", "") == "hybrid"

    def test_onsite(self):
        assert _parse_remote_type("New York, NY (On-site)", "") == "onsite"

    def test_default_remote(self):
        # Unknown defaults to remote for job boards
        assert _parse_remote_type("", "") == "remote"


class TestSalaryParsing:
    def test_usd_range(self):
        lo, hi, cur = _parse_salary("$50,000 - $80,000")
        assert lo == 50000.0
        assert hi == 80000.0
        assert cur == "USD"

    def test_k_notation(self):
        lo, hi, cur = _parse_salary("$50k - $80k")
        assert lo == 50000.0
        assert hi == 80000.0

    def test_hourly(self):
        lo, hi, cur = _parse_salary("$25 - $45")
        assert lo == 25.0
        assert hi == 45.0

    def test_none_input(self):
        lo, hi, cur = _parse_salary(None)
        assert lo is None
        assert hi is None

    def test_invalid_input(self):
        lo, hi, cur = _parse_salary("Competitive")
        assert lo is None


class TestNormalizationAgent:
    def test_normalizes_basic_job(self):
        agent = NormalizationAgent()
        raw = RawJob(
            title="  Python Developer  ",
            company="  ACME Corp  ",
            description="We need a Python dev",
            application_url="https://jobs.com/123",
            source="TestSource",
        )
        result = agent._normalize(raw)
        assert result.title == "Python Developer"
        assert result.company == "ACME Corp"
        assert result.url_hash is not None
        assert result.source_name == "TestSource"

    def test_batch_normalization(self):
        agent = NormalizationAgent()
        jobs = [
            RawJob(title="Dev A", company="Co A", application_url="https://a.com/1", source="S"),
            RawJob(title="Dev B", company="Co B", application_url="https://b.com/1", source="S"),
        ]
        results = agent._execute(jobs)
        assert len(results) == 2

    def test_empty_batch(self):
        agent = NormalizationAgent()
        results = agent._execute([])
        assert results == []
