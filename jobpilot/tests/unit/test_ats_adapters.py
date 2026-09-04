"""
Unit and Fixture tests for Greenhouse and Lever ATS form handling and Submission Verification.
Tests:
- Greenhouse phone country code / national number handling.
- Modern resume upload verification.
- React-Select async combobox strategy.
- Submission verification: requires affirmative proof (URL transition / DOM confirmation).
"""
import pytest
from jobpilot.core.candidate import get_canonical_candidate_profile
from jobpilot.core.submission_verifier import (
    SubmissionEvidence,
    CONFIRMATION_URL_PATTERNS,
    CONFIRMATION_TEXT_PATTERNS,
    CONFIRMATION_SELECTORS,
)


class TestSubmissionVerificationRules:
    def test_confirmation_url_patterns(self):
        urls = [
            "https://boards.greenhouse.io/figma/jobs/123/confirmation",
            "https://jobs.lever.co/palantir/thanks",
            "https://jobs.company.com/apply/success",
            "https://apply.workable.com/app?status=submitted",
        ]
        import re
        for u in urls:
            matched = any(re.search(p, u, re.IGNORECASE) for p in CONFIRMATION_URL_PATTERNS)
            assert matched, f"Expected URL to match confirmation pattern: {u}"

    def test_confirmation_text_patterns(self):
        samples = [
            "Thank you for applying to our software engineering role!",
            "Your application has been received by the recruiting team.",
            "Application submitted successfully.",
            "We have received your application.",
        ]
        for s in samples:
            s_lower = s.lower()
            matched = any(p in s_lower for p in CONFIRMATION_TEXT_PATTERNS)
            assert matched, f"Expected text to match confirmation: '{s}'"

    def test_evidence_model_default_unconfirmed(self):
        ev = SubmissionEvidence(platform="greenhouse")
        assert not ev.is_confirmed
        assert ev.status == "SUBMISSION_UNCONFIRMED"


class TestPhoneNormalization:
    def test_pakistan_phone_structure(self):
        c = get_canonical_candidate_profile()
        # Country code: +92, national number: 3180584128
        assert c["phone_country_code"] == "+92"
        assert c["phone_national"] == "3180584128"
        assert len(c["phone_national"]) == 10  # standard Pakistani 10-digit mobile without leading 0
        assert c["phone_national_with_zero"] == "03180584128"


class TestModernResumeRecognition:
    def test_resume_path_resolution(self):
        from jobpilot.core.candidate import resolve_resume_path
        path = resolve_resume_path()
        assert path is not None
        assert "Ibrahim_Hamid_Resume.pdf" in path
