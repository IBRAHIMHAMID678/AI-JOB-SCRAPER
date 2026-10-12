"""Data persistence & dedup merge-safety tests.

Covers:
  1. Dedup merge field precedence (longer description wins; what is copied)
  2. Negative safety evidence preservation across merges
     (_loc_requirements, enriched locations)
  3. Distinct requisition IDs never merging (per dedup.py docstring contract)
  4. Same title+company with different locations never merging
  5. Fuzzy layer-4 threshold boundaries (similarity + token overlap)
  6. applied.json migration: STATUS_MAP coverage, unknown -> needs_review
     (never terminal), _original_status preserved, idempotency, backup
  7. Feedback persistence across evaluations (record -> reload -> effective),
     including the Jumio URL/no-URL regression and legacy records
  8. Atomic writes (tmp+replace) for save_feedback and migrate_applied

All writes go to temp dirs; production state is never touched.
Run: python3 -m unittest tests.test_persistence_dedup -v
"""
import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dedup
from dedup import deduplicate, canonical_url
import feedback
from feedback import (record_job_feedback, record_company_block,
                      job_suppressed, load_feedback, save_feedback,
                      canonical_job_id, job_identity_keys, SUPPRESSING)
import migrate_applied


def _job(**kw):
    base = {
        "id": "gh-test-1", "title": "AI Engineer", "company": "Acme",
        "description": "desc", "description_status": "full",
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "apply_url": "https://boards.greenhouse.io/acme/jobs/1",
        "apply_email": None, "location": "Remote", "remote": True,
        "salary_min": None, "salary_max": None, "salary_unit": None,
        "posted_at": None, "tags": [], "source": "ats:greenhouse",
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------- merge field precedence
class TestMergeFieldPrecedence(unittest.TestCase):
    def test_longer_description_wins_with_status(self):
        a = _job(description="short", description_status="partial",
                 url="https://x.com/jobs/1")
        b = _job(description="a much longer full description here",
                 description_full="a much longer full description here",
                 description_status="full", url="https://x.com/jobs/1")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        self.assertEqual(uniq[0]["description"], b["description"])
        self.assertEqual(uniq[0]["description_status"], "full")
        self.assertEqual(uniq[0]["description_full"], b["description_full"])

    def test_equal_length_keeps_first_record(self):
        a = _job(description="aaaa", location="Islamabad", url="https://x.com/jobs/2")
        b = _job(description="bbbb", location="Lahore", url="https://x.com/jobs/2")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        # strict greater-than: equal length -> first record's data kept
        self.assertEqual(uniq[0]["description"], "aaaa")
        self.assertEqual(uniq[0]["location"], "Islamabad")

    def test_salary_copied_when_longer_record_has_it(self):
        a = _job(description="short", url="https://x.com/jobs/3")
        b = _job(description="a much longer description with salary",
                 salary_min=30, salary_max=50, salary_unit="hourly",
                 url="https://x.com/jobs/3")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(uniq[0]["salary_min"], 30)
        self.assertEqual(uniq[0]["salary_unit"], "hourly")

    def test_salary_from_dropped_record_is_preserved(self):
        """Salary on the shorter-description record must not silently vanish."""
        a = _job(description="a very long description " * 10, url="https://x.com/jobs/4")
        b = _job(description="short", salary_min=50, salary_max=80,
                 salary_unit="hourly", url="https://x.com/jobs/4")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        self.assertEqual(uniq[0]["salary_min"], 50,
                         "salary from merged duplicate was discarded")

    def test_apply_url_updated_from_longer_record(self):
        a = _job(description="short", apply_url="https://x.com/apply-old",
                 url="https://x.com/jobs/5")
        b = _job(description="a much longer description here",
                 apply_url="https://x.com/apply-new", url="https://x.com/jobs/5")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(uniq[0]["apply_url"], "https://x.com/apply-new")

    def test_dedup_sources_accumulate(self):
        a = _job(source="ats:greenhouse", url="https://x.com/jobs/6")
        b = _job(source="wwr", url="https://x.com/jobs/6")
        c = _job(source="wwr", url="https://x.com/jobs/6")  # same source twice
        uniq, log = deduplicate([copy.deepcopy(a), copy.deepcopy(b), copy.deepcopy(c)])
        self.assertEqual(len(uniq), 1)
        self.assertEqual(sorted(uniq[0]["_dedup_sources"]), ["ats:greenhouse", "wwr"])
        self.assertEqual(uniq[0]["_dedup_merged"], 2)
        self.assertEqual(len(log), 2)
        for m in log:
            self.assertIn("layer", m)
            self.assertIn("reason", m)


# ------------------------------------------------- negative evidence preservation
class TestNegativeEvidencePreserved(unittest.TestCase):
    def test_loc_requirements_survive_merge(self):
        """Structured hiring-region gates must not be dropped on merge."""
        a = _job(id="gh-lr-1", description="short", url="https://x.com/jobs/10")
        b = _job(id="gh-lr-1", description="a much longer description here",
                 url="https://x.com/jobs/10?utm_source=z",
                 _loc_requirements=["United States"])
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        self.assertEqual(uniq[0].get("_loc_requirements"), ["United States"],
                         "_loc_requirements lost during merge")

    def test_enriched_location_not_overwritten(self):
        """A location enriched with hiring-restriction info must survive when
        the merged record has a longer description but a blander location."""
        a = _job(id="gh-lr-2", description="short",
                 location="Remote [hiring: United States]", url="https://x.com/jobs/11")
        b = _job(id="gh-lr-2", description="a much longer description here",
                 location="Remote", url="https://x.com/jobs/11")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        self.assertIn("United States", uniq[0]["location"],
                      "enriched hiring restriction was overwritten on merge")

    def test_kept_record_loc_requirements_survive(self):
        """When the kept (first) record carries the gate info, it stays."""
        a = _job(id="gh-lr-3", description="short", url="https://x.com/jobs/12",
                 _loc_requirements=["Canada"])
        b = _job(id="gh-lr-3", description="a much longer description here",
                 url="https://x.com/jobs/12")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(uniq[0].get("_loc_requirements"), ["Canada"])


# ------------------------------------------------------- distinct requisitions
class TestDistinctRequisitions(unittest.TestCase):
    def test_different_stable_ids_do_not_merge(self):
        """dedup.py docstring: 'different ATS ids ... stay separate'."""
        a = _job(id="gh-req-1", title="AI Engineer", company="Acme",
                 location="Remote", url="https://boards.greenhouse.io/acme/jobs/1")
        b = _job(id="gh-req-2", title="AI Engineer", company="Acme",
                 location="Remote", url="https://boards.greenhouse.io/acme/jobs/2")
        uniq, log = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 2,
                         "distinct requisition IDs were merged")
        self.assertEqual(len(log), 0)

    def test_same_title_company_different_locations_no_merge(self):
        a = _job(id="gh-loc-1", title="AI Engineer", company="Acme",
                 location="Remote", url="https://x.com/jobs/20")
        b = _job(id="gh-loc-2", title="AI Engineer", company="Acme",
                 location="Islamabad", url="https://x.com/jobs/21")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 2)

    def test_same_title_different_companies_no_merge(self):
        a = _job(id="gh-nc-1", title="AI Engineer", company="Acme",
                 location="Remote", url="https://x.com/jobs/22")
        b = _job(id="gh-nc-2", title="AI Engineer", company="Globex",
                 location="Remote", url="https://x.com/jobs/23")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 2)

    def test_same_stable_id_merges(self):
        """Positive control: identical stable IDs must merge."""
        a = _job(id="gh-same-1", source="ats:greenhouse", url="https://x.com/jobs/24")
        b = _job(id="gh-same-1", source="wwr", url="https://other.com/jobs/99")
        uniq, log = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 1)
        self.assertTrue(log[0]["layer"].startswith("layer1"))


# ---------------------------------------------------------- fuzzy boundaries
class TestFuzzyBoundaries(unittest.TestCase):
    def _pair(self, t1, t2, **kw):
        a = _job(id="xx-f1", title=t1, company="Acme", location="Remote",
                 url="https://x.com/fuzzy/1", **kw)
        b = _job(id="yy-f2", title=t2, company="Acme", location="Remote",
                 url="https://y.com/fuzzy/2")
        return [a, b]

    def test_fuzzy_above_threshold_merges(self):
        # sim=0.912 >= 0.88, overlap=4 >= 3 -> layer4 merge
        jobs = self._pair("Applied AI Engineer, Growth",
                          "Applied AI Engineer Growth Team")
        uniq, log = deduplicate([copy.deepcopy(j) for j in jobs])
        self.assertEqual(len(uniq), 1)
        self.assertTrue(log[0]["layer"].startswith("layer4"))

    def test_fuzzy_low_overlap_no_merge(self):
        # sim=0.895 but overlap=2 < 3 -> no merge
        jobs = self._pair("Applied AI Engineer", "Applied ML Engineer")
        uniq, log = deduplicate([copy.deepcopy(j) for j in jobs])
        self.assertEqual(len(uniq), 2)

    def test_fuzzy_low_similarity_no_merge(self):
        # overlap=3 but sim=0.815 < 0.88 -> no merge
        jobs = self._pair("Junior Data Platform Engineer",
                          "Data Platform Engineer Associate")
        uniq, _ = deduplicate([copy.deepcopy(j) for j in jobs])
        self.assertEqual(len(uniq), 2)

    def test_fuzzy_different_location_no_merge(self):
        a = _job(id="xx-f3", title="Applied AI Engineer, Growth",
                 company="Acme", location="Remote", url="https://x.com/fuzzy/3")
        b = _job(id="yy-f4", title="Applied AI Engineer Growth Team",
                 company="Acme", location="Berlin", url="https://y.com/fuzzy/4")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 2)

    def test_fuzzy_different_company_no_merge(self):
        a = _job(id="xx-f5", title="Applied AI Engineer, Growth",
                 company="Acme", location="Remote", url="https://x.com/fuzzy/5")
        b = _job(id="yy-f6", title="Applied AI Engineer Growth Team",
                 company="Globex", location="Remote", url="https://y.com/fuzzy/6")
        uniq, _ = deduplicate([copy.deepcopy(a), copy.deepcopy(b)])
        self.assertEqual(len(uniq), 2)


# ------------------------------------------------------------------ migration
class TestMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_base = migrate_applied.BASE
        self.orig_applied = migrate_applied.APPLIED
        self.orig_dry = migrate_applied.DRY
        migrate_applied.BASE = self.tmp
        migrate_applied.APPLIED = os.path.join(self.tmp, "applied.json")
        migrate_applied.DRY = False

    def tearDown(self):
        migrate_applied.BASE = self.orig_base
        migrate_applied.APPLIED = self.orig_applied
        migrate_applied.DRY = self.orig_dry

    def _write(self, records):
        with open(migrate_applied.APPLIED, "w") as f:
            json.dump(records, f)

    def _read(self):
        with open(migrate_applied.APPLIED) as f:
            return json.load(f)

    def test_status_map_covers_all_known_statuses(self):
        recs = [{"company": f"C{i}", "title": "T", "status": s}
                for i, s in enumerate(migrate_applied.STATUS_MAP)]
        self._write(recs)
        migrate_applied.main()
        out = self._read()
        for e, (old, new) in zip(out, migrate_applied.STATUS_MAP.items()):
            self.assertEqual(e["status"], new, f"{old} -> {new}")
            if new != old:
                self.assertEqual(e["_original_status"], old)

    def test_unknown_status_needs_review_never_terminal(self):
        self._write([{"company": "X", "title": "T", "status": "weird_future_status"}])
        migrate_applied.main()
        out = self._read()
        self.assertEqual(out[0]["status"], "needs_review")
        self.assertEqual(out[0]["_original_status"], "weird_future_status")
        self.assertNotIn("needs_review", migrate_applied.TERMINAL)

    def test_missing_and_empty_status_needs_review(self):
        self._write([
            {"company": "A", "title": "T"},
            {"company": "B", "title": "T", "status": ""},
            {"company": "C", "title": "T", "status": "   "},
            {"company": "D", "title": "T", "status": None},
        ])
        migrate_applied.main()
        out = self._read()
        for e in out:
            self.assertEqual(e["status"], "needs_review")
            self.assertIn("_original_status", e)

    def test_terminal_set_sane(self):
        for s in ("submitted", "submitted_confirmed", "sent", "applied",
                  "rejected", "dead", "blocked"):
            self.assertIn(s, migrate_applied.TERMINAL)
        for s in ("skipped", "pending", "needs_review"):
            self.assertNotIn(s, migrate_applied.TERMINAL,
                             f"{s} must stay suggestible, not terminal")

    def test_idempotent(self):
        recs = [
            {"company": "A", "title": "T", "status": "confirmed"},
            {"company": "B", "title": "T", "status": "mystery"},
            {"company": "C", "title": "T"},
            {"company": "D", "title": "T", "status": "submitted"},
        ]
        self._write(recs)
        migrate_applied.main()
        first = self._read()
        migrate_applied.main()
        second = self._read()
        self.assertEqual(first, second, "second migration run changed data")
        # second run: everything already canonical or needs_review
        statuses = [e["status"] for e in second]
        self.assertEqual(statuses,
                         ["submitted_confirmed", "needs_review", "needs_review", "submitted"])

    def test_backup_created_and_valid(self):
        recs = [{"company": "A", "title": "T", "status": "confirmed"}]
        self._write(recs)
        before = open(migrate_applied.APPLIED).read()
        migrate_applied.main()
        backups = [f for f in os.listdir(self.tmp) if f.startswith("applied.json.bak-")]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(self.tmp, backups[0])) as f:
            self.assertEqual(f.read(), before)


# ------------------------------------------------------- feedback persistence
class TestFeedbackPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = feedback.FEEDBACK_PATH
        feedback.FEEDBACK_PATH = os.path.join(self.tmp, "feedback.json")

    def tearDown(self):
        feedback.FEEDBACK_PATH = self.orig

    def test_record_reload_still_effective(self):
        """Simulate another evaluation: fresh load_feedback() must enforce."""
        job = {"company": "Jumio", "title": "Machine Learning Engineer",
               "url": "https://weworkremotely.com/remote-jobs/jumio-ml"}
        record_job_feedback(job, "dead", note="paywall")
        # "another evaluation": reload from disk, check suppression
        data = load_feedback()
        suppressed, why, via = job_suppressed(dict(job), data)
        self.assertTrue(suppressed)
        self.assertIn("dead", why)
        self.assertTrue(via, "suppression must explain which identity matched")

    def test_jumio_regression_url_vs_no_url(self):
        """The reported defect: feedback recorded with company+title only
        (no URL) must suppress the same job when a sweep later supplies a URL."""
        record_job_feedback({"company": "Jumio", "title": "Machine Learning Engineer"},
                            "dead", note="WWR paywall")
        sweep_job = {"company": "Jumio", "title": "Machine Learning Engineer",
                     "url": "https://weworkremotely.com/remote-jobs/jumio-machine-learning-engineer",
                     "id": "wwr-xyz"}
        suppressed, why, via = job_suppressed(sweep_job)
        self.assertTrue(suppressed, "URL/no-URL identity mismatch broke suppression")
        self.assertIn("ct:", via)

    def test_record_with_url_sweep_without_url(self):
        record_job_feedback({"company": "Acme", "title": "AI Engineer",
                             "url": "https://acme.com/jobs/1"}, "unsuitable")
        sweep_job = {"company": "Acme", "title": "AI Engineer"}  # no URL
        suppressed, _, via = job_suppressed(sweep_job)
        self.assertTrue(suppressed)
        self.assertIn("ct:", via)

    def test_both_urls_differ_no_suppress(self):
        """Conservative: same company+title but different URLs = distinct postings."""
        record_job_feedback({"company": "Acme", "title": "AI Engineer",
                             "url": "https://acme.com/jobs/1"}, "dead")
        sweep_job = {"company": "Acme", "title": "AI Engineer",
                     "url": "https://acme.com/jobs/2"}
        suppressed, _, _ = job_suppressed(sweep_job)
        self.assertFalse(suppressed, "over-suppressed distinct postings")

    def test_stable_id_match(self):
        record_job_feedback({"company": "Acme", "title": "AI Engineer",
                             "id": "gh-acme-123"}, "rejected")
        sweep_job = {"company": "Acme Corp", "title": "AI Engineer (Backend)",
                     "id": "gh-acme-123",
                     "url": "https://boards.greenhouse.io/acme/jobs/123"}
        suppressed, why, via = job_suppressed(sweep_job)
        self.assertTrue(suppressed)
        self.assertIn("stable_id", via)

    def test_legacy_record_reconstructed(self):
        """Records written before identity_keys existed must still work."""
        legacy = {"jobs": {
            "ct:jumio|machine learning engineer": {
                "company": "Jumio", "title": "Machine Learning Engineer",
                "url": "", "decision": "dead",
                "decided_at": "2026-10-09T00:00:00+00:00",
                "decided_by": "manual", "note": "legacy", "source": "manual",
            }}, "companies": {}}
        with open(feedback.FEEDBACK_PATH, "w") as f:
            json.dump(legacy, f)
        sweep_job = {"company": "Jumio", "title": "Machine Learning Engineer",
                     "url": "https://weworkremotely.com/remote-jobs/jumio-x"}
        suppressed, _, via = job_suppressed(sweep_job)
        self.assertTrue(suppressed, "legacy record not reconstructed")

    def test_useful_and_interview_do_not_suppress(self):
        for decision in ("useful", "interview", "offer", "applied"):
            job = {"company": f"Co-{decision}", "title": "AI Engineer",
                   "url": f"https://x.com/{decision}"}
            record_job_feedback(job, decision)
            suppressed, _, _ = job_suppressed(dict(job))
            self.assertFalse(suppressed, f"{decision} should not suppress")

    def test_non_suppressing_decisions_listed(self):
        self.assertEqual(SUPPRESSING, {"dead", "unsuitable", "rejected"})

    def test_company_block(self):
        record_company_block("SpamCorp", "spam")
        suppressed, why, via = job_suppressed({"company": "SpamCorp", "title": "Dev"})
        self.assertTrue(suppressed)
        self.assertIn("company:", via)

    def test_invalid_decision_raises(self):
        with self.assertRaises(ValueError):
            record_job_feedback({"company": "X", "title": "Y"}, "bogus")

    def test_missing_values_not_wildcards(self):
        record_job_feedback({"company": "Acme", "title": "AI Engineer"}, "dead")
        suppressed, _, _ = job_suppressed({"company": "", "title": ""})
        self.assertFalse(suppressed)
        suppressed2, _, _ = job_suppressed({})
        self.assertFalse(suppressed2)

    def test_repeated_evaluations_stable(self):
        job = {"company": "Jumio", "title": "ML Engineer",
               "url": "https://weworkremotely.com/remote-jobs/jumio-ml"}
        record_job_feedback(job, "dead")
        for _ in range(3):
            data = load_feedback()
            suppressed, _, _ = job_suppressed(dict(job), data)
            self.assertTrue(suppressed)


# ---------------------------------------------------------------- atomic writes
class TestAtomicWrites(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = feedback.FEEDBACK_PATH
        feedback.FEEDBACK_PATH = os.path.join(self.tmp, "feedback.json")

    def tearDown(self):
        feedback.FEEDBACK_PATH = self.orig

    def test_save_feedback_no_tmp_leftover(self):
        save_feedback({"jobs": {"a": 1}, "companies": {}})
        leftovers = [f for f in os.listdir(self.tmp) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        with open(feedback.FEEDBACK_PATH) as f:
            self.assertEqual(json.load(f)["jobs"], {"a": 1})

    def test_save_feedback_overwrite_not_partial(self):
        save_feedback({"jobs": {"a": 1}, "companies": {}})
        save_feedback({"jobs": {"b": 2}, "companies": {"c": 3}})
        with open(feedback.FEEDBACK_PATH) as f:
            data = json.load(f)
        self.assertEqual(data, {"jobs": {"b": 2}, "companies": {"c": 3}})

    def test_migrate_no_tmp_leftover(self):
        orig_base, orig_applied, orig_dry = (
            migrate_applied.BASE, migrate_applied.APPLIED, migrate_applied.DRY)
        try:
            migrate_applied.BASE = self.tmp
            migrate_applied.APPLIED = os.path.join(self.tmp, "applied.json")
            migrate_applied.DRY = False
            with open(migrate_applied.APPLIED, "w") as f:
                json.dump([{"company": "A", "title": "T", "status": "confirmed"}], f)
            migrate_applied.main()
            leftovers = [f for f in os.listdir(self.tmp) if f.endswith(".tmp")]
            self.assertEqual(leftovers, [], "tmp file left behind by migration")
            with open(migrate_applied.APPLIED) as f:
                out = json.load(f)
            self.assertEqual(out[0]["status"], "submitted_confirmed")
        finally:
            migrate_applied.BASE, migrate_applied.APPLIED, migrate_applied.DRY = (
                orig_base, orig_applied, orig_dry)


if __name__ == "__main__":
    unittest.main()
