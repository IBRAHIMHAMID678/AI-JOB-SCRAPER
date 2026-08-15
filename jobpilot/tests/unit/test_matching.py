"""Unit tests for job matching/scoring engine."""
import pytest
from jobpilot.core.schemas import NormalizedJob, JobAnalysisResult
from jobpilot.core.security import hash_url
from jobpilot.agents.matching.agent import MatchingAgent, _role_score, _skills_score, _experience_score


class TestRoleScoring:
    def test_ai_engineer_gets_max(self):
        score, matches = _role_score("AI Engineer")
        assert score == 25
        assert "ai engineer" in matches

    def test_llm_engineer(self):
        score, _ = _role_score("LLM Engineer")
        assert score == 25

    def test_software_engineer(self):
        score, _ = _role_score("Software Engineer")
        assert score == 15

    def test_unrelated_title(self):
        score, _ = _role_score("Marketing Manager")
        assert score == 0

    def test_full_stack(self):
        score, _ = _role_score("Full Stack Developer")
        assert score == 20


class TestSkillsScoring:
    def test_all_skills_match(self):
        skills = ["Python", "FastAPI", "React", "LangChain", "RAG", "MongoDB"]
        score, found = _skills_score(skills, "")
        assert score > 0
        assert len(found) > 0

    def test_no_skills_match(self):
        score, found = _skills_score(["COBOL", "Fortran"], "Only old tech")
        assert score == 0
        assert len(found) == 0

    def test_skills_in_description(self):
        score, found = _skills_score([], "Must know Python and FastAPI with MongoDB")
        assert "python" in found
        assert "fastapi" in found


class TestExperienceScoring:
    def test_junior_seniority(self):
        score, is_junior = _experience_score("junior", None)
        assert score == 15
        assert is_junior

    def test_entry_level(self):
        score, is_junior = _experience_score("entry", None)
        assert is_junior

    def test_senior_role(self):
        score, is_junior = _experience_score("senior", None)
        assert score == 0
        assert not is_junior

    def test_mid_level_0_years_req(self):
        score, is_junior = _experience_score("mid", 0)
        assert is_junior

    def test_mid_level_5_years_req(self):
        score, is_junior = _experience_score("mid", 5)
        assert score <= 5


class TestMatchingAgent:
    def _make_job(self, title="Python Developer", company="ACME"):
        url = f"https://jobs.com/{title.replace(' ','-')}"
        return NormalizedJob(
            source_name="test",
            title=title,
            company=company,
            description="We need Python, FastAPI, React, LangChain developer. Junior friendly. Remote worldwide.",
            application_url=url,
            url_hash=hash_url(url),
            remote_type="remote",
            location="Worldwide",
            skills_raw=["Python", "FastAPI", "React"],
        )

    def test_high_score_ai_engineer(self):
        agent = MatchingAgent()
        job = self._make_job("AI Engineer")
        analysis = JobAnalysisResult(
            required_skills=["Python", "FastAPI", "LangChain"],
            seniority="junior",
            pakistan_eligible=True,
        )
        result = agent._execute({"job": job, "analysis": analysis})
        assert result.overall_score >= 60
        assert result.decision in ("approved", "pending")

    def test_low_score_unrelated_job(self):
        agent = MatchingAgent()
        job = self._make_job("Database Administrator", "Legacy Corp")
        job.description = "Manage Oracle databases and stored procedures"
        job.skills_raw = ["Oracle", "SQL", "PL/SQL"]
        result = agent._execute({"job": job, "analysis": None})
        assert result.overall_score < 50

    def test_us_only_reduces_score(self):
        agent = MatchingAgent()
        job = self._make_job("Python Developer")
        analysis = JobAnalysisResult(
            required_skills=["Python"],
            pakistan_eligible=False,
            us_only=True,
        )
        result = agent._execute({"job": job, "analysis": analysis})
        assert not result.auto_approved
        assert len(result.risks) > 0

    def test_result_has_breakdown(self):
        agent = MatchingAgent()
        job = self._make_job("Full Stack Developer")
        result = agent._execute({"job": job, "analysis": None})
        assert result.breakdown is not None
        assert result.breakdown.role_score >= 0
        assert result.overall_score == (
            result.breakdown.role_score + result.breakdown.skills_score +
            result.breakdown.technology_score + result.breakdown.experience_score +
            result.breakdown.location_score + result.breakdown.salary_score +
            result.breakdown.education_score
        )
