"""
Unit tests for Universal Auto-Apply and Field Classifier Engine.
Verifies Ibrahim Hamid profile and universal form field handling.
"""
import pytest
from jobpilot.services.auto_apply import (
    _candidate,
    _classify_and_resolve_field,
    can_apply,
    _find_apply_email,
)
from jobpilot.core.config import settings


class TestCandidateProfile:
    def test_candidate_identity(self):
        c = _candidate()
        assert c["full_name"] == "Ibrahim Hamid"
        assert c["first_name"] == "Ibrahim"
        assert c["last_name"] == "Hamid"
        assert "ibrahimhamid" in c["email"]
        assert "+92" in c["phone"]
        assert "Pakistan" in c["location"]

    def test_candidate_links(self):
        c = _candidate()
        assert "linkedin.com" in c["linkedin"]
        assert "github.com" in c["github"]
        assert "github.com" in c["portfolio"]

    def test_candidate_work_auth_and_sponsorship(self):
        c = _candidate()
        assert c["work_authorization"] == "Yes"
        assert c["sponsorship_needed"] == "No"
        assert c["visa_needed"] == "No"
        assert c["currently_employed"] == "No"
        assert "Immediately" in c["notice_period"]

    def test_candidate_education_and_skills(self):
        c = _candidate()
        assert "Computer Science" in c["degree"]
        assert "Capital University of Science and Technology" in c["university"] or "CUST" in c["university"]
        assert c["graduation_year"] == "2026"
        assert c["graduation_month"] == "July"
        assert c["graduation_date"] == "2026-07-01"
        assert "Python" in c["skills"]
        assert "FastAPI" in c["skills"]
        assert "React" in c["skills"]
        assert "LangChain" in c["skills"]
        assert "RAG" in c["skills"]


class TestFieldClassificationAndResolution:
    def setup_method(self):
        self.candidate = _candidate()

    def test_first_and_last_name_fields(self):
        cat, val = _classify_and_resolve_field("input", "text", "first_name", "first_name", "", "First Name *", "", self.candidate)
        assert cat == "first_name"
        assert val == "Ibrahim"

        cat, val = _classify_and_resolve_field("input", "text", "applicant_lname", "lname", "Enter surname", "Family Name", "", self.candidate)
        assert cat == "last_name"
        assert val == "Hamid"

    def test_contact_fields(self):
        cat, val = _classify_and_resolve_field("input", "email", "user_email", "email_input", "you@example.com", "Email Address", "", self.candidate)
        assert cat == "email"
        assert val == "ibrahimhamid.2600@gmail.com"

        cat, val = _classify_and_resolve_field("input", "tel", "phone_number", "contact_phone", "+1...", "Mobile Phone", "", self.candidate)
        assert cat == "phone"
        assert "+92" in val

    def test_links_and_socials(self):
        cat, val = _classify_and_resolve_field("input", "url", "job_application_linkedin", "linkedin_url", "", "LinkedIn Profile URL", "", self.candidate)
        assert cat == "linkedin"
        assert "linkedin.com" in val

        cat, val = _classify_and_resolve_field("input", "url", "github_profile", "gh_link", "https://...", "GitHub Profile", "", self.candidate)
        assert cat == "github"
        assert "github.com" in val

        cat, val = _classify_and_resolve_field("input", "url", "portfolio_website", "portfolio", "", "Personal Website / Portfolio", "", self.candidate)
        assert cat == "portfolio"
        assert "github.com" in val

    def test_resume_upload_fields(self):
        cat, val = _classify_and_resolve_field("input", "file", "resume_file", "cv_upload", "", "Attach your CV / Resume", "", self.candidate)
        assert cat == "file_upload"
        assert val == "RESUME"

    def test_work_authorization_and_sponsorship_questions(self):
        cat, val = _classify_and_resolve_field("input", "text", "work_auth", "auth_question", "", "Are you legally authorized to work in this position?", "", self.candidate)
        assert cat == "work_authorization"
        assert val == "Yes"

        cat, val = _classify_and_resolve_field("input", "text", "sponsorship", "sponsor_q", "", "Will you now or in the future require visa sponsorship?", "", self.candidate)
        assert cat == "sponsorship_needed"
        assert val == "No"

    def test_salary_and_compensation_fields(self):
        cat, val = _classify_and_resolve_field("input", "text", "salary_expectation", "salary", "$", "Desired Salary / Compensation", "", self.candidate)
        assert cat == "desired_salary"
        assert "$60,000" in val

        cat, val = _classify_and_resolve_field("input", "text", "hourly_pay", "rate", "$/hr", "Desired hourly rate", "", self.candidate)
        assert cat == "salary_hourly"
        assert val == "$30"

    def test_experience_and_education_fields(self):
        cat, val = _classify_and_resolve_field("input", "text", "years_exp", "exp_total", "Years", "How many total years of experience do you have?", "", self.candidate)
        assert cat == "years_experience"
        assert val == "2"

        cat, val = _classify_and_resolve_field("input", "text", "university_name", "school", "", "College or University Attended", "", self.candidate)
        assert cat == "university"
        assert "CUST" in val or "Capital University" in val

        cat, val = _classify_and_resolve_field("input", "text", "degree_name", "degree", "", "Degree and Major", "", self.candidate)
        assert cat == "degree"
        assert "Computer Science" in val

    def test_custom_open_ended_questions(self):
        cat, val = _classify_and_resolve_field("textarea", "textarea", "why_company", "motivation", "", "Why do you want to join our team?", "", self.candidate)
        assert cat == "why_interested"
        assert "Python" in val or "LLM" in val or "FastAPI" in val

        cat, val = _classify_and_resolve_field("textarea", "textarea", "projects_built", "portfolio_desc", "", "Describe a technical project or achievement", "", self.candidate)
        assert cat == "project_experience"
        assert "AI Job Scraper" in val or "RAG" in val

        cat, val = _classify_and_resolve_field("textarea", "textarea", "cover_letter_field", "cover_letter", "", "Paste your Cover Letter", "", self.candidate)
        assert cat == "cover_letter"

    def test_fallback_custom_questions(self):
        cat, val = _classify_and_resolve_field("input", "text", "custom_q_123", "q123", "", "Please share anything else we should know about your candidacy", "", self.candidate)
        assert val is not None
        assert len(val) > 0


class TestEmailApplyDetection:
    def test_find_apply_email_direct(self):
        desc = "We are hiring! Please send your resume to careers@innovatetech.com with your portfolio."
        found = _find_apply_email(desc)
        assert found == "careers@innovatetech.com"

    def test_find_apply_email_keyword_priority(self):
        desc = "Contact info@company.com or send application directly to jobs@company.com for fast review."
        found = _find_apply_email(desc)
        assert found == "jobs@company.com"
