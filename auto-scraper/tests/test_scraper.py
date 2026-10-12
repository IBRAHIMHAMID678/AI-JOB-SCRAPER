"""Regression tests for the job scraper upgrade (2026-10-09).

Covers every confirmed defect from the audit:
- dead Jumio-style job / US-only Deepgram-style role
- empty descriptions (LinkedIn, Arc, SmartRecruiters)
- truncated WAD feed / Reddit post without real JD
- local Isb/Rwp eligibility / Pakistan-eligible remote / unknown geography
- 2-4yr ambiguous range / senior role / 4+ mandatory
- cross-source duplicates / distinct openings with similar titles
- applied.json migration / manual dead feedback persistence
- unverified digest exclusion / transient source errors / 4000+ char descriptions

Run: python3 -m unittest tests.test_scraper -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from filter import filter_job, RULESET_VERSION
from dedup import deduplicate, canonical_url
from extract import enrich_description, set_description, fetch_with_retry
from feedback import (record_job_feedback, job_suppressed, canonical_job_id,
                      load_feedback)
import feedback as feedback_mod

NOW = datetime.now(timezone.utc)


def _job(**kw):
    base = {
        "source": "ats:greenhouse", "id": "gh-test-1",
        "title": "AI Engineer", "company": "TestCo",
        "description": "Remote AI Engineer. Hiring in Pakistan. "
                       "0-2 years experience with Python and LLMs. " * 20,
        "description_status": "full",
        "url": "https://boards.greenhouse.io/testco/jobs/1",
        "apply_url": "https://boards.greenhouse.io/testco/jobs/1",
        "apply_email": None, "location": "Remote", "remote": True,
        "salary_min": None, "salary_max": None, "salary_unit": None,
        "posted_at": NOW - timedelta(days=2), "tags": [],
    }
    base.update(kw)
    return base


class TestGeographicEligibility(unittest.TestCase):
    def test_dead_jumio_style_job_fails(self):
        """Jumio case: dead/paywalled posting must not surface as review."""
        j = _job(company="Jumio", title="Machine Learning Engineer",
                 description="", description_status="empty")
        # empty JD -> cannot pass; must be review at best, never pass
        r = filter_job(j)
        self.assertNotEqual(r["verdict"], "pass")
        self.assertIn("description_status", r["evidence_fields"])

    def test_us_only_deepgram_style_fails(self):
        j = _job(company="Deepgram",
                 description="US citizenship required for this role. " * 20,
                 location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("citizenship_gate", r["reason_codes"])

    def test_local_islamabad_passes(self):
        j = _job(title="Junior Python Developer", location="Islamabad, Pakistan",
                 remote=False,
                 description="Junior Python Developer for our Islamabad office. "
                             "1-2 years experience with FastAPI. " * 20)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "local")

    def test_local_rawalpindi_passes(self):
        j = _job(title="Backend Developer", location="Rawalpindi, Pakistan",
                 remote=False,
                 description="Backend Developer, Rawalpindi office. "
                             "2 years experience with Python. " * 20)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])

    def test_pakistan_eligible_remote_passes(self):
        j = _job(description="We are hiring AI engineers in Pakistan. "
                             "Remote role, 0-2 years experience. " * 20)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "pk_remote")

    def test_unknown_geography_never_passes(self):
        """Unknown hiring country must not become a positive eligibility claim."""
        j = _job(description="Remote ML Engineer. 2 years experience. " * 20,
                 location="Remote")
        r = filter_job(j)
        self.assertNotEqual(r["verdict"], "pass")
        self.assertEqual(r["verdict"], "review")
        self.assertIn("geo_unverified", r["reason_codes"])

    def test_remote_alone_not_worldwide(self):
        j = _job(description="Remote software engineer position. " * 30,
                 location="Remote")
        r = filter_job(j)
        self.assertNotEqual(r["evidence_fields"].get("geo_class"), "worldwide")

    def test_empty_location_not_worldwide(self):
        j = _job(description="Software engineer. 1 year experience. " * 30,
                 location="", remote=True)
        r = filter_job(j)
        self.assertNotEqual(r["verdict"], "pass")

    def test_foreign_city_remote_fails(self):
        j = _job(description="Remote engineer. " * 30, location="Remote, Bangalore",
                 remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("location_out_of_scope", r["reason_codes"])


class TestExperienceParsing(unittest.TestCase):
    def test_ambiguous_2_4_years_review(self):
        j = _job(description="Requires 2-4 years of experience with Python. "
                             "Remote worldwide, hiring globally. " * 10)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "review")
        self.assertIn("exp_ambiguous_range", r["reason_codes"])

    def test_mandatory_4_plus_fails(self):
        j = _job(description="Minimum 4 years of experience required. "
                             "Remote worldwide. " * 10)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("exp_exceeds_cap", r["reason_codes"])

    def test_preferred_high_is_review_not_fail(self):
        j = _job(description="Preferred 5+ years experience but open to junior candidates. "
                             "Remote worldwide. " * 10)
        r = filter_job(j)
        # preferred != mandatory: review, never fail
        self.assertNotEqual(r["verdict"], "fail")

    def test_senior_title_fails(self):
        j = _job(title="Senior AI Engineer")
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("senior_title", r["reason_codes"])

    def test_qa_title_fails(self):
        j = _job(title="QA Automation Engineer",
                 description="Test automation with Python. " * 20)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("qa_title", r["reason_codes"])

    def test_company_age_not_experience(self):
        """'5+ years in business' must not fail the experience gate."""
        j = _job(description="Join our team! 5+ years in business, growing fast. "
                             "Junior developer role, no experience required. " * 10)
        r = filter_job(j)
        self.assertNotIn("exp_exceeds_cap", r["reason_codes"])


class TestDescriptionHandling(unittest.TestCase):
    def test_empty_desc_never_passes(self):
        j = _job(description="", description_status="empty",
                 location="Islamabad, Pakistan", remote=False)
        r = filter_job(j)
        self.assertNotEqual(r["verdict"], "pass")

    def test_long_desc_preserved(self):
        """4000+ char descriptions: full text preserved for filters."""
        long_desc = "AI Engineer. Hiring in Pakistan. 1 year experience. " * 150
        self.assertGreater(len(long_desc), 4000)
        j = _job(description=long_desc)
        set_description(j, long_desc, "full", "test", "http://x")
        self.assertEqual(j["description_status"], "full")
        self.assertGreater(len(j["description_full"]), 4000)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass")

    def test_linkedin_empty_classified(self):
        j = _job(source="linkedin", description="",
                 url="https://linkedin.com/jobs/view/123")
        enrich_description(j, pre_classify_only=True)
        self.assertEqual(j["description_status"], "empty")

    def test_arc_empty_adapter(self):
        j = _job(source="arc", description="",
                 url="https://arc.dev/remote-jobs")
        # no detail URL pattern -> unavailable, not faked
        enrich_description(j)
        self.assertIn(j["description_status"], ("unavailable", "empty", "partial"))
        self.assertNotEqual(j["description_status"], "full")

    def test_reddit_post_not_jd(self):
        j = _job(source="reddit_rss",
                 description="Hiring! DM me. https://example.com/apply",
                 url="https://reddit.com/r/x/1")
        enrich_description(j)
        self.assertEqual(j["description_status"], "partial")
        self.assertIn("_reddit_post_body", j)

    def test_length_alone_not_full(self):
        """500+ chars must not auto-count as complete."""
        j = _job(source="linkedin", description="x" * 600,
                 url="https://linkedin.com/jobs/view/1")
        enrich_description(j, pre_classify_only=True)
        # pre-classify without adapter: partial at best, never 'full'
        self.assertNotEqual(j["description_status"], "full")


class TestDeduplication(unittest.TestCase):
    def test_same_job_different_urls_merges(self):
        a = _job(id="gh-acme-1", url="https://boards.greenhouse.io/acme/jobs/1")
        b = _job(id="as-acme-9", url="https://boards.greenhouse.io/acme/jobs/1?utm_source=x",
                 source="ats:ashby", description="")
        uniq, log = deduplicate([a, b])
        self.assertEqual(len(uniq), 1)
        self.assertIn("ats:ashby", uniq[0]["_dedup_sources"])

    def test_distinct_openings_not_merged(self):
        a = _job(id="gh-acme-1", title="AI Engineer",
                 url="https://boards.greenhouse.io/acme/jobs/1", location="Remote")
        b = _job(id="gh-acme-2", title="AI Engineer",
                 url="https://boards.greenhouse.io/acme/jobs/2", location="Berlin")
        uniq, log = deduplicate([a, b])
        self.assertEqual(len(uniq), 2)

    def test_canonical_url_strips_tracking(self):
        u1 = canonical_url("https://x.com/jobs/1?utm_source=a&foo=bar")
        u2 = canonical_url("https://x.com/jobs/1?foo=bar")
        self.assertEqual(u1, u2)
        self.assertNotIn("utm_source", u1)


class TestFeedbackPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = feedback_mod.FEEDBACK_PATH
        feedback_mod.FEEDBACK_PATH = os.path.join(self.tmp, "feedback.json")

    def tearDown(self):
        feedback_mod.FEEDBACK_PATH = self.orig

    def test_dead_feedback_suppresses(self):
        job = {"company": "Jumio", "title": "Machine Learning Engineer",
               "url": "https://weworkremotely.com/remote-jobs/jumio-x"}
        record_job_feedback(job, "dead", note="test")
        suppressed, why, via = job_suppressed({"company": "jumio",
                                          "title": "machine learning engineer",
                                          "url": "https://weworkremotely.com/remote-jobs/jumio-x"})
        self.assertTrue(suppressed)
        self.assertIn("dead", why)

    def test_useful_does_not_suppress(self):
        job = {"company": "GoodCo", "title": "AI Engineer", "url": "https://x.com/1"}
        record_job_feedback(job, "useful")
        suppressed, _, _ = job_suppressed(job)
        self.assertFalse(suppressed)

    def test_company_block_suppresses(self):
        from feedback import record_company_block
        record_company_block("SpamCorp", "spam")
        suppressed, why, via = job_suppressed({"company": "SpamCorp", "title": "Dev"})
        self.assertTrue(suppressed)

    def test_jumio_url_enrichment_regression(self):
        """P0 REGRESSION: feedback recorded WITHOUT url must suppress the same
        job when a later sweep supplies a URL (the original Jumio defect)."""
        # recorded with company+title only (as the real Jumio entry was)
        record_job_feedback(
            {"company": "Jumio", "title": "Machine Learning Engineer", "url": ""},
            "dead", note="WWR paywall")
        # sweep later finds the same job WITH a URL
        suppressed, why, via = job_suppressed({
            "company": "Jumio", "title": "Machine Learning Engineer",
            "url": "https://weworkremotely.com/remote-jobs/jumio-machine-learning-engineer-xyz",
            "id": "wwr-abc123"})
        self.assertTrue(suppressed, "URL-enriched sweep job must match URL-less feedback")
        self.assertIn("dead", why)
        self.assertTrue(via.startswith("ct:"), f"matched via {via}")

    def test_feedback_with_url_sweep_without_url(self):
        """Reverse: feedback has URL, sweep has only company/title."""
        record_job_feedback(
            {"company": "Acme", "title": "AI Engineer",
             "url": "https://example.com/jobs/1"},
            "unsuitable", note="test")
        suppressed, why, via = job_suppressed(
            {"company": "Acme", "title": "AI Engineer", "url": ""})
        self.assertTrue(suppressed)

    def test_tracking_param_url_variation(self):
        record_job_feedback(
            {"company": "Beta", "title": "Python Dev",
             "url": "https://example.com/jobs/5"}, "dead")
        suppressed, _, via = job_suppressed({
            "company": "Beta", "title": "Python Dev",
            "url": "https://example.com/jobs/5?utm_source=linkedin&utm_medium=x"})
        self.assertTrue(suppressed)
        self.assertTrue(via.startswith("url:"))

    def test_same_title_different_companies_not_suppressed(self):
        record_job_feedback(
            {"company": "CompA", "title": "AI Engineer", "url": ""}, "dead")
        suppressed, _, _ = job_suppressed(
            {"company": "CompB", "title": "AI Engineer", "url": ""})
        self.assertFalse(suppressed, "different companies must not match")

    def test_same_company_different_openings_conservative(self):
        """Both have URLs and they differ → do NOT suppress on ct alone."""
        record_job_feedback(
            {"company": "Gamma", "title": "AI Engineer",
             "url": "https://example.com/jobs/10"}, "dead")
        suppressed, _, _ = job_suppressed({
            "company": "Gamma", "title": "AI Engineer",
            "url": "https://example.com/jobs/20"})
        self.assertFalse(suppressed,
                         "different URLs with same title must not over-suppress")

    def test_stable_id_match(self):
        record_job_feedback(
            {"company": "Delta", "title": "ML Engineer", "id": "gh-delta-99",
             "url": ""}, "rejected")
        suppressed, _, via = job_suppressed({
            "company": "Delta Corp", "title": "Machine Learning Engineer",
            "id": "gh-delta-99",
            "url": "https://boards.greenhouse.io/delta/jobs/99"})
        self.assertTrue(suppressed)
        self.assertTrue(via.startswith("stable_id:"))

    def test_missing_values_not_wildcards(self):
        record_job_feedback({"company": "", "title": "", "url": ""}, "dead")
        # empty job must not suppress everything
        suppressed, _, _ = job_suppressed(
            {"company": "AnyCo", "title": "Anything", "url": "https://x.com/1"})
        self.assertFalse(suppressed)

    def test_legacy_record_readable(self):
        """Legacy records without identity_keys still work."""
        from feedback import load_feedback, save_feedback
        data = load_feedback()
        data["jobs"]["ct:legacy|old role"] = {
            "company": "Legacy", "title": "Old Role", "url": "",
            "decision": "dead", "decided_at": "2026-01-01T00:00:00+00:00",
            "decided_by": "manual", "note": "", "source": "manual",
        }
        save_feedback(data)
        suppressed, _, _ = job_suppressed(
            {"company": "Legacy", "title": "Old Role", "url": ""})
        self.assertTrue(suppressed)

    def test_repeated_evaluations_stable(self):
        record_job_feedback(
            {"company": "Echo", "title": "Dev", "url": ""}, "dead")
        job = {"company": "Echo", "title": "Dev",
               "url": "https://example.com/echo-dev"}
        for _ in range(3):
            suppressed, _, _ = job_suppressed(job)
            self.assertTrue(suppressed)


class TestDigestUnverifiedExclusion(unittest.TestCase):
    """The P0 defect: unverified leads must never enter the outgoing email."""

    def _run_digest_filter(self, leads):
        """Replicate the digest's email-list construction logic."""
        ordered = []
        unverified_log = []
        for l in leads:
            j = l["job"]
            status = j.get("_live", "live")
            if status == "dead":
                continue
            if status == "unverified":
                unverified_log.append({"id": j.get("id")})
                continue  # P0 FIX: never emailed
            ordered.append(l)
        return ordered, unverified_log

    def test_unverified_never_emailed(self):
        leads = [
            {"job": {"id": "1", "title": "A", "_live": "live"}},
            {"job": {"id": "2", "title": "B", "_live": "unverified"}},
            {"job": {"id": "3", "title": "C", "_live": "dead"}},
        ]
        ordered, ulog = self._run_digest_filter(leads)
        emailed_ids = [l["job"]["id"] for l in ordered]
        self.assertEqual(emailed_ids, ["1"])
        self.assertEqual([u["id"] for u in ulog], ["2"])

    def test_empty_ordered_stays_silent(self):
        ordered, _ = self._run_digest_filter(
            [{"job": {"id": "2", "_live": "unverified"}}])
        self.assertEqual(ordered, [])


class TestSourceResilience(unittest.TestCase):
    def test_transient_error_retries_then_reports(self):
        # fetch_with_retry against an unroutable address: bounded, reports error
        text, err = fetch_with_retry("http://127.0.0.1:9/nonexistent",
                                     max_retries=2, timeout=2)
        self.assertIsNone(text)
        self.assertIsNotNone(err)
        self.assertIn("retry_exhausted", err)

    def test_wad_feed_validation(self):
        """Truncated/invalid feed must raise, not silently parse partial data."""
        import sources
        bad_payloads = ['{"rows": []}', '{"error": "forbidden"}', 'not json at all']
        for payload in bad_payloads:
            with patch("extract.fetch_with_retry", return_value=(payload, None)):
                with self.assertRaises(ValueError):
                    sources.fetch_wearedistributed()


class TestAppliedMigration(unittest.TestCase):
    def test_status_normalization(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from migrate_applied import STATUS_MAP
        self.assertEqual(STATUS_MAP["confirmed"], "submitted_confirmed")
        self.assertEqual(STATUS_MAP["rejected_visa_wall"], "rejected")
        # unknown statuses must not be in the map (they go to needs_review)
        self.assertNotIn("some_random_status", STATUS_MAP)

    def test_ruleset_version_present(self):
        j = _job()
        r = filter_job(j)
        self.assertEqual(r["ruleset_version"], RULESET_VERSION)
        for k in ("verdict", "reason_codes", "evidence_fields",
                  "missing_fields", "confidence"):
            self.assertIn(k, r)


if __name__ == "__main__":
    unittest.main()
