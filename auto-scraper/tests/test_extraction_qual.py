"""Adversarial tests for description extraction (extract.py) and qualification
(filter.py).

Deterministic: no network access. All HTTP is mocked via unittest.mock.
Covers every adapter's success and failure paths, description-status
classification honesty, filter geography/experience decisions, malformed
records, and the never-pass-on-empty-description guarantee.

Run: cd ~/workspace/job_hunt/auto-scraper && python3 -m unittest tests.test_extraction_qual -v
"""
import html as _html
import json
import os
import sys
import types
import urllib.error
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from filter import filter_job, RULESET_VERSION, _exp_assessment, _desc_status
from extract import (
    enrich_description, set_description, fetch_with_retry,
    adapt_arc, adapt_smartrecruiters, adapt_linkedin, adapt_reddit, adapt_wad,
    _classify_length, _ADAPTERS,
)

NOW = datetime.now(timezone.utc)


def _job(**kw):
    """Minimal valid job dict; override per test."""
    base = {
        "source": "ats:greenhouse", "id": "gh-test-1",
        "title": "AI Engineer", "company": "TestCo",
        "description": "", "description_status": "full",
        "url": "https://boards.greenhouse.io/testco/jobs/1",
        "apply_url": "https://boards.greenhouse.io/testco/jobs/1",
        "apply_email": None, "location": "Remote", "remote": True,
        "salary_min": None, "salary_max": None, "salary_unit": None,
        "posted_at": NOW - timedelta(days=2), "tags": [],
    }
    base.update(kw)
    return base


def _long_desc(words="Remote AI Engineer role. ", reps=40):
    return words * reps


# ===========================================================================
# fetch_with_retry
# ===========================================================================
class TestFetchWithRetry(unittest.TestCase):
    def _http_error(self, code):
        return urllib.error.HTTPError("http://x/", code, "msg", {}, None)

    def test_404_returns_immediately_no_retry(self):
        with patch("extract.urllib.request.urlopen",
                   side_effect=self._http_error(404)) as m, \
             patch("extract.time.sleep") as slp:
            text, err = fetch_with_retry("http://x/", max_retries=3)
        self.assertIsNone(text)
        self.assertEqual(err, "http_404_not_found")
        self.assertEqual(m.call_count, 1, "404 must not be retried")
        slp.assert_not_called()

    def test_410_returns_immediately(self):
        with patch("extract.urllib.request.urlopen",
                   side_effect=self._http_error(410)):
            text, err = fetch_with_retry("http://x/", max_retries=3)
        self.assertEqual(err, "http_410_not_found")

    def test_403_is_blocked_not_retried(self):
        with patch("extract.urllib.request.urlopen",
                   side_effect=self._http_error(403)) as m, \
             patch("extract.time.sleep") as slp:
            text, err = fetch_with_retry("http://x/", max_retries=5)
        self.assertIsNone(text)
        self.assertIn("blocked", err)
        self.assertEqual(m.call_count, 1, "403 must not be retried")
        slp.assert_not_called()

    def test_429_retried_then_exhausted(self):
        with patch("extract.urllib.request.urlopen",
                   side_effect=self._http_error(429)) as m, \
             patch("extract.time.sleep"):
            text, err = fetch_with_retry("http://x/", max_retries=3)
        self.assertIsNone(text)
        self.assertIn("retry_exhausted", err)
        self.assertIn("429", err)
        self.assertEqual(m.call_count, 3)

    def test_500_retried(self):
        with patch("extract.urllib.request.urlopen",
                   side_effect=self._http_error(500)) as m, \
             patch("extract.time.sleep"):
            text, err = fetch_with_retry("http://x/", max_retries=2)
        self.assertEqual(m.call_count, 2)
        self.assertIn("retry_exhausted", err)

    def test_transient_failure_then_success(self):
        good = MagicMock()
        good.read.return_value = b"ok body"
        good.__enter__.return_value = good
        with patch("extract.urllib.request.urlopen",
                   side_effect=[TimeoutError("t"), good]) as m, \
             patch("extract.time.sleep"):
            text, err = fetch_with_retry("http://x/", max_retries=3)
        self.assertEqual(text, "ok body")
        self.assertIsNone(err)
        self.assertEqual(m.call_count, 2)

    def test_backoff_timing(self):
        with patch("extract.urllib.request.urlopen",
                   side_effect=TimeoutError("t")), \
             patch("extract.time.sleep") as slp:
            fetch_with_retry("http://x/", max_retries=4)
        # 1s, 2s, 4s between 4 attempts
        self.assertEqual([c.args[0] for c in slp.call_args_list], [1, 2, 4])

    def test_incomplete_read_is_retried(self):
        import http.client
        with patch("extract.urllib.request.urlopen",
                   side_effect=http.client.IncompleteRead(b"a", 10)) as m, \
             patch("extract.time.sleep"):
            text, err = fetch_with_retry("http://x/", max_retries=2)
        self.assertIsNone(text)
        self.assertEqual(m.call_count, 2)
        self.assertIn("IncompleteRead", err)


# ===========================================================================
# set_description / _classify_length
# ===========================================================================
class TestSetDescription(unittest.TestCase):
    def test_sets_all_fields(self):
        j = _job(url="https://x.com/1")
        set_description(j, "  hello world  ", "full", "test_method",
                        "https://detail.com/1")
        self.assertEqual(j["description"], "hello world")
        self.assertEqual(j["description_full"], "hello world")
        self.assertEqual(j["description_status"], "full")
        self.assertEqual(j["description_method"], "test_method")
        self.assertEqual(j["description_source_url"], "https://detail.com/1")
        self.assertIn("description_fetched_at", j)

    def test_error_recorded_and_cleared(self):
        j = _job()
        set_description(j, "", "unavailable", "m", error="boom")
        self.assertEqual(j["description_error"], "boom")
        set_description(j, "text", "full", "m2")
        self.assertNotIn("description_error", j)

    def test_none_text_becomes_empty(self):
        j = _job()
        set_description(j, None, "empty", "m")
        self.assertEqual(j["description"], "")
        self.assertEqual(j["description_full"], "")

    def test_full_never_truncated(self):
        j = _job()
        big = "z" * 9000
        set_description(j, big, "full", "m")
        self.assertEqual(len(j["description_full"]), 9000)
        self.assertEqual(len(j["description"]), 9000)

    def test_source_url_falls_back_to_job_url(self):
        j = _job(url="https://fallback.com/9")
        set_description(j, "t", "partial", "m")
        self.assertEqual(j["description_source_url"], "https://fallback.com/9")


class TestClassifyLength(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(_classify_length(""), "empty")
        self.assertEqual(_classify_length("   "), "empty")
        self.assertEqual(_classify_length(None), "empty")

    def test_short_is_partial(self):
        self.assertEqual(_classify_length("x" * 199), "partial")

    def test_long_is_still_only_partial(self):
        # KEY HONESTY CHECK: length alone must never yield 'full'.
        # 'full' requires verified complete retrieval, not character count.
        self.assertEqual(_classify_length("x" * 200), "partial")
        self.assertEqual(_classify_length("x" * 5000), "partial")
        self.assertEqual(_classify_length("x" * 100000), "partial")


# ===========================================================================
# adapt_linkedin
# ===========================================================================
class TestAdaptLinkedIn(unittest.TestCase):
    def test_full_description_accepted(self):
        j = _job(source="linkedin", description="d" * 900,
                 url="https://linkedin.com/jobs/view/1")
        self.assertTrue(adapt_linkedin(j))
        self.assertEqual(j["description_status"], "full")
        self.assertEqual(j["description_method"], "jobspy_api")

    def test_exactly_800_is_full(self):
        j = _job(source="linkedin", description="d" * 800)
        self.assertTrue(adapt_linkedin(j))
        self.assertEqual(j["description_status"], "full")

    def test_799_is_partial(self):
        j = _job(source="linkedin", description="d" * 799)
        self.assertFalse(adapt_linkedin(j))
        self.assertEqual(j["description_status"], "partial")
        self.assertIn("truncated", j["description_error"])

    def test_empty_is_unavailable(self):
        j = _job(source="linkedin", description="",
                 url="https://linkedin.com/jobs/view/2")
        self.assertFalse(adapt_linkedin(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "jobspy_empty")
        self.assertIn("auth", j["description_error"].lower())

    def test_whitespace_only_is_unavailable(self):
        j = _job(source="linkedin", description="   \n  ")
        self.assertFalse(adapt_linkedin(j))
        self.assertEqual(j["description_status"], "unavailable")

    def test_never_attempts_network(self):
        # LinkedIn detail pages are bot-walled; the adapter must not fetch.
        j = _job(source="linkedin", description="",
                 url="https://linkedin.com/jobs/view/3")
        with patch("extract.fetch_with_retry") as fr:
            adapt_linkedin(j)
        fr.assert_not_called()


# ===========================================================================
# adapt_arc
# ===========================================================================
def _arc_page(payload_obj):
    payload = json.dumps(payload_obj)
    return (f'<html><body><script id="__NEXT_DATA__" type="application/json">'
            f'{payload}</script></body></html>')


class TestAdaptArc(unittest.TestCase):
    def _ok_job(self):
        return _job(source="arc",
                    url="https://arc.dev/remote-jobs/details/ai-eng-abc123")

    def test_success_extracts_nested_description(self):
        desc_html = "<p>" + "Build AI systems. " * 30 + "</p>"
        page = _arc_page({"props": {"pageProps": {"job": {
            "title": "AI Engineer", "description": desc_html}}}})
        j = self._ok_job()
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            self.assertTrue(adapt_arc(j))
        self.assertEqual(j["description_status"], "full")
        self.assertEqual(j["description_method"], "arc_next_data")
        self.assertIn("Build AI systems", j["description"])
        self.assertNotIn("<p>", j["description"], "HTML must be stripped")

    def test_alternate_field_names(self):
        for key in ("jobDescription", "details", "aboutRole"):
            page = _arc_page({"x": {key: "<div>" + "y" * 400 + "</div>"}})
            j = self._ok_job()
            with patch("extract.fetch_with_retry", return_value=(page, None)):
                self.assertTrue(adapt_arc(j), f"field {key} not found")
            self.assertEqual(j["description_status"], "full")

    def test_deeply_nested_list_payload(self):
        page = _arc_page({"a": [{"b": {"description": "<p>" + "z" * 400 + "</p>"}}]})
        j = self._ok_job()
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            self.assertTrue(adapt_arc(j))
        self.assertEqual(j["description_status"], "full")

    def test_non_arc_url_rejected(self):
        j = _job(source="arc", url="https://example.com/jobs/1")
        with patch("extract.fetch_with_retry") as fr:
            self.assertFalse(adapt_arc(j))
        fr.assert_not_called()
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "arc_no_detail_url")

    def test_missing_url_rejected(self):
        j = _job(source="arc", url="")
        self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "unavailable")

    def test_blocked_fetch(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=(None, "http_403_blocked")):
            self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "blocked")
        self.assertIn("403", j["description_error"])

    def test_failed_fetch_unavailable(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=(None, "retry_exhausted(TimeoutError)")):
            self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "unavailable")

    def test_missing_next_data(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=("<html><body>Cloudflare challenge</body></html>", None)):
            self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "arc_next_data_missing")

    def test_invalid_json(self):
        j = self._ok_job()
        bad = ('<script id="__NEXT_DATA__" type="application/json">'
               '{not valid json</script>')
        with patch("extract.fetch_with_retry", return_value=(bad, None)):
            self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "arc_next_data_parse")

    def test_no_description_field(self):
        j = self._ok_job()
        page = _arc_page({"props": {"pageProps": {"job": {"title": "x"}}}})
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertIn("no description field", j["description_error"])

    def test_short_description_not_picked_up(self):
        # _walk requires >300 chars to even consider a field; a short
        # description is skipped entirely -> 'unavailable', not 'partial'.
        j = self._ok_job()
        page = _arc_page({"description": "<p>" + "short. " * 20 + "</p>"})  # ~147 chars
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            result = adapt_arc(j)
        self.assertFalse(result)
        self.assertEqual(j["description_status"], "unavailable")
        self.assertIn("no description field", j["description_error"])

    def test_301_chars_is_full(self):
        # _walk needs strictly >300; the final check is >=300.
        j = self._ok_job()
        page = _arc_page({"description": "<p>" + "q" * 301 + "</p>"})
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            self.assertTrue(adapt_arc(j))
        self.assertEqual(j["description_status"], "full")

    def test_exactly_300_chars_with_tags_is_full(self):
        # _walk counts raw HTML (tags included): "<p>"+300 chars+"</p>" = 307
        # > 300 -> picked up; stripped to 300 -> >= 300 -> 'full'.
        j = self._ok_job()
        page = _arc_page({"description": "<p>" + "q" * 300 + "</p>"})
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            self.assertTrue(adapt_arc(j))
        self.assertEqual(j["description_status"], "full")

    def test_300_chars_no_tags_rejected_by_walk(self):
        # Without tags, exactly 300 chars fails the strict '> 300' _walk gate.
        j = self._ok_job()
        page = _arc_page({"description": "q" * 300})
        with patch("extract.fetch_with_retry", return_value=(page, None)):
            self.assertFalse(adapt_arc(j))
        self.assertEqual(j["description_status"], "unavailable")


# ===========================================================================
# adapt_smartrecruiters
# ===========================================================================
def _sr_api_response(job_text_len=500, include_company=True):
    sections = {
        "jobDescription": {"text": "<p>" + "J" * job_text_len + "</p>"},
        "qualifications": {"text": "<ul><li>Python</li></ul>"},
    }
    jd = {"sections": sections}
    if include_company:
        jd["companyDescription"] = {"text": "<p>We are Acme.</p>"}
    return json.dumps({"jobAd": jd})


class TestAdaptSmartRecruiters(unittest.TestCase):
    def _ok_job(self, url="https://jobs.smartrecruiters.com/AcmeCorp/abcdef12-senior"):
        return _job(source="ats:smartrecruiters", url=url)

    def test_success_full(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=(_sr_api_response(), None)) as fr:
            self.assertTrue(adapt_smartrecruiters(j))
        self.assertEqual(j["description_status"], "full")
        self.assertEqual(j["description_method"], "sr_api")
        self.assertIn("api.smartrecruiters.com", j["description_source_url"])
        self.assertIn("We are Acme", j["description_full"])
        # called the detail API, not the listing page
        called_url = fr.call_args.args[0]
        self.assertIn("/v1/companies/AcmeCorp/postings/abcdef12", called_url)

    def test_company_and_id_from_url_parsing(self):
        j = _job(source="ats:smartrecruiters",
                 url="https://jobs.smartrecruiters.com/MyCo/ABCDEF12-xyz")
        with patch("extract.fetch_with_retry",
                   return_value=(_sr_api_response(), None)) as fr:
            adapt_smartrecruiters(j)
        called_url = fr.call_args.args[0]
        self.assertIn("/companies/MyCo/postings/ABCDEF12", called_url)

    def test_explicit_sr_ids_take_precedence(self):
        j = self._ok_job(url="https://jobs.smartrecruiters.com/Other/11111111-x")
        j["_sr_company"] = "RealCo"
        j["_sr_id"] = "22222222"
        with patch("extract.fetch_with_retry",
                   return_value=(_sr_api_response(), None)) as fr:
            adapt_smartrecruiters(j)
        self.assertIn("/companies/RealCo/postings/22222222",
                      fr.call_args.args[0])

    def test_no_ids_available(self):
        j = _job(source="ats:smartrecruiters",
                 url="https://jobs.smartrecruiters.com/AcmeCorp/some-job")
        with patch("extract.fetch_with_retry") as fr:
            self.assertFalse(adapt_smartrecruiters(j))
        fr.assert_not_called()
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "sr_no_ids")

    def test_empty_url(self):
        j = _job(source="ats:smartrecruiters", url="")
        self.assertFalse(adapt_smartrecruiters(j))
        self.assertEqual(j["description_status"], "unavailable")

    def test_blocked_api(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=(None, "http_403_blocked")):
            self.assertFalse(adapt_smartrecruiters(j))
        self.assertEqual(j["description_status"], "blocked")

    def test_api_failure_unavailable(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=(None, "retry_exhausted(TimeoutError: t)")):
            self.assertFalse(adapt_smartrecruiters(j))
        self.assertEqual(j["description_status"], "unavailable")

    def test_invalid_json(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=("not json{{{", None)):
            self.assertFalse(adapt_smartrecruiters(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "sr_api_parse")

    def test_empty_body(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry", return_value=("", None)):
            self.assertFalse(adapt_smartrecruiters(j))
        # "{}" -> no jobAd sections -> unavailable
        self.assertEqual(j["description_status"], "unavailable")

    def test_short_sections_partial(self):
        j = self._ok_job()
        with patch("extract.fetch_with_retry",
                   return_value=(_sr_api_response(job_text_len=100,
                                                  include_company=False), None)):
            result = adapt_smartrecruiters(j)
        self.assertEqual(j["description_status"], "partial")
        # NOTE: adapter returns bool(full) -> True even for partial; the
        # return value is ignored by enrich_description, but this is
        # inconsistent with adapt_linkedin/adapt_reddit which return False
        # for partial. Documented as-is.
        self.assertTrue(result)


# ===========================================================================
# adapt_reddit
# ===========================================================================
class TestAdaptReddit(unittest.TestCase):
    def test_post_with_employer_link(self):
        j = _job(source="reddit_rss",
                 description="Hiring engineers! Apply at https://acme.com/careers/123 for details.",
                 url="https://reddit.com/r/forhire/comments/abc")
        self.assertFalse(adapt_reddit(j))  # never claims full
        self.assertEqual(j["description_status"], "partial")
        self.assertEqual(j["_employer_url_candidate"], "https://acme.com/careers/123")
        self.assertIn("Hiring engineers", j["_reddit_post_body"])

    def test_post_without_link(self):
        j = _job(source="reddit_rss", description="Hiring! DM me for details.",
                 url="https://reddit.com/r/x/1")
        self.assertFalse(adapt_reddit(j))
        self.assertEqual(j["description_status"], "partial")
        self.assertNotIn("_employer_url_candidate", j)
        self.assertIn("no employer link", j["description_error"])

    def test_empty_body(self):
        j = _job(source="reddit_rss", description="",
                 url="https://reddit.com/r/x/1")
        self.assertFalse(adapt_reddit(j))
        self.assertEqual(j["description_status"], "empty")

    def test_reddit_urls_not_employer_candidates(self):
        j = _job(source="reddit_rss",
                 description="See https://reddit.com/r/other and https://redd.it/xyz",
                 url="https://reddit.com/r/forhire/comments/abc")
        adapt_reddit(j)
        self.assertNotIn("_employer_url_candidate", j)

    def test_never_returns_true(self):
        # A Reddit post body is never the complete official JD.
        j = _job(source="reddit_rss", description="x" * 5000,
                 url="https://reddit.com/r/x/1")
        self.assertFalse(adapt_reddit(j))
        self.assertNotEqual(j["description_status"], "full")


# ===========================================================================
# adapt_wad (mocked enrich module — no network)
# ===========================================================================
class TestAdaptWad(unittest.TestCase):
    def _inject_enrich(self, fn):
        mod = types.ModuleType("enrich")
        mod.enrich_wad_job = fn
        self._old = sys.modules.get("enrich")
        sys.modules["enrich"] = mod

    def tearDown(self):
        if getattr(self, "_old", None) is None:
            sys.modules.pop("enrich", None)
        else:
            sys.modules["enrich"] = self._old

    def test_success_full(self):
        def fake(job):
            job["description"] = "Complete JD. " * 40
            return True
        self._inject_enrich(fake)
        j = _job(source="wearedistributed", url="https://wearedistributed.org/job/x")
        self.assertTrue(adapt_wad(j))
        self.assertEqual(j["description_status"], "full")
        self.assertEqual(j["description_method"], "wad_jsonld")

    def test_short_description_partial(self):
        def fake(job):
            job["description"] = "Short."
            return True
        self._inject_enrich(fake)
        j = _job(source="wearedistributed", url="https://wearedistributed.org/job/x")
        self.assertFalse(adapt_wad(j))
        self.assertEqual(j["description_status"], "partial")

    def test_enrich_failure(self):
        def fake(job):
            return False
        self._inject_enrich(fake)
        j = _job(source="wearedistributed", url="https://wearedistributed.org/job/x")
        self.assertFalse(adapt_wad(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertIn("fetch failed", j["description_error"])

    def test_enrich_import_error(self):
        sys.modules.pop("enrich", None)
        self._old = None
        # block the real import by making it raise
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "enrich":
                raise ImportError("nope")
            return real_import(name, *a, **k)

        j = _job(source="wearedistributed")
        with patch("builtins.__import__", side_effect=fake_import):
            self.assertFalse(adapt_wad(j))
        self.assertEqual(j["description_status"], "unavailable")
        self.assertEqual(j["description_method"], "wad_enrich_missing")


# ===========================================================================
# enrich_description dispatcher
# ===========================================================================
class TestEnrichDescription(unittest.TestCase):
    def test_api_source_long_desc_no_network(self):
        j = _job(source="ats:greenhouse", description="g" * 1000)
        with patch("extract.fetch_with_retry") as fr:
            enrich_description(j)
        fr.assert_not_called()
        self.assertEqual(j["description_status"], "full")
        self.assertIn("api_complete", j["description_method"])

    def test_api_source_short_desc_partial(self):
        j = _job(source="ats:lever", description="short desc")
        enrich_description(j)
        self.assertEqual(j["description_status"], "partial")
        self.assertIn("api_partial", j["description_method"])

    def test_pre_classify_only_no_network(self):
        j = _job(source="linkedin", description="l" * 900,
                 url="https://linkedin.com/jobs/view/1")
        with patch("extract.fetch_with_retry") as fr:
            enrich_description(j, pre_classify_only=True)
        fr.assert_not_called()
        # 900 chars but NOT verified complete -> partial, never full
        self.assertEqual(j["description_status"], "partial")
        self.assertIn("pre_classify", j["description_method"])

    def test_pre_classify_empty(self):
        j = _job(source="arc", description="")
        enrich_description(j, pre_classify_only=True)
        self.assertEqual(j["description_status"], "empty")

    def test_unknown_source_with_text(self):
        j = _job(source="some_new_board", description="n" * 500)
        enrich_description(j)
        self.assertEqual(j["description_status"], "partial")
        self.assertIn("as_scraped", j["description_method"])

    def test_unknown_source_empty(self):
        j = _job(source="some_new_board", description="")
        enrich_description(j)
        self.assertEqual(j["description_status"], "empty")

    def test_adapter_exception_handled(self):
        j = _job(source="linkedin", description="")
        with patch("extract._ADAPTERS", {"linkedin": MagicMock(side_effect=RuntimeError("boom"))}):
            enrich_description(j)
        self.assertEqual(j["description_status"], "unavailable")
        self.assertIn("adapter_error", j["description_method"])
        self.assertIn("RuntimeError", j["description_error"])

    def test_adapters_registered(self):
        for key in ("linkedin", "arc", "ats:smartrecruiters",
                    "wearedistributed", "reddit_rss", "reddit_forhire"):
            self.assertIn(key, _ADAPTERS, f"adapter missing: {key}")


# ===========================================================================
# filter: geography
# ===========================================================================
class TestFilterGeography(unittest.TestCase):
    def _base_pass(self, **kw):
        j = _job(description=(_long_desc("Python Developer role. 1-2 years experience. ") ),
                 description_status="full",
                 location="Islamabad, Pakistan", remote=False,
                 title="Python Developer")
        j.update(kw)
        return j

    def test_local_islamabad_passes(self):
        r = filter_job(self._base_pass())
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "local")
        self.assertIn("geo_eligible", r["reason_codes"])
        self.assertEqual(r["confidence"], "high")

    def test_local_rawalpindi_passes(self):
        r = filter_job(self._base_pass(location="Rawalpindi, Pakistan"))
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "local")

    def test_local_karachi_passes(self):
        r = filter_job(self._base_pass(location="Karachi, Pakistan"))
        self.assertEqual(r["verdict"], "pass", r["reasons"])

    def test_local_abbreviations(self):
        for loc in ("RWP, Pakistan", "ISB", "Bahria Town, Rawalpindi"):
            r = filter_job(self._base_pass(location=loc))
            self.assertEqual(r["evidence_fields"]["geo_class"], "local", loc)

    def test_pakistan_eligible_remote_passes(self):
        j = self._base_pass(
            description=_long_desc("Remote AI Engineer. We are hiring in Pakistan. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "pk_remote")

    def test_worldwide_authoritative_passes(self):
        j = self._base_pass(
            description=_long_desc("Remote engineer. We hire worldwide, work from anywhere. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "worldwide")

    def test_marketing_worldwide_fluff_not_enough(self):
        # "developers worldwide" without hiring-scope language must not pass
        j = self._base_pass(
            description=_long_desc("Join our team of developers worldwide. Remote role. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertNotEqual(r["verdict"], "pass")
        self.assertEqual(r["verdict"], "review")

    def test_us_only_citizenship_fails(self):
        j = self._base_pass(
            description=_long_desc("US citizenship required. Remote AI Engineer. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("citizenship_gate", r["reason_codes"])

    def test_us_work_authorization_fails(self):
        # DEFECT: "Must have US work authorization." is not caught by any
        # CITIZENSHIP_HARD_GATE_PATTERNS entry. The patterns require
        # "work authorization (in|for)...required" or "US work authorization
        # required" - the bare "Must have US work authorization" phrasing
        # slips through to review. Do not fix here.
        j = self._base_pass(
            description=_long_desc("Must have US work authorization. Remote role. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("citizenship_gate", r["reason_codes"])

    def test_unknown_geography_review_never_pass(self):
        j = self._base_pass(
            description=_long_desc("Remote ML Engineer. 2 years experience with Python. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "review")
        self.assertIn("geo_unverified", r["reason_codes"])
        self.assertIn("hiring_country", r["missing_fields"])
        self.assertNotEqual(r["verdict"], "pass")

    def test_empty_location_remote_review(self):
        j = self._base_pass(
            description=_long_desc("Remote developer. 1 year experience. "),
            location="", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "review")
        self.assertIn("geo_unverified", r["reason_codes"])

    def test_foreign_city_location_fails(self):
        j = self._base_pass(
            description=_long_desc("Remote engineer. 1-2 years experience. "),
            location="Remote, Bangalore", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("location_out_of_scope", r["reason_codes"])

    def test_foreign_country_location_fails(self):
        j = self._base_pass(
            description=_long_desc("Remote engineer. 1-2 years experience. "),
            location="Remote, Germany", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("location_out_of_scope", r["reason_codes"])

    def test_loc_requirements_excluding_pakistan_fails(self):
        j = self._base_pass(
            description=_long_desc("Remote engineer. 1-2 years experience. "),
            location="Remote", remote=True,
            _loc_requirements=["United States", "Canada"])
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("location_out_of_scope", r["reason_codes"])

    def test_loc_requirements_including_pakistan_passes(self):
        j = self._base_pass(
            description=_long_desc("Remote engineer. 1-2 years experience. "),
            location="Remote", remote=True,
            _loc_requirements=["Pakistan", "India"])
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertEqual(r["evidence_fields"]["geo_class"], "pk_remote")

    def test_non_remote_non_pakistan_fails(self):
        j = self._base_pass(location="Austin, Texas", remote=False,
                            description=_long_desc("On-site engineer. 1-2 years experience. "))
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")

    def test_region_preference_goes_to_review(self):
        j = self._base_pass(
            description=_long_desc("Only candidates in Europe. Remote AI Engineer. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "review")
        self.assertIn("region_preference", r["reason_codes"])

    def test_onsite_abroad_in_description_fails(self):
        j = self._base_pass(
            description=_long_desc("Based in our New York City office. In-office 3 days per week. 1-2 years experience. "),
            location="Remote", remote=True)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("onsite_abroad", r["reason_codes"])


# ===========================================================================
# filter: experience
# ===========================================================================
class TestFilterExperience(unittest.TestCase):
    def _base(self, desc_text):
        return _job(description=_long_desc(desc_text),
                    description_status="full",
                    location="Islamabad, Pakistan", remote=False)

    def test_range_2_4_ambiguous_review(self):
        r = filter_job(self._base("Requires 2-4 years of experience with Python. "))
        self.assertEqual(r["verdict"], "review")
        self.assertIn("exp_ambiguous_range", r["reason_codes"])
        self.assertEqual(r["confidence"], "medium")

    def test_range_1_3_within_cap(self):
        r = filter_job(self._base("Requires 1-3 years of experience. "))
        self.assertIn("exp_ok", r["reason_codes"])

    def test_mandatory_4_plus_fails(self):
        r = filter_job(self._base("Minimum 4 years of experience required. "))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("exp_exceeds_cap", r["reason_codes"])
        self.assertEqual(r["confidence"], "high")

    def test_at_least_5_years_fails(self):
        r = filter_job(self._base("At least 5 years experience needed. "))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("exp_exceeds_cap", r["reason_codes"])

    def test_3_plus_years_experience_fails(self):
        # "3+ years of experience" -> mandatory_min=3, mandatory_max=3; not >= 4...
        # pattern 1 captures "3+" as a single value
        r = filter_job(self._base("3+ years of experience required. "))
        # 3 is within cap -> should not fail on experience
        self.assertNotIn("exp_exceeds_cap", r["reason_codes"])

    def test_4_plus_years_experience_fails(self):
        r = filter_job(self._base("4+ years of experience required. "))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("exp_exceeds_cap", r["reason_codes"])

    def test_preferred_high_years_review(self):
        # SPEC: preferred (not mandatory) high years -> review, never fail/pass.
        # DEFECT: _exp_assessment sets preferred=5 AND none_found=False, so the
        # filter's `exp_preferred_high` branch (which requires none_found=True)
        # is dead code. Result is exp_ok -> can PASS. Do not fix here.
        r = filter_job(self._base("Preferred 5+ years of experience with LLMs. "))
        self.assertNotEqual(r["verdict"], "fail")
        self.assertEqual(r["verdict"], "review")

    def test_company_age_not_experience(self):
        r = filter_job(self._base("Join us! 5+ years in business and growing fast. Junior role. "))
        self.assertNotIn("exp_exceeds_cap", r["reason_codes"])

    def test_no_experience_mentioned(self):
        r = filter_job(self._base("Exciting AI Engineer opportunity. Apply now. "))
        self.assertIn("exp_unspecified", r["reason_codes"])

    def test_exp_assessment_unit(self):
        e = _exp_assessment("Requires 2-4 years of experience.")
        self.assertTrue(e["ambiguous"])
        self.assertEqual((e["mandatory_min"], e["mandatory_max"]), (2, 4))
        e2 = _exp_assessment("Minimum 4 years required.")
        self.assertGreaterEqual(e2["mandatory_min"], 4)
        e3 = _exp_assessment("No numbers here at all.")
        self.assertTrue(e3["none_found"])


# ===========================================================================
# filter: malformed records
# ===========================================================================
class TestFilterMalformed(unittest.TestCase):
    def test_missing_title(self):
        j = _job(title=None, description="Python developer role. " * 30,
                 description_status="full")
        r = filter_job(j)  # must not crash
        self.assertIn(r["verdict"], ("pass", "review", "fail"))

    def test_empty_dict(self):
        r = filter_job({})
        self.assertIn(r["verdict"], ("pass", "review", "fail"))
        self.assertEqual(r["ruleset_version"], RULESET_VERSION)

    def test_all_none_values(self):
        j = {k: None for k in ("source", "id", "title", "company", "description",
                               "description_status", "url", "apply_url",
                               "apply_email", "location", "remote",
                               "salary_min", "salary_max", "salary_unit",
                               "posted_at", "tags")}
        r = filter_job(j)
        self.assertIn(r["verdict"], ("pass", "review", "fail"))

    def test_none_description(self):
        j = _job(description=None, description_status=None)
        r = filter_job(j)
        self.assertIn(r["verdict"], ("pass", "review", "fail"))
        # None description -> empty status -> cannot pass
        self.assertNotEqual(r["verdict"], "pass")

    def test_naive_posted_at(self):
        j = _job(posted_at=datetime.now() - timedelta(days=1))  # naive
        r = filter_job(j)
        self.assertIn("freshness_ok", r["reason_codes"])

    def test_future_posted_at(self):
        j = _job(posted_at=NOW + timedelta(days=1))
        r = filter_job(j)  # must not crash on negative age
        self.assertIn(r["verdict"], ("pass", "review", "fail"))

    def test_stale_posting_fails(self):
        j = _job(posted_at=NOW - timedelta(days=60))
        r = filter_job(j)
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("stale_posting", r["reason_codes"])

    def test_non_string_description_status(self):
        # DEFECT: _desc_status does (job.get("description_status") or "").lower()
        # which raises AttributeError when description_status is a non-string
        # (e.g. int). A malformed record crashes filter_job instead of being
        # handled gracefully. Do not fix here.
        j = _job(description_status=123)
        r = filter_job(j)
        self.assertIn(r["verdict"], ("pass", "review", "fail"))


# ===========================================================================
# filter: never pass on empty/missing description
# ===========================================================================
class TestNeverPassOnEmptyDescription(unittest.TestCase):
    def _eligible_but_empty(self, **kw):
        j = _job(title="Python Developer",
                 location="Islamabad, Pakistan", remote=False,
                 description="", description_status="empty",
                 apply_url="https://boards.greenhouse.io/testco/jobs/1")
        j.update(kw)
        return j

    def test_local_empty_desc_review(self):
        r = filter_job(self._eligible_but_empty())
        self.assertNotEqual(r["verdict"], "pass")
        self.assertEqual(r["verdict"], "review")
        self.assertIn("no_pass_without_desc", r["reason_codes"])

    def test_pk_remote_empty_desc_review(self):
        r = filter_job(self._eligible_but_empty(
            description="", description_status="empty",
            location="Remote", remote=True,
            _loc_requirements=["Pakistan"]))
        self.assertNotEqual(r["verdict"], "pass")

    def test_unavailable_desc_review(self):
        r = filter_job(self._eligible_but_empty(description_status="unavailable"))
        self.assertNotEqual(r["verdict"], "pass")
        self.assertIn("job_description", r["missing_fields"])

    def test_blocked_desc_review(self):
        r = filter_job(self._eligible_but_empty(description_status="blocked"))
        self.assertNotEqual(r["verdict"], "pass")

    def test_partial_desc_can_still_pass(self):
        # partial is sufficient for pass (gates checked on available text)
        j = self._eligible_but_empty(
            description="Python Developer, Islamabad office. 1-2 years experience. " * 10,
            description_status="partial")
        r = filter_job(j)
        self.assertEqual(r["verdict"], "pass", r["reasons"])

    def test_unknown_date_never_passes(self):
        j = self._eligible_but_empty(
            description="Python Developer, Islamabad. 1-2 years. " * 15,
            description_status="full", posted_at=None)
        r = filter_job(j)
        self.assertNotEqual(r["verdict"], "pass")
        self.assertIn("no_pass_without_date", r["reason_codes"])


# ===========================================================================
# filter: title gates & routes
# ===========================================================================
class TestFilterTitleGates(unittest.TestCase):
    def test_senior_fails(self):
        for title in ("Senior AI Engineer", "Staff Engineer", "Lead Developer",
                      "Principal Engineer", "Engineering Manager"):
            r = filter_job(_job(title=title))
            self.assertEqual(r["verdict"], "fail", title)
            self.assertIn("senior_title", r["reason_codes"])

    def test_qa_fails(self):
        for title in ("QA Engineer", "SDET", "Test Automation Engineer"):
            r = filter_job(_job(title=title))
            self.assertEqual(r["verdict"], "fail", title)
            self.assertIn("qa_title", r["reason_codes"])

    def test_non_dev_fails(self):
        for title in ("Sales Engineer", "DevOps Engineer", "Security Engineer",
                      "iOS Developer"):
            r = filter_job(_job(title=title))
            self.assertEqual(r["verdict"], "fail", title)
            self.assertIn("non_dev_title", r["reason_codes"])

    def test_visa_wall_company_fails(self):
        r = filter_job(_job(company="GitLab", title="AI Engineer"))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("visa_wall_company", r["reason_codes"])

    def test_irrelevant_role_fails(self):
        r = filter_job(_job(title="Office Assistant",
                            description="Administrative work. " * 20))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("role_irrelevant", r["reason_codes"])

    def test_intern_title_review(self):
        j = _job(title="AI Engineering Intern",
                 description="AI engineering internship, Islamabad. " * 20,
                 description_status="full",
                 location="Islamabad", remote=False)
        r = filter_job(j)
        self.assertEqual(r["verdict"], "review")
        self.assertIn("intern_title", r["reason_codes"])


class TestFilterRoutes(unittest.TestCase):
    def _remote_ok(self, **kw):
        j = _job(description=_long_desc("Remote AI Engineer. Hiring in Pakistan. 1-2 years. "),
                 description_status="full", location="Remote", remote=True)
        j.update(kw)
        return j

    def test_easy_apply_blocked(self):
        r = filter_job(self._remote_ok(
            apply_url="https://www.linkedin.com/jobs/apply/123"))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("route_blocked", r["reason_codes"])

    def test_no_apply_route_fails(self):
        r = filter_job(self._remote_ok(apply_url="", url=""))
        self.assertEqual(r["verdict"], "fail")
        self.assertIn("route_blocked", r["reason_codes"])

    def test_direct_email_ok(self):
        r = filter_job(self._remote_ok(apply_email="jobs@acme.com"))
        self.assertEqual(r["verdict"], "pass", r["reasons"])
        self.assertIn("route_ok", r["reason_codes"])

    def test_linkedin_view_url_ok(self):
        r = filter_job(self._remote_ok(
            source="linkedin",
            apply_url="https://www.linkedin.com/jobs/view/12345"))
        self.assertIn("route_ok", r["reason_codes"])

    def test_linkedin_source_no_url_unverified(self):
        r = filter_job(self._remote_ok(source="linkedin", apply_url="",
                                       url="https://linkedin.com/jobs/view/1"))
        # apply_url empty -> url falls back? apply_url="" so url="" -> then
        # source==linkedin -> unverified
        self.assertEqual(r["verdict"], "review")
        self.assertIn("route_unverified", r["reason_codes"])


# ===========================================================================
# filter: structured output contract
# ===========================================================================
class TestFilterStructure(unittest.TestCase):
    def test_all_keys_present(self):
        r = filter_job(_job())
        for key in ("verdict", "reason_codes", "evidence_fields",
                    "missing_fields", "confidence", "ruleset_version",
                    "reasons"):
            self.assertIn(key, r, f"missing key: {key}")

    def test_verdict_values_valid(self):
        for kw in ({}, {"title": "Senior X"}, {"location": "Islamabad", "remote": False,
                   "description": "Python dev. " * 30, "title": "Python Developer"}):
            r = filter_job(_job(**kw))
            self.assertIn(r["verdict"], ("pass", "review", "fail"))
            self.assertIn(r["confidence"], ("high", "medium", "low"))

    def test_ruleset_version(self):
        r = filter_job(_job())
        self.assertEqual(r["ruleset_version"], RULESET_VERSION)
        self.assertEqual(RULESET_VERSION, "2026-10-09-p0")

    def test_reason_codes_are_stable_strings(self):
        r = filter_job(_job(title="Senior AI Engineer"))
        for code in r["reason_codes"]:
            self.assertIsInstance(code, str)
            self.assertTrue(code, "empty reason code")
            self.assertNotIn(" ", code, "codes must be snake_case")

    def test_desc_status_fallback_legacy_length(self):
        # Legacy jobs without description_status: length-based fallback.
        # NOTE: this trusts length alone, contrary to the module's stated
        # principle ("Never trust length alone"). Documented here as-is.
        self.assertEqual(_desc_status({"description": "x" * 900}), "full")
        self.assertEqual(_desc_status({"description": "x" * 500}), "partial")
        self.assertEqual(_desc_status({"description": ""}), "empty")
        self.assertEqual(_desc_status({"description_status": "FULL"}), "full")


if __name__ == "__main__":
    unittest.main()
