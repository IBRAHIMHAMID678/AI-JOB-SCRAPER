"""
Comprehensive Test Suite for Experience & Seniority Gatekeeper and Candidate Profile.
Verifies:
- >3 years experience explicit requirements are rejected.
- <=3 years experience and junior/mid roles are accepted.
- Senior leadership roles (Manager, Director, VP, Lead, Principal, Staff, PhD) are rejected.
- Truthful geographic eligibility checks.
- Candidate graduation date is July 2026 (CUST).
"""
import pytest
from jobpilot.core.candidate import get_canonical_candidate_profile
from jobpilot.core.eligibility import (
    evaluate_job_eligibility,
    check_seniority,
    check_experience_requirement,
    check_geographic_eligibility,
)


class TestCandidateCanonicalProfile:
    def test_graduation_date_is_july_2026(self):
        profile = get_canonical_candidate_profile()
        assert profile["graduation_date"] == "2026-07-01"
        assert profile["graduation_month"] == "July"
        assert profile["graduation_month_num"] == "07"
        assert profile["graduation_year"] == "2026"
        assert profile["graduation_text"] == "July 2026"

    def test_education_institution_is_cust(self):
        profile = get_canonical_candidate_profile()
        assert "Capital University of Science and Technology" in profile["university"]
        assert "CUST" in profile["institution"]
        assert profile["degree"] == "Bachelor of Science in Computer Science"

    def test_phone_normalization_fields(self):
        profile = get_canonical_candidate_profile()
        assert profile["phone_country_code"] == "+92"
        assert profile["phone_national"] == "3180584128"
        assert profile["phone_dial_code"] == "92"
        assert "+92" in profile["phone_intl"]


class TestExperienceGatekeeper:
    @pytest.mark.parametrize(
        "desc, expected_rejection",
        [
            ("Requires 4+ years of software engineering experience.", True),
            ("Minimum 5 years of experience with Python and FastAPI.", True),
            ("Candidate must have 5-7 years of backend development.", True),
            ("Requires at least 4 years of experience.", True),
            ("6+ years of relevant experience mandatory.", True),
            ("1-3 years of Python experience required.", False),
            ("0-2 years of experience or fresh graduates welcome.", False),
            ("Looking for Junior AI Engineer with 1-2 years experience.", False),
            ("Up to 3 years experience preferred.", False),
            ("Experience with Python, FastAPI, and Docker.", False),
        ],
    )
    def test_experience_criteria(self, desc, expected_rejection):
        ok, reason, evidence = check_experience_requirement(desc)
        if expected_rejection:
            assert not ok, f"Expected description to be rejected: '{desc}'"
            assert "EXPERIENCE_EXCEEDED" in reason
        else:
            assert ok, f"Expected description to be accepted: '{desc}'"


class TestSeniorityGatekeeper:
    @pytest.mark.parametrize(
        "title, expected_rejection",
        [
            ("Engineering Manager - DevEx AI Tools", True),
            ("Senior Director of Engineering", True),
            ("VP of AI and Technology", True),
            ("Staff Software Engineer", True),
            ("Principal AI Architect", True),
            ("Technical Lead - Backend Services", True),
            ("Data Scientist - PhD Required", True),
            ("Junior Software Engineer", False),
            ("AI Engineer", False),
            ("Full Stack Developer", False),
            ("Python Developer", False),
            ("Associate AI Developer", False),
        ],
    )
    def test_seniority_titles(self, title, expected_rejection):
        ok, reason, evidence = check_seniority(title)
        if expected_rejection:
            assert not ok, f"Expected title to be rejected: '{title}'"
            assert "SENIORITY_REJECTED" in reason
        else:
            assert ok, f"Expected title to be accepted: '{title}'"


class TestGeographicEligibility:
    def test_rejects_us_only_ineligible(self):
        desc = "Only accepting applications from candidates residing in the United States."
        ok, reason, evidence = check_geographic_eligibility(description=desc)
        assert not ok
        assert reason == "LOCATION_INELIGIBLE"

    def test_accepts_worldwide_remote(self):
        desc = "This is a 100% remote worldwide position open to contractors globally."
        ok, reason, evidence = check_geographic_eligibility(description=desc)
        assert ok


class TestFullEligibilityEvaluation:
    def test_palantir_forward_deployed_eligible(self):
        res = evaluate_job_eligibility(
            job_id="palantir-fdse-1",
            title="Forward Deployed Software Engineer",
            company="Palantir",
            description="Seeking software engineers with 1-3 years of experience in Python and distributed systems.",
        )
        assert res.is_eligible
        assert res.decision == "ELIGIBLE"

    def test_figma_engineering_manager_rejected(self):
        res = evaluate_job_eligibility(
            job_id="figma-mgr-1",
            title="Manager, Software Engineering - DevEx AI Tools",
            company="Figma",
            description="Lead a team of 8 engineers.",
        )
        assert not res.is_eligible
        assert res.decision == "SENIORITY_REJECTED"
